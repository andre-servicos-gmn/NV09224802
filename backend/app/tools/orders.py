"""Orders operations using Supabase database."""

from datetime import datetime, timezone

from app.core.database import (
    create_ticket,
    get_order_by_number,
    get_orders_by_email,
    resolve_tenant_uuid,
)


def _calculate_days_since(timestamp: str | None) -> int | None:
    """Calculate days since a timestamp."""
    if not timestamp:
        return None
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        return delta.days
    except (ValueError, TypeError):
        return None


def lookup_order_by_id(tenant_id: str, order_id: str) -> dict:
    """Look up order by order number using database."""
    tenant_uuid = resolve_tenant_uuid(tenant_id)
    order = get_order_by_number(tenant_uuid, order_id)
    if not order:
        return {"status": "unknown", "tracking_url": None, "last_update_days": None}

    return {
        "order_id": order.get("order_number"),
        "status": order.get("status", "unknown"),
        "tracking_url": order.get("tracking_url"),
        "last_update_days": _calculate_days_since(order.get("tracking_last_update")),
    }


def lookup_order_by_email(tenant_id: str, email: str) -> dict:
    """Look up most recent order by email using database."""
    tenant_uuid = resolve_tenant_uuid(tenant_id)
    orders = get_orders_by_email(tenant_uuid, email)
    if not orders:
        return {
            "order_id": None,
            "status": "unknown",
            "tracking_url": None,
            "last_update_days": None,
        }

    # Get most recent order
    order = orders[0]
    return {
        "order_id": order.get("order_number"),
        "status": order.get("status", "unknown"),
        "tracking_url": order.get("tracking_url"),
        "last_update_days": _calculate_days_since(order.get("tracking_last_update")),
    }


def open_carrier_ticket(
    tenant_id: str,
    order_id: str,
    conversation_id: str | None = None,
    user_id: str | None = None,
) -> bool:
    """Open a support ticket for carrier complaint."""
    if not tenant_id or not order_id:
        return False

    try:
        tenant_uuid = resolve_tenant_uuid(tenant_id)
        # Get the order to link to ticket
        order = get_order_by_number(tenant_uuid, order_id)
        order_uuid = order.get("id") if order else None

        ticket = create_ticket(
            tenant_id=tenant_uuid,
            type_="carrier_complaint",
            user_id=user_id,
            conversation_id=conversation_id,
            order_id=order_uuid,
            subject=f"Rastreio parado - Pedido #{order_id}",
            description="Cliente reportou que o rastreio não atualiza há mais de 7 dias.",
        )
        return bool(ticket)
    except Exception:
        return False
