
import json
import os
import logging
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

REFUND_INTENT_ANALYSIS_PROMPT = """Analise se o usuário está SOLICITANDO um reembolso/cancelamento ou apenas PERGUNTANDO sobre a política.

## MENSAGEM DO USUÁRIO
"{message}"

## CONTEXTO (se disponível)
{context}

---

## CRITÉRIOS

SOLICITAÇÃO (return TRUE):
- "quero meu dinheiro de volta"
- "cancela meu pedido"
- "quero reembolso do pedido #12345"
- "devolve meu dinheiro"
- Usuário já tem um pedido e quer cancelar/reembolsar

PERGUNTA (return FALSE):
- "como funciona o reembolso?"
- "qual a política de devolução?"
- "em quanto tempo cai o reembolso?"
- "posso pedir reembolso depois de quanto tempo?"
- Usuário está se informando sobre o processo

## CASOS AMBÍGUOS
Se não tem certeza, considere:
- Usuário mencionou número de pedido? → Provavelmente SOLICITAÇÃO
- Usa verbos no imperativo? ("cancela", "devolve") → SOLICITAÇÃO
- Usa verbos no condicional/interrogativo? ("posso", "como") → PERGUNTA

---

## SUA TAREFA
Retorne JSON válido:
{{
  "is_request": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "breve explicação"
}}

Sua resposta (apenas JSON):
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
