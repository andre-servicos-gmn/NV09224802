from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def handoff(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    base = "Entendi. Vou te colocar com um atendente humano pra resolver isso agora."
    message = f"{base} {tenant.handoff_message}"
    if not state.customer_email:
        message = f"{message} Pode me informar seu email?"
    else:
        message = f"{message} Pode me dizer seu nome?"
    state.last_bot_message = message
    return state
