"""Knowledge Base Indexer Graph.

Orchestrates the indexing flow following AGENT.md architecture.
"""

import os
from app.core.kb_indexer_state import KBIndexerState
from app.nodes.kb_fetch_pending import kb_fetch_pending
from app.nodes.kb_build_text import kb_build_text
from app.nodes.kb_embed import kb_embed
from app.nodes.kb_update_row import kb_update_row
from app.nodes.kb_indexer_decide import kb_indexer_decide
from app.nodes.kb_indexer_respond import kb_indexer_respond


def _process_single_record(state: KBIndexerState) -> KBIndexerState:
    """Process a single record: build text → embed → update.
    
    Pops record from pending_records and processes it.
    """
    if not state.pending_records:
        return state
    
    # Pop next record
    state.current_record = state.pending_records.pop(0)
    
    if os.getenv("DEBUG"):
        record_id = state.current_record.get("id", "?")
        print(f"[PROCESS] Processing record {record_id}")
    
    # Action 2: Build text
    state = kb_build_text(state)
    if not state.last_action_success:
        return state
    
    # Action 3: Generate embedding
    state = kb_embed(state)
    if not state.last_action_success:
        return state
    
    # Action 4: Update row
    state = kb_update_row(state)
    
    # Clear current record
    state.current_record = None
    state.current_text = None
    state.current_embedding = None
    
    return state


def run_kb_indexer() -> KBIndexerState:
    """Run the KB indexer graph.
    
    Flow:
    1. KB_FETCH_PENDING - fetch records needing embeddings
    2. KB_DECIDE - choose strategy
    3. If embed_and_upsert: loop through records
       - KB_BUILD_TEXT → KB_EMBED_1536 → KB_UPDATE_ROW
    4. KB_RESPOND - communicate result
    
    Returns final state with response_message.
    """
    state = KBIndexerState()
    
    print("\n" + "=" * 50)
    print("  KNOWLEDGE BASE INDEXER")
    print("=" * 50 + "\n")
    
    # Action 1: Fetch pending records
    state = kb_fetch_pending(state)
    
    # Decide: what strategy?
    state = kb_indexer_decide(state)
    
    # If error or done, go to respond
    if state.next_step == "respond":
        state = kb_indexer_respond(state)
        return state
    
    # Process loop
    total_to_process = len(state.pending_records)
    print(f"Processing {total_to_process} records...\n")
    
    while state.pending_records and state.last_action_success is not False:
        remaining = len(state.pending_records)
        print(f"  [{total_to_process - remaining + 1}/{total_to_process}] ", end="", flush=True)
        
        state = _process_single_record(state)
        
        if state.last_action_success:
            print("✓")
        else:
            print("✗")
            break
    
    # Decide after processing
    state = kb_indexer_decide(state)
    
    # Respond
    state = kb_indexer_respond(state)
    
    return state


def validate_indexer() -> dict:
    """Validate that all active records have embeddings.
    
    Returns dict with:
    - total_active: count of active records
    - total_with_embedding: count with non-null embedding
    - success: True if all active have embedding
    """
    from app.core.supabase_client import get_supabase
    
    client = get_supabase()
    
    # Count total active
    total_result = (
        client.table("knowledge_base")
        .select("id")
        .eq("is_active", True)
        .execute()
    )
    total_active = len(total_result.data) if total_result.data else 0
    
    # Count with NULL embedding
    null_result = (
        client.table("knowledge_base")
        .select("id")
        .eq("is_active", True)
        .is_("embedding", "null")
        .execute()
    )
    null_count = len(null_result.data) if null_result.data else 0
    
    total_with_embedding = total_active - null_count
    
    return {
        "total_active": total_active,
        "total_with_embedding": total_with_embedding,
        "pending": null_count,
        "success": null_count == 0,
    }
