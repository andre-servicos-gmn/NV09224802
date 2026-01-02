from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.tools.store_faq_stub import get_faq_answer


def action_answer_faq(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    answer = get_faq_answer(tenant.tenant_id, state.intent)
    state.metadata["faq_answer"] = answer
    state.last_action = "answer_faq"
    state.last_action_success = bool(answer)
    return state
