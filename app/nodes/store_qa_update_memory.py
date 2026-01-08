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


SYSTEM_PROMPT = """Você é um extrator de fatos de conversas de atendimento ao cliente.

Sua tarefa é analisar a conversa e extrair APENAS fatos que o cliente EXPLICITAMENTE disse.

REGRAS ABSOLUTAS:
1. NÃO INFERIR dados que não foram ditos
2. Se o cliente disser "meu pedido 1234", extraia order_id: "1234"
3. Se o cliente disser "paguei via Pix", extraia pagamento: "pix"
4. Se o cliente corrigir um dado, use o valor NOVO (mais recente)
5. NÃO invente CPF, telefone, email se não foram ditos
6. Mantenha o resumo CURTO (2-4 linhas)

REGRA ESPECIAL - PERGUNTAS INSTITUCIONAIS:
Para perguntas sobre CNPJ, razão social, endereço da empresa, política geral, formas de pagamento:
- NÃO coloque order_id ou email em missing_info_needed
- Essas perguntas devem ser respondidas via manual da loja

FORMATO DE SAÍDA (JSON):
{
  "conversation_summary": "Resumo curto da conversa (2-4 linhas)",
  "facts": {
    "order_id": "valor ou null",
    "email": "valor ou null",
    "nome": "valor ou null",
    "cep": "valor ou null",
    "produto": "valor ou null",
    "problema": "descrição curta ou null",
    "pagamento": "método ou null",
    "data_compra": "data ou null",
    "urgencia": "baixa/média/alta ou null"
  },
  "missing_info_needed": ["lista de info importante que falta - NUNCA order_id/email para perguntas institucionais"]
}

Retorne APENAS o JSON, sem explicações."""


def store_qa_update_memory(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Update conversation memory by extracting facts from recent messages.
    
    This is an ACTION node per AGENT.md:
    - Executes action (extract facts via LLM)
    - Updates state (conversation_summary, facts, missing_info_needed)
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

Extraia os fatos e gere o resumo."""

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
        if "conversation_summary" in parsed:
            state.conversation_summary = parsed["conversation_summary"]
        
        if "facts" in parsed and isinstance(parsed["facts"], dict):
            # Merge with existing facts, new values override old
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
            state.missing_info_needed = []
            if os.getenv("DEBUG"):
                print(f"[Memory] institutional={is_institutional} manual_intent={is_manual_intent} → no missing info")
        elif "missing_info_needed" in parsed:
            # For normal support questions, keep order_id/email if LLM says it's needed
            # Only filter out clearly irrelevant items (like CNPJ for user)
            state.missing_info_needed = parsed.get("missing_info_needed", [])
        
        state.last_action = "update_memory"
        state.last_action_success = True
        
        if os.getenv("DEBUG"):
            print(f"[Memory] intent={state.intent} Summary: {state.conversation_summary}")
            print(f"[Memory] Facts: {state.facts}")
            print(f"[Memory] Missing: {state.missing_info_needed}")
        
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
