
import os
import sys
from app.core.router import classify
from app.nodes.respond import respond
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig

# Mock tenant
tenant = TenantConfig(
    tenant_id="demo", 
    name="Demo Store", 
    store_domain="demo.com", 
    shopify_access_token="123",
    brand_voice="curto_humano"
)

def test_media_fallback():
    print("Testing Media Fallback...")
    # Test AUDIO
    decision = classify("[AUDIO] some file")
    print(f"Input: [AUDIO] -> Intent: {decision.intent} (Expected: media_unsupported)")
    assert decision.intent == "media_unsupported"
    
    # Test Response
    state = ConversationState(tenant_id="demo", session_id="test", intent=decision.intent)
    state = respond(state, tenant)
    print(f"Response: {state.last_bot_message}")
    assert "Ainda não consigo ouvir" in state.last_bot_message
    print("[PASS] Media Fallback\n")

def test_typos():
    print("Testing Typo Tolerance (LLM)...")
    cases = [
        ("quero cmprar uma camiza", "purchase_intent"),
        ("neu pedid nao xegou ainda", "order_complaint"),
        ("rastreio do pedid 12345", "order_tracking"),
        ("qual o valor do freeti", "shipping_question"),
        ("aceita piks?", "payment_question"),
    ]
    
    passed = 0
    for text, expected in cases:
        decision = classify(text)
        print(f"Input: '{text}' -> Intent: {decision.intent}\n   Expected: {expected} | Confidence: {decision.confidence}")
        if decision.intent == expected:
            passed += 1
        else:
            print("   [FAIL]")
            
    print(f"\nResult: {passed}/{len(cases)} passed.")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    try:
        test_media_fallback()
        test_typos()
    except Exception as e:
        print(f"Error: {e}")
