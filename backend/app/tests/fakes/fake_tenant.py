"""Fake tenant registry para testes."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FakeTenantConfig:
    """Espelho minimalista de TenantConfig para testes."""
    tenant_id: str = "fake-tenant-id"
    uuid: Optional[str] = "00000000-0000-0000-0000-000000000001"
    name: str = "Fake Store"
    active: bool = True
    brand_voice: Optional[str] = None  # None → supervisor usa default voice section
    store_policies_summary: Optional[str] = None
    # Campos adicionais que turn_processor não usa, mas podem ser checados:
    store_domain: Optional[str] = None
    shopify_access_token: Optional[str] = None
    shopify_api_version: str = "2024-01"
    handoff_message: str = "Vou te encaminhar..."
    store_niche: Optional[str] = None
    whatsapp_provider: Optional[str] = None
    whatsapp_instance_url: Optional[str] = None
    whatsapp_api_key: Optional[str] = None
    whatsapp_instance_name: Optional[str] = None
    webhook_secret: Optional[str] = None


class FakeTenantRegistry:
    """Fake do TenantRegistry. Aceita configuração injetada por teste."""

    def __init__(self, tenant: Optional[FakeTenantConfig] = None, should_raise: bool = False):
        self._tenant = tenant or FakeTenantConfig()
        self._should_raise = should_raise

    def get(self, tenant_id: str, use_cache: bool = True) -> FakeTenantConfig:
        if self._should_raise:
            raise ValueError(f"Tenant not found: {tenant_id}")
        return self._tenant
