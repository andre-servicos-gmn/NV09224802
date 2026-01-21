"""
Base Platform Adapter for Nouvaris RAG.

Abstract base class that all e-commerce platform adapters must implement.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from app.models.unified_product import UnifiedProduct


class BasePlatformAdapter(ABC):
    """Abstract base class for e-commerce platform adapters."""
    
    platform_name: str = "unknown"
    
    def __init__(self, tenant_id: str, credentials: dict):
        """Initialize adapter.
        
        Args:
            tenant_id: UUID of the tenant.
            credentials: Platform-specific credentials dict.
        """
        self.tenant_id = tenant_id
        self.credentials = credentials
    
    @abstractmethod
    def fetch_all_products(self) -> list[UnifiedProduct]:
        """Fetch all products from the platform.
        
        Returns:
            List of UnifiedProduct instances.
        """
        pass
    
    @abstractmethod
    def fetch_product_by_id(self, product_id: str) -> Optional[UnifiedProduct]:
        """Fetch a single product by its platform ID.
        
        Args:
            product_id: Product ID in the original platform.
            
        Returns:
            UnifiedProduct or None if not found.
        """
        pass
    
    @abstractmethod
    def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Validate incoming webhook signature.
        
        Args:
            payload: Raw request body bytes.
            signature: Signature from request header.
            
        Returns:
            True if signature is valid.
        """
        pass
    
    @abstractmethod
    def parse_webhook_event(self, event_type: str, payload: dict) -> Optional[UnifiedProduct]:
        """Parse webhook payload into unified product.
        
        Args:
            event_type: Webhook event type (e.g., "products/create").
            payload: Webhook payload JSON.
            
        Returns:
            UnifiedProduct or None for non-product events.
        """
        pass
    
    def get_platform_name(self) -> str:
        """Return the platform name."""
        return self.platform_name
