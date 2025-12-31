from app.core.constants import (
    INTENT_CART_RETRY,
    INTENT_CHECKOUT_ERROR,
    INTENT_GREETING,
    INTENT_PRODUCT_LINK,
    INTENT_PURCHASE_INTENT,
)
from app.core.state import ConversationState
from app.core.strategies import next_strategy
from app.core.tenancy import TenantConfig


def decide(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    if state.frustration_level >= 3:
        state.next_step = "handoff"
        return state

    if state.intent == INTENT_PRODUCT_LINK:
        state.next_step = "action_resolve_product"
        return state

    if state.intent in {INTENT_PURCHASE_INTENT, INTENT_CART_RETRY, INTENT_CHECKOUT_ERROR}:
        if state.selected_variant_id:
            if state.intent in {INTENT_CART_RETRY, INTENT_CHECKOUT_ERROR}:
                if state.last_action_success is False:
                    state.last_strategy = next_strategy(state.last_strategy)
            state.next_step = "action_generate_link"
        else:
            state.next_step = "respond"
        return state

    if state.intent == INTENT_GREETING:
        state.next_step = "respond"
        return state

    state.next_step = "respond"
    return state
