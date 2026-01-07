"""
Action node que resolve produto a partir de URL Shopify.

Este node busca informações do produto (ID, variante, título, preço)
usando a API real da Shopify.
"""

from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.tools.shopify_client import ShopifyClient


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
    
    try:
        product = client.get_product_by_url(state.last_user_message or "")
        state.selected_product_id = product["product_id"]
        state.selected_variant_id = product["variant_id"]
        state.metadata["product_title"] = product["title"]
        state.metadata["product_price"] = product["price"]
        state.last_action_success = True
    except Exception as e:
        state.last_action_success = False
        state.metadata["product_error"] = str(e)
        state.selected_product_id = None
        state.selected_variant_id = None
        state.bump_frustration()
    
    state.last_action = "resolve_product"
    state.next_step = "respond"
    return state
