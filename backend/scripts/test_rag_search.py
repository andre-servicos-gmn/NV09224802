#!/usr/bin/env python
"""Test RAG semantic search."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.tenancy import TenantRegistry
from app.rag_engine.pipeline import RAGPipeline

registry = TenantRegistry()
tenant = registry.get("demo")

print(f"Tenant: {tenant.name} (UUID: {tenant.uuid})")
print()

pipeline = RAGPipeline(tenant_id=tenant.uuid)

queries = [
    "vestido para casamento",
    "colar elegante",
    "bracelet gold",
    "acessório para presente",
]

for query in queries:
    print(f"Query: '{query}'")
    results = pipeline.search_products(query, limit=3)
    print(f"  Found {len(results)} products:")
    for r in results:
        sim = r.get("similarity", 0)
        print(f"    - {r['title']} (R$ {r['price']}) - similarity: {sim:.3f}")
    print()
