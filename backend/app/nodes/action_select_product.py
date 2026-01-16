# Created: action node to select a product from search results.
"""
Action node que seleciona um produto de uma lista de resultados.

Extrai o numero da mensagem do usuario e carrega variantes do produto.
"""


import re
import requests

from app.core.tenancy import TenantConfig
from app.tools.shopify_client import ShopifyClient


def _extract_selection(message: str) -> int | None:
    match = re.search(r"\b([1-9][0-9]?)\b", message)
    if not match:
        return None
    return int(match.group(1))


def action_select_product(
    state: ConversationState,
    tenant: TenantConfig
) -> ConversationState:
    """
    Seleciona um produto da lista e busca variantes na Shopify.

    Args:
        state: Estado atual da conversa
        tenant: Configuracao do tenant (com credenciais Shopify)

    Returns:
        ConversationState atualizado com selected_product_id e available_variants
    """
    client = ShopifyClient(
        store_domain=tenant.store_domain,
        access_token=tenant.shopify_access_token,
        api_version=tenant.shopify_api_version,
    )

    try:
        if not state.selected_products:
            state.last_action_success = False
            state.metadata["select_product_error"] = "no_selected_products"
            state.bump_frustration()
            state.next_step = "respond"
            state.last_action = "select_product"
            return state

        message = state.last_user_message or ""
        selection = _extract_selection(message)
        if selection is None:
            state.last_action_success = False
            state.metadata["select_product_error"] = "no_selection"
            state.bump_frustration()
            state.next_step = "respond"
            state.last_action = "select_product"
            return state

        index = selection - 1
        if index < 0 or index >= len(state.selected_products):
            state.last_action_success = False
            state.metadata["select_product_error"] = "selection_out_of_range"
            state.bump_frustration()
            state.next_step = "respond"
            state.last_action = "select_product"
            return state

        product = state.selected_products[index]
        product_id = str(product.get("product_id"))

        variants = client.get_product_variants(product_id)
        state.selected_product_id = product_id
        state.available_variants = variants
        state.metadata["product_title"] = product.get("title", "")
        state.metadata["product_price"] = product.get("price", "")
        state.metadata.pop("out_of_stock", None)

        if len(variants) <= 1:
            if variants:
                variant = variants[0]
                state.selected_variant_id = variant.get("variant_id")
                state.metadata["selected_variant_title"] = variant.get("title", "")
                state.metadata["selected_variant_price"] = variant.get("price", "")
            state.available_variants = []
        else:
            state.selected_variant_id = None

        state.last_action_success = True

    except requests.Timeout:
        state.last_action_success = False
        state.metadata["select_product_error"] = "timeout"
        state.available_variants = []
        state.selected_product_id = None
        state.selected_variant_id = None
        state.bump_frustration()

    except requests.HTTPError as exc:
        state.last_action_success = False
        if exc.response.status_code == 429:
            state.metadata["select_product_error"] = "rate_limit"
        else:
            state.metadata["select_product_error"] = str(exc)
        state.available_variants = []
        state.selected_product_id = None
        state.selected_variant_id = None
        state.bump_frustration()

    except Exception as exc:
        state.last_action_success = False
        state.metadata["select_product_error"] = str(exc)
        state.available_variants = []
        state.selected_product_id = None
        state.selected_variant_id = None
        state.bump_frustration()

    state.last_action = "select_product"
    state.next_step = "respond"
    return state
