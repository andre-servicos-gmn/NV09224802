"""Support decision node.

Responsabilidade: decidir o proximo passo sem executar acoes ou gerar texto.

TERMINOLOGIA DE IDS DE PEDIDO (Shopify):
=========================================
- order_number: ID visível ao cliente (ex: 1001, 1002).
  É o que o cliente fornece e vê no email de confirmação.
  SEMPRE use este para interagir com o cliente.

- order_name: Formato com prefixo "#" (ex: "#1001", "#1002").
  Usado internamente pela Shopify na API (campo "name").
  Ao buscar por order_number, a Shopify filtra por este campo.

- shopify_order_id: ID interno Shopify (ex: 5832749012345678).
  ID numérico longo usado na API para endpoints /orders/{id}.json.
  NUNCA pedir ao cliente — é interno do sistema.

REGRAS DE GROUNDING:
====================
1. NUNCA inventar SLA de entrega (ex: "chega em 3 dias").
2. NUNCA inventar status de pedido não retornado pela API.
3. NUNCA inventar número de rastreio ou URL de tracking.
4. Se não houver tracking_url, dizer "ainda não há rastreio disponível".
5. NUNCA pedir shopify_order_id ao cliente — usar order_number.
6. Não criar dados fictícios no Decide — apenas rotear.

FLUXO DE FALLBACK:
==================
- Se state.order_id existe → buscar por order_number.
- Se não encontrar e state.customer_email existe → fallback por email.
- Se NENHUM dos dois existe → support_respond pede ao cliente.
"""
import re

from app.core.constants import (
    INTENT_ORDER_COMPLAINT,
    INTENT_ORDER_STATUS,
    INTENT_ORDER_TRACKING,
    INTENT_PROVIDE_EMAIL,
    INTENT_PROVIDE_ORDER_ID,
)
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def normalize_order_input(raw: str) -> str | None:
    """
    Normaliza input do cliente para order_number.

    Exemplos:
        "1001"   → "1001"
        "#1001"  → "1001"
        " #1001 " → "1001"
        "abc"    → None

    Args:
        raw: String fornecida pelo cliente.

    Returns:
        order_number normalizado (apenas dígitos) ou None se inválido.
    """
    if not raw:
        return None
    cleaned = raw.strip().lstrip("#").strip()
    if not cleaned.isdigit() or len(cleaned) < 3:
        return None
    return cleaned


def _extract_order_id(message: str) -> str | None:
    """Extrai order_number (3+ dígitos) de mensagem livre."""
    match = re.search(r"#?(\d{3,})\b", message)
    if not match:
        return None
    return match.group(1)  # Retorna apenas os dígitos, sem #


def _extract_email(message: str) -> str | None:
    match = re.search(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", message.lower())
    if not match:
        return None
    return match.group(0)


def _reset_order_context(state: ConversationState) -> None:
    state.tracking_url = None
    state.tracking_last_update_days = None
    state.ticket_opened = False
    state.metadata.pop("tracking_number", None)
    state.metadata.pop("fulfillment_status", None)
    state.metadata.pop("order_status", None)


def support_decide(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    if state.needs_handoff or state.frustration_level >= 3:
        state.next_step = "handoff"
        state.last_action = "route_to_handoff"
        state.last_action_success = True
        return state

    message = state.last_user_message or ""
    order_id = _extract_order_id(message)
    email = _extract_email(message)

    if order_id and order_id != state.order_id:
        state.order_id = order_id
        _reset_order_context(state)

    if email and email != state.customer_email:
        state.customer_email = email

    if state.intent in {INTENT_PROVIDE_ORDER_ID, INTENT_PROVIDE_EMAIL}:
        if state.order_id or state.customer_email:
            state.next_step = "action_get_order"
        else:
            state.next_step = "support_respond"
        return state

    if state.intent in {INTENT_ORDER_STATUS, INTENT_ORDER_TRACKING, INTENT_ORDER_COMPLAINT}:
        if state.order_id or state.customer_email:
            if state.intent == INTENT_ORDER_COMPLAINT:
                state.next_step = "action_open_ticket"
            elif state.intent == INTENT_ORDER_TRACKING and state.tracking_url:
                state.next_step = "support_respond"
            else:
                state.next_step = "action_get_order"
        else:
            state.next_step = "support_respond"
        return state

    state.next_step = "support_respond"
    return state
