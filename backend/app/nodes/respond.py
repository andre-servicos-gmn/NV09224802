# Modified: prefer LLM responses with minimal fallback handling.
"""
Sales response generation using humanized LLM.
"""
import re

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


def _sanitize_fake_links(message: str, real_link: str | None) -> str:
    """
    Remove fake link placeholders AND hallucinated link sentences from LLM response.
    
    Catches both explicit placeholders ([LINK], (link aqui)) AND natural language
    patterns where the LLM says "Aqui está o link" without an actual URL.
    """
    # If there's a real link with a valid URL, no sanitization needed
    if real_link and real_link.startswith('http'):
        return message
    
    # Check if message contains any real URL — if so, skip sanitization
    if re.search(r'https?://\S+', message):
        return message

    # Phase 1: Remove explicit placeholder patterns
    placeholder_patterns = [
        r'\[LINK\]',
        r'\(link aqui\)',
        r'\(link\)',
        r'🔗\s*\[LINK\]',
        r'🔗\s*\(link\)',
        r'🔗\s*$',
        r'clique aqui:\s*$',
        r'link:?\s*$',
    ]
    
    combined_placeholder = '|'.join(placeholder_patterns)
    cleaned = re.sub(combined_placeholder, '', message, flags=re.IGNORECASE | re.MULTILINE)
    
    # Phase 2: Remove hallucinated "link delivery" sentences
    # These are lines where the LLM promises a link but there's no URL
    hallucinated_link_patterns = [
        r'^.*aqui\s+(está|tá|ta)\s+(o\s+)?link.*$',
        r'^.*segue\s+(o\s+)?link.*$',
        r'^.*só\s+clicar\s+e\s+finalizar.*$',
        r'^.*é\s+só\s+clicar.*$',
        r'^.*clique\s+(aqui|no\s+link).*$',
        r'^.*acesse\s+(o\s+)?link.*$',
        r'^.*link\s+(pra|para)\s+garantir.*$',
        r'^.*link\s+de\s+compra.*:?\s*$',
        r'^.*🔗.*$',
    ]
    
    for pattern in hallucinated_link_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
    
    # Clean up extra whitespace/newlines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = cleaned.strip()
    
    # If the message was substantially about the link and got emptied, provide fallback
    if not cleaned or len(cleaned) < 10:
        # Don't inject a CTA — let the LLM handle this naturally via the prompt.
        # Return empty so the caller can use a generic fallback.
        cleaned = ""
    
    return cleaned


import logging

logger = logging.getLogger(__name__)


def respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Generate Sales response using humanized LLM."""
    logger.info("=" * 50)
    logger.info("[RESPOND] ▶️ ENTRY")
    logger.info(f"[RESPOND] Intent: {state.intent}")
    logger.info(f"[RESPOND] Last Action: {state.last_action}")
    logger.info(f"[RESPOND] checkout_link: {state.checkout_link}")
    logger.info(f"[RESPOND] selected_variant_id: {state.soft_context.get('selected_variant_id')}")
    
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

        # Sanitize fake link placeholders BEFORE ensuring real link
        link = state.checkout_link
        logger.info(f"[RESPOND] Sanitizing with real_link={link}")
        response = _sanitize_fake_links(response, link)
        
        # Only force-append checkout link for purchase-related intents
        # For checkout_error, support, etc. — DON'T inject the link
        NON_LINK_INTENTS = {"checkout_error", "greeting", "general", "order_status", "order_complaint"}
        if state.intent not in NON_LINK_INTENTS:
            response = _ensure_link_once(response, link)
        logger.info(f"[RESPOND] Final Response (first 150 chars): {response[:150] if response else 'NONE'}...")

        state.last_bot_message = response
        state.soft_context["response_model"] = get_model_name()
        return state

    except Exception as exc:
        state.soft_context["response_error"] = str(exc)
        return _fallback_response(state)


def _fallback_response(state: ConversationState) -> ConversationState:
    """Fallback response when LLM fails."""
    state.last_bot_message = "Desculpe, tive um problema tecnico. Pode repetir?"
    state.soft_context["response_model"] = "fallback"
    return state
