from app.core.constants import (
    INTENT_PAYMENT_QUESTION,
    INTENT_RETURN_EXCHANGE,
    INTENT_SHIPPING_QUESTION,
    INTENT_STORE_QUESTION,
)
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def store_qa_decide(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    if state.intent in {
        INTENT_STORE_QUESTION,
        INTENT_SHIPPING_QUESTION,
        INTENT_PAYMENT_QUESTION,
        INTENT_RETURN_EXCHANGE,
    }:
        state.next_step = "action_answer_faq"
    else:
        state.next_step = "store_qa_respond"
    return state
