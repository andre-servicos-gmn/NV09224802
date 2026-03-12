"""
Módulo centralizado de conexão Redis — Nouva PT

Fornece cliente sync e async via connection pool singleton.
Todos os consumidores (session_store, message_buffer, health check)
devem usar este módulo em vez de criar conexões próprias.

Padrão singleton inspirado em supabase_client.py (lru_cache).
"""

import logging
import os
from typing import Optional

import redis
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# ── Connection Pools (singletons) ──────────────────────────────────
_sync_pool: Optional[redis.ConnectionPool] = None
_async_pool: Optional[aioredis.ConnectionPool] = None

_SOCKET_TIMEOUT = 2.0
_SOCKET_CONNECT_TIMEOUT = 2.0


def _get_redis_url() -> Optional[str]:
    """Retorna REDIS_URL ou None se não configurado."""
    return os.getenv('REDIS_URL')


# ── SYNC CLIENT ────────────────────────────────────────────────────

def get_redis_sync() -> Optional[redis.Redis]:
    """
    Retorna cliente Redis síncrono via connection pool (singleton).
    Retorna None se REDIS_URL não estiver definido ou conexão falhar.
    """
    global _sync_pool

    url = _get_redis_url()
    if not url:
        return None

    try:
        if _sync_pool is None:
            _sync_pool = redis.ConnectionPool.from_url(
                url,
                decode_responses=True,
                socket_timeout=_SOCKET_TIMEOUT,
                socket_connect_timeout=_SOCKET_CONNECT_TIMEOUT,
                retry_on_timeout=True,
            )
            logger.info('Redis sync connection pool criado')

        client = redis.Redis(connection_pool=_sync_pool)
        # Ping leve para validar (apenas na primeira criação do pool)
        client.ping()
        return client
    except Exception as e:
        logger.warning(f'Redis sync indisponível: {e}')
        # Reset pool para tentar reconectar no próximo request
        _sync_pool = None
        return None


# ── ASYNC CLIENT ───────────────────────────────────────────────────

def get_redis_async() -> Optional[aioredis.Redis]:
    """
    Retorna cliente Redis assíncrono via connection pool (singleton).
    Retorna None se REDIS_URL não estiver definido ou pool falhar.

    Nota: Não faz ping aqui pois seria chamada async.
    O caller deve tratar exceções de conexão.
    """
    global _async_pool

    url = _get_redis_url()
    if not url:
        return None

    try:
        if _async_pool is None:
            _async_pool = aioredis.ConnectionPool.from_url(
                url,
                decode_responses=True,
                socket_timeout=_SOCKET_TIMEOUT,
                socket_connect_timeout=_SOCKET_CONNECT_TIMEOUT,
                retry_on_timeout=True,
            )
            logger.info('Redis async connection pool criado')

        return aioredis.Redis(connection_pool=_async_pool)
    except Exception as e:
        logger.warning(f'Redis async pool indisponível: {e}')
        _async_pool = None
        return None


# ── HEALTH CHECK ───────────────────────────────────────────────────

def get_redis_health() -> dict:
    """Retorna status de saúde do Redis para monitoramento."""
    r = get_redis_sync()
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
