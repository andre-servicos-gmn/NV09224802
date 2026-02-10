"""Store Q&A response generation using RAG from Supabase + memory context."""

import os
import random
from app.core.llm_humanized import generate_humanized_response
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def store_qa_respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Generate Store Q&A response using the unified Response Synthesizer."""
    
    # Delegate everything to the unified logic
    # It handles RAG, Memory, Tone, and Missing Info internally now.
    try:
        response = generate_humanized_response(
            state=state,
            tenant=tenant,
            domain="store_qa",
            categories=None # Let it figure out from intent/message
        )
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[store_qa_respond] Error generating response: {e}")
        response = "Desculpe, tive um problema técnico. Pode repetir?"

    # Check for resolution tag logic (if the Synthesizer decides to use it based on prompt instructions)
    # Note: The new prompt doesn't explicitly mention [RESOLVED], but we can infer resolution 
    # if the user is saying goodbye or thank you.
    # For now, we trust the LLM's natural closing.
    
    # If explicit strategies are needed, we can set them in state.metadata before calling generate.
    
    state.last_bot_message = response
    state.last_action = "generate_response"
    state.last_action_success = bool(response)
    
    return state

