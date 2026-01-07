import argparse
import os
import sys
import unicodedata
import uuid
from pathlib import Path
from typing import NoReturn

from dotenv import load_dotenv

from app.core.constants import FRUSTRATION_KEYWORDS
from app.core.router import apply_entities_to_state, classify
from app.core.state import ConversationState
from app.core.tenancy import TenantRegistry
from app.graphs.main_graph import run_main_graph


class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return text


def _has_frustration(text: str) -> bool:
    msg = _normalize(text)
    return any(keyword in msg for keyword in FRUSTRATION_KEYWORDS)


def _load_script_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def print_banner():
    print(f"{Colors.HEADER}==========================================")
    print(f"   NOUVARIS AGENTS V2 - CLI INTERFACE")
    print(f"=========================================={Colors.ENDC}")
    print(f"{Colors.CYAN}Type '/help' for commands.{Colors.ENDC}\n")


def print_help():
    print(f"\n{Colors.BOLD}Available Commands:{Colors.ENDC}")
    print(f"  {Colors.GREEN}/quit, /exit{Colors.ENDC} : Exit the application")
    print(f"  {Colors.GREEN}/clear{Colors.ENDC}       : Clear the screen")
    print(f"  {Colors.GREEN}/debug{Colors.ENDC}       : Toggle debug mode")
    print(f"  {Colors.GREEN}/help{Colors.ENDC}        : Show this help message\n")


def run_chat(
    tenant_id: str,
    session_id: str,
    debug: bool,
    script_path: Path | None,
    use_llm_router: bool,
) -> int:
    registry = TenantRegistry()
    try:
        tenant = registry.get(tenant_id)
    except KeyError:
        print(f"{Colors.FAIL}Error: Tenant '{tenant_id}' not found.{Colors.ENDC}")
        return 1

    state = ConversationState(tenant_id=tenant.tenant_id, session_id=session_id)

    if script_path:
        lines = _load_script_lines(script_path)
    else:
        print_banner()
        lines = []

    try:
        while True:
            if lines:
                message = lines.pop(0)
                print(f"{Colors.BLUE}You (script):{Colors.ENDC} {message}")
            else:
                try:
                    message = input(f"{Colors.BLUE}You:{Colors.ENDC} ").strip()
                except EOFError:
                    break

            if not message:
                if lines:
                    continue
                # If interactive and empty, just prompt again
                continue

            # Handle Slash Commands
            if message.startswith("/"):
                cmd = message.lower()
                if cmd in ["/quit", "/exit"]:
                    print(f"{Colors.HEADER}Goodbye!{Colors.ENDC}")
                    break
                elif cmd == "/clear":
                    os.system('cls' if os.name == 'nt' else 'clear')
                    print_banner()
                    continue
                elif cmd == "/debug":
                    debug = not debug
                    status = "ON" if debug else "OFF"
                    print(f"{Colors.WARNING}Debug mode: {status}{Colors.ENDC}")
                    continue
                elif cmd == "/help":
                    print_help()
                    continue
                else:
                    print(f"{Colors.FAIL}Unknown command: {cmd}{Colors.ENDC}")
                    continue

            # Logic Flow
            state.last_user_message = message
            state.add_to_history("user", message)  # Add to conversation memory
            context = {
                "tenant_id": state.tenant_id,
                "session_id": state.session_id,
                "last_domain": state.domain,
                "last_intent": state.intent,
                "has_variant_id": bool(state.selected_variant_id),
                "has_order_id": bool(state.order_id),
                "store_name": tenant.name,
                "store_niche": tenant.store_niche or "loja online",
            }
            decision = classify(message, context=context, use_llm=use_llm_router)
            state.set_intent(decision.intent)
            state.domain = decision.domain
            apply_entities_to_state(state, decision.entities)
            state.sentiment_level = decision.sentiment_level
            state.sentiment_score = decision.sentiment_score
            state.needs_handoff = decision.needs_handoff
            state.handoff_reason = decision.handoff_reason

            if decision.sentiment_level != "calm" or _has_frustration(message):
                state.bump_frustration()
                if debug:
                    print(f"{Colors.FAIL}[Frustration Detected]{Colors.ENDC}")

            state = run_main_graph(state, tenant)
            state.add_to_history("agent", state.last_bot_message or "")  # Add bot response to memory
            
            print(f"{Colors.GREEN}Agent:{Colors.ENDC} {state.last_bot_message}")

            if debug:
                print(f"\n{Colors.WARNING}[DEBUG INFO]{Colors.ENDC}")
                print(f"  Tenant: {state.tenant_id}")
                print(f"  Session: {state.session_id}")
                print(f"  Domain: {state.domain}")
                print(f"  Intent: {state.intent}")
                print(f"  Confidence: {decision.confidence}")
                print(f"  Entities: {decision.entities}")
                print(f"  Used Fallback: {decision.used_fallback}")
                print(f"  Reason: {decision.reason}")
                print(f"  Sentiment Level: {decision.sentiment_level}")
                print(f"  Sentiment Score: {decision.sentiment_score}")
                print(f"  Needs Handoff: {decision.needs_handoff}")
                print(f"  Handoff Reason: {decision.handoff_reason}")
                print(f"  Sentiment LLM: {decision.used_sentiment_llm}")
                if decision.used_fallback:
                    print(f"  Fallback: ACTIVE")

                print(f"  Last Strategy: {state.last_strategy}")
                print(f"  Action Success: {state.last_action_success}")
                print(f"{Colors.WARNING}-------------------------{Colors.ENDC}\n")

    except KeyboardInterrupt:
        print(f"\n{Colors.HEADER}Interrupted. Goodbye!{Colors.ENDC}")
        return 0

    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="CLI chat for Nouvaris Agents V2")
    parser.add_argument("--tenant", default="demo", help="Tenant ID to use")
    parser.add_argument("--session", default=uuid.uuid4().hex, help="Session ID")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--script", type=Path, help="Path to a script file")
    parser.add_argument("--llm-router", dest="llm_router", action="store_true", default=True)
    parser.add_argument("--no-llm-router", dest="llm_router", action="store_false")
    args = parser.parse_args()

    return run_chat(args.tenant, args.session, args.debug, args.script, args.llm_router)


if __name__ == "__main__":
    sys.exit(main())
