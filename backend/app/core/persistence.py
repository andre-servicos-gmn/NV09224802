"""Conversation persistence using Supabase database."""

import os

from app.core.database import (
    get_or_create_conversation,
    resolve_tenant_uuid,
    save_message,
    update_conversation_state,
)
from app.core.state import ConversationState


def persist_user_message(
    state: ConversationState,
    message: str,
) -> str | None:
    """Save user message to database and return conversation ID."""
    try:
        tenant_uuid = resolve_tenant_uuid(state.tenant_id)

        # Get or create conversation - session_id is the phone number for WhatsApp
        conversation = get_or_create_conversation(
            tenant_id=tenant_uuid,
            session_id=state.session_id,
            channel=state.channel,
            number=state.session_id if state.channel == "whatsapp" else None,
        )
        conversation_id = conversation["id"]

        # Save user message
        save_message(
            conversation_id=conversation_id,
            sender_type="user",
            content=message,
            intent=state.intent,
            domain=state.domain,
        )

        return conversation_id
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[DB] Error persisting user message: {e}")
        return None


def persist_agent_message(
    conversation_id: str | None,
    state: ConversationState,
) -> None:
    """Save agent message to database."""
    if not conversation_id or not state.last_bot_message:
        return

    try:
        save_message(
            conversation_id=conversation_id,
            sender_type="agent",
            content=state.last_bot_message,
            intent=state.intent,
            domain=state.domain,
            metadata={
                "last_action": state.last_action,
                "last_strategy": state.last_strategy,
                "frustration_level": state.frustration_level,
            },
        )
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[DB] Error persisting agent message: {e}")


def persist_conversation_state(
    conversation_id: str | None,
    state: ConversationState,
) -> None:
    """Update conversation state in database."""
    if not conversation_id:
        return

    try:
        state_dict = {
            "domain": state.domain,
            "intent": state.intent,
            "selected_product_id": state.soft_context.get("focused_product_id"),
            "selected_variant_id": state.soft_context.get("selected_variant_id"),
            "quantity": state.soft_context.get("quantity"),
            "order_id": state.order_id,
            "customer_email": state.customer_email,
            "frustration_level": state.frustration_level,
            "last_action": state.last_action,
            "last_strategy": state.last_strategy,
            "last_action_success": state.last_action_success,
        }
        update_conversation_state(conversation_id, state_dict)
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[DB] Error persisting state: {e}")
