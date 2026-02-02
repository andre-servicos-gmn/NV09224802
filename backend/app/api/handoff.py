"""
Handoff API endpoints for human agent takeover.

Provides endpoints for human agents to:
- Claim a conversation (status -> human_active)
- Close a conversation (status -> closed)
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.supabase_client import get_supabase
from app.core.database import save_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/handoff", tags=["handoff"])


class ClaimRequest(BaseModel):
    conversation_id: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None


class CloseRequest(BaseModel):
    conversation_id: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    resolution: Optional[str] = None


class HandoffResponse(BaseModel):
    success: bool
    conversation_id: str
    new_status: str
    message: str


@router.post("/claim", response_model=HandoffResponse)
async def claim_conversation(request: ClaimRequest):
    """
    Human agent claims a conversation.
    Sets status to 'human_active' and logs system event.
    """
    supabase = get_supabase()
    conversation_id = request.conversation_id
    
    # 1. Verify conversation exists and is in handoff status
    try:
        conv = supabase.table("conversations").select("id, status").eq("id", conversation_id).single().execute()
        if not conv.data:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        current_status = conv.data.get("status")
        if current_status not in ("handoff", "active"):
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot claim conversation with status '{current_status}'"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch conversation")
    
    # 2. Update status to human_active
    try:
        supabase.table("conversations").update({
            "status": "human_active"
        }).eq("id", conversation_id).execute()
    except Exception as e:
        logger.error(f"Failed to update conversation status: {e}")
        raise HTTPException(status_code=500, detail="Failed to claim conversation")
    
    # 3. Save system event message
    try:
        agent_info = request.agent_name or request.agent_id or "Atendente"
        save_message(
            conversation_id=conversation_id,
            sender_type="system",
            content=f"Conversa assumida por {agent_info}",
            metadata={
                "event": "claim",
                "agent_id": request.agent_id,
                "agent_name": request.agent_name,
            }
        )
    except Exception as e:
        logger.warning(f"Failed to save claim event: {e}")
    
    return HandoffResponse(
        success=True,
        conversation_id=conversation_id,
        new_status="human_active",
        message=f"Conversa assumida com sucesso"
    )


@router.post("/close", response_model=HandoffResponse)
async def close_conversation(request: CloseRequest):
    """
    Human agent closes a conversation.
    Sets status to 'closed' and logs system event with resolution.
    """
    supabase = get_supabase()
    conversation_id = request.conversation_id
    
    # 1. Verify conversation exists
    try:
        conv = supabase.table("conversations").select("id, status").eq("id", conversation_id).single().execute()
        if not conv.data:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        current_status = conv.data.get("status")
        if current_status == "closed":
            return HandoffResponse(
                success=True,
                conversation_id=conversation_id,
                new_status="closed",
                message="Conversa já estava encerrada"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch conversation")
    
    # 2. Update status to closed and RESET state
    try:
        # Fetch current state to preserve some long-term memory if needed
        # But user requested "resetar state". We will keep critical context like 'facts'/history 
        # but wipe transaction data (cart, intent, etc).
        
        # Reset state dict
        reset_state = {
            "intent": "general",
            "cart_items": [],
            "selected_products": [],
            "selected_product_id": None,
            "selected_variant_id": None,
            "quantity": 1,
            "order_id": None,
            "ticket_opened": False,
            "last_action": None,
            "last_strategy": None,
            "frustration_level": 0,
            "needs_handoff": False,
            "handoff_reason": None,
            # Maintain long-term memory
            "conversation_history": [],  # Or keep last few? Usually reset is better for fresh start
            "conversation_summary": conv.data.get("state", {}).get("conversation_summary"),
            "facts": conv.data.get("state", {}).get("facts", {})
        }

        supabase.table("conversations").update({
            "status": "closed",
            "state": reset_state
        }).eq("id", conversation_id).execute()
    except Exception as e:
        logger.error(f"Failed to update conversation status: {e}")
        raise HTTPException(status_code=500, detail="Failed to close conversation")
    
    # 3. Save system event message
    try:
        agent_info = request.agent_name or request.agent_id or "Atendente"
        save_message(
            conversation_id=conversation_id,
            sender_type="system",
            content=f"Conversa encerrada por {agent_info}" + (f": {request.resolution}" if request.resolution else ""),
            metadata={
                "event": "close",
                "agent_id": request.agent_id,
                "agent_name": request.agent_name,
                "resolution": request.resolution,
            }
        )
    except Exception as e:
        logger.warning(f"Failed to save close event: {e}")
    
    return HandoffResponse(
        success=True,
        conversation_id=conversation_id,
        new_status="closed",
        message="Conversa encerrada com sucesso"
    )


@router.post("/reopen", response_model=HandoffResponse)
async def reopen_conversation(request: ClaimRequest):
    """
    Reopen a closed conversation (set status back to active).
    """
    supabase = get_supabase()
    conversation_id = request.conversation_id
    
    try:
        supabase.table("conversations").update({
            "status": "active"
        }).eq("id", conversation_id).execute()
        
        save_message(
            conversation_id=conversation_id,
            sender_type="system",
            content="Conversa reaberta",
            metadata={"event": "reopen", "agent_id": request.agent_id}
        )
    except Exception as e:
        logger.error(f"Failed to reopen conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to reopen conversation")
    
    return HandoffResponse(
        success=True,
        conversation_id=conversation_id,
        new_status="active",
        message="Conversa reaberta com sucesso"
    )
