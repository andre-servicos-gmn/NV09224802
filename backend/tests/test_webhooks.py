"""
Tests for webhook handlers.

Tests the Shopify webhook endpoint including:
- HMAC signature validation
- Rate limiting
- Tenant verification
- Product sync operations
"""

import base64
import hashlib
import hmac
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add parent path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.api.main import app


client = TestClient(app)


# Test constants
TEST_TENANT_ID = "test-tenant-123"
TEST_WEBHOOK_SECRET = "shpss_test_secret_key_12345"
TEST_STORE_DOMAIN = "test-store.myshopify.com"


def _generate_hmac(payload: bytes, secret: str) -> str:
    """Generate Shopify HMAC signature."""
    digest = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode()


@pytest.fixture
def mock_tenant():
    """Mock tenant registry to return test tenant."""
    with patch("app.api.webhooks.TenantRegistry") as mock:
        tenant_config = MagicMock()
        tenant_config.active = True
        tenant_config.uuid = TEST_TENANT_ID
        tenant_config.store_domain = TEST_STORE_DOMAIN
        tenant_config.shopify_access_token = "test_token"
        tenant_config.shopify_api_version = "2024-01"
        tenant_config.webhook_secret = TEST_WEBHOOK_SECRET
        
        mock.return_value.get.return_value = tenant_config
        yield mock


@pytest.fixture
def mock_sync_service():
    """Mock sync service to capture calls."""
    with patch("app.api.webhooks.SyncService") as mock:
        mock.return_value.process_webhook.return_value = {
            "status": "synced",
            "external_id": "12345",
            "title": "Test Product",
        }
        yield mock


@pytest.fixture
def sample_product_payload():
    """Sample Shopify product payload."""
    return {
        "id": 12345,
        "title": "Camiseta Teste",
        "body_html": "<p>Uma camiseta muito legal</p>",
        "vendor": "Test Brand",
        "product_type": "Roupas",
        "tags": "algodao, basico",
        "variants": [
            {
                "id": 1,
                "price": "79.90",
                "inventory_quantity": 10,
            }
        ],
        "images": [
            {"src": "https://example.com/image.jpg"}
        ],
        "handle": "camiseta-teste",
    }


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_root_endpoint(self):
        """Test root endpoint returns service info."""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["service"] == "Nouvaris API"
    
    def test_health_endpoint(self):
        """Test global health check."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_webhooks_health(self):
        """Test webhooks service health."""
        response = client.get("/webhooks/health")
        assert response.status_code == 200
        assert response.json()["service"] == "webhooks"


class TestShopifyWebhook:
    """Test Shopify webhook endpoint."""
    
    def test_missing_headers_returns_422(self):
        """Test that missing required headers returns 422."""
        response = client.post(
            f"/webhooks/shopify/{TEST_TENANT_ID}",
            json={"id": 123},
        )
        assert response.status_code == 422
    
    def test_unknown_tenant_returns_404(self, mock_tenant):
        """Test that unknown tenant returns 404."""
        mock_tenant.return_value.get.side_effect = ValueError("Not found")
        
        response = client.post(
            f"/webhooks/shopify/unknown-tenant",
            json={"id": 123},
            headers={
                "X-Shopify-Topic": "products/create",
                "X-Shopify-Hmac-SHA256": "invalid",
            },
        )
        assert response.status_code == 404
    
    def test_invalid_hmac_returns_401(self, mock_tenant):
        """Test that invalid HMAC signature returns 401."""
        response = client.post(
            f"/webhooks/shopify/{TEST_TENANT_ID}",
            json={"id": 123},
            headers={
                "X-Shopify-Topic": "products/create",
                "X-Shopify-Hmac-SHA256": "invalid_signature",
            },
        )
        assert response.status_code == 401
    
    def test_valid_webhook_product_create(
        self, mock_tenant, mock_sync_service, sample_product_payload
    ):
        """Test valid product create webhook is processed."""
        payload = json.dumps(sample_product_payload).encode()
        signature = _generate_hmac(payload, TEST_WEBHOOK_SECRET)
        
        response = client.post(
            f"/webhooks/shopify/{TEST_TENANT_ID}",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Topic": "products/create",
                "X-Shopify-Hmac-SHA256": signature,
                "X-Shopify-Shop-Domain": TEST_STORE_DOMAIN,
            },
        )
        
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["event"] == "products/create"
        
        # Verify sync service was called
        mock_sync_service.return_value.process_webhook.assert_called_once()
    
    def test_valid_webhook_product_update(
        self, mock_tenant, mock_sync_service, sample_product_payload
    ):
        """Test valid product update webhook is processed."""
        payload = json.dumps(sample_product_payload).encode()
        signature = _generate_hmac(payload, TEST_WEBHOOK_SECRET)
        
        response = client.post(
            f"/webhooks/shopify/{TEST_TENANT_ID}",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Topic": "products/update",
                "X-Shopify-Hmac-SHA256": signature,
                "X-Shopify-Shop-Domain": TEST_STORE_DOMAIN,
            },
        )
        
        assert response.status_code == 200
        assert response.json()["success"] is True
    
    def test_valid_webhook_product_delete(
        self, mock_tenant, mock_sync_service
    ):
        """Test valid product delete webhook is processed."""
        payload = json.dumps({"id": 12345}).encode()
        signature = _generate_hmac(payload, TEST_WEBHOOK_SECRET)
        
        mock_sync_service.return_value.process_webhook.return_value = {
            "status": "deleted",
            "external_id": "12345",
        }
        
        response = client.post(
            f"/webhooks/shopify/{TEST_TENANT_ID}",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Topic": "products/delete",
                "X-Shopify-Hmac-SHA256": signature,
                "X-Shopify-Shop-Domain": TEST_STORE_DOMAIN,
            },
        )
        
        assert response.status_code == 200
        assert response.json()["success"] is True
    
    def test_shop_domain_mismatch_returns_401(self, mock_tenant):
        """Test that shop domain mismatch returns 401."""
        payload = json.dumps({"id": 123}).encode()
        signature = _generate_hmac(payload, TEST_WEBHOOK_SECRET)
        
        response = client.post(
            f"/webhooks/shopify/{TEST_TENANT_ID}",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Topic": "products/create",
                "X-Shopify-Hmac-SHA256": signature,
                "X-Shopify-Shop-Domain": "malicious-store.myshopify.com",
            },
        )
        
        assert response.status_code == 401


class TestRateLimiting:
    """Test rate limiting functionality."""
    
    def test_rate_limit_not_triggered_on_low_traffic(self, mock_tenant, mock_sync_service):
        """Test that rate limit is not triggered on low traffic."""
        payload = json.dumps({"id": 123}).encode()
        signature = _generate_hmac(payload, TEST_WEBHOOK_SECRET)
        
        # Make 5 requests
        for _ in range(5):
            response = client.post(
                f"/webhooks/shopify/{TEST_TENANT_ID}",
                content=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Shopify-Topic": "products/update",
                    "X-Shopify-Hmac-SHA256": signature,
                    "X-Shopify-Shop-Domain": TEST_STORE_DOMAIN,
                },
            )
            assert response.status_code == 200
