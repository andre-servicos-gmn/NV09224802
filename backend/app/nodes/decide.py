# Modified: removed checkout/cart/link generation — consultant+WISMO mode only.
import logging
import re
from app.core.constants import (
    INTENT_GREETING,
    INTENT_PRODUCT_LINK,
    INTENT_SEARCH_PRODUCT,
    INTENT_SELECT_PRODUCT,
    INTENT_SELECT_VARIANT,
)
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig

logger = logging.getLogger(__name__)


def _match_product_by_name(state: ConversationState) -> dict | None:
    """Try to match the user's message against existing selected_products by title."""
    if not state.selected_products or not state.last_user_message:
        return None

    msg = state.last_user_message.lower().strip()

    best_match = None
    best_score = 0

    for product in state.selected_products:
        title = (product.get("title") or "").lower()
        if not title:
            continue

        if title in msg:
            score = len(title)
            if score > best_score:
                best_match = product
                best_score = score
            continue

        title_words = title.split()
        matched_words = sum(1 for w in title_words if w in msg)
        if matched_words > 0:
            score = matched_words / len(title_words)
            if score >= 0.5 and score > best_score:
                best_match = product
                best_score = score

    return best_match


SALES_DECIDE_PROMPT = """Você é o Cérebro de Vendas do Nouvaris AI.
Sua missão é ajudar o cliente a encontrar e entender os produtos da loja.

## ESTADO ATUAL
Ferramentas disponíveis: [search_products, select_variant, human_handoff]
Contexto: {context}

## ESTRATÉGIA DE DECISÃO

1. **FASE DE DESCOBERTA (O cliente não sabe o que quer)**
   - Ação: `search_products`
   - Gatilho: Perguntas genéricas ("tem tênis?", "quais as novidades?").

2. **FASE DE REFINAMENTO (O cliente gostou, mas precisa decidir)**
   - Ação: `select_variant` ou Pergunta de Clarificação (resposta texto).
   - Gatilho: Cliente escolheu o modelo mas falta cor/tamanho.

3. **FASE DE INFORMAÇÃO (O cliente quer saber mais)**
   - Ação: resposta texto.
   - Gatilho: Perguntas sobre preço, material, disponibilidade.

4. **FASE DE RECUPERAÇÃO/ERRO**
   - Ação: `human_handoff`
   - Gatilho: O cliente está confuso, irritado, ou pede falar com atendente.

## OUTPUT
Retorne apenas o nome da tool ou "response" se for apenas falar."""


def _build_product_context(state: ConversationState) -> str:
    lines = []

    if state.selected_products:
        lines.append(f"📦 Produtos Selecionados: {len(state.selected_products)}")
        for i, p in enumerate(state.selected_products[:3], 1):
            title = p.get("title", "Sem título")
            variants = p.get("variants", [])
            variant_count = len(variants) if isinstance(variants, list) else 0
            lines.append(f"   {i}. {title} ({variant_count} variantes)")
            if variant_count == 1:
                lines.append(f"      → Variante única: {variants[0].get('title', 'Default')}")
    else:
        lines.append("📦 Produtos Selecionados: Nenhum")

    selected_variant_id = state.soft_context.get("selected_variant_id")
    if selected_variant_id:
        lines.append(f"✅ Variante Escolhida: {selected_variant_id}")
    else:
        lines.append("⏳ Variante Escolhida: Nenhuma")

    if state.available_variants:
        lines.append(f"🎨 Variantes Disponíveis: {len(state.available_variants)}")
        for v in state.available_variants[:5]:
            lines.append(f"   - {v.get('title', 'N/A')}")

    if state.search_query:
        lines.append(f"🔍 Busca: \"{state.search_query}\"")

    return "\n".join(lines)


def _build_conversation_context(state: ConversationState) -> str:
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

    selected_variant_id = state.soft_context.get("selected_variant_id")

    # ======================================================================
    # PRIORITY 1: Frustration/Handoff
    # ======================================================================
    if state.needs_handoff:
        return "handoff"

    if state.frustration_level >= 3:
        return "handoff"

    # ======================================================================
    # PRIORITY 2: USER NAMES A PRODUCT → MATCH & SET FOCUS
    # ======================================================================
    if (state.selected_products
            and state.intent in [INTENT_PRODUCT_LINK, INTENT_SEARCH_PRODUCT]
            and not selected_variant_id):

        matched = _match_product_by_name(state)
        if matched:
            variants = matched.get("variants") or []
            in_stock = matched.get("in_stock", True)

            if not in_stock:
                logger.info(f"[DECIDE] Product '{matched.get('title')}' matched but OUT OF STOCK")
            elif len(variants) > 1:
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
                logger.info(f"[DECIDE] Matched '{matched.get('title')}' with {len(variants)} variants → action_select_variant")
                return "action_select_variant"

    # ======================================================================
    # PRIORITY 3: Available variants but none selected → ask user
    # ======================================================================
    if state.available_variants and not selected_variant_id:
        if state.intent == INTENT_SELECT_VARIANT:
            return "action_select_variant"
        return "respond"

    # ======================================================================
    # PRIORITY 4: Intent-based routing
    # ======================================================================
    if state.intent == INTENT_PRODUCT_LINK:
        if state.selected_products:
            product = state.selected_products[0]
            variants = product.get("variants") or []
            if len(variants) > 1:
                if state.available_variants:
                    return "action_select_variant"
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
            return "respond"
        return "action_resolve_product"

    if state.intent == INTENT_SEARCH_PRODUCT:
        return "action_search_products"

    if state.intent == INTENT_SELECT_PRODUCT:
        if state.selected_products:
            return "action_select_product"
        return "action_search_products"

    if state.intent == INTENT_SELECT_VARIANT:
        # Só dispara select_variant se há ambiguidade real (variants pendentes
        # de escolha) OU se a msg referencia explicitamente um produto/variante.
        if state.available_variants:
            return "action_select_variant"

        # Sem available_variants, exige referência explícita à seleção:
        # número puro ("1", "2"), keywords ("o primeiro", "esse aí", "quero",
        # "esse"), ou nome de variante (cor/tamanho mencionado).
        msg = (state.last_user_message or "").lower().strip()
        explicit_selection = bool(re.match(
            r"^(o\s+)?(primeiro|segundo|terceiro|esse|este|aquele|"
            r"\d+\s*$|quero\s+(o|esse|este)|me\s+(ve|mostra)\s+(o|esse))",
            msg
        ))
        if explicit_selection and state.selected_products:
            return "action_select_variant"

        # Falso positivo do router — reclassifica baseado no contexto.
        if state.selected_products:
            logger.info(
                f"[DECIDE] select_variant rejeitado: msg='{msg[:50]}' sem "
                f"referência explícita. Re-classificando como search_product."
            )
            return "action_search_products"
        return "respond"

    if state.intent == INTENT_GREETING:
        return "respond"

    return "respond"


def decide(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Decide qual ação executar no fluxo de vendas."""
    next_step = _decide_with_heuristics(state)

    state.next_step = next_step
    state.last_action = f"decide_{next_step}"

    logger.info(
        f"[DECIDE] intent={state.intent} → next_step={next_step} "
        f"(variant={state.soft_context.get('selected_variant_id')}, products={len(state.selected_products or [])})"
    )

    return state


def decide_with_llm(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """LLM-powered decision for complex/ambiguous cases."""
    from app.core.llm import get_llm

    product_context = _build_product_context(state)
    conversation_history = _build_conversation_context(state)

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

        tool_map = {
            "search_products": "action_search_products",
            "select_variant": "action_select_variant",
            "human_handoff": "handoff",
            "response": "respond"
        }

        next_step = tool_map.get(raw_response, "respond")
        state.next_step = next_step
        state.last_action = f"decide_llm_{next_step}"

        logger.info(f"[DECIDE LLM] Response: {raw_response} → Node: {next_step}")

    except Exception as e:
        logger.error(f"[DECIDE LLM] Error: {e}, falling back to heuristics")
        state.next_step = _decide_with_heuristics(state)

    return state
