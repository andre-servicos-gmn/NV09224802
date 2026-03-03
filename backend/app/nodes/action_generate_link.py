# Modified: add inventory check and robust error handling before link generation.
"""
Action node que gera link de checkout Shopify.

Implementa logica de estrategias: se uma estrategia falhar,
escala para a proxima (permalink -> add_to_cart -> checkout_direct -> human_handoff).
"""
import logging
import requests

from app.core.constants import INTENT_CART_RETRY, INTENT_CHECKOUT_ERROR
from app.core.state import ConversationState
from app.core.strategies import next_strategy
from app.core.tenancy import TenantConfig
from app.tools.shopify_client import ShopifyClient

logger = logging.getLogger(__name__)


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
        ConversationState atualizado com link de checkout
    """
    logger.info("=" * 50)
    logger.info("[GENERATE_LINK] ▶️ ENTRY")
    logger.info(f"[GENERATE_LINK] Intent: {state.intent}")
    logger.info(f"[GENERATE_LINK] Last Action: {state.last_action}")
    logger.info(f"[GENERATE_LINK] Selected Products: {len(state.selected_products or [])}")
    logger.info(f"[GENERATE_LINK] Variant ID: {state.soft_context.get('selected_variant_id')}")
    logger.info(f"[GENERATE_LINK] Current checkout_link: {state.checkout_link}")
    
    try:
        # Escala estrategia se houve erro/retry
        if state.last_action_success is False and state.intent in {INTENT_CART_RETRY, INTENT_CHECKOUT_ERROR}:
            state.last_strategy = next_strategy(state.last_strategy)

        strategy = state.last_strategy or tenant.default_link_strategy or "permalink"
        
        # Validate strategy is a valid CHECKOUT strategy
        # last_strategy can be "rag_answer" from store_qa domain, which is not a checkout strategy
        VALID_CHECKOUT_STRATEGIES = {"permalink", "add_to_cart", "checkout_direct", "human_handoff"}
        if strategy not in VALID_CHECKOUT_STRATEGIES:
            logger.warning(f"[GENERATE_LINK] Invalid checkout strategy '{strategy}', falling back to permalink")
            strategy = tenant.default_link_strategy or "permalink"
            if strategy not in VALID_CHECKOUT_STRATEGIES:
                strategy = "permalink"
        
        logger.info(f"[GENERATE_LINK] Strategy: {strategy}")

        # Se chegou em human_handoff, sinaliza escalonamento humano
        if strategy == "human_handoff":
            logger.warning("[GENERATE_LINK] Strategy exhausted → human_handoff")
            state.last_action = "generate_link"
            state.last_strategy = strategy
            state.last_action_success = False
            state.needs_handoff = True
            state.handoff_reason = "checkout_strategy_exhausted"
            state.checkout_link = None
            state.next_step = "respond"
            return state

        selected_variant_id = state.soft_context.get("selected_variant_id")
        if not selected_variant_id:
            logger.error("[GENERATE_LINK] ❌ NO VARIANT_ID! Cannot generate link.")
            link = ""
        else:
            client = ShopifyClient(
                store_domain=tenant.store_domain,
                access_token=tenant.shopify_access_token,
                api_version=tenant.shopify_api_version,
            )
            inventory = client.check_inventory(selected_variant_id)
            if not inventory.get("available", False):
                state.last_action = "generate_link"
                state.last_strategy = strategy
                state.last_action_success = False
                state.soft_context["out_of_stock"] = True
                state.soft_context["out_of_stock_message"] = (
                     "Ops! Esse produto acabou de esgotar enquanto você escolhia. "
                     "Quer que eu busque opções similares?"
                )
                state.checkout_link = None
                state.bump_frustration()
                state.next_step = "respond"
                return state

            if "out_of_stock" in state.soft_context:
                del state.soft_context["out_of_stock"]
            
            quantity = int(state.soft_context.get("quantity", 1))
            link = client.build_checkout_link(
                variant_id=selected_variant_id,
                quantity=quantity,
                strategy=strategy,
            )
            logger.info(f"[GENERATE_LINK] ✅ Link generated: {link[:50] if link else 'NONE'}...")

        state.last_action = "generate_link"
        state.last_strategy = strategy
        state.last_action_success = bool(link)
        logger.info(f"[GENERATE_LINK] Success: {state.last_action_success}")

        if link:
            state.checkout_link = link
            logger.info(f"[GENERATE_LINK] 🔗 checkout_link SET: {link}")
            # Clear previous errors
            if "select_variant_error" in state.soft_context:
                del state.soft_context["select_variant_error"]
            if "checkout_error" in state.soft_context:
                del state.soft_context["checkout_error"]
        else:
            state.checkout_link = None

        state.next_step = "respond"
        return state

    except requests.Timeout:
        state.last_action = "generate_link"
        state.last_action_success = False
        state.system_error = "timeout"
        state.soft_context["checkout_error"] = "timeout"
        state.checkout_link = None
        state.bump_frustration()
        state.next_step = "respond"
        return state

    except requests.HTTPError as exc:
        state.last_action = "generate_link"
        state.last_action_success = False
        if exc.response.status_code == 429:
            state.system_error = "rate_limit"
            state.soft_context["checkout_error"] = "rate_limit"
        else:
            state.system_error = str(exc)
            state.soft_context["checkout_error"] = str(exc)
        state.checkout_link = None
        state.bump_frustration()
        state.next_step = "respond"
        return state

    except Exception as exc:
        state.last_action = "generate_link"
        state.last_action_success = False
        state.system_error = str(exc)
        state.soft_context["checkout_error"] = str(exc)
        state.checkout_link = None
        state.bump_frustration()
        state.next_step = "respond"
        return state
