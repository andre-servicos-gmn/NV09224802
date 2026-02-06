# Modified: improved router prompt with better context and examples.
"""LLM-powered intent/domain classification router.

Uses OpenAI to classify user messages into domain/intent with entity extraction.
"""

import os
import re
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError, confloat

from app.core.constants import INTENT_DESCRIPTIONS, SUPPORTED_DOMAINS, SUPPORTED_INTENTS
from app.core.llm import get_model_name
from app.core.llm_utils import normalize_token_usage


# =============================================================================
# CONFIDENCE THRESHOLDS (increased for better accuracy)
# =============================================================================

MIN_CONFIDENCE = 0.75      # Minimum to accept LLM result
HIGH_CONFIDENCE = 0.85     # Skip sanity check if above this
AMBIGUOUS_THRESHOLD = 0.75 # Below this = ambiguous


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

IntentLiteral = Literal[*SUPPORTED_INTENTS]
DomainLiteral = Literal[*SUPPORTED_DOMAINS]


class TopIntent(BaseModel):
    intent: IntentLiteral
    confidence: confloat(ge=0.0, le=1.0)


class RouterResult(BaseModel):
    domain: DomainLiteral
    intent: IntentLiteral
    confidence: confloat(ge=0.0, le=1.0)
    ambiguous: bool = False
    top_intents: list[TopIntent] = Field(default_factory=list)
    entities: dict = Field(default_factory=dict)
    rationale: str = ""
    token_usage: dict = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


# =============================================================================
# IMPROVED SYSTEM PROMPT
# =============================================================================

ROUTER_SYSTEM_PROMPT = """## MISSÃO
Sua tarefa é identificar a intenção do cliente de um e-commerce no WhatsApp.
Em vez de buscar palavras-chave, analise o MOMENTO e o OBJETIVO da jornada do usuário.

## DOMÍNIOS E LÓGICA DE NEGÓCIO

1. **SALES** (Foco: Conversão e Produto)
   - O usuário está no "topo ou meio do funil".
   - Ele quer descobrir o que existe, tirar dúvidas sobre um item (material, cor, tamanho) ou avançar para o pagamento.
   - Pense: "O usuário quer gastar dinheiro ou saber sobre o que pode comprar?"
   - **Regra de Ouro**: Se o contexto já é sobre um produto e o usuário faz perguntas curtas ("é de ouro?", "tem G?", "qual o preço?"), MANTENHA em SALES.

2. **SUPPORT** (Foco: Pós-Venda)
   - O usuário já tem um vínculo transacional (um pedido feito ou tentado).
   - Ele está ansioso, reclamando ou buscando informação de algo que já "é dele".
   - Pense: "O usuário está rastreando um valor que já saiu do bolso dele?"
   - **Regra de Ouro**: Se mencionar status de entrega, atrasos ou defeitos, é SUPPORT.

3. **STORE_QA** (Foco: Institucional)
   - Dúvidas genéricas que não dependem do catálogo de produtos nem de um CPF/Pedido.
   - Perguntas sobre regras da empresa (horário, política de troca, localização).
   - Pense: "Isso é uma regra da empresa ou uma dúvida sobre um objeto específico?"
   - **⚠️ ATENÇÃO**: Perguntas sobre "produtos", "catálogo", "o que vocês vendem", "quais produtos têm" são SALES (search_product), NÃO store_qa!

---

## INTENTS (Referência Técnica)

### SALES GRUPO (Priorize se cliente já está discutindo produto)
- **purchase_intent**: SINAL DE COMPRA! Exemplos: "quero comprar", "bora fechar", "vou levar", "quero esse", "quero garantir", "pode mandar o link", "me manda", "sim, quero", "fecha", "bora", "aceito", "tô dentro", "manda o pix"
  → Se cliente CONFIRMOU interesse ("quero", "sim", "bora") após ver produto = purchase_intent
- **product_link**: URL de produto
- **search_product**: Busca de itens, catálogo, perguntas sobre "o que vocês têm", "quais produtos", "me mostra", "quero ver produtos" ou especificidades de um produto (cor, material, tamanho). Também: "produtos da loja", "o que vendem", "catálogo"
- **select_product**: Escolha entre opções ("o primeiro", "esse")
- **select_variant**: Escolha de variação ("azul", "tamanho M")
- **add_to_cart**: Adicionar ao carrinho
- **cart_retry**: Pedir link novamente
- **checkout_error**: Erro no pagamento
- **greeting**: Oi, Olá (Início de conversa = Venda)
- **general**: Conversa fiada (Manter engajamento = Venda)

### SUPPORT GRUPO
- **order_status**: Rastreio, onde está
- **order_tracking**: Pedir código
- **order_complaint**: Reclamação de atraso/defeito
- **provide_order_id**: Número do pedido
- **provide_email**: Email do cliente

### STORE_QA GRUPO
- **store_question**: Horários, endereço
- **shipping_question**: Frete geral (não de pedido específico)
- **payment_question**: Formas de pagamento
- **return_exchange**: Regras de devolução
- **media_unsupported**: Arquivos de mídia

---

## ENTIDADES A EXTRAIR
- `order_id`: Sequência numérica (3-8 dígitos)
- `email`: Formato de email
- `product_url`: Links da loja
- `search_query`: O termo de busca (ex: "colar de ouro" em "quero um colar de ouro")

---

## OUTPUT FORMAT (JSON Obrigatório)
Retorne APENAS JSON válido, sem markdown:
{
  "domain": "sales|support|store_qa",
  "intent": "<intent_name>",
  "confidence": 0.0-1.0,
  "ambiguous": true|false,
  "entities": {"..."},
  "rationale": "Explique o raciocínio: 'Usuário está no meio do funil perguntando sobre material...'"
}
"""


# =============================================================================
# CONTEXT BUILDING
# =============================================================================

def _build_intent_reference(intents: list[str]) -> str:
    """Build intent reference list."""
    lines = []
    for intent in intents:
        description = INTENT_DESCRIPTIONS.get(intent, "No description.")
        lines.append(f"- {intent}: {description}")
    return "\n".join(lines)


def _build_conversation_context(context: dict | None) -> str:
    """Build conversation context block."""
    if not context:
        return "Nenhum contexto anterior."
    
    lines = []
    
    # Key context flags
    if context.get("has_selected_products"):
        count = context.get("selected_products_count", 0)
        lines.append(f"✓ Produtos selecionados: {count}")
        if context.get("last_products_discussed"):
            lines.append(f"  → {context['last_products_discussed']}")
    
    if context.get("has_variant_id"):
        lines.append("✓ Variante já escolhida")
    
    if context.get("has_order_id"):
        lines.append("✓ Order ID já fornecido")
    
    if context.get("last_domain"):
        lines.append(f"• Último domain: {context['last_domain']}")
    
    if context.get("last_intent"):
        lines.append(f"• Último intent: {context['last_intent']}")
    
    if context.get("store_name"):
        lines.append(f"• Loja: {context['store_name']}")
    
    if context.get("store_niche"):
        lines.append(f"• Nicho: {context['store_niche']}")
    
    return "\n".join(lines) if lines else "Nenhum contexto relevante."


def _build_user_prompt(message: str, intents: list[str], context: dict | None) -> str:
    """Build the user prompt with message and context."""
    intent_lines = _build_intent_reference(intents)
    context_block = _build_conversation_context(context)
    
    # Check for obvious patterns to help the LLM
    hints = []
    
    # URL detection
    if re.search(r'https?://\S+', message):
        hints.append("⚠️ Mensagem contém URL")
    
    # Number-only detection
    if re.match(r'^\d{3,8}$', message.strip()):
        hints.append("⚠️ Mensagem é apenas um número (provável order_id)")
    
    # Order keywords
    if any(w in message.lower() for w in ['pedido', 'rastreio', 'entrega', 'não chegou', 'atrasado']):
        hints.append("⚠️ Menciona termos de pedido/entrega")
    
    # Confirmation keywords
    if re.match(r'^(sim|quero|esse|pode|ok|beleza|bora|yes|manda|claro|aceito)\W*$', message.lower().strip()):
        hints.append("⚠️ Parece ser confirmação simples")
    
    hints_block = "\n".join(hints) if hints else ""
    
    prompt = f"""## MENSAGEM DO USUÁRIO
"{message}"

## CONTEXTO DA CONVERSA
{context_block}

## INTENTS SUPORTADOS
{intent_lines}
"""
    
    if hints_block:
        prompt += f"""
## OBSERVAÇÕES AUTOMÁTICAS
{hints_block}
"""
    
    prompt += """
---
Retorne APENAS o JSON de classificação."""
    
    return prompt


# =============================================================================
# MAIN CLASSIFICATION FUNCTION
# =============================================================================

def classify_with_llm(
    message: str,
    context: dict | None,
    intents: tuple[str, ...],
    timeout_s: float | None = None,
) -> RouterResult:
    """Classify message intent and domain using LLM.
    
    Args:
        message: User message to classify
        context: Conversation context (has_selected_products, last_domain, etc.)
        intents: Supported intents tuple
        timeout_s: Request timeout in seconds
    
    Returns:
        RouterResult with domain, intent, confidence, entities
    
    Raises:
        RuntimeError: If OPENAI_API_KEY not set
        ValueError: If intents list invalid or LLM returns invalid JSON
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")
    if not intents:
        raise ValueError("Intents list is empty.")
    for intent in intents:
        if intent not in SUPPORTED_INTENTS:
            raise ValueError(f"Unsupported intent: {intent}")

    llm = ChatOpenAI(
        model=get_model_name(), 
        temperature=0, 
        request_timeout=timeout_s
    )
    
    system_prompt = ROUTER_SYSTEM_PROMPT
    user_prompt = _build_user_prompt(message, list(intents), context)
    
    result = llm.invoke([
        SystemMessage(content=system_prompt), 
        HumanMessage(content=user_prompt)
    ])
    
    content = (result.content or "").strip()
    
    # Clean markdown code blocks if present
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()
    
    try:
        router_result = RouterResult.model_validate_json(content)
        
        # Capture token usage
        usage_raw = result.response_metadata.get("token_usage")
        router_result.token_usage = normalize_token_usage(usage_raw)
        
        return router_result
        
    except ValidationError as exc:
        raise ValueError(f"Invalid router JSON: {content[:200]}") from exc


# =============================================================================
# QUICK HEURISTIC CLASSIFICATION (for obvious cases)
# =============================================================================

def classify_heuristic(message: str, context: dict | None = None) -> RouterResult | None:
    """Quick heuristic classification for obvious patterns.
    
    Returns None if no obvious pattern found (should use LLM).
    """
    msg_lower = message.lower().strip()
    
    # Media messages
    if msg_lower.startswith(("[audio]", "[image]", "[video]", "[media]")):
        return RouterResult(
            domain="store_qa",
            intent="media_unsupported",
            confidence=1.0,
            ambiguous=False,
            rationale="Media message detected",
        )
    
    # Number-only (order_id)
    if re.match(r'^\d{3,8}$', msg_lower):
        return RouterResult(
            domain="support",
            intent="provide_order_id",
            confidence=0.95,
            ambiguous=False,
            entities={"order_id": msg_lower},
            rationale="Number-only message",
        )
    
    # Email-only
    email_match = re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', msg_lower)
    if email_match:
        return RouterResult(
            domain="support",
            intent="provide_email",
            confidence=0.95,
            ambiguous=False,
            entities={"email": msg_lower},
            rationale="Email-only message",
        )
    
    # URL with products
    url_match = re.search(r'https?://\S*products/\S+', message)
    if url_match:
        return RouterResult(
            domain="sales",
            intent="product_link",
            confidence=0.95,
            ambiguous=False,
            entities={"product_url": url_match.group(0)},
            rationale="Product URL detected",
        )
    
    # ==========================================================================
    # CRITICAL: Simple confirmation with product context → purchase_intent
    # When user says "sim", "quero", "bora", etc. AND there are selected products,
    # this is a PURCHASE CONFIRMATION. Skip LLM and route directly to generate link.
    # ==========================================================================
    confirmation_patterns = [
        r'^(sim|quero|esse|pode|ok|beleza|bora|yes|manda|claro|aceito|isso|fechou?|vou levar|quero esse|pode ser|manda o link|gera o link|me manda|por favor|pfv|pf)\W*$',
        r'^(sim|quero),?\s*(por favor|pfv|pode)?\W*$',
        r'^gera\s*(o link|pra mim)?\W*$',
        r'^manda\s*(o link|pra mim|ai)?\W*$',
    ]
    
    has_products = context and context.get("has_selected_products")
    
    for pattern in confirmation_patterns:
        if re.match(pattern, msg_lower, re.IGNORECASE):
            if has_products:
                return RouterResult(
                    domain="sales",
                    intent="purchase_intent",
                    confidence=0.98,
                    ambiguous=False,
                    rationale="Simple confirmation with product context → purchase",
                )
    
    # No obvious pattern, use LLM
    return None
