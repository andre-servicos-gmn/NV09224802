"""Abstract base class for WhatsApp provider adapters.
This module defines the interface that all WhatsApp providers must implement,
allowing easy switching between Evolution API, Twilio, Meta Cloud API, etc.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from fastapi import Request


@dataclass
class WhatsAppMessage:
    """Standardized incoming WhatsApp message."""
    
    message_id: str
    from_number: str  # Phone number of sender (e.g., "5511999999999")
    to_number: str    # Phone number of recipient (your WhatsApp number)
    text: str         # Message text content
    timestamp: int    # Unix timestamp
    is_group: bool = False
    group_id: Optional[str] = None
    media_type: Optional[str] = None  # "image", "audio", "video", "document"
    media_url: Optional[str] = None
    raw_payload: Optional[dict] = None  # Original provider payload for debugging


@dataclass
class WhatsAppSendResult:
    """Result of sending a message."""
    
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


class WhatsAppAdapterBase(ABC):
    """Abstract base class for WhatsApp provider adapters."""
    
    def __init__(
        self,
        instance_url: str,
        api_key: str,
        instance_name: Optional[str] = None,
    ):
        self.instance_url = instance_url.rstrip("/")
        self.api_key = api_key
        self.instance_name = instance_name or "default"
    
    @abstractmethod
    async def validate_webhook(self, request: Request) -> bool:
        """Validate incoming webhook request (e.g., HMAC signature)."""
        pass
    
    @abstractmethod
    def parse_incoming_message(self, payload: dict) -> Optional[WhatsAppMessage]:
        """Parse incoming webhook payload into standardized message."""
        pass
    
    @abstractmethod
    async def send_text_message(self, to: str, text: str) -> WhatsAppSendResult:
        """Send a text message to a WhatsApp number."""
        pass
    
    @abstractmethod
    async def send_media_message(
        self,
        to: str,
        media_url: str,
        media_type: str,
        caption: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send a media message (image, audio, video, document)."""
        pass
    
    @abstractmethod
    async def mark_as_read(self, message_id: str) -> bool:
        """Mark a message as read."""
        pass
