"""
Vector Retriever for Nouvaris RAG.

Searches for similar products in Supabase pgvector using semantic similarity.
Uses the project's custom SupabaseClient instead of the official SDK.
"""

import os
from typing import Optional

import httpx

from app.core.supabase_client import get_supabase, SupabaseClient
from app.rag_engine.embedder import EmbeddingService


class VectorRetriever:
    """Retrieves products from Supabase pgvector by semantic similarity."""
    
    def __init__(self, embedder: Optional[EmbeddingService] = None):
        """Initialize vector retriever.
        
        Args:
            embedder: EmbeddingService instance. Creates new one if not provided.
        """
        self.supabase: SupabaseClient = get_supabase()
        self.embedder = embedder or EmbeddingService()
    
    def search_products(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        only_in_stock: bool = False,
    ) -> list[dict]:
        """Search products by semantic similarity.
        
        Args:
            tenant_id: UUID of the tenant.
            query: User's search query.
            limit: Maximum number of results to return.
            only_in_stock: If True, only return products that are in stock.
            
        Returns:
            List of product dicts with similarity scores.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"[RETRIEVER] search_products called: tenant={tenant_id}, query='{query}', limit={limit}")
        
        if not query or not query.strip():
            logger.warning("[RETRIEVER] Empty query, returning []")
            return []
        
        # Generate query embedding
        logger.info(f"[RETRIEVER] Generating embedding for query: '{query}'")
        query_embedding = self.embedder.embed_text(query)
        logger.info(f"[RETRIEVER] Got embedding vector of length {len(query_embedding)}")
        
        # Call Supabase RPC function via REST
        result = self._call_rpc(
            "search_products_by_embedding",
            {
                "query_embedding": query_embedding,
                "tenant_uuid": tenant_id,
                "match_count": limit,
                "only_in_stock": only_in_stock,
            }
        )
        
        logger.info(f"[RETRIEVER] RPC returned {len(result)} products")
        for i, p in enumerate(result[:3]):
            logger.info(f"[RETRIEVER]   {i+1}. {p.get('title', 'N/A')} (similarity={p.get('similarity', 'N/A'):.4f})")
        
        return result
    
    def _call_rpc(self, function_name: str, params: dict) -> list[dict]:
        """Call a Supabase RPC function.
        
        Args:
            function_name: Name of the RPC function.
            params: Parameters to pass to the function.
            
        Returns:
            List of results from the function.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        url = f"{self.supabase.url}/rest/v1/rpc/{function_name}"
        logger.info(f"[RETRIEVER] Calling RPC: {function_name}")
        
        try:
            response = httpx.post(
                url,
                json=params,
                headers=self.supabase.headers,
                timeout=30,
            )
            logger.info(f"[RETRIEVER] RPC response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"[RETRIEVER] RPC error response: {response.text[:500]}")
            
            response.raise_for_status()
            
            result = response.json()
            return result if isinstance(result, list) else []
            
        except Exception as e:
            logger.error(f"[RETRIEVER] RPC call failed: {e}", exc_info=True)
            raise
    
    def get_product_by_external_id(
        self,
        tenant_id: str,
        platform: str,
        external_id: str,
    ) -> Optional[dict]:
        """Get a specific product by its external ID.
        
        Args:
            tenant_id: UUID of the tenant.
            platform: Platform name (shopify, woocommerce, etc.)
            external_id: Product ID in the original platform.
            
        Returns:
            Product dict or None if not found.
        """
        result = (
            self.supabase.table("product_embeddings")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("platform", platform)
            .eq("external_id", external_id)
            .execute()
        )
        
        if result.data:
            return result.data[0]
        return None
    
    def upsert_product(
        self,
        product_data: dict,
        embedding: list[float],
    ) -> dict:
        """Insert or update a product with its embedding.
        
        Args:
            product_data: Product data dict from UnifiedProduct.to_db_dict().
            embedding: Vector embedding for the product.
            
        Returns:
            The upserted product data.
        """
        # Add embedding to product data (as list, will be converted by Supabase)
        product_data["embedding"] = embedding
        
        # Use upsert
        result = (
            self.supabase.table("product_embeddings")
            .upsert(product_data, on_conflict="tenant_id,platform,external_id")
            .execute_upsert()
        )
        
        return result.data[0] if result.data else {}
    
    def delete_product(
        self,
        tenant_id: str,
        platform: str,
        external_id: str,
    ) -> bool:
        """Delete a product from the vector store.
        
        Args:
            tenant_id: UUID of the tenant.
            platform: Platform name.
            external_id: Product ID in the original platform.
            
        Returns:
            True if deleted, False if not found.
        """
        url = f"{self.supabase.url}/rest/v1/product_embeddings"
        
        params = {
            "tenant_id": f"eq.{tenant_id}",
            "platform": f"eq.{platform}",
            "external_id": f"eq.{external_id}",
        }
        
        response = httpx.delete(
            url,
            params=params,
            headers=self.supabase.headers,
            timeout=10,
        )
        response.raise_for_status()
        
        # Check if anything was deleted
        result = response.json()
        return len(result) > 0 if isinstance(result, list) else False
    
    def count_products(self, tenant_id: str) -> int:
        """Count total products for a tenant.
        
        Args:
            tenant_id: UUID of the tenant.
            
        Returns:
            Number of products indexed.
        """
        result = (
            self.supabase.table("product_embeddings")
            .select("id")
            .eq("tenant_id", tenant_id)
            .execute()
        )
        
        return len(result.data) if result.data else 0
    
    def list_products(
        self,
        tenant_id: str,
        limit: int = 50,
    ) -> list[dict]:
        """List all products for a tenant.
        
        Args:
            tenant_id: UUID of the tenant.
            limit: Maximum results.
            
        Returns:
            List of product dicts.
        """
        result = (
            self.supabase.table("product_embeddings")
            .select("id, title, description, price, image_url, in_stock, platform, external_id, synced_at")
            .eq("tenant_id", tenant_id)
            .order("title")
            .limit(limit)
            .execute()
        )
        
        return result.data or []
