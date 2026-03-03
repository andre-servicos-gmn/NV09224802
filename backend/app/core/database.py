"""Supabase database client for Nouvaris Agents V2.

Uses pure REST client instead of supabase-py SDK to avoid
dependency issues with pyroaring on Windows.
"""

import os
from functools import lru_cache

from app.core.supabase_client import SupabaseClient, get_supabase


@lru_cache(maxsize=1)
def get_client() -> SupabaseClient:
    """Get a cached Supabase client instance."""
    return get_supabase()


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
    
    # Default to demo tenant
    return "73ee1a5c-1160-4a51-ba34-3fdddcd49f9e"


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
    domain: str = "store_qa",
    number: str | None = None,
) -> dict:
    """Create a new conversation with all required fields."""
    client = get_client()
    data = {
        "tenant_id": str(tenant_id),
        "session_id": str(session_id),
        "channel": channel,
        "status": "active",
        "domain": domain,
        "frustration_level": 0,
        "state": {},
    }
    if user_id:
        data["user_id"] = str(user_id)
    if number:
        data["number"] = str(number)

    result = client.table("conversations").insert(data).execute()
    return result.data[0] if result.data else {}


def get_conversation_by_session(tenant_id: str, session_id: str) -> dict | None:
    """Get conversation by session ID."""
    client = get_client()
    result = (
        client.table("conversations")
        .select("*")
        .eq("tenant_id", str(tenant_id))
        .eq("session_id", str(session_id))
        .execute()
    )
    return result.data[0] if result.data else None


def get_or_create_conversation(
    tenant_id: str,
    session_id: str,
    user_id: str | None = None,
    channel: str = "whatsapp",
    domain: str = "store_qa",
    number: str | None = None,
) -> dict:
    """Get existing conversation or create a new one with proper defaults."""
    conversation = get_conversation_by_session(tenant_id, session_id)
    if conversation:
        # Update number if provided and not already set
        if number and not conversation.get("number"):
            client = get_client()
            client.table("conversations").update({"number": number}).eq("id", conversation["id"]).execute()
            conversation["number"] = number

        # Auto-Reactivation Check
        if conversation.get("status") == "closed":
            client = get_client()
            # Reactivate
            client.table("conversations").update({
                "status": "active",
                # Optional: Reset frustration or other metrics? Keeping it simple for now as requested.
            }).eq("id", conversation["id"]).execute()
            
            # Log system message for reactivation
            save_message(
                conversation_id=conversation["id"],
                sender_type="system",
                content="Conversa reativada por nova mensagem do cliente",
                metadata={"event": "auto_reactivate"}
            )
            
            conversation["status"] = "active"

        return conversation


    return create_conversation(str(tenant_id), str(session_id), user_id, channel, domain, number)


def update_conversation_state(conversation_id: str, state: dict) -> dict:
    """
    Update conversation state.
    WARNING: This replaces the entire 'state' JSON column with the provided dict.
    Ensure you are passing the full desired state, not a partial update,
    unless you intend to wipe other fields.
    """
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
    created_at: str | None = None,
) -> dict:
    """Save a message to the conversation.
    
    Args:
        conversation_id: UUID of the conversation
        sender_type: 'user', 'agent', or 'system'
        content: Message content
        intent: Detected intent (optional)
        domain: Domain (sales, support, store_qa)
        metadata: Additional metadata dict
        created_at: Optional ISO timestamp to force specific time
    """
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
    if created_at:
        data["created_at"] = created_at

    try:
        # Save message
        result = client.table("messages").insert(data).execute()
        
        # Update conversation updated_at
        # We use a raw string "now()" which Supabase/Postgres understands, or fetch current time.
        # Ideally, use client-generated time or rely on DB default. 
        # But 'update' requires a value. 
        from datetime import datetime, timezone
        now_ts = datetime.now(timezone.utc).isoformat()
        
        client.table("conversations").update({"updated_at": now_ts}).eq("id", conversation_id).execute()
        
        return result.data[0] if result.data else {}
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[DB Error] Failed to save message: {e}")
        return {}


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
        .order("created_at", ascending=True)
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
    # For now, just get orders for the first user found
    # TODO: Support IN clause for multiple user IDs
    if user_ids:
        result = (
            client.table("orders")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("user_id", user_ids[0])
            .order("created_at", ascending=False)
            .execute()
        )
        return result.data
    return []


# =============================================================================
# KNOWLEDGE BASE OPERATIONS (RAG)
# =============================================================================


def search_knowledge_base_semantic(
    tenant_id: str,
    query: str,
    limit: int = 5,
    min_score: float = 0.3,
) -> list[dict]:
    """Semantic search in knowledge base using embeddings.
    
    Uses OpenAI embeddings and pgvector cosine similarity.
    Based on working RAG implementation pattern.
    """
    import os
    try:
        from langchain_openai import OpenAIEmbeddings
        
        # Generate embedding for the query
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        query_embedding = embeddings.embed_query(query)
        
        # Format vector as string for SQL
        vec_str = "[" + ",".join([str(x) for x in query_embedding]) + "]"
        
        if os.getenv("DEBUG"):
            print(f"[RAG] Query: {query[:50]}...")
            print(f"[RAG] Vector length: {len(query_embedding)}")
        
        # Direct SQL query with cosine similarity (like working implementation)
        client = get_client()
        result = client.rpc(
            "match_knowledge_base",
            {
                "query_embedding": vec_str,
                "p_tenant_id": tenant_id,
                "p_min_score": min_score,
                "p_limit": limit,
            }
        ).execute()
        
        if os.getenv("DEBUG"):
            print(f"[RAG] Results: {len(result.data) if result.data else 0}")
        
        if result.data:
            return result.data
        
        # Fallback to simple search if no semantic results
        if os.getenv("DEBUG"):
            print("[RAG] Falling back to simple search")
        return search_knowledge_base_simple(tenant_id, limit=limit)
        
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[Semantic Search Error] {e}")
        # Fallback to simple search on any error
        return search_knowledge_base_simple(tenant_id, limit=limit)


def search_knowledge_base_simple(
    tenant_id: str,
    category: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Simple search in knowledge base - uses metadata as store manual."""
    client = get_client()
    query = (
        client.table("knowledge_base")
        .select("id, category, metadata")
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


