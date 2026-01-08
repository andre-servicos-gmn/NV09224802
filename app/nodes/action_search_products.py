# Modified: clear cross-domain metadata and store search metadata for sales.
"""
Action node que busca produtos por texto na Shopify.

Atualiza o estado com ate 5 resultados para listagem no respond node.
"""

import requests

from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.tools.shopify_client import ShopifyClient


def action_search_products(
    state: ConversationState,
    tenant: TenantConfig
) -> ConversationState:
    """
    Busca produtos por texto usando a Shopify Admin API.

    Args:
        state: Estado atual da conversa
        tenant: Configuracao do tenant (com credenciais Shopify)

    Returns:
        ConversationState atualizado com selected_products
    """
    client = ShopifyClient(
        store_domain=tenant.store_domain,
        access_token=tenant.shopify_access_token,
        api_version=tenant.shopify_api_version,
    )

    try:
        # Limpar contexto de outros dominios
        state.metadata.pop("tracking_url", None)
        state.metadata.pop("order_id", None)
        state.metadata.pop("ticket_id", None)
        state.metadata.pop("order_status", None)

        query = (state.search_query or state.last_user_message or "").strip()
        state.search_query = query or None
        state.metadata["search_query"] = query or None
        state.selected_products = []
        state.available_variants = []
        state.selected_product_id = None
        state.selected_variant_id = None
        state.metadata["search_results_count"] = 0

        if not query:
            state.last_action_success = False
            state.metadata["search_error"] = "missing_search_query"
            state.bump_frustration()
        else:
            results = client.search_products(query=query, limit=5)
            state.selected_products = results
            state.metadata["search_results_count"] = len(results)
            if not results:
                state.last_action_success = False
                state.metadata["search_error"] = "no_results"
                state.bump_frustration()
            else:
                state.last_action_success = True
                state.metadata.pop("search_error", None)

    except requests.Timeout:
        state.last_action_success = False
        state.metadata["search_error"] = "timeout"
        state.selected_products = []
        state.bump_frustration()

    except requests.HTTPError as exc:
        state.last_action_success = False
        if exc.response.status_code == 429:
            state.metadata["search_error"] = "rate_limit"
        else:
            state.metadata["search_error"] = str(exc)
        state.selected_products = []
        state.bump_frustration()

    except Exception as exc:
        state.last_action_success = False
        state.metadata["search_error"] = str(exc)
        state.selected_products = []
        state.bump_frustration()

    state.last_action = "search_products"
    state.next_step = "respond"
    return state
