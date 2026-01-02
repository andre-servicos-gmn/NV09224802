def lookup_order_by_id(tenant_id: str, order_id: str) -> dict:
    if tenant_id and order_id == "1001":
        return {
            "status": "fulfilled",
            "tracking_url": "https://track.example.com/ABC",
            "last_update_days": 30,
        }
    return {"status": "unknown", "tracking_url": None, "last_update_days": None}


def lookup_order_by_email(tenant_id: str, email: str) -> dict:
    if tenant_id and email:
        return {
            "order_id": "1001",
            "status": "fulfilled",
            "tracking_url": "https://track.example.com/ABC",
            "last_update_days": 30,
        }
    return {"order_id": None, "status": "unknown", "tracking_url": None, "last_update_days": None}


def open_carrier_ticket(tenant_id: str, order_id: str) -> bool:
    if tenant_id and order_id:
        return True
    return False
