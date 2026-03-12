"""
Chat API endpoint with human handoff support.

Key behaviors:
- Always saves user messages (even when AI is blocked)
- Blocks AI when conversation status != 'active'
- Triggers handoff on: frustration >= 3, refund requests, or needs_handoff
"""

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
from app.core.session_store_v2 import get_session, save_session
from app.core.constants import INTENT_RETURN_EXCHANGE
from app.graphs.main_graph import run_main_graph

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Handoff configuration
FRUSTRATION_THRESHOLD = 3
HANDOFF_RESPONSE = "Entendi. Um atendente humano vai assumir essa conversa em breve. Por favor, aguarde."
BLOCKED_RESPONSES = {
    "handoff": "Um atendente humano assumirá em breve. Por favor, aguarde.",
    "human_active": "",  # Human is responding, AI stays silent
    "closed": "",  # Conversation closed, no response
}


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    tenant_id: Optional[str] = "73ee1a5c-1160-4a51-ba34-3fdddcd49f9e"
    personality_id: Optional[str] = "professional"
    is_playground: bool = False


class ChatResponse(BaseModel):
    response: str
    session_id: str
    action: Optional[str] = None
    status: Optional[str] = None


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Chat endpoint with human handoff support.
    
    Flow:
    1. Get or create conversation
    2. Always save user message
    3. If status != 'active': return blocked response (no AI processing)
    4. If active: run classification and graph
    5. Check for handoff triggers (frustration, refund, needs_handoff)
    6. Save agent response and persist state
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

    # 1.1 Check agent status (unless playground)
    if not request.is_playground:
        try:
            tenant_data = supabase.table("tenants").select("active").eq("id", tenant_uuid).execute()
            if tenant_data.data and tenant_data.data[0].get("active") is False:
                return ChatResponse(
                    response="O agente está temporariamente desativado. Por favor, tente novamente mais tarde.",
                    session_id=session_id,
                    action="agent_disabled",
                    status="disabled"
                )
        except Exception as e:
            logger.warning(f"Failed to check tenant status: {e}")

    # 2. Get or create conversation
    conversation = get_or_create_conversation(
        tenant_id=tenant_uuid,
        session_id=session_id,
        channel="web"
    )
    conversation_id = conversation.get("id")
    conv_status = conversation.get("status", "active")
    
    if not conversation_id:
        logger.error("Failed to get or create conversation")
        raise HTTPException(status_code=500, detail="Failed to initialize conversation")

    # 3. Always save user message first (even if AI is blocked)
    message = request.message
    try:
        save_message(
            conversation_id=conversation_id,
            sender_type="user",
            content=message,
            metadata={"blocked": conv_status != "active"}
        )
    except Exception as e:
        logger.warning(f"Failed to save user message: {e}")

    # 4. Check if AI should be blocked
    if conv_status in ("handoff", "human_active", "closed"):
        blocked_response = BLOCKED_RESPONSES.get(conv_status, "")
        return ChatResponse(
            response=blocked_response,
            session_id=session_id,
            action=f"blocked_{conv_status}",
            status=conv_status
        )

    # 5. Load or Initialize State via session_store_v2 (Redis L1 + Supabase L2)
    state = get_session(tenant_uuid, session_id)
    
    if state:
        state.tenant_id = tenant.tenant_id
        state.session_id = session_id
        if request.personality_id:
            state.personality_id = request.personality_id
    else:
        state = ConversationState(
            tenant_id=tenant.tenant_id,
            session_id=session_id,
            personality_id=request.personality_id or "professional"
        )

    # 6. Process message
    state.last_user_message = message
    state.add_to_history("user", message)

    # 6.1 Classification
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

    # 7. Check handoff triggers BEFORE running graph
    handoff_reason = None
    
    if decision.needs_handoff:
        handoff_reason = decision.handoff_reason or "escalation"
    elif decision.intent == INTENT_RETURN_EXCHANGE:
        handoff_reason = "refund_request"
        state.needs_handoff = True
    elif state.frustration_level >= FRUSTRATION_THRESHOLD:
        handoff_reason = "high_frustration"
        state.needs_handoff = True

    # 8. If handoff triggered, skip graph and return handoff response
    if state.needs_handoff:
        try:
            # Update conversation status via unified store
            save_session(tenant_uuid, session_id, state)
            supabase.table("conversations").update({
                "status": "handoff",
            }).eq("id", conversation_id).execute()
            
            # Save system event
            save_message(
                conversation_id=conversation_id,
                sender_type="system",
                content=f"Handoff ativado: {handoff_reason}",
                metadata={
                    "event": "handoff",
                    "reason": handoff_reason,
                    "frustration_level": state.frustration_level,
                    "intent": decision.intent,
                }
            )
            
            # Save agent message (the handoff notification)
            save_message(
                conversation_id=conversation_id,
                sender_type="agent",
                content=HANDOFF_RESPONSE,
                intent="handoff",
                domain=state.domain,
            )
        except Exception as e:
            logger.error(f"Failed to process handoff: {e}")
        
        return ChatResponse(
            response=HANDOFF_RESPONSE,
            session_id=session_id,
            action="handoff_triggered",
            status="handoff"
        )

    # 9. Run Graph (normal AI response)
    state = run_main_graph(state, tenant)
    state.add_to_history("agent", state.last_bot_message or "")

    # 9.1 Save agent message
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

    # 10. Persist State via unified session store (Redis L1 + Supabase L2)
    try:
        save_session(tenant_uuid, session_id, state)
        supabase.table("conversations").update({
            "status": "active"
        }).eq("id", conversation_id).execute()
    except Exception as e:
        logger.error(f"Failed to persist state: {e}")

    return ChatResponse(
        response=state.last_bot_message or "...",
        session_id=session_id,
        action=state.last_action,
        status="active"
    )
