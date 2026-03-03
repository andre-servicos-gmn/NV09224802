"""Support response generation using humanized LLM.

Responsabilidade: gerar mensagem humana sem executar logica de negocio.
"""
from app.core.llm_humanized import generate_humanized_response, get_model_name
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def _ensure_link_once(message: str, link: str | None) -> str:
    """Ensure tracking link appears exactly once in the message."""
    if not link:
        return message
    if link not in message:
        return f"{message}\n\n{link}".strip()
    count = message.count(link)
    if count <= 1:
        return message

    parts = message.split(link)
    cleaned = parts[0] + link + "".join(parts[1:])
    return cleaned.strip()


def support_respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Generate Support response using humanized LLM."""
    try:
        response = generate_humanized_response(
            state=state,
            tenant=tenant,
            domain="support",
            categories=None,
        )
        response = _ensure_link_once(response, state.tracking_url)

        state.last_bot_message = response
        state.metadata["response_model"] = get_model_name()
        return state

    except Exception as exc:
        import traceback
        traceback.print_exc()
        state.metadata["response_error"] = str(exc)
        return _fallback_response(state)


def _fallback_response(state: ConversationState) -> ConversationState:
    """Fallback response when LLM fails."""
    state.last_bot_message = "Desculpe, tive um problema tecnico. Pode repetir?"
    state.metadata["response_model"] = "fallback"
    return state