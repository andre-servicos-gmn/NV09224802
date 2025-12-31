from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def handoff(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    message = (
        f"Sinto muito pela frustracao. {tenant.handoff_message} "
        "Pode me dizer seu nome?"
    )
    state.last_bot_message = message
    return state
