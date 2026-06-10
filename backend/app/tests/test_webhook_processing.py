"""Suite do handler do buffer WhatsApp (process_consolidated_message).

Patches mínimos pra isolar do banco/Redis/HTTP:
- TenantRegistry (resolve tenant)
- _get_whatsapp_adapter (retorna fake adapter)
- clear_session (no-op capturado)
- process_message (capturado + retorno controlado)
"""

import asyncio
import pytest

from app.api import webhooks
from app.api.webhooks import process_consolidated_message
from app.tests.fakes import FakeTenantConfig, FakeTenantRegistry


class _FakeSendResult:
    """Espelho minimalista do SendResult do adapter."""

    def __init__(self, success: bool = True, error: str = None):
        self.success = success
        self.error = error


class _FakeWhatsAppAdapter:
    """Adapter WhatsApp fake. Captura chamadas de send/mark_as_read/send_typing."""

    def __init__(self, send_success: bool = True):
        self.sent_messages: list[tuple[str, str]] = []  # (to, text)
        self.marked_read_ids: list[str] = []
        self.send_typing_calls: list[str] = []
        self._send_success = send_success

    async def send_text_message(self, to: str, text: str):
        self.sent_messages.append((to, text))
        return _FakeSendResult(success=self._send_success)

    async def mark_as_read(self, message_id: str):
        self.marked_read_ids.append(message_id)

    async def send_typing(self, to: str):
        self.send_typing_calls.append(to)
        return True


def _setup_fakes(
    monkeypatch,
    *,
    tenant: FakeTenantConfig = None,
    adapter: _FakeWhatsAppAdapter = None,
    bot_message: str = "[fake graph reply]",
    process_message_raises: bool = False,
):
    """Aplica patches mínimos para testar process_consolidated_message.

    Retorna (fake_registry, fake_adapter, calls, cleared).
    """
    fake_registry = FakeTenantRegistry(tenant=tenant)
    fake_adapter = adapter if adapter is not None else _FakeWhatsAppAdapter()
    calls: list[dict] = []
    cleared: list[tuple] = []

    monkeypatch.setattr("app.api.webhooks.TenantRegistry", lambda: fake_registry)
    monkeypatch.setattr(
        "app.api.webhooks._get_whatsapp_adapter", lambda t: fake_adapter
    )
    monkeypatch.setattr(
        "app.api.webhooks.clear_session",
        lambda tu, sid: cleared.append((tu, sid)),
    )

    from app.core.turn_processor import ProcessResult

    def fake_process_message(**kwargs):
        calls.append(kwargs)
        if process_message_raises:
            raise RuntimeError("simulated process_message failure")
        return ProcessResult(
            status="active",
            bot_message=bot_message,
            session_id=kwargs.get("session_id"),
            action=None,
            error=None,
        )

    monkeypatch.setattr("app.api.webhooks.process_message", fake_process_message)
    webhooks.SENT_MESSAGE_HASHES.clear()

    return fake_registry, fake_adapter, calls, cleared


# ───── Caminho feliz ─────

def test_processes_message_and_sends_single_chunk(monkeypatch):
    """Mensagem curta: process_message chamado, 1 chunk enviado ao destinatário."""
    _, fake_adapter, calls, _ = _setup_fakes(monkeypatch, bot_message="Olá!")
    asyncio.run(process_consolidated_message("oi", tenant_id="t1", from_number="5511999", session_id="s1", message_ids=["msg1"]))
    assert len(calls) == 1
    assert len(fake_adapter.sent_messages) == 1
    assert fake_adapter.sent_messages[0] == ("5511999", "Olá!")


def test_calls_process_message_with_correct_kwargs(monkeypatch):
    """process_message recebe tenant/session/user_message/channel/number/playground corretos."""
    _, _, calls, _ = _setup_fakes(monkeypatch)
    asyncio.run(process_consolidated_message("oi", tenant_id="t1", from_number="5511999", session_id="s1", message_ids=["msg1"]))
    assert calls[0]["tenant_id"] == "t1"
    assert calls[0]["session_id"] == "s1"
    assert calls[0]["user_message"] == "oi"
    assert calls[0]["channel"] == "whatsapp"
    assert calls[0]["number"] == "5511999"
    assert calls[0]["is_playground"] is False


def test_splits_long_message_into_multiple_chunks(monkeypatch):
    """Mensagem com múltiplos parágrafos longos é dividida em chunks naturais."""
    _, fake_adapter, _, _ = _setup_fakes(
        monkeypatch,
        bot_message=(
            "Primeiro parágrafo bem longo com conteúdo substancial suficiente para passar do limite mínimo de mescla.\n\n"
            "Segundo parágrafo também com texto extenso para garantir que cada bloco fique acima do threshold de sessenta caracteres.\n\n"
            "Terceiro parágrafo igualmente longo e descritivo, projetado para que o split realmente fragmente a mensagem em três chunks distintos."
        ),
    )
    asyncio.run(process_consolidated_message("oi", tenant_id="t1", from_number="5511999", session_id="s1", message_ids=["msg1"]))
    assert len(fake_adapter.sent_messages) >= 2
    for to, _text in fake_adapter.sent_messages:
        assert to == "5511999"


# ───── /reset ─────

def test_reset_command_clears_session_and_sends_confirmation(monkeypatch):
    """/reset chama clear_session, pula process_message e envia confirmação."""
    _, fake_adapter, calls, cleared = _setup_fakes(monkeypatch)
    asyncio.run(process_consolidated_message("/reset", tenant_id="t1", from_number="5511999", session_id="s1", message_ids=["msg1"]))
    assert len(cleared) == 1
    assert len(calls) == 0
    assert len(fake_adapter.sent_messages) == 1
    assert "reiniciada" in fake_adapter.sent_messages[0][1]


# ───── Silêncio quando bot_message vazio ─────

def test_empty_bot_message_does_not_send_anything(monkeypatch):
    """bot_message vazio não dispara send nem mark_as_read."""
    _, fake_adapter, _, _ = _setup_fakes(monkeypatch, bot_message="")
    asyncio.run(process_consolidated_message("oi", tenant_id="t1", from_number="5511999", session_id="s1", message_ids=["msg1"]))
    assert len(fake_adapter.sent_messages) == 0
    assert len(fake_adapter.marked_read_ids) == 0


# ───── Anti-eco ─────

def test_records_sent_message_for_anti_echo(monkeypatch):
    """Mensagem enviada é registrada no cache anti-eco (_is_echo_message)."""
    _setup_fakes(monkeypatch, bot_message="Resposta única!")
    assert webhooks._is_echo_message("Resposta única!") is False
    asyncio.run(process_consolidated_message("oi", tenant_id="t1", from_number="5511999", session_id="s1", message_ids=["msg1"]))
    assert webhooks._is_echo_message("Resposta única!") is True


# ───── Adapter ausente ─────

def test_returns_early_when_adapter_unavailable(monkeypatch):
    """_get_whatsapp_adapter retornando None aborta antes do process_message."""
    _, _, calls, _ = _setup_fakes(monkeypatch)
    monkeypatch.setattr(
        "app.api.webhooks._get_whatsapp_adapter", lambda t: None
    )
    asyncio.run(process_consolidated_message("oi", tenant_id="t1", from_number="5511999", session_id="s1", message_ids=["msg1"]))
    assert len(calls) == 0


# ───── Resposta obsoleta (supersede via generation) ─────

def test_stale_response_is_not_sent(monkeypatch):
    """generation desatualizada: graph é invocado, mas nada é enviado."""
    _, fake_adapter, calls, _ = _setup_fakes(monkeypatch, bot_message="Resposta velha")
    webhooks.message_buffer._generation["s1"] = 7  # chegou msg nova (gen 7)
    try:
        asyncio.run(
            process_consolidated_message(
                "oi",
                tenant_id="t1",
                from_number="5511999",
                session_id="s1",
                message_ids=["msg1"],
                generation=6,  # lote foi disparado na gen 6
            )
        )
        assert len(calls) == 1  # turno FOI processado (fica no checkpoint)
        assert len(fake_adapter.sent_messages) == 0  # mas nada foi enviado
        assert len(fake_adapter.marked_read_ids) == 0
    finally:
        webhooks.message_buffer._generation.pop("s1", None)


def test_current_generation_sends_normally(monkeypatch):
    """generation atual: fluxo normal de envio + mark_as_read de todos os ids."""
    _, fake_adapter, calls, _ = _setup_fakes(monkeypatch, bot_message="Olá!")
    webhooks.message_buffer._generation["s1"] = 3
    try:
        asyncio.run(
            process_consolidated_message(
                "oi\ntudo bem?",
                tenant_id="t1",
                from_number="5511999",
                session_id="s1",
                message_ids=["m1", "m2"],
                generation=3,
            )
        )
        assert len(fake_adapter.sent_messages) == 1
        assert fake_adapter.marked_read_ids == ["m1", "m2"]
    finally:
        webhooks.message_buffer._generation.pop("s1", None)


# ───── Defesa contra exceção ─────

def test_exception_in_process_message_is_logged_not_raised(monkeypatch):
    """Exception no process_message é capturada pelo try/except, não propaga."""
    _, fake_adapter, _, _ = _setup_fakes(monkeypatch, process_message_raises=True)
    asyncio.run(process_consolidated_message("oi", tenant_id="t1", from_number="5511999", session_id="s1", message_ids=["msg1"]))
    assert len(fake_adapter.sent_messages) == 0
