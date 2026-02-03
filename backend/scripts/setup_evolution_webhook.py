"""
Script para configurar o webhook da Evolution API.

Este script configura o webhook na instância Evolution para enviar eventos
para o backend do Nouvaris via ngrok tunnel.

Uso:
    python scripts/setup_evolution_webhook.py <NGROK_URL> [TENANT_ID]
    
Exemplo:
    python scripts/setup_evolution_webhook.py https://abc123.ngrok-free.dev demo
"""

import asyncio
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import httpx
from app.core.tenancy import TenantRegistry


async def get_current_webhook(base_url: str, api_key: str, instance_name: str) -> dict:
    """Busca a configuração atual do webhook."""
    async with httpx.AsyncClient(headers={"apikey": api_key}, timeout=30) as client:
        try:
            response = await client.get(f"{base_url}/webhook/find/{instance_name}")
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            print(f"⚠️ Erro ao buscar webhook atual: {e}")
            return {}


async def set_webhook(
    base_url: str, 
    api_key: str, 
    instance_name: str, 
    webhook_url: str
) -> bool:
    """Configura o webhook na Evolution API."""
    
    # Formato para Evolution API v2
    webhook_config = {
        "webhook": {
            "enabled": True,
            "url": webhook_url,
            "webhookByEvents": False,
            "webhookBase64": False,
            "events": [
                "MESSAGES_UPSERT",
                "MESSAGES_UPDATE", 
                "MESSAGES_DELETE",
                "SEND_MESSAGE",
                "CONNECTION_UPDATE",
                "PRESENCE_UPDATE"
            ]
        }
    }
    
    async with httpx.AsyncClient(headers={"apikey": api_key}, timeout=30) as client:
        try:
            # Evolution API v2: POST /webhook/set/{instance}
            response = await client.post(
                f"{base_url}/webhook/set/{instance_name}",
                json=webhook_config
            )
            
            if response.status_code in (200, 201):
                print(f"✅ Webhook configurado com sucesso!")
                print(f"   URL: {webhook_url}")
                return True
            
            # Fallback: tentar formato simples (v1)
            simple_config = {
                "url": webhook_url,
                "enabled": True,
                "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE"]
            }
            
            response = await client.post(
                f"{base_url}/webhook/set/{instance_name}",
                json=simple_config
            )
            
            if response.status_code in (200, 201):
                print(f"✅ Webhook configurado (formato v1)!")
                print(f"   URL: {webhook_url}")
                return True
                
            print(f"❌ Falha ao configurar webhook: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
        except Exception as e:
            print(f"❌ Erro ao configurar webhook: {e}")
            return False


async def check_instance_status(base_url: str, api_key: str, instance_name: str) -> dict:
    """Verifica o status da instância Evolution."""
    async with httpx.AsyncClient(headers={"apikey": api_key}, timeout=30) as client:
        try:
            response = await client.get(f"{base_url}/instance/connectionState/{instance_name}")
            if response.status_code == 200:
                return response.json()
            return {"error": f"Status {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}


async def main(ngrok_url: str, tenant_id: str = "demo"):
    """Configura o webhook para o tenant especificado."""
    
    print("=" * 60)
    print("🚀 CONFIGURAÇÃO DO WEBHOOK EVOLUTION API")
    print("=" * 60)
    
    # 1. Buscar configuração do tenant
    print(f"\n📋 Buscando tenant: {tenant_id}...")
    try:
        registry = TenantRegistry()
        tenant = registry.get(tenant_id)
    except ValueError as e:
        print(f"❌ Tenant não encontrado: {e}")
        return
    
    print(f"   Nome: {tenant.name}")
    print(f"   Provider: {tenant.whatsapp_provider}")
    print(f"   Instance Name: {tenant.whatsapp_instance_name}")
    print(f"   Instance URL: {tenant.whatsapp_instance_url}")
    
    if tenant.whatsapp_provider != "evolution":
        print(f"❌ Tenant não usa Evolution API!")
        return
    
    base_url = tenant.whatsapp_instance_url.rstrip("/")
    api_key = tenant.whatsapp_api_key
    instance_name = tenant.whatsapp_instance_name or "default"
    
    # 2. Verificar status da instância
    print(f"\n📡 Verificando status da instância '{instance_name}'...")
    status = await check_instance_status(base_url, api_key, instance_name)
    print(f"   Status: {status}")
    
    # 3. Montar URL do webhook
    webhook_url = f"{ngrok_url.rstrip('/')}/webhooks/whatsapp/{tenant_id}"
    print(f"\n🔗 URL do Webhook: {webhook_url}")
    
    # 4. Buscar configuração atual
    print(f"\n🔍 Buscando configuração atual do webhook...")
    current = await get_current_webhook(base_url, api_key, instance_name)
    if current:
        print(f"   Configuração atual: {current.get('url', 'Nenhuma')}")
    
    # 5. Configurar novo webhook
    print(f"\n⚙️ Configurando webhook...")
    success = await set_webhook(base_url, api_key, instance_name, webhook_url)
    
    if success:
        print("\n" + "=" * 60)
        print("✅ CONFIGURAÇÃO CONCLUÍDA COM SUCESSO!")
        print("=" * 60)
        print(f"\n📱 Agora você pode enviar mensagens para o WhatsApp conectado")
        print(f"   à instância '{instance_name}' e elas serão processadas pelo")
        print(f"   agente AI do Nouvaris.")
        print(f"\n🔗 Webhook URL: {webhook_url}")
        print(f"\n💡 Dica: Mantenha o ngrok rodando enquanto testa!")
    else:
        print("\n❌ Falha na configuração. Verifique os logs acima.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/setup_evolution_webhook.py <NGROK_URL> [TENANT_ID]")
        print("Exemplo: python scripts/setup_evolution_webhook.py https://abc123.ngrok-free.dev demo")
        sys.exit(1)
    
    ngrok_url = sys.argv[1]
    tenant_id = sys.argv[2] if len(sys.argv) > 2 else "demo"
    
    asyncio.run(main(ngrok_url, tenant_id))
