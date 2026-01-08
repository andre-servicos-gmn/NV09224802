# Created: action node to select a variant from available options.
"""
Action node que seleciona uma variante (cor/tamanho) a partir de lista.

Valida estoque antes de confirmar selecao.
"""

import re

import re
import requests

from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def _extract_selection(message: str) -> int | None:
    match = re.search(r"\b([1-9][0-9]?)\b", message)
    if not match:
        return None
    return int(match.group(1))


def action_select_variant(
    state: ConversationState,
    tenant: TenantConfig
) -> ConversationState:
    """
    Seleciona uma variante da lista de opcoes disponiveis.

    Args:
        state: Estado atual da conversa
        tenant: Configuracao do tenant (nao usado)

    Returns:
        ConversationState atualizado com selected_variant_id
    """
    _ = tenant

    try:
        if not state.available_variants:
            state.last_action_success = False
            state.metadata["select_variant_error"] = "no_available_variants"
            state.bump_frustration()
            state.next_step = "respond"
            state.last_action = "select_variant"
            return state

        message = state.last_user_message or ""
        selection = _extract_selection(message)
        if selection is None:
            state.last_action_success = False
            state.metadata["select_variant_error"] = "no_selection"
            state.bump_frustration()
            state.next_step = "respond"
            state.last_action = "select_variant"
            return state

        index = selection - 1
        if index < 0 or index >= len(state.available_variants):
            state.last_action_success = False
            state.metadata["select_variant_error"] = "selection_out_of_range"
            state.bump_frustration()
            state.next_step = "respond"
            state.last_action = "select_variant"
            return state

        variant = state.available_variants[index]
        inventory_quantity = int(variant.get("inventory_quantity") or 0)
        if inventory_quantity <= 0 or not variant.get("available", True):
            state.last_action_success = False
            state.metadata["out_of_stock"] = True
            state.metadata["select_variant_error"] = "out_of_stock"
            state.bump_frustration()
            state.next_step = "respond"
            state.last_action = "select_variant"
            return state

        state.selected_variant_id = variant.get("variant_id")
        state.metadata["selected_variant_title"] = variant.get("title", "")
        state.metadata["selected_variant_price"] = variant.get("price", "")
        state.metadata.pop("out_of_stock", None)
        state.last_action_success = True

    except requests.Timeout:
        state.last_action_success = False
        state.metadata["select_variant_error"] = "timeout"
        state.bump_frustration()

    except requests.HTTPError as exc:
        state.last_action_success = False
        if exc.response.status_code == 429:
            state.metadata["select_variant_error"] = "rate_limit"
        else:
            state.metadata["select_variant_error"] = str(exc)
        state.bump_frustration()

    except Exception as exc:
        state.last_action_success = False
        state.metadata["select_variant_error"] = str(exc)
        state.bump_frustration()

    state.last_action = "select_variant"
    state.next_step = "respond"
    return state
