"""
Support Decide Node.

Responsabilidade: Decidir o próximo passo do suporte com base no estado.
NUNCA chama APIs. NUNCA gera texto ao usuário.
Segue o contrato do AGENT.md.
"""
import os
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.core.constants import (
    INTENT_ORDER_STATUS,
    INTENT_ORDER_TRACKING,
    INTENT_ORDER_COMPLAINT,
    INTENT_PROVIDE_ORDER_ID,
    INTENT_PROVIDE_EMAIL,
)

WISMO_INTENTS = {
    INTENT_ORDER_STATUS,
    INTENT_ORDER_TRACKING,
    INTENT_ORDER_COMPLAINT,
    INTENT_PROVIDE_ORDER_ID,
    INTENT_PROVIDE_EMAIL,
}


def support_decide(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """
    Decide o próximo nó do support_graph com base no estado.

    Lógica de decisão:
    1. Se frustration_level >= 3 → handoff
    2. Se needs_handoff == True → handoff
    3. Se intent é WISMO E ainda não buscamos o pedido → action_get_order
    4. Se intent é WISMO MAS já buscamos E faltam dados → support_respond (vai pedir email/pedido)
    5. Se needs_resolution ou ticket aberto recentemente → action_open_ticket (se aplicável)
    6. Caso padrão → support_respond
    """
    if os.getenv("DEBUG"):
        print(f"[support_decide] intent={state.intent}, wismo_done={state.wismo_lookup_done}, "
              f"order_id={state.order_id}, email={state.customer_email}, "
              f"phone={state.customer_phone}, frustration={state.frustration_level}")

    # --- Regra 1 e 2: Escalada humana ---
    if state.needs_handoff or state.frustration_level >= 3:
        state.next_step = "handoff"
        return state

    # --- Regra 3: Intent de rastreio E ainda não buscamos ---
    # Reset wismo_lookup_done if user just provided new identifying data
    if state.intent in WISMO_INTENTS and state.wismo_lookup_done:
        # If user provided fresh email or order_id, allow a new lookup
        if state.intent in {INTENT_PROVIDE_EMAIL, INTENT_PROVIDE_ORDER_ID}:
            if os.getenv("DEBUG"):
                print(f"[support_decide] Resetting wismo_lookup_done — user provided new data")
            state.wismo_lookup_done = False

    if state.intent in WISMO_INTENTS and not state.wismo_lookup_done:
        state.next_step = "action_get_order"
        return state

    # --- Regra 4: Intent de rastreio, já buscamos, mas ainda faltam dados ---
    # (action_get_order setou wismo_lookup_done=True mas não encontrou pedido)
    if state.intent in WISMO_INTENTS and state.wismo_lookup_done:
        # Se encontrou dados, support_respond vai formatar a resposta
        # Se não encontrou, support_respond vai pedir mais info
        state.next_step = "support_respond"
        return state

    # --- Regra 5: Abertura de ticket ---
    if state.intent == INTENT_ORDER_COMPLAINT and not state.ticket_opened:
        state.next_step = "action_open_ticket"
        return state

    # --- Padrão ---
    state.next_step = "support_respond"
    return state
