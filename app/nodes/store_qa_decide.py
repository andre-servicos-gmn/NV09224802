"""Store Q&A decision node - with memory-based strategies."""

from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def store_qa_decide(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Decide next step for Store Q&A based on memory state.
    
    Strategies:
    - handoff: if needs_handoff is true
    - ask_one_missing: if missing_info_needed has items and repeat_count < 2
    - rag_answer: default, use RAG to answer
    """
    if state.needs_handoff:
        state.next_step = "handoff"
        state.last_action = "route_to_handoff"
        state.last_action_success = True
        return state
    
    # Check if we need to ask for missing info (max 2 times to avoid loops)
    if state.missing_info_needed and state.repeat_count < 2:
        state.last_strategy = "ask_one_missing"
        state.next_step = "store_qa_respond"
        return state
    
    # Default: use RAG to answer
    state.last_strategy = "rag_answer"
    state.next_step = "store_qa_respond"
    return state

