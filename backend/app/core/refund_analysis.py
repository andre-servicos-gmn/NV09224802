
import json
import os
import logging
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

REFUND_INTENT_ANALYSIS_PROMPT = """Atue como um Analista de Risco e Retenção.
Determine se o objetivo do usuário é INFORMATIVO (Dúvida) ou TRANSACIONAL (Ação de Reembolso/Cancelamento).

## INPUT
Mensagem: "{message}"
Contexto Prévio: {context}

## MATRIZ DE DECISÃO

1. **SOLICITAÇÃO REAL (is_request: true)**
   - O usuário quer reverter uma transação.
   - Sinais: Imperativos ("Quero devolver"), Ultimatos ("Não vou pagar"), Frustração extrema ligada a um pedido específico.
   - *Nuance:* "Chegou quebrado" -> Implica solicitação de troca/devolução, mesmo sem a palavra "reembolso".

2. **DÚVIDA / POLÍTICA (is_request: false)**
   - O usuário está sondando o terreno ou inseguro antes de comprar.
   - Sinais: Condicionais ("Se não servir, posso trocar?"), Perguntas de prazo ("Quanto tempo tenho?").

3. **AMBIGUIDADE CRÍTICA**
   - Se o usuário diz apenas "reembolso", olhe o histórico. Se ele acabou de reclamar de um defeito = REQUEST. Se está escolhendo produto = QUESTION.

## OUTPUT JSON
{{
  "is_request": true/false,
  "confidence": 0.0-1.0,
  "intent_category": "return_request | cancellation | policy_inquiry | complaint_only",
  "risk_level": "low (curioso) | medium (insatisfeito) | high (churn iminente)",
  "reasoning": "Uma frase explicando sua dedução."
}}
"""

def analyze_refund_intent(message: str, context: dict | None = None) -> dict:
    """
    Analisa se mensagem é solicitação de reembolso ou apenas pergunta.
    
    Returns:
        {
            "is_request": bool,
            "confidence": float,
            "reasoning": str
        }
    """
    logger.info(f"[REFUND_INTENT] Analyzing message: {message[:50]}...")
    
    try:
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=model, temperature=0)
        
        # Format prompt safely
        prompt = REFUND_INTENT_ANALYSIS_PROMPT.format(
            message=message.replace("{", "{{").replace("}", "}}"), 
            context=json.dumps(context or {}, ensure_ascii=False, indent=2)
        )
        
        result = llm.invoke([
            SystemMessage(content=prompt)
        ])
        
        response_text = result.content.strip()
        
        # Clean markdown
        if response_text.startswith("```"):
            parts = response_text.split("```")
            if len(parts) >= 2:
                response_text = parts[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
        
        parsed = json.loads(response_text)
        
        # Confidence threshold check (conservative approach)
        # Default behavior: treat as question if confidence is low
        if parsed.get("confidence", 0) < 0.75:
            logger.warning(f"[REFUND_INTENT] Low confidence ({parsed.get('confidence')}), treating as question")
            parsed["is_request"] = False
            parsed["reasoning"] += " (Low confidence override)"
            
        return parsed
        
    except Exception as e:
        logger.error(f"[REFUND_INTENT] Analysis failed: {e}")
        # Fail safe: treat as question to avoid unnecessary handoff
        return {
            "is_request": False,
            "confidence": 0.0,
            "reasoning": f"Error: {str(e)}"
        }
