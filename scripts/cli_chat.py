import argparse
import sys
import unicodedata
import uuid
from pathlib import Path

from dotenv import load_dotenv

from app.core.constants import FRUSTRATION_KEYWORDS
from app.core.router import classify_intent
from app.core.state import ConversationState
from app.core.tenancy import TenantRegistry
from app.graphs.sales_graph import run_sales_graph


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


def run_chat(tenant_id: str, session_id: str, debug: bool, script_path: Path | None) -> int:
    registry = TenantRegistry()
    tenant = registry.get(tenant_id)
    state = ConversationState(tenant_id=tenant.tenant_id, session_id=session_id)

    if script_path:
        lines = _load_script_lines(script_path)
    else:
        lines = []

    try:
        while True:
            if lines:
                message = lines.pop(0)
            else:
                message = input("voce: ").strip()
            if not message:
                if lines:
                    continue
                break

            state.last_user_message = message
            state.set_intent(classify_intent(message))
            if _has_frustration(message):
                state.bump_frustration()

            state = run_sales_graph(state, tenant)
            print(state.last_bot_message)

            if debug:
                print(
                    f"[debug] intent={state.intent} "
                    f"strategy={state.last_strategy} "
                    f"last_action_success={state.last_action_success} "
                    f"response_model={state.metadata.get('response_model')} "
                    f"response_error={state.metadata.get('response_error')}"
                )
    except (EOFError, KeyboardInterrupt):
        return 0

    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="CLI chat for Nouvaris Agents V2")
    parser.add_argument("--tenant", default="demo")
    parser.add_argument("--session", default=uuid.uuid4().hex)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--script", type=Path)
    args = parser.parse_args()

    return run_chat(args.tenant, args.session, args.debug, args.script)


if __name__ == "__main__":
    sys.exit(main())

