"""
Shopify Platform Adapter for Nouvaris RAG.

Fetches products from Shopify Admin API and converts to unified schema.
"""

import hashlib
import hmac
import base64
from decimal import Decimal
from typing import Optional

import requests

from app.adapters.base_adapter import BasePlatformAdapter
from app.models.unified_product import UnifiedProduct


class ShopifyAdapter(BasePlatformAdapter):
    """Adapter for Shopify e-commerce platform."""
    
    platform_name = "shopify"
    
    def __init__(
        self,
        tenant_id: str,
        store_domain: str,
        access_token: str,
        api_version: str = "2024-01",
        webhook_secret: Optional[str] = None,
    ):
        """Initialize Shopify adapter.
        
        Args:
            tenant_id: UUID of the tenant.
            store_domain: Shopify store domain (e.g., "my-store.myshopify.com").
            access_token: Shopify Admin API access token.
            api_version: Shopify API version.
            webhook_secret: Secret for validating webhooks.
        """
        super().__init__(tenant_id, {
            "store_domain": store_domain,
            "access_token": access_token,
            "api_version": api_version,
            "webhook_secret": webhook_secret,
        })
        
        self.store_domain = store_domain
        self.access_token = access_token
        self.api_version = api_version
        self.webhook_secret = webhook_secret
        
        self.base_url = f"https://{store_domain}/admin/api/{api_version}"
        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }
    
    def fetch_all_products(self) -> list[UnifiedProduct]:
        """Fetch all published products from Shopify.
        
        Handles pagination automatically.
        
        Returns:
            List of UnifiedProduct instances.
        """
        products = []
        url = f"{self.base_url}/products.json"
        params = {
            "limit": 250,  # Max allowed by Shopify
            "published_status": "published",
        }
        
        while url:
            response = requests.get(
                url,
                params=params,
                headers=self.headers,
                timeout=30,
            )
            response.raise_for_status()
            
            data = response.json()
            
            for product_data in data.get("products", []):
                unified = self._to_unified_product(product_data)
                products.append(unified)
            
            # Handle pagination via Link header
            url = None
            params = None  # Only use params on first request
            
            link_header = response.headers.get("Link", "")
            if 'rel="next"' in link_header:
                # Extract next page URL
                for part in link_header.split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip(" <>")
                        break
        
        return products
    
    def fetch_product_by_id(self, product_id: str) -> Optional[UnifiedProduct]:
        """Fetch a single product by Shopify ID.
        
        Args:
            product_id: Shopify product ID.
            
        Returns:
            UnifiedProduct or None if not found.
        """
        try:
            response = requests.get(
                f"{self.base_url}/products/{product_id}.json",
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            
            product_data = response.json().get("product")
            if product_data:
                return self._to_unified_product(product_data)
            return None
            
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Validate Shopify webhook HMAC signature.
        
        Args:
            payload: Raw request body.
            signature: X-Shopify-Hmac-SHA256 header value.
            
        Returns:
            True if signature is valid.
        """
        if not self.webhook_secret:
            return False
        
        computed = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).digest()
        
        computed_b64 = base64.b64encode(computed).decode()
        return hmac.compare_digest(computed_b64, signature)
    
    def parse_webhook_event(
        self,
        event_type: str,
        payload: dict,
    ) -> Optional[UnifiedProduct]:
        """Parse Shopify webhook payload.
        
        Args:
            event_type: Shopify topic (e.g., "products/create").
            payload: Webhook JSON payload.
            
        Returns:
            UnifiedProduct for product events, None otherwise.
        """
        if event_type in ("products/create", "products/update"):
            return self._to_unified_product(payload)
        
        if event_type == "products/delete":
            # Return minimal product for deletion
            return UnifiedProduct(
                tenant_id=self.tenant_id,
                platform=self.platform_name,
                external_id=str(payload.get("id", "")),
                title="",
            )
        
        return None
    
    def _to_unified_product(self, shopify_product: dict) -> UnifiedProduct:
        """Convert Shopify product JSON to unified schema.
        
        Args:
            shopify_product: Shopify product JSON.
            
        Returns:
            UnifiedProduct instance.
        """
        variants = shopify_product.get("variants", []) or []
        first_variant = variants[0] if variants else {}
        
        # Calculate price from first variant
        price = Decimal(str(first_variant.get("price", "0"))) if first_variant.get("price") else Decimal("0")
        
        # Check stock across all variants
        in_stock = any(
            (v.get("inventory_quantity") or 0) > 0
            for v in variants
        )
        
        # Parse tags
        tags_str = shopify_product.get("tags", "")
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        
        # Get all images
        images = [
            img.get("src")
            for img in shopify_product.get("images", [])
            if img.get("src")
        ]
        
        # Build product URL
        handle = shopify_product.get("handle", "")
        url = f"https://{self.store_domain}/products/{handle}" if handle else None
        
        return UnifiedProduct(
            tenant_id=self.tenant_id,
            platform=self.platform_name,
            external_id=str(shopify_product["id"]),
            title=shopify_product.get("title", ""),
            description=shopify_product.get("body_html") or "",
            price=price,
            currency="BRL",  # Could be derived from shop settings
            tags=tags,
            categories=[shopify_product.get("product_type", "")] if shopify_product.get("product_type") else [],
            product_type=shopify_product.get("product_type"),
            vendor=shopify_product.get("vendor"),
            image_url=images[0] if images else None,
            images=images,
            url=url,
            in_stock=in_stock,
            variants_count=len(variants),
            raw_data=shopify_product,
        )
