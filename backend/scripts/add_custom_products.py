import os
import sys
import uuid
from datetime import datetime
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rag_engine.retriever import VectorRetriever
from app.rag_engine.embedder import EmbeddingService

def add_products():
    load_dotenv()
    
    tenant_id = "c35fe360-dc69-4997-9d1f-ae57f4d8a135"
    
    retriever = VectorRetriever()
    embedder = EmbeddingService()
    
    products = [
        {
            "tenant_id": tenant_id,
            "platform": "custom",
            "external_id": "custom-whey-001",
            "title": "100% Pure Whey Probiótica - 900g Baunilha",
            "description": "O 100% PURE WHEY® é o suplemento ideal para quem busca ganho de massa muscular e recuperação pós-treino. Formulado com proteína concentrada do soro do leite de alta qualidade, fornece 24g de proteína por porção, além de ser rico em BCAA e glutamina. Sabor baunilha cremoso, baixa gordura e sem adição de açúcares. Ideal para atletas de alta performance e entusiastas do fitness.",
            "price": 149.90,
            "currency": "BRL",
            "vendor": "Probiótica",
            "product_type": "Suplemento",
            "image_url": "https://raw.githubusercontent.com/nouvaris/assets/main/whey.png", # Placeholder or local path
            "url": "https://loja.probiotica.com.br/whey",
            "in_stock": True,
            "variants_count": 1,
            "tags": ["whey", "proteina", "probiotica", "fitness"],
            "categories": ["Suplementos", "Massa Muscular"]
        },
        {
            "tenant_id": tenant_id,
            "platform": "custom",
            "external_id": "custom-table-001",
            "title": "Mesa de Jantar Minimalista Walnut - 6 Lugares",
            "description": "Elegante mesa de jantar retangular fabricada em madeira maciça de nogueira (walnut) com acabamento acetinado. Design escandinavo com pés em aço carbono preto fosco. Medidas: 180cm (comprimento) x 90cm (largura) x 75cm (altura). Perfeita para ambientes modernos e sofisticados. Acomoda confortavelmente até 6 pessoas.",
            "price": 3890.00,
            "currency": "BRL",
            "vendor": "Nouvaris Home",
            "product_type": "Móveis",
            "image_url": "https://raw.githubusercontent.com/nouvaris/assets/main/table.png", # Placeholder or local path
            "url": "https://nouvaris.com/mesas/walnut",
            "in_stock": True,
            "variants_count": 1,
            "tags": ["mesa", "jantar", "madeira", "walnut", "minimalista"],
            "categories": ["Móveis", "Sala de Jantar"]
        }
    ]
    
    for p in products:
        print(f"Adding product: {p['title']}")
        
        # Combine title and description for better embedding
        text_to_embed = f"{p['title']} {p['description']} {p['vendor']} {p['product_type']}"
        embedding = embedder.embed_text(text_to_embed)
        
        # Add metadata and synced_at
        p["synced_at"] = datetime.now().isoformat()
        p["raw_data"] = p.copy()
        
        try:
            # We don't use upsert_product because it calls execute_upsert which might not be mapped in our simple client
            # Let's use the table().upsert().execute() pattern
            client = retriever.supabase
            p["embedding"] = embedding
            
            result = client.table("product_embeddings").upsert(p).execute_upsert()
            if result.data:
                print(f"Successfully added {p['title']}")
            else:
                print(f"Failed to add {p['title']}")
        except Exception as e:
            print(f"Error adding {p['title']}: {e}")

if __name__ == "__main__":
    add_products()
