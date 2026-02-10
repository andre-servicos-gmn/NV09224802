
"""
Resolution action node.
Closes the conversation and resets state.
"""

import os
from app.core.state import ConversationState
from app.api.handoff import close_conversation, CloseRequest
from app.core.supabase_client import get_supabase

def action_resolve(state: ConversationState) -> ConversationState:
    """Action that closes the conversation via API logic."""
    if os.getenv("DEBUG"):
        print(f"[action_resolve] Closing conversation {state.session_id}")
    
    try:
        # We need the conversation ID from session ID
        # Since state only has session_id, we fetch it
        supabase = get_supabase()
        conv = supabase.table("conversations").select("id").eq("session_id", state.session_id).eq("tenant_id", state.tenant_id).single().execute()
        
        if conv.data:
            conversation_id = conv.data["id"]
            
            # Use the existing close logic from handoff API
            # Ideally we extract the logic to a service function, 
            # but for now we mimic the update since close_conversation is an async route handler
            
            # Reset state dict (logic reused from handoff.py)
            reset_state = {
                "intent": "general",
                "cart_items": [],
                "selected_products": [],
                "checkout_link": None,
                "soft_context": {},
                "blocking_info": [],
                "rag_context": None,
                "order_id": None,
                # "ticket_opened": False, # Was not in new state explicit fields, maybe soft_context
                # "needs_resolution": False, # Removed
                "last_action": None,
                "last_strategy": None,
                "frustration_level": 0,
                "needs_handoff": False,
                "handoff_reason": None,
                # Maintain long-term memory
                "conversation_history": [],
                "facts": state.facts
            }

            supabase.table("conversations").update({
                "status": "closed",
                "state": reset_state
            }).eq("id", conversation_id).execute()
            
            state.next_step = "END"
            state.last_action_success = True
            
        else:
            if os.getenv("DEBUG"):
                print("[action_resolve] Conversation not found")
            state.last_action_success = False

    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[action_resolve] Error: {e}")
        state.last_action_success = False
        
    return state
