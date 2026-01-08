"""Store Q&A decision node - with memory-based strategies."""

import os
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def store_qa_decide(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Decide next step for Store Q&A based on memory state.
    
    Strategies:
    - handoff: if needs_handoff is true
    - ask_one_missing: if missing_info_needed has items and repeat_count < 2
    - rag_answer: default, use RAG to answer
    """
    # Path A: Handoff needed
    if state.needs_handoff:
        state.next_step = "handoff"
        state.last_action = "route_to_handoff"
        state.last_action_success = True
        if os.getenv("DEBUG"):
            print(f"[store_qa_decide] intent={state.intent} needs_handoff={state.needs_handoff} missing={state.missing_info_needed} repeat={state.repeat_count} next={state.next_step} strategy={state.last_strategy}")
        return state
    
    # Path B: Ask for missing info (max 2 times to avoid loops)
    if state.missing_info_needed and state.repeat_count < 2:
        state.last_strategy = "ask_one_missing"
        state.next_step = "store_qa_respond"
        if os.getenv("DEBUG"):
            print(f"[store_qa_decide] intent={state.intent} needs_handoff={state.needs_handoff} missing={state.missing_info_needed} repeat={state.repeat_count} next={state.next_step} strategy={state.last_strategy}")
        return state
    
    # Path C: Default - use RAG to answer
    state.last_strategy = "rag_answer"
    state.next_step = "store_qa_respond"
    if os.getenv("DEBUG"):
        print(f"[store_qa_decide] intent={state.intent} needs_handoff={state.needs_handoff} missing={state.missing_info_needed} repeat={state.repeat_count} next={state.next_step} strategy={state.last_strategy}")
    return state


