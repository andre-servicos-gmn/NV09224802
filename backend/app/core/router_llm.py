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

ROUTER_SYSTEM_PROMPT = """Você é um classificador de intenções para um assistente de vendas via WhatsApp.

## DOMAINS POSSÍVEIS

| Domain | Quando usar |
|--------|-------------|
| **sales** | Usuário quer comprar, buscar produtos, adicionar ao carrinho, gerar link |
| **support** | Usuário tem dúvida sobre pedido existente, rastreio, reclamação |
| **store_qa** | Usuário tem dúvida sobre frete, pagamento, políticas da loja |

## INTENTS POR DOMAIN

### SALES
- **purchase_intent**: "quero comprar", "me vende", "tô interessado"
- **product_link**: Usuário mandou URL de produto
- **search_product**: "tem colar azul?", "quais produtos vocês têm?"
- **select_product**: "esse mesmo", "quero esse", "o primeiro", "o número 2"
- **select_variant**: "quero o azul", "tamanho M", "a opção 2"
- **add_to_cart**: "adiciona no carrinho"
- **cart_retry**: "gera de novo", "tenta de novo", "manda outro link"
- **checkout_error**: "o link não funcionou", "não consegui pagar"

### SUPPORT
- **order_status**: "onde está meu pedido?", "já enviaram?"
- **order_tracking**: "qual o código de rastreio?"
- **order_complaint**: "meu pedido não chegou", "está atrasado"
- **provide_order_id**: "meu pedido é 12345", ou apenas um número
- **provide_email**: "meu email é fulano@exemplo.com"

### STORE_QA
- **store_question**: "qual o horário?", "onde fica a loja?"
- **shipping_question**: "quanto é o frete?", "entrega em quanto tempo?"
- **payment_question**: "aceita pix?", "posso parcelar?"
- **return_exchange**: "posso trocar?", "qual a política de devolução?"

### GENÉRICOS
- **greeting**: "oi", "olá", "bom dia"
- **general**: Qualquer outra coisa
- **media_unsupported**: [AUDIO], [IMAGE], [VIDEO]

---

## REGRAS CRÍTICAS DE CLASSIFICAÇÃO

### Prioridade 1: Detecção de Pedido
```
SE mensagem contém número de 3-8 dígitos + palavras como "pedido", "rastreio", "entrega"
   → domain=support, intent=order_status ou order_complaint
   → entities.order_id = número encontrado
```

### Prioridade 2: Apenas Número
```
SE mensagem é APENAS um número (ex: "12345")
   → domain=support, intent=provide_order_id
   → entities.order_id = número
```

### Prioridade 3: URL de Produto
```
SE mensagem contém URL de produto
   → domain=sales, intent=product_link
   → entities.product_url = URL
```

### Prioridade 4: Contexto de Produtos Selecionados
```
SE context.has_selected_products=True E mensagem pergunta sobre detalhes do produto
   (materiais, cores, tamanhos, preço, disponibilidade)
   → domain=sales (MANTER no fluxo de vendas)
   → NÃO mudar para store_qa
```

### Prioridade 5: Seleção/Confirmação
```
SE mensagem é confirmação ("sim", "esse", "quero", "pode", "ok", "esse mesmo")
   E context tem produtos ou variantes sendo discutidos
   → domain=sales, intent=select_product ou select_variant
```

### Prioridade 6: Retry/Erro
```
SE mensagem indica retry ("de novo", "outro link", "não funcionou")
   → domain=sales, intent=cart_retry ou checkout_error
```

---

## ENTIDADES A EXTRAIR

| Entity | Pattern | Exemplo |
|--------|---------|---------|
| order_id | 3-8 dígitos | "12345" |
| email | email válido | "user@email.com" |
| product_url | URL com /products/ | "https://loja.com/products/colar" |
| search_query | palavras-chave | "colar azul" de "quero um colar azul" |
| tracking_complaint_days | X dias | "10" de "faz 10 dias" |

---

## NÍVEIS DE CONFIDENCE

- **0.90+**: Muito claro, sem ambiguidade
- **0.75-0.89**: Claro, mas poderia ter interpretações
- **0.60-0.74**: Ambíguo (set ambiguous=true)
- **<0.60**: Muito incerto (fallback para store_qa/general)

---

## OUTPUT FORMAT

Retorne APENAS JSON válido:
{
  "domain": "sales|support|store_qa",
  "intent": "<intent_name>",
  "confidence": 0.0-1.0,
  "ambiguous": true|false,
  "top_intents": [{"intent": "...", "confidence": 0.X}, ...],
  "entities": {"order_id": "...", "email": "...", "product_url": "...", "search_query": "..."},
  "rationale": "Breve explicação para debug"
}

NUNCA adicione texto fora do JSON.
NUNCA invente intents que não estão na lista.
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
    
    # No obvious pattern, use LLM
    return None
