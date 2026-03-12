# Constants for consultant mode — no cart/purchase intents.
INTENT_PRODUCT_LINK = "product_link"
INTENT_SEARCH_PRODUCT = "search_product"
INTENT_GREETING = "greeting"
INTENT_STORE_QUESTION = "store_question"
INTENT_SHIPPING_QUESTION = "shipping_question"
INTENT_PAYMENT_QUESTION = "payment_question"
INTENT_RETURN_EXCHANGE = "return_exchange"
INTENT_ORDER_STATUS = "order_status"
INTENT_ORDER_TRACKING = "order_tracking"
INTENT_ORDER_COMPLAINT = "order_complaint"
INTENT_PROVIDE_ORDER_ID = "provide_order_id"
INTENT_PROVIDE_EMAIL = "provide_email"
INTENT_MEDIA_UNSUPPORTED = "media_unsupported"
INTENT_GENERAL = "general"
DEFAULT_INTENT = INTENT_GENERAL

INTENT_DESCRIPTIONS: dict[str, str] = {
    INTENT_PRODUCT_LINK: "User shares a product URL to ask about it.",
    INTENT_SEARCH_PRODUCT: "User asks to search products by text.",
    INTENT_GREETING: "Greeting or hello.",
    INTENT_STORE_QUESTION: "General store policy or contact question.",
    INTENT_SHIPPING_QUESTION: "Shipping, delivery time, or freight question.",
    INTENT_PAYMENT_QUESTION: "Payment methods or pricing question.",
    INTENT_RETURN_EXCHANGE: "Return, exchange, or refund request.",
    INTENT_ORDER_STATUS: "Order status question.",
    INTENT_ORDER_TRACKING: "Tracking code or tracking status question.",
    INTENT_ORDER_COMPLAINT: "Delivery complaint or delayed shipment.",
    INTENT_PROVIDE_ORDER_ID: "User provides an order ID only.",
    INTENT_PROVIDE_EMAIL: "User provides an email address.",
    INTENT_MEDIA_UNSUPPORTED: "User sent an audio or image file.",
    INTENT_GENERAL: "General or unclear message.",
}

SUPPORTED_INTENTS: tuple[str, ...] = tuple(INTENT_DESCRIPTIONS.keys())
SUPPORTED_DOMAINS: tuple[str, ...] = ("sales", "support", "store_qa")

INTENTS = set(SUPPORTED_INTENTS)

FRUSTRATION_KEYWORDS = ["que saco", "ridiculo", "droga", "aff"]
