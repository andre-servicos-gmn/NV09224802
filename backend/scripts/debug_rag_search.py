"""Debug script to test RAG search for products."""
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env
from dotenv import load_dotenv
load_dotenv()

TENANT_UUID = "c35fe360-dc69-4997-9d1f-ae57f4d8a135"

def test_rag_search(query: str):
    print(f"\n🔍 Testing RAG search for: '{query}'")
    print("-" * 50)
    
    try:
        from app.rag_engine.pipeline import RAGPipeline
        
        pipeline = RAGPipeline(tenant_id=TENANT_UUID)
        results = pipeline.search_products(query, limit=5)
        
        print(f"📦 Found {len(results)} products:")
        for i, p in enumerate(results, 1):
            print(f"  {i}. {p.get('title', 'N/A')}")
            print(f"     Price: {p.get('price', 'N/A')}")
            print(f"     In Stock: {p.get('in_stock', 'N/A')}")
        
        return results
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return []

def test_products_in_db():
    """List products in DB."""
    print(f"\n📊 Products in database for tenant:")
    print("-" * 50)
    
    from app.core.supabase_client import get_supabase
    sb = get_supabase()
    
    result = sb.table("product_embeddings").select(
        "id,title,in_stock"
    ).eq("tenant_id", TENANT_UUID).limit(20).execute()
    
    print(f"📦 Found {len(result.data)} products:")
    for i, p in enumerate(result.data, 1):
        print(f"  {i}. {p.get('title', 'N/A')} (in_stock: {p.get('in_stock')})")
    
    return result.data

if __name__ == "__main__":
    # List products first
    test_products_in_db()
    
    # Test RAG search  
    query = sys.argv[1] if len(sys.argv) > 1 else "colar summer"
    test_rag_search(query)
