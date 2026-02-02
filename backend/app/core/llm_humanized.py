# Modified: merged improved prompts with BRAND_VOICE_MAP and Regras de Ouro.
"""Humanized LLM response generation for all agents.

Uses OpenAI to generate natural, human-like responses as if from a real
customer service representative.

MERGED: Best of both worlds - RAG + clear brand voice guidelines + golden rules.
"""

import os
import re

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
# BRAND VOICE DEFINITIONS (from user's improved prompt)
# =============================================================================

BRAND_VOICE_MAP = {
    # 1. PROFISSIONAL (Padrão)
    "profissional": """
TOM: Profissional, Corporativo e Seguro.
OBJETIVO: Transmitir confiança, competência e seriedade.

REGRAS:
- Use norma culta do português (gramática impecável).
- NUNCA use gírias, abreviações ou emojis (🚫 emojis).
- Seja educada, mas mantenha distanciamento profissional.
- Estrutura clara: Sujeito + Verbo + Predicado.
- Tratamento: Use sempre "o senhor" / "a senhora" se houver contexto, ou impessoal "você" culto.

FRASES TÍPICAS:
✓ "Certamente. Irei verificar essa informação para o senhor."
✓ "Agradecemos o seu contato. Como podemos auxiliar?"
✓ "O pagamento foi confirmado. O pedido será despachado em breve."

O QUE EVITAR:
✗ "Opa, beleza?"
✗ "Vou dar uma olhada pra vc."
✗ "Confia na gente! 😉"
    """,

    # 2. SIMPÁTICO
    "simpático": """
TOM: Acolhedor, Empático e Caloroso.
OBJETIVO: Encantar o cliente e criar conexão emocional.

REGRAS:
- Use emojis para transmitir emoção (😊, ✨, 👋) - máx 2 por mensagem.
- Seja positiva e demonstre interesse genuíno.
- Use pontos de exclamação para demonstrar entusiasmo!
- Linguagem acessível, mas correta.
- Reconheça sentimentos: "Entendo perfeitamente", "Que ótimo!", "Sinto muito por isso".

FRASES TÍPICAS:
✓ "Olá! Que alegria ter você por aqui! 😊"
✓ "Fique tranquilo, vou resolver isso agora mesmo para você ✨"
✓ "Essa escolha é maravilhosa! Tenho certeza que vai amar."

O QUE EVITAR:
✗ Respostas secas ou monossilábicas.
✗ Ironia ou frieza.
✗ "Não sei." (Use: "Vou descobrir rapidinho para você!")
    """,

    # 3. CONVERSACIONAL
    "conversacional": """
TOM: Casual, Fluido e Próximo (Estilo WhatsApp).
OBJETIVO: Parecer uma conversa natural com um amigo ou conhecido.

REGRAS:
- Frases curtas e dinâmicas (como num chat real).
- Pode usar abreviações comuns ("vc", "tbm", "pra").
- Tom leve e descontraído.
- Emojis são bem-vindos para dar o tom da conversa 😎
- Evite "textões" (blocos grandes de texto). Quebre em ideias simples.

FRASES TÍPICAS:
✓ "Opa, tudo certo?"
✓ "Vi aqui que seu pedido já saiu, tá a caminho 🚚"
✓ "Ah, esse modelo é top. Todo mundo gosta."

O QUE EVITAR:
✗ Linguagem robótica ou muito formal ("Prezado cliente").
✗ Textos muito longos e complexos.
    """,

    # 4. DIRETO
    "direto": """
TOM: Objetivo, Conciso e Focado em Dados.
OBJETIVO: Economizar tempo do cliente e entregar informação pura.

REGRAS:
- NUNCA use saudações longas ("Olá, espero que esteja bem..."). Corte isso.
- Responda EXATAMENTE o que foi perguntado. Nada mais.
- Sem emojis, sem gírias, sem sentimentos.
- Foco em: Preço, Prazo, Status, Link.
- Se for erro: Diga o erro e a solução de forma cirúrgica.

FRASES TÍPICAS:
✓ "Preço: R$ 150,00."
✓ "Status: Entregue."
✓ "Link: [link]"
✓ "Não temos estoque desse item."

O QUE EVITAR:
✗ "Gostaria de informar que..."
✗ "Por favor, sinta-se à vontade para..."
✗ Qualquer palavra que não agregue informação útil.
    """,
}

# English Aliases for Frontend/Code Compatibility
# All map to the Portuguese definitions above.
BRAND_VOICE_ALIASES = {
    # Profissional aliases
    "professional": "profissional",
    "formal": "profissional",
    "curto_humano": "profissional", # Padrão para legacy/testes conforme solicitado
    "default": "profissional",

    # Simpático aliases
    "friendly": "simpático",
    "simpatico": "simpático", # Handle missing accent
    "warm": "simpático",

    # Conversacional aliases
    "conversational": "conversacional",
    "casual": "conversacional",
    "descontraido": "conversacional",

    # Direto aliases
    "direct": "direto",
    "tecnico": "direto",
    "objective": "direto",
}


# =============================================================================
# GOLDEN RULES (REGRAS DE OURO) - from user's improved prompt
# =============================================================================

GOLDEN_RULES = """
## REGRAS DE OURO (NUNCA VIOLAR)

1. **FRUSTRAÇÃO**: Se frustration_level >= 2, RECONHEÇA a frustração ANTES de qualquer coisa
   - Exemplo: "Entendo a frustração, vamos resolver isso..."

2. **AÇÃO FALHOU**: Se last_action_success = False, explique o que deu errado e ofereça alternativa
   - Exemplo: "O link não funcionou, mas posso te ajudar de outra forma..."

3. **NUNCA INVENTE**: Só use informações que estão no estado/contexto
   - Se não sabe o prazo → NÃO diga "chega em 3 dias"
   - Se não sabe o preço → NÃO invente valores
   - Se não tem tracking → NÃO invente URLs

4. **USE OS FATOS**: Se o estado tem dados, USE-OS
   - Se tem order_id → use ele
   - Se tem email → use ele
   - Se tem nome → use ele

5. **SEJA DIRETO**: Uma mensagem = uma ação clara
   - Máximo 3-4 linhas no WhatsApp
   - Não enrole, vá direto ao ponto

6. **NUNCA PEÇA O QUE JÁ TEM**:
   - Se selected_products existe → não pergunte "qual produto?"
   - Se tem order_id → não peça de novo
   - Se tem variante selecionada → não pergunte cor/tamanho
"""


# =============================================================================
# KNOWLEDGE BASE CONTEXT (kept from original - RAG support)
# =============================================================================


def _extract_metadata_content(metadata: dict | list | str | None) -> str:
    """Extract readable content from metadata field."""
    import json
    
    if not metadata:
        return ""
    
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, (dict, list)):
                return _extract_metadata_content(parsed)
        except json.JSONDecodeError:
            return metadata
    
    if isinstance(metadata, list):
        return " | ".join(str(item) for item in metadata if item)
    
    if isinstance(metadata, dict):
        parts = []
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
        if not parts:
            parts = [str(v) for k, v in metadata.items() if k not in ("keywords", "source") and v]
        return " ".join(parts)
    
    return str(metadata)


def get_knowledge_context(
    tenant_id: str, 
    categories: list[str] | None = None,
    user_message: str | None = None,
) -> str:
    """Fetch relevant knowledge base entries for RAG context."""
    from app.core.database import search_knowledge_base_semantic
    
    try:
        tenant_uuid = resolve_tenant_uuid(tenant_id)
        
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
        if os.getenv("DEBUG"):
            print(f"[RAG Error] {e}")
        return "[Manual da Loja]\nErro ao buscar informações. Diga que vai verificar com a equipe."


# =============================================================================
# SYSTEM PROMPTS (merged: structure from original + clarity from user's prompt)
# =============================================================================


def _get_brand_voice_guidelines(tenant: TenantConfig) -> str:
    """Get brand voice guidelines from map or use tenant's custom voice."""
    voice_key = (tenant.brand_voice or "profissional").lower().strip()
    
    # 1. Check if it's a direct key
    if voice_key in BRAND_VOICE_MAP:
        return BRAND_VOICE_MAP[voice_key]
        
    # 2. Check aliases
    if voice_key in BRAND_VOICE_ALIASES:
        real_key = BRAND_VOICE_ALIASES[voice_key]
        return BRAND_VOICE_MAP[real_key]
    
    # 3. Fallback: If unknown, default to Profissional (per user request)
    # Unless it looks like a custom prompt (long text)
    if len(voice_key) > 50:
        # Custom brand voice from tenant config (rare case)
        return f"""
TOM: Personalizado
REGRAS: {voice_key}
        """
    
    # Default fallback
    return BRAND_VOICE_MAP["profissional"]


def build_sales_prompt(tenant: TenantConfig) -> str:
    """Build system prompt for Sales agent."""
    brand_voice = _get_brand_voice_guidelines(tenant)
    
    return f"""Você é a assistente de vendas da {tenant.name}.

## BRAND VOICE
{brand_voice}

{GOLDEN_RULES}

## CONTEXTO - VENDAS
Você está ajudando clientes a comprar produtos da {tenant.name}.

## COMPORTAMENTO
- Seja solícita ao apresentar produtos
- Forneça o link de checkout de forma clara
- Se houver erro no link, informe e ofereça nova tentativa
- Se não tiver link, pergunte qual produto o cliente deseja

## GROUNDING RULES (DADOS CRÍTICOS)
- Se selected_products existe → liste EXATAMENTE os produtos fornecidos
- Use os TÍTULOS e PREÇOS exatos dos dados
- Numere os produtos: 1, 2, 3...
- NUNCA invente produtos ou preços
- Se available_variants existe → liste EXATAMENTE as variantes com títulos e preços
- Se checkout_link existe → inclua a URL EXATA no FINAL da mensagem
- Se last_action_success = False → reconheça o erro com empatia
- NUNCA invente URLs, IDs ou valores monetários

## EXEMPLOS
"Encontrei o produto que você procurava! Quer que eu gere o link?"
"Pronto, aqui está o link: [link]"
"Ops, esse link deu problema. Vou gerar outro, um momento."

## REGRA ESPECIAL PARA LINKS
Se last_action = "action_generate_link" e last_action_success = True:
- O link JÁ foi gerado e está sendo enviado junto com sua mensagem
- NÃO pergunte "quer que eu gere o link?"
- APENAS confirme de forma natural: "Aqui está!" ou "Pronto! 😊"
"""


def build_support_prompt(tenant: TenantConfig) -> str:
    """Build system prompt for Support agent."""
    brand_voice = _get_brand_voice_guidelines(tenant)
    
    return f"""Você é a assistente de suporte da {tenant.name}.

## BRAND VOICE
{brand_voice}

{GOLDEN_RULES}

## CONTEXTO - SUPORTE
Você está dando suporte pós-venda para clientes da {tenant.name}.

## COMPORTAMENTO
- Demonstre compreensão quando há problemas com pedidos
- Forneça informações de rastreio de forma clara
- Se houver atraso, explique a situação
- Pergunte se pode ajudar em mais alguma coisa

## GROUNDING RULES (DADOS CRÍTICOS)
- Se tracking_url existe → inclua a URL EXATA no FINAL
- Se order_id existe → mantenha EXATO (nunca mude IDs)
- Se last_action_success = False → reconheça o erro com empatia
- NUNCA invente status, prazos, URLs ou valores

## QUANDO NÃO TEM DADOS DO PEDIDO
- NÃO mencione prazos ou SLA específicos
- NÃO finja que vai verificar algo
- APENAS peça o número do pedido ou email

## EXEMPLOS
"Entendo sua preocupação. Vou verificar o status do seu pedido."
"Localizei! Está em trânsito, aqui o rastreio: [link]"
"Houve um atraso. Já abri um chamado junto à transportadora."
"""


def build_store_qa_prompt(tenant: TenantConfig) -> str:
    """Build system prompt for Store Q&A agent with strict RAG grounding."""
    brand_voice = _get_brand_voice_guidelines(tenant)
    
    return f"""Você é a assistente de atendimento da {tenant.name}.

## BRAND VOICE
{brand_voice}

{GOLDEN_RULES}

## CONTEXTO - DÚVIDAS DA LOJA
Você está respondendo dúvidas sobre políticas e informações da {tenant.name}.

## REGRAS ABSOLUTAS DE GROUNDING (NUNCA VIOLAR)

1. **NUNCA INVENTE INFORMAÇÕES**
   - Você SÓ pode usar informações do [Manual da Loja] fornecido
   - Se a informação NÃO está no manual: "Não tenho essa informação no momento. Posso verificar com a equipe."
   - NUNCA invente prazos, preços, políticas ou qualquer dado

2. **FRASES PROIBIDAS** (só use se estiver no manual):
   - "O prazo é de X dias"
   - "O frete custa R$X"
   - "Aceitamos..."
   - "A política é..."

3. **QUANDO NÃO SOUBER**:
   - "Não tenho essa informação no momento. Posso verificar com a equipe."
   - "Para informações mais detalhadas, nossa equipe pode ajudar melhor."

## COMPORTAMENTO
- Seja clara e objetiva
- Se o manual tiver a resposta, use exatamente as informações dele
- Se não tiver, admita e ofereça verificar
"""


# =============================================================================
# CONTEXT BUILDING (improved with additional_context from user's prompt)
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


def _build_additional_context(state: ConversationState) -> str:
    """Build additional context based on last action (from user's prompt)."""
    lines = []
    
    if state.last_action == "action_generate_link" and state.last_action_success:
        lines.append("✓ Você ACABOU de gerar um link de checkout. Envie-o de forma natural.")
        lines.append("CRÍTICO: O link JÁ FOI GERADO. NÃO pergunte se quer gerar. APENAS envie.")
        checkout_link = state.metadata.get("checkout_link")
        if checkout_link:
            lines.append(f"  Link: {checkout_link}")
    
    elif state.last_action == "action_search_products" and state.last_action_success:
        count = len(state.selected_products or [])
        lines.append(f"✓ Você ACABOU de buscar produtos. Encontrou {count} produtos.")
        lines.append("  Liste os produtos encontrados para o cliente escolher.")
    
    elif state.last_action == "action_select_variant" and state.last_action_success:
        lines.append("✓ Cliente ACABOU de escolher uma variante.")
        lines.append("  Confirme a escolha e ofereça gerar o link.")
    
    elif state.last_action == "action_resolve_product" and state.last_action_success:
        lines.append("✓ Você ACABOU de resolver um link de produto.")
        product_title = state.metadata.get("product_title")
        if product_title:
            lines.append(f"  Produto: {product_title}")
    
    elif state.last_action_success is False:
        lines.append("⚠️ A ÚLTIMA AÇÃO FALHOU.")
        lines.append("  Reconheça o problema e ofereça uma alternativa.")
        error = _collect_error_details(state)
        if error:
            lines.append(f"  Erro: {error}")
    
    return "\n".join(lines) if lines else ""


def _build_context_prompt(
    state: ConversationState,
    tenant: TenantConfig,
    knowledge_context: str,
) -> str:
    """Build the context/user prompt with all relevant state info."""
    lines = []

    # Conversation history
    if state.conversation_history:
        lines.append("[Histórico da Conversa]")
        for entry in state.conversation_history[-6:]:
            role = "👤 Cliente" if entry["role"] == "user" else "🤖 Você"
            message = entry.get("message", entry.get("content", ""))
            lines.append(f"{role}: {message}")
        lines.append("")

    # Original complaint (persistent context)
    if state.original_complaint:
        lines.append("[Problema Original do Cliente]")
        lines.append(f"{state.original_complaint}")
        lines.append("")

    # Current user message
    lines.append("[Mensagem Atual do Cliente]")
    lines.append(f'"{state.last_user_message or "(sem mensagem)"}"')
    lines.append("")

    # Additional context based on last action (from user's prompt)
    additional = _build_additional_context(state)
    if additional:
        lines.append("[O que Acabou de Acontecer]")
        lines.append(additional)
        lines.append("")

    # Critical data
    current_domain = state.domain or "sales"
    lines.append("[DADOS CRÍTICOS - use EXATAMENTE como fornecidos]")
    
    checkout_link = state.metadata.get("checkout_link")
    tracking_url = state.tracking_url
    lines.append(f"- checkout_link: {checkout_link or '(nenhum)'}")
    lines.append(f"- tracking_url: {tracking_url or '(nenhum)'}")
    lines.append(f"- order_id: {state.order_id or '(nenhum)'}")
    lines.append(f"- variant_id: {state.selected_variant_id or '(nenhum)'}")

    # Product info
    product_title = state.metadata.get("product_title")
    product_price = state.metadata.get("product_price")
    if product_title or product_price:
        price_text = _format_price(product_price)
        if price_text:
            lines.append(f"- product: {product_title or '(none)'} - {price_text}")
        else:
            lines.append(f"- product: {product_title or '(none)'}")
    
    # Product description for answering questions
    product_description = state.metadata.get("product_description")
    if product_description:
        clean_desc = re.sub(r'<[^>]+>', '', product_description).strip()
        if clean_desc:
            lines.append(f"- product_description: {clean_desc[:500]}")
    
    product_tags = state.metadata.get("product_tags")
    if product_tags:
        lines.append(f"- product_tags: {product_tags}")

    # Selected variant
    selected_variant_title = state.metadata.get("selected_variant_title")
    selected_variant_price = state.metadata.get("selected_variant_price")
    if selected_variant_title or selected_variant_price:
        price_text = _format_price(selected_variant_price)
        if price_text:
            lines.append(f"- selected_variant: {selected_variant_title or '(none)'} - {price_text}")
        else:
            lines.append(f"- selected_variant: {selected_variant_title or '(none)'}")

    # Selected products
    if state.selected_products:
        lines.append("- selected_products:")
        for idx, product in enumerate(state.selected_products, start=1):
            title = product.get("title") or "Produto"
            price = _format_price(product.get("price"))
            desc = product.get("description", "")
            if desc:
                desc = re.sub(r'<[^>]+>', '', desc).strip()[:200]
            
            if price:
                lines.append(f"  {idx}. {title} - {price}")
            else:
                lines.append(f"  {idx}. {title}")
            
            if desc:
                lines.append(f"     ({desc})")
    else:
        lines.append("- selected_products: (nenhum)")

    # Available variants
    # Available variants
    if state.available_variants:
        lines.append("- available_variants:")
        lines.append("  (IMPORTANTE: O produto tem variantes. Pergunte qual o cliente prefere)")
        for idx, variant in enumerate(state.available_variants, start=1):
            title = variant.get("title") or "Opção"
            price = _format_price(variant.get("price"))
            available = variant.get("available", True)
            if isinstance(available, str): 
                available = available.lower() == "true"
            status = "✅ Disponível" if available else "❌ Esgotado"
            
            if price:
                lines.append(f"  {idx}. {title} - {price} ({status})")
            else:
                lines.append(f"  {idx}. {title} ({status})")
    else:
        lines.append("- available_variants: (nenhum)")

    lines.append("")
    
    # Contextual data
    lines.append("[DADOS CONTEXTUAIS]")
    lines.append(f"- intent: {state.intent}")
    lines.append(f"- last_action: {state.last_action or '(nenhum)'}")
    lines.append(f"- last_action_success: {state.last_action_success}")
    lines.append(f"- frustration_level: {state.frustration_level}/5")
    lines.append(f"- sentiment: {state.sentiment_level}")

    error_details = _collect_error_details(state)
    if error_details:
        lines.append(f"- errors: {error_details}")

    # Domain-specific data
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

    # FAQ answer if available
    faq_answer = state.metadata.get("faq_answer")
    if faq_answer:
        lines.append(f"- faq_answer: {faq_answer}")

    # Knowledge context (RAG)
    if knowledge_context:
        lines.append("")
        lines.append(knowledge_context)

    # Instructions
    lines.append("")
    lines.append("[INSTRUÇÃO FINAL]")
    lines.append("Gere UMA resposta natural e humanizada (1-4 linhas).")
    lines.append("Sem markdown. Sem aspas. Apenas o texto da mensagem.")

    # Special cases
    if state.domain == "support" and not state.order_id and not state.customer_email:
        lines.append("")
        lines.append("⚠️ ATENÇÃO: Faltam dados do pedido.")
        lines.append("- NÃO mencione prazos ou status específicos")
        lines.append("- NÃO finja que vai verificar algo")
        lines.append("- Apenas peça o número do pedido ou email")
    
    if state.domain == "support" and state.last_action and state.last_action_success is False:
        lines.append("")
        lines.append("⚠️ ATENÇÃO: A última ação FALHOU.")
        lines.append("- Não diga que 'vou verificar' ou 'encontrei'")
        lines.append("- Informe que não foi possível com os dados fornecidos")
        lines.append("- Peça uma informação alternativa")

    return "\n".join(lines)


# =============================================================================
# RESPONSE GENERATION
# =============================================================================


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
    
    # Debug
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
    
    # Call LLM
    model = get_model_name()
    if os.getenv("DEBUG"):
        print(f"[LLM] Using model: {model}")
    
    llm = ChatOpenAI(model=model, temperature=0.7)
    result = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=context_prompt),
    ])
    
    response = (result.content or "").strip()
    
    # Capture token usage
    usage_raw = result.response_metadata.get("token_usage")
    state.metadata["token_usage_agent"] = normalize_token_usage(usage_raw)
    
    if not response:
        raise ValueError("LLM returned empty response")
    
    # Clean response - remove quotes if wrapped
    if response.startswith('"') and response.endswith('"'):
        response = response[1:-1]
    if response.startswith("'") and response.endswith("'"):
        response = response[1:-1]
    
    # Ensure important links are included
    if domain == "sales":
        checkout_link = state.metadata.get("checkout_link")
        if checkout_link and checkout_link not in response:
            response = f"{response}\n\n{checkout_link}"
    elif domain == "support":
        tracking_url = state.tracking_url
        if tracking_url and tracking_url not in response:
            response = f"{response}\n\n{tracking_url}"
    
    return response
