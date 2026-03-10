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
        "whatsapp_provider": "twilio",
        "whatsapp_instance_url": os.getenv("TWILIO_PHONE_NUMBER", "+14155238886"), # Twilio Phone Number
        "whatsapp_api_key": os.getenv("TWILIO_AUTH_TOKEN", "REPLACE_ME"), # Auth Token
        "whatsapp_instance_name": os.getenv("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000"), # Account SID
    }
    
    print(f"Updating tenant {tenant_id}...")
    try:
        response = supabase.table("tenants").update(data).eq("id", tenant_id).execute()
        print(f"Success! Response: {response.data}")
    except Exception as e:
        print(f"Error updating tenant: {e}")

if __name__ == "__main__":
    asyncio.run(update_demo_tenant())
