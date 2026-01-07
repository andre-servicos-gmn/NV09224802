"""Script to seed knowledge base with vector embeddings.

This script generates embeddings for knowledge base entries and inserts them
into Supabase with proper tenant isolation.

Usage:
    python scripts/seed_knowledge_base.py --tenant demo
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from langchain_openai import OpenAIEmbeddings
from supabase import create_client


def get_supabase_client():
    """Get Supabase client."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def get_or_create_tenant(client, tenant_name: str) -> str:
    """Get tenant UUID or create if doesn't exist."""
    # Try to find existing tenant
    result = client.table("tenants").select("id").eq("name", tenant_name).execute()
    if result.data:
        return result.data[0]["id"]
    
    # Create new tenant with demo UUID for "Demo Store"
    if tenant_name.lower() == "demo store" or tenant_name.lower() == "demo":
        tenant_id = "00000000-0000-0000-0000-000000000001"
    else:
        import uuid
        tenant_id = str(uuid.uuid4())
    
    client.table("tenants").upsert({
        "id": tenant_id,
        "name": tenant_name,
        "store_domain": f"{tenant_name.lower().replace(' ', '')}.myshopify.com",
        "brand_voice": "profissional e cordial, mas acolhedor. Use linguagem clara e direta. Mostre empatia quando o cliente tem problemas.",
        "handoff_message": "Vou te conectar com um de nossos especialistas para resolver isso.",
    }).execute()
    
    return tenant_id


# =============================================================================
# KNOWLEDGE BASE DATA
# =============================================================================

KNOWLEDGE_DATA = [
    # SHIPPING
    {
        "category": "shipping",
        "question": "Prazo de entrega padrão",
        "answer": "O prazo de entrega é de 5 a 12 dias úteis para capitais e 7 a 15 dias úteis para interior. Após o envio, você recebe o código de rastreio por email e SMS."
    },
    {
        "category": "shipping",
        "question": "Como rastrear meu pedido",
        "answer": "Você pode rastrear seu pedido usando o código de rastreio enviado por email. Acesse nosso site e clique em 'Rastrear Pedido' ou use o link direto dos Correios."
    },
    {
        "category": "shipping",
        "question": "Frete grátis",
        "answer": "Oferecemos frete grátis para compras acima de R$ 299,00 em todo o Brasil. Para valores menores, o frete é calculado pelo CEP no checkout."
    },
    {
        "category": "shipping",
        "question": "Entrega expressa",
        "answer": "Temos opção de entrega expressa via Sedex para capitais, com prazo de 2 a 4 dias úteis. O custo adicional é mostrado no checkout."
    },
    {
        "category": "shipping",
        "question": "Pedido atrasado",
        "answer": "Se seu pedido passou do prazo estimado, entre em contato informando o número do pedido. Verificaremos com a transportadora e daremos retorno em até 24 horas."
    },
    
    # PAYMENT
    {
        "category": "payment",
        "question": "Formas de pagamento aceitas",
        "answer": "Aceitamos cartão de crédito (Visa, Mastercard, Elo, Amex) em até 12x sem juros, PIX com 5% de desconto, e boleto bancário com vencimento em 3 dias úteis."
    },
    {
        "category": "payment",
        "question": "Parcelamento sem juros",
        "answer": "Parcelamos em até 12x sem juros no cartão de crédito para compras acima de R$ 100,00. Para valores menores, o parcelamento máximo é 3x."
    },
    {
        "category": "payment",
        "question": "Desconto no PIX",
        "answer": "Pagamentos via PIX têm 5% de desconto automaticamente aplicado no checkout. O PIX é processado instantaneamente e seu pedido é liberado imediatamente."
    },
    {
        "category": "payment",
        "question": "Pagamento recusado",
        "answer": "Se seu pagamento foi recusado, verifique os dados do cartão, limite disponível, ou tente outro método de pagamento. Caso persista, entre em contato com seu banco."
    },
    {
        "category": "payment",
        "question": "Nota fiscal",
        "answer": "A nota fiscal é enviada automaticamente por email após a confirmação do pagamento. Você também pode acessá-la na área 'Meus Pedidos' do site."
    },
    
    # RETURN
    {
        "category": "return",
        "question": "Política de troca e devolução",
        "answer": "Você tem 30 dias após o recebimento para solicitar troca ou devolução. O produto deve estar na embalagem original, sem uso e com etiquetas."
    },
    {
        "category": "return",
        "question": "Como solicitar troca",
        "answer": "Para trocar, acesse 'Meus Pedidos', selecione o item e clique em 'Solicitar Troca'. Enviaremos uma etiqueta de postagem por email em até 24 horas."
    },
    {
        "category": "return",
        "question": "Reembolso",
        "answer": "O reembolso é processado em até 7 dias úteis após recebermos o produto devolvido. Para cartão, o valor volta na fatura seguinte. Para PIX/boleto, fazemos depósito em conta."
    },
    {
        "category": "return",
        "question": "Produto com defeito",
        "answer": "Produtos com defeito podem ser devolvidos a qualquer momento dentro da garantia. Enviamos um novo produto ou fazemos reembolso integral, você escolhe."
    },
    {
        "category": "return",
        "question": "Troca de tamanho",
        "answer": "Para trocar o tamanho, o custo do frete de retorno é por nossa conta. Envie o produto original e despachamos o novo tamanho em até 2 dias úteis após recebimento."
    },
    
    # STORE
    {
        "category": "store",
        "question": "Horário de atendimento",
        "answer": "Nosso atendimento funciona de segunda a sexta, das 9h às 18h, e sábados das 9h às 13h. Fora desse horário, deixe sua mensagem que responderemos no próximo dia útil."
    },
    {
        "category": "store",
        "question": "Contato da loja",
        "answer": "Você pode nos contatar pelo WhatsApp (11) 99999-9999, email contato@demostore.com.br, ou pelo chat do site. Respondemos em até 2 horas em horário comercial."
    },
    {
        "category": "store",
        "question": "Loja física",
        "answer": "Temos loja física na Av. Paulista, 1000, São Paulo/SP, aberta de segunda a sábado das 10h às 20h. Você pode retirar pedidos online na loja sem custo adicional."
    },
    {
        "category": "store",
        "question": "Garantia dos produtos",
        "answer": "Todos os produtos têm garantia de 90 dias contra defeitos de fabricação. Produtos eletrônicos têm garantia estendida de 1 ano."
    },
    {
        "category": "store",
        "question": "Programa de fidelidade",
        "answer": "No nosso programa de pontos, cada R$ 1 em compras = 1 ponto. Acumule 500 pontos e troque por R$ 25 de desconto. Pontos não expiram."
    },
    {
        "category": "store",
        "question": "Cupom de desconto",
        "answer": "Para usar um cupom de desconto, insira o código no campo 'Cupom' antes de finalizar a compra. Cupons não são cumulativos e têm validade."
    },
    
    # PRODUCTS
    {
        "category": "products",
        "question": "Tabela de tamanhos",
        "answer": "Nossa tabela de tamanhos está disponível na página de cada produto. Medimos em centímetros: P (36-38), M (40-42), G (44-46), GG (48-50)."
    },
    {
        "category": "products",
        "question": "Produto esgotado",
        "answer": "Quando um produto está esgotado, você pode clicar em 'Avise-me quando chegar' para receber um email assim que estiver disponível novamente."
    },
    {
        "category": "products",
        "question": "Cores disponíveis",
        "answer": "As cores disponíveis de cada produto são mostradas na página do item. Clique na cor desejada para ver as fotos reais do produto naquela cor."
    },
]


def generate_embedding(embeddings_model, text: str) -> list[float]:
    """Generate embedding for a text."""
    return embeddings_model.embed_query(text)


def seed_knowledge_base(tenant_name: str, clear_existing: bool = True):
    """Seed knowledge base with embeddings for a tenant."""
    print(f"\n{'='*60}")
    print(f"Seeding knowledge base for tenant: {tenant_name}")
    print(f"{'='*60}\n")
    
    # Initialize
    client = get_supabase_client()
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    # Get or create tenant
    tenant_id = get_or_create_tenant(client, tenant_name)
    print(f"Tenant ID: {tenant_id}")
    
    # Clear existing entries for this tenant if requested
    if clear_existing:
        print("\nClearing existing knowledge base entries...")
        client.table("knowledge_base").delete().eq("tenant_id", tenant_id).execute()
        print("Done!")
    
    # Insert entries with embeddings
    print(f"\nInserting {len(KNOWLEDGE_DATA)} knowledge base entries with embeddings...")
    
    for i, entry in enumerate(KNOWLEDGE_DATA):
        # Create text for embedding (combines question and answer for better semantic matching)
        embed_text = f"{entry['question']} {entry['answer']}"
        
        # Generate embedding
        embedding = generate_embedding(embeddings, embed_text)
        
        # Insert into database
        client.table("knowledge_base").insert({
            "tenant_id": tenant_id,
            "category": entry["category"],
            "question": entry["question"],
            "answer": entry["answer"],
            "embedding": embedding,
            "is_active": True,
        }).execute()
        
        print(f"  [{i+1}/{len(KNOWLEDGE_DATA)}] {entry['category']}: {entry['question'][:50]}...")
    
    # Verify
    result = client.table("knowledge_base").select("category").eq("tenant_id", tenant_id).execute()
    
    print(f"\n{'='*60}")
    print(f"DONE! Inserted {len(result.data)} entries with vector embeddings")
    print(f"{'='*60}")
    
    # Category summary
    categories = {}
    for item in result.data:
        cat = item["category"]
        categories[cat] = categories.get(cat, 0) + 1
    
    print("\nBy category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Seed knowledge base with vector embeddings")
    parser.add_argument("--tenant", default="Demo Store", help="Tenant name")
    parser.add_argument("--keep-existing", action="store_true", help="Don't clear existing entries")
    args = parser.parse_args()
    
    seed_knowledge_base(args.tenant, clear_existing=not args.keep_existing)


if __name__ == "__main__":
    main()
