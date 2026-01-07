"""Store Q&A decision node - simplified to always use RAG."""

from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def store_qa_decide(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Decide next step for Store Q&A - always use RAG respond unless handoff needed."""
    if state.needs_handoff:
        state.next_step = "handoff"
        state.last_action = "route_to_handoff"
        state.last_action_success = True
    else:
        # Always go to respond with RAG - no FAQ action needed
        state.next_step = "store_qa_respond"
    return state
