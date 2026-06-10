"""Suite E2E do endpoint POST /chat (FastAPI TestClient).

process_message é real; só `invoke` (do graph) e o TenantRegistry são
patcheados via monkeypatch.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chat import router
from app.graphs.invoke import AgentResult
from app.tests.fakes import FakeTenantConfig, FakeTenantRegistry


def _make_client(
    monkeypatch,
    tenant: FakeTenantConfig = None,
    registry_raises: bool = False,
    agent_result: AgentResult = None,
):
    """Cria TestClient com TenantRegistry + invoke patcheados."""
    fake_registry = FakeTenantRegistry(tenant=tenant, should_raise=registry_raises)
    monkeypatch.setattr(
        "app.core.turn_processor.TenantRegistry", lambda: fake_registry
    )

    invoke_calls = []
    default_result = agent_result or AgentResult(
        bot_message="[fake reply]", tool_calls=[], iterations=1
    )

    def fake_invoke(**kw):
        invoke_calls.append(kw)
        if isinstance(default_result, Exception):
            raise default_result
        return default_result

    monkeypatch.setattr("app.core.turn_processor.invoke", fake_invoke)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    return client, invoke_calls


# ───── Smoke / shape ─────

def test_endpoint_returns_200_and_response_shape(monkeypatch):
    """POST /chat retorna 200 com as 4 chaves esperadas no JSON."""
    client, _ = _make_client(monkeypatch)
    response = client.post(
        "/chat",
        json={"message": "oi", "tenant_id": "t1", "session_id": "s1"},
    )
    assert response.status_code == 200
    data = response.json()
    for key in ("response", "session_id", "action", "status"):
        assert key in data


def test_endpoint_generates_session_id_when_not_provided(monkeypatch):
    """Sem session_id no request, endpoint gera um uuid4().hex de 32 chars."""
    client, _ = _make_client(monkeypatch)
    response = client.post(
        "/chat",
        json={"message": "oi", "tenant_id": "t1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["session_id"], str)
    assert len(data["session_id"]) == 32


def test_endpoint_preserves_session_id_when_provided(monkeypatch):
    """session_id explícito no request é preservado na resposta."""
    client, _ = _make_client(monkeypatch)
    response = client.post(
        "/chat",
        json={"message": "oi", "tenant_id": "t1", "session_id": "my-custom-session"},
    )
    assert response.json()["session_id"] == "my-custom-session"


# ───── Status mapping ─────

def test_endpoint_returns_active_status_on_happy_path(monkeypatch):
    """Caminho feliz: status=active, response do graph, invoke chamado uma vez."""
    client, invoke_calls = _make_client(
        monkeypatch,
        agent_result=AgentResult(
            bot_message="[fake reply]", tool_calls=["search_products"], iterations=2
        ),
    )
    response = client.post(
        "/chat",
        json={"message": "oi", "tenant_id": "t1", "session_id": "s1"},
    )
    data = response.json()
    assert data["status"] == "active"
    assert data["response"] == "[fake reply]"
    assert data["action"] == "search_products"
    assert len(invoke_calls) == 1


def test_endpoint_returns_blocked_for_inactive_tenant_non_playground(monkeypatch):
    """Tenant inativo fora do playground: status=blocked, sem chamar invoke."""
    inactive = FakeTenantConfig(active=False)
    client, invoke_calls = _make_client(monkeypatch, tenant=inactive)
    response = client.post(
        "/chat",
        json={
            "message": "oi",
            "tenant_id": "t1",
            "session_id": "s1",
            "is_playground": False,
        },
    )
    data = response.json()
    assert data["status"] == "blocked"
    assert data["action"] == "agent_disabled"
    assert "desativado" in data["response"]
    assert len(invoke_calls) == 0


def test_endpoint_returns_handoff_when_tool_escalated(monkeypatch):
    """AgentResult.handoff_triggered=True → endpoint retorna status='handoff'."""
    client, _ = _make_client(
        monkeypatch,
        agent_result=AgentResult(
            bot_message="Vou te colocar com um atendente.",
            tool_calls=["escalate_handoff"],
            iterations=2,
            handoff_triggered=True,
        ),
    )
    response = client.post(
        "/chat",
        json={"message": "quero humano", "tenant_id": "t1", "session_id": "s1"},
    )
    data = response.json()
    assert data["status"] == "handoff"
    assert data["action"] == "escalate_handoff"


def test_endpoint_returns_error_status_when_tenant_not_found(monkeypatch):
    """Tenant não encontrado retorna 200 com status=error."""
    client, invoke_calls = _make_client(monkeypatch, registry_raises=True)
    response = client.post(
        "/chat",
        json={"message": "oi", "tenant_id": "invalid", "session_id": "s1"},
    )
    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "error"
    assert data["response"] == "Tenant inválido"
    assert len(invoke_calls) == 0


# ───── Defesa contra exceções ─────

def test_endpoint_degrades_gracefully_when_invoke_raises(monkeypatch):
    """invoke que retorna AgentResult com error → status='error' + mensagem amigável."""
    client, _ = _make_client(
        monkeypatch,
        agent_result=AgentResult(
            bot_message="", tool_calls=[], iterations=0, error="simulated crash"
        ),
    )

    response = client.post(
        "/chat",
        json={"message": "oi", "tenant_id": "t1", "session_id": "s1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert "problema" in data["response"].lower()
