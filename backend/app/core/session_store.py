"""Session store for maintaining conversation state across webhook calls.
This module provides in-memory session storage for WhatsApp conversations.
In production, this should be replaced with Redis or database-backed storage.
"""
import time
import logging
from typing import Optional
from app.core.state import ConversationState

logger = logging.getLogger(__name__)

# In-memory session store
# Key: "{tenant_id}:{session_id}" (e.g., "demo:5511999999999")
_session_store: dict[str, dict] = {}

# Session expiry time in seconds (30 minutes)
SESSION_TTL_SECONDS = 30 * 60


def _get_session_key(tenant_id: str, session_id: str) -> str:
    """Generate session key from tenant and session ID."""
    return f"{tenant_id}:{session_id}"


def get_session(tenant_id: str, session_id: str) -> Optional[ConversationState]:
    """Retrieve an existing session state."""
    key = _get_session_key(tenant_id, session_id)
    session = _session_store.get(key)
    
    if not session:
        return None
    
    # Check if session has expired
    if time.time() - session["last_activity"] > SESSION_TTL_SECONDS:
        del _session_store[key]
        return None
    
    return session["state"]


def save_session(tenant_id: str, session_id: str, state: ConversationState) -> None:
    """Save or update a session state."""
    # Adjustment 2: Lazy Cleanup (Option B)
    if len(_session_store) > 1000:
        cleaned = cleanup_expired_sessions()
        if cleaned > 0:
            logger.info(f"Lazy cleanup removed {cleaned} expired sessions")

    key = _get_session_key(tenant_id, session_id)
    _session_store[key] = {
        "state": state,
        "last_activity": time.time(),
    }


def clear_session(tenant_id: str, session_id: str) -> None:
    """Clear a session (e.g., after handoff or explicit end)."""
    key = _get_session_key(tenant_id, session_id)
    _session_store.pop(key, None)


def cleanup_expired_sessions() -> int:
    """Remove expired sessions from the store."""
    now = time.time()
    expired_keys = [
        key for key, session in _session_store.items()
        if now - session["last_activity"] > SESSION_TTL_SECONDS
    ]
    
    for key in expired_keys:
        del _session_store[key]
    
    return len(expired_keys)
