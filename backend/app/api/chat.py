"""Endpoint REST para o playground / chat web do Nouva.

Camada fina sobre turn_processor.process_message(). Toda a lógica de
orquestração de turno (tenant, graph LangGraph, persistência via
PostgresSaver) vive no turn_processor + app/graphs. Aqui só fazemos
a tradução HTTP ↔ ProcessResult.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.turn_processor import process_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Tenant default — mantido pra compat com frontend que não envia tenant_id.
_DEFAULT_TENANT_ID = "73ee1a5c-1160-4a51-ba34-3fdddcd49f9e"


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    tenant_id: Optional[str] = _DEFAULT_TENANT_ID
    personality_id: Optional[str] = "professional"  # reservado p/ Fase 3
    is_playground: bool = False


class ChatResponse(BaseModel):
    response: str
    session_id: str
    action: Optional[str] = None
    status: Optional[str] = None


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """Processa uma mensagem do playground/chat web.

    Sempre retorna HTTP 200; erros são graciosos via bot_message.
    """
    session_id = request.session_id or uuid.uuid4().hex
    tenant_id = request.tenant_id or _DEFAULT_TENANT_ID

    try:
        result = process_message(
            tenant_id=tenant_id,
            session_id=session_id,
            user_message=request.message,
            channel="web",
            is_playground=request.is_playground,
        )
    except Exception as e:
        # Defesa adicional: process_message já deveria capturar tudo.
        logger.exception(
            f"Unexpected error in /chat for session {session_id}: {e}"
        )
        return ChatResponse(
            response="Desculpe, tive um problema técnico. Pode repetir?",
            session_id=session_id,
            action="error",
            status="error",
        )

    return ChatResponse(
        response=result.bot_message or "",
        session_id=result.session_id,
        action=result.action,
        status=result.status,
    )
