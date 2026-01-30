
import os
import sys

# Add parent path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.tenancy import TenantRegistry

def check():
    print(f"Checking tenant 'demo'...")
    try:
        registry = TenantRegistry()
        tenant = registry.get("demo", use_cache=False)
        print(f"✅ Tenant found: {tenant.name} (ID: {tenant.tenant_id})")
        print(f"   Active: {tenant.active}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check()
