from pydantic import BaseModel, Field


class ConversationState(BaseModel):
    tenant_id: str
    session_id: str
    channel: str = "whatsapp"
    domain: str | None = None
    intent: str = "general"
    selected_product_id: str | None = None
    selected_variant_id: str | None = None
    quantity: int = 1
    order_id: str | None = None
    customer_email: str | None = None
    tracking_url: str | None = None
    tracking_last_update_days: int | None = None
    ticket_opened: bool = False
    last_action: str | None = None
    last_strategy: str | None = None
    last_action_success: bool = True
    frustration_level: int = 0
    sentiment_level: str = "calm"
    sentiment_score: float = 0.0
    needs_handoff: bool = False
    handoff_reason: str | None = None
    last_user_message: str | None = None
    last_bot_message: str | None = None
    next_step: str | None = None
    metadata: dict = Field(default_factory=dict)

    def bump_frustration(self) -> None:
        self.frustration_level += 1

    def set_intent(self, intent: str) -> None:
        self.intent = intent
