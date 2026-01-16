"""
Script para testar integração REAL com Shopify (SEM MOCKS).
Requer .env configurado com SUPABASE_URL e SUPABASE_SERVICE_KEY.
"""
import os
import sys
from dotenv import load_dotenv

# Carrega variáveis do .env
load_dotenv()

# Verifica se credenciais do Supabase existem
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

if not supabase_url or not supabase_key:
    print("❌ ERRO: SUPABASE_URL e SUPABASE_SERVICE_KEY precisam estar no .env")
    sys.exit(1)

try:
    from app.core.tenancy import TenantRegistry
    from app.tools.shopify_client import ShopifyClient
    
    print("\n=== TESTE DE INTEGRAÇÃO REAL SHOPIFY ===\n")
    
    # 1. Obter tenant 'demo' do Supabase
    print("1. Buscando configurações do tenant 'demo' no Supabase...")
    registry = TenantRegistry()
    try:
        tenant = registry.get("demo")
        print(f"   ✅ Tenant encontrado: {tenant.tenant_id}")
        print(f"   🏪 Domínio: {tenant.store_domain}")
    except Exception as e:
        print(f"   ❌ Erro ao buscar tenant: {e}")
        sys.exit(1)

    # 2. Inicializar cliente Shopify real
    print("\n2. Inicializando cliente Shopify com credenciais reais...")
    client = ShopifyClient(
        store_domain=tenant.store_domain,
        access_token=tenant.shopify_access_token,
        api_version=tenant.shopify_api_version
    )

    # 3. Buscar produtos
    term = ""  # Busca vazia para listar tudo
    print(f"\n3. Buscando TODOS os produtos (query vazia)...")
    try:
        products = client.search_products(term, limit=3)
        if products:
            print(f"   ✅ Sucesso! Encontrados {len(products)} produtos:")
            for p in products:
                status = "Disponível" if p.get("in_stock") else "Sem Estoque"
                print(f"      - {p['title']} ({p['price']}) [{status}]")
        else:
            print("   ⚠️ Nenhum produto encontrado (mas a API respondeu).")
            
    except Exception as e:
        print(f"   ❌ Erro na busca: {e}")
        # Tenta listar qualquer produto para debug
        print("\n   Trying to list any products...")
        try:
            products = client.search_products("", limit=3)
            print(f"   Result empty search: {len(products)}")
        except Exception as e2:
            print(f"   ❌ Fatal error: {e2}")

except ImportError:
    print("❌ Erro de importação. Verifique se está rodando na raiz do projeto.")
except Exception as e:
    print(f"❌ Erro inesperado: {e}")
