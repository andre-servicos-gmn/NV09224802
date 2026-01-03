"""Humanized LLM response generation for all agents.

Uses OpenAI to generate natural, human-like responses as if from a real
customer service representative.
"""

import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.database import resolve_tenant_uuid, search_knowledge_base_simple
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig

DEFAULT_MODEL = "gpt-4o-mini"


def get_model_name() -> str:
    """Get model name from environment."""
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)


# =============================================================================
# KNOWLEDGE BASE CONTEXT
# =============================================================================


def get_knowledge_context(tenant_id: str, categories: list[str] | None = None) -> str:
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
        
        context_lines = ["[Informações da Base de Conhecimento]"]
        for item in all_results:
            q = item.get("question", "")
            a = item.get("answer", "")
            if q and a:
                context_lines.append(f"- {q}: {a}")
        
        return "\n".join(context_lines)
    except Exception:
        return ""


# =============================================================================
# HUMANIZED SYSTEM PROMPTS
# =============================================================================


BASE_PERSONA = """Você é Ana, assistente virtual de atendimento ao cliente.

PERSONALIDADE:
- Profissional, cordial e eficiente
- Educada e prestativa, mas direta ao ponto
- Transmite confiança e competência
- Mostra empatia quando o cliente tem problemas

ESTILO DE COMUNICAÇÃO:
- Tom equilibrado: profissional mas acolhedor
- Frases claras e objetivas
- Evita gírias e expressões muito informais
- Pode usar "por favor", "com certeza", "claro"
- Sem emojis (ou no máximo 1 quando apropriado)

REGRAS:
- NUNCA use markdown (sem **, ##, -, etc)
- URLs devem aparecer sozinhas em uma linha
- Máximo 3 frases por resposta
- Seja direta e resolva o problema rapidamente
- Se não souber, diga que vai verificar com a equipe"""


def build_sales_prompt(tenant: TenantConfig) -> str:
    """Build system prompt for Sales agent."""
    return f"""{BASE_PERSONA}

CONTEXTO - VENDAS:
Você está ajudando clientes a comprar produtos da {tenant.name}.

COMPORTAMENTO:
- Seja solícita ao apresentar produtos
- Forneça o link de checkout de forma clara e direta
- Se houver erro no link, informe e ofereça nova tentativa
- Se não tiver link, pergunte qual produto o cliente deseja

EXEMPLOS DE RESPOSTAS:
"Encontrei o produto que você procurava. Deseja que eu gere o link de pagamento?"
"Pronto, aqui está o link para finalizar sua compra: [link]"
"Houve um problema com este link. Vou gerar outro para você, um momento."
"""


def build_support_prompt(tenant: TenantConfig) -> str:
    """Build system prompt for Support agent."""
    return f"""{BASE_PERSONA}

CONTEXTO - SUPORTE:
Você está dando suporte pós-venda para clientes da {tenant.name}.

COMPORTAMENTO:
- Demonstre compreensão quando há problemas com pedidos
- Forneça informações de rastreio de forma clara
- Se houver atraso, explique a situação e informe as providências
- Pergunte se pode ajudar em mais alguma coisa

EXEMPLOS DE RESPOSTAS:
"Entendo sua preocupação. Vou verificar o status do seu pedido."
"Localizei seu pedido. Ele está em trânsito, aqui está o rastreio: [link]"
"Realmente houve um atraso. Já abri um chamado junto à transportadora para acompanhamento."
"""


def build_store_qa_prompt(tenant: TenantConfig) -> str:
    """Build system prompt for Store Q&A agent."""
    return f"""{BASE_PERSONA}

CONTEXTO - DÚVIDAS DA LOJA:
Você está respondendo dúvidas sobre políticas e informações da {tenant.name}.

COMPORTAMENTO:
- Responda dúvidas sobre frete, pagamento e trocas de forma clara e objetiva
- Use as informações da base de conhecimento
- Se não tiver a informação, informe que vai verificar com a equipe
- Ofereça informações adicionais quando relevante

EXEMPLOS DE RESPOSTAS:
"O prazo de entrega é de 3 a 7 dias úteis, dependendo da sua região."
"Para trocas, você tem 30 dias. Enviaremos as instruções por email."
"Aceitamos cartão de crédito, PIX e boleto bancário."
"""


# =============================================================================
# RESPONSE GENERATION
# =============================================================================


def _build_context_prompt(
    state: ConversationState,
    tenant: TenantConfig,
    knowledge_context: str,
) -> str:
    """Build the context/user prompt with all relevant state info."""
    lines = []
    
    # Conversation history for context (memory)
    if state.conversation_history:
        lines.append("[Histórico da Conversa]")
        for entry in state.conversation_history[-6:]:  # Last 6 messages
            role = "Cliente" if entry["role"] == "user" else "Você"
            lines.append(f"{role}: {entry['message']}")
        lines.append("")
    
    # Original complaint for persistent context
    if state.original_complaint:
        lines.append(f"[Problema Original do Cliente]")
        lines.append(f"{state.original_complaint}")
        lines.append("")
    
    lines.append("[Mensagem Atual do Cliente]")
    lines.append(f"{state.last_user_message or '(sem mensagem)'}")
    lines.append("")
    lines.append("[Contexto]")
    lines.append(f"- Intenção detectada: {state.intent}")
    lines.append(f"- Nível de frustração: {state.frustration_level}/5")
    
    # Action outcome - CRITICAL for Respond alignment per AGENT.md
    if state.last_action:
        lines.append(f"- Última ação executada: {state.last_action}")
        lines.append(f"- Resultado da ação: {'SUCESSO' if state.last_action_success else 'FALHA'}")
    
    # Sales context
    if state.selected_product_id:
        title = state.metadata.get("product_title", "produto selecionado")
        lines.append(f"- Produto: {title}")
    
    checkout_link = state.metadata.get("checkout_link")
    if checkout_link:
        lines.append(f"- Link de checkout disponível: {checkout_link}")
    
    # Support context
    if state.order_id:
        lines.append(f"- Número do pedido: {state.order_id}")
    
    if state.tracking_url:
        lines.append(f"- Link de rastreio: {state.tracking_url}")
    
    order_status = state.metadata.get("order_status")
    if order_status:
        lines.append(f"- Status: {order_status}")
    
    if state.ticket_opened:
        lines.append("- Um chamado foi aberto para acompanhamento")
    
    # Store Q&A context
    faq_answer = state.metadata.get("faq_answer")
    if faq_answer:
        lines.append(f"- Resposta da FAQ: {faq_answer}")
    
    # Knowledge base context
    if knowledge_context:
        lines.append("")
        lines.append(knowledge_context)
    
    # Final instruction
    lines.append("")
    lines.append("[Instruções]")
    lines.append("Gere uma resposta natural e humanizada para o cliente.")
    lines.append("Lembre-se: máximo 3 frases, sem markdown.")
    
    # CRITICAL: Grounding for Support domain per AGENT.md contract
    # Respond cannot invent data - must be grounded in state
    if state.domain == "support" and not state.order_id and not state.customer_email:
        lines.append("")
        lines.append("ATENÇÃO: Faltam dados do pedido.")
        lines.append("- NÃO mencione prazos, SLA ou status específicos (ex: '3 a 7 dias úteis')")
        lines.append("- NÃO finja que vai verificar algo - você não tem os dados")
        lines.append("- Apenas peça o número do pedido ou email para prosseguir")
        lines.append("- Use: 'Para verificar seu pedido, preciso do número do pedido ou seu email.'")
    
    # CRITICAL: Action-Respond alignment per AGENT.md contract
    if state.last_action and state.last_action_success is False:
        lines.append("")
        lines.append("ATENÇÃO: A última ação FALHOU.")
        lines.append("- NÃO diga que 'vou verificar' ou 'encontrei' se a ação falhou")
        lines.append("- Informe que não foi possível localizar com os dados fornecidos")
        lines.append("- Peça uma informação alternativa (email ou outro número de pedido)")
    
    if checkout_link:
        lines.append(f"IMPORTANTE: Inclua este link na resposta: {checkout_link}")
    
    if state.tracking_url:
        lines.append(f"IMPORTANTE: Inclua este link de rastreio: {state.tracking_url}")
    
    return "\n".join(lines)


def generate_humanized_response(
    state: ConversationState,
    tenant: TenantConfig,
    domain: str,
    categories: list[str] | None = None,
) -> str:
    """Generate a humanized LLM response.
    
    Args:
        state: Current conversation state
        tenant: Tenant configuration
        domain: Current domain (sales, support, store_qa)
        categories: Optional knowledge base categories to fetch
    
    Returns:
        Generated humanized response
    
    Raises:
        Exception: If LLM call fails - no fallback responses
    """
    # Get knowledge context
    knowledge_context = get_knowledge_context(tenant.tenant_id, categories)
    
    # Select system prompt based on domain
    if domain == "sales":
        system_prompt = build_sales_prompt(tenant)
    elif domain == "support":
        system_prompt = build_support_prompt(tenant)
    else:
        system_prompt = build_store_qa_prompt(tenant)
    
    # Build context prompt
    context_prompt = _build_context_prompt(state, tenant, knowledge_context)
    
    # Call LLM - NO fallback, must succeed
    model = get_model_name()
    if os.getenv("DEBUG"):
        print(f"[LLM] Using model: {model}")
    
    llm = ChatOpenAI(model=model, temperature=0.7)
    result = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=context_prompt),
    ])
    
    response = (result.content or "").strip()
    
    if not response:
        raise ValueError("LLM returned empty response")
    
    # Ensure important links are included
    checkout_link = state.metadata.get("checkout_link")
    if checkout_link and checkout_link not in response:
        response = f"{response}\n\n{checkout_link}"
    
    tracking_url = state.tracking_url
    if tracking_url and tracking_url not in response:
        response = f"{response}\n\n{tracking_url}"
    
    return response

