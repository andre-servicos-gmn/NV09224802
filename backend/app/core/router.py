import os
import re
import time
import unicodedata
from dataclasses import dataclass

from .constants import (
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
    INTENT_RETURN_EXCHANGE,
    INTENT_SEARCH_PRODUCT,
    INTENT_SHIPPING_QUESTION,
    INTENT_STORE_QUESTION,
    DEFAULT_INTENT,
    SUPPORTED_DOMAINS,
    SUPPORTED_INTENTS,
)
from .router_llm import classify_with_llm, classify_heuristic, MIN_CONFIDENCE, HIGH_CONFIDENCE
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
        INTENT_PRODUCT_LINK,
        INTENT_SEARCH_PRODUCT,
        INTENT_GREETING,
        INTENT_GENERAL,
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
        if state.order_id != new_order_id:
            # Clear stale tracking data from previous order
            state.tracking_url = None
            state.tracking_last_update_days = None
            if "order_status" in state.soft_context:
                del state.soft_context["order_status"]
            state.soft_context["ticket_opened"] = False
        state.order_id = new_order_id
    
    new_email = entities.get("email")
    if new_email:
        state.customer_email = new_email
    
    if entities.get("product_url") and not state.soft_context.get("product_url"):
        state.soft_context["product_url"] = entities.get("product_url")

    # Map extracted search query to state
    if entities.get("search_query"):
        state.search_query = entities["search_query"]
        
    # Map extracted disliked terms to state
    if entities.get("disliked_terms"):
        # Append to existing list to maintain history
        existing_disliked = set(state.soft_context.get("disliked_terms", []))
        new_disliked = entities["disliked_terms"]
        if isinstance(new_disliked, str):
            new_disliked = [new_disliked]
        existing_disliked.update(new_disliked)
        state.soft_context["disliked_terms"] = list(existing_disliked)
    
    state.soft_context["entities"] = entities


def classify(message: str, context: dict | None = None, use_llm: bool = True) -> RouterDecision:
    if use_llm:
        cached = _cache_get(context, message)
        if cached:
            return cached

    # Quick heuristic classification for obvious patterns (saves LLM call)
    heuristic_result = classify_heuristic(message, context)
    if heuristic_result:
        sentiment = analyze_sentiment_llm(message)
        return RouterDecision(
            domain=heuristic_result.domain,
            intent=heuristic_result.intent,
            entities=heuristic_result.entities,
            confidence=heuristic_result.confidence,
            used_fallback=False,
            reason=f"heuristic_{heuristic_result.rationale}",
            sentiment_level=sentiment["sentiment_level"],
            sentiment_score=sentiment["sentiment_score"],
            needs_handoff=sentiment["needs_handoff"],
            handoff_reason=sentiment["handoff_reason"],
            used_sentiment_llm=True,
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
            if result.confidence < MIN_CONFIDENCE:
                raise ValueError(f"LLM confidence {result.confidence} < {MIN_CONFIDENCE}")
            if result.confidence < HIGH_CONFIDENCE and not sanity_check(
                result.domain, result.intent, result.entities, message
            ):
                raise ValueError("LLM sanity check failed.")
            entities = _merge_entities(result.entities, extract_entities_heuristic(message))
            
            # Safety net: ensure domain matches intent
            expected_domain = classify_domain_heuristic(result.intent)
            if expected_domain != result.domain and result.intent != INTENT_GENERAL and result.intent != INTENT_GREETING:
                import logging
                logging.getLogger(__name__).info(
                    f"[ROUTER] Domain override: LLM said {result.domain} but intent {result.intent} → {expected_domain}"
                )
                result.domain = expected_domain
            
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
