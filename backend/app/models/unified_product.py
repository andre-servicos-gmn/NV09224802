"""
Unified Product Schema for multi-platform e-commerce RAG.

This model normalizes product data from different platforms (Shopify, WooCommerce,
VTEX, NuvemShop) into a single schema for embedding and retrieval.
"""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field
import re


class UnifiedProduct(BaseModel):
    """Platform-agnostic product schema for RAG indexing."""
    
    # Identity
    tenant_id: str
    platform: str  # "shopify", "woocommerce", "vtex", "nuvemshop"
    external_id: str  # ID in the original platform
    
    # Core fields
    title: str
    description: str = ""
    price: Decimal = Decimal("0.00")
    currency: str = "BRL"
    
    # Categorization
    tags: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    product_type: str | None = None
    vendor: str | None = None
    
    # Media
    image_url: str | None = None
    images: list[str] = Field(default_factory=list)
    
    # Availability
    url: str | None = None
    in_stock: bool = True
    variants_count: int = 1
    
    # Metadata (raw platform data)
    raw_data: dict = Field(default_factory=dict)
    synced_at: datetime | None = None
    
    def to_embedding_text(self) -> str:
        """Generate text for embedding.
        
        Combines title, description, price, tags, and categories into a single
        text string optimized for semantic search.
        
        Returns:
            String ready for embedding generation.
        """
        # Clean HTML from description
        clean_description = self._strip_html(self.description)
        
        parts = [
            self.title,
            clean_description[:500] if clean_description else "",
            f"Preço: R$ {self.price}" if self.price else "",
            f"Tags: {', '.join(self.tags)}" if self.tags else "",
            f"Categorias: {', '.join(self.categories)}" if self.categories else "",
            f"Tipo: {self.product_type}" if self.product_type else "",
            f"Marca: {self.vendor}" if self.vendor else "",
        ]
        
        return "\n".join(p for p in parts if p).strip()
    
    def _strip_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        if not text:
            return ""
        return re.sub(r'<[^>]+>', '', text).strip()
    
    def to_db_dict(self) -> dict:
        """Convert to dictionary for database insertion.
        
        Returns:
            Dict ready for Supabase upsert.
        """
        return {
            "tenant_id": self.tenant_id,
            "platform": self.platform,
            "external_id": self.external_id,
            "title": self.title,
            "description": self._strip_html(self.description),
            "price": float(self.price) if self.price else None,
            "currency": self.currency,
            "tags": self.tags,
            "categories": self.categories,
            "product_type": self.product_type,
            "vendor": self.vendor,
            "image_url": self.image_url,
            "url": self.url,
            "in_stock": self.in_stock,
            "variants_count": self.variants_count,
            "raw_data": self.raw_data,
            "synced_at": datetime.utcnow().isoformat(),
        }
    
    @classmethod
    def from_db_row(cls, row: dict) -> "UnifiedProduct":
        """Create UnifiedProduct from database row.
        
        Args:
            row: Dict from Supabase query result.
            
        Returns:
            UnifiedProduct instance.
        """
        return cls(
            tenant_id=row["tenant_id"],
            platform=row["platform"],
            external_id=row["external_id"],
            title=row["title"],
            description=row.get("description") or "",
            price=Decimal(str(row["price"])) if row.get("price") else Decimal("0"),
            currency=row.get("currency", "BRL"),
            tags=row.get("tags") or [],
            categories=row.get("categories") or [],
            product_type=row.get("product_type"),
            vendor=row.get("vendor"),
            image_url=row.get("image_url"),
            url=row.get("url"),
            in_stock=row.get("in_stock", True),
            variants_count=row.get("variants_count", 1),
            raw_data=row.get("raw_data") or {},
            synced_at=row.get("synced_at"),
        )
