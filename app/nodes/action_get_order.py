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
    client = ShopifyOrdersClient(
        store_domain=tenant.store_domain,
        access_token=tenant.shopify_access_token,
        api_version=tenant.shopify_api_version,
    )

    try:
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
            state.metadata["order_error"] = "order_not_found"
            state.tracking_url = None
            state.metadata.pop("tracking_number", None)
            state.bump_frustration()
            state.last_action = "get_order"
            return state

        # Success!
        state.last_action_success = True
        state.metadata.pop("order_error", None)
        
        # Store internal Shopify ID for technical reference, but keep state.order_id as customer facing number
        if order.get("id"):
            state.metadata["shopify_order_id"] = str(order.get("id"))
            
        # Ensure state.order_id is the customer facing number (ex: 1001)
        # This is critical for UX consistency.
        if order.get("order_number") and not state.order_id:
            state.order_id = str(order.get("order_number"))
        elif order.get("order_number") and state.order_id and str(order.get("order_number")) != str(state.order_id):
            # If we found it via internal ID but state has something else, align it to number
            # preventing internal ID from sticking in state.order_id
            state.order_id = str(order.get("order_number"))

        # Extract tracking
        # extract_tracking returns (tracking_url, tracking_number)
        tracking_url, tracking_number = client.extract_tracking(order)
        
        state.tracking_url = tracking_url
        if tracking_number:
            state.metadata["tracking_number"] = tracking_number
        
        if order.get("email"):
            state.customer_email = order.get("email")

        state.metadata["order_status"] = order.get("financial_status")
        state.metadata["fulfillment_status"] = order.get("fulfillment_status")
        state.metadata["order_items"] = _extract_items(order)
        state.metadata["order_created_at"] = order.get("created_at")
        if order.get("order_number") is not None:
            state.metadata["order_number"] = str(order.get("order_number"))

        state.last_action_success = True
        state.last_action = "get_order"
        return state

    except Exception as exc:
        state.last_action_success = False
        state.last_action = "get_order"
        state.metadata["order_error"] = str(exc)
        state.tracking_url = None
        state.metadata.pop("tracking_number", None)
        state.bump_frustration()
        return state
