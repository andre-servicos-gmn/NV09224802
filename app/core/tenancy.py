"""
Módulo de multi-tenancy do Nouvaris Agents V2.

Gerencia configurações por tenant, buscando dados do Supabase.
Em runtime, tokens e configurações vêm SEMPRE do banco de dados.
"""

from typing import Optional

from pydantic import BaseModel

from app.core.supabase_client import get_supabase


class TenantConfig(BaseModel):
    """Configuração de um tenant."""
    
    tenant_id: str
    name: str
    store_domain: str | None = None
    shopify_access_token: str | None = None
    shopify_api_version: str = "2024-01"
    default_link_strategy: str = "permalink"
    brand_voice: str = "curto_humano"
    handoff_message: str = "Vou te colocar com um atendente humano..."
    store_niche: str | None = None
    active: bool = True


class TenantRegistry:
    """
    Registro de tenants que busca configurações do Supabase.
    
    Em runtime, todas as configurações (incluindo tokens Shopify)
    são buscadas diretamente do banco de dados Supabase.
    
    NÃO use variáveis de ambiente para tokens em runtime.
    """
    
    def __init__(self) -> None:
        """Inicializa o registry com cliente Supabase."""
        self._supabase = get_supabase()
        self._cache: dict[str, TenantConfig] = {}
    
    def get(self, tenant_id: str, use_cache: bool = True) -> TenantConfig:
        """
        Busca configuração de um tenant do Supabase.
        
        Args:
            tenant_id: ID único do tenant ou nome do tenant
            use_cache: Se True, usa cache em memória (default: True)
            
        Returns:
            TenantConfig com todas as configurações do tenant
            
        Raises:
            ValueError: Se tenant não existir ou estiver inativo
        """
        import os
        
        # Check cache first (by both id and name)
        if use_cache and tenant_id in self._cache:
            return self._cache[tenant_id]
        
        data = None
        
        # Try 1: Fetch by tenant_id column
        try:
            resp = (
                self._supabase.table("tenants")
                .select("*")
                .eq("tenant_id", tenant_id)
                .execute()
            )
            if resp.data and len(resp.data) > 0:
                data = resp.data[0]
        except Exception:
            pass
        
        # Try 2: Fetch by id column (if tenant_id is UUID and table uses "id")
        if not data:
            try:
                resp = (
                    self._supabase.table("tenants")
                    .select("*")
                    .eq("id", tenant_id)
                    .execute()
                )
                if resp.data and len(resp.data) > 0:
                    data = resp.data[0]
            except Exception:
                pass
        
        # Try 3: Fetch by name (ilike for case-insensitive)
        if not data:
            try:
                resp = (
                    self._supabase.table("tenants")
                    .select("*")
                    .ilike("name", tenant_id)
                    .execute()
                )
                if resp.data and len(resp.data) > 0:
                    data = resp.data[0]
            except Exception:
                pass
        
        if not data:
            raise ValueError(f"Tenant not found: {tenant_id}")
        
        # Check if tenant is active
        if data.get("active") is False:
            raise ValueError(f"Tenant is inactive: {tenant_id}")
        
        # Handle different column name variations from Supabase
        actual_tenant_id = data.get("tenant_id") or data.get("id")
        actual_token = data.get("shopify_access_token") or data.get("access_token")
        actual_domain = data.get("store_domain") or data.get("domain") or data.get("shopify_domain")
        
        # Extract store_niche from settings JSON or direct column
        store_niche = data.get("store_niche")
        if not store_niche and isinstance(data.get("settings"), dict):
            store_niche = data["settings"].get("store_niche")
        
        if os.getenv("DEBUG"):
            print(f"[Tenant] Keys: {list(data.keys())} | resolved_id: {actual_tenant_id}")
        
        # Convert to TenantConfig
        tenant = TenantConfig(
            tenant_id=actual_tenant_id,
            name=data.get("name", tenant_id),
            store_domain=actual_domain,
            shopify_access_token=actual_token,
            shopify_api_version=data.get("shopify_api_version", "2024-01"),
            default_link_strategy=data.get("default_link_strategy", "permalink"),
            brand_voice=data.get("brand_voice", "curto_humano"),
            handoff_message=data.get("handoff_message", "Vou te colocar com um atendente humano..."),
            store_niche=store_niche,
            active=data.get("active", True),
        )
        
        # Cache for subsequent requests (by id, name, and original input)
        if actual_tenant_id:
            self._cache[actual_tenant_id] = tenant
        if tenant.name:
            self._cache[tenant.name] = tenant
        self._cache[tenant_id] = tenant  # Also cache by original input for compat
        
        return tenant
    
    def clear_cache(self, tenant_id: Optional[str] = None) -> None:
        """
        Limpa cache de tenants.
        
        Args:
            tenant_id: Se fornecido, limpa apenas este tenant. Se None, limpa todo o cache.
        """
        if tenant_id:
            self._cache.pop(tenant_id, None)
        else:
            self._cache.clear()
