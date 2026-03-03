import asyncio
import os
import sys

# Add parent path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.nodes.support_respond import support_respond

def main():
    # Set up fake tenant
    tenant = TenantConfig(
        tenant_id="demo",
        name="Loja Demo",
        brand_voice="simpático"
    )

    # Set up state
    state = ConversationState(
        tenant_id="demo",
        session_id="test1234",
        domain="support",
        intent="order_status",
        last_user_message="gostei muito da minha compra, to esperando chegar ansioso",
        metadata={"dummy": "data"}   
    )

    # Call the node
    print("Running node...")
    try:
        state = support_respond(state, tenant)
        print(f"Result: {state.last_bot_message}")
        if "response_error" in state.metadata:
            print(f"Error caught: {state.metadata['response_error']}")
    except Exception as e:
        print(f"Unhandled Exception: {e}")

if __name__ == "__main__":
    main()
