import os
import re
import time
import unicodedata
from dataclasses import dataclass

from .constants import (
    INTENT_CART_RETRY,
    INTENT_CHECKOUT_ERROR,
    INTENT_GENERAL,
    INTENT_GREETING,
    INTENT_ORDER_COMPLAINT,
    INTENT_ORDER_STATUS,
    INTENT_ORDER_TRACKING,
    INTENT_PAYMENT_QUESTION,
    INTENT_MEDIA_UNSUPPORTED,
    INTENT_PRODUCT_LINK,
    INTENT_PROVIDE_EMAIL,
    INTENT_PROVIDE_ORDER_ID,
    INTENT_PURCHASE_INTENT,
    INTENT_RETURN_EXCHANGE,
    INTENT_SHIPPING_QUESTION,
    INTENT_STORE_QUESTION,
    DEFAULT_INTENT,
    SUPPORTED_DOMAINS,
    SUPPORTED_INTENTS,
)
from .router_llm import classify_with_llm
from .sentiment import analyze_sentiment_llm

CACHE_TTL_SECONDS = 120.0
LLM_TIMEOUT_S = float(os.getenv("ROUTER_LLM_TIMEOUT_S", "12"))
_CACHE: dict[tuple[str, str, str], tuple[float, "RouterDecision"]] = {}


@dataclass
class RouterDecision:
    domain: str
    intent: str
    entities: dict
    confidence: float
    used_fallback: bool
    reason: str
    sentiment_level: str
    sentiment_score: float
    needs_handoff: bool
    handoff_reason: str | None
    used_sentiment_llm: bool
    token_usage: dict | None = None


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return text


def classify_intent_heuristic(message: str) -> str:
    """
    Formerly used for keyword-based classification.
    Now deprecated/removed to force 100% AI usage.
    Returns general intent as a safe fallback if LLM fails.
    """
    return INTENT_GENERAL


def classify_domain_heuristic(intent: str) -> str:
    sales = {
        INTENT_PURCHASE_INTENT,
        INTENT_PRODUCT_LINK,
        INTENT_CART_RETRY,
        INTENT_CHECKOUT_ERROR,
    }
    support = {
        INTENT_ORDER_STATUS,
        INTENT_ORDER_TRACKING,
        INTENT_ORDER_COMPLAINT,
        INTENT_PROVIDE_ORDER_ID,
        INTENT_PROVIDE_EMAIL,
    }
    store_qa = {
        INTENT_STORE_QUESTION,
        INTENT_SHIPPING_QUESTION,
        INTENT_PAYMENT_QUESTION,
        INTENT_RETURN_EXCHANGE,
    }

    if intent in sales:
        return "sales"
    if intent in support:
        return "support"
    if intent in store_qa:
        return "store_qa"
    return "store_qa"


def extract_entities_heuristic(message: str) -> dict:
    entities: dict = {}
    if not message:
        return entities

    email_match = re.search(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", message.lower())
    if email_match:
        entities["email"] = email_match.group(0)

    order_id_match = re.search(r"\b\d{3,8}\b", message)
    if order_id_match:
        entities["order_id"] = order_id_match.group(0)

    url_match = re.search(r"https?://\S+", message)
    if url_match and "products/" in url_match.group(0):
        entities["product_url"] = url_match.group(0)

    days_match = re.search(r"\b(\d{1,3})\s*dias?\b", message.lower())
    if days_match:
        entities["tracking_complaint_days"] = int(days_match.group(1))

    return entities


def _normalize_cache_key(message: str) -> str:
    normalized = " ".join(message.lower().strip().split())
    return normalized


def _cache_get(context: dict | None, message: str) -> RouterDecision | None:
    if not context:
        return None
    tenant_id = str(context.get("tenant_id", ""))
    session_id = str(context.get("session_id", ""))
    if not tenant_id or not session_id:
        return None
    key = (tenant_id, session_id, _normalize_cache_key(message))
    entry = _CACHE.get(key)
    if not entry:
        return None
    ts, decision = entry
    if time.monotonic() - ts > CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return decision


def _cache_set(context: dict | None, message: str, decision: RouterDecision) -> None:
    if not context:
        return
    tenant_id = str(context.get("tenant_id", ""))
    session_id = str(context.get("session_id", ""))
    if not tenant_id or not session_id:
        return
    key = (tenant_id, session_id, _normalize_cache_key(message))
    _CACHE[key] = (time.monotonic(), decision)


def _message_digits_only(message: str) -> bool:
    msg = _normalize(message)
    return bool(msg) and msg.isdigit()


def _has_order_terms(message: str) -> bool:
    msg = _normalize(message)
    terms = ("pedido", "rastreio", "rastreamento", "tracking", "entrega", "atraso")
    return any(term in msg for term in terms)


def sanity_check(domain: str, intent: str, entities: dict, message: str) -> bool:
    if (entities.get("order_id") or entities.get("email")) and domain == "sales":
        return False
    if entities.get("product_url") and domain == "support" and not entities.get("order_id"):
        return False
    if _message_digits_only(message) and intent != INTENT_PROVIDE_ORDER_ID:
        return False
    if intent in {INTENT_CHECKOUT_ERROR, INTENT_CART_RETRY} and _has_order_terms(message):
        return False
    return True


def _merge_entities(primary: dict, secondary: dict) -> dict:
    merged = dict(primary or {})
    for key, value in (secondary or {}).items():
        if key not in merged:
            merged[key] = value
    return merged


def apply_entities_to_state(state, entities: dict) -> None:
    if not entities:
        return
    
    new_order_id = entities.get("order_id")
    if new_order_id:
        # ALWAYS overwrite order_id when user provides a new one
        # This respects user corrections per AGENT.md canonical state contract
        if state.order_id != new_order_id:
            # Clear stale tracking data from previous order
            state.tracking_url = None
            state.tracking_last_update_days = None
            state.metadata.pop("order_status", None)
            state.ticket_opened = False
        state.order_id = new_order_id
    
    new_email = entities.get("email")
    if new_email:
        # ALWAYS overwrite email when user provides a new one
        state.customer_email = new_email
    
    if entities.get("product_url") and not state.metadata.get("product_url"):
        state.metadata["product_url"] = entities.get("product_url")
    
    state.metadata["entities"] = entities


def classify(message: str, context: dict | None = None, use_llm: bool = True) -> RouterDecision:
    if use_llm:
        cached = _cache_get(context, message)
        if cached:
            return cached

    # Media Check heuristic
    if message.strip().upper().startswith(("[AUDIO]", "[IMAGE]", "[VIDEO]")):
        return RouterDecision(
            domain="general",
            intent=INTENT_MEDIA_UNSUPPORTED,
            entities={},
            confidence=1.0,
            used_fallback=False,
            reason="heuristic_media",
            sentiment_level="calm",
            sentiment_score=0.0,
            needs_handoff=False,
            handoff_reason=None,
            used_sentiment_llm=False,
        )

    sentiment = analyze_sentiment_llm(message)
    used_sentiment_llm = True

    if use_llm and os.getenv("OPENAI_API_KEY"):
        try:
            result = classify_with_llm(message, context, SUPPORTED_INTENTS, timeout_s=LLM_TIMEOUT_S)
            if result.intent not in SUPPORTED_INTENTS:
                raise ValueError("Unsupported intent from LLM.")
            if result.ambiguous:
                raise ValueError("LLM ambiguous.")
            if result.confidence < 0.65:
                raise ValueError("LLM confidence too low.")
            if result.confidence < 0.8 and not sanity_check(
                result.domain, result.intent, result.entities, message
            ):
                raise ValueError("LLM sanity check failed.")
            entities = _merge_entities(result.entities, extract_entities_heuristic(message))
            decision = RouterDecision(
                domain=result.domain,
                intent=result.intent,
                entities=entities,
                confidence=result.confidence,
                used_fallback=False,
                reason="llm_accepted",
                sentiment_level=sentiment["sentiment_level"],
                sentiment_score=sentiment["sentiment_score"],
                needs_handoff=sentiment["needs_handoff"],
                handoff_reason=sentiment["handoff_reason"],
                used_sentiment_llm=used_sentiment_llm,
                token_usage=result.token_usage,
            )
            _cache_set(context, message, decision)
            return decision
        except Exception as exc:
            fallback_reason = f"llm_fallback:{exc.__class__.__name__}"
    else:
        fallback_reason = "llm_disabled_or_missing_key"

    # Fallback when LLM fails:
    # We removed keyword heuristics, so we default to a safe state.
    intent = DEFAULT_INTENT
    domain = "store_qa"
    decision = RouterDecision(
        domain=domain,
        intent=intent,
        entities=extract_entities_heuristic(message),
        confidence=0.5,
        used_fallback=True,
        reason=fallback_reason,
        sentiment_level=sentiment["sentiment_level"],
        sentiment_score=sentiment["sentiment_score"],
        needs_handoff=sentiment["needs_handoff"],
        handoff_reason=sentiment["handoff_reason"],
        used_sentiment_llm=used_sentiment_llm,
    )
    if use_llm:
        _cache_set(context, message, decision)
    return decision


def classify_intent(message: str) -> str:
    return classify_intent_heuristic(message)


def classify_domain(message: str, intent: str) -> str:
    return classify_domain_heuristic(intent)
