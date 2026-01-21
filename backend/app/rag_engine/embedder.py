"""
Embedding Service for Nouvaris RAG.

Generates vector embeddings from text using OpenAI's embedding models.
Includes caching to avoid redundant API calls.
"""

import hashlib
import os
from typing import Optional

from openai import OpenAI


class EmbeddingService:
    """Generates and caches text embeddings using OpenAI."""
    
    # Default model: text-embedding-3-small
    # - 1536 dimensions
    # - $0.00002 per 1K tokens
    # - Best cost/quality ratio for most use cases
    DEFAULT_MODEL = "text-embedding-3-small"
    DIMENSIONS = 1536
    
    def __init__(self, model: Optional[str] = None):
        """Initialize embedding service.
        
        Args:
            model: OpenAI embedding model name. Defaults to text-embedding-3-small.
        """
        self.client = OpenAI()
        self.model = model or os.getenv("OPENAI_EMBEDDING_MODEL", self.DEFAULT_MODEL)
        self._cache: dict[str, list[float]] = {}
    
    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text.
        
        Args:
            text: Text to embed. Will be truncated if too long.
            
        Returns:
            List of floats representing the embedding vector.
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * self.DIMENSIONS
        
        # Truncate text to avoid token limits (roughly 8K tokens max)
        text = text[:32000]  # ~8K tokens
        
        # Check cache
        cache_key = self._cache_key(text)
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Call OpenAI
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
        )
        
        embedding = response.data[0].embedding
        
        # Cache result
        self._cache[cache_key] = embedding
        
        return embedding
    
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed.
            
        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []
        
        # Filter out empty texts and track indices
        valid_texts = []
        valid_indices = []
        results = [None] * len(texts)
        
        for i, text in enumerate(texts):
            if text and text.strip():
                cache_key = self._cache_key(text)
                if cache_key in self._cache:
                    results[i] = self._cache[cache_key]
                else:
                    valid_texts.append(text[:32000])
                    valid_indices.append(i)
            else:
                results[i] = [0.0] * self.DIMENSIONS
        
        # Batch call for non-cached texts
        if valid_texts:
            response = self.client.embeddings.create(
                model=self.model,
                input=valid_texts,
            )
            
            for j, embedding_data in enumerate(response.data):
                idx = valid_indices[j]
                embedding = embedding_data.embedding
                results[idx] = embedding
                
                # Cache result
                cache_key = self._cache_key(texts[idx])
                self._cache[cache_key] = embedding
        
        return results
    
    def embed_product(self, product) -> list[float]:
        """Generate embedding for a UnifiedProduct.
        
        Args:
            product: UnifiedProduct instance.
            
        Returns:
            Embedding vector for the product.
        """
        text = product.to_embedding_text()
        return self.embed_text(text)
    
    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        self._cache.clear()
    
    def _cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(text.encode()).hexdigest()
    
    @property
    def cache_size(self) -> int:
        """Return current cache size."""
        return len(self._cache)
