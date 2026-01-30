import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.state import ConversationState
from app.nodes.action_select_variant import _match_variant_llm

def test_llm_match():
    print("🧪 Testing LLM Variant Matcher...")
    
    # Mock State
    state = ConversationState(
        session_id="test-llm",
        tenant_id="test",
        conversation_history=[
            {"role": "user", "message": "tem o tamanho medio?"},
            {"role": "assistant", "message": "O colar Summer no tamanho médio está esgotado no momento. Mas temos a opção grande disponível. Você gostaria de seguir com essa? 😊"}
        ],
        available_variants=[
            {"id": "VAR_GRANDE_123", "title": "Grande", "available": True},
            {"id": "VAR_MEDIO_456", "title": "Medio", "available": False},
            {"id": "VAR_PEQUENO_789", "title": "Pequeno", "available": False}
        ]
    )
    
    user_input = "pode ser"
    
    print(f"\nScenario 1: 'pode ser' after alternative offer")
    result = _match_variant_llm(user_input, state)
    
    if result and result["id"] == "VAR_GRANDE_123":
        print(f"✅ SUCCESS: Matched 'pode ser' to Grande (ID: {result['id']})")
    else:
        print(f"❌ FAILED: Got {result}")

    # Scenario 2: Specific request
    print(f"\nScenario 2: 'quero o grande'")
    result = _match_variant_llm("quero o grande", state)
    if result and result["id"] == "VAR_GRANDE_123":
        print(f"✅ SUCCESS: Matched 'quero o grande' to Grande")
    else:
        print(f"❌ FAILED: Got {result}")

if __name__ == "__main__":
    test_llm_match()
