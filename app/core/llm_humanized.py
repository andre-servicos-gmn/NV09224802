# Modified: add context filtering to prevent cross-domain leakage.
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
from app.core.llm_utils import normalize_token_usage

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


def _build_brand_voice_section(tenant: TenantConfig) -> str:
    """Build optional brand voice section for system prompts."""
    voice = (tenant.brand_voice or "").strip()
    if not voice:
        return ""
    return (
        "\nTone: {voice}\n"
        "Examples:\n"
        "- 'curto_humano': 'Achei 3 colares! Qual voce prefere?'\n"
        "- 'descontraido': 'Opa! Separei uns colares massa aqui...'\n"
        "- 'formal': 'Encontrei tres opcoes de colares para voce...'\n"
    ).format(voice=voice)


def build_sales_prompt(tenant: TenantConfig) -> str:
    """Build system prompt for Sales agent."""
    return f"""{BASE_PERSONA}{_build_brand_voice_section(tenant)}

CONTEXTO - VENDAS:
Você está ajudando clientes a comprar produtos da {tenant.name}.

COMPORTAMENTO:
- Seja solícita ao apresentar produtos
- Forneça o link de checkout de forma clara e direta
- Se houver erro no link, informe e ofereça nova tentativa
- Se não tiver link, pergunte qual produto o cliente deseja

GROUNDING RULES:
- If selected_products list exists, YOU MUST list EXACTLY the products provided.
- Use the EXACT titles and prices from the data.
- Number them 1, 2, 3...
- Never invent products.
- Never change prices.
- If available_variants list exists, list EXACTLY the variants provided with titles and prices.
- If checkout_link exists, include the EXACT URL provided at the END of your message.
- If last_action_success is False, acknowledge the error with empathy, use the error message in metadata, adapt tone to brand_voice, and suggest next steps.
- Never invent URLs, IDs, or monetary values.

EXEMPLOS DE RESPOSTAS:
"Encontrei o produto que você procurava. Deseja que eu gere o link de pagamento?"
"Pronto, aqui está o link para finalizar sua compra: [link]"
"Houve um problema com este link. Vou gerar outro para você, um momento."
"""


def build_support_prompt(tenant: TenantConfig) -> str:
    """Build system prompt for Support agent."""
    return f"""{BASE_PERSONA}{_build_brand_voice_section(tenant)}

CONTEXTO - SUPORTE:
Você está dando suporte pós-venda para clientes da {tenant.name}.

COMPORTAMENTO:
- Demonstre compreensão quando há problemas com pedidos
- Forneça informações de rastreio de forma clara
- Se houver atraso, explique a situação e informe as providências
- Pergunte se pode ajudar em mais alguma coisa

GROUNDING RULES:
- If tracking_url exists, include the EXACT URL provided at the END of your message.
- If order_id exists, keep it EXACT (never change IDs).
- If last_action_success is False, acknowledge the error with empathy, use the error message in metadata, adapt tone to brand_voice, and suggest next steps.
- Never invent statuses, SLAs, URLs, IDs, or monetary values.

EXEMPLOS DE RESPOSTAS:
"Entendo sua preocupação. Vou verificar o status do seu pedido."
"Localizei seu pedido. Ele está em trânsito, aqui está o rastreio: [link]"
"Realmente houve um atraso. Já abri um chamado junto à transportadora para acompanhamento."
"""


def build_store_qa_prompt(tenant: TenantConfig) -> str:
    """Build system prompt for Store Q&A agent."""
    return f"""{BASE_PERSONA}{_build_brand_voice_section(tenant)}

CONTEXTO - DÚVIDAS DA LOJA:
Você está respondendo dúvidas sobre políticas e informações da {tenant.name}.

COMPORTAMENTO:
- Responda dúvidas sobre frete, pagamento e trocas de forma clara e objetiva
- Use as informações da base de conhecimento
- Se não tiver a informação, informe que vai verificar com a equipe
- Ofereça informações adicionais quando relevante

EXEMPLOS DE RESPOSTAS:
"O prazo de entrega varia conforme a região e será informado no checkout."
"Para trocas, você tem 30 dias. Enviaremos as instruções por email."
"Aceitamos cartão de crédito, PIX e boleto bancário."

REGRA IMPORTANTE:
- NUNCA invente prazos ou SLAs específicos (ex: '3 a 7 dias úteis')
- Use apenas informações da base de conhecimento ou diga que vai verificar
"""


# =============================================================================
# RESPONSE GENERATION
# =============================================================================


def _format_price(value: str | None) -> str:
    if not value:
        return ""
    return f"R$ {value}"


def _collect_error_details(state: ConversationState) -> str:
    errors = []
    for key, value in state.metadata.items():
        if key.endswith("_error") and value:
            errors.append(f"{key}={value}")
    out_of_stock_message = state.metadata.get("out_of_stock_message")
    if out_of_stock_message:
        errors.append(f"out_of_stock_message={out_of_stock_message}")
    if state.metadata.get("out_of_stock"):
        errors.append("out_of_stock=True")
    return "; ".join(errors)


def _build_context_prompt(
    state: ConversationState,
    tenant: TenantConfig,
    knowledge_context: str,
) -> str:
    """Build the context/user prompt with all relevant state info."""
    lines = []

    if state.conversation_history:
        lines.append("[Historico da Conversa]")
        for entry in state.conversation_history[-6:]:
            role = "Cliente" if entry["role"] == "user" else "Voce"
            lines.append(f"{role}: {entry['message']}")
        lines.append("")

    if state.original_complaint:
        lines.append("[Problema Original do Cliente]")
        lines.append(f"{state.original_complaint}")
        lines.append("")

    lines.append("[Mensagem Atual do Cliente]")
    lines.append(f"{state.last_user_message or '(sem mensagem)'}")
    lines.append("")

    current_domain = state.domain or "sales"
    lines.append("CRITICAL DATA (use EXACTLY as provided):")
    checkout_link = state.metadata.get("checkout_link")
    tracking_url = state.tracking_url
    lines.append(f"- checkout_link: {checkout_link or '(none)'}")
    lines.append(f"- tracking_url: {tracking_url or '(none)'}")
    lines.append(f"- order_id: {state.order_id or '(none)'}")
    lines.append(f"- variant_id: {state.selected_variant_id or '(none)'}")

    product_title = state.metadata.get("product_title")
    product_price = state.metadata.get("product_price")
    if product_title or product_price:
        price_text = _format_price(product_price)
        if price_text:
            lines.append(f"- product: {product_title or '(none)'} - {price_text}")
        else:
            lines.append(f"- product: {product_title or '(none)'}")

    selected_variant_title = state.metadata.get("selected_variant_title")
    selected_variant_price = state.metadata.get("selected_variant_price")
    if selected_variant_title or selected_variant_price:
        price_text = _format_price(selected_variant_price)
        if price_text:
            lines.append(f"- selected_variant: {selected_variant_title or '(none)'} - {price_text}")
        else:
            lines.append(f"- selected_variant: {selected_variant_title or '(none)'}")

    if state.selected_products:
        lines.append("- selected_products:")
        for idx, product in enumerate(state.selected_products, start=1):
            title = product.get("title") or "Produto"
            price = _format_price(product.get("price"))
            if price:
                lines.append(f"  {idx}. {title} - {price}")
            else:
                lines.append(f"  {idx}. {title}")
    else:
        lines.append("- selected_products: (none)")

    if state.available_variants:
        lines.append("- available_variants:")
        for idx, variant in enumerate(state.available_variants, start=1):
            title = variant.get("title") or "Opcao"
            price = _format_price(variant.get("price"))
            if price:
                lines.append(f"  {idx}. {title} - {price}")
            else:
                lines.append(f"  {idx}. {title}")
    else:
        lines.append("- available_variants: (none)")

    lines.append("")
    lines.append("CONTEXTUAL DATA (adapt with brand_voice):")
    lines.append(f"- intent: {state.intent}")
    lines.append(f"- last_action: {state.last_action or '(none)'}")
    lines.append(f"- last_action_success: {state.last_action_success}")
    lines.append(f"- frustration_level: {state.frustration_level}/5")

    error_details = _collect_error_details(state)
    if error_details:
        lines.append(f"- last_action_error: {error_details}")

    if current_domain == "sales":
        search_query = state.search_query or state.metadata.get("search_query")
        if search_query:
            lines.append(f"- search_query: {search_query}")
        if state.metadata.get("out_of_stock"):
            lines.append("- out_of_stock: True")
    elif current_domain == "support":
        if state.customer_email:
            lines.append(f"- customer_email: {state.customer_email}")
        ticket_id = state.metadata.get("ticket_id")
        if ticket_id:
            lines.append(f"- ticket_id: {ticket_id}")
        order_status = state.metadata.get("order_status")
        if order_status:
            lines.append(f"- order_status: {order_status}")
        fulfillment_status = state.metadata.get("fulfillment_status")
        if fulfillment_status:
            lines.append(f"- fulfillment_status: {fulfillment_status}")
        tracking_number = state.metadata.get("tracking_number")
        if tracking_number:
            lines.append(f"- tracking_number: {tracking_number}")
        if state.ticket_opened:
            lines.append("- ticket_opened: True")

    faq_answer = state.metadata.get("faq_answer")
    if faq_answer:
        lines.append(f"- faq_answer: {faq_answer}")

    if knowledge_context:
        lines.append("")
        lines.append(knowledge_context)

    lines.append("")
    lines.append("[Instrucoes]")
    lines.append("Gere uma resposta natural e humanizada para o cliente.")
    lines.append("Lembre-se: maximo 3 frases, sem markdown.")

    if state.domain == "support" and not state.order_id and not state.customer_email:
        lines.append("")
        lines.append("ATENCAO: Faltam dados do pedido.")
        lines.append("- Nao mencione prazos, SLA ou status especificos (ex: '3 a 7 dias uteis')")
        lines.append("- Nao finja que vai verificar algo - voce nao tem os dados")
        lines.append("- Apenas peca o numero do pedido ou email para prosseguir")
        lines.append("- Use: 'Para verificar seu pedido, preciso do numero do pedido ou seu email.'")

    if state.last_action and state.last_action_success is False:
        lines.append("")
        lines.append("ATENCAO: A ultima acao FALHOU.")
        lines.append("- Nao diga que 'vou verificar' ou 'encontrei' se a acao falhou")
        lines.append("- Informe que nao foi possivel concluir com os dados fornecidos")
        lines.append("- Peca uma informacao alternativa (email ou outro numero de pedido)")

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
    
    # Capture token usage in state metadata (without changing function signature)
    usage_raw = result.response_metadata.get("token_usage")
    state.metadata["token_usage_agent"] = normalize_token_usage(usage_raw)
    
    if not response:
        raise ValueError("LLM returned empty response")
    
    # Ensure important links are included by domain
    if domain == "sales":
        checkout_link = state.metadata.get("checkout_link")
        if checkout_link and checkout_link not in response:
            response = f"{response}\n\n{checkout_link}"
    elif domain == "support":
        tracking_url = state.tracking_url
        if tracking_url and tracking_url not in response:
            response = f"{response}\n\n{tracking_url}"
    
    return response


