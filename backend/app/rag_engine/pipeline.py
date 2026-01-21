"""
RAG Pipeline for Nouvaris.

Orchestrates the full RAG flow: query → embed → retrieve → format context.
Used by LangGraph agents to get relevant product context for responses.
"""

from typing import Optional

from app.rag_engine.embedder import EmbeddingService
from app.rag_engine.retriever import VectorRetriever


class RAGPipeline:
    """Orchestrates semantic search and context generation for LLM."""
    
    def __init__(
        self,
        tenant_id: str,
        embedder: Optional[EmbeddingService] = None,
        retriever: Optional[VectorRetriever] = None,
    ):
        """Initialize RAG pipeline.
        
        Args:
            tenant_id: UUID of the tenant for scoped searches.
            embedder: Optional EmbeddingService instance.
            retriever: Optional VectorRetriever instance.
        """
        self.tenant_id = tenant_id
        self.embedder = embedder or EmbeddingService()
        self.retriever = retriever or VectorRetriever(self.embedder)
    
    def search_products(
        self,
        query: str,
        limit: int = 5,
        only_in_stock: bool = False,
    ) -> list[dict]:
        """Search for products semantically.
        
        Args:
            query: User's natural language query.
            limit: Maximum results to return.
            only_in_stock: Filter for in-stock products only.
            
        Returns:
            List of matching products with similarity scores.
        """
        return self.retriever.search_products(
            tenant_id=self.tenant_id,
            query=query,
            limit=limit,
            only_in_stock=only_in_stock,
        )
    
    def retrieve_context(
        self,
        query: str,
        context_type: str = "product",
        top_k: int = 5,
    ) -> str:
        """Retrieve and format context for LLM.
        
        Args:
            query: User's query.
            context_type: Type of context ("product", "policy", "faq").
            top_k: Number of results to include in context.
            
        Returns:
            Formatted context string for LLM prompt.
        """
        if context_type == "product":
            products = self.search_products(query, limit=top_k)
            return self._format_product_context(products)
        
        # Future: support other context types
        return ""
    
    def _format_product_context(self, products: list[dict]) -> str:
        """Format products as context for LLM.
        
        Args:
            products: List of product dicts from search.
            
        Returns:
            Formatted string with product information.
        """
        if not products:
            return "[Produtos Encontrados]\nNenhum produto encontrado para esta busca."
        
        lines = ["[Produtos Encontrados]"]
        
        for i, p in enumerate(products, 1):
            title = p.get("title", "Produto")
            price = p.get("price")
            currency = p.get("currency", "BRL")
            in_stock = p.get("in_stock", True)
            similarity = p.get("similarity", 0)
            
            # Format price
            if price:
                if currency == "BRL":
                    price_str = f"R$ {price:.2f}"
                else:
                    price_str = f"{currency} {price:.2f}"
            else:
                price_str = "Preço sob consulta"
            
            # Format availability
            stock_str = "✓ Em estoque" if in_stock else "✗ Indisponível"
            
            lines.append(f"{i}. {title} - {price_str} ({stock_str})")
            
            # Add description if available (truncated)
            description = p.get("description", "")
            if description:
                lines.append(f"   {description[:100]}...")
            
            # Add tags if available
            tags = p.get("tags")
            if tags:
                lines.append(f"   Tags: {', '.join(tags[:5])}")
        
        return "\n".join(lines)
    
    def get_products_for_state(
        self,
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        """Get products formatted for ConversationState.selected_products.
        
        Args:
            query: User's search query.
            limit: Maximum results.
            
        Returns:
            List of product dicts compatible with existing state format.
        """
        products = self.search_products(query, limit=limit)
        
        return [
            {
                "product_id": p.get("external_id", ""),
                "title": p.get("title", ""),
                "description": p.get("description", ""),  # Include for material questions
                "price": str(p.get("price", "")),
                "image_url": p.get("image_url"),
                "url": p.get("url"),
                "in_stock": p.get("in_stock", True),
                "tags": p.get("tags", []),
                "has_variants": False,  # Will be enriched later if needed
            }
            for p in products
        ]
