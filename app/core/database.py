"""Supabase database client for Nouvaris Agents V2."""

import os
from functools import lru_cache

from supabase import Client, create_client


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Get a cached Supabase client instance."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


# =============================================================================
# TENANT OPERATIONS
# =============================================================================


def get_tenant(tenant_id: str) -> dict | None:
    """Get tenant by ID."""
    client = get_client()
    result = client.table("tenants").select("*").eq("id", tenant_id).execute()
    return result.data[0] if result.data else None


def get_tenant_by_name(name: str) -> dict | None:
    """Get tenant by name."""
    client = get_client()
    result = client.table("tenants").select("*").eq("name", name).execute()
    return result.data[0] if result.data else None


def resolve_tenant_uuid(tenant_id_or_name: str) -> str:
    """Resolve tenant name or ID to UUID.
    
    If the input looks like a UUID, return it as-is.
    Otherwise, look up the tenant by name and return its UUID.
    Falls back to demo tenant UUID if not found.
    """
    # Check if it's already a UUID format
    if "-" in tenant_id_or_name and len(tenant_id_or_name) == 36:
        return tenant_id_or_name
    
    # Try to find tenant by name
    client = get_client()
    result = client.table("tenants").select("id").eq("name", tenant_id_or_name).execute()
    if result.data:
        return result.data[0]["id"]
    
    # Try case-insensitive match
    result = client.table("tenants").select("id").ilike("name", tenant_id_or_name).execute()
    if result.data:
        return result.data[0]["id"]
    
    # Default to demo tenant
    return "00000000-0000-0000-0000-000000000001"


# =============================================================================
# USER OPERATIONS
# =============================================================================


def get_or_create_user(
    tenant_id: str,
    phone: str | None = None,
    email: str | None = None,
    name: str | None = None,
) -> dict:
    """Get existing user or create a new one."""
    client = get_client()

    # Try to find by phone first
    if phone:
        result = (
            client.table("users")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("phone", phone)
            .execute()
        )
        if result.data:
            return result.data[0]

    # Try to find by email
    if email:
        result = (
            client.table("users")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("email", email)
            .execute()
        )
        if result.data:
            return result.data[0]

    # Create new user
    user_data = {"tenant_id": tenant_id}
    if phone:
        user_data["phone"] = phone
    if email:
        user_data["email"] = email
    if name:
        user_data["name"] = name

    result = client.table("users").insert(user_data).execute()
    return result.data[0]


# =============================================================================
# CONVERSATION OPERATIONS
# =============================================================================


def create_conversation(
    tenant_id: str,
    session_id: str,
    user_id: str | None = None,
    channel: str = "whatsapp",
) -> dict:
    """Create a new conversation."""
    client = get_client()
    data = {
        "tenant_id": tenant_id,
        "session_id": session_id,
        "channel": channel,
    }
    if user_id:
        data["user_id"] = user_id

    result = client.table("conversations").insert(data).execute()
    return result.data[0]


def get_conversation_by_session(tenant_id: str, session_id: str) -> dict | None:
    """Get conversation by session ID."""
    client = get_client()
    result = (
        client.table("conversations")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("session_id", session_id)
        .execute()
    )
    return result.data[0] if result.data else None


def get_or_create_conversation(
    tenant_id: str,
    session_id: str,
    user_id: str | None = None,
    channel: str = "whatsapp",
) -> dict:
    """Get existing conversation or create a new one."""
    conversation = get_conversation_by_session(tenant_id, session_id)
    if conversation:
        return conversation
    return create_conversation(tenant_id, session_id, user_id, channel)


def update_conversation_state(conversation_id: str, state: dict) -> dict:
    """Update conversation state."""
    client = get_client()
    result = (
        client.table("conversations")
        .update({"state": state})
        .eq("id", conversation_id)
        .execute()
    )
    return result.data[0] if result.data else {}


# =============================================================================
# MESSAGE OPERATIONS
# =============================================================================


def save_message(
    conversation_id: str,
    sender_type: str,
    content: str,
    intent: str | None = None,
    domain: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Save a message to the conversation."""
    client = get_client()
    data = {
        "conversation_id": conversation_id,
        "sender_type": sender_type,
        "content": content,
    }
    if intent:
        data["intent"] = intent
    if domain:
        data["domain"] = domain
    if metadata:
        data["metadata"] = metadata

    result = client.table("messages").insert(data).execute()
    return result.data[0]


def get_conversation_history(
    conversation_id: str,
    limit: int = 20,
) -> list[dict]:
    """Get message history for a conversation."""
    client = get_client()
    result = (
        client.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return result.data


# =============================================================================
# ORDER OPERATIONS
# =============================================================================


def get_order_by_number(tenant_id: str, order_number: str) -> dict | None:
    """Get order by order number."""
    client = get_client()
    result = (
        client.table("orders")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("order_number", order_number)
        .execute()
    )
    return result.data[0] if result.data else None


def get_orders_by_email(tenant_id: str, email: str) -> list[dict]:
    """Get orders by customer email."""
    client = get_client()
    # First find users with this email
    users = (
        client.table("users")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("email", email)
        .execute()
    )
    if not users.data:
        return []

    user_ids = [u["id"] for u in users.data]
    result = (
        client.table("orders")
        .select("*")
        .eq("tenant_id", tenant_id)
        .in_("user_id", user_ids)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


# =============================================================================
# KNOWLEDGE BASE OPERATIONS (RAG)
# =============================================================================


def search_knowledge_base_simple(
    tenant_id: str,
    category: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Simple search in knowledge base without embeddings."""
    client = get_client()
    query = (
        client.table("knowledge_base")
        .select("id, category, question, answer")
        .eq("tenant_id", tenant_id)
        .eq("is_active", True)
    )
    if category:
        query = query.eq("category", category)

    result = query.limit(limit).execute()
    return result.data


def search_knowledge_base_by_category(tenant_id: str, category: str) -> list[dict]:
    """Get all knowledge base entries for a category."""
    return search_knowledge_base_simple(tenant_id, category=category, limit=50)


def get_faq_answer(tenant_id: str, category: str) -> str | None:
    """Get the first FAQ answer for a category (mock RAG for now)."""
    results = search_knowledge_base_by_category(tenant_id, category)
    if results:
        return results[0]["answer"]
    return None


# =============================================================================
# TICKET OPERATIONS
# =============================================================================


def create_ticket(
    tenant_id: str,
    type_: str = "general",
    user_id: str | None = None,
    conversation_id: str | None = None,
    order_id: str | None = None,
    subject: str | None = None,
    description: str | None = None,
) -> dict:
    """Create a support ticket."""
    client = get_client()
    data = {
        "tenant_id": tenant_id,
        "type": type_,
        "status": "open",
    }
    if user_id:
        data["user_id"] = user_id
    if conversation_id:
        data["conversation_id"] = conversation_id
    if order_id:
        data["order_id"] = order_id
    if subject:
        data["subject"] = subject
    if description:
        data["description"] = description

    result = client.table("tickets").insert(data).execute()
    return result.data[0]


# =============================================================================
# PRODUCT OPERATIONS
# =============================================================================


def get_product_by_variant(tenant_id: str, variant_id: str) -> dict | None:
    """Get product by Shopify variant ID."""
    client = get_client()
    result = (
        client.table("products")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("shopify_variant_id", variant_id)
        .eq("is_active", True)
        .execute()
    )
    return result.data[0] if result.data else None
