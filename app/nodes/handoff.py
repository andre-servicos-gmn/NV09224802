from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def handoff(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Generate handoff message per AGENT.md section 6: empathy, explanation, action."""
    # 1. Empathy/confirmation
    empathy = "Entendo sua situação."
    
    # 2. Explanation (from tenant config - no duplication)
    handoff_msg = tenant.handoff_message or "Vou te encaminhar para um atendente."
    
    # 3. Action (collect info for handoff)
    if not state.customer_email:
        action = "Pode me informar seu email para prosseguir?"
    else:
        action = "Em breve um atendente entrará em contato."
    
    state.last_bot_message = f"{empathy} {handoff_msg} {action}"
    state.last_action = "handoff"
    state.last_action_success = True
    return state

