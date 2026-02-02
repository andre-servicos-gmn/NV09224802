"""
Conversations API endpoints for CRM/Inbox panel.

Provides endpoints for:
- Listing conversations by tenant
- Getting messages for a conversation
- Sending messages from human panel
"""

import logging
import asyncio
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.supabase_client import get_supabase
from app.core.database import save_message
from app.core.tenancy import TenantRegistry
from app.adapters.evolution_adapter import EvolutionAdapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationOut(BaseModel):
    id: str
    tenant_id: str
    session_id: str
    channel: str
    status: str
    domain: Optional[str] = None
    frustration_level: int = 0
    push_name: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    sender_type: str
    content: str
    intent: Optional[str] = None
    domain: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: str


class SendMessageRequest(BaseModel):
    content: str


class SendMessageResponse(BaseModel):
    success: bool
    message: Optional[MessageOut] = None
    error: Optional[str] = None


@router.get("")
async def list_conversations(
    tenant_id: str = Query(..., description="Tenant UUID"),
    tab: Literal["active", "handoff", "closed"] = Query("active", description="Filter tab"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List conversations for a tenant.
    - tab=active: status IN ('active')
    - tab=handoff: status IN ('handoff', 'human_active')
    - tab=closed: status IN ('closed')
    """
    supabase = get_supabase()
    
    try:
        query = supabase.table("conversations").select(
            "id, tenant_id, session_id, channel, status, domain, frustration_level, push_name, created_at, updated_at"
        ).eq("tenant_id", tenant_id)
        
        if tab == "active":
            query = query.eq("status", "active")
        elif tab == "handoff":
            query = query.in_("status", ["handoff", "human_active"])
        elif tab == "closed":
            query = query.eq("status", "closed")
        
        result = query.order("created_at", ascending=False).limit(limit).execute()
        
        # For pagination, we need total count
        # For now, return data with has_more flag
        data = result.data or []
        
        return {
            "data": data,
            "count": len(data),
            "has_more": len(data) == limit  # Indicates there might be more
        }
    except Exception as e:
        logger.error(f"Failed to list conversations: {e}")
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get a single conversation by ID."""
    supabase = get_supabase()
    
    try:
        result = supabase.table("conversations").select("*").eq("id", conversation_id).single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return result.data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to get conversation")


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    limit: int = Query(100, ge=1, le=500),
):
    """Get messages for a conversation, ordered by created_at ASC."""
    supabase = get_supabase()
    
    try:
        result = supabase.table("messages").select(
            "id, conversation_id, sender_type, content, intent, domain, metadata, created_at"
        ).eq("conversation_id", conversation_id).order("created_at", ascending=True).limit(limit).execute()
        
        return {
            "data": result.data or [],
            "count": len(result.data) if result.data else 0
        }
    except Exception as e:
        logger.error(f"Failed to get messages: {e}")
        raise HTTPException(status_code=500, detail="Failed to get messages")


@router.post("/{conversation_id}/send-message", response_model=SendMessageResponse)
async def send_human_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message from human panel.
    - Saves message with sender_type='agent' and metadata source='human_panel'
    - Sends via WhatsApp if channel is whatsapp
    """
    supabase = get_supabase()
    
    # 1. Verify conversation exists and get details
    try:
        conv = supabase.table("conversations").select(
            "id, status, channel, tenant_id, number"
        ).eq("id", conversation_id).single().execute()
        
        if not conv.data:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        if conv.data.get("status") == "closed":
            return SendMessageResponse(
                success=False,
                error="Conversa encerrada. Não é possível enviar mensagens."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to verify conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify conversation")
    
    # 2. Save the message
    try:
        saved = save_message(
            conversation_id=conversation_id,
            sender_type="agent",
            content=request.content,
            metadata={
                "source": "human_panel",
                "sent_by": "human_agent"
            }
        )
        
        if not saved or not saved.get("id"):
            return SendMessageResponse(
                success=False,
                error="Falha ao salvar mensagem"
            )
        
        # 3. Send via WhatsApp if applicable
        channel = conv.data.get("channel")
        phone_number = conv.data.get("number")
        tenant_id = conv.data.get("tenant_id")
        
        whatsapp_sent = False
        whatsapp_error = None
        
        if channel == "whatsapp" and phone_number and tenant_id:
            try:
                # Get tenant config for WhatsApp credentials
                registry = TenantRegistry()
                tenant = registry.get(tenant_id, use_cache=True)
                
                if tenant and getattr(tenant, "whatsapp_provider", None) == "evolution":
                    adapter = EvolutionAdapter(
                        instance_url=tenant.whatsapp_instance_url,
                        api_key=tenant.whatsapp_api_key,
                        instance_name=tenant.whatsapp_instance_name or "default",
                    )
                    
                    # Send the message
                    result = await adapter.send_text_message(
                        to=phone_number,
                        text=request.content
                    )
                    
                    await adapter.close()
                    
                    if result.success:
                        whatsapp_sent = True
                        logger.info(f"✅ WhatsApp message sent to {phone_number}")
                    else:
                        whatsapp_error = result.error
                        logger.error(f"❌ WhatsApp send failed: {result.error}")
                else:
                    logger.warning(f"WhatsApp not configured for tenant {tenant_id}")
            except Exception as e:
                whatsapp_error = str(e)
                logger.error(f"❌ WhatsApp send error: {e}")
        
        return SendMessageResponse(
            success=True,
            message=MessageOut(
                id=saved.get("id"),
                conversation_id=conversation_id,
                sender_type="agent",
                content=request.content,
                intent=None,
                domain=None,
                metadata={
                    "source": "human_panel",
                    "whatsapp_sent": whatsapp_sent,
                    "whatsapp_error": whatsapp_error
                },
                created_at=saved.get("created_at", "")
            )
        )
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        return SendMessageResponse(
            success=False,
            error="Erro ao enviar mensagem"
        )


@router.post("/{conversation_id}/close")
async def close_conversation(conversation_id: str):
    """
    Close a handoff - return conversation to active status.
    Agent can resume responding after this.
    """
    supabase = get_supabase()
    
    try:
        # Update status back to active
        supabase.table("conversations").update({
            "status": "active"
        }).eq("id", conversation_id).execute()
        
        # Save system message
        save_message(
            conversation_id=conversation_id,
            sender_type="system",
            content="Handoff finalizado pelo atendente",
            metadata={
                "event": "handoff_completed",
                "source": "human_panel"
            }
        )
        
        return {"success": True, "new_status": "active"}
    except Exception as e:
        logger.error(f"Failed to close handoff: {e}")
        raise HTTPException(status_code=500, detail="Failed to close handoff")


@router.post("/{conversation_id}/pause")
async def pause_agent(conversation_id: str):
    """
    Pause the AI agent for this conversation (manual handoff).
    Sets status to 'human_active' so only humans can respond.
    """
    supabase = get_supabase()
    
    try:
        # Update status to human_active
        supabase.table("conversations").update({
            "status": "human_active"
        }).eq("id", conversation_id).execute()
        
        # Save system message
        save_message(
            conversation_id=conversation_id,
            sender_type="system",
            content="Agente pausado manualmente",
            metadata={
                "event": "agent_paused",
                "source": "human_panel"
            }
        )
        
        return {"success": True, "new_status": "human_active"}
    except Exception as e:
        logger.error(f"Failed to pause agent: {e}")
        raise HTTPException(status_code=500, detail="Failed to pause agent")
