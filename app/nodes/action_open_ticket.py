from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.tools.orders_stub import open_carrier_ticket


def action_open_ticket(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    result = open_carrier_ticket(tenant.tenant_id, state.order_id or "")
    state.ticket_opened = bool(result)
    state.last_action = "open_ticket"
    state.last_action_success = bool(result)
    return state
