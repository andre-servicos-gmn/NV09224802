# Modified: LLM-powered decide node with contextual reasoning.
import logging
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

# ============================================================================
# SALES DECIDE PROMPT - LLM-POWERED DECISION ENGINE
# ============================================================================

SALES_DECIDE_PROMPT = """Você é o DECIDE NODE do agente de vendas Nouvaris.

## SUA TAREFA
Analisar o estado atual e decidir qual ação executar.

## ESTADO ATUAL
- Intent: {intent}
- Sentiment: {sentiment_level}
- Frustration Level: {frustration_level}/5
- Last Action: {last_action}
- Last Action Success: {last_action_success}

## CONTEXTO DE PRODUTOS
{product_context}

## HISTÓRICO RECENTE
{conversation_history}

---

## ÁRVORE DE DECISÃO (siga EXATAMENTE nesta ordem)

### PASSO 1: Verificar Frustração/Problemas
```
SE frustration_level >= 3 OU sentiment = "angry":
   → RETORNAR "handoff"
   
SE last_action_success = False E last_action continha "checkout" ou "link":
   → RETORNAR "handoff" (usuário já teve problema)
```

### PASSO 2: Verificar se JÁ PODEMOS GERAR LINK
```
SE selected_variant_id existe (não é None/null):
   → RETORNAR "action_generate_link" (já temos tudo!)

SE existe produto selecionado E esse produto tem APENAS 1 variante:
   → RETORNAR "action_generate_link" (variante única = pular seleção)
```

### PASSO 3: Verificar se FALTA ESCOLHER VARIANTE
```
SE selected_products existe (lista não vazia)
   E selected_variant_id é None
   E o produto tem MAIS de 1 variante:
   → RETORNAR "action_select_variant"
```

### PASSO 4: Verificar se FALTA ESCOLHER PRODUTO
```
SE intent = "select_product" E selected_products não está vazio:
   → RETORNAR "action_select_product"

SE intent = "select_product" E selected_products está vazio:
   → RETORNAR "action_search_products" (precisa buscar primeiro)
```

### PASSO 5: Resolver Link de Produto
```
SE intent = "product_link":
   → RETORNAR "action_resolve_product"
```

### PASSO 6: Buscar Produtos
```
SE intent = "search_product" OU intent = "purchase_intent":
   → RETORNAR "action_search_products"
   
SE intent = "cart_retry" OU intent = "checkout_error":
   SE selected_variant_id existe:
      → RETORNAR "action_generate_link"
   SENÃO:
      → RETORNAR "respond" (perguntar o que deseja)
```

### PASSO 7: Fallback
```
QUALQUER OUTRO CASO:
   → RETORNAR "respond"
```

---

## NODES VÁLIDOS
- "action_resolve_product" - Resolver produto a partir de URL
- "action_search_products" - Buscar produtos por texto
- "action_select_product" - Usuário escolhe entre produtos
- "action_select_variant" - Usuário escolhe variante (cor, tamanho)
- "action_generate_link" - Gerar link de checkout
- "respond" - Apenas responder/conversar
- "handoff" - Transferir para humano

## RESPOSTA
Retorne APENAS o nome do node. Nada mais."""


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
    if state.selected_variant_id:
        lines.append(f"✅ Variante Escolhida: {state.selected_variant_id}")
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
    
    # Priority 1: Frustration/Handoff
    if state.needs_handoff:
        return "handoff"
    
    if state.frustration_level >= 3:
        return "handoff"
    
    # Priority 2: Already have variant → Generate link
    if state.selected_variant_id:
        return "action_generate_link"
    
    # Priority 3: Single variant product → Generate link directly
    if state.selected_products:
        first_product = state.selected_products[0]
        variants = first_product.get("variants", [])
        if len(variants) == 1:
            # Auto-select the single variant
            state.selected_variant_id = variants[0].get("id")
            return "action_generate_link"
    
    # Priority 4: Intent-based routing
    if state.intent == INTENT_PRODUCT_LINK:
        return "action_resolve_product"
    
    if state.intent == INTENT_SEARCH_PRODUCT:
        return "action_search_products"
    
    if state.intent == INTENT_SELECT_PRODUCT:
        if state.selected_products:
            return "action_select_product"
        else:
            return "action_search_products"
    
    if state.intent == INTENT_SELECT_VARIANT:
        if state.available_variants or state.selected_products:
            return "action_select_variant"
        else:
            return "respond"
    
    if state.intent in {INTENT_PURCHASE_INTENT, INTENT_ADD_TO_CART}:
        if state.selected_products:
            # Has products, check if needs variant selection
            first_product = state.selected_products[0]
            variants = first_product.get("variants", [])
            if len(variants) > 1 and not state.selected_variant_id:
                return "action_select_variant"
            elif state.selected_variant_id:
                return "action_generate_link"
        # No products yet, search
        return "action_search_products"
    
    if state.intent in {INTENT_CART_RETRY, INTENT_CHECKOUT_ERROR}:
        if state.selected_variant_id:
            # Switch strategy if last failed
            if state.last_action_success is False:
                state.last_strategy = next_strategy(state.last_strategy)
            return "action_generate_link"
        else:
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
        f"(variant={state.selected_variant_id}, products={len(state.selected_products or [])})"
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
    
    prompt = SALES_DECIDE_PROMPT.format(
        intent=state.intent,
        sentiment_level=state.sentiment_level,
        frustration_level=state.frustration_level,
        last_action=state.last_action or "None",
        last_action_success=state.last_action_success,
        product_context=product_context,
        conversation_history=conversation_history,
    )
    
    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        next_step = response.content.strip().lower().replace('"', '').replace("'", "")
        
        # Validate response
        valid_nodes = {
            "action_resolve_product",
            "action_search_products",
            "action_select_product",
            "action_select_variant",
            "action_generate_link",
            "respond",
            "handoff",
        }
        
        if next_step not in valid_nodes:
            logger.warning(f"[DECIDE LLM] Invalid response: {next_step}, falling back to heuristics")
            next_step = _decide_with_heuristics(state)
        
        state.next_step = next_step
        state.last_action = f"decide_llm_{next_step}"
        
        logger.info(f"[DECIDE LLM] → {next_step}")
        
    except Exception as e:
        logger.error(f"[DECIDE LLM] Error: {e}, falling back to heuristics")
        state.next_step = _decide_with_heuristics(state)
    
    return state
