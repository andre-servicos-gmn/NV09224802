import sys
import os
import asyncio
from dotenv import load_dotenv

# Load env from project root
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.llm_humanized import generate_humanized_response
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig

async def test_humanizer():
    tenant = TenantConfig(
        tenant_id="demo", 
        name="Loja Teste", 
        brand_voice="simpático", # Voice: Friendly/Emoji
        whatsapp_phone="5511999999999",
        supabase_url="http://mock",
        supabase_key="mock"
    )

    print("\n=== TEST 1: CENÁRIO PADRÃO (SIMPÁTICO) ===")
    state1 = ConversationState(
        tenant_id="demo", 
        session_id="test1",
        intent="search_product",
        sentiment_level="calm",
        last_user_message="Quero ver tênis"
    )
    # Mock search results
    state1.last_action = "action_search_products"
    state1.last_action_success = True
    state1.selected_products = [
        {"title": "Nike Air", "price": "500,00"},
        {"title": "Adidas Run", "price": "450,00"}
    ]
    
    resp1 = generate_humanized_response(state1, tenant, "sales")
    print(f"RESPOSTA:\n{resp1}\n")


    print("\n=== TEST 2: CENÁRIO FRUSTRADO (OVERRIDE) ===")
    state2 = ConversationState(
        tenant_id="demo", 
        session_id="test2",
        intent="order_status",
        sentiment_level="frustrated", # TRIGGER OVERRIDE
        frustration_level=4,          # TRIGGER OVERRIDE
        last_user_message="Meu pedido nunca chega, que droga!"
    )
    state2.last_action = "action_check_order"
    state2.last_action_success = False # Action failed
    state2.metadata["check_order_error"] = "Order not found"
    
    resp2 = generate_humanized_response(state2, tenant, "support")
    print(f"RESPOSTA:\n{resp2}\n")


    print("\n=== TEST 3: CENÁRIO GROUNDING (LINK SAGRADO) ===")
    state3 = ConversationState(
        tenant_id="demo", 
        session_id="test3",
        intent="purchase_intent",
        sentiment_level="calm",
        last_user_message="Manda o link"
    )
    state3.last_action = "action_generate_link"
    state3.last_action_success = True
    state3.metadata["checkout_link"] = "https://checkout.com/123"
    
    resp3 = generate_humanized_response(state3, tenant, "sales")
    print(f"RESPOSTA:\n{resp3}\n")

if __name__ == "__main__":
    asyncio.run(test_humanizer())
