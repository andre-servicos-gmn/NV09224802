from pathlib import Path

import json
import os

import pytest

from dotenv import load_dotenv

load_dotenv()

from app.core.constants import (
    INTENT_CART_RETRY,
    INTENT_ORDER_COMPLAINT,
    INTENT_PRODUCT_LINK,
    INTENT_PROVIDE_ORDER_ID,
)
from app.core.router import classify
from app.core.state import ConversationState
from app.core.tenancy import TenantRegistry
from app.graphs.main_graph import run_main_graph


def _run_message(state, tenant, message):
    state.last_user_message = message
    context = {"tenant_id": state.tenant_id, "session_id": state.session_id}
    decision = classify(message, context=context, use_llm=True)
    state.intent = decision.intent
    state.domain = decision.domain
    if decision.entities:
        state.metadata["entities"] = decision.entities
    state.sentiment_level = decision.sentiment_level
    state.sentiment_score = decision.sentiment_score
    state.needs_handoff = decision.needs_handoff
    state.handoff_reason = decision.handoff_reason
    if decision.sentiment_level != "calm":
        state.bump_frustration()
    return run_main_graph(state, tenant)


def _run_script(state, tenant, path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        state = _run_message(state, tenant, line)
    return state


def test_checkout_retry_dialog():
    tenant = TenantRegistry().get("demo")
    state = ConversationState(tenant_id=tenant.tenant_id, session_id="test-session")

    state = _run_message(state, tenant, "oi")
    state = _run_message(state, tenant, "vi esse produto https://example.com/products/colar")
    assert state.selected_variant_id is not None

    state = _run_message(state, tenant, "quero comprar")
    assert state.last_strategy == "permalink"

    state = _run_message(state, tenant, "deu erro no link")
    state.last_action_success = False

    state = _run_message(state, tenant, "gera de novo")
    assert state.last_strategy == "add_to_cart"
    assert state.last_bot_message.count("https://") == 1


def test_store_qa_payment_dialog():
    tenant = TenantRegistry().get("demo")
    state = ConversationState(tenant_id=tenant.tenant_id, session_id="test-session")
    script_path = Path("tests/dialogs/store_qa_payment.txt")

    state = _run_script(state, tenant, script_path)
    assert state.last_bot_message


def test_order_tracking_stale_dialog():
    tenant = TenantRegistry().get("demo")
    state = ConversationState(tenant_id=tenant.tenant_id, session_id="test-session")
    script_path = Path("tests/dialogs/order_tracking_stale.txt")

    state = _run_script(state, tenant, script_path)
    assert "https://track.example.com/ABC" in state.last_bot_message
    assert state.ticket_opened is True


def _coerce_entity_value(value):
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def test_router_llm_cases():
    script_path = Path("tests/dialogs/router_llm_cases.txt")
    lines = [line.strip() for line in script_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = []
    for line in lines:
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 4:
            raise ValueError(f"Invalid test line: {line}")
        message, expected_domain, expected_intent, expected_entities = parts
        cases.append((message, expected_domain, expected_intent, json.loads(expected_entities)))

    if not os.getenv("OPENAI_API_KEY") or os.getenv("RUN_LLM_TESTS", "false").lower() != "true":
        for message, _domain, _intent, _entities in cases:
            classify(message, context=None, use_llm=False)
        pytest.skip("LLM router tests disabled (missing OPENAI_API_KEY or RUN_LLM_TESTS).")

    for message, expected_domain, expected_intent, expected_entities in cases:
        decision = classify(message, context=None, use_llm=True)
        assert decision.domain == expected_domain
        assert decision.intent == expected_intent
        assert decision.confidence >= 0.65
        for key, value in expected_entities.items():
            assert _coerce_entity_value(decision.entities.get(key)) == _coerce_entity_value(value)


# Heuristic tests removed as we moved to 100% AI router.
# The following tests were deleted because classify_intent_heuristic no longer exists/works.
# - test_router_heuristic_digits_only_order_id
# - test_router_heuristic_order_complaint_days
# - test_router_heuristic_product_url

def test_router_ambiguous_llm_fallback(monkeypatch):
    from app.core.router_llm import RouterResult, TopIntent

    def _fake_llm(_message, _context, _intents, timeout_s=None):
        return RouterResult(
            domain="sales",
            intent=INTENT_CART_RETRY,
            confidence=0.7,
            ambiguous=False,
            top_intents=[TopIntent(intent=INTENT_CART_RETRY, confidence=0.7)],
            entities={"order_id": "1001"},
            rationale="test",
        )

    monkeypatch.setattr("app.core.router.classify_with_llm", _fake_llm)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    # This should trigger sanity check failure because order_id is present but domain is sales
    # (actually sales usually doesn't have order_id, sanity_check line 173:
    # if (entities.get("order_id") or entities.get("email")) and domain == "sales": return False)
    # So this mimics a bad LLM result that should trigger fallback.
    decision = classify("pedido 1001 parado", context=None, use_llm=True)
    assert decision.used_fallback is True



def test_sentiment_handoff_dialog():
    tenant = TenantRegistry().get("demo")
    state = ConversationState(tenant_id=tenant.tenant_id, session_id="test-session")
    script_path = Path("tests/dialogs/sentiment_handoff.txt")

    state = _run_script(state, tenant, script_path)
    assert state.needs_handoff is True
    assert "atendente humano" in state.last_bot_message.lower()
    assert "golpe" not in state.last_bot_message.lower()


def test_sentiment_frustration_no_handoff():
    tenant = TenantRegistry().get("demo")
    state = ConversationState(tenant_id=tenant.tenant_id, session_id="test-session")
    script_path = Path("tests/dialogs/frustration_no_handoff.txt")

    state = _run_script(state, tenant, script_path)
    assert state.needs_handoff is False
