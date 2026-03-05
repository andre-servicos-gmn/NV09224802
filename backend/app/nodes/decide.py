# Modified: LLM-powered decide node with contextual reasoning.
import logging
import re
from app.core.constants import (
    INTENT_CART_RETRY,
    INTENT_CHECKOUT_ERROR,
    INTENT_GREETING,
    INTENT_PRODUCT_LINK,
    INTENT_PURCHASE_INTENT,
    INTENT_SEARCH_PRODUCT,
    INTENT_SELECT_PRODUCT,
    INTENT_SELECT_VARIANT,
    INTENT_ADD_TO_CART,
)
from app.core.state import ConversationState
from app.core.strategies import next_strategy
from app.core.tenancy import TenantConfig

logger = logging.getLogger(__name__)


def _match_product_by_name(state: ConversationState) -> dict | None:
    """Try to match the user's message against existing selected_products by title.
    
    Returns the matched product dict, or None.
    """
    if not state.selected_products or not state.last_user_message:
        return None
    
    msg = state.last_user_message.lower().strip()
    
    # Try exact substring match first
    best_match = None
    best_score = 0
    
    for product in state.selected_products:
        title = (product.get("title") or "").lower()
        if not title:
            continue
        
        # Check if product title is mentioned in the message
        if title in msg:
            score = len(title)  # Longer match = better
            if score > best_score:
                best_match = product
                best_score = score
            continue
        
        # Check each word of the title
        title_words = title.split()
        matched_words = sum(1 for w in title_words if w in msg)
        if matched_words > 0:
            score = matched_words / len(title_words)
            if score >= 0.5 and score > best_score:  # At least 50% of words match
                best_match = product
                best_score = score
    
    return best_match

# ============================================================================
# SALES DECIDE PROMPT - LLM-POWERED DECISION ENGINE
# ============================================================================

SALES_DECIDE_PROMPT = """Você é o Cérebro de Vendas do Nouvaris AI.
Sua missão é mover o cliente pelo funil de vendas da forma mais eficiente possível.

## ESTADO ATUAL
Ferramentas disponíveis: [search_products, select_variant, human_handoff]
Contexto: {context}

## ESTRATÉGIA DE DECISÃO (O "Funil")

1. **FASE DE DESCOBERTA (O cliente não sabe o que quer)**
   - Ação: `search_products`
   - Gatilho: Perguntas genéricas ("tem tênis?", "quais as novidades?").

2. **FASE DE REFINAMENTO (O cliente gostou, mas precisa decidir)**
   - Ação: `select_variant` ou Pergunta de Clarificação (resposta texto).
   - Gatilho: Cliente escolheu o modelo mas falta cor/tamanho.

3. **FASE DE FECHAMENTO (O cliente decidiu)**
   - Ação: `response`
   - Gatilho: "Quero esse", "Quanto fica o frete para CEP X?", "Manda o link".
   - **Regra de Ouro:** Se o cliente deu sinais de compra, NÃO ofereça mais produtos. Conduza o fechamento da venda pelo chat.

4. **FASE DE RECUPERAÇÃO/ERRO**
   - Ação: `human_handoff`
   - Gatilho: O cliente está confuso, irritado, ou pede falar com atendente repetidamente.

## OUTPUT
Retorne apenas o nome da tool ou "response" se for apenas falar."""


def _build_product_context(state: ConversationState) -> str:
    """Build a clear product context summary."""
    lines = []
    
    # Selected products
    if state.selected_products:
        lines.append(f"📦 Produtos Selecionados: {len(state.selected_products)}")
        for i, p in enumerate(state.selected_products[:3], 1):
            title = p.get("title", "Sem título")
            variants = p.get("variants", [])
            variant_count = len(variants) if isinstance(variants, list) else 0
            lines.append(f"   {i}. {title} ({variant_count} variantes)")
            
            # Show variant info if single variant
            if variant_count == 1:
                lines.append(f"      → Variante única: {variants[0].get('title', 'Default')}")
    else:
        lines.append("📦 Produtos Selecionados: Nenhum")
    
    # Selected variant
    selected_variant_id = state.soft_context.get("selected_variant_id")
    if selected_variant_id:
        lines.append(f"✅ Variante Escolhida: {selected_variant_id}")
    else:
        lines.append("⏳ Variante Escolhida: Nenhuma")
    
    # Available variants (if showing options)
    if state.available_variants:
        lines.append(f"🎨 Variantes Disponíveis: {len(state.available_variants)}")
        for v in state.available_variants[:5]:
            lines.append(f"   - {v.get('title', 'N/A')}")
    
    # Search query
    if state.search_query:
        lines.append(f"🔍 Busca: \"{state.search_query}\"")
    
    return "\n".join(lines)


def _build_conversation_context(state: ConversationState) -> str:
    """Build recent conversation history."""
    if not state.conversation_history:
        return "Nenhuma mensagem anterior"
    
    recent = state.conversation_history[-6:]
    lines = []
    for msg in recent:
        role = "👤 User" if msg.get("role") == "user" else "🤖 Bot"
        content = msg.get("message", msg.get("content", ""))[:100]
        lines.append(f"{role}: {content}")
    
    return "\n".join(lines)


def _decide_with_heuristics(state: ConversationState) -> str:
    """Fast heuristic-based decision (no LLM call needed)."""
    
    # ======================================================================
    # CLEANUP: Reset product context on greetings / general conversation
    # If the user says "oi" or starts a new topic, they don't want to see
    # stale products from a previous interaction.
    # ======================================================================
    RESET_INTENTS = {"greeting", "general", "store_qa"}
    if state.intent in RESET_INTENTS:
        state.selected_products = []
        state.available_variants = []
        state.search_query = None
        state.soft_context.pop("focused_product_id", None)
        state.soft_context.pop("selected_variant_id", None)
        state.soft_context.pop("selected_variant_title", None)
        state.soft_context.pop("search_results_count", None)
        state.soft_context.pop("search_method", None)
        state.soft_context.pop("search_error", None)
        logger.info(f"[DECIDE] Intent '{state.intent}' → cleared stale product context")
    
    selected_variant_id = state.soft_context.get("selected_variant_id")
    
    # Intents that SHOULD trigger link generation when variant is selected
    PURCHASE_INTENTS = {
        INTENT_PURCHASE_INTENT, INTENT_PRODUCT_LINK, INTENT_ADD_TO_CART,
        INTENT_CART_RETRY, INTENT_SELECT_VARIANT, INTENT_SELECT_PRODUCT,
    }
    
    # ======================================================================
    # PRIORITY 0: VARIANT SELECTED + PURCHASE INTENT → GENERATE LINK
    # Only generate link when user is actively trying to buy.
    # If user is complaining about checkout errors, asking questions, or
    # having general conversation, let it fall through to respond node.
    # ======================================================================
    if (selected_variant_id 
        and state.selected_products 
        and state.intent in PURCHASE_INTENTS
        and state.last_action != "respond"):
        
        logger.info("[DECIDE] Variant selected + purchase intent → respond")
        return "respond"
    
    # ======================================================================
    # PRIORITY 0.5: USER NAMES A PRODUCT → MATCH & SELECT
    # When user says "gere o link do Silver Threader" and products are
    # already loaded, match the product by name, auto-select variant.
    # ======================================================================
    if (state.selected_products
        and state.intent in [INTENT_PURCHASE_INTENT, INTENT_PRODUCT_LINK, INTENT_ADD_TO_CART, INTENT_CART_RETRY, INTENT_SEARCH_PRODUCT]
        and not selected_variant_id):
        
        matched = _match_product_by_name(state)
        if matched:
            variants = matched.get("variants") or []
            in_stock = matched.get("in_stock", True)
            
            if not in_stock:
                logger.info(f"[DECIDE] Product '{matched.get('title')}' matched but OUT OF STOCK")
                # Let respond node tell the user it's out of stock
            elif len(variants) <= 1:
                # Auto-select single variant
                if len(variants) == 1:
                    state.soft_context["selected_variant_id"] = str(variants[0].get("id"))
                    state.soft_context["selected_variant_title"] = variants[0].get("title", "Default")
                else:
                    state.soft_context["selected_variant_id"] = str(matched.get("product_id") or matched.get("id"))
                    state.soft_context["selected_variant_title"] = matched.get("title", "")
                logger.info(f"[DECIDE] Matched product '{matched.get('title')}' → auto-selected variant → respond")
                return "respond"
            else:
                # Multiple variants — populate available_variants and ask
                state.available_variants = [
                    {
                        "id": str(v.get("id")),
                        "title": v.get("title", ""),
                        "price": str(v.get("price", "")),
                        "available": v.get("available", True),
                    }
                    for v in variants
                ]
                state.soft_context["focused_product_id"] = matched.get("product_id")
                logger.info(f"[DECIDE] Matched product '{matched.get('title')}' with {len(variants)} variants → action_select_variant")
                return "action_select_variant"
    
    # ======================================================================
    # PRIORITY 1: Frustration/Handoff
    # ======================================================================
    if state.needs_handoff:
        return "handoff"
    
    if state.frustration_level >= 3:
        return "handoff"
    
    # Priority 2.5: Product selected but needs variant choice
    # If we have available variants but none selected, we need to handle this
    # We trust that if available_variants is populated, we have a focus product
    if (state.available_variants 
        and not selected_variant_id):
        
        # If user is specifically trying to select variant, purchase, or get link
        if state.intent in [INTENT_SELECT_VARIANT, INTENT_PURCHASE_INTENT, INTENT_SELECT_PRODUCT, INTENT_PRODUCT_LINK, INTENT_ADD_TO_CART, INTENT_CART_RETRY]:
            return "action_select_variant"
        else:
            # Need to ask user which variant
            return "respond"

    # Priority 3: Single variant product → Generate link directly
    # Can happen if available_variants has exactly 1 item
    if state.available_variants and len(state.available_variants) == 1 and not state.soft_context.get("selected_variant_id"):
        state.soft_context["selected_variant_id"] = state.available_variants[0]["id"]
        state.soft_context["selected_variant_title"] = state.available_variants[0]["title"]
        return "respond"
        
        first_product = state.selected_products[0]
        variants = first_product.get("variants") or []
        if len(variants) == 1:
            # Auto-select the single variant (fallback to raw data if needed)
            state.soft_context["selected_variant_id"] = str(variants[0].get("id"))
            return "respond"
    
    # Priority 4: Intent-based routing
    if state.intent == INTENT_PRODUCT_LINK:
        # User asked for link. If we have products, try to generate link directly
        if state.selected_products and len(state.selected_products) > 0:
            product = state.selected_products[0]
            variants = product.get("variants") or []
            
            # Auto-select variant if single or none
            if len(variants) <= 1:
                if len(variants) == 1:
                    state.soft_context["selected_variant_id"] = str(variants[0].get("id"))
                    state.soft_context["selected_variant_title"] = variants[0].get("title", "Default")
                else:
                    state.soft_context["selected_variant_id"] = str(product.get("product_id") or product.get("id"))
                    state.soft_context["selected_variant_title"] = product.get("title", "")
                logger.info(f"[DECIDE] product_link: Auto-selected variant {state.soft_context['selected_variant_id']} → respond")
                return "respond"
            
            # Multiple variants - need to ask user
            if state.available_variants:
                return "action_select_variant"
            
            # Populate variants and ask
            state.available_variants = [
                {
                    "id": str(v.get("id")),
                    "title": v.get("title", ""),
                    "price": str(v.get("price", "")),
                    "available": v.get("available", True)
                }
                for v in variants
            ]
            return "action_select_variant"
        
        # No products yet - resolve the product first
        return "action_resolve_product"
    
    # CART_RETRY: User asking for link again - treat same as product_link
    if state.intent == INTENT_CART_RETRY:
        if state.selected_products and len(state.selected_products) > 0:
            product = state.selected_products[0]
            variants = product.get("variants") or []
            
            # Auto-select variant if single or none
            if len(variants) <= 1:
                if len(variants) == 1:
                    state.soft_context["selected_variant_id"] = str(variants[0].get("id"))
                    state.soft_context["selected_variant_title"] = variants[0].get("title", "Default")
                else:
                    state.soft_context["selected_variant_id"] = str(product.get("product_id") or product.get("id"))
                    state.soft_context["selected_variant_title"] = product.get("title", "")
                logger.info(f"[DECIDE] cart_retry: Auto-selected variant {state.soft_context['selected_variant_id']} → respond")
                return "respond"
            
            # Multiple variants - need to ask user
            return "action_select_variant"
        
        # No products - need to search first
        return "action_search_products"
    
    if state.intent == INTENT_SEARCH_PRODUCT:
        return "action_search_products"
    
    if state.intent == INTENT_SELECT_PRODUCT:
        if state.selected_products:
            return "action_select_product"
        else:
            return "action_search_products"
    
    if state.intent == INTENT_SELECT_VARIANT:
        # If we have variants to choose from, go to select variant
        if state.available_variants:
            return "action_select_variant"
        # If we have products but variants not populated yet
        elif state.selected_products:
            return "action_select_variant"
        else:
            return "respond"
    
    if state.intent in {INTENT_PURCHASE_INTENT, INTENT_ADD_TO_CART}:
        # User wants to buy! Be aggressive about closing the sale.
        
        # If already have variant, just generate link
        if state.soft_context.get("selected_variant_id"):
            return "respond"
        
        # If we have products
        if state.selected_products:
            first_product = state.selected_products[0]
            variants = first_product.get("variants") or []
            
            # Single variant or no variants? Auto-select and generate link!
            if len(variants) <= 1:
                if len(variants) == 1:
                    state.soft_context["selected_variant_id"] = str(variants[0].get("id"))
                    state.soft_context["selected_variant_title"] = variants[0].get("title", "Default")
                else:
                    # No variants in data - use product_id as variant_id (Shopify default)
                    state.soft_context["selected_variant_id"] = str(first_product.get("product_id") or first_product.get("id"))
                    state.soft_context["selected_variant_title"] = first_product.get("title", "")
                logger.info(f"[DECIDE] PURCHASE_INTENT: Auto-selected variant {state.soft_context['selected_variant_id']} → respond")
                return "respond"
            
            # Multiple variants - need user to choose
            if state.available_variants and len(state.available_variants) > 1:
                return "action_select_variant"
            
            # Variants exist in product data but not in state.available_variants - populate them
            if len(variants) > 1:
                state.available_variants = [
                    {
                        "id": str(v.get("id")),
                        "title": v.get("title", ""),
                        "price": str(v.get("price", "")),
                        "available": v.get("available", True)
                    }
                    for v in variants
                ]
                return "action_select_variant"
        
        # No products yet, search first
        return "action_search_products"
    
    if state.intent == INTENT_CART_RETRY:
        if state.soft_context.get("selected_variant_id"):
            # Switch strategy if last failed
            if state.last_action_success is False:
                state.last_strategy = next_strategy(state.last_strategy)
            return "respond"
        else:
            return "respond"
    
    # CHECKOUT_ERROR: User reports payment/checkout issues.
    # DO NOT regenerate the link — instead let the respond node provide
    # actual help (try different card, clear cache, etc.)
    if state.intent == INTENT_CHECKOUT_ERROR:
        return "respond"
    
    if state.intent == INTENT_GREETING:
        return "respond"
    
    # Default: respond
    return "respond"


def decide(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """
    Decide qual ação executar no fluxo de vendas.
    
    Usa heurísticas rápidas para decisões claras.
    Em casos ambíguos, pode usar LLM para decisão contextual.
    """
    
    # Use fast heuristics (covers 95% of cases)
    next_step = _decide_with_heuristics(state)
    
    state.next_step = next_step
    state.last_action = f"decide_{next_step}"
    
    logger.info(
        f"[DECIDE] intent={state.intent} → next_step={next_step} "
        f"(variant={state.soft_context.get('selected_variant_id')}, products={len(state.selected_products or [])})"
    )
    
    return state


def decide_with_llm(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """
    LLM-powered decision for complex/ambiguous cases.
    
    Use this when heuristics are insufficient.
    """
    from app.core.llm import get_llm
    
    # Build context
    product_context = _build_product_context(state)
    conversation_history = _build_conversation_context(state)
    
    # Combined context for Turbo prompt
    full_context = f"""
    INTENT: {state.intent}
    SENTIMENT: {state.sentiment_level}
    FRUSTRATION: {state.frustration_level}
    LAST ACTION: {state.last_action} (Success: {state.last_action_success})
    
    PRODUCTS:
    {product_context}
    
    HISTORY:
    {conversation_history}
    """
    
    prompt = SALES_DECIDE_PROMPT.format(context=full_context)
    
    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        raw_response = response.content.strip().lower().replace('"', '').replace("'", "")
        
        # Tool Mapping (Turbo Prompt friendly names -> System Node names)
        tool_map = {
            "search_products": "action_search_products",
            "human_handoff": "handoff",
            "response": "respond"
        }
        
        # Resolve mapped name, defaulting to raw if not found (fallback)
        next_step = tool_map.get(raw_response, "respond")

        state.next_step = next_step
        state.last_action = f"decide_llm_{next_step}"
        
        logger.info(f"[DECIDE LLM] Response: {raw_response} → Node: {next_step}")
        
    except Exception as e:
        logger.error(f"[DECIDE LLM] Error: {e}, falling back to heuristics")
        state.next_step = _decide_with_heuristics(state)
    
    return state
