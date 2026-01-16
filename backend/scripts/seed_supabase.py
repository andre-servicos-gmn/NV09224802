"""
Popula Supabase com tenant de demonstração.

ATENÇÃO: Este script usa tokens do .env APENAS para seed inicial.
Após executar este script, o sistema busca tokens do Supabase.

Para adicionar novos tenants em produção, use:
- Interface admin (futuro)
- Diretamente no Supabase Dashboard

Uso:
    python scripts/seed_supabase.py
"""

import os
import sys

from dotenv import load_dotenv

# Garante que o path do projeto está no PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()


def seed() -> None:
    """
    Popula Supabase com tenant de demonstração.
    
    Lê credenciais Shopify de variáveis de ambiente (.env)
    e persiste no Supabase para uso em runtime.
    """
    from app.core.supabase_client import get_supabase
    
    supabase = get_supabase()
    
    # Valida variáveis obrigatórias
    store_domain = os.getenv("DEMO_STORE_DOMAIN")
    shopify_token = os.getenv("DEMO_SHOPIFY_TOKEN")
    
    if not store_domain or not shopify_token:
        print("❌ Erro: DEMO_STORE_DOMAIN e DEMO_SHOPIFY_TOKEN devem estar definidos no .env")
        print("\nExemplo:")
        print("  DEMO_STORE_DOMAIN=mystore.myshopify.com")
        print("  DEMO_SHOPIFY_TOKEN=shpat_xxxxxxxxxxxxxxx")
        sys.exit(1)
    
    tenant_data = {
        "tenant_id": "demo",
        "name": "Demo Store",
        "store_domain": store_domain,
        "shopify_access_token": shopify_token,
        "shopify_api_version": "2024-01",
        "default_link_strategy": "permalink",
        "brand_voice": "curto_humano",
        "handoff_message": "Vou te colocar com um atendente humano pra resolver mais rápido.",
        "active": True
    }
    
    # Upsert (insert ou update se já existir)
    try:
        query = supabase.table("tenants").upsert(tenant_data, on_conflict="tenant_id")
        query.execute_upsert()
        
        print("✅ Tenant 'demo' salvo no Supabase com sucesso!")
        print(f"   Store: {tenant_data['store_domain']}")
        print(f"   Strategy: {tenant_data['default_link_strategy']}")
        
    except Exception as e:
        print(f"❌ Erro ao salvar tenant: {e}")
        sys.exit(1)
    
    # Validar que consegue buscar
    try:
        from app.core.tenancy import TenantRegistry
        
        registry = TenantRegistry()
        tenant = registry.get("demo")
        
        print(f"\n✅ Validação OK: tenant '{tenant.name}' carregado do Supabase")
        print(f"   Token: {tenant.shopify_access_token[:10]}...")
        
    except Exception as e:
        print(f"\n⚠️  Aviso: Seed OK, mas validação falhou: {e}")


if __name__ == "__main__":
    seed()
