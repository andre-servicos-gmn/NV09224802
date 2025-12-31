from app.core.constants import (
    INTENT_CART_RETRY,
    INTENT_CHECKOUT_ERROR,
    INTENT_GREETING,
    INTENT_PRODUCT_LINK,
    INTENT_PURCHASE_INTENT,
)
from app.core.llm import generate_response, get_model_name
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig

_SYSTEM_PROMPT = (
    "You are the Respond node for Nouvaris Agents V2. "
    "Write only the final message to the user in pt-BR. "
    "Short, human sentences. No markdown. Raw URLs only. "
    "Order: empathy/confirmation, simple explanation, clear action. "
    "Do not ask for info already present in state. "
    "If frustration_level >= 3, simplify and offer human handoff. "
    "If checkout_link is provided, include it exactly once. "
    "If checkout_link is missing and intent is checkout_error or cart_retry, "
    "use the tenant handoff message."
)


def _build_user_prompt(state: ConversationState, tenant: TenantConfig, link: str | None) -> str:
    product_title = state.metadata.get("product_title", "")
    lines = [
        f"tenant_name={tenant.name}",
        f"brand_voice={tenant.brand_voice}",
        f"handoff_message={tenant.handoff_message}",
        f"intent={state.intent}",
        f"selected_product_id={state.selected_product_id}",
        f"selected_variant_id={state.selected_variant_id}",
        f"quantity={state.quantity}",
        f"last_action={state.last_action}",
        f"last_strategy={state.last_strategy}",
        f"last_action_success={state.last_action_success}",
        f"frustration_level={state.frustration_level}",
        f"checkout_link={link or ''}",
        f"product_title={product_title}",
        f"last_user_message={state.last_user_message or ''}",
    ]
    return "\n".join(lines)


def _ensure_link_once(message: str, link: str | None) -> str:
    if not link:
        return message
    if link not in message:
        return f"{message}\n{link}".strip()
    # Remove duplicate occurrences beyond the first.
    first, *rest = message.split(link)
    if not rest:
        return message
    cleaned = first + link + "".join(rest).replace(link, "")
    return cleaned.strip()


def _fallback_response(state: ConversationState) -> ConversationState:
    link = state.metadata.get("checkout_link")
    parts: list[str] = []

    if state.intent == INTENT_GREETING:
        parts.append("Oi! Como posso ajudar?")
    elif state.intent == INTENT_PRODUCT_LINK and state.selected_variant_id:
        title = state.metadata.get("product_title", "o produto")
        parts.append(f"Perfeito, encontrei {title}. Quer comprar agora?")
    elif state.intent == INTENT_PURCHASE_INTENT and not state.selected_variant_id:
        parts.append("Me manda o link do produto ou o nome exato pra eu gerar o checkout.")
    elif state.intent in {INTENT_CHECKOUT_ERROR, INTENT_CART_RETRY}:
        parts.append("Poxa, entendo. Vou gerar um link mais estavel para o checkout.")
        if link:
            parts.append(link)
        else:
            parts.append("Nao consegui gerar um link agora. Vou te colocar com um atendente humano.")
    else:
        if link:
            parts.append("Pronto! Aqui esta o link para finalizar:")
            parts.append(link)
        else:
            parts.append("Entendi. Me manda o link do produto ou o nome pra eu ajudar.")

    if link and link not in parts and state.intent not in {INTENT_CHECKOUT_ERROR, INTENT_CART_RETRY}:
        parts.append(link)

    message = "\n".join(parts).strip()
    state.last_bot_message = message
    state.metadata["response_model"] = "fallback"
    return state


def respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    link = state.metadata.get("checkout_link")
    try:
        user_prompt = _build_user_prompt(state, tenant, link)
        message = generate_response(_SYSTEM_PROMPT, user_prompt)
        if not message:
            raise ValueError("Empty response from LLM")
        message = _ensure_link_once(message, link)
        state.last_bot_message = message
        state.metadata["response_model"] = get_model_name()
        return state
    except Exception as exc:
        state.metadata["response_error"] = str(exc)
        return _fallback_response(state)

