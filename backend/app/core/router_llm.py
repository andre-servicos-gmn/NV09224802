# Modified: Router for consultant mode — no cart/purchase intents.
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
# CONFIDENCE THRESHOLDS
# =============================================================================

MIN_CONFIDENCE = 0.75
HIGH_CONFIDENCE = 0.85
AMBIGUOUS_THRESHOLD = 0.75


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
# SYSTEM PROMPT — MODO CONSULTOR
# =============================================================================

ROUTER_SYSTEM_PROMPT = """## MISSÃO
Você é o roteador de um assistente consultor de produtos de um e-commerce no WhatsApp.
O assistente NÃO realiza vendas, NÃO gera links de carrinho e NÃO processa pagamentos.
Ele apenas tira dúvidas sobre produtos, ajuda a descobrir o catálogo e esclarece informações.

## DOMÍNIOS

1. **SALES** (Foco: Consultoria de Produto)
   - O usuário quer descobrir produtos, tirar dúvidas sobre itens (material, cor, tamanho, preço) ou entender o catálogo.
   - Pense: "O usuário quer saber mais sobre produtos?"
   - **REGRA DE OURO — Continuidade**: Se produtos JÁ foram apresentados (has_selected_products=true) e a mensagem é curta, uma pergunta ou comentário (ex: "pq brinco", "legal", "tem em prata?"), classifique como **general**. Use **search_product** APENAS quando o usuário pede algo NOVO explicitamente.

2. **SUPPORT** (Foco: Pós-Venda)
   - O usuário já tem um pedido e quer rastreio, reclama de atraso ou defeito.
   - **Regra de Ouro**: Se mencionar pedido, entrega, atraso ou defeito → SUPPORT.

3. **STORE_QA** (Foco: Institucional)
   - Dúvidas sobre regras da empresa (horário, troca, endereço).
   - ⚠️ "Quais produtos vocês têm?" é SALES (search_product), não store_qa.

---

## INTENTS

### SALES
- **search_product**: Busca de produtos, catálogo, dúvidas sobre especificidades de um item (cor, material, tamanho, preço). Ex: "tem colar de ouro?", "quais produtos vocês têm?", "é de prata?", "tem no tam G?"
- **greeting**: Início de conversa. Ex: "oi", "olá", "bom dia"
- **general**: Conversa de contexto, comentários, perguntas curtas sobre produto já apresentado. Ex: "legal", "me conta mais", "pq esse?"

### SUPPORT
- **order_status**: Rastreio, onde está meu pedido
- **order_tracking**: Pedir código de rastreio
- **order_complaint**: Reclamação de atraso ou defeito
- **provide_order_id**: Número do pedido fornecido pelo cliente
- **provide_email**: Email do cliente

### STORE_QA
- **store_question**: Horários, endereço, informações institucionais
- **shipping_question**: Dúvidas gerais sobre frete (não de pedido específico)
- **payment_question**: Formas de pagamento aceitas
- **return_exchange**: Política de troca e devolução
- **media_unsupported**: Mensagens de áudio, imagem ou vídeo

---

## ENTIDADES A EXTRAIR
- `order_id`: Sequência numérica (3-8 dígitos)
- `email`: Formato de email
- `search_query`: Termo de busca (ex: "colar de ouro" em "quero um colar de ouro")

---

## OUTPUT FORMAT (JSON obrigatório, sem markdown)
{
  "domain": "sales|support|store_qa",
  "intent": "<intent_name>",
  "confidence": 0.0-1.0,
  "ambiguous": true|false,
  "entities": {"..."},
  "rationale": "Explique resumidamente o raciocínio."
}
"""


# =============================================================================
# CONTEXT BUILDING
# =============================================================================

def _build_intent_reference(intents: list[str]) -> str:
    lines = []
    for intent in intents:
        description = INTENT_DESCRIPTIONS.get(intent, "")
        lines.append(f"- {intent}: {description}" if description else f"- {intent}")
    return "\n".join(lines)


def _build_conversation_context(context: dict | None) -> str:
    if not context:
        return "Nenhum contexto anterior."

    lines = []

    if context.get("has_selected_products"):
        count = context.get("selected_products_count", 0)
        lines.append(f"✓ Produtos em contexto: {count}")
        if context.get("last_products_discussed"):
            lines.append(f"  → {context['last_products_discussed']}")

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
    intent_lines = _build_intent_reference(intents)
    context_block = _build_conversation_context(context)

    hints = []

    if re.match(r'^\d{3,8}$', message.strip()):
        hints.append("⚠️ Mensagem é apenas um número (provável order_id)")

    if any(w in message.lower() for w in ['pedido', 'rastreio', 'entrega', 'não chegou', 'atrasado']):
        hints.append("⚠️ Menciona termos de pedido/entrega")

    if message.lower().strip().startswith(("[audio]", "[image]", "[video]", "[media]")):
        hints.append("⚠️ Mensagem de mídia")

    hints_block = "\n".join(hints)

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

    prompt += "\n---\nRetorne APENAS o JSON de classificação."
    return prompt


# =============================================================================
# MAIN CLASSIFICATION
# =============================================================================

def classify_with_llm(
    message: str,
    context: dict | None,
    intents: tuple[str, ...],
    timeout_s: float | None = None,
) -> RouterResult:
    """Classify message intent and domain using LLM."""
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
        request_timeout=timeout_s,
    )

    user_prompt = _build_user_prompt(message, list(intents), context)

    result = llm.invoke([
        SystemMessage(content=ROUTER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    content = (result.content or "").strip()

    # Strip markdown fences if present
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        router_result = RouterResult.model_validate_json(content)
        usage_raw = result.response_metadata.get("token_usage")
        router_result.token_usage = normalize_token_usage(usage_raw)
        return router_result

    except ValidationError as exc:
        raise ValueError(f"Invalid router JSON: {content[:200]}") from exc


# =============================================================================
# QUICK HEURISTIC CLASSIFICATION
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

    # ======================================================================
    # CONTINUITY GUARD HEURÍSTICO: mensagem curta com produtos em contexto
    # → general, não search_product
    # ======================================================================
    has_products = context and context.get("has_selected_products")

    SHORT_FOLLOWUP = re.compile(
        r'^(pq|por que|porque|como|qual|quanto|é|faz|serve|vale|gostei|'
        r'esse|esse mesmo|esse que|achei|legal|bacana|interessante|bom|gosto|'
        r'me conta mais|fala mais|me diz|não entendi|tem em|tem no|'
        r'e o|e a|e esse|e essa|e tem)\b',
        re.IGNORECASE,
    )

    if has_products and (len(msg_lower) < 40 or SHORT_FOLLOWUP.match(msg_lower)):
        return RouterResult(
            domain="sales",
            intent="general",
            confidence=0.95,
            ambiguous=False,
            rationale="Short follow-up with product context → general",
        )
    # ======================================================================
    # CATALOG BROWSING → search_product
    # ======================================================================
    product_catalog_patterns = [
        r'(?:quais|quai|qual)\s+(?:s[aã]o\s+)?(?:os\s+)?(?:produtos|itens|peças)',
        r'(?:o\s+que|oque)\s+(?:voc[eê]s?\s+)?(?:vendem?|t[eê]m)',
        r'(?:mostr[ea]|ver|vejo|veja)\s+(?:os?\s+)?(?:produtos|catálogo|catalogo|itens|peças)',
        r'(?:cat[aá]logo|catalogo|vitrine)',
        r'(?:produtos\s+(?:da\s+loja|dispon[ií]veis?|venda))',
        r'(?:tem\s+(?:algum|algo|produtos?))',
        r'(?:quero\s+ver\s+(?:os?\s+)?(?:produtos?|itens|peças))',
        r'(?:me\s+mostr[ae]\s+(?:os?\s+)?(?:produtos?|itens|peças))',
        r'(?:o\s+que\s+tem\s+(?:na\s+loja|pra\s+vender|para\s+vender))',
    ]

    for pattern in product_catalog_patterns:
        if re.search(pattern, msg_lower):
            return RouterResult(
                domain="sales",
                intent="search_product",
                confidence=0.95,
                ambiguous=False,
                entities={"search_query": message.strip()},
                rationale="Product catalog/browsing query detected",
            )

    # No obvious pattern — use LLM
    return None
