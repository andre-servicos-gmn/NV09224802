# Sales response generation using humanized LLM — consultant mode.
import logging

from app.core.llm_humanized import generate_humanized_response, get_model_name
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig

logger = logging.getLogger(__name__)


def respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Generate Sales response using humanized LLM."""
    logger.info("=" * 50)
    logger.info("[RESPOND] ▶️ ENTRY")
    logger.info(f"[RESPOND] Intent: {state.intent}")
    logger.info(f"[RESPOND] Last Action: {state.last_action}")
    
    try:
        if state.intent == "media_unsupported":
            state.last_bot_message = "Ainda não consigo ouvir áudios ou ver imagens. Pode escrever pra mim?"
            state.soft_context["response_model"] = "deterministic"
            return state

        # Generate humanized response
        response = generate_humanized_response(
            state=state,
            tenant=tenant,
            domain="sales",
            categories=None,
        )
        logger.info(f"[RESPOND] LLM Response (first 100 chars): {response[:100] if response else 'NONE'}...")

        state.last_bot_message = response
        state.soft_context["response_model"] = get_model_name()
        return state

    except Exception as exc:
        logger.exception(f"LLM Response failed: {exc}")
        state.soft_context["response_error"] = str(exc)
        return _fallback_response(state)


def _fallback_response(state: ConversationState) -> ConversationState:
    """Fallback response when LLM fails."""
    state.last_bot_message = "Desculpe, tive um problema tecnico. Pode repetir?"
    state.soft_context["response_model"] = "fallback"
    return state
