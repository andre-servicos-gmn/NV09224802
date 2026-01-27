
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.router import apply_entities_to_state, classify
from app.core.state import ConversationState
from app.core.tenancy import TenantRegistry
from app.core.supabase_client import get_supabase
from app.graphs.main_graph import run_main_graph

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    tenant_id: Optional[str] = "73ee1a5c-1160-4a51-ba34-3fdddcd49f9e" # Default demo tenant
    personality_id: Optional[str] = "professional"
    is_playground: bool = False  # If True, bypasses agent status check

class ChatResponse(BaseModel):
    response: str
    session_id: str
    action: Optional[str] = None

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Endpoint for chat interactions.
    Persists state in Supabase conversations table.
    """
    tenant_id = request.tenant_id
    session_id = request.session_id or uuid.uuid4().hex
    
    # 1. Get Tenant
    registry = TenantRegistry()
    try:
        tenant = registry.get(tenant_id)
    except (KeyError, ValueError):
        # Fallback for demo if not found in registry (should be there if seeded correctly)
        # But for safety, try to load 'demo' alias if UUID fails
        try:
             tenant = registry.get("demo")
        except (KeyError, ValueError):
             raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

    # Get Supabase client early for status check and state management
    supabase = get_supabase()

    # 1.1 Check agent status (unless it's playground)
    if not request.is_playground:
        try:
            tenant_uuid = tenant.uuid or tenant.tenant_id
            tenant_data = supabase.table("tenants").select("active").eq("id", tenant_uuid).execute()
            if tenant_data.data and tenant_data.data[0].get("active") is False:
                return ChatResponse(
                    response="O agente está temporariamente desativado. Por favor, tente novamente mais tarde.",
                    session_id=session_id,
                    action="agent_disabled"
                )
        except Exception as e:
            logger.warning(f"Failed to check tenant status: {e}")

    # 2. Load or Initialize State
    state = None
    
    # Try to fetch existing conversation state
    try:
        res = supabase.table("conversations").select("id, metadata").eq("session_id", session_id).single().execute()
        if res.data:
            metadata = res.data[0].get("metadata", {})
            if metadata:
                # Reconstruct state from metadata
                # We need to ensure metadata matches model fields
                try:
                    state = ConversationState(**metadata)
                    # Update transient fields just in case
                    state.tenant_id = tenant.tenant_id
                    state.session_id = session_id
                    # Update personality if changed
                    if request.personality_id:
                        state.personality_id = request.personality_id
                except Exception as e:
                    logger.warning(f"Failed to reconstruction state from DB: {e}. Starting fresh.")
    except Exception as e:
        logger.warning(f"Error fetching conversation: {e}")

    if not state:
        state = ConversationState(
            tenant_id=tenant.tenant_id, 
            session_id=session_id,
            personality_id=request.personality_id or "professional"
        )
        # Create conversation record if not exists
        try:
            supabase.table("conversations").insert({
                "tenant_id": tenant.uuid or tenant.tenant_id,
                "session_id": session_id,
                "channel": "web",
                "status": "active",
                "metadata": state.model_dump(mode='json')
            }).execute()
        except Exception as e:
            logger.error(f"Failed to create conversation record: {e}")

    # 3. Process Message
    message = request.message
    state.last_user_message = message
    state.add_to_history("user", message)

    # 3.1 Classification
    context = {
        "tenant_id": state.tenant_id,
        "session_id": state.session_id,
        "last_domain": state.domain,
        "last_intent": state.intent,
        "store_name": tenant.name,
    }
    
    # Run classification
    decision = classify(message, context=context, use_llm=True)
    
    state.set_intent(decision.intent)
    state.domain = decision.domain
    apply_entities_to_state(state, decision.entities)
    state.sentiment_level = decision.sentiment_level
    state.needs_handoff = decision.needs_handoff
    
    if decision.needs_handoff:
         # Update status in DB
         try:
             supabase.table("conversations").update({"status": "handoff"}).eq("session_id", session_id).execute()
         except Exception as e:
             logger.error(f"Failed to update handoff status: {e}")

    # 4. Run Graph
    state = run_main_graph(state, tenant)
    
    # Add bot response to history
    state.add_to_history("agent", state.last_bot_message or "")

    # 5. Persist State
    try:
        supabase.table("conversations").update({
            "metadata": state.model_dump(mode='json')
        }).eq("session_id", session_id).execute()
    except Exception as e:
        logger.error(f"Failed to persist state: {e}")

    return {
        "response": state.last_bot_message or "...",
        "session_id": session_id,
        "action": state.last_action
    }
