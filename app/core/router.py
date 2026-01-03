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
from .sentiment import analyze_sentiment_local
from .sentiment_llm import analyze_sentiment_llm

CACHE_TTL_SECONDS = 120.0
LLM_TIMEOUT_S = float(os.getenv("ROUTER_LLM_TIMEOUT_S", "12"))
SENTIMENT_LLM_TIMEOUT_S = float(os.getenv("SENTIMENT_LLM_TIMEOUT_S", "8"))
SENTIMENT_LLM_ENABLED = os.getenv("SENTIMENT_LLM_ENABLED", "false").lower() == "true"
SENTIMENT_LLM_THRESHOLD_LOW = float(os.getenv("SENTIMENT_LLM_THRESHOLD_LOW", "0.35"))
SENTIMENT_LLM_THRESHOLD_HIGH = float(os.getenv("SENTIMENT_LLM_THRESHOLD_HIGH", "0.65"))
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


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return text


def classify_intent_heuristic(message: str) -> str:
    msg = _normalize(message)
    if not msg:
        return INTENT_GENERAL

    email_match = re.search(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", message.lower())
    order_id_match = re.search(r"\b\d{3,}\b", msg)

    checkout_error_phrases = [
        "deu erro",
        "erro",
        "falhou",
        "quebrou",
        "nao funciona",
        "nao abre",
        "link nao funciona",
    ]
    cart_retry_phrases = [
        "gera de novo",
        "gere novamente",
        "manda outro link",
        "refaz",
        "tenta de novo",
        "envia de novo",
        "regera",
    ]
    purchase_phrases = [
        "quero comprar",
        "comprar",
        "pagar",
        "checkout",
        "finalizar",
        "link de pagamento",
    ]
    greeting_phrases = ["oi", "ola", "bom dia", "boa tarde", "boa noite"]
    order_complaint_phrases = [
        "parado",
        "nao atualiza",
        "sem atualizacao",
        "travado",
        "atrasado",
        "nao anda",
    ]
    order_tracking_phrases = [
        "rastreio",
        "rastreamento",
        "tracking",
        "codigo de rastreio",
        "codigo de rastreamento",
    ]
    order_status_phrases = ["status do pedido", "status", "meu pedido", "pedido"]
    shipping_phrases = ["frete", "entrega", "prazo", "envio", "shipping"]
    payment_phrases = ["pagamento", "cartao", "pix", "boleto", "parcelamento"]
    return_phrases = ["troca", "devolucao", "devolver", "reembolso", "return"]
    store_phrases = ["contato", "horario", "endereco", "loja", "whatsapp"]

    if any(phrase in msg for phrase in checkout_error_phrases):
        return INTENT_CHECKOUT_ERROR
    if any(phrase in msg for phrase in cart_retry_phrases):
        return INTENT_CART_RETRY
    if "http" in msg and "products/" in msg:
        return INTENT_PRODUCT_LINK
    if any(phrase in msg for phrase in purchase_phrases):
        return INTENT_PURCHASE_INTENT
    if any(phrase in msg for phrase in order_complaint_phrases):
        return INTENT_ORDER_COMPLAINT
    if any(phrase in msg for phrase in order_tracking_phrases):
        return INTENT_ORDER_TRACKING
    if any(phrase in msg for phrase in order_status_phrases):
        return INTENT_ORDER_STATUS
    if any(phrase in msg for phrase in shipping_phrases):
        return INTENT_SHIPPING_QUESTION
    if any(phrase in msg for phrase in payment_phrases):
        return INTENT_PAYMENT_QUESTION
    if any(phrase in msg for phrase in return_phrases):
        return INTENT_RETURN_EXCHANGE
    if any(phrase in msg for phrase in store_phrases):
        return INTENT_STORE_QUESTION
    if email_match:
        return INTENT_PROVIDE_EMAIL
    if order_id_match and msg.strip().isdigit():
        return INTENT_PROVIDE_ORDER_ID
    if any(phrase in msg for phrase in greeting_phrases):
        return INTENT_GREETING
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
    if state.order_id is None and entities.get("order_id"):
        state.order_id = entities.get("order_id")
    if state.customer_email is None and entities.get("email"):
        state.customer_email = entities.get("email")
    if entities.get("product_url") and not state.metadata.get("product_url"):
        state.metadata["product_url"] = entities.get("product_url")
    state.metadata["entities"] = entities


def classify(message: str, context: dict | None = None, use_llm: bool = True) -> RouterDecision:
    if use_llm:
        cached = _cache_get(context, message)
        if cached:
            return cached

    sentiment = analyze_sentiment_local(message)
    used_sentiment_llm = False
    if (
        use_llm
        and SENTIMENT_LLM_ENABLED
        and not sentiment["needs_handoff"]
        and SENTIMENT_LLM_THRESHOLD_LOW <= sentiment["sentiment_score"] <= SENTIMENT_LLM_THRESHOLD_HIGH
        and os.getenv("OPENAI_API_KEY")
    ):
        try:
            llm_result = analyze_sentiment_llm(message, timeout_s=SENTIMENT_LLM_TIMEOUT_S)
            sentiment = {
                "sentiment_level": llm_result.sentiment_level,
                "sentiment_score": llm_result.sentiment_score,
                "needs_handoff": llm_result.needs_handoff,
                "handoff_reason": llm_result.handoff_reason,
            }
            used_sentiment_llm = True
        except Exception:
            pass

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
            )
            _cache_set(context, message, decision)
            return decision
        except Exception as exc:
            fallback_reason = f"llm_fallback:{exc.__class__.__name__}"
    else:
        fallback_reason = "llm_disabled_or_missing_key"

    intent = classify_intent_heuristic(message)
    if intent not in SUPPORTED_INTENTS:
        intent = DEFAULT_INTENT
    domain = classify_domain_heuristic(intent)
    if domain not in SUPPORTED_DOMAINS:
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
