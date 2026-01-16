"""KB Build Text Action Node.

ACTION 2: Build text from metadata for embedding generation.
Follows AGENT.md: Action Nodes executam ações, não decidem fluxo.
"""

import os
import json
from app.core.kb_indexer_state import KBIndexerState


def kb_build_text(state: KBIndexerState) -> KBIndexerState:
    """Build text from record metadata for embedding.
    
    Text format:
        Título: {metadata.title}
        Categoria: {category}
        Conteúdo: {metadata.content}
        Keywords: {metadata.keywords}
    
    This improves semantic retrieval and ensures grounding.
    """
    record = state.current_record
    
    if not record:
        state.record_action("KB_BUILD_TEXT", success=False, error="No current record")
        return state
    
    try:
        metadata = record.get("metadata", {})
        
        # Parse metadata if it's a JSON string
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {"content": metadata}
        
        # Build text parts
        parts = []
        
        title = metadata.get("title", "")
        if title:
            parts.append(f"Título: {title}")
        
        category = record.get("category", "")
        if category:
            parts.append(f"Categoria: {category}")
        
        content = metadata.get("content", "")
        if content:
            parts.append(f"Conteúdo: {content}")
        
        keywords = metadata.get("keywords", [])
        if keywords:
            if isinstance(keywords, list):
                keywords = ", ".join(keywords)
            parts.append(f"Keywords: {keywords}")
        
        # Fallback: use raw metadata if no structured content
        if not parts:
            parts.append(str(metadata))
        
        state.current_text = "\n".join(parts)
        state.record_action("KB_BUILD_TEXT", success=True)
        
        if os.getenv("DEBUG"):
            print(f"[KB_BUILD_TEXT] Text length: {len(state.current_text)}")
        
    except Exception as e:
        state.record_action("KB_BUILD_TEXT", success=False, error=str(e))
        state.current_text = None
        
        if os.getenv("DEBUG"):
            print(f"[KB_BUILD_TEXT] Error: {e}")
    
    return state
