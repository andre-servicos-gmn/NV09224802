import logging
import re
from app.core.constants import (
    INTENT_GREETING,
    INTENT_SEARCH_PRODUCT,
)
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig

logger = logging.getLogger(__name__)


# ============================================================================
# SALES DECIDE PROMPT - CONSULTANT MODE
# ============================================================================

SALES_DECIDE_PROMPT = """Você é o Consultor de Produtos do Nouvaris AI.
Sua missão é tirar todas as dúvidas do cliente sobre produtos da loja.
Você NÃO realiza vendas, NÃO gera links de carrinho e NÃO processa pagamentos.

## ESTADO ATUAL
Ferramentas disponíveis: [search_products, human_handoff]
Contexto: {context}

## ESTRATÉGIA DE DECISÃO

1. **FASE DE DESCOBERTA (O cliente não sabe o que quer)**
   - Ação: `search_products`
   - Gatilho: Perguntas genéricas ("tem tênis?", "quais as novidades?").

2. **FASE DE ESCLARECIMENTO (O cliente quer saber mais sobre um produto)**
   - Ação: `response`
   - Gatilho: Perguntas sobre produto já apresentado (material, cor, tamanho, preço).

3. **FASE DE RECUPERAÇÃO/ERRO**
   - Ação: `human_handoff`
   - Gatilho: O cliente está confuso, irritado, ou pede para falar com atendente.

## OUTPUT
Retorne apenas "search_products", "human_handoff" ou "response"."""


def _build_product_context(state: ConversationState) -> str:
    """Build a clear product context summary."""
    lines = []

    if state.selected_products:
        lines.append(f"📦 Produtos em contexto: {len(state.selected_products)}")
        for i, p in enumerate(state.selected_products[:3], 1):
            title = p.get("title", "Sem título")
            lines.append(f"   {i}. {title}")
    else:
        lines.append("📦 Produtos em contexto: Nenhum")

    if state.search_query:
        lines.append(f'🔍 Última busca: "{state.search_query}"')

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
    # CONTINUITY GUARD: Se já há produtos e o usuário comenta/pergunta
    # sobre eles (não pede algo novo explicitamente), responde no contexto
    # atual ao invés de buscar de novo.
    # ======================================================================
    SHORT_QUESTION_PATTERN = re.compile(
        r'^(pq|por que|porque|como|qual|quanto|tem|é|faz|serve|vale|gostei|'
        r'esse|esse mesmo|esse que|achei|legal|bacana|interessante|bom|gosto|'
        r'me conta mais|fala mais|me diz|não entendi|me fala|quero saber|'
        r'e o|e a|e esse|e essa)\b',
        re.IGNORECASE
    )

    if (
        state.selected_products
        and state.intent in {INTENT_SEARCH_PRODUCT, INTENT_GREETING, "general", "store_qa"}
        and state.last_user_message
        and (
            len(state.last_user_message.strip()) < 40
            or SHORT_QUESTION_PATTERN.match(state.last_user_message.strip())
        )
    ):
        logger.info("[DECIDE] Continuity guard: produto existente + mensagem curta → respond")
        return "respond"

    # ======================================================================
    # CLEANUP: Reset product context on greetings / general conversation
    # sem produtos ativos. Se o usuário recomeça do zero, limpa o contexto.
    # ======================================================================
    RESET_INTENTS = {"greeting", "general", "store_qa"}
    if state.intent in RESET_INTENTS and not state.selected_products:
        state.search_query = None
        state.soft_context.pop("focused_product_id", None)
        state.soft_context.pop("search_results_count", None)
        state.soft_context.pop("search_method", None)
        state.soft_context.pop("search_error", None)
        logger.info(f"[DECIDE] Intent '{state.intent}' sem produtos → cleared stale context")
    # ======================================================================
    # PRIORITY 1: Frustration/Handoff
    # ======================================================================
    if state.needs_handoff:
        return "handoff"

    if state.frustration_level >= 3:
        return "handoff"

    # ======================================================================
    # PRIORITY 2: Busca de produto
    # ======================================================================
    if state.intent == INTENT_SEARCH_PRODUCT:
        return "action_search_products"

    # ======================================================================
    # PRIORITY 3: Greeting → responde boas-vindas
    # ======================================================================
    if state.intent == INTENT_GREETING:
        return "respond"

    # Default: responde com o contexto atual
    return "respond"


def decide(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """
    Decide qual ação executar no fluxo de consultoria.

    Usa heurísticas rápidas para decisões claras.
    """

    next_step = _decide_with_heuristics(state)

    state.next_step = next_step

    logger.info(
        f"[DECIDE] intent={state.intent} → next_step={next_step} "
        f"(products={len(state.selected_products or [])})"
    )

    return state


def decide_with_llm(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """
    LLM-powered decision para casos ambíguos.
    """
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
            "human_handoff": "handoff",
            "response": "respond",
        }

        next_step = tool_map.get(raw_response, "respond")

        state.next_step = next_step

        logger.info(f"[DECIDE LLM] Response: {raw_response} → Node: {next_step}")

    except Exception as e:
        logger.error(f"[DECIDE LLM] Error: {e}, falling back to heuristics")
        state.next_step = _decide_with_heuristics(state)

    return state
