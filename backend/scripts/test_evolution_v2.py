import asyncio
import os
import sys
import httpx

# Adicionar raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.tenancy import TenantRegistry

async def main():
    try:
        print("Initializing Registry...")
        registry = TenantRegistry()
        
        print("Fetching tenant 'demo'...")
        tenant = await registry.get_async("demo")
        
        instance_name = tenant.whatsapp_instance_name or "nouvaris"
        url = tenant.whatsapp_instance_url
        api_key = tenant.whatsapp_api_key
        
        # Target number (raw)
        target_number = "5511951733692"
        
        print(f"Sending V2 payload to {target_number}...")
        
        payload = {
            "number": target_number,
            "options": {
                "delay": 1200,
                "presence": "composing",
                "linkPreview": False
            },
            "textMessage": {
                "text": "Teste V2 Payload (Com Options e TextMessage)"
            }
        }
        
        async with httpx.AsyncClient(headers={"apikey": api_key}) as client:
            resp = await client.post(
                f"{url}/message/sendText/{instance_name}",
                json=payload
            )
            print(f"Status Code: {resp.status_code}")
            print(f"Response: {resp.text}")
            
    except Exception as e:
        print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    asyncio.run(main())
