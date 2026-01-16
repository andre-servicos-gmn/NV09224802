# Modified: add inventory check and robust error handling before link generation.
"""
Action node que gera link de checkout Shopify.

Implementa logica de estrategias: se uma estrategia falhar,
escala para a proxima (permalink -> add_to_cart -> checkout_direct -> human_handoff).
"""

from app.core.constants import INTENT_CART_RETRY, INTENT_CHECKOUT_ERROR
from app.core.state import ConversationState
from app.core.strategies import next_strategy
from app.core.tenancy import TenantConfig
from app.tools.shopify_client import ShopifyClient
import requests


def action_generate_link(
    state: ConversationState,
    tenant: TenantConfig
) -> ConversationState:
    """
    Gera link de checkout usando a estrategia apropriada.

    Se a ultima acao falhou e o intent indica retry/erro de checkout,
    escala para a proxima estrategia automaticamente.

    Args:
        state: Estado atual da conversa
        tenant: Configuracao do tenant (com credenciais Shopify)

    Returns:
        ConversationState atualizado com link de checkout em metadata
    """
    try:
        # Escala estrategia se houve erro/retry
        if state.last_action_success is False and state.intent in {INTENT_CART_RETRY, INTENT_CHECKOUT_ERROR}:
            state.last_strategy = next_strategy(state.last_strategy)

        strategy = state.last_strategy or tenant.default_link_strategy or "permalink"

        # Se chegou em human_handoff, sinaliza escalonamento humano
        if strategy == "human_handoff":
            state.last_action = "generate_link"
            state.last_strategy = strategy
            state.last_action_success = False
            state.needs_handoff = True
            state.handoff_reason = "checkout_strategy_exhausted"
            state.metadata.pop("checkout_link", None)
            state.next_step = "respond"
            return state

        if not state.selected_variant_id:
            link = ""
        else:
            client = ShopifyClient(
                store_domain=tenant.store_domain,
                access_token=tenant.shopify_access_token,
                api_version=tenant.shopify_api_version,
            )
            inventory = client.check_inventory(state.selected_variant_id)
            if not inventory.get("available", False):
                state.last_action = "generate_link"
                state.last_strategy = strategy
                state.last_action_success = False
                state.metadata["out_of_stock"] = True
                state.metadata["out_of_stock_message"] = (
                     "Ops! Esse produto acabou de esgotar enquanto você escolhia. "
                     "Quer que eu busque opções similares?"
                )
                state.metadata.pop("checkout_link", None)
                state.bump_frustration()
                state.next_step = "respond"
                return state

            state.metadata.pop("out_of_stock", None)
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

    except requests.Timeout:
        state.last_action = "generate_link"
        state.last_action_success = False
        state.metadata["checkout_error"] = "timeout"
        state.metadata.pop("checkout_link", None)
        state.bump_frustration()
        state.next_step = "respond"
        return state

    except requests.HTTPError as exc:
        state.last_action = "generate_link"
        state.last_action_success = False
        if exc.response.status_code == 429:
            state.metadata["checkout_error"] = "rate_limit"
        else:
            state.metadata["checkout_error"] = str(exc)
        state.metadata.pop("checkout_link", None)
        state.bump_frustration()
        state.next_step = "respond"
        return state

    except Exception as exc:
        state.last_action = "generate_link"
        state.last_action_success = False
        state.metadata["checkout_error"] = str(exc)
        state.metadata.pop("checkout_link", None)
        state.bump_frustration()
        state.next_step = "respond"
        return state
