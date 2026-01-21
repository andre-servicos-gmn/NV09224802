"""
Sync Service for Nouvaris RAG.

Orchestrates product synchronization from e-commerce platforms to vector store.
"""

import os
from datetime import datetime
from typing import Optional

from app.adapters.base_adapter import BasePlatformAdapter
from app.adapters.shopify_adapter import ShopifyAdapter
from app.models.unified_product import UnifiedProduct
from app.rag_engine.embedder import EmbeddingService
from app.rag_engine.retriever import VectorRetriever


class SyncService:
    """Orchestrates synchronization from platforms to vector store."""
    
    def __init__(
        self,
        embedder: Optional[EmbeddingService] = None,
        retriever: Optional[VectorRetriever] = None,
    ):
        """Initialize sync service.
        
        Args:
            embedder: Optional EmbeddingService instance.
            retriever: Optional VectorRetriever instance.
        """
        self.embedder = embedder or EmbeddingService()
        self.retriever = retriever or VectorRetriever(self.embedder)
        self.debug = os.getenv("DEBUG", "").lower() in ("true", "1")
    
    def get_adapter_for_tenant(
        self,
        tenant_id: str,
        platform: str,
        credentials: dict,
    ) -> BasePlatformAdapter:
        """Get appropriate adapter for platform.
        
        Args:
            tenant_id: UUID of the tenant.
            platform: Platform name.
            credentials: Platform credentials.
            
        Returns:
            Platform adapter instance.
            
        Raises:
            ValueError: If platform is not supported.
        """
        if platform == "shopify":
            return ShopifyAdapter(
                tenant_id=tenant_id,
                store_domain=credentials["store_domain"],
                access_token=credentials["access_token"],
                api_version=credentials.get("api_version", "2024-01"),
                webhook_secret=credentials.get("webhook_secret"),
            )
        
        # Future: add more platforms
        raise ValueError(f"Unsupported platform: {platform}")
    
    def sync_full_catalog(
        self,
        tenant_id: str,
        platform: str,
        credentials: dict,
        batch_size: int = 50,
    ) -> dict:
        """Sync entire product catalog from platform to vector store.
        
        Args:
            tenant_id: UUID of the tenant.
            platform: Platform name.
            credentials: Platform credentials.
            batch_size: Number of products to embed in each batch.
            
        Returns:
            Sync result stats.
        """
        start_time = datetime.utcnow()
        
        adapter = self.get_adapter_for_tenant(tenant_id, platform, credentials)
        
        if self.debug:
            print(f"[Sync] Starting full sync for tenant {tenant_id} from {platform}")
        
        # Fetch all products
        products = adapter.fetch_all_products()
        total = len(products)
        
        if self.debug:
            print(f"[Sync] Fetched {total} products from {platform}")
        
        # Process in batches
        synced = 0
        errors = 0
        
        for i in range(0, total, batch_size):
            batch = products[i:i + batch_size]
            
            # Generate embeddings for batch
            texts = [p.to_embedding_text() for p in batch]
            embeddings = self.embedder.embed_texts(texts)
            
            # Upsert each product
            for j, product in enumerate(batch):
                try:
                    self.retriever.upsert_product(
                        product_data=product.to_db_dict(),
                        embedding=embeddings[j],
                    )
                    synced += 1
                except Exception as e:
                    errors += 1
                    if self.debug:
                        print(f"[Sync] Error syncing product {product.external_id}: {e}")
            
            if self.debug:
                print(f"[Sync] Progress: {synced}/{total} products synced")
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        result = {
            "tenant_id": tenant_id,
            "platform": platform,
            "total_products": total,
            "synced": synced,
            "errors": errors,
            "duration_seconds": duration,
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
        }
        
        if self.debug:
            print(f"[Sync] Complete: {synced} products synced in {duration:.1f}s")
        
        return result
    
    def sync_single_product(
        self,
        tenant_id: str,
        platform: str,
        credentials: dict,
        product_id: str,
    ) -> Optional[dict]:
        """Sync a single product.
        
        Args:
            tenant_id: UUID of the tenant.
            platform: Platform name.
            credentials: Platform credentials.
            product_id: Product ID in the platform.
            
        Returns:
            Synced product data or None if not found.
        """
        adapter = self.get_adapter_for_tenant(tenant_id, platform, credentials)
        
        product = adapter.fetch_product_by_id(product_id)
        if not product:
            return None
        
        # Generate embedding
        embedding = self.embedder.embed_product(product)
        
        # Upsert
        result = self.retriever.upsert_product(
            product_data=product.to_db_dict(),
            embedding=embedding,
        )
        
        return result
    
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
            external_id: Product ID in the platform.
            
        Returns:
            True if deleted, False otherwise.
        """
        return self.retriever.delete_product(
            tenant_id=tenant_id,
            platform=platform,
            external_id=external_id,
        )
    
    def process_webhook(
        self,
        tenant_id: str,
        platform: str,
        credentials: dict,
        event_type: str,
        payload: dict,
    ) -> dict:
        """Process a webhook event from a platform.
        
        Args:
            tenant_id: UUID of the tenant.
            platform: Platform name.
            credentials: Platform credentials.
            event_type: Webhook event type.
            payload: Webhook payload.
            
        Returns:
            Processing result.
        """
        adapter = self.get_adapter_for_tenant(tenant_id, platform, credentials)
        
        product = adapter.parse_webhook_event(event_type, payload)
        if not product:
            return {"status": "ignored", "event": event_type}
        
        if event_type == "products/delete":
            deleted = self.delete_product(
                tenant_id=tenant_id,
                platform=platform,
                external_id=product.external_id,
            )
            return {"status": "deleted" if deleted else "not_found", "external_id": product.external_id}
        
        # Create or update
        embedding = self.embedder.embed_product(product)
        self.retriever.upsert_product(
            product_data=product.to_db_dict(),
            embedding=embedding,
        )
        
        return {"status": "synced", "external_id": product.external_id, "title": product.title}
