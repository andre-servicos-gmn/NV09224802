"""Evolution API adapter for WhatsApp integration.

Simplified version with proper LID (Linked Device ID) handling.
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
            headers={"apikey": self.api_key.strip(), "Content-Type": "application/json"},
            timeout=30.0,
        )
        self._session_phone: Optional[str] = None
    
    async def validate_webhook(self, request: Request) -> bool:
        """Evolution API does not require HMAC validation by default."""
        return True
    
    def parse_incoming_message(self, payload: dict) -> Optional[WhatsAppMessage]:
        """Parse Evolution API MESSAGES_UPSERT event into standardized message."""
        event = payload.get("event", "")
        if event not in ("messages.upsert", "MESSAGES_UPSERT"):
            print(f"DEBUG: Ignoring event {event}", flush=True)
            return None
        
        # DEBUG RAW PAYLOAD
        import json
        print(f"DEBUG: Incoming Webhook Payload: {json.dumps(payload)}", flush=True)
        
        data = payload.get("data", {})
        key = data.get("key", {})
        message_content = data.get("message", {})
        
        # Skip messages sent by us
        logger.info(f"🔍 Checking message source. Key: {key}")
        if key.get("fromMe") in (True, "true"):
            logger.info("⚠️ Skipping message identified as fromMe=True")
            return None
        
        remote_jid = key.get("remoteJid", "")
        if "status@broadcast" in remote_jid:
            return None
        
        # --- PHONE NUMBER EXTRACTION ---
        # Priority: senderPn > remoteJidAlt > extract from remoteJid
        phone = None
        
        # 1. senderPn (Best for LID resolution)
        sender_pn = data.get("senderPn") or payload.get("senderPn")
        if sender_pn:
            phone = sender_pn
            logger.info(f"📱 Phone from senderPn: {phone}")
        
        # 2. remoteJidAlt (Alternative JID field)
        if not phone:
            alt_jid = key.get("remoteJidAlt") or data.get("remoteJidAlt")
            if alt_jid and "@s.whatsapp.net" in alt_jid:
                phone = alt_jid.replace("@s.whatsapp.net", "")
                logger.info(f"📱 Phone from remoteJidAlt: {phone}")
        
        # 3. Extract from remoteJid (only if not LID)
        if not phone and "@s.whatsapp.net" in remote_jid:
            phone = remote_jid.replace("@s.whatsapp.net", "")
            logger.info(f"📱 Phone from remoteJid: {phone}")
        
        # 4. LID fallback - use it directly (will fail on send, but at least logs)
        if not phone and "@lid" in remote_jid:
            phone = remote_jid
            logger.warning(f"⚠️ Using LID as fallback (may fail on send): {phone}")
        
        if not phone:
            logger.error("❌ Could not extract phone number from payload")
            return None
        
        self._session_phone = phone
        
        # --- TEXT EXTRACTION ---
        text = message_content.get("conversation")
        if not text:
            text = message_content.get("extendedTextMessage", {}).get("text")
        if not text:
            # Check for media messages
            media_types = ["imageMessage", "audioMessage", "videoMessage", "documentMessage"]
            if any(k in message_content for k in media_types):
                text = "[MEDIA]"
        
        if not text:
            logger.debug("No text content in message")
            return None
        
        return WhatsAppMessage(
            message_id=key.get("id", ""),
            from_number=phone,
            to_number=phone,  # Reply destination
            text=text,
            timestamp=data.get("messageTimestamp", 0),
            is_group="@g.us" in remote_jid,
            group_id=remote_jid if "@g.us" in remote_jid else None,
            raw_payload=payload,
        )
    
    def get_session_id(self) -> str | None:
        """Return the phone number for session tracking."""
        return self._session_phone
    
    async def send_text_message(self, to: str, text: str) -> WhatsAppSendResult:
        """Send a text message via Evolution API."""
        try:
            # Clean phone number
            # If addressing a LID (Linked Device), force fallback to specific mobile number
            if "@lid" in to or to.endswith("lid"):
                 logger.warning(f"⚠️ Redirecting LID {to} to fallback mobile 5511954501500")
                 number = "5511954501500"
            else:
                 number = to.replace("@s.whatsapp.net", "").replace("+", "").replace("-", "").replace(" ", "")
            
            logger.info(f"📤 Sending to: {number}")
            
            response = await self._client.post(
                f"/message/sendText/{self.instance_name}",
                json={"number": number, "text": text},
            )
            
            if response.status_code in (200, 201):
                data = response.json()
                logger.info(f"✅ Sent! ID: {data.get('key', {}).get('id')}")
                return WhatsAppSendResult(
                    success=True,
                    message_id=data.get("key", {}).get("id"),
                )
            else:
                logger.error(f"❌ Send failed: {response.status_code} - {response.text}")
                return WhatsAppSendResult(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}",
                )
                
        except Exception as e:
            logger.exception(f"❌ Error sending: {e}")
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
            if "@lid" in to or to.endswith("lid"):
                 logger.warning(f"⚠️ Redirecting LID {to} to fallback mobile 5511954501500")
                 number = "5511954501500"
            else:
                 number = to.replace("@s.whatsapp.net", "").replace("+", "").replace("-", "").replace(" ", "")
            
            response = await self._client.post(
                f"/message/sendMedia/{self.instance_name}",
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
            logger.exception(f"Error sending media: {e}")
            return WhatsAppSendResult(success=False, error=str(e))
    
    async def mark_as_read(self, message_id: str) -> bool:
        """Mark a message as read."""
        try:
            response = await self._client.post(
                f"/chat/markMessageAsRead/{self.instance_name}",
                json={"readMessages": [message_id]},
            )
            return response.status_code in (200, 201)
        except Exception:
            return False
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
