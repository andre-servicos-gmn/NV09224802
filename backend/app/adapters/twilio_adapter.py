"""Twilio API adapter for WhatsApp integration.

Documentation: https://www.twilio.com/docs/whatsapp
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


class TwilioAdapter(WhatsAppAdapterBase):
    """Twilio API implementation of WhatsApp adapter."""
    
    def __init__(
        self,
        instance_url: str,  # In Twilio, this is the Twilio Phone Number
        api_key: str,       # In Twilio, this is the Auth Token
        instance_name: str, # In Twilio, this is the Account SID
    ):
        super().__init__(instance_url, api_key, instance_name)
        
        self.twilio_phone = instance_url
        self.auth_token = api_key
        self.account_sid = instance_name
        
        # Twilio API URIs use the Account SID
        self._base_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}"
        
        # httpx Basic Auth (Account SID: Auth Token)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            auth=(self.account_sid, self.auth_token),
            timeout=30.0,
        )
        self._session_phone: Optional[str] = None
    
    async def validate_webhook(self, request: Request) -> bool:
        """Validate Twilio webhook request."""
        # For a full production app, you would use twilio.request_validator here
        # For now, we trust the incoming webhook if it parses correctly.
        return True
    
    def parse_incoming_message(self, payload: dict) -> Optional[WhatsAppMessage]:
        """Parse Twilio webhook form payload into standardized message."""
        # Twilio payload comes from form data
        
        # Required fields for an incoming message
        from_number = payload.get("From", "")
        to_number = payload.get("To", "")
        body = payload.get("Body", "")
        message_sid = payload.get("MessageSid", "")
        
        if not from_number or not message_sid:
            logger.debug("Not a valid Twilio message payload")
            return None
        
        # Clean Twilio's "whatsapp:+123..." prefix
        clean_from = from_number.replace("whatsapp:", "").replace("+", "")
        clean_to = to_number.replace("whatsapp:", "").replace("+", "")
        
        self._session_phone = clean_from
        
        # Handle Media
        num_media = int(payload.get("NumMedia", "0"))
        media_url = None
        media_type = None
        
        if num_media > 0:
            media_url = payload.get("MediaUrl0")
            media_content_type = payload.get("MediaContentType0", "")
            
            if "image" in media_content_type:
                media_type = "image"
            elif "audio" in media_content_type:
                media_type = "audio"
            elif "video" in media_content_type:
                media_type = "video"
            else:
                media_type = "document"
            
            if not body:
                body = "[MEDIA]"
        
        # Use Twilio server time if available, or approximate with 0
        import time
        timestamp = int(time.time() * 1000)
        
        return WhatsAppMessage(
            message_id=message_sid,
            from_number=clean_from,
            to_number=clean_to,
            text=body,
            timestamp=timestamp,
            is_group=False, # Twilio doesn't support generic group chats well
            group_id=None,
            media_type=media_type,
            media_url=media_url,
            raw_payload=payload,
        )
    
    def get_session_id(self) -> str | None:
        """Return the phone number for session tracking."""
        return self._session_phone
    
    async def send_text_message(self, to: str, text: str) -> WhatsAppSendResult:
        """Send a text message via Twilio API."""
        try:
            # Clean string
            to = to.replace("whatsapp:", "").replace("+", "").replace(" ", "").replace("-", "")
            
            # Twilio requires E.164 format with 'whatsapp:' prefix
            formatted_to = f"whatsapp:+{to}"
            
            # Formatted From number - ensure exact match to Twilio's requirements
            from_base = self.twilio_phone.replace("whatsapp:", "").replace("+", "").replace(" ", "").replace("-", "")
            formatted_from = f"whatsapp:+{from_base}"
                
            logger.info(f"📤 Sending Twilio to: {formatted_to}")
            
            # Twilio API uses Form Encoded data, not JSON
            data = {
                "To": formatted_to,
                "From": formatted_from,
                "Body": text
            }
            
            logger.info(f"🐛 TWILIO DEBUG - Sending data: {data}")
            logger.info(f"🐛 TWILIO DEBUG - Auth Token ends with: *(snip)*{self.auth_token[-4:]}")
            logger.info(f"🐛 TWILIO DEBUG - Account SID: {self.account_sid}")
            logger.info(f"🐛 TWILIO DEBUG - Base URL: {self._base_url}")
            
            response = await self._client.post(
                "/Messages.json",
                data=data,
            )
            
            if response.status_code in (200, 201):
                resp_json = response.json()
                msg_sid = resp_json.get("sid")
                logger.info(f"✅ Twilio Sent! ID: {msg_sid}")
                return WhatsAppSendResult(
                    success=True,
                    message_id=msg_sid,
                )
            else:
                logger.error(f"❌ Twilio Send failed: {response.status_code} - {response.text}")
                return WhatsAppSendResult(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}",
                )
                
        except Exception as e:
            logger.exception(f"❌ Error sending via Twilio: {e}")
            return WhatsAppSendResult(success=False, error=str(e))

    async def send_media_message(
        self,
        to: str,
        media_url: str,
        media_type: str,
        caption: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send a media message via Twilio API."""
        try:
            if not to.startswith("+"):
                to = f"+{to}"
            formatted_to = f"whatsapp:{to}"
            
            formatted_from = self.twilio_phone
            if not formatted_from.startswith("whatsapp:"):
                formatted_from = f"whatsapp:{formatted_from}"
            
            data = {
                "To": formatted_to,
                "From": formatted_from,
                "MediaUrl": media_url,
            }
            
            if caption:
                data["Body"] = caption
                
            response = await self._client.post(
                "/Messages.json",
                data=data,
            )
            
            if response.status_code in (200, 201):
                resp_json = response.json()
                return WhatsAppSendResult(
                    success=True,
                    message_id=resp_json.get("sid"),
                )
            else:
                return WhatsAppSendResult(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}",
                )
                
        except Exception as e:
            logger.exception(f"Error sending media via Twilio: {e}")
            return WhatsAppSendResult(success=False, error=str(e))
    
    async def mark_as_read(self, message_id: str) -> bool:
        """Mark a message as read in Twilio. 
        Note: Twilio handles Read Receipts differently, usually automatic."""
        return True
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
