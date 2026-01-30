import os
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env
from dotenv import load_dotenv
load_dotenv()

from app.rag_engine.pipeline import RAGPipeline
from app.core.state import ConversationState  # Removed ConversationMetadata
from app.core.tenancy import TenantConfig
from app.nodes.action_search_products import action_search_products
from app.nodes.decide import decide

TENANT_UUID = "c35fe360-dc69-4997-9d1f-ae57f4d8a135"

def test_flow():
    print("\n🔍 Testing Search Flow for 'colar summer'")
    print("-" * 50)
    
    # 1. Setup State
    state = ConversationState(
        session_id="test-debug",  # Corrected
        tenant_id="test",
        metadata={}  # metadata is a dict
    )
    state.last_user_message = "quero o colar summer"
    state.intent = "search_product"
    
    tenant = TenantConfig(
        tenant_id=TENANT_UUID,
        uuid=TENANT_UUID,
        name="Nouvaris",
        store_domain="test.myshopify.com",
        shopify_access_token="123",
        shopify_api_version="2024-01"
    )

    # 2. Run Search Action
    print("🚀 Running action_search_products...")
    state = action_search_products(state, tenant)
    
    print(f"\n📦 Search Results: {len(state.selected_products or [])}")
    if state.selected_products:
        p = state.selected_products[0]
        print(f"   Product: {p.get('title')}")
        print(f"   Has Variants: {p.get('has_variants')}")
        print(f"   Variants Count: {p.get('variants_count')}")
        print(f"   Variants Data: {len(p.get('variants') or [])} items")
        
    print(f"\n📋 Available Variants in State: {len(state.available_variants or [])}")
    for v in state.available_variants or []:
        print(f"   - {v.get('title')} (Available: {v.get('available')})")
        
    # 3. Run Decide Node
    print("\n🧠 Running decide node...")
    next_action = decide(state, tenant)
    print(f"👉 Next Action: {next_action}")
    
    if next_action == "action_generate_link":
        print("❌ ERROR: Skipped variant selection!")
    elif next_action == "respond":
        print("✅ SUCCESS: Will ask user (respond)")
    elif next_action == "action_select_variant":
        print("❓ WARNING: Auto-selected variant action?")
        
if __name__ == "__main__":
    test_flow()
