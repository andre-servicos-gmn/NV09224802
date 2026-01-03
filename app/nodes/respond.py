"""Sales response generation using humanized LLM."""

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
    first, *rest = message.split(link)
    if not rest:
        return message
    cleaned = first + link + "".join(rest).replace(link, "")
    return cleaned.strip()


def respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Generate Sales response using humanized LLM."""
    try:
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
    link = state.metadata.get("checkout_link")
    
    if state.intent == "greeting":
        message = "Oi! Tudo bem? Como posso te ajudar hoje? 😊"
    elif state.intent == "product_link" and state.selected_variant_id:
        title = state.metadata.get("product_title", "o produto")
        message = f"Show! Encontrei {title}. Quer que eu gere o link de pagamento?"
    elif link:
        message = f"Prontinho! Aqui tá o link pra você finalizar:\n\n{link}"
    else:
        message = "Me manda o link do produto ou o nome que eu gero o checkout pra você!"
    
    state.last_bot_message = message
    state.metadata["response_model"] = "fallback"
    return state
