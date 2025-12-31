from app.core.router import classify_intent
from app.core.state import ConversationState
from app.core.tenancy import TenantRegistry
from app.graphs.sales_graph import run_sales_graph


def _run_message(state, tenant, message):
    state.last_user_message = message
    state.intent = classify_intent(message)
    return run_sales_graph(state, tenant)


def test_checkout_retry_dialog():
    tenant = TenantRegistry().get("demo")
    state = ConversationState(tenant_id=tenant.tenant_id, session_id="test-session")

    state = _run_message(state, tenant, "oi")
    state = _run_message(state, tenant, "vi esse produto https://example.com/products/colar")
    assert state.selected_variant_id is not None

    state = _run_message(state, tenant, "quero comprar")
    assert state.last_strategy == "permalink"

    state = _run_message(state, tenant, "deu erro no link")
    state.last_action_success = False

    state = _run_message(state, tenant, "gera de novo")
    assert state.last_strategy == "add_to_cart"
    assert state.last_bot_message.count("https://") == 1
