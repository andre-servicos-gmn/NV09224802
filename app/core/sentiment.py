"""Sentiment analysis using LLM.

This module analyzes user messages for sentiment, frustration, and handoff needs
using the same LLM model used for responses. Results are for internal use only
and should NEVER be exposed to the client.
"""

import json
import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

DEFAULT_MODEL = "gpt-4o-mini"


def get_model_name() -> str:
    """Get model name from environment."""
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)


SENTIMENT_SYSTEM_PROMPT = """Você é um analisador de sentimentos para atendimento ao cliente.

Analise a mensagem do usuário e retorne APENAS um JSON válido com:

{
  "sentiment_level": "calm" | "frustrated" | "aggressive" | "threat",
  "sentiment_score": 0.0 a 1.0,
  "needs_handoff": true | false,
  "handoff_reason": null | "threat_detected" | "fraud_accusation" | "handoff_requested" | "high_frustration"
}

CRITÉRIOS:

1. sentiment_level:
   - "calm": Mensagem neutra ou educada
   - "frustrated": Reclamação moderada, impaciência
   - "aggressive": Insultos, acusações graves, xingamentos
   - "threat": Ameaças legais (processar, advogado, polícia, Procon)

2. needs_handoff = true quando:
   - Ameaça legal (processar, advogado, Procon, justiça)
   - Acusação de fraude/golpe/roubo
   - Pedido explícito de humano ("quero falar com atendente", "não quero bot")
   - Frustração extrema (muitos !!!, CAPS LOCK, xingamentos)

3. sentiment_score:
   - 0.0-0.3: Calmo
   - 0.4-0.6: Frustrado
   - 0.7-1.0: Agressivo/Ameaça

IMPORTANTE: Retorne APENAS o JSON, sem explicação ou markdown."""


def analyze_sentiment_llm(message: str) -> dict:
    """Analyze sentiment using LLM.
    
    This is for INTERNAL USE ONLY. Results should never be exposed to the client.
    
    Args:
        message: User message to analyze
        
    Returns:
        Dict with sentiment_level, sentiment_score, needs_handoff, handoff_reason
    """
    if not message or not message.strip():
        return {
            "sentiment_level": "calm",
            "sentiment_score": 0.0,
            "needs_handoff": False,
            "handoff_reason": None,
        }
    
    try:
        model = get_model_name()
        llm = ChatOpenAI(model=model, temperature=0)  # Low temp for consistent analysis
        
        result = llm.invoke([
            SystemMessage(content=SENTIMENT_SYSTEM_PROMPT),
            HumanMessage(content=f"Mensagem do usuário: {message}"),
        ])
        
        response_text = (result.content or "").strip()
        
        # Parse JSON response
        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        
        data = json.loads(response_text)
        
        return {
            "sentiment_level": data.get("sentiment_level", "calm"),
            "sentiment_score": float(data.get("sentiment_score", 0.0)),
            "needs_handoff": bool(data.get("needs_handoff", False)),
            "handoff_reason": data.get("handoff_reason"),
        }
        
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[Sentiment LLM Error] {e}")
        # Fallback to calm on error - never block the flow
        return {
            "sentiment_level": "calm",
            "sentiment_score": 0.0,
            "needs_handoff": False,
            "handoff_reason": None,
        }
