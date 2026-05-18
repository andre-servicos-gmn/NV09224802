# Modified: removed checkout/cart/link generation — consultant+WISMO mode only.
import logging
import re
import unicodedata
from collections import Counter
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


# Stopwords gramaticais PT-BR universais (linguagem, não dados de tenant)
_PT_STOPWORDS = frozenset({
    "de", "da", "do", "das", "dos", "com", "para", "pra", "e", "em",
    "no", "na", "nos", "nas", "o", "a", "os", "as", "um", "uma", "uns",
    "umas", "ao", "aos", "à", "às", "por", "que", "se", "ou", "mas",
})

def _normalize(text: str) -> str:
    """Lowercase + remove acentos."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))

def _tokenize(text: str) -> list[str]:
    """Tokens normalizados, sem stopwords PT-BR, sem 1-2 chars, sem dígitos puros."""
    norm = _normalize(text)
    raw = norm.replace("-", " ").replace("/", " ").replace(",", " ").split()
    return [
        t for t in raw
        if len(t) >= 3 and t not in _PT_STOPWORDS and not t.isdigit()
    ]

def _build_dynamic_stopwords(products: list[dict]) -> frozenset[str]:
    """
    Stopwords dinâmicas por vitrine (TF-IDF leve).

    Token que aparece em > 50% dos títulos da vitrine ativa é considerado
    ruidoso (provavelmente marca/vendor/categoria genérica do tenant) e
    descartado do matching. Funciona pra qualquer tenant sem hardcode.

    Só ativa com 4+ produtos (abaixo disso, "frequência alta" não é sinal
    confiável de ruído).
    """
    if not products or len(products) < 4:
        return frozenset()

    token_doc_freq: Counter[str] = Counter()
    for p in products:
        title = p.get("title") or ""
        unique_tokens = set(_tokenize(title))
        for t in unique_tokens:
            token_doc_freq[t] += 1

    threshold = len(products) * 0.5
    return frozenset(t for t, count in token_doc_freq.items() if count > threshold)


def _match_product_by_name(state: ConversationState) -> tuple[dict | None, float]:
    """
    Match user message against selected_products by title.
    Returns (best_product, best_score). Score in [0.0, 1.0].

    Usa stopwords dinâmicas derivadas da vitrine ativa pra remover ruído de
    marca/vendor/categoria sem hardcode. Sistema multitenant-safe.
    """
    if not state.selected_products or not state.last_user_message:
        return None, 0.0

    dynamic_stops = _build_dynamic_stopwords(state.selected_products)

    def significant(text: str) -> set[str]:
        return {t for t in _tokenize(text) if t not in dynamic_stops}

    msg_tokens = significant(state.last_user_message)
    if not msg_tokens:
        return None, 0.0

    msg_norm = _normalize(state.last_user_message)

    best_match = None
    best_score = 0.0

    for product in state.selected_products:
        title = product.get("title") or ""
        title_set = significant(title)
        if not title_set:
            continue

        matched = msg_tokens & title_set

        # Exige no mínimo 2 tokens significativos OU 1 token longo (≥6 chars)
        if len(matched) < 2 and not any(len(t) >= 6 for t in matched):
            continue

        score = len(matched) / len(title_set)

        # Bonus: substring exata de token longo (apelido tipo "mopinho", "strong")
        for t in title_set:
            if len(t) >= 5 and t in msg_norm:
                score += 0.15
                break

        if score > best_score:
            best_match = product
            best_score = min(score, 1.0)

    return best_match, best_score


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

    # PRIORITY 2: USER NAMES A PRODUCT FROM ACTIVE SHOWCASE → PROMOTE TO FOCUS
    # Roda ANTES do roteamento por intent — caso contrário action_search_products
    # zera selected_products e perde a vitrine antes do match acontecer.
    if state.selected_products and not selected_variant_id:
        msg_norm = _normalize(state.last_user_message or "")
        msg_significant = _tokenize(state.last_user_message or "")
        followup_markers = {"fala", "mais", "sobre", "esse", "este", "aquele",
                            "qual", "quanto", "preco", "valor", "detalhe",
                            "info", "informacao", "produto", "tem"}
        is_followup = (
            len(msg_significant) <= 8
            or any(m in msg_norm for m in followup_markers)
        )

        if is_followup:
            matched, score = _match_product_by_name(state)
            if matched and score >= 0.6:
                variants = matched.get("variants") or []
                in_stock = matched.get("in_stock", True)

                if not in_stock:
                    logger.info(
                        f"[DECIDE] Match '{matched.get('title')}' OUT OF STOCK, "
                        f"skipping promotion"
                    )
                elif len(variants) > 1:
                    state.available_variants = [
                        {"id": str(v.get("id")), "title": v.get("title", ""),
                         "price": str(v.get("price", "")),
                         "available": v.get("available", True)}
                        for v in variants
                    ]
                    state.soft_context["focused_product_id"] = matched.get("product_id")
                    state.soft_context["product_title"] = matched.get("title")
                    state.soft_context["product_url"] = matched.get("url")
                    state.soft_context["product_price"] = matched.get("price")
                    logger.info(
                        f"[DECIDE] Promoted '{matched.get('title')}' "
                        f"(score={score:.2f}) → action_select_variant"
                    )
                    return "action_select_variant"
                else:
                    # BRANCH NOVO: produto sem variants → foco + respond direto
                    state.soft_context["focused_product_id"] = matched.get("product_id")
                    state.soft_context["product_title"] = matched.get("title")
                    state.soft_context["product_url"] = matched.get("url")
                    state.soft_context["product_price"] = matched.get("price")
                    logger.info(
                        f"[DECIDE] Promoted '{matched.get('title')}' "
                        f"(score={score:.2f}) → respond (no variants)"
                    )
                    return "respond"

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
