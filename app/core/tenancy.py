from pathlib import Path

import yaml
from pydantic import BaseModel


class TenantConfig(BaseModel):
    tenant_id: str
    name: str
    store_domain: str
    default_link_strategy: str
    brand_voice: str
    handoff_message: str


class TenantRegistry:
    def __init__(self, path: str | Path = "tenants.yaml") -> None:
        self.path = Path(path)
        self._tenants = self._load()

    def _load(self) -> dict[str, TenantConfig]:
        if not self.path.exists():
            raise FileNotFoundError(f"Tenant registry not found: {self.path}")
        data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        tenants = data.get("tenants", {})
        return {key: TenantConfig(**value) for key, value in tenants.items()}

    def get(self, tenant_id: str) -> TenantConfig:
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Unknown tenant_id: {tenant_id}")
        return tenant
