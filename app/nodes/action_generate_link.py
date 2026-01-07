"""
Action node que gera link de checkout Shopify.

Implementa lógica de estratégias: se uma estratégia falhar,
escala para a próxima (permalink -> add_to_cart -> checkout_direct -> human_handoff).
"""

from app.core.constants import INTENT_CART_RETRY, INTENT_CHECKOUT_ERROR
from app.core.state import ConversationState
from app.core.strategies import next_strategy
from app.core.tenancy import TenantConfig
from app.tools.shopify_client import ShopifyClient


def action_generate_link(
    state: ConversationState,
    tenant: TenantConfig
) -> ConversationState:
    """
    Gera link de checkout usando a estratégia apropriada.
    
    Se a última ação falhou e o intent indica retry/erro de checkout,
    escala para a próxima estratégia automaticamente.
    
    Args:
        state: Estado atual da conversa
        tenant: Configuração do tenant (com credenciais Shopify)
        
    Returns:
        ConversationState atualizado com link de checkout em metadata
    """
    # Escala estratégia se houve erro/retry
    if state.last_action_success is False and state.intent in {INTENT_CART_RETRY, INTENT_CHECKOUT_ERROR}:
        state.last_strategy = next_strategy(state.last_strategy)

    strategy = state.last_strategy or tenant.default_link_strategy or "permalink"
    
    # Se chegou em human_handoff, encaminha para atendimento humano
    if strategy == "human_handoff":
        state.last_action = "generate_link"
        state.last_strategy = strategy
        state.last_action_success = False
        state.next_step = "handoff"
        state.metadata.pop("checkout_link", None)
        return state

    # Gera link usando cliente real
    if not state.selected_variant_id:
        link = ""
    else:
        client = ShopifyClient(
            store_domain=tenant.store_domain,
            access_token=tenant.shopify_access_token,
            api_version=tenant.shopify_api_version,
        )
        link = client.build_checkout_link(
            variant_id=state.selected_variant_id,
            quantity=state.quantity,
            strategy=strategy,
        )

    state.last_action = "generate_link"
    state.last_strategy = strategy
    state.last_action_success = bool(link)
    
    if link:
        state.metadata["checkout_link"] = link
    else:
        state.metadata.pop("checkout_link", None)
    
    state.next_step = "respond"
    return state
