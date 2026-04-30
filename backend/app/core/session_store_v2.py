"""
Session store com arquitetura de duas camadas:
  Layer 1: Redis  (velocidade, <1ms, TTL automático)
  Layer 2: Supabase (durabilidade, backup permanente)

CONTRATO:
  - Todas as funções públicas aceitam tenant_id como UUID (preferido)
    ou slug/nome (compat — gera warning).
  - Internamente, sempre opera com UUID. Slug/nome é resolvido na fronteira.
  - Após Sprint 1 fase 2B, callers devem passar SEMPRE UUID.
    Slug-as-input é depreciado mas suportado.

Estratégia write-through: grava nos dois simultaneamente.
Em caso de falha do Redis, opera normalmente apenas via Supabase.
"""
import json
import logging
import os
import re
from typing import Optional

from app.core.state import ConversationState
from app.core.supabase_client import get_supabase
from app.core.redis_client import get_redis_sync

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = int(os.getenv('SESSION_TTL_SECONDS', '1800'))

_UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


def _ensure_uuid(tenant_id_or_slug: str) -> Optional[str]:
    """Garante que o valor retornado é um UUID válido de tenant.

    Aceita UUID (pass-through) ou nome/slug (lookup via TenantRegistry).
    Retorna None se não conseguir resolver — caller deve tratar como erro fatal.

    Esta função é o cinto de segurança contra slug/UUID mismatch com o Postgres.
    O ideal é que callers sempre passem UUID; esta camada é de compatibilidade.
    """
    if not tenant_id_or_slug:
        logger.error('[session_store_v2] _ensure_uuid recebeu valor vazio')
        return None

    if _UUID_PATTERN.match(tenant_id_or_slug):
        return tenant_id_or_slug

    # Não é UUID — resolver via TenantRegistry (lazy import para evitar circular)
    try:
        from app.core.tenancy import TenantRegistry
        registry = TenantRegistry()
        tenant = registry.get(tenant_id_or_slug, use_cache=True)
        resolved = tenant.uuid
        if resolved and _UUID_PATTERN.match(resolved):
            logger.warning(
                f'[session_store_v2] Resolvido "{tenant_id_or_slug}" -> UUID "{resolved}". '
                f'CALLER DEVERIA PASSAR UUID DIRETO.'
            )
            return resolved
        logger.error(
            f'[session_store_v2] Tenant "{tenant_id_or_slug}" encontrado mas sem UUID válido: {resolved!r}'
        )
        return None
    except Exception as e:
        logger.error(
            f'[session_store_v2] Falha ao resolver tenant "{tenant_id_or_slug}": {e}'
        )
        return None


def _redis_key(tenant_id: str, session_id: str) -> str:
    return f"session:{tenant_id}:{session_id}"


# ── REDIS LAYER ─────────────────────────────────────────────────────
def _redis_get(tenant_id: str, session_id: str) -> Optional[ConversationState]:
    r = get_redis_sync()
    if not r:
        return None
    try:
        data = r.get(_redis_key(tenant_id, session_id))
        if data:
            try:
                return ConversationState(**json.loads(data))
            except Exception as e:
                logger.warning(f'Redis deserialize error (invalidating key): {e}')
                try:
                    r.delete(_redis_key(tenant_id, session_id))
                except Exception:
                    pass
                return None
        return None
    except Exception as e:
        logger.warning(f'Redis get error: {e}')
        return None


def _redis_set(tenant_id: str, session_id: str, state: ConversationState) -> None:
    r = get_redis_sync()
    if not r:
        return
    try:
        key = _redis_key(tenant_id, session_id)
        data = json.dumps(state.model_dump(mode='json'), ensure_ascii=False)
        r.setex(key, SESSION_TTL_SECONDS, data)
    except Exception as e:
        logger.warning(f'Redis set error: {e}')


def _redis_delete(tenant_id: str, session_id: str) -> None:
    r = get_redis_sync()
    if not r:
        return
    try:
        r.delete(_redis_key(tenant_id, session_id))
    except Exception as e:
        logger.warning(f'Redis delete error: {e}')


# ── SUPABASE LAYER ──────────────────────────────────────────────────
def _supabase_get(tenant_id: str, session_id: str) -> Optional[ConversationState]:
    try:
        supabase = get_supabase()
        result = (
            supabase.table('conversations')
            .select('state, updated_at')
            .eq('tenant_id', tenant_id)
            .eq('session_id', session_id)
            .single()
            .execute()
        )
        if not result.data:
            return None

        state_dict = result.data.get('state') or {}
        if not state_dict:
            return None

        return ConversationState(**state_dict)
    except Exception as e:
        logger.warning(f'Supabase get error: {e}')
        return None


def _supabase_set(tenant_id: str, session_id: str, state: ConversationState) -> bool:
    """Persiste estado no Supabase. tenant_id DEVE ser UUID já resolvido."""
    try:
        supabase = get_supabase()
        from datetime import datetime, timezone
        result = supabase.table('conversations').update({
            'state': state.model_dump(mode='json'),
            'domain': state.domain,
            'frustration_level': state.frustration_level,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }).eq('tenant_id', tenant_id).eq('session_id', session_id).execute()

        rows = result.data if result.data else []
        if isinstance(rows, dict):
            rows = [rows]
        if len(rows) != 1:
            logger.error(
                f'[_supabase_set] UPDATE não atualizou 1 row '
                f'(tenant_uuid={tenant_id}, session_id={session_id}, rows={len(rows)}). '
                f'Possíveis causas: (1) conversation não existe ainda, (2) UUID errado, '
                f'(3) session_id mismatch. State NÃO foi persistido.'
            )
            return False
        return True
    except Exception as e:
        logger.error(
            f'[_supabase_set] EXCEPTION durante UPDATE '
            f'(tenant_uuid={tenant_id}, session_id={session_id}): {e}',
            exc_info=True,
        )
        return False


# ── INTERFACE PÚBLICA ───────────────────────────────────────────────
def get_session(tenant_id: str, session_id: str) -> Optional[ConversationState]:
    """Busca sessão com fallback: Redis → Supabase.

    tenant_id pode ser UUID (preferido) ou nome/slug (compat, gera warning).
    """
    tenant_uuid = _ensure_uuid(tenant_id)
    if not tenant_uuid:
        logger.error(
            f'[get_session] ABORTED: não foi possível resolver tenant_id="{tenant_id}" '
            f'para session={session_id}.'
        )
        return None

    state = _redis_get(tenant_uuid, session_id)
    if state:
        return state

    state = _supabase_get(tenant_uuid, session_id)
    if state:
        _redis_set(tenant_uuid, session_id, state)
        logger.debug(f'Cache repopulated from Supabase for {session_id}')
    return state


def save_session(tenant_id: str, session_id: str, state: ConversationState) -> None:
    """Persiste sessão — Supabase primeiro (authoritative), Redis depois (cache).

    tenant_id pode ser UUID (preferido) ou nome/slug (compat, gera warning).
    Se Supabase falhar, o cache Redis é invalidado para evitar state fantasma.
    """
    tenant_uuid = _ensure_uuid(tenant_id)
    if not tenant_uuid:
        logger.error(
            f'[save_session] ABORTED: não foi possível resolver tenant_id="{tenant_id}". '
            f'State NÃO foi salvo para session={session_id}.'
        )
        return

    supabase_ok = _supabase_set(tenant_uuid, session_id, state)
    if supabase_ok:
        _redis_set(tenant_uuid, session_id, state)
    else:
        _redis_delete(tenant_uuid, session_id)
        logger.warning(f'Redis cache invalidated for {session_id} due to Supabase write failure')


def clear_session(tenant_id: str, session_id: str) -> None:
    """Remove sessão de ambos os layers.

    tenant_id pode ser UUID (preferido) ou nome/slug (compat, gera warning).
    """
    tenant_uuid = _ensure_uuid(tenant_id)
    if not tenant_uuid:
        logger.error(
            f'[clear_session] ABORTED: não foi possível resolver tenant_id="{tenant_id}" '
            f'para session={session_id}.'
        )
        return

    _redis_delete(tenant_uuid, session_id)
    try:
        get_supabase().table('conversations').update({'state': {}}) \
            .eq('tenant_id', tenant_uuid).eq('session_id', session_id).execute()
    except Exception as e:
        logger.warning(f'clear_session supabase error: {e}')


def cleanup_expired_sessions() -> int:
    """Redis faz TTL automático. Supabase é gerenciado via updated_at."""
    return 0
