# Created: action node to select a product from search results.
"""
Action node que seleciona um produto de uma lista de resultados.

Extrai o numero da mensagem do usuario e carrega variantes do produto.
"""


import re
import logging
from app.core.tenancy import TenantConfig
from app.core.state import ConversationState
from app.tools.shopify_client import ShopifyClient

logger = logging.getLogger(__name__)

def _extract_selection(message: str) -> int | None:
    # Match any stand-alone number in the message
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
    """
    client = ShopifyClient(
        store_domain=tenant.store_domain,
        access_token=tenant.shopify_access_token,
        api_version=tenant.shopify_api_version,
    )

    try:
        if not state.selected_products:
            logger.error("[SELECT_PRODUCT] No selected_products in state")
            state.last_action_success = False
            state.soft_context["select_product_error"] = "no_selected_products"
            state.bump_frustration()
            state.next_step = "respond"
            state.last_action = "select_product"
            return state

        message = state.last_user_message or ""
        selection = _extract_selection(message)
        logger.info(f"[SELECT_PRODUCT] Extracted selection '{selection}' from message '{message}'")
        
        if selection is None:
            logger.error("[SELECT_PRODUCT] Could not extract numeric selection")
            state.last_action_success = False
            state.soft_context["select_product_error"] = "no_selection"
            state.bump_frustration()
            state.next_step = "respond"
            state.last_action = "select_product"
            return state

        index = selection - 1
        if index < 0 or index >= len(state.selected_products):
            logger.error(f"[SELECT_PRODUCT] Index {index} (selection {selection}) out of range (0-{len(state.selected_products)-1})")
            state.last_action_success = False
            state.soft_context["select_product_error"] = "selection_out_of_range"
            state.bump_frustration()
            state.next_step = "respond"
            state.last_action = "select_product"
            return state

        product = state.selected_products[index]
        product_id = str(product.get("product_id") or product.get("id"))
        
        logger.info(f"[SELECT_PRODUCT] Selected product index {index}, ID: {product_id}, Title: {product.get('title')}")

        logger.info(f"[SELECT_PRODUCT] Fetching variants for Shopify product {product_id}")
        variants = client.get_product_variants(product_id)
        logger.info(f"[SELECT_PRODUCT] Fetched {len(variants)} variants")
        
        state.soft_context["focused_product_id"] = product_id
        state.available_variants = variants
        state.soft_context["product_title"] = product.get("title", "")
        state.soft_context["product_price"] = product.get("price", "")
        if "out_of_stock" in state.soft_context:
            del state.soft_context["out_of_stock"]

        if len(variants) <= 1:
            if variants:
                variant = variants[0]
                state.soft_context["selected_variant_id"] = variant.get("variant_id")
                state.soft_context["selected_variant_title"] = variant.get("title", "")
                state.soft_context["selected_variant_price"] = variant.get("price", "")
            state.available_variants = []
            logger.info("[SELECT_PRODUCT] Single variant (or none). Auto-selected variant.")
        else:
            state.soft_context["selected_variant_id"] = None
            logger.info("[SELECT_PRODUCT] Multiple variants. Will need variant selection.")

        state.last_action_success = True

    except requests.Timeout:
        logger.error("[SELECT_PRODUCT] Shopify API Timeout")
        state.last_action_success = False
        state.system_error = "timeout"
        state.soft_context["select_product_error"] = "timeout"
        state.available_variants = []
        state.soft_context["focused_product_id"] = None
        state.soft_context["selected_variant_id"] = None
        state.bump_frustration()

    except requests.HTTPError as exc:
        logger.error(f"[SELECT_PRODUCT] Shopify HTTPError: {exc}")
        state.last_action_success = False
        if exc.response is not None and exc.response.status_code == 429:
            state.system_error = "rate_limit"
            state.soft_context["select_product_error"] = "rate_limit"
        else:
            state.system_error = str(exc)
            state.soft_context["select_product_error"] = str(exc)
        state.available_variants = []
        state.soft_context["focused_product_id"] = None
        state.soft_context["selected_variant_id"] = None
        state.bump_frustration()

    except Exception as exc:
        logger.error(f"[SELECT_PRODUCT] Unknown Error: {exc}", exc_info=True)
        state.last_action_success = False
        state.system_error = str(exc)
        state.soft_context["select_product_error"] = str(exc)
        state.available_variants = []
        state.soft_context["focused_product_id"] = None
        state.soft_context["selected_variant_id"] = None
        state.bump_frustration()

    state.last_action = "select_product"
    state.next_step = "respond"
    return state
