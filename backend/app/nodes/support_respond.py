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
        state.soft_context["response_model"] = get_model_name()
        return state

    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f"[support_respond] LLM error: {exc}", exc_info=True)
        state.system_error = "llm_unavailable"
        state.soft_context["response_error"] = str(exc)
        return _fallback_response(state)


_SYSTEM_ERROR_MESSAGES = {
    "llm_timeout": "Demorei um pouco mais que o esperado. Pode repetir sua mensagem?",
    "llm_unavailable": "Estou com dificuldades técnicas no momento. Tente novamente em instantes.",
    "shopify_timeout": "O sistema de checkout está lento agora. Pode tentar novamente em instantes?",
    "rate_limit": "Muitas requisições simultâneas. Aguarde um momento e tente novamente.",
}


def _fallback_response(state: ConversationState) -> ConversationState:
    """Fallback response when LLM fails — usa system_error para mensagem contextualizada."""
    error_key = state.system_error or state.soft_context.get("response_error", "")
    message = _SYSTEM_ERROR_MESSAGES.get(error_key, "Desculpe, tive um problema técnico. Pode repetir?")
    state.last_bot_message = message
    state.soft_context["response_model"] = "fallback"
    return state