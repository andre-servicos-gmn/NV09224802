"""KB Fetch Pending Action Node.

ACTION 1: Fetch records from knowledge_base where embedding IS NULL.
Follows AGENT.md: Action Nodes executam ações, não decidem fluxo.
"""

import os
from app.core.kb_indexer_state import KBIndexerState
from app.core.supabase_client import get_supabase


BATCH_SIZE = 50


def kb_fetch_pending(state: KBIndexerState) -> KBIndexerState:
    """Fetch pending records that need embeddings.
    
    Queries: knowledge_base WHERE is_active=true AND embedding IS NULL
    Stores results in state.pending_records
    
    This action does NOT decide what to do next.
    """
    try:
        client = get_supabase()
        
        result = (
            client.table("knowledge_base")
            .select("id, tenant_id, category, metadata")
            .eq("is_active", True)
            .is_("embedding", "null")
            .limit(BATCH_SIZE)
            .execute()
        )
        
        state.pending_records = result.data if result.data else []
        state.record_action("KB_FETCH_PENDING", success=True)
        
        if os.getenv("DEBUG"):
            print(f"[KB_FETCH_PENDING] Found {len(state.pending_records)} pending records")
        
    except Exception as e:
        state.record_action("KB_FETCH_PENDING", success=False, error=str(e))
        state.pending_records = []
        
        if os.getenv("DEBUG"):
            print(f"[KB_FETCH_PENDING] Error: {e}")
    
    return state
