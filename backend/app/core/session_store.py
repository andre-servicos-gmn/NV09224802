"""
SHIM: Este módulo re-exporta tudo de session_store_v2.

Mantido apenas para compatibilidade de imports legados.
Qualquer novo código deve importar diretamente de session_store_v2.
"""
from app.core.session_store_v2 import (
    get_session,
    save_session,
    clear_session,
    cleanup_expired_sessions,
    get_redis_health,
    SESSION_TTL_SECONDS,
)

__all__ = [
    "get_session",
    "save_session",
    "clear_session",
    "cleanup_expired_sessions",
    "get_redis_health",
    "SESSION_TTL_SECONDS",
]
