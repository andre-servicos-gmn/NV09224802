"""Multi-tenant configuration with Supabase integration.

Tenants are loaded from Supabase database. The brand_voice field is a free-form
text that the client defines to describe the exact tone the agent should use.
"""

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from app.core.database import get_client


class TenantConfig(BaseModel):
    """Tenant configuration loaded from Supabase or YAML fallback."""
    tenant_id: str
    name: str
    store_domain: str = ""
    default_link_strategy: str = "permalink"
    brand_voice: str = "profissional e cordial"  # Free-form text from client
    handoff_message: str = "Vou te encaminhar para um atendente."
    # Additional settings from Supabase JSONB
    settings: dict = {}


def get_tenant_from_db(tenant_id: str) -> TenantConfig | None:
    """Load tenant configuration from Supabase database.
    
    The brand_voice field is free-form text defined by the client.
    Examples:
        - "profissional e direto ao ponto"
        - "simpático e acolhedor, usando emojis"
        - "informal e descontraído, como um amigo"
    """
    try:
        client = get_client()
        
        # Try by UUID first
        if "-" in tenant_id and len(tenant_id) == 36:
            result = client.table("tenants").select("*").eq("id", tenant_id).execute()
        else:
            # Try by name
            result = client.table("tenants").select("*").eq("name", tenant_id).execute()
            if not result.data:
                # Case-insensitive match
                result = client.table("tenants").select("*").ilike("name", tenant_id).execute()
        
        if not result.data:
            return None
        
        tenant_data = result.data[0]
        return TenantConfig(
            tenant_id=tenant_data.get("id", tenant_id),
            name=tenant_data.get("name", tenant_id),
            store_domain=tenant_data.get("store_domain", ""),
            default_link_strategy=tenant_data.get("default_link_strategy", "permalink"),
            brand_voice=tenant_data.get("brand_voice", "profissional e cordial"),
            handoff_message=tenant_data.get("handoff_message", "Vou te encaminhar para um atendente."),
            settings=tenant_data.get("settings") or {},
        )
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[Tenant DB Error] {e}")
        return None


class TenantRegistry:
    """Registry for tenant configurations with Supabase + YAML fallback."""
    
    def __init__(self, path: str | Path = "tenants.yaml") -> None:
        self.path = Path(path)
        self._yaml_tenants = self._load_yaml()

    def _load_yaml(self) -> dict[str, TenantConfig]:
        """Load tenants from YAML as fallback."""
        if not self.path.exists():
            return {}
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            tenants = data.get("tenants", {})
            return {
                key: TenantConfig(
                    tenant_id=value.get("tenant_id", key),
                    name=value.get("name", key),
                    store_domain=value.get("store_domain", ""),
                    default_link_strategy=value.get("default_link_strategy", "permalink"),
                    brand_voice=value.get("brand_voice", "profissional e cordial"),
                    handoff_message=value.get("handoff_message", "Vou te encaminhar para um atendente."),
                )
                for key, value in tenants.items()
            }
        except Exception:
            return {}

    @lru_cache(maxsize=100)
    def get(self, tenant_id: str) -> TenantConfig:
        """Get tenant config from Supabase, with YAML fallback.
        
        Priority:
        1. Supabase database (primary source)
        2. YAML file (fallback for offline/dev)
        3. Default demo config (last resort)
        """
        # Try Supabase first
        db_tenant = get_tenant_from_db(tenant_id)
        if db_tenant:
            return db_tenant
        
        # Fallback to YAML
        yaml_tenant = self._yaml_tenants.get(tenant_id)
        if yaml_tenant:
            return yaml_tenant
        
        # Default demo tenant
        return TenantConfig(
            tenant_id="demo",
            name="Demo Store",
            store_domain="",
            brand_voice="profissional e cordial",
            handoff_message="Vou te encaminhar para um atendente.",
        )
    
    def clear_cache(self) -> None:
        """Clear the tenant cache."""
        self.get.cache_clear()
