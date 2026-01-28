"""Evolution API adapter for WhatsApp integration.
Implements the WhatsAppAdapterBase for Evolution API.
Documentation: https://doc.evolution-api.com/
"""
import logging
from typing import Optional
import httpx
from fastapi import Request
from app.adapters.whatsapp_base import (
    WhatsAppAdapterBase,
    WhatsAppMessage,
    WhatsAppSendResult,
)

logger = logging.getLogger(__name__)

# Cache para mapear LID (Linked Device IDs) para números reais
# Problema: WhatsApp Web/Desktop usa LID em vez do número real
LID_PHONE_CACHE: dict[str, str] = {}
PUSHNAME_PHONE_CACHE: dict[str, str] = {}


class EvolutionAdapter(WhatsAppAdapterBase):
    """Evolution API implementation of WhatsApp adapter."""
    
    def __init__(
        self,
        instance_url: str,
        api_key: str,
        instance_name: str = "default",
    ):
        super().__init__(instance_url, api_key, instance_name)
        self._client = httpx.AsyncClient(
            base_url=self.instance_url,
            headers={
                "apikey": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
    
    async def validate_webhook(self, request: Request) -> bool:
        """Validate incoming webhook request.
        
        Evolution API currently does not require HMAC validation by default.
        """
        return True
    
    def parse_incoming_message(self, payload: dict) -> Optional[WhatsAppMessage]:
        """Parse Evolution API MESSAGES_UPSERT event into standardized message.
        
        Evolution API payload structure for MESSAGES_UPSERT:
        {
            "event": "messages.upsert",
            "instance": "instance_name",
            "data": {
                "key": {
                    "remoteJid": "5511999999999@s.whatsapp.net",
                    "fromMe": false,
                    "id": "message_id"
                },
                "pushName": "John",
                "message": {
                    "conversation": "Hello"  # or "extendedTextMessage": {"text": "..."}
                },
                "messageTimestamp": 1234567890
            }
        }
        """
        event = payload.get("event", "")
        
        # Only process message events
        if event not in ("messages.upsert", "MESSAGES_UPSERT"):
            return None
        
        data = payload.get("data", {})
        key = data.get("key", {})
        message_content = data.get("message", {})
        
        # Skip messages sent by us (fromMe=true)
        is_from_me = key.get("fromMe", False)
        if str(is_from_me).lower() == "true" or is_from_me is True:
            logger.info(f"Ignoring message fromMe={is_from_me}")
            return None
        
        remote_jid = key.get("remoteJid", "")
        
        # Ignore status updates
        if "status@broadcast" in remote_jid:
            return None
        
        push_name = data.get("pushName", "")
        target_jid = remote_jid
        
        # Handle LID vs Phone number resolution
        if "@s.whatsapp.net" in remote_jid:
            phone_jid = remote_jid
            if push_name:
                PUSHNAME_PHONE_CACHE[push_name] = phone_jid
            target_jid = phone_jid
        elif "@lid" in remote_jid:
            # Try to resolve LID to real phone number
            if remote_jid in LID_PHONE_CACHE:
                target_jid = LID_PHONE_CACHE[remote_jid]
            elif push_name and push_name in PUSHNAME_PHONE_CACHE:
                target_jid = PUSHNAME_PHONE_CACHE[push_name]
                LID_PHONE_CACHE[remote_jid] = target_jid
            else:
                logger.warning(f"Cannot resolve LID {remote_jid}")
                target_jid = remote_jid
        
        # Extract phone number from JID
        if "@lid" in target_jid:
            from_number = target_jid
        else:
            from_number = target_jid.split("@")[0] if "@" in target_jid else target_jid
        
        self._resolved_session_id = from_number
        
        # Extract text content
        text = ""
        if "conversation" in message_content:
            text = message_content["conversation"]
        elif "extendedTextMessage" in message_content:
            text = message_content["extendedTextMessage"].get("text", "")
        elif "imageMessage" in message_content:
            text = "[IMAGE]"
        elif "audioMessage" in message_content:
            text = "[AUDIO]"
        elif "videoMessage" in message_content:
            text = "[VIDEO]"
        elif "documentMessage" in message_content:
            text = "[DOCUMENT]"
        
        if not text:
            return None
        
        return WhatsAppMessage(
            message_id=key.get("id", ""),
            from_number=from_number,
            to_number=self.instance_name,
            text=text,
            timestamp=data.get("messageTimestamp", 0),
            is_group="@g.us" in remote_jid,
            group_id=remote_jid if "@g.us" in remote_jid else None,
            raw_payload=payload,
        )
    
    def get_session_id(self) -> str | None:
        """Return the normalized session ID (real phone number when possible)."""
        return getattr(self, "_resolved_session_id", None)
    
    async def send_text_message(self, to: str, text: str) -> WhatsAppSendResult:
        """Send a text message via Evolution API."""
        try:
            if "@" in to:
                number = to
            else:
                number = to.replace("+", "").replace("-", "").replace(" ", "")
            
            response = await self._client.post(
                f"/message/sendText/{self.instance_name}",
                json={
                    "number": number,
                    "text": text,
                },
            )
            
            if response.status_code in (200, 201):
                data = response.json()
                return WhatsAppSendResult(
                    success=True,
                    message_id=data.get("key", {}).get("id"),
                )
            else:
                logger.error(f"Evolution API error: {response.status_code} - {response.text}")
                return WhatsAppSendResult(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}",
                )
                
        except Exception as e:
            logger.exception(f"Error sending message via Evolution API: {e}")
            return WhatsAppSendResult(success=False, error=str(e))
    
    async def send_media_message(
        self,
        to: str,
        media_url: str,
        media_type: str,
        caption: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send a media message via Evolution API."""
        try:
            if "@" in to:
                number = to
            else:
                number = to.replace("+", "").replace("-", "").replace(" ", "")
            
            endpoint_map = {
                "image": "sendMedia",
                "audio": "sendWhatsAppAudio",
                "video": "sendMedia",
                "document": "sendMedia",
            }
            endpoint = endpoint_map.get(media_type, "sendMedia")
            
            response = await self._client.post(
                f"/message/{endpoint}/{self.instance_name}",
                json={
                    "number": number,
                    "mediatype": media_type,
                    "media": media_url,
                    "caption": caption or "",
                },
            )
            
            if response.status_code in (200, 201):
                data = response.json()
                return WhatsAppSendResult(
                    success=True,
                    message_id=data.get("key", {}).get("id"),
                )
            else:
                return WhatsAppSendResult(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}",
                )
                
        except Exception as e:
            logger.exception(f"Error sending media via Evolution API: {e}")
            return WhatsAppSendResult(success=False, error=str(e))
    
    async def mark_as_read(self, message_id: str) -> bool:
        """Mark a message as read via Evolution API."""
        try:
            response = await self._client.post(
                f"/chat/markMessageAsRead/{self.instance_name}",
                json={"id": message_id},
            )
            return response.status_code in (200, 201)
        except Exception:
            return False
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
