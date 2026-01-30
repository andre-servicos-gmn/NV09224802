"""
Testa envio para um numero diferente (5511954499030)
"""
import asyncio
import os
import sys
import httpx
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.tenancy import TenantRegistry

async def main():
    print("=" * 60)
    print("TESTE COM NUMERO DIFERENTE: 5511954499030")
    print("=" * 60)
    
    try:
        print("\nInitializing Registry...")
        registry = TenantRegistry()
        
        print("Fetching tenant 'demo'...")
        tenant = await registry.get_async("demo")
        
        instance_name = tenant.whatsapp_instance_name or "nouvaris"
        url = tenant.whatsapp_instance_url.rstrip("/")
        api_key = tenant.whatsapp_api_key
        
        target_number = "5511954499030"
        
        print(f"\nConfiguration:")
        print(f"  Instance Name: {instance_name}")
        print(f"  Instance URL: {url}")
        print(f"  Target Number: {target_number}")
        
        payload = {
            "number": target_number,
            "text": "Teste de mensagem do sistema Nouvaris para numero diferente"
        }
        
        print(f"\nPayload: {json.dumps(payload, indent=2)}")
        
        async with httpx.AsyncClient(
            headers={"apikey": api_key, "Content-Type": "application/json"},
            timeout=30.0
        ) as client:
            print("\nEnviando mensagem...")
            resp = await client.post(
                f"{url}/message/sendText/{instance_name}",
                json=payload
            )
            
            print(f"\nStatus Code: {resp.status_code}")
            print(f"Response: {resp.text}")
            
            if resp.status_code == 201:
                data = resp.json()
                print(f"\n✓ Mensagem aceita pela API!")
                print(f"  Message ID: {data.get('key', {}).get('id')}")
                print(f"  Status: {data.get('status')}")
                print(f"  Remote JID: {data.get('key', {}).get('remoteJid')}")
                print(f"\nVerifique se a mensagem chegou no WhatsApp do numero {target_number}")
            else:
                print(f"\n✗ Erro ao enviar mensagem")
                
    except Exception as e:
        print(f"\nEXCEPTION: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
