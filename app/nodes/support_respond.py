"""Support response generation using humanized LLM."""

from app.core.llm_humanized import generate_humanized_response
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def support_respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Generate Support response using humanized LLM."""
    # Generate humanized response with shipping/return context
    response = generate_humanized_response(
        state=state,
        tenant=tenant,
        domain="support",
        categories=["shipping", "return"],
    )
    
    state.last_bot_message = response
    return state
