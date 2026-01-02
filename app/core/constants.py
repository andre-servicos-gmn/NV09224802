INTENT_CHECKOUT_ERROR = "checkout_error"
INTENT_CART_RETRY = "cart_retry"
INTENT_PRODUCT_LINK = "product_link"
INTENT_PURCHASE_INTENT = "purchase_intent"
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
INTENT_GENERAL = "general"

INTENT_DESCRIPTIONS = {
    INTENT_CHECKOUT_ERROR: "User reports checkout link error or failure.",
    INTENT_CART_RETRY: "User asks to retry or regenerate checkout/cart link.",
    INTENT_PRODUCT_LINK: "User shares a product URL.",
    INTENT_PURCHASE_INTENT: "User wants to buy, pay, or checkout.",
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
    INTENT_GENERAL: "General or unclear message.",
}

SUPPORTED_INTENTS = list(INTENT_DESCRIPTIONS.keys())

INTENTS = set(SUPPORTED_INTENTS)

FRUSTRATION_KEYWORDS = ["que saco", "ridiculo", "droga", "aff"]
