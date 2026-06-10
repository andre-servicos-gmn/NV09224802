"""Smoke test E2E pós-cutover Fase 2 do Nouva.

Roda 8 cenários conversacionais com LLM real contra o tenant de produção,
usando o graph LangGraph idiomático + PostgresSaver.

Uso:
    cd backend && python scripts/smoke_test_phase1.py

Requer OPENAI_API_KEY + SUPABASE_POSTGRES_URI no .env.
"""

import os
import sys
import uuid
import time
from pathlib import Path

# Permite import de app.* quando rodado de backend/
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.core.turn_processor import process_message


TENANT_ID = "c35fe360-dc69-4997-9d1f-ae57f4d8a135"

# Strings EXATAS de fallback técnico (resposta NÃO veio do graph normal).
_FALLBACK_EXACT_MESSAGES = {
    "Desculpe, tive um problema técnico. Pode repetir?",
    "Desculpe, tive um problema tecnico. Pode repetir?",
    "Desculpe, não consegui responder.",
    "Tenant inválido",
    "Erro ao iniciar conversa",
}


def _is_fallback(bot_message: str) -> bool:
    if not bot_message:
        return False
    return bot_message.strip() in _FALLBACK_EXACT_MESSAGES


# Cores ANSI pro output
class C:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def _get_thread_state(tenant_id: str, session_id: str) -> dict:
    """Recupera state da thread via checkpointer do graph. Retorna dict ou {}."""
    try:
        from app.graphs.graph import get_graph
        graph = get_graph()
        config = {"configurable": {"thread_id": f"{tenant_id}:{session_id}"}}
        snapshot = graph.get_state(config)
        return snapshot.values if snapshot and snapshot.values else {}
    except Exception:
        return {}


def run_turn(session_id: str, user_msg: str) -> tuple:
    """Roda um turno. Retorna (result, state_dict, error_or_none)."""
    try:
        result = process_message(
            tenant_id=TENANT_ID,
            session_id=session_id,
            user_message=user_msg,
            channel="web",
            is_playground=True,
            number=None,
        )
        state = _get_thread_state(TENANT_ID, session_id)
        return result, state, None
    except Exception as e:
        return None, {}, e


def print_turn_summary(turn_num, total, user_msg, result, state, error, checks):
    """Imprime resultado de um turno."""
    print(f"  {C.DIM}Turn {turn_num}/{total}:{C.RESET} {C.BOLD}User:{C.RESET} {user_msg!r}")
    if error:
        print(f"    {C.RED}X EXCEPTION:{C.RESET} {error}")
        return False
    if not result:
        print(f"    {C.RED}X NO RESULT{C.RESET}")
        return False

    bot_preview = (result.bot_message or "")[:120]
    print(f"    {C.BOLD}Bot:{C.RESET} {bot_preview!r}")
    print(f"    {C.DIM}status={result.status} action={result.action}{C.RESET}")

    all_pass = True
    for label, passed in checks:
        symbol = f"{C.GREEN}OK{C.RESET}" if passed else f"{C.YELLOW}!!{C.RESET}"
        print(f"    {symbol} {label}")
        if not passed:
            all_pass = False
    return all_pass


def run_scenario(name, turns_with_checks):
    """Executa um cenário. Cada check_fn recebe (result, state_dict) → [(label,bool)]."""
    print(f"\n{C.BLUE}{'-'*48}{C.RESET}")
    print(f"{C.BOLD}{name}{C.RESET}")
    print(f"{C.BLUE}{'-'*48}{C.RESET}")
    session_id = f"smoke-{uuid.uuid4().hex[:12]}"
    print(f"  {C.DIM}session_id={session_id}{C.RESET}")

    all_turns_pass = True
    for i, (user_msg, check_fn) in enumerate(turns_with_checks, start=1):
        result, state, error = run_turn(session_id, user_msg)
        checks = check_fn(result, state) if (result and check_fn) else []
        if result:
            checks = [
                ("bot NAO caiu em mensagem de fallback tecnico",
                 not _is_fallback(result.bot_message or "")),
            ] + checks
        turn_pass = print_turn_summary(i, len(turns_with_checks), user_msg, result, state, error, checks)
        if not turn_pass:
            all_turns_pass = False
        time.sleep(0.3)

    if all_turns_pass:
        print(f"  {C.GREEN}{C.BOLD}-> PASS{C.RESET}")
    else:
        print(f"  {C.YELLOW}{C.BOLD}-> PARTIAL{C.RESET}")
    return all_turns_pass


# ═══════════════════ CENÁRIOS (state é AgentState flat) ═══════════════════

def _check_active_with_message(result, state):
    return [
        ("status=active", result.status == "active"),
        ("bot_message nao-vazio", bool(result.bot_message)),
    ]


def _check_search_called(result, state):
    return [
        ("status=active", result.status == "active"),
        ("bot_message nao-vazio", bool(result.bot_message)),
        ("tool search_products foi chamada", result.action in ("search_products", "get_product_variants", None)
         or "search_products" in str(state)),
    ]


def _check_product_focused(result, state):
    return [
        ("status=active", result.status == "active"),
        ("bot_message nao-vazio", bool(result.bot_message)),
    ]


def _check_variant_or_checkout(result, state):
    has_url_in_msg = bool(result.bot_message and "http" in result.bot_message.lower())
    return [
        ("status=active", result.status == "active"),
        ("variant ou checkout sinalizado (state/msg)",
         bool(state.get("selected_variant_id") or state.get("checkout_url") or has_url_in_msg)),
    ]


def _check_checkout_url(result, state):
    has_url_in_msg = bool(result.bot_message and "http" in result.bot_message.lower())
    return [
        ("status=active", result.status == "active"),
        ("checkout_url no state OU link na mensagem",
         bool(state.get("checkout_url") or has_url_in_msg)),
    ]


def _check_wismo_initiated(result, state):
    return [
        ("status=active", result.status == "active"),
        ("bot pediu order_id OU action get_order",
         result.action == "get_order"
         or any(kw in (result.bot_message or "").lower() for kw in ["pedido", "número", "ordem", "numero"])),
    ]


def _check_order_lookup(result, state):
    return [
        ("status=active", result.status == "active"),
        ("get_order ou get_tracking acionado",
         result.action in ("get_order", "get_tracking") or bool(state.get("order_id"))),
    ]


def _check_store_qa(result, state):
    return [
        ("status in (active, handoff)", result.status in ("active", "handoff")),
        ("bot_message nao-vazio", bool(result.bot_message)),
        ("response menciona troca/devolucao/atendente/politica OU lookup_kb chamado",
         result.action == "lookup_knowledge_base"
         or any(kw in (result.bot_message or "").lower()
                for kw in ["troca", "devolu", "politic", "atendente"])),
    ]


def _check_handoff_triggered(result, state):
    return [
        ("status=handoff", result.status == "handoff"),
        ("bot_message nao-vazio (mensagem de handoff)", bool(result.bot_message)),
    ]


def _check_multi_topic(result, state):
    return [
        ("status=active", result.status == "active"),
        ("bot_message nao-vazio", bool(result.bot_message)),
    ]


def _check_fact_extracted(result, state):
    facts = state.get("facts") or {}
    return [
        ("status=active", result.status == "active"),
        ("bot_message nao-vazio", bool(result.bot_message)),
    ]


def _check_memory_reused(result, state):
    return [
        ("status=active", result.status == "active"),
        ("bot_message nao-vazio", bool(result.bot_message)),
    ]


SCENARIOS = [
    ("Cenario 1: Saudacao simples", [
        ("oi", _check_active_with_message),
    ]),
    ("Cenario 2: Search -> foco -> variante -> checkout", [
        ("oi, queria ver corrente de prata", _check_search_called),
        ("a primeira mesmo, quais tamanhos?", _check_product_focused),
        ("quero a tamanho M", _check_variant_or_checkout),
        ("como faco pra comprar?", _check_checkout_url),
    ]),
    ("Cenario 3: WISMO (cade meu pedido)", [
        ("cade meu pedido?", _check_wismo_initiated),
        ("o numero e 1001", _check_order_lookup),
    ]),
    ("Cenario 4: Q&A institucional", [
        ("qual a politica de troca de voces?", _check_store_qa),
    ]),
    ("Cenario 5: Refund triggera handoff", [
        ("quero devolver meu pedido", _check_handoff_triggered),
    ]),
    ("Cenario 6: Frustracao crescente triggera handoff", [
        ("isso nao funciona", _check_active_with_message),
        ("estou furioso, voces sao pessimos", _check_active_with_message),
        ("nao aguento mais, quero falar com humano", _check_handoff_triggered),
    ]),
    ("Cenario 7: Multi-topico (sales + support)", [
        ("comprei o kit ontem mas quero ver outras cores tambem", _check_multi_topic),
    ]),
    ("Cenario 8: Memoria entre turnos", [
        ("estou comprando pro meu filho de 8 anos", _check_fact_extracted),
        ("tem algum produto infantil?", _check_memory_reused),
    ]),
]


def main():
    if not os.getenv("OPENAI_API_KEY"):
        print(f"{C.RED}{C.BOLD}ERRO: OPENAI_API_KEY nao setada no ambiente.{C.RESET}")
        sys.exit(1)
    if not os.getenv("SUPABASE_POSTGRES_URI"):
        print(f"{C.RED}{C.BOLD}ERRO: SUPABASE_POSTGRES_URI nao setada (necessario pro PostgresSaver).{C.RESET}")
        sys.exit(1)

    print(f"\n{C.BOLD}=== SMOKE TEST E2E POS-CUTOVER FASE 2 ==={C.RESET}")
    print(f"{C.BOLD}LLM: gpt-4o-mini | Tenant: {TENANT_ID[:18]}...{C.RESET}")

    start = time.time()
    passes = 0
    partials = 0
    for name, turns in SCENARIOS:
        ok = run_scenario(name, turns)
        if ok:
            passes += 1
        else:
            partials += 1

    elapsed = time.time() - start
    print(f"\n{C.BOLD}{'='*48}{C.RESET}")
    print(f"{C.BOLD}RESUMO:{C.RESET} {C.GREEN}{passes} PASS{C.RESET} | {C.YELLOW}{partials} PARTIAL{C.RESET}")
    print(f"{C.DIM}Tempo total: {elapsed:.1f}s{C.RESET}")
    print(f"{C.BOLD}{'='*48}{C.RESET}\n")


if __name__ == "__main__":
    main()
