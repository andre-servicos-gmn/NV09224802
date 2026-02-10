"""Store Q&A Memory Update Action Node.

Extracts facts from conversation and updates state memory.
This node is responsible for maintaining short-term memory for human-like conversations.

Per AGENT.md:
- Action Nodes execute actions and update state
- Action Nodes do NOT decide flow
- Only extract EXPLICIT facts (no inference)
"""

import os
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


SYSTEM_PROMPT = """Você é o Córtex de Memória do Nouvaris AI.
Sua função não é apenas registrar dados, mas entender o ESTADO ATUAL do cliente para guiar a próxima ação.

## TAREFA
Analise a última interação e atualize o estado da memória.

## REGRAS DE INTEGRIDADE (HARD RULES)
1. **Fatos Rígidos vs. Contexto:** Separe o que é DADO TÉCNICO (CPF, ID) do que é CONTEXTO (motivação, urgência).
2. **Princípio da Substituição:** Se o usuário corrigiu ("não é M, é G"), esqueça o antigo, grave o novo.
3. **Detecção de Bloqueio:** Se falta uma informação CRÍTICA para a próxima etapa lógica, sinalize em `blocking_info`.

## EXTRAÇÃO DE CONTEXTO (A "Alma" da venda)
- Se o usuário der uma razão de compra ("presente", "trabalho"), extraia em `motivation`.
- Se demonstrar pressa ("preciso pra ontem"), marque `urgency: high`.

FORMATO DE SAÍDA (JSON):
{
  "interaction_summary": "Visão tática: O que acabou de acontecer? (Ex: Usuário rejeitou frete e pediu desconto)",
  "hard_facts": {
    "order_id": "valor ou null",
    "email": "valor ou null",
    "customer_name": "valor ou null",
    "zip_code": "valor ou null",
    "payment_method": "valor ou null",
    "nome": "valor ou null",
    "cep": "valor ou null",
    "produto": "valor ou null",
    "problema": "valor ou null",
    "data_compra": "valor ou null"
  },
  "soft_context": {
    "product_interest": "Ex: Tênis de corrida preto",
    "motivation": "Ex: Presente de natal / Dor nas costas",
    "urgency": "low|medium|high",
    "sentiment": "positive|neutral|frustrated"
  },
  "blocking_info": ["O que FALTA EXATAMENTE para o agente prosseguir? Ex: 'tamanho_produto'"]
}

Retorne APENAS o JSON, sem explicações."""


def store_qa_update_memory(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Update conversation memory by extracting facts from recent messages.
    
    This is an ACTION node per AGENT.md:
    - Executes action (extract facts via LLM)
    - Executes action (extract facts via LLM)
    - Updates state (facts, blocking_info, soft_context)
    - Does NOT decide flow
    """
    
    # Get recent conversation history (last 10 messages)
    recent_history = state.conversation_history[-10:] if state.conversation_history else []
    
    if not recent_history:
        # No history to analyze
        state.last_action = "update_memory"
        state.last_action_success = True
        return state
    
    # Format conversation for LLM
    conversation_text = []
    for entry in recent_history:
        role = "Cliente" if entry.get("role") == "user" else "Atendente"
        message = entry.get("message", "")
        conversation_text.append(f"{role}: {message}")
    
    # Include current facts for context (so LLM knows what was already extracted)
    current_facts = state.facts or {}
    
    user_prompt = f"""CONVERSA ATUAL:
{chr(10).join(conversation_text)}

FATOS JÁ CONHECIDOS (atualize se o cliente corrigir):
{json.dumps(current_facts, ensure_ascii=False, indent=2)}

ÚLTIMA MENSAGEM DO CLIENTE:
{state.last_user_message or "(nenhuma)"}

Extraia o contexto e atualize a memória."""

    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        result = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
        
        response_text = (result.content or "").strip()
        
        # Parse JSON response
        # Handle markdown code blocks if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        
        parsed = json.loads(response_text)
        
        # Update state with extracted data
        # Update state with extracted data
        # conversation_summary removed in State 2.0
        # if "interaction_summary" in parsed:
        #     state.conversation_summary = parsed["interaction_summary"]

        
        # Process Hard Facts
        if "hard_facts" in parsed and isinstance(parsed["hard_facts"], dict):
            for key, value in parsed["hard_facts"].items():
                if value is not None and value != "null" and value != "":
                    state.facts[key] = value

        # Process Soft Context (Now stored in state.soft_context)
        if "soft_context" in parsed and isinstance(parsed["soft_context"], dict):
            for key, value in parsed["soft_context"].items():
                if value is not None and value != "null" and value != "":
                    state.soft_context[key] = value
        
        # Fallback for old prompt format (just in case)
        if "facts" in parsed and isinstance(parsed["facts"], dict):
             for key, value in parsed["facts"].items():
                if value is not None and value != "null" and value != "":
                    state.facts[key] = value

        # DETERMINISTIC RULE: Institutional questions never ask for order/email
        institutional_terms = ["cnpj", "razão social", "razao social", "endereço", "endereco", 
                               "inscrição estadual", "inscricao estadual", "telefone da loja",
                               "horário de funcionamento", "horario de funcionamento"]
        msg_lower = (state.last_user_message or "").lower()
        is_institutional = any(term in msg_lower for term in institutional_terms)
        
        # HARDEN: Manual/policy intents should NEVER ask for missing info
        manual_intents = {"shipping_question", "payment_question", "return_exchange", "store_question"}
        is_manual_intent = state.intent in manual_intents
        
        if is_institutional or is_manual_intent:
            # For institutional/policy questions, don't ask for any missing info
            state.blocking_info = []
            if os.getenv("DEBUG"):
                print(f"[Memory] institutional={is_institutional} manual_intent={is_manual_intent} → no missing info")
        elif "blocking_info" in parsed:
             state.blocking_info = parsed.get("blocking_info", [])
        elif "missing_info_needed" in parsed:
            # For normal support questions, keep order_id/email if LLM says it's needed
            # Only filter out clearly irrelevant items (like CNPJ for user)
            state.blocking_info = parsed.get("missing_info_needed", [])
        
        state.last_action = "update_memory"
        state.last_action_success = True
        
        if os.getenv("DEBUG"):
            print(f"[Memory] intent={state.intent}")
            print(f"[Memory] Facts: {state.facts}")
            print(f"[Memory] Soft: {state.soft_context}")
            print(f"[Memory] Blocking: {state.blocking_info}")
        
    except json.JSONDecodeError as e:
        if os.getenv("DEBUG"):
            print(f"[Memory] JSON parse error: {e}")
        state.last_action = "update_memory"
        state.last_action_success = False
        
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[Memory] Error: {e}")
        state.last_action = "update_memory"
        state.last_action_success = False
    
    return state
