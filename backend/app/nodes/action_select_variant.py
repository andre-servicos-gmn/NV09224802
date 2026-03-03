# Created: action node to select a variant from available options.
"""
Action node que seleciona uma variante (cor/tamanho) a partir de lista.

Valida estoque antes de confirmar selecao.
"""

import re
from difflib import get_close_matches
import requests

from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def _match_variant(user_input: str, available_variants: list) -> dict | None:
    """
    Match user input to available variants.
    Handles: "M", "medio", "o grande", "primeiro", "1", etc.
    """
    if not user_input:
        return None
        
    user_input = user_input.lower().strip()
    
    # 1. Tentar match exato
    for variant in available_variants:
        if user_input == str(variant.get("title", "")).lower():
            return variant
    
    # 2. Tentar match por número/posição
    # Extrair primeiro número encontrado
    number_match = re.search(r"\b([1-9][0-9]?)\b", user_input)
    if number_match:
        idx = int(number_match.group(1)) - 1  # "1" = primeiro
        if 0 <= idx < len(available_variants):
            return available_variants[idx]
    
    # 3. Tentar match por posição em texto (ordinal)
    position_map = {
        "primeiro": 0, "primeira": 0, "1º": 0, "1o": 0,
        "segundo": 1, "segunda": 1, "2º": 1, "2o": 1,
        "terceiro": 2, "terceira": 2, "3º": 2, "3o": 2,
        "quarto": 3, "quarta": 3, "4º": 3, "4o": 3,
    }
    for key, idx in position_map.items():
        if key in user_input and idx < len(available_variants):
            return available_variants[idx]
    
    # 4. Fuzzy match nos títulos
    variant_titles = [str(v.get("title", "")).lower() for v in available_variants]
    
    # Remove palavras comuns para melhorar match ("quero o medio" -> "medio")
    clean_input = re.sub(r'^(quero|gostaria|vou|de|o|a|no|na)\s+', '', user_input).strip()
    
    matches = get_close_matches(clean_input, variant_titles, n=1, cutoff=0.6)
    if matches:
        idx = variant_titles.index(matches[0])
        return available_variants[idx]
    
    # 5. Match parcial (contém)
    for variant in available_variants:
        title = str(variant.get("title", "")).lower()
        if clean_input in title or title in clean_input:
            return variant
            
    return None


def _match_variant_llm(user_input: str, state: ConversationState) -> dict | None:
    """
    Use LLM to understand which variant the user wants based on context.
    Essential for confirmations like "pode ser", "sim" referring to a specific suggestion.
    """
    from app.core.llm import generate_response
    
    if not state.available_variants:
        return None

    variants_text = "\n".join([
        f"- ID: {v.get('id')} | Title: {v.get('title')} | Available: {v.get('available', True)}"
        for v in state.available_variants
    ])
    
    # Simple history context
    history_lines = []
    for m in state.conversation_history[-4:]:
        role = "User" if m.get("role") == "user" else "Bot"
        msg = m.get("message", "")[:200]
        history_lines.append(f"{role}: {msg}")
    history = "\n".join(history_lines)

    system_prompt = "Você é um assistente que identifica qual variante de produto o usuário escolheu baseada no histórico da conversa."
    
    user_prompt = f"""
VARIANTES DISPONÍVEIS:
{variants_text}

HISTÓRICO RECENTE:
{history}

INPUT DO USUÁRIO: "{user_input}"

INSTRUÇÕES:
1. Se o usuário confirmou uma sugestão do bot (ex: "pode ser", "sim", "quero esse"), veja qual variante o bot sugeriu por último.
2. Se o usuário foi específico (ex: "quero o grande"), faça o match pelo título.
3. Retorne APENAS o ID da variante escolhida.
4. Se não entender ou não houver escolha clara, retorne "NONE".
""".strip()

    try:
        response = generate_response(system_prompt, user_prompt)
        response = response.strip().replace('"', '').replace("'", "")
        
        if response and response.lower() != "none":
            # Find variant by ID
            for v in state.available_variants:
                if str(v.get("id")) == response:
                    return v
    except Exception as e:
        print(f"DEBUG: LLM variant match failed: {e}")
        return None
        
    return None


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
    
    # Rename action for consistency
    state.last_action = "action_select_variant"

    try:
        if not state.available_variants:
            state.last_action_success = False
            state.soft_context["select_variant_error"] = "no_available_variants"
            # Se não tem variantes mas tem produto, talvez seja produto simples
            if state.selected_products and len(state.selected_products) == 1:
                 # Auto-recover: treat likely single product as selected
                 state.soft_context["selected_variant_id"] = "default" 
                 state.last_action_success = True
                 state.next_step = "respond"
                 return state
                 
            state.bump_frustration()
            state.next_step = "respond"
            return state

        message = state.last_user_message or ""
        
        # Tenta encontrar a variante
        variant = _match_variant(message, state.available_variants)
        
        if not variant:
            # Tentar lógica de confirmação ("sim", "pode ser") se só houver 1 opção disponível
            confirmation_pattern = r'^(sim|quero|pode|ok|ta|tá|beleza|bora|yes|manda|claro|aceito|isso)\W*$'
            if re.match(confirmation_pattern, message.lower().strip()):
                # Filtrar variantes com estoque > 0
                in_stock = [v for v in state.available_variants if int(v.get("inventory_quantity", 0)) > 0]
                
                # Se só tem 1 em estoque, assume que é essa
                if len(in_stock) == 1:
                    variant = in_stock[0]
                # Se não tem nenhuma em estoque mas só tem 1 cadastrada, seleciona ela (vai dar erro de estoque depois, o que é correto)
                elif len(state.available_variants) == 1:
                    variant = state.available_variants[0]

        if not variant:
            # Fallback: Use LLM for contextual understanding (e.g. "pode ser" after an offer)
            variant = _match_variant_llm(message, state)

        if not variant:
            state.last_action_success = False
            state.soft_context["select_variant_error"] = "variant_not_found"
            state.bump_frustration()
            state.next_step = "respond"
            return state

        # Check availability
        is_available = variant.get("available", True)
        if isinstance(is_available, str):
            is_available = is_available.lower() == "true"
            
        inventory = variant.get("inventory_quantity")
        if inventory is not None and int(inventory) <= 0:
            is_available = False
            
        if not is_available:
            state.last_action_success = False
            state.soft_context["out_of_stock"] = True
            state.soft_context["select_variant_error"] = "out_of_stock"
            state.soft_context["unavailable_variant_title"] = variant.get("title")
            state.bump_frustration()
            state.next_step = "respond"
            return state

        # Success!
        state.soft_context["selected_variant_id"] = str(variant.get("id"))
        state.soft_context["selected_variant_title"] = variant.get("title", "")
        state.soft_context["selected_variant_price"] = variant.get("price", "")
        
        if "out_of_stock" in state.soft_context:
            del state.soft_context["out_of_stock"]
        if "select_variant_error" in state.soft_context:
            del state.soft_context["select_variant_error"]

        state.last_action_success = True

    except Exception as exc:
        state.last_action_success = False
        state.system_error = str(exc)
        state.soft_context["select_variant_error"] = str(exc)
        state.bump_frustration()

    state.next_step = "respond"
    return state
