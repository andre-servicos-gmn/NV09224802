"""Testes de integração: tools individuais + send_typing no webhook.

Sem rede: RAG e Shopify monkeypatchados.
"""

import asyncio
import pytest

from app.graphs.tools import (
    search_products,
    generate_checkout_link,
    escalate_handoff,
    extract_user_facts,
)
from app.tests.fakes import FakeTenantConfig, FakeTenantRegistry


# ─── Helpers ──────────────────────────────────────────────────────────

class _FakeRAGPipeline:
    """Fake do RAGPipeline pra evitar Supabase/pgvector real."""

    def __init__(self, products=None, context=""):
        self._products = products or []
        self._context = context
        self.tenant_id = "fake"

    def search_products(self, query, limit=5, only_in_stock=False):
        return self._products[:limit]

    def retrieve_context(self, query, context_type="product", top_k=5):
        return self._context


# ─── Tools individuais ────────────────────────────────────────────────

def test_tool_search_products_calls_rag_engine_and_formats(monkeypatch):
    """search_products chama RAGPipeline e formata 3 produtos."""
    fake_products = [
        {"product_id": "p1", "title": "Colar A", "price": 49.9, "description": "Bonito"},
        {"product_id": "p2", "title": "Colar B", "price": 59.9, "description": "Mais bonito"},
        {"product_id": "p3", "title": "Colar C", "price": 69.9, "description": ""},
    ]
    monkeypatch.setattr(
        "app.graphs.tools._get_rag_pipeline",
        lambda tenant_id: _FakeRAGPipeline(products=fake_products),
    )

    result = search_products.invoke(
        {"query": "corrente", "state": {"tenant_id": "t1"}}
    )

    assert "Produto 1: Colar A" in result
    assert "Produto 2: Colar B" in result
    assert "Produto 3: Colar C" in result
    assert "R$ 49.90" in result


def test_tool_generate_checkout_link_builds_shopify_url(monkeypatch):
    """generate_checkout_link constrói URL Shopify usando tenant.store_domain."""
    fake_tenant = FakeTenantConfig(store_domain="lojinha.myshopify.com")
    monkeypatch.setattr(
        "app.graphs.tools._resolve_tenant", lambda tenant_id: fake_tenant
    )

    result = generate_checkout_link.invoke(
        {"product_id": "p1", "variant_id": "v1", "state": {"tenant_id": "t1"}}
    )

    assert "https://lojinha.myshopify.com/cart/v1:1" in result


def test_tool_escalate_handoff_returns_string_with_reason():
    """escalate_handoff retorna string contendo o motivo da escalação.

    A detecção do handoff acontece em invoke() varrendo tool_calls do turno.
    """
    result = escalate_handoff.invoke(
        {"reason": "cliente pediu humano", "state": {"tenant_id": "t1"}}
    )

    assert isinstance(result, str)
    assert "cliente pediu humano" in result


# ─── Webhook send_typing antes de process_message ─────────────────────

class _SpyAdapter:
    """FakeAdapter que captura ordem dos métodos chamados."""

    def __init__(self):
        self.send_typing_calls = []
        self.sent_messages = []
        self.marked_read_ids = []
        self.call_log = []

    async def send_typing(self, to: str):
        self.send_typing_calls.append(to)
        self.call_log.append("send_typing")
        return True

    async def send_text_message(self, to: str, text: str):
        self.sent_messages.append((to, text))
        self.call_log.append("send_text_message")

        class _R:
            success = True
            error = None
        return _R()

    async def mark_as_read(self, message_id: str):
        self.marked_read_ids.append(message_id)
        self.call_log.append("mark_as_read")


def test_webhook_calls_send_typing_before_process_message(monkeypatch):
    """webhook chama adapter.send_typing(to=from_number) ANTES de process_message."""
    from app.api import webhooks
    from app.api.webhooks import process_consolidated_message

    fake_registry = FakeTenantRegistry()
    fake_adapter = _SpyAdapter()

    monkeypatch.setattr("app.api.webhooks.TenantRegistry", lambda: fake_registry)
    monkeypatch.setattr(
        "app.api.webhooks._get_whatsapp_adapter", lambda t: fake_adapter
    )
    monkeypatch.setattr("app.api.webhooks.clear_session", lambda tu, sid: None)

    from app.core.turn_processor import ProcessResult

    process_message_called_at = {"idx": None}

    def fake_process_message(**kwargs):
        process_message_called_at["idx"] = len(fake_adapter.call_log)
        return ProcessResult(
            status="active",
            bot_message="resposta",
            session_id=kwargs.get("session_id"),
            intent="general",
            domain="store_qa",
        )

    monkeypatch.setattr("app.api.webhooks.process_message", fake_process_message)
    webhooks.SENT_MESSAGE_HASHES.clear()

    asyncio.run(
        process_consolidated_message(
            "oi",
            tenant_id="t1",
            from_number="5511999",
            session_id="s1",
            message_ids=["msg1"],
        )
    )

    assert len(fake_adapter.send_typing_calls) == 1
    assert fake_adapter.send_typing_calls[0] == "5511999"

    # send_typing veio ANTES da execução de process_message
    assert process_message_called_at["idx"] is not None
    assert fake_adapter.call_log[0] == "send_typing"
    assert process_message_called_at["idx"] >= 1


# ─── extract_user_facts: persistência via Command + ToolMessage (Fase 4) ───

def test_extract_user_facts_persists_facts_in_state(monkeypatch):
    """extract_user_facts retorna Command com facts merge + ToolMessage."""
    from langgraph.types import Command
    from langchain_core.messages import ToolMessage

    monkeypatch.setattr(
        "app.graphs.tools._extract_facts_llm",
        lambda msg: {"filho_idade": 8, "localizacao": "SP"},
    )

    # Acessa o inner function via __wrapped__ ou func attribute pra contornar
    # a restrição de ToolCall format quando InjectedToolCallId está presente.
    inner = extract_user_facts.func
    result = inner(
        message="estou comprando pro meu filho de 8 anos em SP",
        state={"facts": {}, "tenant_id": "t1"},
        tool_call_id="tc1",
    )

    assert isinstance(result, Command)
    assert result.update["facts"] == {"filho_idade": 8, "localizacao": "SP"}
    msgs = result.update["messages"]
    assert len(msgs) == 1
    assert isinstance(msgs[0], ToolMessage)
    assert msgs[0].tool_call_id == "tc1"
    assert "filho_idade" in msgs[0].content


def test_extract_user_facts_merges_with_existing_facts(monkeypatch):
    """Facts novos são mergeados com os existentes (sem perder anteriores)."""
    from langgraph.types import Command

    monkeypatch.setattr(
        "app.graphs.tools._extract_facts_llm",
        lambda msg: {"interesse": "joias"},
    )

    inner = extract_user_facts.func
    result = inner(
        message="amo joias",
        state={"facts": {"filho_idade": 8}, "tenant_id": "t1"},
        tool_call_id="tc2",
    )

    assert isinstance(result, Command)
    assert result.update["facts"] == {"filho_idade": 8, "interesse": "joias"}


def test_extract_user_facts_returns_command_when_no_facts(monkeypatch):
    """Sem facts extraídos → Command sem update de facts, só ToolMessage."""
    from langgraph.types import Command
    from langchain_core.messages import ToolMessage

    monkeypatch.setattr("app.graphs.tools._extract_facts_llm", lambda msg: {})

    inner = extract_user_facts.func
    result = inner(
        message="obrigado",
        state={"facts": {}, "tenant_id": "t1"},
        tool_call_id="tc3",
    )

    assert isinstance(result, Command)
    assert "facts" not in result.update
    msgs = result.update["messages"]
    assert isinstance(msgs[0], ToolMessage)
    assert msgs[0].tool_call_id == "tc3"
    assert "Nada novo" in msgs[0].content


def test_build_system_prompt_injects_facts_section():
    """facts preenchido → seção CONTEXTO PESSOAL no prompt."""
    from app.graphs.supervisor import _build_system_prompt

    tenant = FakeTenantConfig()
    facts = {"filho_idade": 8, "localizacao": "SP"}
    prompt = _build_system_prompt(tenant, facts=facts)

    assert "CONTEXTO PESSOAL JÁ CONHECIDO" in prompt
    assert "filho_idade: 8" in prompt
    assert "localizacao: SP" in prompt


def test_build_system_prompt_omits_facts_section_when_empty():
    """facts vazio ou None → seção CONTEXTO PESSOAL omitida."""
    from app.graphs.supervisor import _build_system_prompt

    tenant = FakeTenantConfig()

    prompt_empty = _build_system_prompt(tenant, facts={})
    assert "CONTEXTO PESSOAL JÁ CONHECIDO" not in prompt_empty

    prompt_none = _build_system_prompt(tenant, facts=None)
    assert "CONTEXTO PESSOAL JÁ CONHECIDO" not in prompt_none
