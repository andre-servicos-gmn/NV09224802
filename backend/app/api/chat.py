
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.router import apply_entities_to_state, classify
from app.core.state import ConversationState
from app.core.tenancy import TenantRegistry
from app.core.supabase_client import get_supabase
from app.core.database import get_or_create_conversation, save_message
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
    Persists state in Supabase conversations.state (jsonb) column.
    All updates are done by conversation UUID (id), never by session_id.
    """
    tenant_id = request.tenant_id
    session_id = request.session_id or uuid.uuid4().hex
    
    # 1. Get Tenant
    registry = TenantRegistry()
    try:
        tenant = registry.get(tenant_id)
    except (KeyError, ValueError):
        try:
             tenant = registry.get("demo")
        except (KeyError, ValueError):
             raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

    supabase = get_supabase()
    tenant_uuid = tenant.uuid or tenant.tenant_id

    # 1.1 Check agent status (unless it's playground)
    if not request.is_playground:
        try:
            tenant_data = supabase.table("tenants").select("active").eq("id", tenant_uuid).execute()
            if tenant_data.data and tenant_data.data[0].get("active") is False:
                return ChatResponse(
                    response="O agente está temporariamente desativado. Por favor, tente novamente mais tarde.",
                    session_id=session_id,
                    action="agent_disabled"
                )
        except Exception as e:
            logger.warning(f"Failed to check tenant status: {e}")

    # 2. Get or create conversation (single source of truth)
    conversation = get_or_create_conversation(
        tenant_id=tenant_uuid,
        session_id=session_id,
        channel="web"
    )
    conversation_id = conversation.get("id")
    
    if not conversation_id:
        logger.error("Failed to get or create conversation")
        raise HTTPException(status_code=500, detail="Failed to initialize conversation")

    # 3. Load or Initialize State from conversations.state
    state = None
    existing_state = conversation.get("state", {})
    
    if existing_state and isinstance(existing_state, dict) and existing_state:
        try:
            state = ConversationState(**existing_state)
            state.tenant_id = tenant.tenant_id
            state.session_id = session_id
            if request.personality_id:
                state.personality_id = request.personality_id
        except Exception as e:
            logger.warning(f"Failed to reconstruct state from DB: {e}. Starting fresh.")

    if not state:
        state = ConversationState(
            tenant_id=tenant.tenant_id, 
            session_id=session_id,
            personality_id=request.personality_id or "professional"
        )

    # 4. Process Message
    message = request.message
    state.last_user_message = message
    state.add_to_history("user", message)

    # 4.1 Save user message
    try:
        save_message(
            conversation_id=conversation_id,
            sender_type="user",
            content=message,
            domain=state.domain
        )
    except Exception as e:
        logger.warning(f"Failed to save user message: {e}")

    # 4.2 Classification
    context = {
        "tenant_id": state.tenant_id,
        "session_id": state.session_id,
        "last_domain": state.domain,
        "last_intent": state.intent,
        "store_name": tenant.name,
    }
    
    decision = classify(message, context=context, use_llm=True)
    
    state.set_intent(decision.intent)
    state.domain = decision.domain
    apply_entities_to_state(state, decision.entities)
    state.sentiment_level = decision.sentiment_level
    state.needs_handoff = decision.needs_handoff

    # 5. Run Graph
    state = run_main_graph(state, tenant)
    state.add_to_history("agent", state.last_bot_message or "")

    # 5.1 Save agent message
    try:
        if state.last_bot_message:
            save_message(
                conversation_id=conversation_id,
                sender_type="agent",
                content=state.last_bot_message,
                intent=state.intent,
                domain=state.domain,
                metadata={
                    "action": state.last_action,
                    "strategy": state.last_strategy,
                }
            )
    except Exception as e:
        logger.warning(f"Failed to save agent message: {e}")

    # 5.2 Save handoff system event if needed
    if state.needs_handoff:
        try:
            save_message(
                conversation_id=conversation_id,
                sender_type="system",
                content=f"Handoff requested: {decision.handoff_reason or 'escalation'}",
                metadata={"event": "handoff"}
            )
        except Exception as e:
            logger.warning(f"Failed to save handoff message: {e}")

    # 6. Persist State to conversations.state (by UUID, not session_id)
    try:
        supabase.table("conversations").update({
            "state": state.model_dump(mode='json'),
            "domain": state.domain,
            "frustration_level": state.frustration_level,
            "status": "handoff" if state.needs_handoff else "active"
        }).eq("id", conversation_id).execute()
    except Exception as e:
        logger.error(f"Failed to persist state: {e}")

    return {
        "response": state.last_bot_message or "...",
        "session_id": session_id,
        "action": state.last_action
    }
