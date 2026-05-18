# Modified: clear cross-domain metadata before storing support data.
"""Order lookup action using Shopify Admin API.

Responsabilidade: buscar pedido na Shopify e atualizar o estado com dados reais.

TERMINOLOGIA DE IDS:
====================
- order_number: Visível ao cliente (ex: 1001). O cliente fornece este.
- order_name: Com prefixo "#" (ex: "#1001"). Shopify filtra por este campo.
- shopify_order_id: ID interno longo (ex: 5832749012345). Nunca pedir ao cliente.

FLUXO DE LOOKUP:
================
1. Se state.order_id existe → buscar via get_order_by_number (order_number).
2. Se não encontrar → tentar get_order_by_id (caso seja shopify_order_id legado).
3. Se ainda não encontrar E state.customer_email existe → fallback por email.
4. Se nada funcionar → marcar last_action_success = False.
"""
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.tools.shopify_orders import ShopifyOrdersClient


# 🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨
# MOCK WISMO — DEMO TEMPORÁRIO
# Esses dados são hardcoded SOMENTE para o tenant demo durante apresentação.
# REMOVER ANTES DE PRIMEIRO CLIENTE REAL ENTRAR EM PRODUÇÃO.
# Ativação: tenant_id deve ser EXATAMENTE d8ef2997-c035-4af7-b995-93b0332786c4
# 🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨
DEMO_TENANT_UUID = "d8ef2997-c035-4af7-b995-93b0332786c4"

DEMO_MOCK_ORDERS = {
    # Cenário 1: Pedido em trânsito normal (recém despachado)
    "1001": {
        "id": 999000001,
        "order_number": 1001,
        "name": "#1001",
        "email": "cliente.demo@example.com",
        "financial_status": "paid",
        "fulfillment_status": "fulfilled",
        "created_at": "2026-04-30T10:00:00-03:00",
        "fulfillments": [{
            "tracking_number": "BR123456789BR",
            "tracking_url": "https://rastreamento.correios.com.br/app/index.php?objeto=BR123456789BR",
            "tracking_company": "Correios",
            "updated_at": "2026-05-04T14:00:00-03:00",
        }],
        "line_items": [{
            "name": "Carro Kit 3 Mop Líquido e Limpeza Seca - Bralimpia",
            "quantity": 1,
            "sku": "BLP-NY",
            "variant_id": 1,
        }],
    },
    # Cenário 2: Pedido pago mas não despachado
    "1042": {
        "id": 999000002,
        "order_number": 1042,
        "name": "#1042",
        "email": "outro.cliente@example.com",
        "financial_status": "paid",
        "fulfillment_status": None,
        "created_at": "2026-05-05T16:00:00-03:00",
        "fulfillments": [],
        "line_items": [{
            "name": "Pulverizador de Compressão Prévia 6 litros - Guarani",
            "quantity": 2,
            "sku": "GU-6L",
            "variant_id": 2,
        }],
    },
    # Cenário 3: Pedido atrasado (tracking parado há 8 dias)
    "987": {
        "id": 999000003,
        "order_number": 987,
        "name": "#987",
        "email": "atrasado@example.com",
        "financial_status": "paid",
        "fulfillment_status": "fulfilled",
        "created_at": "2026-04-15T09:00:00-03:00",
        "fulfillments": [{
            "tracking_number": "BR987654321BR",
            "tracking_url": "https://rastreamento.correios.com.br/app/index.php?objeto=BR987654321BR",
            "tracking_company": "Correios",
            "updated_at": "2026-04-28T10:00:00-03:00",
        }],
        "line_items": [{
            "name": "Cera Protetora Carnaúba 5L - Vonixx",
            "quantity": 1,
            "sku": "VX-5L",
            "variant_id": 3,
        }],
    },
}


def _get_mock_order(state: "ConversationState") -> dict | None:
    """Retorna mock order baseado em state.order_id ou customer_email.

    🚨 SOMENTE TENANT DEMO 🚨
    """
    if state.order_id:
        normalized = state.order_id.lstrip("#")
        if normalized in DEMO_MOCK_ORDERS:
            return DEMO_MOCK_ORDERS[normalized]

    if state.customer_email:
        for order in DEMO_MOCK_ORDERS.values():
            if (order.get("email") or "").lower() == state.customer_email.lower():
                return order

    return None


def _extract_items(order: dict) -> list[dict]:
    items = []
    for item in order.get("line_items", []) or []:
        items.append(
            {
                "name": item.get("name"),
                "quantity": item.get("quantity"),
                "sku": item.get("sku"),
                "variant_id": item.get("variant_id"),
            }
        )
    return items


def action_get_order(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    # 🚨 INTERCEPTAÇÃO MOCK WISMO — DEMO 🚨
    # Se for o tenant demo, busca em DEMO_MOCK_ORDERS em vez de chamar Shopify.
    # Mantém o resto da função intacto pro caminho real (outros tenants).
    if tenant.uuid == DEMO_TENANT_UUID or tenant.tenant_id == DEMO_TENANT_UUID:
        if "search_query" in state.soft_context:
            del state.soft_context["search_query"]
        state.selected_products = []
        state.available_variants = []

        order = _get_mock_order(state)

        if not order:
            state.last_action_success = False
            state.last_action_status = "empty"
            state.soft_context["order_error"] = "order_not_found"
            state.tracking_url = None
            if "tracking_number" in state.soft_context:
                del state.soft_context["tracking_number"]
            state.bump_frustration()
            state.last_action = "get_order"
            return state

        state.last_action_success = True
        state.last_action_status = "success"
        if order.get("id"):
            state.soft_context["shopify_order_id"] = str(order["id"])
        if order.get("order_number") is not None:
            state.order_id = str(order["order_number"])

        fulfillments = order.get("fulfillments") or []
        if fulfillments:
            ff = fulfillments[0]
            state.tracking_url = ff.get("tracking_url")
            if ff.get("tracking_number"):
                state.soft_context["tracking_number"] = ff["tracking_number"]

            updated_at = ff.get("updated_at")
            if updated_at:
                from datetime import datetime, timezone
                try:
                    dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    days_since = (now - dt).days
                    state.tracking_last_update_days = max(0, days_since)
                except Exception:
                    pass
        else:
            state.tracking_url = None

        if order.get("email"):
            state.customer_email = order.get("email")

        state.soft_context["order_status"] = order.get("financial_status")
        state.soft_context["fulfillment_status"] = order.get("fulfillment_status")
        state.soft_context["order_created_at"] = order.get("created_at")
        if order.get("order_number") is not None:
            state.soft_context["order_number"] = str(order.get("order_number"))

        state.soft_context["order_items"] = _extract_items(order)

        state.last_action = "get_order"
        return state

    client = ShopifyOrdersClient(
        store_domain=tenant.store_domain,
        access_token=tenant.shopify_access_token,
        api_version=tenant.shopify_api_version,
    )

    try:
        # Limpar contexto de outros dominios
        if "search_query" in state.soft_context:
            del state.soft_context["search_query"]
        state.selected_products = []
        state.available_variants = []

        order = None
        
        # 1. Tentar buscar por order_number (o que o cliente geralmente fornece, ex: "1001")
        if state.order_id:
            order = client.get_order_by_number(state.order_id)
            
            # If not found by order_number, try as Shopify internal ID
            if not order:
                order = client.get_order_by_id(state.order_id)
        
        # Fall back to email lookup
        if not order and state.customer_email:
            order = client.get_latest_order_by_email(state.customer_email)

        if not order:
            state.last_action_success = False
            state.last_action_status = "empty"
            state.soft_context["order_error"] = "order_not_found"
            state.tracking_url = None
            if "tracking_number" in state.soft_context:
                del state.soft_context["tracking_number"]
            state.bump_frustration()
            state.last_action = "get_order"
            return state

        # Success!
        state.last_action_success = True
        state.last_action_status = "success"
        # Store internal Shopify ID for technical reference, but keep state.order_id as customer facing number
        if order.get("id"):
            state.soft_context["shopify_order_id"] = str(order.get("id"))
            
        # Ensure state.order_id is the customer facing number (ex: 1001)
        # This is critical for UX consistency.
        if order.get("order_number") and not state.order_id:
            state.order_id = str(order.get("order_number"))
        elif order.get("order_number") and state.order_id and str(order.get("order_number")) != str(state.order_id):
            # If we found it via internal ID but state has something else, align it to number
            # preventing internal ID from sticking in state.order_id
            state.order_id = str(order.get("order_number"))

        # Extract tracking
        # extract_tracking returns (tracking_number, tracking_url)
        tracking_number, tracking_url = client.extract_tracking(order)
        
        state.tracking_url = tracking_url
        if tracking_number:
            state.soft_context["tracking_number"] = tracking_number
        
        if order.get("email"):
            state.customer_email = order.get("email")

        state.soft_context["order_status"] = order.get("financial_status")
        state.soft_context["fulfillment_status"] = order.get("fulfillment_status")
        state.soft_context["order_items"] = _extract_items(order)
        state.soft_context["order_created_at"] = order.get("created_at")
        if order.get("order_number") is not None:
            state.soft_context["order_number"] = str(order.get("order_number"))

        state.last_action_success = True
        state.last_action = "get_order"
        return state

    except Exception as exc:
        state.last_action_success = False
        state.last_action_status = "system_error"
        state.last_action = "get_order"
        state.soft_context["order_error"] = str(exc)
        state.system_error = str(exc)
        state.tracking_url = None
        if "tracking_number" in state.soft_context:
            del state.soft_context["tracking_number"]
        state.bump_frustration()
        return state
