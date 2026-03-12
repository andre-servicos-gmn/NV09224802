from pathlib import Path

import json
import os

import pytest

from dotenv import load_dotenv

load_dotenv()

from app.core.router import classify, apply_entities_to_state
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
        state.soft_context["entities"] = decision.entities
        apply_entities_to_state(state, decision.entities)
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


def test_store_qa_payment_dialog():
    tenant = TenantRegistry().get("demo")
    state = ConversationState(tenant_id=tenant.tenant_id, session_id="test-session")
    script_path = Path("tests/dialogs/store_qa_payment.txt")

    state = _run_script(state, tenant, script_path)
    assert state.last_bot_message


def test_order_tracking_stale_dialog(monkeypatch):
    # Mock classify to return predictable intents for the script messages
    from app.core.router import RouterDecision
    
    def mock_classify(message: str, context=None, use_llm=True):
        # Message 1: "meu pedido esta parado..." -> order_complaint
        if "parado" in message.lower() and "dias" in message.lower():
            return RouterDecision(
                domain="support",
                intent="order_complaint",
                entities={},
                confidence=0.9,
                used_fallback=False,
                reason="mock",
                sentiment_level="frustrated",
                sentiment_score=0.6,
                needs_handoff=False,
                handoff_reason=None,
                used_sentiment_llm=False,
            )
        # Message 2: "1001" -> provide_order_id
        elif message.strip() == "1001":
            return RouterDecision(
                domain="support",
                intent="provide_order_id",
                entities={"order_id": "1001"},
                confidence=0.95,
                used_fallback=False,
                reason="mock",
                sentiment_level="calm",
                sentiment_score=0.2,
                needs_handoff=False,
                handoff_reason=None,
                used_sentiment_llm=False,
            )
        # Message 3: "entao eu disse..." -> order_complaint (to trigger ticket)
        elif "disse" in message.lower() and "parado" in message.lower():
            return RouterDecision(
                domain="support",
                intent="order_complaint",
                entities={},
                confidence=0.85,
                used_fallback=False,
                reason="mock",
                sentiment_level="frustrated",
                sentiment_score=0.7,
                needs_handoff=False,
                handoff_reason=None,
                used_sentiment_llm=False,
            )
        # Fallback
        return RouterDecision(
            domain="store_qa",
            intent="general",
            entities={},
            confidence=0.5,
            used_fallback=True,
            reason="mock_fallback",
            sentiment_level="calm",
            sentiment_score=0.2,
            needs_handoff=False,
            handoff_reason=None,
            used_sentiment_llm=False,
        )
    
    monkeypatch.setattr("app.core.router.classify", mock_classify)
    monkeypatch.setattr("app.tests.test_dialogs.classify", mock_classify)
    
    # Mock Shopify Client
    def mock_get_order_by_number(self, order_number):
        if str(order_number) == "1001":
            return {
                "id": 12345,
                "order_number": 1001,
                "email": "customer@example.com",
                "financial_status": "paid",
                "fulfillment_status": "fulfilled",
                "fulfillments": [
                    {
                        "tracking_urls": ["https://track.example.com/ABC"],
                        "tracking_number": "ABC",
                    }
                ],
                "line_items": [{"name": "Item A", "quantity": 1, "sku": "SKU1", "variant_id": 1}],
                "created_at": "2023-01-01T12:00:00Z",
                "updated_at": "2023-01-01T12:00:00Z",
            }
        return None

    monkeypatch.setattr("app.tools.shopify_orders.ShopifyOrdersClient.get_order_by_number", mock_get_order_by_number)

    # Mock Supabase for ticket creation
    class MockSupabase:
        def table(self, name):
            return self
        def upsert(self, data):
            return self
        def execute_upsert(self):
            class Resp:
                data = [{"id": 1}]
            return Resp()
            
    monkeypatch.setattr("app.nodes.action_open_ticket.get_supabase", lambda: MockSupabase())

    tenant = TenantRegistry().get("demo")
    state = ConversationState(tenant_id=tenant.tenant_id, session_id="test-session")
    script_path = Path("tests/dialogs/order_tracking_stale.txt")

    state = _run_script(state, tenant, script_path)
    assert state.tracking_url == "https://track.example.com/ABC"
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
            classify(message, context=None, use_llm=False)
        pytest.skip("OPENAI_API_KEY not set; skipping LLM router cases.")

    for message, expected_domain, expected_intent, expected_entities in cases:
        decision = classify(message, context=None, use_llm=True)
        assert decision.domain == expected_domain
        assert decision.intent == expected_intent
        assert decision.confidence >= 0.65
        for key, value in expected_entities.items():
            assert _coerce_entity_value(decision.entities.get(key)) == _coerce_entity_value(value)


def test_router_ambiguous_llm_fallback(monkeypatch):
    from app.core.router_llm import RouterResult, TopIntent

    def _fake_llm(_message, _context, _intents, timeout_s=None):
        return RouterResult(
            domain="sales",
            intent="search_product",
            confidence=0.7,
            ambiguous=False,
            top_intents=[TopIntent(intent="search_product", confidence=0.7)],
            entities={"order_id": "1001"},
            rationale="test",
        )

    monkeypatch.setattr("app.core.router.classify_with_llm", _fake_llm)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
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


def test_greeting_no_apology():
    """Regression: a sales greeting with no products must NOT mention a failed action."""
    from app.core.llm_humanized import _get_system_data_payload
    from app.core.tenancy import TenantRegistry

    tenant = TenantRegistry().get("demo")
    state = ConversationState(tenant_id=tenant.tenant_id, session_id="test-greeting")
    state.intent = "greeting"
    state.domain = "sales"

    # --- Unit check: payload must not contain failure guidance ---
    payload = _get_system_data_payload(state, tenant, "sales", "")
    assert "ERRO" not in payload, (
        f"Payload should not contain failure guidance for a greeting.\nPayload:\n{payload}"
    )
    assert "falhou" not in payload.lower(), (
        f"Payload should not mention 'falhou' for a greeting.\nPayload:\n{payload}"
    )

    # --- Integration check: bot reply must not apologise ---
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set; skipping LLM integration part.")

    state = _run_message(state, tenant, "oi")
    reply = (state.last_bot_message or "").lower()
    apology_words = ["erro", "falhou", "problema", "desculp"]
    for word in apology_words:
        assert word not in reply, (
            f"Greeting reply should not contain '{word}'.\nReply: {state.last_bot_message}"
        )
