# Modified: add search/products/variants/cart fields for sales flow.
from pydantic import BaseModel, Field


class ConversationState(BaseModel):
    tenant_id: str
    session_id: str
    personality_id: str = "professional"
    channel: str = "whatsapp"
    domain: str | None = None
    intent: str = "general"
    search_query: str | None = None
    selected_products: list[dict] = Field(default_factory=list)
    selected_product_id: str | None = None
    available_variants: list[dict] = Field(default_factory=list)
    selected_variant_id: str | None = None
    cart_items: list[dict] = Field(default_factory=list)
    quantity: int = 1
    order_id: str | None = None
    customer_email: str | None = None
    tracking_url: str | None = None
    tracking_last_update_days: int | None = None
    ticket_opened: bool = False
    last_action: str | None = None
    last_strategy: str | None = None
    last_action_success: bool | None = None  # None = no action ran yet
    frustration_level: int = 0
    sentiment_level: str = "calm"
    sentiment_score: float = 0.0
    needs_handoff: bool = False
    handoff_reason: str | None = None
    last_user_message: str | None = None
    last_bot_message: str | None = None
    next_step: str | None = None
    metadata: dict = Field(default_factory=dict)
    # Conversation memory for personalized context
    conversation_history: list[dict] = Field(default_factory=list)
    original_complaint: str | None = None  # Stores the original issue for context
    
    # Short-term memory for Store Q&A (human touch)
    conversation_summary: str | None = None  # 2-6 lines summary
    facts: dict = Field(default_factory=dict)  # order_id, email, nome, cep, produto, problema, pagamento, data_compra, urgencia
    missing_info_needed: list[str] = Field(default_factory=list)  # What info we still need
    repeat_count: int = 0  # Avoid repeating same question

    def bump_frustration(self) -> None:
        self.frustration_level += 1

    def set_intent(self, intent: str) -> None:
        self.intent = intent

    def add_to_history(self, role: str, message: str) -> None:
        """Add a message to conversation history (store 20, use 10 for context)."""
        self.conversation_history.append({"role": role, "message": message})
        # Keep last 20 messages in storage, 10 used for LLM context
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]
        # Capture original complaint for persistent context
        if role == "user" and not self.original_complaint:
            if any(w in message.lower() for w in ["errado", "problema", "reclamação", "atrasado", "não chegou", "defeito"]):
                self.original_complaint = message


