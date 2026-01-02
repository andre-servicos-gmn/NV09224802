from pathlib import Path

import json
import os

import pytest

from app.core.router import classify
from app.core.state import ConversationState
from app.core.tenancy import TenantRegistry
from app.graphs.main_graph import run_main_graph


def _run_message(state, tenant, message):
    state.last_user_message = message
    domain, intent, entities, _confidence = classify(message, use_llm=False)
    state.intent = intent
    state.domain = domain
    if entities:
        state.metadata["entities"] = entities
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

    if not os.getenv("OPENAI_API_KEY"):
        for message, _domain, _intent, _entities in cases:
            classify(message, use_llm=False)
        pytest.skip("OPENAI_API_KEY not set; skipping LLM router cases.")

    for message, expected_domain, expected_intent, expected_entities in cases:
        domain, intent, entities, confidence = classify(message, use_llm=True)
        assert domain == expected_domain
        assert intent == expected_intent
        assert confidence >= 0.65
        for key, value in expected_entities.items():
            assert _coerce_entity_value(entities.get(key)) == _coerce_entity_value(value)
