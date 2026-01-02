import os
import re
import unicodedata

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
    SUPPORTED_INTENTS,
)
from .router_llm import classify_with_llm


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


def _is_question(message: str) -> bool:
    msg = _normalize(message)
    if not msg:
        return False
    if "?" in message:
        return True
    starters = ("como", "qual", "quais", "quando", "onde", "quanto", "prazo")
    return msg.startswith(starters)


def classify_domain_heuristic(message: str, intent: str) -> str:
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
    return "store_qa" if _is_question(message) else "general"


def _extract_entities_heuristic(message: str) -> dict:
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


def classify(message: str, use_llm: bool = True) -> tuple[str, str, dict, float]:
    if use_llm and os.getenv("OPENAI_API_KEY"):
        try:
            result = classify_with_llm(message, SUPPORTED_INTENTS)
            if result.intent not in SUPPORTED_INTENTS:
                raise ValueError("Unsupported intent from LLM.")
            if result.confidence < 0.65:
                raise ValueError("LLM confidence too low.")
            return result.domain, result.intent, result.entities, result.confidence
        except Exception:
            pass

    intent = classify_intent_heuristic(message)
    domain = classify_domain_heuristic(message, intent)
    if domain not in {"sales", "support", "store_qa"}:
        domain = "store_qa"
    return domain, intent, _extract_entities_heuristic(message), 0.5


def classify_intent(message: str) -> str:
    return classify_intent_heuristic(message)


def classify_domain(message: str, intent: str) -> str:
    return classify_domain_heuristic(message, intent)
