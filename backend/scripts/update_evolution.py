import asyncio
import os
import sys
from dotenv import load_dotenv

# Load env vars
load_dotenv()

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import get_supabase

async def update_demo_tenant():
    supabase = get_supabase()
    
    tenant_id = "c35fe360-dc69-4997-9d1f-ae57f4d8a135"
    
    # Supabase UPDATE
    data = {
        "whatsapp_provider": "evolution",
        "whatsapp_instance_url": os.getenv("EVOLUTION_API_URL", "http://localhost:8080"),
        "whatsapp_api_key": os.getenv("EVOLUTION_API_KEY", "mock_key"),
        "whatsapp_instance_name": os.getenv("EVOLUTION_INSTANCE_NAME", "test_instance"),
    }
    
    print(f"Atualizando o tenant {tenant_id} de volta para Evolution API...")
    try:
        response = supabase.table("tenants").update(data).eq("id", tenant_id).execute()
        print(f"Sucesso! Banco atualizado: {response.data}")
    except Exception as e:
        print(f"Erro ao atualizar: {e}")

if __name__ == "__main__":
    asyncio.run(update_demo_tenant())
