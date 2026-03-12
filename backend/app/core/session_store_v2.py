"""
Session store com arquitetura de duas camadas:
  Layer 1: Redis  (velocidade, <1ms, TTL automático)
  Layer 2: Supabase (durabilidade, backup permanente)
Estratégia write-through: grava nos dois simultaneamente.
Em caso de falha do Redis, opera normalmente apenas via Supabase.
"""
import json
import logging
import os
from typing import Optional

from app.core.state import ConversationState
from app.core.supabase_client import get_supabase
from app.core.redis_client import get_redis_sync

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = int(os.getenv('SESSION_TTL_SECONDS', '1800'))

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
                # Dados corrompidos ou schema mudou — invalidar cache
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
    """Persiste estado no Supabase. Retorna True se exatamente 1 row foi atualizada."""
    try:
        supabase = get_supabase()
        from datetime import datetime, timezone
        result = supabase.table('conversations').update({
            'state': state.model_dump(mode='json'),
            'domain': state.domain,
            'frustration_level': state.frustration_level,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }).eq('tenant_id', tenant_id).eq('session_id', session_id).execute()
        
        # Verificar que exatamente 1 row foi atualizada
        rows = result.data if result.data else []
        if isinstance(rows, dict):
            rows = [rows]
        if len(rows) != 1:
            logger.error(
                f'Supabase set: expected 1 row updated, got {len(rows)} '
                f'for tenant={tenant_id} session={session_id}'
            )
            return False
        return True
    except Exception as e:
        logger.error(f'Supabase set error: {e}')
        return False

# ── INTERFACE PÚBLICA ───────────────────────────────────────────────
def get_session(tenant_id: str, session_id: str) -> Optional[ConversationState]:
    """
    Busca sessão com fallback automático:
    1. Tenta Redis (rápido)
    2. Se miss, busca no Supabase e repovoar Redis
    """
    # Layer 1: Redis
    state = _redis_get(tenant_id, session_id)
    if state:
        return state
        
    # Layer 2: Supabase (cache miss ou Redis indisponível)
    state = _supabase_get(tenant_id, session_id)
    if state:
        # Repovoar o Redis com o dado do Supabase
        _redis_set(tenant_id, session_id, state)
        logger.debug(f'Cache repopulated from Supabase for {session_id}')
    return state

def save_session(tenant_id: str, session_id: str, state: ConversationState) -> None:
    """
    Persiste sessão — Supabase primeiro (authoritative), Redis depois (cache).
    Se Supabase falhar, o cache Redis é invalidado para evitar state fantasma.
    """
    supabase_ok = _supabase_set(tenant_id, session_id, state)  # Layer 2 (authoritative)
    if supabase_ok:
        _redis_set(tenant_id, session_id, state)  # Layer 1 (cache, only on success)
    else:
        # Supabase falhou — não deixar estado órfão no Redis
        _redis_delete(tenant_id, session_id)
        logger.warning(f'Redis cache invalidated for {session_id} due to Supabase write failure')

def clear_session(tenant_id: str, session_id: str) -> None:
    """Remove sessão de ambos os layers."""
    _redis_delete(tenant_id, session_id)
    try:
        get_supabase().table('conversations').update({'state': {}}).\
            eq('tenant_id', tenant_id).eq('session_id', session_id).execute()
    except Exception as e:
        logger.warning(f'clear_session supabase error: {e}')

def cleanup_expired_sessions() -> int:
    """Redis faz TTL automático. Supabase é gerenciado via updated_at."""
    return 0
