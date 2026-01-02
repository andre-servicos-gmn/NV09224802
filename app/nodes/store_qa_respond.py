from app.core.constants import INTENT_GREETING
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def store_qa_respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    answer = state.metadata.get("faq_answer")
    if answer:
        message = answer
    elif state.intent == INTENT_GREETING:
        message = "Oi! Como posso ajudar?"
    else:
        message = "Posso ajudar com frete, pagamento ou troca. Qual sua duvida?"

    state.last_bot_message = message.strip()
    return state
