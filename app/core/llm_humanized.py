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


def _extract_metadata_content(metadata: dict | list | str | None) -> str:
    """Extract readable content from metadata field.
    
    metadata can be:
    - JSON string: parse first then extract
    - dict: {"title": "...", "content": "...", "keywords": [...]}
    - list: ["info1", "info2", ...]
    - str: direct text content
    """
    import json
    
    if not metadata:
        return ""
    
    # If it's a JSON string, parse it first
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, (dict, list)):
                return _extract_metadata_content(parsed)  # Recurse with parsed data
        except json.JSONDecodeError:
            return metadata  # Return as-is if not valid JSON
    
    if isinstance(metadata, list):
        return " | ".join(str(item) for item in metadata if item)
    
    if isinstance(metadata, dict):
        parts = []
        # Extract common fields from store manual format
        if "title" in metadata:
            parts.append(f"{metadata['title']}:")
        if "content" in metadata:
            parts.append(str(metadata["content"]))
        if "topic" in metadata:
            parts.append(f"Tópico: {metadata['topic']}")
        if "info" in metadata:
            parts.append(str(metadata["info"]))
        if "text" in metadata:
            parts.append(str(metadata["text"]))
        # If none of the above, dump all non-keyword values
        if not parts:
            parts = [str(v) for k, v in metadata.items() if k not in ("keywords", "source") and v]
        return " ".join(parts)
    
    return str(metadata)


def get_knowledge_context(
    tenant_id: str, 
    categories: list[str] | None = None,
    user_message: str | None = None,
) -> str:
    """Fetch relevant knowledge base entries for RAG context.
    
    Uses semantic search when user_message is provided (better relevance).
    Knowledge is stored in the metadata column as a store manual.
    """
    from app.core.database import search_knowledge_base_semantic
    
    try:
        tenant_uuid = resolve_tenant_uuid(tenant_id)
        
        # Use semantic search if we have the user's message
        if user_message:
            all_results = search_knowledge_base_semantic(
                tenant_uuid, 
                query=user_message, 
                limit=5
            )
        elif categories:
            all_results = []
            for cat in categories:
                results = search_knowledge_base_simple(tenant_uuid, category=cat, limit=3)
                all_results.extend(results)
        else:
            all_results = search_knowledge_base_simple(tenant_uuid, limit=10)
        
        if not all_results:
            return "[Manual da Loja]\nNenhuma informação encontrada na base de dados."
        
        context_lines = ["[Manual da Loja]"]
        context_lines.append("Use APENAS as informações abaixo para responder:")
        context_lines.append("")
        
        for item in all_results:
            category = item.get("category", "geral")
            metadata = item.get("metadata")
            content = _extract_metadata_content(metadata)
            if content:
                context_lines.append(f"[{category.upper()}] {content}")
                context_lines.append("")
        
        return "\n".join(context_lines)
    except Exception as e:
        import os
        if os.getenv("DEBUG"):
            print(f"[RAG Error] {e}")
        return "[Manual da Loja]\nErro ao buscar informações. Diga que vai verificar com a equipe."


# =============================================================================
# HUMANIZED SYSTEM PROMPTS
# =============================================================================


def build_base_persona(tenant: TenantConfig) -> str:
    """Build base persona dynamically using tenant.brand_voice from Supabase.
    
    The brand_voice is a free-form text defined by the client in Supabase.
    Examples:
        - "profissional e direto ao ponto"
        - "simpático e acolhedor, usando emojis moderadamente"
        - "informal e descontraído, como um amigo próximo"
    """
    brand_voice = tenant.brand_voice or "profissional e cordial"
    
    return f"""Você é Ana, assistente virtual de atendimento ao cliente da {tenant.name}.

TOM E ESTILO (definido pelo cliente):
{brand_voice}

REGRAS GERAIS:
- Adapte seu tom exatamente conforme descrito acima
- NUNCA use markdown (sem **, ##, -, etc)
- URLs devem aparecer sozinhas em uma linha
- Máximo 3 frases por resposta
- Seja direta e resolva o problema rapidamente
- Se não souber, diga que vai verificar com a equipe
- Mostra empatia quando o cliente tem problemas"""


def build_sales_prompt(tenant: TenantConfig) -> str:
    """Build system prompt for Sales agent."""
    base = build_base_persona(tenant)
    return f"""{base}

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
    base = build_base_persona(tenant)
    return f"""{base}

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
    """Build system prompt for Store Q&A agent with strict RAG grounding AND security rules."""
    from app.core.security import get_prompt_guard
    
    base = build_base_persona(tenant)
    prompt_guard = get_prompt_guard()
    
    return f"""{prompt_guard}

{base}

CONTEXTO - DÚVIDAS DA LOJA:
Você está respondendo dúvidas sobre políticas e informações da {tenant.name}.

=== REGRAS ABSOLUTAS DE GROUNDING (NUNCA VIOLAR) ===

1. NUNCA INVENTE INFORMAÇÕES
   - Você SÓ pode usar informações que estão no [Manual da Loja] fornecido
   - Se a informação NÃO está no manual, diga: "Não tenho essa informação no momento. Posso verificar com a equipe e retornar."
   - NUNCA invente prazos, preços, políticas ou qualquer dado específico

2. SEMPRE CONFIRME NO MANUAL DA LOJA
   - Antes de responder qualquer dúvida, verifique se a resposta está no manual
   - Se a pergunta do cliente não tem resposta no manual, NÃO INVENTE
   - Use APENAS os dados fornecidos, nunca conhecimento externo

3. FRASES PROIBIDAS (NUNCA USE SE NÃO ESTIVER NO MANUAL):
   - "O prazo é de X dias" (só se estiver no manual)
   - "O frete custa R$X" (só se estiver no manual)
   - "Aceitamos..." (só liste o que está no manual)
   - "A política é..." (só se estiver no manual)

4. QUANDO NÃO SOUBER:
   - Diga: "Não tenho essa informação no momento. Posso verificar com a equipe e retornar."
   - Ou: "Para informações mais detalhadas sobre isso, nossa equipe pode ajudar melhor."

5. COPIE NÚMEROS E PRAZOS EXATAMENTE:
   Copie exatamente números, valores e prazos do Manual da Loja.
   NÃO converta dias↔horas, NÃO arredonde, NÃO resuma prazos.

=== FIM DAS REGRAS ===

COMPORTAMENTO:
- Seja clara e objetiva
- Se o manual tiver a resposta, use exatamente as informações dele
- Se não tiver, admita e ofereça verificar
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
        # Tri-state: True=SUCESSO, False=FALHA, None=N/A (nenhuma action executada)
        if state.last_action_success is True:
            action_result = "SUCESSO"
        elif state.last_action_success is False:
            action_result = "FALHA"
        else:
            action_result = "N/A"
        lines.append(f"- Resultado da ação: {action_result}")
    
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
    # Only applies to support domain which has real actions (lookup order, etc.)
    if state.domain == "support" and state.last_action and state.last_action_success is False:
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
    # Get knowledge context - use semantic search for store_qa
    user_msg = state.last_user_message if domain == "store_qa" else None
    knowledge_context = get_knowledge_context(
        tenant.tenant_id, 
        categories,
        user_message=user_msg
    )
    
    # Debug: show knowledge context
    if os.getenv("DEBUG"):
        print(f"[RAG] Domain: {domain}")
        print(f"[RAG] Categories: {categories}")
        print(f"[RAG] User message for search: {user_msg}")
        print(f"[RAG] Knowledge context (first 300 chars): {knowledge_context[:300]}...")
    
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

