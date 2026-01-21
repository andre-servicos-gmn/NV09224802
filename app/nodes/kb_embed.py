"""KB Embed Action Node.

ACTION 3: Generate 1536-dimensional embedding via OpenAI.
Follows AGENT.md: Action Nodes executam ações, não decidem fluxo.
"""

import os
from app.core.kb_indexer_state import KBIndexerState


EXPECTED_DIMENSIONS = 1536
EMBEDDING_MODEL = "text-embedding-3-small"


def kb_embed(state: KBIndexerState) -> KBIndexerState:
    """Generate embedding for the current text.
    
    Uses OpenAI text-embedding-3-small (1536 dimensions).
    Validates that output is exactly 1536 dimensions.
    
    If dimension mismatch, action FAILS.
    """
    if not state.current_text:
        state.record_action("KB_EMBED_1536", success=False, error="No text to embed")
        return state
    
    try:
        from langchain_openai import OpenAIEmbeddings
        
        embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
        vector = embeddings.embed_query(state.current_text)
        
        # Validate dimensions
        if len(vector) != EXPECTED_DIMENSIONS:
            state.record_action(
                "KB_EMBED_1536", 
                success=False, 
                error=f"Dimension mismatch: got {len(vector)}, expected {EXPECTED_DIMENSIONS}"
            )
            state.current_embedding = None
            return state
        
        state.current_embedding = vector
        state.record_action("KB_EMBED_1536", success=True)
        
        if os.getenv("DEBUG"):
            print(f"[KB_EMBED_1536] Generated {len(vector)}-dim embedding")
        
    except Exception as e:
        state.record_action("KB_EMBED_1536", success=False, error=str(e))
        state.current_embedding = None
        
        if os.getenv("DEBUG"):
            print(f"[KB_EMBED_1536] Error: {e}")
    
    return state
