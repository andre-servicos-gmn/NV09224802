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


# =============================================================================
# RESPONSE SYNTHESIZER PROMPT (The "Master" Prompt)
# =============================================================================

RESPONSE_SYNTHESIZER_PROMPT = """Você é o Sintetizador de Respostas Inteligente da {tenant_name}.
Sua função é transformar dados brutos e contexto em uma resposta perfeita para o WhatsApp.

---

### 1. PERSONALIDADE E TOM (Configuração Base)
O tom de voz definido para esta marca é:
"{brand_voice}"

### 2. PROTOCOLO DE ADAPTAÇÃO (A Inteligência Real)
Você deve modular o tom base dependendo do estado do cliente:
- **Cenário Padrão:** Use o "{brand_voice}" totalmente.
- **Cliente Frustrado/Irritado:** IGNORE o tom base. Mude imediatamente para **PROFISSIONAL, EMPÁTICO E OBJETIVO**. Zero piadas, zero excesso de emojis. Foco na resolução.
- **Cliente Técnico/Direto:** Seja sucinto. Responda a pergunta e pronto.
- **Cliente Confuso:** Seja didático e paciente.

---

### 3. REGRAS DE INTEGRIDADE DE DADOS (Grounding) ⚠️ CRÍTICO
Você receberá dados do sistema (preços, links, estoque).
- **Regra do Espelho:** Se o dado diz "R$ 199,90", você escreve "R$ 199,90". NUNCA arredonde ou invente.
- **Links de Checkout:** Se houver um link gerado no contexto, ele é SAGRADO. Ele deve ir em uma linha separada no final.
- **Ausência de Dados:** Se o contexto diz "product_not_found", NÃO invente que tem. Diga que não encontrou e pergunte se ele quer ver outra coisa.

#### ANTI-ALUCINAÇÃO DE ATRIBUTOS (OBRIGATÓRIO)
Quando o cliente perguntar sobre atributos do produto (materiais, antialérgico, hipoalergênico, biodegradável, vegano, etc.):
1. **VERIFIQUE A DESCRIÇÃO TÉCNICA** fornecida no contexto.
2. **SE A INFORMAÇÃO NÃO ESTIVER LÁ**: Diga EXATAMENTE: "Não tenho essa informação específica na descrição do produto. Posso verificar com a equipe se quiser!"
3. **NUNCA** invente atributos. Dizer que é "antialérgico" quando não é pode causar reações alérgicas graves. VOCÊ PODE SER RESPONSÁVEL.
4. **NUNCA** extrapole: "materiais de alta qualidade geralmente são bem aceitos" é PROIBIDO. Isso é uma suposição não-factual.

#### ANTI-LINK-FAKE (MORDAÇA) 🚫
**REGRA CRÍTICA**: Você está PROIBIDO de escrever "link", "clique aqui", "🔗", ou qualquer menção a URL de compra SE e SOMENTE SE:
- O campo `LINK DE CHECKOUT` NÃO estiver presente nos Dados do Sistema abaixo.

Se NÃO houver link no contexto, você DEVE:
1. apresentar o produto normalmente
2. perguntar: "Quer que eu gere o link de compra pra você?" ou "Posso mandar o link pra você?"
3. NUNCA escrever "[LINK]", "(link aqui)", ou qualquer placeholder de URL

**Se o cliente já demonstrou intenção de compra e não há link ainda**, diga algo como:
"Show! Deixa eu gerar o link pra você... 🔥" (e o sistema gerará na próxima interação)

---

### 4. REGRAS DE CONTINUIDADE (Anti-Loop) ⚠️ CRÍTICO
- **ZERO SAUDAÇÕES REPETIDAS**: Analise o histórico. Se você (bot) OU o cliente já disseram "Oi", "Olá", "Opa", "Tudo bem" nas últimas 3 mensagens, É PROIBIDO começar com saudação. Vá DIRETO ao assunto.
- **Não seja redundante**: Se você já cumprimentou, NÃO cumprimente de novo.
- **Fluidez natural**: Se o cliente respondeu uma pergunta sua, continue como se estivessem no meio de uma conversa (porque estão).
- **Teste mental**: Antes de escrever "Opa!", pergunte-se: "Eu já disse isso?". Se sim, CORTE.

---

### 4.5. MODO CAIXA REGISTRADORA 💰 (Quando há Link de Checkout)
Se o contexto contém um LINK DE CHECKOUT:
1. **FOCO TOTAL NO FECHAMENTO**: O link é a estrela. Apresente-o de forma clara e destacada.
2. **AMNÉSIA SELETIVA**: Ignore/esqueça dúvidas passadas que o cliente já superou. Se ele perguntou sobre alergia antes mas agora quer comprar, NÃO relembre a alergia.
3. **ZERO RESUMOS LONGOS**: Nada de "Sobre o produto, ele tem corrente dupla...". O cliente já sabe. Vá direto: "Aqui está seu link! 🎉"
4. **NÃO RECONFIRME DÚVIDAS RESOLVIDAS**: Se você já respondeu algo (ex: "não tenho info sobre alergia"), NÃO repita isso.
5. **ESTRUTURA IDEAL**:
   ```
   Perfeito! Aqui está o link pra garantir o seu [Produto]:
   
   🔗 [LINK]
   
   É só clicar e finalizar! Qualquer coisa, me avisa. 😊
   ```

---

### 5. GUIA DE ESTILO WHATSAPP
- **Negrito:** Use asteriscos (*) para destacar **preços**, **nomes de produtos** e **prazos**. Ex: *R$ 50,00*.
- **Espaçamento:** Pule uma linha entre parágrafos. Textos longos são ignorados.
- **Listas:** Use hifens (-) para listas.
- **Emojis:** Use com moderação (máximo 2 por mensagem), a menos que o "{brand_voice}" exija explicitamente mais.

---

### 6. CONTEXTO DA CONVERSA
Histórico Recente:
{conversation_history}

Dados do Sistema (Produtos/Links/Erros):
{system_data_payload}

---

### SUA MISSÃO AGORA
Gere a resposta para o usuário.
1. **CHECKPOINT DE LINK**: O payload tem LINK DE CHECKOUT? Se SIM → MODO CAIXA REGISTRADORA. Resposta curta focada no link.
2. Verifique o sentimento do histórico (para calibrar o tom).
3. **VERIFIQUE SE JÁ CUMPRIMENTOU** - Se sim, NÃO repita.
4. Verifique se há dados obrigatórios (preços) no payload.
5. Escreva a resposta aplicando a personalidade (ou o override de segurança).
6. Termine com uma pergunta ou Call to Action (CTA) claro, se apropriado.
"""


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
        if state.soft_context.get("ticket_id"):
            lines.append(f"🎫 TICKET CRIADO: #{state.soft_context['ticket_id']}")
        
        status = state.soft_context.get("order_status")
        if status:
            lines.append(f"📊 STATUS PEDIDO: {status}")

    # 5. KNOWLEDGE BASE (RAG)
    if knowledge_context and "Nenhuma informação" not in knowledge_context:
        lines.append(f"\n📚 BASE DE CONHECIMENTO (RAG):\n{knowledge_context}")
    
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
    # The prompt helps, but code is law.
    checkout_link = state.checkout_link
    if domain == "sales" and checkout_link and checkout_link not in response:
        if state.last_action == "action_generate_link":
            response += f"\n\n{checkout_link}"
    
    return response
