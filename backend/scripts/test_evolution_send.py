import asyncio
import os
import sys

# Adicionar raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.tenancy import TenantRegistry
from app.adapters.evolution_adapter import EvolutionAdapter

async def main():
    try:
        print("Initializing Registry...")
        registry = TenantRegistry()
        
        print("Fetching tenant 'demo'...")
        tenant = await registry.get_async("demo")
        
        print(f"Tenant found: {tenant.name}")
        print(f"Instance URL: {tenant.whatsapp_instance_url or 'NOT SET'}")
        
        if not tenant.whatsapp_instance_url:
            print("ERROR: whatsapp_instance_url is missing!")
            return

        adapter = EvolutionAdapter(
            instance_url=tenant.whatsapp_instance_url,
            api_key=tenant.whatsapp_api_key,
            instance_name=tenant.whatsapp_instance_name or "nouvaris"
        )
        
        # Numero do usuario extraido do log anterior
        target_number = "5511951733692"
        print(f"Sending test message to {target_number}...")
        
        result = await adapter.send_text_message(target_number, "Teste de diagnostico do Backend Nouvaris (Direct Send)")
        
        print(f"Result: {result}")
        if result.success:
            print("✅ Message sent successfully!")
        else:
            print(f"❌ Failed to send: {result.error}")
        
        await adapter.close()
        
    except Exception as e:
        print(f"EXCEPTION: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
