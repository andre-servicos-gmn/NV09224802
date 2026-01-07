"""Store Q&A response generation using RAG from Supabase."""

import os
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.llm_humanized import build_store_qa_prompt, get_model_name
from app.core.database import search_knowledge_base_semantic, resolve_tenant_uuid
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def _extract_metadata_content(metadata) -> str:
    """Extract readable content from metadata field."""
    if not metadata:
        return ""
    
    # If it's a JSON string, parse it first
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                parts = []
                if "title" in parsed:
                    parts.append(f"{parsed['title']}:")
                if "content" in parsed:
                    parts.append(str(parsed["content"]))
                return " ".join(parts) if parts else ""
        except json.JSONDecodeError:
            return metadata
    
    if isinstance(metadata, dict):
        parts = []
        if "title" in metadata:
            parts.append(f"{metadata['title']}:")
        if "content" in metadata:
            parts.append(str(metadata["content"]))
        return " ".join(parts) if parts else ""
    
    return str(metadata) if metadata else ""


def _build_knowledge_context(results: list) -> str:
    """Build knowledge context from RAG results."""
    if not results:
        return "[Manual da Loja]\nNenhuma informação encontrada na base de dados."
    
    lines = ["[Manual da Loja]"]
    lines.append("Use APENAS as informações abaixo para responder:")
    lines.append("")
    
    for item in results:
        category = item.get("category", "geral")
        metadata = item.get("metadata")
        content = _extract_metadata_content(metadata)
        if content:
            lines.append(f"[{category.upper()}] {content}")
            lines.append("")
    
    return "\n".join(lines)


def store_qa_respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Generate Store Q&A response using RAG from Supabase.
    
    This is the ONLY place where store knowledge is fetched.
    All information comes from the Supabase knowledge_base via semantic search.
    """
    
    # Get user message for semantic search
    user_message = state.last_user_message or ""
    
    if os.getenv("DEBUG"):
        print(f"[store_qa_respond] User message: {user_message}")
    
    # Semantic search in Supabase knowledge_base
    try:
        tenant_uuid = resolve_tenant_uuid(tenant.tenant_id)
        results = search_knowledge_base_semantic(
            tenant_uuid, 
            query=user_message, 
            limit=5
        )
        
        if os.getenv("DEBUG"):
            print(f"[store_qa_respond] RAG results: {len(results) if results else 0}")
        
        state.last_action = "rag_search"
        state.last_action_success = bool(results)
        
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[store_qa_respond] RAG error: {e}")
        results = []
        state.last_action = "rag_search"
        state.last_action_success = False
    
    # Build knowledge context from results
    knowledge_context = _build_knowledge_context(results)
    
    if os.getenv("DEBUG"):
        print(f"[store_qa_respond] Context: {knowledge_context[:200]}...")
    
    # Build system prompt
    system_prompt = build_store_qa_prompt(tenant)
    
    # Build user prompt with RAG context
    user_prompt = f"""[Mensagem do Cliente]
{user_message or '(sem mensagem)'}

[Intenção Detectada]
{state.intent}

{knowledge_context}

[Instruções]
Responda à dúvida do cliente usando APENAS as informações do Manual da Loja acima.
Se a informação não estiver no manual, diga: "Não tenho essa informação no momento. Posso verificar com a equipe e retornar."
Máximo 3 frases, sem markdown.
"""
    
    # Call LLM
    model = get_model_name()
    if os.getenv("DEBUG"):
        print(f"[store_qa_respond] Using model: {model}")
    
    llm = ChatOpenAI(model=model, temperature=0.7)
    result = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    
    state.last_bot_message = (result.content or "").strip()
    return state
