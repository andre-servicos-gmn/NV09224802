# Modified: Uses RAG semantic search with REST API fallback.
"""
Action node que busca produtos por texto usando RAG (busca semântica).

Usa embeddings e pgvector para encontrar produtos semanticamente similares.
Fallback para REST API se RAG falhar ou não houver produtos indexados.
"""

import os
from typing import Optional

from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.tools.shopify_client import ShopifyClient


def _search_with_rag(
    tenant: TenantConfig,
    query: str,
    limit: int = 10,
    disliked_terms: list[str] = None,
) -> Optional[list[dict]]:
    """Search products using RAG semantic search.
    
    Args:
        tenant: Tenant configuration with UUID.
        query: Search query.
        limit: Maximum results (increased to 10 for diversity).
        disliked_terms: List of product terms to exclude from results.
        
    Returns:
        List of products or None if RAG is unavailable/empty.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"[RAG] Starting RAG search for query='{query}' tenant_uuid={tenant.uuid}")
    
    if not tenant.uuid:
        logger.warning("[RAG] No tenant UUID available, skipping RAG search")
        return None
    
    try:
        from app.rag_engine.pipeline import RAGPipeline
        
        logger.info(f"[RAG] Creating RAGPipeline with tenant_id={tenant.uuid}")
        pipeline = RAGPipeline(tenant_id=tenant.uuid)
        
        logger.info(f"[RAG] Calling get_products_for_state('{query}', limit={limit})")
        results = pipeline.get_products_for_state(query, limit=limit)
        
        logger.info(f"[RAG] get_products_for_state returned {len(results) if results else 0} results")
        
        # Filter disliked terms
        if results and disliked_terms:
            filtered_results = []
            for p in results:
                # Combine title, description and tags for checking safely
                p_title = p.get("title") or ""
                p_desc = p.get("description") or ""
                p_tags = p.get("tags") or []
                
                text_to_check = (
                    str(p_title) + " " + 
                    str(p_desc) + " " + 
                    " ".join([str(t) for t in p_tags])
                ).lower()
                
                is_disliked = False
                for term in disliked_terms:
                    if term.lower() in text_to_check:
                        is_disliked = True
                        break
                
                if not is_disliked:
                    filtered_results.append(p)
                else:
                    logger.info(f"[RAG] Excluded product due to disliked terms: {p.get('title')}")
            
            results = filtered_results
        
        if results:
            for i, p in enumerate(results[:3]):
                logger.info(f"[RAG]   Result {i+1}: {p.get('title', 'N/A')} (in_stock={p.get('in_stock')})")
        
        # Return None if RAG returned no results (may need fallback)
        
        return results
        
    except Exception as e:
        logger.error(f"[RAG] Search failed with exception: {e}", exc_info=True)
        return None


def _search_with_rest_api(
    tenant: TenantConfig,
    query: str,
    limit: int = 5,
) -> list[dict]:
    """Search products using Shopify REST API (fallback).
    
    Args:
        tenant: Tenant configuration.
        query: Search query.
        limit: Maximum results.
        
    Returns:
        List of products.
    """
    client = ShopifyClient(
        store_domain=tenant.store_domain,
        access_token=tenant.shopify_access_token,
        api_version=tenant.shopify_api_version,
    )
    return client.search_products(query=query, limit=limit)


def action_search_products(
    state: ConversationState,
    tenant: TenantConfig
) -> ConversationState:
    """
    Busca produtos por texto usando RAG semantic search.
    
    Prioriza busca semântica via embeddings (mais precisa).
    Fallback para REST API se RAG não disponível.

    Args:
        state: Estado atual da conversa
        tenant: Configuracao do tenant (com credenciais Shopify)

    Returns:
        ConversationState atualizado com selected_products
    """
    import requests
    
    try:
        # Limpar contexto de outros dominios
        state.tracking_url = None
        state.order_id = None

        query = (state.search_query or state.last_user_message or "").strip()
        state.search_query = query or None
        state.soft_context["search_query"] = query or None
        state.selected_products = []
        state.available_variants = []
        state.soft_context["focused_product_id"] = None
        state.soft_context["selected_variant_id"] = None
        state.soft_context["search_results_count"] = 0


        if not query:
            state.last_action_success = False
            state.soft_context["search_error"] = "missing_search_query"
            state.bump_frustration()
        else:
            import logging
            logger = logging.getLogger(__name__)
            
            # Try RAG first (semantic search)
            disliked_terms = state.soft_context.get("disliked_terms", [])
            results = _search_with_rag(tenant, query, limit=10, disliked_terms=disliked_terms)
            search_method = "rag"
            
            logger.info(f"[SEARCH] RAG returned {len(results) if results else 0} results for '{query}'")
            
            # Fallback to REST API if RAG didn't return results OR returned empty
            if not results:
                logger.info(f"[SEARCH] Falling back to REST API for '{query}'")
                results = _search_with_rest_api(tenant, query, limit=5)
                search_method = "rest_api"
                logger.info(f"[SEARCH] REST API returned {len(results)} results")
                
                # Filter out-of-stock from REST API results too
                if results:
                    in_stock_results = [p for p in results if p.get("in_stock", True)]
                    removed = len(results) - len(in_stock_results)
                    if removed > 0:
                        logger.info(f"[SEARCH] Filtered out {removed} out-of-stock products from REST API")
                    results = in_stock_results
            
            state.selected_products = results
            state.soft_context["search_results_count"] = len(results)
            state.soft_context["search_method"] = search_method
            
            # Check for variants in the top result
            if results:
                product = results[0]
                if product.get("has_variants") and product.get("variants"):
                    state.soft_context["focused_product_id"] = product.get("product_id")
                    
                    # Transform variants to simplified format for state
                    # Only include IN-STOCK variants
                    all_variants = [
                        {
                            "id": str(v.get("id")),
                            "title": v.get("title", ""),
                            "price": str(v.get("price", "")),
                            "available": int(v.get("inventory_quantity", 0)) > 0,
                            "inventory_quantity": int(v.get("inventory_quantity", 0))
                        }
                        for v in product.get("variants", [])
                    ]
                    state.available_variants = [v for v in all_variants if v["available"]]
                    logger.info(f"[SEARCH] Auto-selected focus on product {product.get('title')} with {len(state.available_variants)} variants")
            
            if os.getenv("DEBUG"):
                print(f"[Search] Method: {search_method}, Results: {len(results)}")
            
            if not results:
                state.last_action_success = False
                state.soft_context["search_error"] = "no_results"
                state.bump_frustration()
            else:
                state.last_action_success = True
                if "search_error" in state.soft_context:
                    del state.soft_context["search_error"]

    except requests.Timeout:
        state.last_action_success = False
        state.system_error = "timeout"
        state.soft_context["search_error"] = "timeout"
        state.selected_products = []
        state.bump_frustration()

    except requests.HTTPError as exc:
        state.last_action_success = False
        if exc.response.status_code == 429:
            state.system_error = "rate_limit"
            state.soft_context["search_error"] = "rate_limit"
        else:
            state.system_error = str(exc)
            state.soft_context["search_error"] = str(exc)
        state.selected_products = []
        state.bump_frustration()

    except Exception as exc:
        state.last_action_success = False
        state.system_error = str(exc)
        state.soft_context["search_error"] = str(exc)
        state.selected_products = []
        state.bump_frustration()

    state.last_action = "search_products"
    state.next_step = "respond"

    return state
