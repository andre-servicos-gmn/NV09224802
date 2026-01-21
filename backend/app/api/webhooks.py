"""
Webhook handlers for e-commerce platform integrations.

Receives product events from platforms (Shopify, WooCommerce, etc.) and
syncs them to the RAG vector store.

Security measures:
- HMAC signature validation (timing-safe)
- Tenant existence and active status verification
- Rate limiting per tenant
- Secure logging (no sensitive data exposure)
"""

import logging
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.adapters.shopify_adapter import ShopifyAdapter
from app.core.tenancy import TenantRegistry
from app.sync.sync_service import SyncService


# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Simple in-memory rate limiter
# In production, use Redis or similar
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 100  # per tenant per window


def _check_rate_limit(tenant_id: str) -> bool:
    """Check if tenant is within rate limits.
    
    Args:
        tenant_id: Tenant identifier.
        
    Returns:
        True if allowed, False if rate limited.
    """
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    
    # Clean old entries
    _rate_limit_store[tenant_id] = [
        t for t in _rate_limit_store[tenant_id] if t > window_start
    ]
    
    # Check limit
    if len(_rate_limit_store[tenant_id]) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    
    # Record request
    _rate_limit_store[tenant_id].append(now)
    return True


def _get_tenant_credentials(tenant_id: str) -> Optional[dict]:
    """Get tenant credentials from registry.
    
    Args:
        tenant_id: Tenant identifier (UUID or name).
        
    Returns:
        Credentials dict or None if not found.
    """
    try:
        registry = TenantRegistry()
        tenant = registry.get(tenant_id, use_cache=False)  # No cache for security
        
        if not tenant.active:
            return None
            
        return {
            "tenant_uuid": tenant.uuid,
            "store_domain": tenant.store_domain,
            "access_token": tenant.shopify_access_token,
            "api_version": tenant.shopify_api_version,
            # webhook_secret should come from DB - we'll add this
            "webhook_secret": getattr(tenant, "webhook_secret", None),
        }
    except ValueError:
        return None


@router.post(
    "/shopify/{tenant_id}",
    status_code=status.HTTP_200_OK,
    summary="Receive Shopify product webhooks",
    description="Endpoint for Shopify to send product create/update/delete events.",
)
async def shopify_webhook(
    request: Request,
    tenant_id: str,
    x_shopify_topic: str = Header(..., alias="X-Shopify-Topic"),
    x_shopify_hmac_sha256: str = Header(..., alias="X-Shopify-Hmac-SHA256"),
    x_shopify_shop_domain: str = Header(None, alias="X-Shopify-Shop-Domain"),
):
    """
    Handle Shopify webhook for product sync.
    
    Security:
    - Validates HMAC signature using timing-safe comparison
    - Verifies tenant exists and is active
    - Rate limits requests per tenant
    - Returns 200 OK even on errors (prevents Shopify retries/fingerprinting)
    
    Args:
        request: FastAPI request object.
        tenant_id: Tenant identifier from URL.
        x_shopify_topic: Webhook event type (e.g., "products/create").
        x_shopify_hmac_sha256: HMAC signature for validation.
        x_shopify_shop_domain: Shop domain from Shopify.
        
    Returns:
        Success response.
        
    Raises:
        HTTPException: On authentication/validation errors.
    """
    # Get raw body for HMAC validation
    raw_body = await request.body()
    
    # Rate limiting
    if not _check_rate_limit(tenant_id):
        logger.warning(f"Rate limit exceeded for tenant: {tenant_id[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    
    # Get tenant credentials
    credentials = _get_tenant_credentials(tenant_id)
    if not credentials:
        logger.warning(f"Unknown or inactive tenant: {tenant_id[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    # Validate webhook secret is configured
    webhook_secret = credentials.get("webhook_secret")
    if not webhook_secret:
        logger.error(f"Webhook secret not configured for tenant: {tenant_id[:8]}...")
        # Still return 401 to not expose configuration issues
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )
    
    # Validate HMAC signature
    adapter = ShopifyAdapter(
        tenant_id=credentials["tenant_uuid"],
        store_domain=credentials["store_domain"],
        access_token=credentials["access_token"],
        api_version=credentials["api_version"],
        webhook_secret=webhook_secret,
    )
    
    if not adapter.validate_webhook_signature(raw_body, x_shopify_hmac_sha256):
        logger.warning(
            f"Invalid HMAC signature for tenant: {tenant_id[:8]}... "
            f"topic: {x_shopify_topic}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )
    
    # Validate shop domain matches (extra security layer)
    if x_shopify_shop_domain and credentials["store_domain"]:
        if x_shopify_shop_domain.lower() != credentials["store_domain"].lower():
            logger.warning(
                f"Shop domain mismatch for tenant: {tenant_id[:8]}... "
                f"expected: {credentials['store_domain']}, got: {x_shopify_shop_domain}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )
    
    # Parse JSON payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )
    
    # Process webhook
    sync_service = SyncService()
    
    try:
        result = sync_service.process_webhook(
            tenant_id=credentials["tenant_uuid"],
            platform="shopify",
            credentials={
                "store_domain": credentials["store_domain"],
                "access_token": credentials["access_token"],
                "api_version": credentials["api_version"],
                "webhook_secret": webhook_secret,
            },
            event_type=x_shopify_topic,
            payload=payload,
        )
        
        logger.info(
            f"Webhook processed: tenant={tenant_id[:8]}... "
            f"topic={x_shopify_topic} result={result.get('status')}"
        )
        
        return {
            "success": True,
            "event": x_shopify_topic,
            "result": result,
        }
        
    except Exception as e:
        # Log error but return 200 to prevent Shopify retries
        # that could be used for timing attacks
        import traceback
        print(f"[WEBHOOK ERROR] {e}")
        traceback.print_exc()
        logger.error(
            f"Error processing webhook for tenant {tenant_id[:8]}...: {e}",
            exc_info=True,
        )
        return {
            "success": False,
            "event": x_shopify_topic,
            "message": "Processing error",
        }


@router.get("/health", summary="Health check for webhook service")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "service": "webhooks"}
