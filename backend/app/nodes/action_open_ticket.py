"""Support ticket action using Supabase service role.

Responsabilidade: abrir ticket no Supabase sem decidir fluxo.
"""
from app.core.state import ConversationState
from app.core.supabase_client import get_supabase
from app.core.tenancy import TenantConfig


def action_open_ticket(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    client = get_supabase()
    payload = {
        "tenant_id": tenant.tenant_id,
        "order_id": state.order_id,
        "customer_email": state.customer_email,
        "channel": state.channel,
        "session_id": state.session_id,
        "intent": state.intent,
        "original_complaint": state.original_complaint,
    }
    payload = {key: value for key, value in payload.items() if value}

    try:
        client.table("support_tickets").upsert(payload).execute_upsert()
        state.ticket_opened = True
        state.last_action_success = True
    except Exception as exc:
        state.ticket_opened = False
        state.last_action_success = False
        state.metadata["ticket_error"] = str(exc)
        state.bump_frustration()

    state.last_action = "open_ticket"
    return state
