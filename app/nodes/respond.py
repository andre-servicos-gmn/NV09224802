# Modified: prefer LLM responses with minimal fallback handling.
"""
Sales response generation using humanized LLM.
"""
from app.core.llm_humanized import generate_humanized_response, get_model_name
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def _ensure_link_once(message: str, link: str | None) -> str:
    """Ensure checkout link appears exactly once in the message."""
    if not link:
        return message
    if link not in message:
        return f"{message}\n\n{link}".strip()
    # Remove duplicate occurrences beyond the first
    count = message.count(link)
    if count <= 1:
        return message

    parts = message.split(link)
    cleaned = parts[0] + link + "".join(parts[1:])
    return cleaned.strip()


def respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Generate Sales response using humanized LLM."""
    try:
        if state.intent == "media_unsupported":
            state.last_bot_message = "Ainda não consigo ouvir áudios ou ver imagens. Pode escrever pra mim?"
            state.metadata["response_model"] = "deterministic"
            return state

        # Generate humanized response
        response = generate_humanized_response(
            state=state,
            tenant=tenant,
            domain="sales",
            categories=None,
        )

        # Ensure checkout link is included properly
        link = state.metadata.get("checkout_link")
        response = _ensure_link_once(response, link)

        state.last_bot_message = response
        state.metadata["response_model"] = get_model_name()
        return state

    except Exception as exc:
        state.metadata["response_error"] = str(exc)
        return _fallback_response(state)


def _fallback_response(state: ConversationState) -> ConversationState:
    """Fallback response when LLM fails."""
    state.last_bot_message = "Desculpe, tive um problema tecnico. Pode repetir?"
    state.metadata["response_model"] = "fallback"
    return state
