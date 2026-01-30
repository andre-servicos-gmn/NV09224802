"""
Debug completo do fluxo webhook -> resposta
Simula uma mensagem recebida e mostra exatamente para onde a resposta seria enviada
"""
import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.tenancy import TenantRegistry
from app.adapters.evolution_adapter import EvolutionAdapter

# Simula payload do webhook
def create_test_payload(from_number):
    """Cria um payload de teste simulando mensagem recebida"""
    return {
        "event": "messages.upsert",
        "instance": "nouvaris",
        "data": {
            "key": {
                "remoteJid": f"{from_number}@s.whatsapp.net",
                "fromMe": False,
                "id": "TEST_MSG_ID_123"
            },
            "pushName": "Test User",
            "message": {
                "conversation": "Oi, tudo bem?"
            },
            "messageTimestamp": 1769709569
        }
    }

async def main():
    print("=" * 70)
    print("DEBUG DO FLUXO WEBHOOK -> RESPOSTA")
    print("=" * 70)
    
    try:
        print("\n[1] Buscando tenant 'demo'...")
        registry = TenantRegistry()
        tenant = await registry.get_async("demo")
        
        print(f"    Tenant: {tenant.name}")
        print(f"    Instance URL: {tenant.whatsapp_instance_url}")
        print(f"    Instance Name: {tenant.whatsapp_instance_name}")
        
        # Cria adapter
        adapter = EvolutionAdapter(
            instance_url=tenant.whatsapp_instance_url,
            api_key=tenant.whatsapp_api_key,
            instance_name=tenant.whatsapp_instance_name or "nouvaris"
        )
        
        # Testa com numero diferente (simulando webhook)
        test_number = "5511954499030"
        
        print(f"\n[2] Simulando webhook de mensagem recebida de: {test_number}")
        payload = create_test_payload(test_number)
        print(f"    Payload: {json.dumps(payload, indent=4)}")
        
        print(f"\n[3] Parse da mensagem...")
        message = adapter.parse_incoming_message(payload)
        
        if message:
            print(f"    [OK] Mensagem parseada:")
            print(f"      - from_number: {message.from_number}")
            print(f"      - to_number: {message.to_number}")
            print(f"      - text: {message.text}")
            print(f"      - session_id (do adapter): {adapter.get_session_id()}")
        else:
            print("    [ERRO] Mensagem foi ignorada (None)")
            return
        
        print(f"\n[4] Fluxo de resposta:")
        print(f"    - Usuario enviou mensagem de: {message.from_number}")
        print(f"    - Sistema vai responder PARA: {message.from_number}")
        print(f"    - (O 'from' do webhook vira 'to' da resposta)")
        
        # Simula o que acontece no webhooks.py linha 241
        from_number_for_response = message.from_number
        
        print(f"\n[5] Teste real de envio de resposta...")
        print(f"    Enviando mensagem de teste PARA: {from_number_for_response}")
        
        result = await adapter.send_text_message(
            to=from_number_for_response,
            text="Esta e uma mensagem de teste do debug_webhook_flow"
        )
        
        if result.success:
            print(f"    [OK] Mensagem enviada!")
            print(f"      Message ID: {result.message_id}")
        else:
            print(f"    [ERRO] Falha: {result.error}")
        
        await adapter.close()
        
        print(f"\n" + "=" * 70)
        print("ANALISE:")
        print("=" * 70)
        print(f"Se o numero {test_number} recebeu a mensagem, o fluxo esta CORRETO!")
        print(f"O problema pode estar em:")
        print(f"  1. O webhook nao esta chegando no backend")
        print(f"  2. O processamento do AI esta falhando")
        print(f"  3. A resposta do AI esta vazia (response_text = None)")
        
    except Exception as e:
        print(f"\nEXCEPTION: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
