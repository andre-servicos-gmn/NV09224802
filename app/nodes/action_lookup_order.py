from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.tools.orders_stub import lookup_order_by_email, lookup_order_by_id


def action_lookup_order(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    data: dict
    if state.order_id:
        data = lookup_order_by_id(tenant.tenant_id, state.order_id)
    elif state.customer_email:
        data = lookup_order_by_email(tenant.tenant_id, state.customer_email)
        if data.get("order_id") and not state.order_id:
            state.order_id = data["order_id"]
    else:
        data = {"status": "unknown", "tracking_url": None, "last_update_days": None}

    state.metadata["order_status"] = data.get("status")
    state.tracking_url = data.get("tracking_url")
    state.tracking_last_update_days = data.get("last_update_days")
    state.last_action = "lookup_order"
    state.last_action_success = data.get("tracking_url") is not None
    return state
