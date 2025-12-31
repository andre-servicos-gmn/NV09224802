from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.tools.shopify_stub import build_checkout_link


def action_generate_link(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    strategy = state.last_strategy or tenant.default_link_strategy or "permalink"

    if not state.selected_variant_id:
        link = ""
    else:
        link = build_checkout_link(
            tenant.store_domain,
            state.selected_variant_id,
            state.quantity,
            strategy,
        )

    state.last_action = "generate_link"
    state.last_strategy = strategy
    state.last_action_success = bool(link)
    if link:
        state.metadata["checkout_link"] = link
    else:
        state.metadata.pop("checkout_link", None)
    state.next_step = "respond"
    return state
