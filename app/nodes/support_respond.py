from app.core.constants import INTENT_ORDER_COMPLAINT, INTENT_ORDER_STATUS, INTENT_ORDER_TRACKING
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def support_respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    parts: list[str] = []
    complaint = state.intent == INTENT_ORDER_COMPLAINT or state.metadata.get("complaint_pending")

    if complaint:
        parts.append("Entendo, isso e chato mesmo.")
    elif state.intent in {INTENT_ORDER_STATUS, INTENT_ORDER_TRACKING}:
        parts.append("Vou verificar seu pedido.")

    if not state.order_id and not state.customer_email:
        parts.append("Me passa o numero do pedido.")
        state.last_bot_message = "\n".join(parts).strip()
        return state

    if state.ticket_opened:
        parts.append("Abri um chamado na transportadora e vou acompanhar.")

    if state.tracking_url:
        parts.append("Segue o rastreio:")
        parts.append(state.tracking_url)
    else:
        status = state.metadata.get("order_status")
        if status and status != "unknown":
            parts.append(f"Status do pedido: {status}.")
        else:
            parts.append("Nao encontrei o pedido com esses dados.")

    state.last_bot_message = "\n".join(parts).strip()
    return state
