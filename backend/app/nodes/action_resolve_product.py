"""
Action node que resolve produto a partir de URL Shopify.

Este node busca informações do produto (ID, variante, título, preço)
usando a API real da Shopify.
"""

from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.tools.shopify_client import ShopifyClient
import requests


def action_resolve_product(
    state: ConversationState,
    tenant: TenantConfig
) -> ConversationState:
    """
    Resolve produto a partir da URL na mensagem do usuário.
    
    Usa o cliente Shopify real com tokens do tenant (vindos do Supabase).
    
    Args:
        state: Estado atual da conversa
        tenant: Configuração do tenant (com credenciais Shopify)
        
    Returns:
        ConversationState atualizado com informações do produto
    """
    # Cria cliente com credenciais do tenant (vindas do Supabase)
    client = ShopifyClient(
        store_domain=tenant.store_domain,
        access_token=tenant.shopify_access_token,
        api_version=tenant.shopify_api_version,
    )
    
    # Usar product_url da entidade extraída pelo router, não a mensagem inteira
    product_url = state.soft_context.get("product_url") or ""
    
    # Fallback: tentar extrair URL da mensagem se não estiver no metadata

    if not product_url:
        import re
        url_match = re.search(r"https?://\S+", state.last_user_message or "")
        if url_match and "products/" in url_match.group(0):
            product_url = url_match.group(0)
    
    if not product_url:
        state.last_action_success = False
        state.soft_context["product_error"] = "missing_product_url"
        state.next_step = "respond"
        return state
    
    try:
        product = client.get_product_by_url(product_url)
        state.soft_context["focused_product_id"] = product["product_id"]
        state.soft_context["selected_variant_id"] = product["variant_id"]
        state.soft_context["product_title"] = product["title"]
        state.soft_context["product_price"] = product["price"]
        state.soft_context["product_description"] = product.get("description") or ""
        state.soft_context["product_tags"] = product.get("tags") or ""
        state.soft_context["product_type"] = product.get("product_type") or ""
        state.soft_context["product_vendor"] = product.get("vendor") or ""
        state.last_action_success = True
    except requests.Timeout:
        state.last_action_success = False
        state.system_error = "timeout"
        state.soft_context["product_error"] = "timeout"
        state.bump_frustration()
    except requests.HTTPError as e:
        state.last_action_success = False
        if e.response.status_code == 404:
            state.soft_context["product_error"] = "not_found"
        elif e.response.status_code == 429:
            state.soft_context["product_error"] = "rate_limit"
        else:
            state.soft_context["product_error"] = str(e)
            state.system_error = str(e)
        state.bump_frustration()
    except Exception as e:
        state.last_action_success = False
        state.system_error = str(e)
        state.soft_context["product_error"] = str(e)
        state.soft_context["focused_product_id"] = None
        state.soft_context["selected_variant_id"] = None
        state.bump_frustration()
    
    state.last_action = "resolve_product"
    state.next_step = "respond"
    return state
