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
    store_domain: str
    shopify_access_token: str
    shopify_api_version: str = "2024-01"
    default_link_strategy: str = "permalink"
    brand_voice: str = "curto_humano"
    handoff_message: str = "Vou te colocar com um atendente humano..."
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
            tenant_id: ID único do tenant
            use_cache: Se True, usa cache em memória (default: True)
            
        Returns:
            TenantConfig com todas as configurações do tenant
            
        Raises:
            ValueError: Se tenant não existir ou estiver inativo
        """
        # Check cache first
        if use_cache and tenant_id in self._cache:
            return self._cache[tenant_id]
        
        # Fetch from Supabase
        try:
            response = (
                self._supabase.table("tenants")
                .select("*")
                .eq("tenant_id", tenant_id)
                .single()
                .execute()
            )
        except Exception as e:
            raise ValueError(f"Failed to fetch tenant '{tenant_id}': {e}") from e
        
        if not response.data:
            raise ValueError(f"Tenant not found: {tenant_id}")
        
        # REST client always returns a list, get first element
        data = response.data[0] if isinstance(response.data, list) else response.data
        
        # Check if tenant is active
        if not data.get("active", True):
            raise ValueError(f"Tenant is inactive: {tenant_id}")
        
        # Convert to TenantConfig
        tenant = TenantConfig(
            tenant_id=data["tenant_id"],
            name=data.get("name", tenant_id),
            store_domain=data["store_domain"],
            shopify_access_token=data["shopify_access_token"],
            shopify_api_version=data.get("shopify_api_version", "2024-01"),
            default_link_strategy=data.get("default_link_strategy", "permalink"),
            brand_voice=data.get("brand_voice", "curto_humano"),
            handoff_message=data.get("handoff_message", "Vou te colocar com um atendente humano..."),
            active=data.get("active", True),
        )
        
        # Cache for subsequent requests
        self._cache[tenant_id] = tenant
        
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
