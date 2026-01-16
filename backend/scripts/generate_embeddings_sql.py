"""Generate SQL file with embeddings for Supabase."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from langchain_openai import OpenAIEmbeddings

KNOWLEDGE_DATA = [
    {"category": "shipping", "question": "Prazo de entrega padrão", "answer": "O prazo de entrega é de 5 a 12 dias úteis para capitais e 7 a 15 dias úteis para interior. Após o envio, você recebe o código de rastreio por email e SMS."},
    {"category": "shipping", "question": "Como rastrear meu pedido", "answer": "Você pode rastrear seu pedido usando o código de rastreio enviado por email. Acesse nosso site e clique em Rastrear Pedido ou use o link direto dos Correios."},
    {"category": "shipping", "question": "Frete grátis", "answer": "Oferecemos frete grátis para compras acima de R$ 299,00 em todo o Brasil. Para valores menores, o frete é calculado pelo CEP no checkout."},
    {"category": "shipping", "question": "Entrega expressa", "answer": "Temos opção de entrega expressa via Sedex para capitais, com prazo de 2 a 4 dias úteis. O custo adicional é mostrado no checkout."},
    {"category": "shipping", "question": "Pedido atrasado", "answer": "Se seu pedido passou do prazo estimado, entre em contato informando o número do pedido. Verificaremos com a transportadora e daremos retorno em até 24 horas."},
    {"category": "payment", "question": "Formas de pagamento aceitas", "answer": "Aceitamos cartão de crédito (Visa, Mastercard, Elo, Amex) em até 12x sem juros, PIX com 5% de desconto, e boleto bancário com vencimento em 3 dias úteis."},
    {"category": "payment", "question": "Parcelamento sem juros", "answer": "Parcelamos em até 12x sem juros no cartão de crédito para compras acima de R$ 100,00. Para valores menores, o parcelamento máximo é 3x."},
    {"category": "payment", "question": "Desconto no PIX", "answer": "Pagamentos via PIX têm 5% de desconto automaticamente aplicado no checkout. O PIX é processado instantaneamente e seu pedido é liberado imediatamente."},
    {"category": "payment", "question": "Pagamento recusado", "answer": "Se seu pagamento foi recusado, verifique os dados do cartão, limite disponível, ou tente outro método de pagamento. Caso persista, entre em contato com seu banco."},
    {"category": "payment", "question": "Nota fiscal", "answer": "A nota fiscal é enviada automaticamente por email após a confirmação do pagamento. Você também pode acessá-la na área Meus Pedidos do site."},
    {"category": "return", "question": "Política de troca e devolução", "answer": "Você tem 30 dias após o recebimento para solicitar troca ou devolução. O produto deve estar na embalagem original, sem uso e com etiquetas."},
    {"category": "return", "question": "Como solicitar troca", "answer": "Para trocar, acesse Meus Pedidos, selecione o item e clique em Solicitar Troca. Enviaremos uma etiqueta de postagem por email em até 24 horas."},
    {"category": "return", "question": "Reembolso", "answer": "O reembolso é processado em até 7 dias úteis após recebermos o produto devolvido. Para cartão, o valor volta na fatura seguinte. Para PIX/boleto, fazemos depósito em conta."},
    {"category": "return", "question": "Produto com defeito", "answer": "Produtos com defeito podem ser devolvidos a qualquer momento dentro da garantia. Enviamos um novo produto ou fazemos reembolso integral, você escolhe."},
    {"category": "return", "question": "Troca de tamanho", "answer": "Para trocar o tamanho, o custo do frete de retorno é por nossa conta. Envie o produto original e despachamos o novo tamanho em até 2 dias úteis após recebimento."},
    {"category": "store", "question": "Horário de atendimento", "answer": "Nosso atendimento funciona de segunda a sexta, das 9h às 18h, e sábados das 9h às 13h. Fora desse horário, deixe sua mensagem que responderemos no próximo dia útil."},
    {"category": "store", "question": "Contato da loja", "answer": "Você pode nos contatar pelo WhatsApp (11) 99999-9999, email contato@demostore.com.br, ou pelo chat do site. Respondemos em até 2 horas em horário comercial."},
    {"category": "store", "question": "Loja física", "answer": "Temos loja física na Av. Paulista, 1000, São Paulo/SP, aberta de segunda a sábado das 10h às 20h. Você pode retirar pedidos online na loja sem custo adicional."},
    {"category": "store", "question": "Garantia dos produtos", "answer": "Todos os produtos têm garantia de 90 dias contra defeitos de fabricação. Produtos eletrônicos têm garantia estendida de 1 ano."},
    {"category": "store", "question": "Programa de fidelidade", "answer": "No nosso programa de pontos, cada R$ 1 em compras = 1 ponto. Acumule 500 pontos e troque por R$ 25 de desconto. Pontos não expiram."},
    {"category": "store", "question": "Cupom de desconto", "answer": "Para usar um cupom de desconto, insira o código no campo Cupom antes de finalizar a compra. Cupons não são cumulativos e têm validade."},
    {"category": "products", "question": "Tabela de tamanhos", "answer": "Nossa tabela de tamanhos está disponível na página de cada produto. Medimos em centímetros: P (36-38), M (40-42), G (44-46), GG (48-50)."},
    {"category": "products", "question": "Produto esgotado", "answer": "Quando um produto está esgotado, você pode clicar em Avise-me quando chegar para receber um email assim que estiver disponível novamente."},
    {"category": "products", "question": "Cores disponíveis", "answer": "As cores disponíveis de cada produto são mostradas na página do item. Clique na cor desejada para ver as fotos reais do produto naquela cor."},
]

def main():
    print("Generating embeddings...")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    sql_lines = []
    sql_lines.append("-- Generated knowledge base with embeddings")
    sql_lines.append("-- Tenant: Demo Store (00000000-0000-0000-0000-000000000001)")
    sql_lines.append("-- Run this in Supabase SQL Editor")
    sql_lines.append("")
    sql_lines.append("DELETE FROM knowledge_base WHERE tenant_id = '00000000-0000-0000-0000-000000000001';")
    sql_lines.append("")
    sql_lines.append("INSERT INTO knowledge_base (tenant_id, category, question, answer, embedding, is_active) VALUES")
    
    values = []
    for i, entry in enumerate(KNOWLEDGE_DATA):
        text = f"{entry['question']} {entry['answer']}"
        emb = embeddings.embed_query(text)
        emb_str = "[" + ",".join([str(x) for x in emb]) + "]"
        q = entry["question"].replace("'", "''")
        a = entry["answer"].replace("'", "''")
        values.append(f"('00000000-0000-0000-0000-000000000001', '{entry['category']}', '{q}', '{a}', '{emb_str}', true)")
        print(f"  [{i+1}/{len(KNOWLEDGE_DATA)}] {entry['category']}: {entry['question'][:40]}...")
    
    sql_lines.append(",\n".join(values) + ";")
    
    output_path = Path(__file__).parent.parent / "supabase" / "seed_with_embeddings.sql"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sql_lines))
    
    print(f"\nDone! SQL file saved to: {output_path}")


if __name__ == "__main__":
    main()
