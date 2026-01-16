"""KB Update Row Action Node.

ACTION 4: Update embedding in Supabase knowledge_base table.
Follows AGENT.md: Action Nodes executam ações, não decidem fluxo.
"""

import os
from app.core.kb_indexer_state import KBIndexerState
from app.core.supabase_client import get_supabase


def kb_update_row(state: KBIndexerState) -> KBIndexerState:
    """Update the embedding column for a record in knowledge_base.
    
    Table: public.knowledge_base
    Filter: id = current_record.id
    Set: embedding = current_embedding (1536-dim vector)
    """
    if not state.current_record:
        state.record_action("KB_UPDATE_ROW", success=False, error="No current record")
        return state
    
    if not state.current_embedding:
        state.record_action("KB_UPDATE_ROW", success=False, error="No embedding to save")
        return state
    
    record_id = state.current_record.get("id")
    if not record_id:
        state.record_action("KB_UPDATE_ROW", success=False, error="Record has no ID")
        return state
    
    try:
        client = get_supabase()
        
        # Format embedding as string for vector column
        embedding_str = "[" + ",".join([str(x) for x in state.current_embedding]) + "]"
        
        result = (
            client.table("knowledge_base")
            .update({"embedding": embedding_str})
            .eq("id", record_id)
            .execute()
        )
        
        if result.data:
            state.processed_count += 1
            state.record_action("KB_UPDATE_ROW", success=True)
            
            if os.getenv("DEBUG"):
                print(f"[KB_UPDATE_ROW] Updated record {record_id}")
        else:
            state.record_action("KB_UPDATE_ROW", success=False, error="No rows updated")
        
    except Exception as e:
        state.record_action("KB_UPDATE_ROW", success=False, error=str(e))
        
        if os.getenv("DEBUG"):
            print(f"[KB_UPDATE_ROW] Error: {e}")
    
    return state
