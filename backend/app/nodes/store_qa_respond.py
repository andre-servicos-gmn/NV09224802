"""Store Q&A response generation using RAG from Supabase + memory context."""

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
    
    # Debug: log first item keys
    if os.getenv("DEBUG") and results:
        first_item = results[0]
        print(f"[RAG] First result keys: {list(first_item.keys())}")
    
    for idx, item in enumerate(results):
        category = item.get("category", "geral")
        content = ""
        
        # Try multiple formats
        metadata = item.get("metadata")
        if metadata:
            content = _extract_metadata_content(metadata)
        if not content:
            content = item.get("content") or item.get("text") or item.get("document") or ""
        if not content:
            fallback_item = {k: v for k, v in item.items() if k != "embedding"}
            content = str(fallback_item)[:500]
        
        if content and content.strip():
            lines.append(f"[{category.upper()}] {content}")
            lines.append("")
            if os.getenv("DEBUG") and idx == 0:
                print(f"[RAG] Extracted content: {content[:120]}...")
    
    return "\n".join(lines)


def _build_memory_context(state: ConversationState) -> str:
    """Build memory context from state for human-like responses.
    
    SECURITY: Only includes facts_safe (no PII) and redacted summary.
    PII is NOT sent to the LLM prompt.
    """
    from app.core.security import redact_pii
    
    lines = []
    
    if state.conversation_summary:
        lines.append("[Resumo da Conversa]")
        # Summary should already be redacted, but double-check
        lines.append(redact_pii(state.conversation_summary))
        lines.append("")
    
    # Only include facts_safe (non-PII) in prompt
    if state.facts_safe:
        lines.append("[Fatos Conhecidos sobre o Cliente]")
        for key, value in state.facts_safe.items():
            if value:
                lines.append(f"- {key}: {value}")
        lines.append("")
    
    if state.missing_info_needed:
        lines.append("[Info que Precisamos Perguntar]")
        for info in state.missing_info_needed[:1]:
            lines.append(f"- {info}")
        lines.append("")
    
    return "\n".join(lines) if lines else ""


def store_qa_respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Generate Store Q&A response using RAG + memory context.
    
    Handles two strategies:
    - ask_one_missing: Ask for ONE missing piece of info
    - rag_answer: Use RAG to answer the question
    """
    
    user_message = state.last_user_message or ""
    
    if os.getenv("DEBUG"):
        print(f"[store_qa_respond] Strategy: {state.last_strategy}")
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
        
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[store_qa_respond] RAG error: {e}")
        results = []
    
    knowledge_context = _build_knowledge_context(results)
    memory_context = _build_memory_context(state)
    
    if os.getenv("DEBUG"):
        print(f"[store_qa_respond] Memory context: {memory_context[:200]}..." if memory_context else "[store_qa_respond] No memory context")
    
    system_prompt = build_store_qa_prompt(tenant)
    
    # Build prompt based on strategy
    if state.last_strategy == "ask_one_missing":
        missing_info = state.missing_info_needed[0] if state.missing_info_needed else "mais informações"
        
        user_prompt = f"""[Mensagem do Cliente]
{user_message or '(sem mensagem)'}

{memory_context}

{knowledge_context}

[Estratégia: Perguntar Info Faltante]
Você precisa perguntar: {missing_info}

[Instruções]
- Primeiro, reconheça o que o cliente disse
- Depois, faça UMA pergunta natural sobre: {missing_info}
- NÃO pergunte algo que já está nos fatos conhecidos
- Seja empático e humano
- Máximo 3 frases, sem markdown

Exemplo: "Entendi. Você pagou via Pix e ainda não apareceu o rastreio. Pra eu verificar certinho, me manda o número do pedido ou o e-mail da compra?"
"""
        state.repeat_count += 1
        
    else:
        # Strategy: rag_answer (default)
        user_prompt = f"""[Mensagem do Cliente]
{user_message or '(sem mensagem)'}

{memory_context}

[Intenção Detectada]
{state.intent}

{knowledge_context}

[Instruções]
- Use o resumo da conversa para dar contexto
- Responda usando APENAS informações do Manual da Loja
- Se não estiver no manual, diga: "Não tenho essa informação no momento. Posso verificar com a equipe."
- Use os fatos conhecidos para personalizar (ex: "sobre seu pedido 1234...")
- NÃO invente prazos, políticas ou status
- Copie exatamente números e prazos do manual (não converta dias↔horas)
- Máximo 3 frases, sem markdown
"""
    
    # Call LLM
    model = get_model_name()
    if os.getenv("DEBUG"):
        print(f"[store_qa_respond] Using model: {model}")
    
    llm = ChatOpenAI(model=model, temperature=0.2)
    result = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    
    response = (result.content or "").strip()
    state.last_bot_message = response
    state.last_action = "generate_response"
    state.last_action_success = bool(response)
    
    return state

