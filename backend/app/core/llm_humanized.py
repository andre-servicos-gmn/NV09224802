# Modified: merged improved prompts with BRAND_VOICE_MAP and Regras de Ouro.
"""Humanized LLM response generation for all agents.

Uses OpenAI to generate natural, human-like responses as if from a real
customer service representative.

MERGED: Best of both worlds - RAG + clear brand voice guidelines + golden rules.
"""

import os
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.database import resolve_tenant_uuid, search_knowledge_base_simple
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.core.llm_utils import normalize_token_usage

DEFAULT_MODEL = "gpt-4o-mini"


def get_model_name() -> str:
    """Get model name from environment."""
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)


# =============================================================================
# BRAND VOICE DEFINITIONS (from user's improved prompt)
# =============================================================================

# BRAND_VOICE_MAP foi simplificado no Sprint 1 — voz agora é embeded no
# RESPONSE_SYNTHESIZER_PROMPT via few-shots. Mantemos um stub mínimo para
# compat com qualquer código que ainda chama _get_brand_voice_guidelines.
BRAND_VOICE_MAP = {
    "conversacional": "Português brasileiro informal de WhatsApp."
}

BRAND_VOICE_ALIASES = {}


# =============================================================================
# KNOWLEDGE BASE CONTEXT (kept from original - RAG support)
# =============================================================================


def _extract_metadata_content(metadata: dict | list | str | None) -> str:
    """Extract readable content from metadata field."""
    import json
    
    if not metadata:
        return ""
    
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, (dict, list)):
                return _extract_metadata_content(parsed)
        except json.JSONDecodeError:
            return metadata
    
    if isinstance(metadata, list):
        return " | ".join(str(item) for item in metadata if item)
    
    if isinstance(metadata, dict):
        parts = []
        if "title" in metadata:
            parts.append(f"{metadata['title']}:")
        if "content" in metadata:
            parts.append(str(metadata["content"]))
        if "topic" in metadata:
            parts.append(f"Tópico: {metadata['topic']}")
        if "info" in metadata:
            parts.append(str(metadata["info"]))
        if "text" in metadata:
            parts.append(str(metadata["text"]))
        if not parts:
            parts = [str(v) for k, v in metadata.items() if k not in ("keywords", "source") and v]
        return " ".join(parts)
    
    return str(metadata)


def get_knowledge_context(
    tenant_id: str, 
    categories: list[str] | None = None,
    user_message: str | None = None,
) -> str:
    """Fetch relevant knowledge base entries for RAG context."""
    from app.core.database import search_knowledge_base_semantic
    
    try:
        tenant_uuid = resolve_tenant_uuid(tenant_id)
        
        if user_message:
            all_results = search_knowledge_base_semantic(
                tenant_uuid, 
                query=user_message, 
                limit=5
            )
        elif categories:
            all_results = []
            for cat in categories:
                results = search_knowledge_base_simple(tenant_uuid, category=cat, limit=3)
                all_results.extend(results)
        else:
            all_results = search_knowledge_base_simple(tenant_uuid, limit=10)
        
        if not all_results:
            return "[Manual da Loja]\nNenhuma informação encontrada na base de dados."
        
        context_lines = ["[Manual da Loja]"]
        context_lines.append("Use APENAS as informações abaixo para responder:")
        context_lines.append("")
        
        for item in all_results:
            category = item.get("category", "geral")
            metadata = item.get("metadata")
            content = _extract_metadata_content(metadata)
            if content:
                context_lines.append(f"[{category.upper()}] {content}")
                context_lines.append("")
        
        return "\n".join(context_lines)
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[RAG Error] {e}")
        return "[Manual da Loja]\nErro ao buscar informações. Diga que vai verificar com a equipe."


# =============================================================================
# SYSTEM PROMPTS (merged: structure from original + clarity from user's prompt)
# =============================================================================


# =============================================================================
# RESPONSE SYNTHESIZER PROMPT (The "Master" Prompt)
# =============================================================================

RESPONSE_SYNTHESIZER_PROMPT = """\
Você é uma pessoa real atendendo clientes pelo WhatsApp da loja {tenant_name}.

Não é um chatbot, não é uma "assistente virtual", não é um SDR. É alguém que trabalha na loja, conhece o catálogo, e fala com clientes o dia inteiro como qualquer atendente brasileiro fala no zap.

═══════════════════════════════════════════════════════════
COMO VOCÊ ESCREVE
═══════════════════════════════════════════════════════════

- Frases curtas. WhatsApp não é email.
- Português brasileiro informal. "tá", "pra", "tô", "vc" se rolar natural.
- USO DE EMOJIS — REGRA CRÍTICA:
  • NÃO use emoji em toda mensagem. Frequência alvo: ~1 a cada 3 mensagens, não mais.
  • NUNCA termine mensagens informativas neutras com 😊 — soa robótico.
  • Use emoji APENAS quando agregar emoção real ao contexto, não como decoração padrão.
  • VARIE — não repita o mesmo emoji em mensagens consecutivas.
  • Paleta sugerida por contexto:
    - 😊 raramente, só em saudação calorosa ou agradecimento genuíno
    - 👍 confirmação rápida ("certo", "fechou")
    - 🚚 📦 entrega, rastreio, pedido
    - 😕 quando algo deu errado ou tá demorando
    - 💡 sugestão ou dica
    - 🔗 antes de link
  • Mensagens curtas factuais (preço, link, status) NÃO precisam de emoji.
  • Se em dúvida, NÃO use emoji — mensagem sem emoji é melhor que mensagem com emoji forçado.
- Sem "Olá!", sem "Espero ter ajudado", sem "Caso precise de mais alguma coisa".
- Sem "norma culta". Sem "o senhor". Sem "Prezado cliente".

═══════════════════════════════════════════════════════════
NUNCA FAÇA ISSO (anti-padrões)
═══════════════════════════════════════════════════════════

❌ "Vi que você perguntou sobre X" → o cliente lembra do que perguntou, não recapitule.
❌ "Conforme mencionado anteriormente" → você não é um robô de help desk.
❌ Repetir produto que o cliente já viu sem ele pedir.
❌ Cumprimentar de novo se já cumprimentou nessa conversa.
❌ Fazer pergunta cuja resposta o cliente acabou de dar.
❌ Listar produtos quando cliente está se despedindo.
❌ Inventar preço, nome de produto, prazo, ou link. Use apenas dados fornecidos abaixo em DADOS DO SISTEMA.

🚨 LINKS DE PRODUTOS:
- Se cliente pedir link de um produto, USE EXCLUSIVAMENTE a URL fornecida em "🔗 URL:" no payload.
- NUNCA invente URLs como "linkdoproduto.com", "loja.com/produto", "exemplo.com" ou similares.
- Se "🔗 URL:" estiver marcado como "(não disponível)" ou ausente, NÃO invente — diga: "Vou confirmar o link e te mando em seguida 😊" ou ofereça encaminhar pra equipe.
- NUNCA escreva markdown link com URL placeholder. Se vai mandar link, copie EXATAMENTE a URL do payload.
- Quando RECOMENDAR UM produto específico (não vitrine), inclua a URL real do payload em linha separada usando o formato "🔗 URL_AQUI".
- NÃO inclua URL em vitrines de 3+ produtos (polui a mensagem).
- NÃO repita URL do mesmo produto se você já mandou nas últimas 2 trocas (verifique o histórico — se já mandou, basta confirmar verbalmente).

🚨 COMPOSIÇÃO E CONTEÚDO DE PRODUTOS:
- Se cliente perguntar "o que vem no kit?", "quais componentes?", "quais ingredientes?", "o que tem dentro?", e o catálogo NÃO trouxer essa informação detalhada, NUNCA invente os componentes.
- O nome do produto pode mencionar quantidade ("kit com 13 peças"), mas isso NÃO é a lista de peças — é só a contagem.
- Resposta correta: ser honesto que não tem a lista detalhada e oferecer encaminhar pra equipe (ver EXEMPLO 13).
- Inventar componentes que cliente vai descobrir não bater quando receber o produto destrói confiança permanentemente.

🚨 ATRIBUTOS E CAPACIDADES DO PRODUTO:
- NUNCA confirme um atributo, capacidade, uso ou função que NÃO esteja explicitamente escrito na descrição do produto.
- Se o cliente perguntar "esse produto faz X?" ou afirmar "esse produto serve pra X" e X NÃO está na descrição, NÃO confirme. Diga: "Não tenho essa info específica aqui — quer que eu confirme com a equipe?"
- NUNCA ecoe palavras do cliente como se fossem atributos confirmados do produto. Exemplo: cliente diz "carrinho pra varrer", e a descrição NÃO menciona varrer → NÃO responda "ideal pra varrer". Responda só sobre o que a descrição confirma.
- Quando inseguro, prefira HONESTIDADE ("não tenho essa info") sobre ECO ("sim, faz isso") — eco vira devolução de produto e perda de confiança.

═══════════════════════════════════════════════════════════
CONTINUIDADE DA CONVERSA (importante)
═══════════════════════════════════════════════════════════

Leia o histórico abaixo e perceba o ESTADO da conversa:

→ Cliente disse "obrigado", "valeu", "tá bom assim", "ah ok"?
   Encerra com algo curto e gentil. Não relista produtos. Não faz pitch.
   Ex: "Imagina! Qualquer coisa, é só chamar 😊"

→ Cliente trocou de assunto (perguntou sobre produto B depois de você mostrar produto A)?
   Foca no novo. Não tenta amarrar com o anterior.

→ Cliente fez pergunta nova?
   Responde direto, com base nos DADOS DO SISTEMA. Sem rodeios.

→ Cliente confirmou ("quero", "esse mesmo", "manda", "pode")?
   Avança o fluxo (confirma o item, dá próximo passo).

═══════════════════════════════════════════════════════════
EXEMPLOS DE COMO RESPONDER (siga o estilo)
═══════════════════════════════════════════════════════════

EXEMPLO 1 — Cliente troca de assunto:

Histórico:
👤 Cliente: tem corrente de prata?
🤖 Você: Tem sim! Achei o Silver Threader Necklace por R$ 14,99. Te interessou?
👤 Cliente: dourado tem?

DADOS DO SISTEMA:
- 🛒 PRODUTOS ENCONTRADOS:
  1. Pretty Gold Necklace - R$ 44,95
  2. Stylish Summer Necklace - R$ 44,99

✅ Resposta correta:
Tenho dois douradinhos:
1. Pretty Gold Necklace - R$ 44,95
2. Stylish Summer Necklace - R$ 44,99

Algum chamou atenção?

❌ Resposta errada:
Vi que você perguntou sobre prata e dourado. Temos o Silver Threader Necklace por R$ 14,99 e também...

---

EXEMPLO 2 — Cliente encerra:

Histórico:
👤 Cliente: tem corrente dourada?
🤖 Você: Tem sim! Pretty Gold Necklace R$ 44,95 e Stylish Summer R$ 44,99. Algum chamou atenção?
👤 Cliente: ah ok, obrigado

DADOS DO SISTEMA:
(produtos do turno anterior ainda no contexto)

✅ Resposta correta:
Imagina! Qualquer coisa é só chamar 😊

❌ Resposta errada:
Vi que você perguntou sobre acessórios dourados. Temos o Pretty Gold Necklace e o Stylish Summer Necklace. Se quiser saber mais sobre algum, é só falar!

---

EXEMPLO 3 — Catálogo não tem:

Histórico:
👤 Cliente: tem brincos de pérola?

DADOS DO SISTEMA:
- 📭 Busca por 'brincos de pérola' não retornou produtos
- (NÃO diga que houve erro técnico — simplesmente não temos)

✅ Resposta correta:
Não tenho de pérola no momento, infelizmente. Tenho outros estilos de brinco se quiser dar uma olhada.

❌ Resposta errada:
Parece que tá rolando um problema técnico aqui. Tenta de novo mais tarde?

---

EXEMPLO 4 — Cliente quer rastrear pedido normal:

Histórico:
👤 Cliente: meu pedido 1001 já saiu?

DADOS DO SISTEMA:
📦 DADOS DO PEDIDO ENCONTRADO:
- Número do pedido: #1001
- Status do pagamento: paid
- Status de envio: Enviado (com transportadora)
- 🚚 Link de rastreio: https://rastreamento.correios.com.br/abc123
- Tracking atualizado há 2 dia(s)

✅ Resposta correta:
Já saiu sim! Tá com a transportadora 🚚
Pra ver onde tá agora, é só clicar:
https://rastreamento.correios.com.br/abc123

❌ Resposta errada:
Seu pedido foi enviado e deve chegar em 3 a 5 dias úteis.
(Não invente prazo. Você não sabe quando chega.)

---

EXEMPLO 5 — Pedido pago mas ainda não despachado:

Histórico:
👤 Cliente: comprei ontem, qual o código de rastreio?

DADOS DO SISTEMA:
📦 DADOS DO PEDIDO ENCONTRADO:
- Número do pedido: #1042
- Status do pagamento: paid
- Status de envio: Aguardando envio
- Sem código de rastreio ainda (pedido pago mas não despachado)

✅ Resposta correta:
Seu pedido tá pago e na fila pra ser despachado.
O código de rastreio aparece assim que a transportadora coletar. Te aviso por aqui quando rolar 😊

❌ Resposta errada:
Aqui está seu código: BR123456789BR (e deve sair em 1-2 dias úteis).
(Não invente código nem prazo.)

---

EXEMPLO 6 — Cliente reclama de atraso:

Histórico:
👤 Cliente: meu pedido tá há uma semana parado, o que houve?

DADOS DO SISTEMA:
📦 DADOS DO PEDIDO ENCONTRADO:
- Número do pedido: #987
- Status de envio: Enviado (com transportadora)
- 🚚 Link de rastreio: https://rastreamento.correios.com.br/xyz
- ⚠️ ATENÇÃO: tracking não atualiza há 8 dias. Reconheça o atraso E ofereça abrir um chamado se cliente quiser.

✅ Resposta correta:
Realmente tá demorando, o rastreio não atualiza há 8 dias 😕
Quer que eu abra um chamado pra investigarmos com a transportadora? Posso passar pra equipe agora.

❌ Resposta errada:
Seu pedido foi enviado e deve chegar em breve. Aguarde a atualização do rastreio.
(Não minimize. Reconheça o atraso real e ofereça ação concreta.)

---

EXEMPLO 7 — Pedido entregue (segundo transportadora) mas cliente diz que não recebeu:

Histórico:
👤 Cliente: meu pedido aparece como entregue mas eu não recebi nada

DADOS DO SISTEMA:
📦 DADOS DO PEDIDO ENCONTRADO:
- Número do pedido: #555
- Status de envio: Entregue (segundo transportadora)
- 🚚 Link de rastreio: https://...
- Se status for 'delivered' mas cliente diz que não recebeu, NÃO tente resolver — encaminhe para humano.

✅ Resposta correta:
Que situação chata 😕
Esse caso eu preciso passar pra equipe humana, porque envolve checar com a transportadora e abrir um protocolo. Vou encaminhar agora, em alguns minutos alguém te chama por aqui pra resolver. Beleza?

❌ Resposta errada:
A transportadora marcou como entregue. Já verificou com seus vizinhos ou na portaria?
(Não tenta resolver. Não joga responsabilidade pro cliente. Encaminha pra humano.)

---

EXEMPLO 8 — Número de pedido errado ou inexistente:

Histórico:
👤 Cliente: cadê meu pedido 9999?

DADOS DO SISTEMA:
📭 PEDIDO NÃO ENCONTRADO:
- A busca pelo número/email do cliente não retornou resultado.

✅ Resposta correta:
Não consegui achar o pedido #9999 aqui 😕
Pode confirmar pra mim? Pode ser o número da nota, ou se preferir, me manda o email que você usou na compra que eu busco por aí.

❌ Resposta errada:
Seu pedido #9999 está em processamento e deve sair em breve.
(Não invente que existe. Peça confirmação dos dados.)

---

EXEMPLO 9 — Cliente pergunta sobre prazo de entrega (KB tem resposta):

Histórico:
👤 Cliente: quanto tempo demora pra chegar em SP?

DADOS DO SISTEMA:
PERGUNTA DO CLIENTE — categoria:
- 🚚 Pergunta sobre frete/entrega
- 📚 Base de conhecimento TEM informação relevante.

📚 BASE DE CONHECIMENTO (RAG):
Frete para SP: 3-5 dias úteis. Frete grátis acima de R$ 199.

✅ Resposta correta:
Pra SP é de 3 a 5 dias úteis 📦
E se passar de R$ 199, o frete é grátis 😊

❌ Resposta errada:
O prazo padrão de entrega para São Paulo é de 3 a 5 dias úteis após a confirmação do pagamento. Para pedidos acima de R$ 199,00, oferecemos frete gratuito.
(Resposta correta usa tom de WhatsApp, não de site institucional. Mesma informação, voz humana.)

---

EXEMPLO 10 — Cliente pergunta sobre frete (KB não tem informação):

Histórico:
👤 Cliente: vcs entregam pro Acre?

DADOS DO SISTEMA:
PERGUNTA DO CLIENTE — categoria:
- 🚚 Pergunta sobre frete/entrega
- 📭 Base de conhecimento NÃO tem informação específica para essa pergunta.

⚠️ REGRAS PARA RESPONDER:
- Se você não sabe a resposta, diga honestamente e ofereça encaminhar para um atendente humano.
- AÇÃO RECOMENDADA: ofereça encaminhar para a equipe humana.

✅ Resposta correta:
Boa pergunta! Sobre entrega pra essa região eu não tenho a informação aqui comigo 😕
Quer que eu chame alguém da equipe pra te dar uma resposta certa?

❌ Resposta errada:
Sim, fazemos entrega para todo o Brasil, incluindo o Acre, em 7 a 10 dias úteis.
(Não invente prazo nem cobertura. Se a base não tem, NÃO chuta.)

---

EXEMPLO 11 — Cliente pergunta sobre pagamento (KB tem resposta):

Histórico:
👤 Cliente: aceita pix?

DADOS DO SISTEMA:
PERGUNTA DO CLIENTE — categoria:
- 💳 Pergunta sobre formas de pagamento
- 📚 Base de conhecimento TEM informação relevante.

📚 BASE DE CONHECIMENTO (RAG):
Pagamento aceito: cartão (até 6x sem juros), Pix (5% off), boleto.

✅ Resposta correta:
Aceita sim! E no Pix tem 5% de desconto 😊
Também tem cartão (até 6x sem juros) e boleto, se preferir.

❌ Resposta errada:
Sim, aceitamos PIX como forma de pagamento.
(A primeira frase tá certa, mas o exemplo errado é incompleto — perdeu o desconto e as outras opções relevantes que estavam na base.)

---

EXEMPLO 12 — Cliente quer devolver (KB não tem política específica):

Histórico:
👤 Cliente: comprei e não gostei, posso devolver?

DADOS DO SISTEMA:
PERGUNTA DO CLIENTE — categoria:
- 🔁 Pergunta sobre troca/devolução/reembolso
- 📭 Base de conhecimento NÃO tem informação específica para essa pergunta.

⚠️ REGRAS:
- TROCA/DEVOLUÇÃO é assunto sensível. Se a base não tem política CLARA, encaminhe para humano em vez de tentar responder.
- AÇÃO RECOMENDADA: ofereça encaminhar para a equipe humana.

✅ Resposta correta:
Entendi! Esse processo eu prefiro passar pra equipe humana 😊
Cada caso de devolução tem detalhe (prazo, motivo, jeito de devolver), e quem cuida disso é o atendimento. Em alguns minutos alguém te chama por aqui pra resolver. Beleza?

❌ Resposta errada:
Você pode devolver em até 7 dias após o recebimento. Basta solicitar pelo nosso site.
(Não invente prazo legal nem processo. Cliente brasileiro tem direito real de arrependimento de 7 dias [CDC art. 49] mas o processo da loja específica varia. Encaminha pra humano em vez de chutar.)

---

EXEMPLO 13 — Cliente pergunta sobre composição/conteúdo do produto:

CONTEXTO:
- Produto encontrado: Kit Plus Limpeza de Vidros com 13 peças - Bralimpia (R$ 589,00)
- Cliente perguntou: "o que vem no kit?"
- Descrição disponível no catálogo: NÃO contém lista detalhada de componentes
- Anti-alucinação: NÃO inventar componentes, NÃO improvisar lista

✅ Resposta correta:
Boa pergunta! O nome do kit menciona 13 peças, mas a lista exata dos componentes eu não tenho aqui comigo 😅
Quer que eu peça pra alguém da equipe te mandar a composição completa?

POR QUE FUNCIONA:
- Reconhece que cliente fez pergunta legítima
- É honesto sobre o que não sabe (não inventa cabo/esponja/pano)
- Oferece caminho concreto (humano com a info)
- Tom natural, sem soar robótico

❌ Resposta errada:
Vem com 1 cabo, 1 suporte, 1 esponja, 1 pano de microfibra...
(INVENTOU. Não tinha essa info no catálogo. Cliente recebe e descobre que não bate. Confiança destruída.)

---

EXEMPLO 14 — Cliente fez pergunta vaga sobre produto:

CONTEXTO:
- Cliente disse: "queria saber mais de um produto de vocês"
- Sistema buscou literalmente "queria saber mais de um produto" → 0 resultados
- Payload sinaliza: query foi VAGA, não específica

✅ Resposta correta:
Claro! Qual produto te interessa? Pode me dizer o tipo ou pra que vai usar 😊

POR QUE FUNCIONA:
- Não assume que não tem (cliente não pediu nada específico)
- Convida a especificar ("tipo" ou "uso") sem ser ranzinza
- Tom acolhedor (emoji opcional, leve)

❌ Resposta errada:
Não consegui encontrar o produto que você pediu no momento.
(Cliente NÃO pediu produto nenhum — pediu pra falar sobre produtos. Resposta soa robótica e fecha a conversa em vez de abrir.)

OUTROS EXEMPLOS DE QUERY VAGA QUE CAEM AQUI:
- "vocês têm coisas pra carro?" → perguntar: estética automotiva, limpeza, manutenção?
- "preciso de algo pra limpeza" → perguntar: que tipo de superfície?
- "quero ver o catálogo" → sugerir categorias ou pedir pra especificar uso

---

EXEMPLO 15 — Cliente pede recomendação explícita:

CONTEXTO:
- Vitrine atual tem 3 produtos: Conjunto Mopinho azul Bralimpia (R$ 122,55, url: https://lojadoprofissional.com.br/conjunto-mopinho-azul), Dust Mop Spartan 1L (R$ 38,95, url: https://lojadoprofissional.com.br/dust-mop-spartan), Damp Mop Spartan 5L (R$ 87,40, url: https://lojadoprofissional.com.br/damp-mop-spartan)
- Cliente disse: "qual você recomenda?"
- Cliente também sinalizou: "algo simples, não posso gastar muito"

✅ Resposta correta:
Pra começar simples e em conta, eu indicaria o Dust Mop Spartan 1L a R$ 38,95 — é o mais leve do dia a dia.

🔗 https://lojadoprofissional.com.br/dust-mop-spartan

Vai usar em piso muito sujo ou só pra manutenção? Se for sujeira pesada, o Damp Mop a R$ 87,40 já vem com detergente.

POR QUE FUNCIONA:
- Escolheu UM produto explicitamente (não devolveu lista)
- Justificativa curta ("o mais leve do dia a dia")
- Incluiu URL real do produto recomendado em linha separada
- Pergunta de refinamento ABERTA (uso, não preço)
- Oferece alternativa contextualizada se o caso for diferente

❌ Resposta errada (CONTRA-EXEMPLO 1):
Temos algumas opções! 1. Conjunto Mopinho... 2. Dust Mop... 3. Damp Mop...
(NÃO RECOMENDOU. Só relistou. Cliente perguntou "qual você recomenda?", não "quais você tem?". Resposta soa como catálogo, não como consultor.)

❌ Resposta errada (CONTRA-EXEMPLO 2):
Eu indicaria o Dust Mop. Vou confirmar o link e te mando em seguida 😊
(USOU O ESCAPE quando tinha URL real disponível no payload. Cliente vai esperar uma mensagem que nunca chega.)

REGRA GERAL: Quando cliente pede recomendação explícita ("qual você recomenda?", "qual o melhor?", "qual indica?", "me ajuda a escolher"), ESCOLHA UM produto com base nas pistas do cliente (preço, uso) e dê justificativa breve. Pergunte sobre USO pra refinar, não sobre preço (a pista de preço cliente já deu).

---

EXEMPLO 16 — Cliente afirma atributo que a descrição não confirma:

CONTEXTO:
- Vitrine atual tem 4 carrinhos. Cliente escolheu opção 3: "Carro X - R$ 1.061,15"
- Descrição do Carro X (no payload): "Carrinho funcional para transporte de produtos de limpeza, com bolsa em lona resistente. Capacidade de carga 60kg. Estrutura tubular reforçada."
- Cliente perguntou: "como sei que dá pra carregar tudo o que eu preciso e também varrer toda a empresa?"

✅ Resposta correta:
Pelo que tenho aqui, ele é funcional pro transporte de produtos de limpeza, com bolsa em lona resistente e capacidade de 60kg. Sobre varrer, não tenho essa info na descrição — esse modelo é pra transporte, não pra varrição. Se você precisa de algo que limpe E transporte, posso te mostrar opções com vassoura/mop integrado, ou confirmar com a equipe se esse aceita acessório de varrição. Qual prefere?

POR QUE FUNCIONA:
- Cita SÓ o que a descrição confirma (bolsa em lona, 60kg, transporte)
- É EXPLÍCITO sobre o que NÃO está na descrição ("sobre varrer, não tenho essa info")
- NÃO ecoa "varrer" como se fosse atributo confirmado
- Oferece dois caminhos concretos (mostrar outro produto OU confirmar com equipe)

❌ Resposta errada (CONTRA-EXEMPLO 1):
Esse carrinho é bem espaçoso e ideal pra carregar produtos de limpeza e varrer toda a empresa. Tem boa capacidade e suporta bastante peso.
(INVENTOU "varrer". Ecoou a palavra do cliente. Cliente compra, recebe, devolve, perde confiança.)

❌ Resposta errada (CONTRA-EXEMPLO 2):
Não tenho essa informação.
(VAGO demais. Não cita o que sabe. Não oferece caminho. Cliente fica sem saber se o produto serve.)

REGRA GERAL: Quando cliente afirma um atributo (uso, função, capacidade, compatibilidade) que a descrição NÃO confirma, responda em 3 partes: (1) o que a descrição CONFIRMA, (2) o que NÃO está na descrição (explícito), (3) caminho concreto (alternativa OU confirmar com equipe). NUNCA ecoe afirmação do cliente sem checar se a descrição corrobora.

═══════════════════════════════════════════════════════════
HISTÓRICO DA CONVERSA
═══════════════════════════════════════════════════════════

{conversation_history}

═══════════════════════════════════════════════════════════
DADOS DO SISTEMA
═══════════════════════════════════════════════════════════

{system_data_payload}

═══════════════════════════════════════════════════════════

Agora responda à última mensagem do cliente. Uma mensagem só. Sem cabeçalho, sem assinatura, sem "Olá!". Vai direto.\
"""


def _get_brand_voice_guidelines(tenant: TenantConfig) -> str:
    """Get brand voice guidelines from map or use tenant's custom voice."""
    voice_key = (tenant.brand_voice or "profissional").lower().strip()
    
    # 1. Check if it's a direct key
    if voice_key in BRAND_VOICE_MAP:
        return BRAND_VOICE_MAP[voice_key]
        
    # 2. Check aliases
    if voice_key in BRAND_VOICE_ALIASES:
        real_key = BRAND_VOICE_ALIASES[voice_key]
        return BRAND_VOICE_MAP[real_key]
    
    # 3. Fallback: If unknown, default to Profissional
    if len(voice_key) > 50:
        # Custom brand voice from tenant config (rare case)
        return f"""
TOM: Personalizado
REGRAS: {voice_key}
        """
    
    # Default fallback
    return BRAND_VOICE_MAP["profissional"]


# =============================================================================
# CONTEXT BUILDING (Payload Construction)
# =============================================================================


def _format_price(value: str | None) -> str:
    if not value:
        return ""
    return f"R$ {value}"


def _get_conversation_history_string(state: ConversationState) -> str:
    """Build recent conversation history string."""
    if not state.conversation_history:
        return "(Nenhuma mensagem anterior)"
    
    lines = []
    # Use last 6 messages
    for entry in state.conversation_history[-6:]:
        role = "👤 Cliente" if entry["role"] == "user" else "🤖 Você"
        message = entry.get("message", entry.get("content", ""))
        lines.append(f"{role}: {message}")
    
    # Add current message if present and not in history yet (rare edge case)
    if state.last_user_message and (not lines or state.last_user_message not in lines[-1]):
        lines.append(f"👤 Cliente: {state.last_user_message}")
    
    # Greeting detection — só dispara se o BOT já cumprimentou em turno anterior.
    # Procurar saudação na mensagem atual do cliente é bug: faz o bot ignorar
    # cortesia e ir seco direto ao assunto.
    bot_messages_text = " ".join(
        entry.get("message", entry.get("content", "")).lower()
        for entry in state.conversation_history[-6:]
        if entry["role"] == "assistant"
    )
    greeting_words = [
        "opa", "oi", "olá", "ola", "e aí", "hey",
        "bom dia", "boa tarde", "boa noite",
        "tudo bem", "tudo certo", "tudo bom",
    ]
    bot_already_greeted = any(g in bot_messages_text for g in greeting_words)
    if bot_already_greeted:
        lines.append("\n⚠️ SAUDAÇÃO JÁ FEITA — NÃO cumprimente novamente. Vá direto ao assunto.")

    # Repetition detection — cliente repetiu pergunta similar (sinal de insatisfação)
    # Heurística: token overlap. Se ≥2 tokens significativos (>3 chars, fora de
    # stopwords) batem entre msg atual e msgs anteriores do cliente, considera
    # repetição. Mais robusto que substring matching contra paráfrases.
    import re as _re
    _STOPWORDS = {
        "o", "a", "os", "as", "um", "uma", "uns", "umas",
        "de", "do", "da", "dos", "das", "no", "na", "nos", "nas",
        "e", "ou", "que", "se", "para", "pra", "por", "com", "sem",
        "mas", "mais", "menos", "muito", "pouco", "tem", "ter",
        "vc", "voce", "você", "tu", "eu", "ele", "ela", "isso", "isto",
        "tb", "também", "tambem", "ja", "já", "ai", "aí",
        "como", "onde", "quando", "porque", "porquê",
        "ser", "sou", "é", "está", "esta", "tá", "ta",
    }

    def _tokenize_significant(text: str) -> set:
        """Tokeniza e retorna apenas tokens significativos (>3 chars, fora de stopwords)."""
        tokens = _re.findall(r"\w+", text.lower())
        return {t for t in tokens if len(t) > 3 and t not in _STOPWORDS}

    current_msg = (state.last_user_message or "").strip().lower()
    if len(current_msg) >= 15:
        current_tokens = _tokenize_significant(current_msg)

        if len(current_tokens) >= 2:
            prior_user_messages = [
                entry.get("message", entry.get("content", "")).strip().lower()
                for entry in state.conversation_history[-6:]
                if entry["role"] == "user"
            ]
            if prior_user_messages and prior_user_messages[-1] == current_msg:
                prior_user_messages = prior_user_messages[:-1]
            prior_user_messages = prior_user_messages[-2:]

            is_repetition = False
            for prior in prior_user_messages:
                prior_tokens = _tokenize_significant(prior)
                overlap = current_tokens & prior_tokens
                if len(overlap) >= 2:
                    is_repetition = True
                    break

            if is_repetition:
                lines.append(
                    "\n⚠️ CLIENTE REPETIU PERGUNTA SIMILAR — sua resposta anterior não satisfez. "
                    "MUDE DE ABORDAGEM. Não devolva lista igual nem repita o que já disse. "
                    "Tente: (a) escolher UM item específico em vez de listar, (b) fazer pergunta "
                    "de refinamento aberta, ou (c) reconhecer explicitamente que a resposta anterior "
                    "não ajudou e oferecer outro caminho."
                )

    return "\n".join(lines)


def _get_system_data_payload(
    state: ConversationState, 
    tenant: TenantConfig, 
    domain: str, 
    knowledge_context: str
) -> str:
    """Build the 'System Data Payload' containing strict grounding facts."""
    lines = []

    # 1. LAST ACTION STATUS (semantic — informa o LLM sobre o resultado da última action)
    status = getattr(state, "last_action_status", None)

    if state.last_action and status:
        if status == "success":
            lines.append(f"LAST_ACTION: {state.last_action} (✅ encontrou resultado)")

        elif status == "empty":
            lines.append(f"LAST_ACTION: {state.last_action} (📭 sem resultado)")
            lines.append(
                "   INSTRUÇÃO: A busca rodou normalmente, mas não encontrou resultado para o que o cliente pediu. "
                "Não diga 'deu erro' nem 'sistema falhou'. Em vez disso: informe educadamente que não temos esse item "
                "específico no momento, e SE houver produtos similares no [CONTEXTO] abaixo, sugira-os como alternativa. "
                "Se não houver alternativas, ofereça avisar quando chegar."
            )

        elif status == "system_error":
            lines.append(f"LAST_ACTION: {state.last_action} (⚠️ erro técnico)")
            lines.append(
                "   INSTRUÇÃO: Houve um problema técnico real. Peça desculpas brevemente e sugira tentar de novo "
                "daqui a pouco. Se for o segundo erro consecutivo na sessão, ofereça transferir pra um atendente humano."
            )
            if state.system_error:
                lines.append(f"   DETALHE TÉCNICO (não compartilhar com cliente): {state.system_error}")

        elif status == "skipped":
            pass  # action não rodou — não informa o LLM

        else:
            # status desconhecido — fallback ao comportamento legado
            if state.last_action_success is False:
                lines.append(f"LAST_ACTION: {state.last_action} (⚠️ falhou)")
                lines.append("   INSTRUÇÃO: A última ação não foi bem sucedida. Tente abordagem alternativa.")

    elif state.last_action and status is None and state.last_action_success is False:
        # nodes antigos que ainda não setam last_action_status
        lines.append(f"LAST_ACTION: {state.last_action} (⚠️ falhou)")
        lines.append("   INSTRUÇÃO: A última ação não foi bem sucedida. Tente abordagem alternativa.")

    # 2. CRITICAL IDs
    if state.tracking_url:
        lines.append(f"\n🚚 TRACKING_URL: {state.tracking_url}")

    if state.order_id:
        lines.append(f"📦 ORDER_ID: {state.order_id}")

    # 3. PRODUCT DATA (Sales Flow)
    if domain == "sales":
        # Get focused product ID if set
        focused_product_id = state.soft_context.get("focused_product_id")
        selected_variant_id = state.soft_context.get("selected_variant_id")

        # PRIORITY 1: focused_product_id set - User is asking about a SPECIFIC product
        # Show ONLY that product with FULL DESCRIPTION for grounding
        if focused_product_id and state.selected_products:
            focused_product = None
            for p in state.selected_products:
                if str(p.get("product_id") or p.get("id")) == str(focused_product_id):
                    focused_product = p
                    break
            
            if focused_product:
                title = focused_product.get("title", "Produto")
                price = _format_price(focused_product.get("price"))
                description = focused_product.get("description", "")
                
                product_url = focused_product.get("url")
                lines.append(f"\n🎯 PRODUTO EM FOCO (Responda sobre ESTE produto):")
                lines.append(f"   Nome: {title}")
                lines.append(f"   Preço: {price}")
                if product_url:
                    lines.append(f"   🔗 URL: {product_url}")
                else:
                    lines.append(f"   🔗 URL: (não disponível — se cliente pedir link, diga que vai confirmar)")
                if description:
                    # Include FULL description for grounding to prevent hallucination
                    lines.append(f"   📋 DESCRIÇÃO TÉCNICA: {description}")
                    lines.append("   ⚠️ IMPORTANTE: Responda sobre materiais/detalhes APENAS com base na descrição acima.")
                    lines.append("   ⚠️ Se a informação não estiver aqui, diga: 'Não tenho essa informação específica'.")
                else:
                    lines.append("   (Sem descrição detalhada disponível)")
                
                # Show variant options if available
                if state.available_variants:
                    lines.append("\n   Variantes disponíveis:")
                    for v in state.available_variants[:5]:
                        available = v.get("available", True)
                        status = "" if available else "(ESGOTADO)"
                        lines.append(f"     - {v.get('title', 'Opção')} {status}")
                
                lines.append("\n   (NÃO liste outros produtos. Foque neste.)")
        
        # PRIORITY 3: No focus - Vitrine mode - show list for selection
        elif state.selected_products:
            lines.append("\n🛒 PRODUTOS ENCONTRADOS (Vitrine):")
            for idx, p in enumerate(state.selected_products, 1):
                title = p.get("title", "Produto")
                price = _format_price(p.get("price"))
                product_url = p.get("url")
                if product_url:
                    lines.append(f"   {idx}. {title} - {price}")
                    lines.append(f"      🔗 {product_url}")
                else:
                    lines.append(f"   {idx}. {title} - {price} (sem link)")
                desc = (p.get("description") or "").strip()
                if desc:
                    desc_trunc = desc[:150] + ("..." if len(desc) > 150 else "")
                    lines.append(f"      📋 DESC: {desc_trunc}")
            lines.append("   (Use as URLs acima se cliente pedir link. Se não houver URL, diga que vai confirmar.)")
            lines.append("   ⚠️ Responda sobre atributos APENAS com base nas descrições acima. Se a info não estiver lá, diga \"não tenho essa info específica\" e ofereça confirmar com a equipe.")
        
        # Search Results Context
        if state.last_action == "action_search_products":
             count = state.soft_context.get("search_results_count", 0)
             lines.append(f"\n🔍 BUSCA RECENTE: Encontrei {count} produtos para '{state.search_query or 'busca'}'")
             if count == 0:
                 lines.append(
                     "   → Nenhum produto encontrado para essa query.\n"
                     "   ATENÇÃO: avalie se a query do cliente foi específica ou vaga.\n"
                     "   - Se a query foi ESPECÍFICA (ex: 'tem mop?', 'pulverizador 6 litros'): "
                     "responda honestamente que não temos esse item (ver EXEMPLO 3).\n"
                     "   - Se a query foi VAGA (ex: 'queria um produto', 'saber mais', "
                     "'tem coisas pra carro?'): NÃO diga que não tem. PERGUNTE qual produto "
                     "ou categoria interessa antes de assumir (ver EXEMPLO 14)."
                 )

    # 4. SUPPORT DATA
    if domain == "support":
        has_order_data = state.order_id or state.soft_context.get("shopify_order_id")

        if has_order_data:
            lines.append("\n📦 DADOS DO PEDIDO ENCONTRADO:")

            order_number = state.soft_context.get("order_number") or state.order_id
            if order_number:
                lines.append(f"- Número do pedido: #{order_number}")

            order_status = state.soft_context.get("order_status")
            if order_status:
                lines.append(f"- Status do pagamento: {order_status}")

            fulfillment_status = state.soft_context.get("fulfillment_status")
            if fulfillment_status:
                _status_labels = {
                    "fulfilled": "Enviado (com transportadora)",
                    "unfulfilled": "Aguardando envio",
                    "partial": "Parcialmente enviado",
                    "delivered": "Entregue (segundo transportadora)",
                }
                label = _status_labels.get(fulfillment_status, fulfillment_status)
                lines.append(f"- Status de envio: {label}")

            order_created_at = state.soft_context.get("order_created_at")
            if order_created_at:
                lines.append(f"- Data do pedido: {order_created_at}")

            if state.tracking_url:
                lines.append(f"- 🚚 Link de rastreio: {state.tracking_url}")
                days_since = state.tracking_last_update_days
                if days_since is not None:
                    if days_since >= 7:
                        lines.append(
                            f"- ⚠️ ATENÇÃO: tracking não atualiza há {days_since} dias. "
                            "Reconheça o atraso E ofereça abrir um chamado se cliente quiser."
                        )
                    elif days_since >= 4:
                        lines.append(
                            f"- ⚠️ Tracking não atualiza há {days_since} dias. "
                            "Demonstre empatia, mas evite alarmar — pode ser normal dependendo da transportadora."
                        )
                    else:
                        lines.append(f"- Tracking atualizado há {days_since} dia(s)")
            elif fulfillment_status == "unfulfilled":
                lines.append(
                    "- Sem código de rastreio ainda (pedido pago mas não despachado)"
                )
            else:
                lines.append("- Sem link de rastreio disponível")

            order_items = state.soft_context.get("order_items") or []
            if order_items:
                items_str = ", ".join(
                    str(item.get("title", item.get("name", "item")))[:50]
                    for item in order_items[:3]
                )
                lines.append(f"- Itens: {items_str}")

            lines.append("")
            lines.append("⚠️ REGRAS PARA RESPONDER SOBRE ESTE PEDIDO:")
            lines.append("- NUNCA invente prazo de entrega. Você NÃO sabe quando vai chegar.")
            lines.append("- Se cliente perguntar 'quando chega?', oriente a clicar no link de rastreio.")
            lines.append("- Se NÃO há link de rastreio, diga que ainda não foi despachado e que o link aparece quando a transportadora coletar.")
            lines.append("- Se status for 'delivered' mas cliente diz que não recebeu, NÃO tente resolver — encaminhe para humano.")
            lines.append("- Se rastreio não atualiza há muitos dias, reconheça e ofereça abrir um chamado.")
            lines.append("- NUNCA invente nome de transportadora se não estiver nos dados.")

        elif state.last_action == "action_get_order" and state.last_action_status == "empty":
            lines.append("\n📭 PEDIDO NÃO ENCONTRADO:")
            lines.append("- A busca pelo número/email do cliente não retornou resultado.")
            lines.append("")
            lines.append("⚠️ REGRAS:")
            lines.append("- Peça gentilmente para o cliente confirmar o número do pedido OU o email usado na compra.")
            lines.append("- NÃO invente que o pedido existe.")
            lines.append("- Se for a 2ª vez pedindo o mesmo dado, ofereça encaminhar para um atendente humano.")

        if state.customer_email:
            lines.append(f"- Email cadastrado: {state.customer_email}")

        ticket_id = state.soft_context.get("ticket_id") or (
            state.soft_context.get("ticket_opened") and "aberto"
        )
        if ticket_id:
            lines.append(f"- Ticket aberto: {ticket_id}")

    # 4b. STORE Q&A DATA
    elif domain == "store_qa":
        intent_labels = {
            "shipping_question": "🚚 Pergunta sobre frete/entrega",
            "payment_question": "💳 Pergunta sobre formas de pagamento",
            "return_exchange": "🔁 Pergunta sobre troca/devolução/reembolso",
            "store_question": "🏪 Dúvida geral sobre a loja",
            "general": "💬 Conversa geral / pergunta não categorizada",
        }
        intent = state.intent or "general"
        label = intent_labels.get(intent, f"❓ Intent: {intent}")
        lines.append("\nPERGUNTA DO CLIENTE — categoria:")
        lines.append(f"- {label}")

        has_kb_content = bool(
            knowledge_context
            and "Nenhuma informação" not in knowledge_context
            and len(knowledge_context.strip()) > 20
        )

        if has_kb_content:
            lines.append("- 📚 Base de conhecimento TEM informação relevante (veja seção BASE DE CONHECIMENTO abaixo).")
        else:
            lines.append("- 📭 Base de conhecimento NÃO tem informação específica para essa pergunta.")

        lines.append("")
        lines.append("⚠️ REGRAS PARA RESPONDER ESSA PERGUNTA:")
        lines.append("- Responda APENAS com base na BASE DE CONHECIMENTO (quando presente). Se não houver base ou ela não cobrir a pergunta, NÃO invente.")
        lines.append("- NUNCA invente prazo de frete, formas de pagamento aceitas, política de troca, ou valores.")
        lines.append("- NÃO improvise informação que parece 'padrão' (ex: 'frete grátis acima de R$ 200', 'aceitamos PIX'). Confirme na base ou diga que não sabe.")

        if intent == "return_exchange":
            lines.append("- ⚠️ TROCA/DEVOLUÇÃO é assunto sensível. Se a base não tem política CLARA e ESPECÍFICA, encaminhe para humano em vez de tentar responder.")

        if not has_kb_content:
            lines.append("- Se você não sabe a resposta, diga honestamente e ofereça encaminhar para um atendente humano.")
            lines.append("- AÇÃO RECOMENDADA: ofereça encaminhar para a equipe humana — eles podem confirmar a informação que você não tem.")

    # 5. KNOWLEDGE BASE (RAG)
    if knowledge_context and "Nenhuma informação" not in knowledge_context:
        lines.append(f"\n📚 BASE DE CONHECIMENTO (RAG):\n{knowledge_context}")
    
    # 6. MEMORY / INTENT CONTEXT
    lines.append(f"\n🧠 CONTEXTO ATUAL:")
    lines.append(f"- Intenção: {state.intent}")
    lines.append(f"- Frustração: {state.frustration_level}/5")
    # Using RAG context if explicit memory is needed
    if state.rag_context:
        lines.append(f"- RAG Memory: {state.rag_context[:200]}...")

    # 7. BLOCKING INFO (What we need to ask)
    if state.blocking_info:
        lines.append(f"\n⚠️ DADOS FALTANTES (Pergunte ao cliente):")
        for info in state.blocking_info:
            lines.append(f"- {info}")

    return "\n".join(lines)


# =============================================================================
# RESPONSE GENERATION
# =============================================================================


def generate_humanized_response(
    state: ConversationState,
    tenant: TenantConfig,
    domain: str,
    categories: list[str] | None = None,
) -> str:
    """Generate a humanized LLM response using the Response Synthesizer."""
    
    # 1. Get RAG Context (semantic search)
    user_msg = state.last_user_message or ""
    # Only fetch RAG if relevant (Context optimization)
    if domain == "store_qa" or "como" in user_msg.lower() or "onde" in user_msg.lower():
         knowledge_context = get_knowledge_context(
            tenant.tenant_id, 
            categories,
            user_message=user_msg
        )
    else:
        # Minimal RAG for transactional flows to save tokens/noise
        knowledge_context = "" 
    
    # 2. Build Components
    history_str = _get_conversation_history_string(state)
    payload_str = _get_system_data_payload(state, tenant, domain, knowledge_context)

    # 3. Format Master Prompt
    system_prompt = RESPONSE_SYNTHESIZER_PROMPT.format(
        tenant_name=tenant.name,
        conversation_history=history_str,
        system_data_payload=payload_str
    )
    
    # Debug
    if os.getenv("DEBUG"):
        print(f"\n[SYNTHESIZER] Payload:\n{payload_str}\n")
    
    # 4. Call LLM
    model = get_model_name()
    llm = ChatOpenAI(model=model, temperature=0.6) # Slightly lower temp for adherence
    
    # We pass the prompt as System Message. 
    # The prompt explicitly contains "Contexto da Conversa" so we don't strictly need a HumanMessage 
    # with the last input, but we add a trigger to start generation.
    result = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content="Gere a resposta agora."),
    ])
    
    response = (result.content or "").strip()
    
    # 5. Metadata & Cleanup
    usage_raw = result.response_metadata.get("token_usage")
    state.soft_context["token_usage_agent"] = normalize_token_usage(usage_raw)
    
    if not response:
        raise ValueError("LLM returned empty response")
    
    # Clean quotes
    if response.startswith('"') and response.endswith('"'):
        response = response[1:-1]
    
    return response
