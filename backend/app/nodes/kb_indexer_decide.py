"""KB Indexer Decide Node.

Decide node chooses strategy based on state.
Follows AGENT.md: Decide Node escolhe estratégia, mas NÃO chama APIs.
"""

import os
from app.core.kb_indexer_state import KBIndexerState


def kb_indexer_decide(state: KBIndexerState) -> KBIndexerState:
    """Decide next strategy based on current state.
    
    Strategies:
    - embed_and_upsert: If there are pending records to process
    - noop_done: If no pending records (all indexed)
    - error_stop: If last action failed
    
    This node does NOT call APIs or write to user.
    """
    
    # If last action failed, stop
    if state.last_action_success is False:
        state.last_strategy = "error_stop"
        state.next_step = "respond"
        
        if os.getenv("DEBUG"):
            print(f"[KB_DECIDE] Strategy: error_stop (last action failed)")
        
        return state
    
    # If there are pending records to process
    if state.pending_records:
        state.last_strategy = "embed_and_upsert"
        state.next_step = "process_next"
        
        if os.getenv("DEBUG"):
            print(f"[KB_DECIDE] Strategy: embed_and_upsert ({len(state.pending_records)} pending)")
        
        return state
    
    # No pending records - we're done
    state.last_strategy = "noop_done"
    state.next_step = "respond"
    
    if os.getenv("DEBUG"):
        print(f"[KB_DECIDE] Strategy: noop_done (all indexed)")
    
    return state
