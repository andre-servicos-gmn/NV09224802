from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from app.core.constants import INTENT_DESCRIPTIONS, SUPPORTED_INTENTS
from app.core.llm import get_model_name


class RouterResult(BaseModel):
    domain: Literal["sales", "support", "store_qa"]
    intent: str
    confidence: float = Field(ge=0.0, le=1.0)
    entities: dict = Field(default_factory=dict)
    rationale: str

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
        "- If it is order/tracking/delivery complaint, domain = support.\n"
        "- If it is store policy or general store question, domain = store_qa.\n"
        "- Intent must be one of the supported intents listed by the user.\n"
        "- Entities: product_url (product URL), order_id (3-8 digits), "
        "email (email address), tracking_complaint_days (integer days when user says 'X dias').\n"
        "- Confidence: 0.9+ when clear, 0.6-0.75 when ambiguous, <0.65 when very uncertain.\n"
        "Return JSON with keys: domain, intent, confidence, entities, rationale.\n"
        "Rationale must be short and for debugging only."
    )


def _build_user_prompt(message: str, intents: list[str]) -> str:
    intent_lines = _build_intent_lines(intents)
    return (
        "Supported intents:\n"
        f"{intent_lines}\n\n"
        "Message:\n"
        f"{message}\n\n"
        "Return ONLY valid JSON."
    )


def classify_with_llm(message: str, intents: list[str]) -> RouterResult:
    if not intents:
        raise ValueError("Intents list is empty.")
    for intent in intents:
        if intent not in SUPPORTED_INTENTS:
            raise ValueError(f"Unsupported intent: {intent}")

    llm = ChatOpenAI(model=get_model_name(), temperature=0)
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(message, intents)
    result = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
    content = (result.content or "").strip()
    try:
        return RouterResult.model_validate_json(content)
    except ValidationError as exc:
        raise ValueError("Invalid router JSON.") from exc
