"""AgentState v2 — LangGraph idiomático com MessagesState."""

from typing import Optional
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """State único e flat do agente v2.

    Herda `messages: Annotated[list[BaseMessage], add_messages]` de MessagesState.
    Todo o resto é flat — sem submodels, sem 4 camadas. LangGraph cuida do resto.
    """
    # ─── Identity (imutável durante a conversa) ───
    tenant_id: str
    session_id: str
    channel: str  # "whatsapp" | "web"

    # ─── Domain context (preenchido por tools, lido pelo supervisor) ───
    focused_product_id: Optional[str]
    focused_product_title: Optional[str]
    selected_variant_id: Optional[str]
    checkout_url: Optional[str]

    order_id: Optional[str]
    order_status: Optional[str]
    tracking_url: Optional[str]

    # ─── Memory (persistente entre turnos via checkpointer) ───
    facts: dict
    soft_context: dict
    frustration_level: int

    # ─── Turn metadata ───
    last_tool_called: Optional[str]
    handoff_reason: Optional[str]
