"""Enhanced LLM response generation with knowledge base context."""

import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.database import resolve_tenant_uuid, search_knowledge_base_simple
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.core.brand_voice import build_brand_voice_block

DEFAULT_MODEL = "gpt-4o-mini"


def get_model_name() -> str:
    """Get model name from environment or use default."""
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)


def _get_knowledge_context(tenant_id: str, categories: list[str] | None = None) -> str:
    """Fetch relevant knowledge base entries for context."""
    try:
        tenant_uuid = resolve_tenant_uuid(tenant_id)
        if categories:
            all_results = []
            for cat in categories:
                results = search_knowledge_base_simple(tenant_uuid, category=cat, limit=3)
                all_results.extend(results)
        else:
            all_results = search_knowledge_base_simple(tenant_uuid, limit=10)
        
        if not all_results:
            return ""
        
        context_lines = []
        for item in all_results:
            q = item.get("question", "")
            a = item.get("answer", "")
            if q and a:
                context_lines.append(f"P: {q}\nR: {a}")
        
        return "\n\n".join(context_lines)
    except Exception:
        return ""


def _build_base_system_prompt(tenant: TenantConfig, domain: str) -> str:
    """Build system prompt based on domain and tenant config."""
    base = (
        f"Você é um assistente virtual da {tenant.name}. "
        "Responda em português brasileiro, de forma curta e humana. "
        "Não use markdown. URLs devem ser enviadas como texto simples. "
        "Ordem da resposta: 1) empatia/confirmação, 2) explicação simples, 3) ação clara. "
    )
    
    if domain == "sales":
        base += (
            "Você está ajudando o cliente a comprar produtos. "
            "Se ele quiser comprar, gere ou forneça o link de checkout. "
            "Se o link falhar, ofereça alternativas. "
        )
    elif domain == "support":
        base += (
            "Você está ajudando com suporte pós-venda. "
            "Ajude com status de pedido, rastreamento e reclamações. "
            "Se o cliente está frustrado, reconheça primeiro antes de resolver. "
        )
    elif domain == "store_qa":
        base += (
            "Você está respondendo dúvidas sobre a loja. "
            "Use as informações da base de conhecimento para responder. "
            "Se não souber a resposta, diga que vai verificar com a equipe. "
        )
    
    brand_voice = build_brand_voice_block(tenant.brand_voice)
    if brand_voice:
        base += f"{brand_voice} "
    
    return base


def _build_user_prompt(state: ConversationState, knowledge_context: str) -> str:
    """Build user prompt with state and context."""
    lines = [
        f"Mensagem do cliente: {state.last_user_message or ''}",
        f"Intenção detectada: {state.intent}",
    ]
    
    # Add relevant state info
    if state.selected_product_id:
        title = state.metadata.get("product_title", "produto selecionado")
        lines.append(f"Produto selecionado: {title}")
    
    if state.order_id:
        lines.append(f"Número do pedido: {state.order_id}")
        if state.tracking_url:
            lines.append(f"Link de rastreio: {state.tracking_url}")
        status = state.metadata.get("order_status")
        if status:
            lines.append(f"Status do pedido: {status}")
    
    checkout_link = state.metadata.get("checkout_link")
    if checkout_link:
        lines.append(f"Link de checkout gerado: {checkout_link}")
    
    faq_answer = state.metadata.get("faq_answer")
    if faq_answer:
        lines.append(f"Resposta da FAQ encontrada: {faq_answer}")
    
    if state.frustration_level >= 2:
        lines.append(f"ATENÇÃO: Cliente parece frustrado (nível {state.frustration_level})")
    
    if state.ticket_opened:
        lines.append("Um ticket de suporte foi aberto para este caso.")
    
    # Add knowledge context
    if knowledge_context:
        lines.append("\n--- Base de Conhecimento ---")
        lines.append(knowledge_context)
    
    lines.append("\nGere uma resposta natural e útil para o cliente.")
    
    return "\n".join(lines)


def generate_llm_response(
    state: ConversationState,
    tenant: TenantConfig,
    domain: str,
    categories: list[str] | None = None,
) -> str:
    """Generate LLM response with knowledge base context.
    
    Args:
        state: Current conversation state
        tenant: Tenant configuration
        domain: Current domain (sales, support, store_qa)
        categories: Optional list of knowledge base categories to fetch
    
    Returns:
        Generated response text
    """
    try:
        # Get knowledge context
        knowledge_context = _get_knowledge_context(tenant.tenant_id, categories)
        
        # Build prompts
        system_prompt = _build_base_system_prompt(tenant, domain)
        user_prompt = _build_user_prompt(state, knowledge_context)
        
        # Call LLM
        model = get_model_name()
        llm = ChatOpenAI(model=model, temperature=0.4)
        result = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        
        response = (result.content or "").strip()
        
        # Ensure checkout link is included if present
        checkout_link = state.metadata.get("checkout_link")
        if checkout_link and checkout_link not in response:
            response = f"{response}\n\n{checkout_link}"
        
        return response
    except Exception as e:
        # Fallback response
        if os.getenv("DEBUG"):
            print(f"[LLM] Error: {e}")
        return _get_fallback_response(state, domain)


def _get_fallback_response(state: ConversationState, domain: str) -> str:
    """Get fallback response when LLM fails."""
    if state.intent == "greeting":
        return "Oi! Como posso ajudar?"
    
    if domain == "sales":
        checkout_link = state.metadata.get("checkout_link")
        if checkout_link:
            return f"Pronto! Aqui está o link para finalizar:\n{checkout_link}"
        return "Me manda o link do produto ou o nome pra eu ajudar."
    
    if domain == "support":
        if state.tracking_url:
            return f"Aqui está o rastreio do seu pedido:\n{state.tracking_url}"
        if state.order_id:
            return f"Estou verificando o pedido {state.order_id}. Um momento."
        return "Me passa o número do pedido para eu verificar."
    
    if domain == "store_qa":
        faq = state.metadata.get("faq_answer")
        if faq:
            return faq
        return "Posso ajudar com dúvidas sobre frete, pagamento ou trocas."
    
    return "Como posso ajudar?"
