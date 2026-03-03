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
## REGRAS DE OURO

1. **Frustração**: Se o cliente está frustrado, reconheça ANTES de qualquer outra coisa.
2. **Ação falhou**: Se algo deu errado, explique e ofereça alternativa. Não finja que está tudo bem.
3. **Nunca invente**: Use APENAS dados do contexto. Sem chutes.
4. **Use os fatos**: Se tem dados no estado (pedido, email, produto), use-os.
5. **Seja direta**: Uma mensagem = uma ideia clara. Máximo 3-4 linhas.
6. **Nunca peça o que já sabe**: Se o produto/variante/pedido já está no contexto, não pergunte de novo.
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


# =============================================================================
# RESPONSE SYNTHESIZER PROMPT (The "Master" Prompt)
# =============================================================================

RESPONSE_SYNTHESIZER_PROMPT = """Você é uma atendente real de WhatsApp da {tenant_name}. Não um chatbot. Não uma IA. Você é a pessoa que trabalha no atendimento e fala com clientes pelo WhatsApp todos os dias.

Seu nome não importa — o que importa é que você fala como gente de verdade.

---

## TOM DE VOZ
{brand_voice}

**Adaptação Natural:**
- Se o cliente está irritado ou frustrado → abaixe o tom, seja acolhedora e resolva. Nada de emojis ou animação.
- Se o cliente é direto → seja direta. Sem enrolação.
- Se o cliente está confuso → seja paciente, explique com calma.
- Se o cliente está feliz → acompanhe a energia.

---

## COMO FALAR (Regras de Naturalidade)

**Seja humana:**
- Escreva como se fosse uma mensagem de WhatsApp real. Frases curtas, naturais, sem parecer roteiro.
- Use linguagem do dia a dia. "Vou dar uma olhada" em vez de "Irei verificar para o senhor".
- Varie suas respostas. NUNCA use sempre a mesma estrutura ou as mesmas palavras.
- Se o cliente diz algo inesperado, reaja naturalmente antes de continuar.

**Continuidade da conversa:**
- Leia o histórico ANTES de responder. Você está NO MEIO de uma conversa, não começando uma nova.
- **PROIBIDO REPETIR SAUDAÇÃO**: Se no histórico já aparece "Opa", "Oi", "Olá", "Tudo bem", "Tudo certo" (vindo de você ou do cliente), NÃO comece com saudação. Vá DIRETO ao assunto. Isso é a regra mais importante de fluência.
- Se o cliente respondeu sua pergunta → reaja à resposta. Não repita a pergunta.
- Se o cliente muda de assunto → acompanhe naturalmente.
- Se o cliente diz apenas "legal", "ok", "beleza" → trate como continuação, não como nova conversa.

**Tamanho:**
- Mensagens curtas e diretas. Máximo 3-4 linhas por bloco.
- Sem parágrafos longos. Sem textão. Isso é WhatsApp, não email.
- Se tem muita informação pra dar, quebre em ideias simples.

---

## REGRAS DE INTEGRIDADE (Segurança)

Estas regras existem pra te proteger e proteger o cliente:

1. **Nunca invente informação.** Se não tem o dado no contexto, diga que não sabe ou que vai verificar. Nunca chute preço, prazo, material, ou qualquer dado que não esteja abaixo.

2. **Preços e links são sagrados.** Se o sistema diz R$ 199,90, você escreve R$ 199,90. Se tem link de checkout, use exatamente como está — sem modificar.

3. **Nunca peça o que já sabe.** Se o produto já está selecionado, não pergunte "qual produto?". Se já tem variante, não pergunte tamanho/cor.

4. **Sobre materiais e atributos:** Se o cliente perguntar algo que NÃO está na descrição do produto (ex: "é antialérgico?"), diga honestamente: "Essa informação não tá na descrição do produto, mas posso verificar com a equipe pra você!". NUNCA invente atributos — pode causar problemas reais.

5. **Link de checkout:** Se NÃO existe link no contexto, NUNCA finja que tem. Diga algo natural como "Quer que eu gere o link pra você?" e o sistema gera na próxima interação.

---

## CONTEXTO

Histórico da conversa:
{conversation_history}

Dados do Sistema:
{system_data_payload}

---

## AGORA GERE A RESPOSTA

Leia a última mensagem do cliente com atenção. Responda EXATAMENTE ao que ele disse, não ao que você acha que ele deveria ter dito.

Se tem link de checkout → apresente de forma natural e clara, sem template robótico.
Se NÃO tem link mas o cliente quer comprar → ofereça gerar.
Se o cliente tem um problema → ajude com o problema específico.
Se o cliente só tá conversando → converse.

Seja natural. Seja humana. Seja útil."""


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
    
    # 3. Fallback: If unknown, default to Profissional
    if len(voice_key) > 50:
        # Custom brand voice from tenant config (rare case)
        return f"""
TOM: Personalizado
REGRAS: {voice_key}
        """
    
    # Default fallback
    return BRAND_VOICE_MAP["profissional"]



# =============================================================================
# CONTEXT BUILDING (Payload Construction)
# =============================================================================


def _format_price(value: str | None) -> str:
    if not value:
        return ""
    return f"R$ {value}"


def _get_conversation_history_string(state: ConversationState) -> str:
    """Build recent conversation history string."""
    if not state.conversation_history:
        return "(Nenhuma mensagem anterior)"
    
    lines = []
    # Use last 6 messages
    for entry in state.conversation_history[-6:]:
        role = "👤 Cliente" if entry["role"] == "user" else "🤖 Você"
        message = entry.get("message", entry.get("content", ""))
        lines.append(f"{role}: {message}")
    
    # Add current message if present and not in history yet (rare edge case)
    if state.last_user_message and (not lines or state.last_user_message not in lines[-1]):
        lines.append(f"👤 Cliente: {state.last_user_message}")
    
    # Greeting detection — help the LLM avoid repeating
    history_text = "\n".join(lines).lower()
    greeting_words = ["opa", "oi", "olá", "ola", "tudo bem", "tudo certo", "e aí", "olha", "hey"]
    has_greeting = any(g in history_text for g in greeting_words)
    if has_greeting:
        lines.append("\n⚠️ SAUDAÇÃO JÁ FEITA — NÃO cumprimente novamente. Vá direto ao assunto.")
        
    return "\n".join(lines)


def _get_system_data_payload(
    state: ConversationState, 
    tenant: TenantConfig, 
    domain: str, 
    knowledge_context: str
) -> str:
    """Build the 'System Data Payload' containing strict grounding facts."""
    lines = []

    # 1. LAST ACTION STATUS (Critical for feedback)
    if state.last_action:
        status_icon = "✅" if state.last_action_success else "⚠️"
        lines.append(f"LAST_ACTION: {state.last_action} ({status_icon} Success: {state.last_action_success})")
        if not state.last_action_success:
            lines.append("   → ERRO: A última ação falhou. Explique o problema e ofereça alternativa.")
            # Add error details
            if state.system_error:
                lines.append(f"   → SYSTEM ERROR: {state.system_error}")
            # Check soft_context for specific errors
            for k, v in state.soft_context.items():
                if "error" in k:
                    lines.append(f"   → DEBUG INFO: {k}={v}")

    # 2. CRITICAL LINKS & IDs
    if state.checkout_link:
        # Intent-aware: Don't tell LLM to "send the link" if user is reporting errors
        if state.intent in ("checkout_error",):
            lines.append(f"\n🔗 LINK DE CHECKOUT (Já enviado ao cliente): {state.checkout_link}")
            lines.append("   ⚠️ O cliente JÁ TEM este link e está relatando PROBLEMAS.")
            lines.append("   → NÃO reenvie o link. Leia a mensagem do cliente e responda ao problema ESPECÍFICO dele.")
            lines.append("   → Responda com base no que o cliente disse, não repita respostas anteriores.")
        else:
            lines.append(f"\n🔗 CHECKOUT_LINK (SAGRADO - Envie exatamente): {state.checkout_link}")
            # Tip for the model
            if state.last_action == "action_generate_link" and state.last_action_success:
                 lines.append("   (O link acabou de ser gerado. Envie-o agora!)")

    if state.tracking_url:
        lines.append(f"\n🚚 TRACKING_URL: {state.tracking_url}")

    if state.order_id:
        lines.append(f"📦 ORDER_ID: {state.order_id}")

    # 3. PRODUCT DATA (Sales Flow)
    if domain == "sales":
        # Get focused product ID if set
        focused_product_id = state.soft_context.get("focused_product_id")
        selected_variant_id = state.soft_context.get("selected_variant_id")
        
        # PRIORITY 1: Checkout link exists - show only the carted product
        if state.checkout_link and state.selected_products:
            focused_product = None
            
            if selected_variant_id:
                for p in state.selected_products:
                    for v in p.get("variants") or []:
                        if str(v.get("id")) == str(selected_variant_id):
                            focused_product = p
                            break
                    if focused_product:
                        break
            
            if not focused_product and state.selected_products:
                focused_product = state.selected_products[0]
            
            if focused_product:
                title = focused_product.get("title", "Produto")
                price = _format_price(focused_product.get("price"))
                lines.append(f"\n🛒 PRODUTO NO CARRINHO: {title} - {price}")
                v_title = state.soft_context.get("selected_variant_title")
                if v_title:
                    lines.append(f"   → Variante: {v_title}")
                lines.append("   (Checkout link já gerado. NÃO liste outros produtos.)")
        
        # PRIORITY 2: focused_product_id set - User is asking about a SPECIFIC product
        # Show ONLY that product with FULL DESCRIPTION for grounding
        elif focused_product_id and state.selected_products:
            focused_product = None
            for p in state.selected_products:
                if str(p.get("product_id") or p.get("id")) == str(focused_product_id):
                    focused_product = p
                    break
            
            if focused_product:
                title = focused_product.get("title", "Produto")
                price = _format_price(focused_product.get("price"))
                description = focused_product.get("description", "")
                
                lines.append(f"\n🎯 PRODUTO EM FOCO (Responda sobre ESTE produto):")
                lines.append(f"   Nome: {title}")
                lines.append(f"   Preço: {price}")
                if description:
                    # Include FULL description for grounding to prevent hallucination
                    lines.append(f"   📋 DESCRIÇÃO TÉCNICA: {description}")
                    lines.append("   ⚠️ IMPORTANTE: Responda sobre materiais/detalhes APENAS com base na descrição acima.")
                    lines.append("   ⚠️ Se a informação não estiver aqui, diga: 'Não tenho essa informação específica'.")
                else:
                    lines.append("   (Sem descrição detalhada disponível)")
                
                # Show variant options if available
                if state.available_variants:
                    lines.append("\n   Variantes disponíveis:")
                    for v in state.available_variants[:5]:
                        available = v.get("available", True)
                        status = "" if available else "(ESGOTADO)"
                        lines.append(f"     - {v.get('title', 'Opção')} {status}")
                
                lines.append("\n   (NÃO liste outros produtos. Foque neste.)")
        
        # PRIORITY 3: No focus - Vitrine mode - show list for selection
        elif state.selected_products:
            lines.append("\n🛒 PRODUTOS ENCONTRADOS (Vitrine):")
            for idx, p in enumerate(state.selected_products, 1):
                title = p.get("title", "Produto")
                price = _format_price(p.get("price"))
                lines.append(f"   {idx}. {title} - {price}")
            lines.append("   (O cliente pode escolher ou perguntar sobre um deles)")
        
        # Search Results Context
        if state.last_action == "action_search_products":
             count = state.soft_context.get("search_results_count", 0)
             lines.append(f"\n🔍 BUSCA RECENTE: Encontrei {count} produtos para '{state.search_query or 'busca'}'")
             if count == 0:
                 lines.append("   → Nenhum produto encontrado. Avise o cliente.")

    # 4. SUPPORT DATA
    if domain == "support":
        if state.customer_email:
            lines.append(f"📧 EMAIL: {state.customer_email}")
        
        # Ticket/Refund context
        if state.soft_context.get("ticket_id") or state.metadata.get("ticket_id"):
            tid = state.soft_context.get("ticket_id") or state.metadata.get("ticket_id")
            lines.append(f"🎫 TICKET CRIADO: #{tid}")
        
        status = state.soft_context.get("order_status") or state.metadata.get("order_status")
        if status:
            lines.append(f"📊 STATUS PEDIDO: {status}")
            
        if state.ticket_opened:
            lines.append("- ticket_opened: True")

        wismo_context_parts = []

        if state.order_id:
            wismo_context_parts.append(f"Número do pedido: #{state.order_id}")

        if state.order_status:
            wismo_context_parts.append(f"Status do pedido: {state.order_status}")

        if state.tracking_code:
            wismo_context_parts.append(f"Código de rastreio: {state.tracking_code}")

        if state.tracking_last_event:
            wismo_context_parts.append(f"Última movimentação logística: {state.tracking_last_event}")

        if state.tracking_url:
            wismo_context_parts.append(f"Link de rastreio: {state.tracking_url}")

        if state.estimated_delivery:
            wismo_context_parts.append(f"Previsão de entrega: {state.estimated_delivery}")

        if state.missing_info_needed:
            if "email" in state.missing_info_needed:
                wismo_context_parts.append(
                    "INSTRUÇÃO: O sistema não encontrou o pedido automaticamente. "
                    "Peça o e-mail da compra de forma natural e amigável. "
                    "Não peça CPF. Não peça número do pedido ainda."
                )

        if state.metadata.get("wismo_error") == "order_not_found":
            wismo_context_parts.append(
                "INSTRUÇÃO: O pedido não foi encontrado com os dados fornecidos. "
                "Confirme se o e-mail ou número estão corretos, e ofereça abrir um ticket."
            )

        if state.metadata.get("wismo_error") == "shopify_not_configured":
            wismo_context_parts.append(
                "INSTRUÇÃO: Sistema de pedidos temporariamente indisponível. "
                "Peça desculpas e ofereça contato humano."
            )

        if wismo_context_parts:
            lines.append("## Dados do Pedido (WISMO)")
            lines.extend(wismo_context_parts)

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
    if domain == "support" and not state.order_id and not state.customer_email:
        lines.append("")
        lines.append("⚠️ ATENÇÃO: Faltam dados do pedido.")
        lines.append("- Se o cliente estiver apenas expressando emoção, agradecimento ou expectativa (ex: 'ansioso para chegar', 'gostei muito'), responda com empatia, celebre junto e agradeça a preferência, SEM pedir o número do pedido.")
        lines.append("- Caso ele faça uma solicitação real de status ou rastreio, aí sim peça o número do pedido ou email.")
        lines.append("- NUNCA invente prazos ou status específicos.")
    
    # 6. MEMORY / INTENT CONTEXT
    lines.append(f"\n🧠 CONTEXTO ATUAL:")
    lines.append(f"- Intenção: {state.intent}")
    lines.append(f"- Frustração: {state.frustration_level}/5")
    # Using RAG context if explicit memory is needed
    if state.rag_context:
        lines.append(f"- RAG Memory: {state.rag_context[:200]}...")

    # 7. BLOCKING INFO (What we need to ask)
    if state.blocking_info:
        lines.append(f"\n⚠️ DADOS FALTANTES (Pergunte ao cliente):")
        for info in state.blocking_info:
            lines.append(f"- {info}")

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
    """Generate a humanized LLM response using the Response Synthesizer."""
    
    # 1. Get RAG Context (semantic search)
    user_msg = state.last_user_message or ""
    # Only fetch RAG if relevant (Context optimization)
    if domain == "store_qa" or "como" in user_msg.lower() or "onde" in user_msg.lower():
         knowledge_context = get_knowledge_context(
            tenant.tenant_id, 
            categories,
            user_message=user_msg
        )
    else:
        # Minimal RAG for transactional flows to save tokens/noise
        knowledge_context = "" 
    
    # 2. Build Components
    history_str = _get_conversation_history_string(state)
    payload_str = _get_system_data_payload(state, tenant, domain, knowledge_context)
    brand_voice_guidelines = _get_brand_voice_guidelines(tenant)
    
    # 3. Format Master Prompt
    system_prompt = RESPONSE_SYNTHESIZER_PROMPT.format(
        tenant_name=tenant.name,
        brand_voice=brand_voice_guidelines,
        conversation_history=history_str,
        system_data_payload=payload_str
    )
    
    # Debug
    if os.getenv("DEBUG"):
        print(f"\n[SYNTHESIZER] Payload:\n{payload_str}\n")
    
    # 4. Call LLM
    model = get_model_name()
    llm = ChatOpenAI(model=model, temperature=0.6) # Slightly lower temp for adherence
    
    # We pass the prompt as System Message. 
    # The prompt explicitly contains "Contexto da Conversa" so we don't strictly need a HumanMessage 
    # with the last input, but we add a trigger to start generation.
    result = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content="Gere a resposta agora."),
    ])
    
    response = (result.content or "").strip()
    
    # 5. Metadata & Cleanup
    usage_raw = result.response_metadata.get("token_usage")
    state.soft_context["token_usage_agent"] = normalize_token_usage(usage_raw)
    
    if not response:
        raise ValueError("LLM returned empty response")
    
    # Clean quotes
    if response.startswith('"') and response.endswith('"'):
        response = response[1:-1]
    
    # Safety Net: Ensure link is present if we just generated it
    # But NOT for checkout_error or other non-purchase intents
    checkout_link = state.checkout_link
    non_link_intents = {"checkout_error", "greeting", "general", "order_status", "order_complaint"}
    if (domain == "sales" 
        and checkout_link 
        and checkout_link not in response
        and state.intent not in non_link_intents):
        if state.last_action == "action_generate_link":
            response += f"\n\n{checkout_link}"
    
    return response
