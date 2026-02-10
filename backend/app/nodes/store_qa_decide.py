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

    # CRITICAL RULE:
    # - If NOT handoff, this function MUST continue to evaluate missing_info and rag_answer.
    # - NEVER return early in the non-handoff path.

    from app.core.constants import INTENT_RETURN_EXCHANGE, INTENT_ORDER_COMPLAINT

    # A) Handoff path (only case where we return immediately)
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

    # NEW RULE: INTELLIGENT REFUND HANDOFF
    # Distinguish between "Questions about refund" (RAG) and "Requests for refund" (Handoff)
    
    refund_keywords = ["reembolso", "estorno", "dinheiro de volta", "devolver dinheiro", "cancelar compra", "cancelamento"]
    user_msg_lower = (state.last_user_message or "").lower()
    
    is_refund_keyword = any(k in user_msg_lower for k in refund_keywords)
    
    if is_refund_keyword:
        import logging
        from app.core.refund_analysis import analyze_refund_intent
        logger = logging.getLogger(__name__)

        # CASE 1: High Frustration + Refund Keywords -> Immediate Handoff
        if state.frustration_level >= 3:
            logger.info("[REFUND] High frustration + keywords -> immediate handoff")
            state.needs_handoff = True
            state.handoff_reason = "Solicitação de reembolso com alta frustração"
            state.next_step = "handoff"
            state.last_action = "route_to_handoff"
            state.last_action_success = True
            return state

        # Prepare context for analysis
        context = {
            "order_id": state.facts.get("order_id") or state.order_id,
            "frustration_level": state.frustration_level,
            "conversation_history": state.conversation_history[-4:] if state.conversation_history else []
        }

        # CASE 2: Order ID present + Refund Keywords -> Bias towards Request
        # If we have an order ID, they likely want action on THAT order
        # We still call LLM but the presence of order_id in context heavily implies request
        
        # KEY STEP: LLM Analysis
        analysis = analyze_refund_intent(state.last_user_message, context)
        
        if analysis.get("is_request"):
            # CASE 3: LLM Validated Request
            state.needs_handoff = True
            confidence = analysis.get("confidence", 0.0)
            state.handoff_reason = f"Solicitação de reembolso (Confidence: {confidence:.2f})"
            state.next_step = "handoff"
            state.last_action = "route_to_handoff"
            state.last_action_success = True
            
            logger.info(f"[REFUND] Request validated: {analysis.get('reasoning')}")
            if os.getenv("DEBUG"):
                print(f"[store_qa_decide] INTELLIGENT HANDOFF: {state.handoff_reason}")
            return state
        else:
            # Classified as Question -> Continue to RAG
            logger.info(f"[REFUND] Classified as question: {analysis.get('reasoning')}")
            if os.getenv("DEBUG"):
                print(f"[store_qa_decide] REFUND QUESTION identified, proceeding to RAG.")

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
