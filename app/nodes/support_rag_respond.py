"""Support RAG response for policy questions (shipping, payment, returns).

Responds to policy questions using RAG without requiring order lookup.
"""

import os
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.llm_humanized import get_model_name
from app.core.database import search_knowledge_base_semantic, resolve_tenant_uuid
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def _build_knowledge_context(results: list) -> str:
    """Build knowledge context from RAG results."""
    if not results:
        return ""
    
    lines = ["[Manual da Loja]"]
    lines.append("Use APENAS as informações abaixo:")
    lines.append("")
    
    for item in results:
        category = item.get("category", "geral")
        metadata = item.get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except:
                pass
        
        if isinstance(metadata, dict):
            content = metadata.get("content") or metadata.get("title") or ""
        else:
            content = str(metadata) if metadata else ""
        
        if content:
            lines.append(f"[{category.upper()}] {content}")
            lines.append("")
    
    return "\n".join(lines)


def support_rag_respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Generate response for policy questions using RAG.
    
    This handles shipping, payment, return/exchange questions without order lookup.
    """
    
    user_message = state.last_user_message or ""
    
    if os.getenv("DEBUG"):
        print(f"[support_rag_respond] Policy intent: {state.intent}")
        print(f"[support_rag_respond] User message: {user_message}")
    
    # Semantic search in knowledge base
    try:
        tenant_uuid = resolve_tenant_uuid(tenant.tenant_id)
        results = search_knowledge_base_semantic(
            tenant_uuid, 
            query=user_message, 
            limit=5
        )
        
        if os.getenv("DEBUG"):
            print(f"[support_rag_respond] RAG results: {len(results) if results else 0}")
        
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[support_rag_respond] RAG error: {e}")
        results = []
    
    knowledge_context = _build_knowledge_context(results)
    
    # Build prompt
    system_prompt = f"""Você é Ana, assistente virtual da {tenant.name}.

REGRAS:
- Responda APENAS usando informações do Manual da Loja
- Se não houver informação no manual, diga: "Não encontrei essa informação no manual. Posso verificar com a equipe."
- NUNCA invente prazos, preços ou políticas
- Copie exatamente números, valores e prazos do manual (não converta dias↔horas, não arredonde)
- Máximo 3 frases, sem markdown
- Tom amigável e profissional"""

    if knowledge_context:
        user_prompt = f"""[Pergunta do Cliente]
{user_message}

{knowledge_context}

Responda a pergunta usando somente as informações do manual."""
    else:
        user_prompt = f"""[Pergunta do Cliente]
{user_message}

[Manual da Loja]
Nenhuma informação encontrada.

Diga que não encontrou essa informação no manual e que pode verificar com a equipe."""

    # Call LLM
    model = get_model_name()
    llm = ChatOpenAI(model=model, temperature=0.2)
    result = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    
    state.last_bot_message = (result.content or "").strip()
    state.last_action = "rag_policy_response"
    state.last_action_success = True
    
    return state
