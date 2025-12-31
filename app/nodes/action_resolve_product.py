from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.tools.shopify_stub import resolve_product_from_url


def action_resolve_product(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    product = resolve_product_from_url(state.last_user_message or "")
    state.selected_product_id = product["product_id"]
    state.selected_variant_id = product["variant_id"]
    state.metadata["product_title"] = product["title"]
    state.metadata["product_price"] = product["price"]
    state.last_action = "resolve_product"
    state.last_action_success = True
    state.next_step = "respond"
    return state
