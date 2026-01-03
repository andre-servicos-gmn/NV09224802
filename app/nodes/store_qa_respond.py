"""Store Q&A response generation using humanized LLM."""

from app.core.llm_humanized import generate_humanized_response
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig

# Map intents to knowledge base categories
INTENT_TO_CATEGORIES = {
    "shipping_question": ["shipping"],
    "payment_question": ["payment"],
    "return_exchange": ["return"],
    "store_question": ["store"],
    "greeting": [],
    "general": ["shipping", "payment", "return", "store"],
}


def store_qa_respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Generate Store Q&A response using humanized LLM."""
    # Get relevant categories for this intent
    categories = INTENT_TO_CATEGORIES.get(state.intent, [])
    
    # Generate humanized response
    response = generate_humanized_response(
        state=state,
        tenant=tenant,
        domain="store_qa",
        categories=categories if categories else None,
    )
    
    state.last_bot_message = response
    return state
