import sys
import os
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.core.llm_humanized import generate_humanized_response, _get_brand_voice_guidelines
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig

def main():
    print("Testing Brand Voice Mapping...")
    tenant = TenantConfig(
        tenant_id="demo",
        name="Nouvaris Demo",
        brand_voice="professional", # Testing the alias from Frontend
        active=True
    )
    
    guidelines = _get_brand_voice_guidelines(tenant)
    print(f"Guidelines length: {len(guidelines)}")
    if "Profissional e respeitoso" in guidelines:
        print("SUCCESS: 'professional' mapped to 'formal' correctly.")
    else:
        print("FAIL: 'professional' did NOT map to 'formal'.")
        print(f"Got: {guidelines[:100]}...")

    print("\nTesting Response Generation...")
    state = ConversationState(
        tenant_id="demo",
        session_id="test_prompt",
        intent="general",
        last_user_message="Quais serviços vocês oferecem? Tenho interesse em automação.",
        conversation_history=[{"role": "user", "message": "Oi"}]
    )
    
    try:
        response = generate_humanized_response(state, tenant, domain="store_qa")
        print(f"\nAgent Response:\n{response}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
