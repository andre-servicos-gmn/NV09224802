"""Store Q&A decision node - with memory-based strategies.

Strategies:
    - handoff: if needs_handoff is true
    - resolve: if needs_resolution is true
    - ask_one_missing: if missing_info_needed has items and repeat_count < 2
    - rag_answer: default, use RAG to answer
    """

import os
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def store_qa_decide(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Decide next step for Store Q&A based on memory state."""

    # A) Handoff path
    if state.needs_handoff:
        state.next_step = "handoff"
        state.last_action = "route_to_handoff"
        state.last_action_success = True
        if os.getenv("DEBUG"):
            print(f"[store_qa_decide] HANDOFF intent={state.intent} next={state.next_step}")
        return state

    # B) Resolution path
    if state.needs_resolution:
        state.next_step = "action_resolve"
        state.last_action = "route_to_resolve"
        state.last_action_success = True
        if os.getenv("DEBUG"):
            print(f"[store_qa_decide] RESOLVE intent={state.intent}")
        return state

    # Safety: manual/policy intents should NEVER ask for missing info
    manual_intents = {"shipping_question", "payment_question", "return_exchange", "store_question"}
    if state.intent in manual_intents:
        state.missing_info_needed = []

    # B) Ask one missing info (max 2 times)
    if state.missing_info_needed and state.repeat_count < 2:
        state.last_strategy = "ask_one_missing"
        state.next_step = "store_qa_respond"
        if os.getenv("DEBUG"):
            print(
                f"[store_qa_decide] ASK_ONE_MISSING intent={state.intent} "
                f"missing={state.missing_info_needed} repeat={state.repeat_count} "
                f"strategy={state.last_strategy} next={state.next_step}"
            )
        return state

    # C) Default: answer via RAG
    state.last_strategy = "rag_answer"
    state.next_step = "store_qa_respond"
    if os.getenv("DEBUG"):
        print(
            f"[store_qa_decide] RAG_ANSWER intent={state.intent} "
            f"missing={state.missing_info_needed} repeat={state.repeat_count} "
            f"strategy={state.last_strategy} next={state.next_step}"
        )
    return state
