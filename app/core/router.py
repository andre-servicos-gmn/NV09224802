import unicodedata

from .constants import (
    INTENT_CART_RETRY,
    INTENT_CHECKOUT_ERROR,
    INTENT_GENERAL,
    INTENT_GREETING,
    INTENT_PRODUCT_LINK,
    INTENT_PURCHASE_INTENT,
)


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return text


def classify_intent(message: str) -> str:
    msg = _normalize(message)
    if not msg:
        return INTENT_GENERAL

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

    if any(phrase in msg for phrase in checkout_error_phrases):
        return INTENT_CHECKOUT_ERROR
    if any(phrase in msg for phrase in cart_retry_phrases):
        return INTENT_CART_RETRY
    if "http" in msg and "products/" in msg:
        return INTENT_PRODUCT_LINK
    if any(phrase in msg for phrase in purchase_phrases):
        return INTENT_PURCHASE_INTENT
    if any(phrase in msg for phrase in greeting_phrases):
        return INTENT_GREETING
    return INTENT_GENERAL
