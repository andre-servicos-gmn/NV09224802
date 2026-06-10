"""Testes do `process_message` minimalista pós-cutover Fase 2.

process_message virou camada fina: resolve tenant → checa active → invoca
graph → mapeia AgentResult → ProcessResult. Os testes monkeypatcham
`invoke` (do app.graphs) e validam o mapeamento.
"""

import pytest

from app.core.turn_processor import process_message, ProcessResult
from app.graphs.invoke import AgentResult
from app.tests.fakes import FakeTenantConfig, FakeTenantRegistry


def _patch_invoke(monkeypatch, agent_result, registry=None):
    """Substitui invoke() (chamado dentro de process_message) e TenantRegistry."""
    registry = registry or FakeTenantRegistry()
    monkeypatch.setattr(
        "app.core.turn_processor.TenantRegistry", lambda: registry
    )
    # invoke é importado no topo do turn_processor (não lazy).
    monkeypatch.setattr(
        "app.core.turn_processor.invoke", lambda **kw: agent_result
    )
    return registry


def test_resolves_tenant_and_invokes_graph(monkeypatch):
    """Tenant válido → invoke() é chamado e o resultado é mapeado pra ProcessResult."""
    called = {"invoked": False, "kwargs": None}

    def fake_invoke(**kw):
        called["invoked"] = True
        called["kwargs"] = kw
        return AgentResult(bot_message="ok!", tool_calls=[], iterations=1)

    monkeypatch.setattr(
        "app.core.turn_processor.TenantRegistry", lambda: FakeTenantRegistry()
    )
    monkeypatch.setattr("app.core.turn_processor.invoke", fake_invoke)

    result = process_message(
        tenant_id="t1", session_id="s1", user_message="oi", channel="web",
    )

    assert called["invoked"] is True
    assert called["kwargs"]["tenant_id"] == "t1"
    assert called["kwargs"]["session_id"] == "s1"
    assert called["kwargs"]["user_message"] == "oi"
    assert called["kwargs"]["channel"] == "web"
    assert result.status == "active"
    assert result.bot_message == "ok!"


def test_blocks_inactive_tenant_non_playground(monkeypatch):
    """Tenant inativo fora do playground → status=blocked, invoke NÃO chamado."""
    invoked = {"v": False}

    def should_not_invoke(**kw):
        invoked["v"] = True
        return AgentResult(bot_message="x")

    inactive_registry = FakeTenantRegistry(tenant=FakeTenantConfig(active=False))
    monkeypatch.setattr(
        "app.core.turn_processor.TenantRegistry", lambda: inactive_registry
    )
    monkeypatch.setattr("app.core.turn_processor.invoke", should_not_invoke)

    result = process_message(
        tenant_id="t1", session_id="s1", user_message="oi", is_playground=False,
    )

    assert result.status == "blocked"
    assert result.action == "agent_disabled"
    assert "desativado" in result.bot_message
    assert invoked["v"] is False


def test_passes_inactive_tenant_in_playground(monkeypatch):
    """Tenant inativo no playground → bloqueio ignorado, invoke roda."""
    _patch_invoke(
        monkeypatch,
        AgentResult(bot_message="resposta playground", tool_calls=[], iterations=1),
        registry=FakeTenantRegistry(tenant=FakeTenantConfig(active=False)),
    )

    result = process_message(
        tenant_id="t1", session_id="s1", user_message="oi", is_playground=True,
    )

    assert result.status == "active"
    assert result.bot_message == "resposta playground"


def test_maps_agent_result_to_process_result(monkeypatch):
    """AgentResult.tool_calls[-1] vira ProcessResult.action."""
    _patch_invoke(
        monkeypatch,
        AgentResult(
            bot_message="achei",
            tool_calls=["search_products", "get_product_variants"],
            iterations=3,
        ),
    )

    result = process_message(
        tenant_id="t1", session_id="s1", user_message="oi",
    )

    assert result.status == "active"
    assert result.action == "get_product_variants"
    assert result.bot_message == "achei"


def test_handoff_triggered_returns_status_handoff(monkeypatch):
    """AgentResult.handoff_triggered=True → ProcessResult.status='handoff'."""
    _patch_invoke(
        monkeypatch,
        AgentResult(
            bot_message="Vou te colocar com um atendente.",
            tool_calls=["escalate_handoff"],
            iterations=2,
            handoff_triggered=True,
        ),
    )

    result = process_message(
        tenant_id="t1", session_id="s1", user_message="quero humano",
    )

    assert result.status == "handoff"
    assert result.action == "escalate_handoff"
    assert "atendente" in result.bot_message.lower()


def test_v_error_returns_status_error(monkeypatch):
    """AgentResult.error preenchido → ProcessResult.status='error'."""
    _patch_invoke(
        monkeypatch,
        AgentResult(
            bot_message="",
            tool_calls=[],
            iterations=0,
            error="simulated crash",
        ),
    )

    result = process_message(
        tenant_id="t1", session_id="s1", user_message="oi",
    )

    assert result.status == "error"
    assert result.error == "simulated crash"
    assert "problema" in result.bot_message.lower()


def test_tenant_not_found_returns_error_without_invoking(monkeypatch):
    """TenantRegistry.get → ValueError → ProcessResult.status='error', invoke não roda."""
    invoked = {"v": False}

    def should_not_invoke(**kw):
        invoked["v"] = True
        return AgentResult(bot_message="x")

    failing_registry = FakeTenantRegistry(should_raise=True)
    monkeypatch.setattr(
        "app.core.turn_processor.TenantRegistry", lambda: failing_registry
    )
    monkeypatch.setattr("app.core.turn_processor.invoke", should_not_invoke)

    result = process_message(
        tenant_id="invalid", session_id="s1", user_message="oi",
    )

    assert result.status == "error"
    assert result.error == "tenant_not_found"
    assert result.bot_message == "Tenant inválido"
    assert invoked["v"] is False
