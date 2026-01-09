import os
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError, confloat

from app.core.constants import INTENT_DESCRIPTIONS, SUPPORTED_DOMAINS, SUPPORTED_INTENTS
from app.core.llm import get_model_name
from app.core.llm_utils import normalize_token_usage


IntentLiteral = Literal[*SUPPORTED_INTENTS]
DomainLiteral = Literal[*SUPPORTED_DOMAINS]


class TopIntent(BaseModel):
    intent: IntentLiteral
    confidence: confloat(ge=0.0, le=1.0)


class RouterResult(BaseModel):
    domain: DomainLiteral
    intent: IntentLiteral
    confidence: confloat(ge=0.0, le=1.0)
    ambiguous: bool = False
    top_intents: list[TopIntent] = Field(default_factory=list)
    entities: dict = Field(default_factory=dict)
    rationale: str = ""
    token_usage: dict = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


def _build_intent_lines(intents: list[str]) -> str:
    lines = []
    for intent in intents:
        description = INTENT_DESCRIPTIONS.get(intent, "No description.")
        lines.append(f"- {intent}: {description}")
    return "\n".join(lines)


def _build_system_prompt() -> str:
    return (
        "You are a router that classifies the message domain and intent and extracts entities. "
        "You only return JSON. Do not add any other text.\n"
        "Rules:\n"
        "- Domain must be one of: sales, support, store_qa.\n"
        "- If it is purchase/checkout/payment link, domain = sales.\n"
        "- If it is product search, browsing options, or selecting products, domain = sales.\n"
        "- If it is order/tracking/delivery complaint, domain = support.\n"
        "- If it is store policy or general store question, domain = store_qa.\n"
        "- Intent must be one of the supported intents listed by the user.\n"
        "- NEVER invent an intent outside the list.\n"
        "- If ambiguous, set ambiguous=true and reduce confidence below 0.75.\n"
        "- If order_id (3-8 digits) or tracking/delivery complaint is present, prioritize domain=support.\n"
        "- If message is only a number (ex: 1001), intent=provide_order_id and domain=support.\n"
        "- If product_url is present, domain=sales and intent=product_link unless order_id is also present.\n"
        "- If message says 'gera de novo' or 'tenta de novo' and context indicates link/checkout, "
        "domain=sales and intent=cart_retry.\n"
        "- Entities: product_url (product URL), order_id (3-8 digits), "
        "email (email address), tracking_complaint_days (integer days when user says 'X dias'), "
        "search_query (short keywords for product search, e.g. 'blue necklace' from 'I want a blue necklace').\n"
        "- Confidence: 0.9+ when clear, 0.6-0.75 when ambiguous, <0.65 when very uncertain.\n"
        "- top_intents must be a list of objects: {intent, confidence}, highest confidence first.\n"
        "Return JSON with keys: domain, intent, confidence, ambiguous, top_intents, entities, rationale.\n"
        "Rationale must be short and for debugging only."
    )


def _build_user_prompt(message: str, intents: list[str], context: dict | None) -> str:
    intent_lines = _build_intent_lines(intents)
    context_block = "None"
    if context:
        parts = [f"{key}={value}" for key, value in context.items()]
        context_block = "; ".join(parts)
    return (
        "Supported intents:\n"
        f"{intent_lines}\n\n"
        f"Context:\n{context_block}\n\n"
        "Message:\n"
        f"{message}\n\n"
        "Return ONLY valid JSON."
    )


def classify_with_llm(
    message: str,
    context: dict | None,
    intents: tuple[str, ...],
    timeout_s: float | None = None,
) -> RouterResult:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")
    if not intents:
        raise ValueError("Intents list is empty.")
    for intent in intents:
        if intent not in SUPPORTED_INTENTS:
            raise ValueError(f"Unsupported intent: {intent}")

    llm = ChatOpenAI(model=get_model_name(), temperature=0, request_timeout=timeout_s)
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(message, list(intents), context)
    result = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
    content = (result.content or "").strip()
    try:
        router_result = RouterResult.model_validate_json(content)
        # Capture token usage from LangChain response
        usage_raw = result.response_metadata.get("token_usage")
        router_result.token_usage = normalize_token_usage(usage_raw)
        return router_result
    except ValidationError as exc:
        raise ValueError("Invalid router JSON.") from exc
