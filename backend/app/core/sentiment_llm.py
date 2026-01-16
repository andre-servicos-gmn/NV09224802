import os
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError, confloat


SentimentLiteral = Literal["calm", "frustrated", "aggressive", "threat"]


class SentimentResult(BaseModel):
    sentiment_level: SentimentLiteral
    sentiment_score: confloat(ge=0.0, le=1.0)
    needs_handoff: bool
    handoff_reason: str

    model_config = {"extra": "forbid"}


def _build_system_prompt() -> str:
    return (
        "You classify sentiment and risk from a single user message. "
        "Return ONLY JSON with keys: sentiment_level, sentiment_score, needs_handoff, handoff_reason. "
        "sentiment_level must be one of: calm, frustrated, aggressive, threat. "
        "If threat or severe aggression, set needs_handoff=true. "
        "Be conservative and avoid over-escalation. No extra text."
    )


def analyze_sentiment_llm(message: str, timeout_s: float | None = None) -> SentimentResult:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")
    model = os.getenv("SENTIMENT_LLM_MODEL", "gpt-5-nano")
    llm = ChatOpenAI(model=model, temperature=0, max_output_tokens=80, request_timeout=timeout_s)
    result = llm.invoke(
        [
            SystemMessage(content=_build_system_prompt()),
            HumanMessage(content=message),
        ]
    )
    content = (result.content or "").strip()
    try:
        return SentimentResult.model_validate_json(content)
    except ValidationError as exc:
        raise ValueError("Invalid sentiment JSON.") from exc
