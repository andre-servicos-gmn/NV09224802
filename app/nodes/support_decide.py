"""Support decision node.

Responsabilidade: decidir o proximo passo sem executar acoes ou gerar texto.
NÃO extrai entidades (responsabilidade do Router).
NÃO modifica contexto (responsabilidade do Router/Action).
"""
from app.core.constants import (
    INTENT_ORDER_COMPLAINT,
    INTENT_ORDER_STATUS,
    INTENT_ORDER_TRACKING,
    INTENT_PROVIDE_EMAIL,
    INTENT_PROVIDE_ORDER_ID,
)
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def support_decide(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    if state.needs_handoff or state.frustration_level >= 3:
        state.next_step = "handoff"
        state.last_action = "route_to_handoff"
        state.last_action_success = True
        return state

    # Routing logic based on INTENT and STATE availability
    # Router already populated state.order_id / state.customer_email if entities were found.

    # 1. User providing info (Order ID or Email)
    if state.intent in {INTENT_PROVIDE_ORDER_ID, INTENT_PROVIDE_EMAIL}:
        # If we have data, go check order. If not, ask again.
        if state.order_id or state.customer_email:
            state.next_step = "action_get_order"
        else:
            state.next_step = "support_respond"
        return state

    # 2. User asking about order (Status, Tracking, Complaint)
    if state.intent in {INTENT_ORDER_STATUS, INTENT_ORDER_TRACKING, INTENT_ORDER_COMPLAINT}:
        if state.order_id or state.customer_email:
            if state.intent == INTENT_ORDER_COMPLAINT:
                state.next_step = "action_open_ticket"
            elif state.intent == INTENT_ORDER_TRACKING and state.tracking_url:
                # If we ALREADY have tracking URL in state (e.g. from previous turn), just respond
                state.next_step = "support_respond"
            else:
                # Need to fetch fresh data
                state.next_step = "action_get_order"
        else:
            state.next_step = "support_respond"
        return state

    # Default fallback
    state.next_step = "support_respond"
    return state
