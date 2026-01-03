import re

from app.core.constants import (
    INTENT_ORDER_COMPLAINT,
    INTENT_ORDER_STATUS,
    INTENT_ORDER_TRACKING,
    INTENT_PROVIDE_EMAIL,
    INTENT_PROVIDE_ORDER_ID,
)
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def _extract_order_id(message: str) -> str | None:
    match = re.search(r"\b\d{3,}\b", message)
    if not match:
        return None
    return match.group(0)


def _extract_email(message: str) -> str | None:
    match = re.search(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", message.lower())
    if not match:
        return None
    return match.group(0)


def support_decide(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    if state.needs_handoff:
        state.next_step = "handoff"
        state.last_action = "route_to_handoff"
        state.last_action_success = True
        return state

    if state.intent == INTENT_ORDER_COMPLAINT:
        state.metadata["complaint_pending"] = True

    # Extract order_id from message - ALWAYS overwrite if intent is provide_order_id
    # This respects user corrections per AGENT.md canonical state contract
    order_id = _extract_order_id(state.last_user_message or "")
    if order_id:
        if state.intent == INTENT_PROVIDE_ORDER_ID or not state.order_id:
            if state.order_id != order_id:
                # Clear stale tracking data from previous order
                state.tracking_url = None
                state.tracking_last_update_days = None
                state.metadata.pop("order_status", None)
                state.ticket_opened = False
            state.order_id = order_id

    # Extract email - ALWAYS overwrite if intent is provide_email
    email = _extract_email(state.last_user_message or "")
    if email:
        if state.intent == INTENT_PROVIDE_EMAIL or not state.customer_email:
            state.customer_email = email

    if state.last_action == "lookup_order":
        if (
            state.tracking_last_update_days is not None
            and state.tracking_last_update_days >= 7
            and state.metadata.get("complaint_pending")
        ):
            state.next_step = "action_open_ticket"
        else:
            state.next_step = "support_respond"
        return state

    if state.intent in {INTENT_ORDER_STATUS, INTENT_ORDER_TRACKING, INTENT_ORDER_COMPLAINT}:
        if not state.order_id and not state.customer_email:
            state.next_step = "support_respond"
        else:
            state.next_step = "action_lookup_order"
        return state

    if state.intent in {INTENT_PROVIDE_ORDER_ID, INTENT_PROVIDE_EMAIL}:
        if state.order_id or state.customer_email:
            state.next_step = "action_lookup_order"
        else:
            state.next_step = "support_respond"
        return state

    state.next_step = "support_respond"
    return state
