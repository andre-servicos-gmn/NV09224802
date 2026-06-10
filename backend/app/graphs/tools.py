"""Tools v2 do supervisor — implementação real (Prompt 2.2).

Tools reaproveitam infra v1:
- search_products / lookup_knowledge_base → app.rag_engine.pipeline.RAGPipeline
- get_order / get_tracking → app.tools.shopify_orders.ShopifyOrdersClient
- generate_checkout_link → constrói URL Shopify standard
- extract_user_facts → LLM call dedicada (gpt-4o-mini)
- escalate_handoff → detecção feita em invoke varrendo tool_calls

Tools que precisam de tenant_id recebem state via InjectedState do langgraph.
"""

import json
import logging
from typing import Annotated, Optional

from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────

def _resolve_tenant(tenant_id: str):
    """Resolve TenantConfig via registry. Lazy import pra evitar ciclos."""
    from app.core.tenancy import TenantRegistry
    return TenantRegistry().get(tenant_id, use_cache=True)


def _get_rag_pipeline(tenant_id: str):
    """Cria RAGPipeline pro tenant. tenant_id deve ser UUID."""
    from app.rag_engine.pipeline import RAGPipeline
    from app.core.database import resolve_tenant_uuid
    tenant_uuid = resolve_tenant_uuid(tenant_id)
    return RAGPipeline(tenant_id=tenant_uuid)


def _get_shopify_orders_client(tenant_id: str):
    """Cria ShopifyOrdersClient pro tenant atual."""
    from app.tools.shopify_orders import ShopifyOrdersClient
    tenant = _resolve_tenant(tenant_id)
    if not tenant.store_domain or not tenant.shopify_access_token:
        raise RuntimeError(f"Tenant {tenant_id} sem credenciais Shopify configuradas.")
    return ShopifyOrdersClient(
        store_domain=tenant.store_domain,
        access_token=tenant.shopify_access_token,
        api_version=getattr(tenant, "shopify_api_version", "2024-01"),
    )


def _format_products(products: list[dict]) -> str:
    """Formata lista de produtos pra string legível pelo LLM."""
    if not products:
        return "Nenhum produto encontrado para essa busca."
    lines = []
    for i, p in enumerate(products, 1):
        title = p.get("title", "Produto")
        pid = p.get("product_id") or p.get("id") or p.get("external_id") or "?"
        price = p.get("price")
        price_str = f"R$ {price:.2f}" if isinstance(price, (int, float)) else "consulta"
        lines.append(f"Produto {i}: {title} (ID: {pid}, {price_str})")
        desc = (p.get("description") or "").strip()
        if desc:
            lines.append(f"  {desc[:100]}")
    return "\n".join(lines)


def _format_order(order: dict) -> str:
    """Formata dict de pedido Shopify pra string legível pelo LLM."""
    if not order:
        return "Pedido não localizado."
    order_number = order.get("order_number") or order.get("name", "?")
    status = order.get("financial_status") or "desconhecido"
    fulfillment = order.get("fulfillment_status") or "pendente"
    total = order.get("total_price") or order.get("current_total_price") or "?"
    created_at = order.get("created_at", "")
    line_items = order.get("line_items") or []
    items_str = ", ".join(
        (li.get("title") or li.get("name", "item"))[:50] for li in line_items[:5]
    ) or "?"
    return (
        f"Pedido #{order_number}:\n"
        f"Status: {status} / fulfillment: {fulfillment}\n"
        f"Itens: {items_str}\n"
        f"Total: R$ {total}\n"
        f"Data: {created_at}"
    )


def _extract_tracking(order: dict) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extrai (tracking_url, tracking_number, status) dos fulfillments do order."""
    if not order:
        return None, None, None
    fulfillments = order.get("fulfillments") or []
    if not fulfillments:
        return None, None, None
    latest = fulfillments[-1]
    url = latest.get("tracking_url") or (
        (latest.get("tracking_urls") or [None])[0]
    )
    number = latest.get("tracking_number")
    status = latest.get("shipment_status") or latest.get("status")
    return url, number, status


# ─── Helper LLM pra extract_user_facts ────────────────────────────────

_EXTRACT_PROMPT = """Extraia fatos pessoais úteis do cliente desta mensagem.
Responda APENAS em JSON: {"facts": {"chave": "valor"}}.
Se nenhum fato relevante, responda: {"facts": {}}.
Exemplos:
- "comprando pro filho de 8 anos" → {"facts": {"filho_idade": 8}}
- "moro em SP" → {"facts": {"localizacao": "SP"}}
- "obrigado" → {"facts": {}}"""

_extract_llm = None


def _extract_facts_llm(message: str) -> dict:
    """Chama LLM dedicada pra extrair facts. Lazy init pra suportar tests."""
    global _extract_llm
    if _extract_llm is None:
        from langchain_openai import ChatOpenAI
        _extract_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    try:
        response = _extract_llm.invoke([
            SystemMessage(content=_EXTRACT_PROMPT),
            HumanMessage(content=message),
        ])
        content = response.content if hasattr(response, "content") else str(response)
        return json.loads(content).get("facts", {}) or {}
    except Exception as e:
        logger.warning(f"extract_facts_llm falhou: {e}")
        return {}


# ─── Tools ────────────────────────────────────────────────────────────


@tool
def search_products(
    query: str,
    state: Annotated[dict, InjectedState],
    limit: int = 5,
) -> str:
    """Busca produtos por similaridade semântica no catálogo da loja.

    Use quando o cliente menciona interesse em um tipo de produto, categoria,
    característica, ou pede recomendação. Exemplo: "corrente de prata",
    "algo pra presente", "tem em azul?".

    Args:
        query: termo de busca em linguagem natural
        limit: número máximo de produtos a retornar (default 5)

    Returns:
        string formatada com lista de produtos (id, título, preço, descrição curta)
    """
    try:
        pipeline = _get_rag_pipeline(state["tenant_id"])
        products = pipeline.search_products(query=query, limit=limit)
        return _format_products(products)
    except Exception as e:
        logger.exception("search_products falhou")
        return f"[erro buscando produtos: {e}]"


@tool
def get_product_variants(
    product_id: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Retorna variantes (tamanho, cor, etc) de um produto específico.

    Use APÓS o cliente demonstrar interesse num produto específico,
    quando ele perguntar sobre tamanhos, cores, ou opções disponíveis.

    Args:
        product_id: ID do produto (vindo de search_products)

    Returns:
        string com variantes disponíveis (id, título, preço, estoque)
    """
    try:
        from app.rag_engine.retriever import VectorRetriever
        from app.rag_engine.embedder import EmbeddingService
        from app.core.database import resolve_tenant_uuid

        tenant_uuid = resolve_tenant_uuid(state["tenant_id"])
        retriever = VectorRetriever(EmbeddingService())
        product = retriever.get_product_by_external_id(
            tenant_id=tenant_uuid,
            platform="shopify",
            external_id=product_id,
        )
        if not product:
            return f"Produto {product_id} não encontrado."

        variants = product.get("variants") or []
        if not variants:
            return "Esse produto não tem variantes — pode comprar direto."

        lines = [f"Variantes do produto {product_id}:"]
        for v in variants:
            vid = v.get("variant_id") or v.get("id", "?")
            vtitle = v.get("title", "Variante")
            vprice = v.get("price")
            vprice_str = f"R$ {vprice:.2f}" if isinstance(vprice, (int, float)) else "consulta"
            vstock = v.get("inventory_quantity") or v.get("stock", "?")
            lines.append(f"- {vtitle} (ID: {vid}, {vprice_str}, estoque: {vstock})")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("get_product_variants falhou")
        return f"[erro buscando variantes: {e}]"


@tool
def generate_checkout_link(
    product_id: str,
    variant_id: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Gera link de checkout do Shopify pra um produto+variante específicos.

    Use QUANDO o cliente confirmar intenção de compra com produto+variante
    definidos. Exemplo: "quero a tamanho M", "vou levar essa", "como compro?".
    NÃO use sem ter product_id E variant_id definidos.

    Args:
        product_id: ID do produto
        variant_id: ID da variante específica

    Returns:
        URL de checkout do Shopify
    """
    try:
        tenant = _resolve_tenant(state["tenant_id"])
        if not tenant.store_domain:
            return "[erro: tenant sem store_domain configurado]"
        url = f"https://{tenant.store_domain}/cart/{variant_id}:1"
        return f"Link de checkout gerado: {url}"
    except Exception as e:
        logger.exception("generate_checkout_link falhou")
        return f"[erro gerando checkout: {e}]"


@tool
def get_order(
    order_number: str,
    state: Annotated[dict, InjectedState],
    customer_email: Optional[str] = None,
) -> str:
    """Busca informações de um pedido (status, itens, valor).

    Use quando o cliente perguntar sobre um pedido específico — "cadê meu pedido",
    "comprei tal coisa e...". Se o cliente não forneceu o número, peça primeiro.

    Args:
        order_number: número do pedido (ex: "1001")
        customer_email: email do cliente (opcional, pra confirmação adicional)

    Returns:
        string com status do pedido, itens, valor, data
    """
    try:
        client = _get_shopify_orders_client(state["tenant_id"])
        order = client.get_order_by_number(order_number)
        if not order and customer_email:
            order = client.get_latest_order_by_email(customer_email)
        if not order:
            return "Pedido não localizado. Confirma o número?"
        return _format_order(order)
    except Exception as e:
        msg = str(e)
        if "402" in msg or "Payment Required" in msg:
            return (
                "Não consegui acessar os pedidos agora (problema temporário). "
                "Tenta de novo em alguns minutos."
            )
        logger.exception("get_order falhou")
        return f"[erro buscando pedido: {e}]"


@tool
def get_tracking(
    order_number: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Retorna URL e status de rastreio de um pedido enviado.

    Use APÓS get_order confirmar que o pedido foi despachado,
    ou quando o cliente perguntar especificamente sobre rastreio/entrega.

    Args:
        order_number: número do pedido

    Returns:
        URL de rastreio + status atual + última atualização
    """
    try:
        client = _get_shopify_orders_client(state["tenant_id"])
        order = client.get_order_by_number(order_number)
        if not order:
            return "Pedido não localizado pra rastreio."
        url, number, status = _extract_tracking(order)
        if not url and not number:
            return "Esse pedido ainda não foi despachado."
        return (
            f"Rastreio: {url or '(sem URL)'} | "
            f"Código: {number or '?'} | "
            f"Status: {status or 'em trânsito'}"
        )
    except Exception as e:
        msg = str(e)
        if "402" in msg or "Payment Required" in msg:
            return (
                "Não consegui acessar o rastreio agora (problema temporário). "
                "Tenta de novo em alguns minutos."
            )
        logger.exception("get_tracking falhou")
        return f"[erro buscando rastreio: {e}]"


@tool
def lookup_knowledge_base(
    query: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Busca em FAQ/políticas da loja (troca, devolução, frete, prazos).

    Use quando o cliente perguntar sobre políticas da loja, prazos de entrega,
    formas de pagamento, política de troca/devolução, garantias.

    Args:
        query: pergunta em linguagem natural

    Returns:
        trecho relevante da knowledge base
    """
    try:
        pipeline = _get_rag_pipeline(state["tenant_id"])
        result = pipeline.retrieve_context(query=query, context_type="policy")
        if not result or not result.strip():
            return (
                "Não tenho essa informação na base. "
                "Vou te transferir pra um humano se precisar de resposta exata."
            )
        return f"Encontrei isso na base: {result}"
    except Exception as e:
        logger.exception("lookup_knowledge_base falhou")
        return f"[erro buscando na base: {e}]"


@tool
def extract_user_facts(
    message: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Extrai fatos relevantes que o cliente mencionou e persiste em state.facts.

    Use quando o cliente compartilhar informação útil pra futuras respostas.
    Exemplo: "estou comprando pro meu filho de 8 anos", "moro em SP",
    "sou alérgico a níquel". O fato é salvo na memória persistente do graph
    (PostgresSaver) e fica disponível pro supervisor no prompt das próximas
    interações via seção "CONTEXTO PESSOAL JÁ CONHECIDO".

    Args:
        message: a frase do cliente que contém o fato

    Returns:
        Command com update de state.facts merge + ToolMessage explícito.
    """
    try:
        new_facts = _extract_facts_llm(message)
    except Exception as e:
        logger.warning(f"extract_user_facts falhou: {e}")
        return Command(update={
            "messages": [ToolMessage(
                content="Não consegui processar agora.",
                tool_call_id=tool_call_id,
            )]
        })

    if not new_facts:
        return Command(update={
            "messages": [ToolMessage(
                content="Nada novo capturado.",
                tool_call_id=tool_call_id,
            )]
        })

    # Merge com facts existentes (preserva o que já estava)
    existing = state.get("facts", {}) or {}
    merged = {**existing, **new_facts}

    captured_keys = ", ".join(new_facts.keys())
    return Command(update={
        "facts": merged,
        "messages": [ToolMessage(
            content=f"Capturei: {captured_keys}.",
            tool_call_id=tool_call_id,
        )]
    })


@tool
def escalate_handoff(
    reason: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Escala a conversa para um atendente humano.

    Use quando: cliente pede explicitamente humano, situação complexa fora
    do escopo do bot (reembolso, reclamação séria, dúvida legal), ou
    detectar frustração crescente. Após chamar essa tool, NÃO responda nada
    mais — a conversa fica pausada até humano resolver.

    Args:
        reason: motivo da escalação (uso interno + analytics)

    Returns:
        confirmação de escalação
    """
    # Retorna string simples (vira ToolMessage automaticamente no ToolNode).
    # A detecção do handoff acontece em invoke, varrendo tool_calls do turno.
    return f"Conversa escalada pra humano. Motivo: {reason}."


ALL_TOOLS = [
    search_products,
    get_product_variants,
    generate_checkout_link,
    get_order,
    get_tracking,
    lookup_knowledge_base,
    extract_user_facts,
    escalate_handoff,
]
