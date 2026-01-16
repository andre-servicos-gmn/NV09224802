"""Knowledge Base Indexer State Model.

Follows AGENT.md: State armazena fatos, nunca decisões.
"""

from pydantic import BaseModel, Field


class KBIndexerState(BaseModel):
    """State for the Knowledge Base Indexer agent.
    
    This state holds ONLY facts about the indexing process.
    No decisions or logic should be stored here.
    """
    
    # Intent (set by router, never changed)
    intent: str = "kb_index"
    
    # Last action executed
    last_action: str | None = None
    
    # Strategy chosen by decide node
    last_strategy: str | None = None
    
    # Whether last action succeeded
    last_action_success: bool | None = None
    
    # Records pending embedding (fetched by KB_FETCH_PENDING)
    pending_records: list[dict] = Field(default_factory=list)
    
    # Current record being processed
    current_record: dict | None = None
    
    # Text built for embedding (from KB_BUILD_TEXT)
    current_text: str | None = None
    
    # Embedding generated (from KB_EMBED_1536)
    current_embedding: list[float] | None = None
    
    # Counters
    processed_count: int = 0
    error_count: int = 0
    
    # Error details
    error_message: str | None = None
    
    # Next step (set by decide node)
    next_step: str | None = None
    
    # Final message (set by respond node)
    response_message: str | None = None
    
    def record_action(self, action: str, success: bool, error: str | None = None) -> None:
        """Record the result of an action."""
        self.last_action = action
        self.last_action_success = success
        if error:
            self.error_message = error
            self.error_count += 1
