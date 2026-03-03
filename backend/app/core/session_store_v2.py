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
import redis

from app.core.state import ConversationState
from app.core.supabase_client import get_supabase

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = int(os.getenv('SESSION_TTL_SECONDS', '1800'))

_redis_client: Optional[redis.Redis] = None

def _get_redis() -> Optional[redis.Redis]:
    """Retorna cliente Redis (singleton). Retorna None se indisponível."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    
    url = os.getenv('REDIS_URL')
    if not url:
        return None
        
    try:
        client = redis.from_url(url, decode_responses=True, socket_timeout=2.0)
        client.ping()  # Valida conexão
        _redis_client = client
        logger.info('Redis conectado com sucesso')
        return _redis_client
    except Exception as e:
        logger.warning(f'Redis indisponível, usando apenas Supabase: {e}')
        return None

def _redis_key(tenant_id: str, session_id: str) -> str:
    return f"session:{tenant_id}:{session_id}"

# ── REDIS LAYER ─────────────────────────────────────────────────────
def _redis_get(tenant_id: str, session_id: str) -> Optional[ConversationState]:
    r = _get_redis()
    if not r:
        return None
    try:
        data = r.get(_redis_key(tenant_id, session_id))
        if data:
            return ConversationState(**json.loads(data))
        return None
    except Exception as e:
        logger.warning(f'Redis get error: {e}')
        return None

def _redis_set(tenant_id: str, session_id: str, state: ConversationState) -> None:
    r = _get_redis()
    if not r:
        return
    try:
        key = _redis_key(tenant_id, session_id)
        data = json.dumps(state.model_dump(mode='json'), ensure_ascii=False)
        r.setex(key, SESSION_TTL_SECONDS, data)
    except Exception as e:
        logger.warning(f'Redis set error: {e}')

def _redis_delete(tenant_id: str, session_id: str) -> None:
    r = _get_redis()
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

def _supabase_set(tenant_id: str, session_id: str, state: ConversationState) -> None:
    try:
        supabase = get_supabase()
        from datetime import datetime, timezone
        supabase.table('conversations').update({
            'state': state.model_dump(mode='json'),
            'domain': state.domain,
            'frustration_level': state.frustration_level,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }).eq('tenant_id', tenant_id).eq('session_id', session_id).execute()
    except Exception as e:
        logger.error(f'Supabase set error: {e}')

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
    Persiste sessão nos dois layers (write-through).
    Redis falha silenciosamente; Supabase é obrigatório.
    """
    _redis_set(tenant_id, session_id, state)   # Layer 1 (best-effort)
    _supabase_set(tenant_id, session_id, state) # Layer 2 (authoritative)

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

def get_redis_health() -> dict:
    """Retorna status de saúde do Redis para monitoramento."""
    r = _get_redis()
    if not r:
        return {'connected': False, 'reason': 'REDIS_URL not set or connection failed'}
    try:
        info = r.info('server')
        return {
            'connected': True,
            'version': info.get('redis_version'),
            'uptime_days': info.get('uptime_in_days'),
        }
    except Exception as e:
        return {'connected': False, 'reason': str(e)}
