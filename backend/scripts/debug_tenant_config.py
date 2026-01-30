import asyncio
import os
import sys

# Adicionar raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.tenancy import TenantRegistry
from app.adapters.evolution_adapter import EvolutionAdapter
import httpx

async def main():
    try:
        print("Initializing Registry...")
        registry = TenantRegistry()
        
        print("Fetching tenant 'demo'...")
        tenant = await registry.get_async("demo")
        
        print(f"--- Tenant Config Dump ---")
        print(f"Name: {tenant.name}")
        print(f"WhatsApp Provider: {tenant.whatsapp_provider}")
        print(f"WhatsApp Instance Name (DB): '{tenant.whatsapp_instance_name}'")
        print(f"WhatsApp Instance URL: {tenant.whatsapp_instance_url}")
        print(f"--------------------------")
        
        adapter_instance_name = tenant.whatsapp_instance_name or "default"
        print(f"Adapter will use instance name: '{adapter_instance_name}'")

        if adapter_instance_name == "default":
             print("Checking status of 'default' instance...")
             url = tenant.whatsapp_instance_url
             api_key = tenant.whatsapp_api_key
             async with httpx.AsyncClient(headers={"apikey": api_key}) as client:
                resp = await client.get(f"{url}/instance/connectionState/default")
                print(f"Status Code: {resp.status_code}")
                print(f"Response: {resp.text}")

    except Exception as e:
        print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    asyncio.run(main())
