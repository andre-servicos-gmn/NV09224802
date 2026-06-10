"""Suite do AsyncMessageBuffer (debounce de rajadas WhatsApp).

Cada teste cria um buffer próprio com timings curtos (evita interferência
do singleton global e de event loops distintos entre testes). Margens
generosas nos sleeps pra não flakar em máquina lenta/Windows.
"""

import asyncio
import time

from app.core.message_buffer import AsyncMessageBuffer


class _Recorder:
    """Callback fake que registra cada disparo do buffer."""

    def __init__(self, delay: float = 0.0):
        self.calls: list[dict] = []
        self._delay = delay

    async def __call__(self, text, *, session_id, message_ids, generation, **kwargs):
        if self._delay:
            await asyncio.sleep(self._delay)
        self.calls.append(
            {
                "at": time.time(),
                "text": text,
                "session_id": session_id,
                "message_ids": message_ids,
                "generation": generation,
                "kwargs": kwargs,
            }
        )


# ───── Consolidação de rajada ─────

def test_burst_consolidates_into_single_callback():
    """3 mensagens em rajada → 1 callback com texto unido por \\n e todos os ids."""
    async def run():
        buf = AsyncMessageBuffer(debounce_seconds=0.15)
        rec = _Recorder()
        await buf.add_message("s1", "oi", message_id="m1", process_callback=rec, tenant_id="t1")
        await buf.add_message("s1", "queria saber", message_id="m2", process_callback=rec, tenant_id="t1")
        await buf.add_message("s1", "do meu pedido", message_id="m3", process_callback=rec, tenant_id="t1")
        await asyncio.sleep(0.5)

        assert len(rec.calls) == 1
        call = rec.calls[0]
        assert call["text"] == "oi\nqueria saber\ndo meu pedido"
        assert call["message_ids"] == ["m1", "m2", "m3"]
        assert call["session_id"] == "s1"
        assert call["kwargs"] == {"tenant_id": "t1"}

    asyncio.run(run())


def test_debounce_resets_on_each_message():
    """Timer reinicia a cada mensagem: só dispara após silêncio real."""
    async def run():
        buf = AsyncMessageBuffer(debounce_seconds=0.25)
        rec = _Recorder()
        await buf.add_message("s1", "a", process_callback=rec)
        await asyncio.sleep(0.15)
        await buf.add_message("s1", "b", process_callback=rec)
        # 0.3s desde a 1ª msg (> debounce), mas só 0.15s desde a última.
        await asyncio.sleep(0.15)
        assert len(rec.calls) == 0
        await asyncio.sleep(0.4)
        assert len(rec.calls) == 1
        assert rec.calls[0]["text"] == "a\nb"

    asyncio.run(run())


def test_sessions_are_independent():
    """Sessões diferentes têm lotes e disparos independentes."""
    async def run():
        buf = AsyncMessageBuffer(debounce_seconds=0.1)
        rec = _Recorder()
        await buf.add_message("s1", "msg s1", process_callback=rec)
        await buf.add_message("s2", "msg s2", process_callback=rec)
        await asyncio.sleep(0.4)
        assert len(rec.calls) == 2
        sessions = {c["session_id"]: c["text"] for c in rec.calls}
        assert sessions == {"s1": "msg s1", "s2": "msg s2"}

    asyncio.run(run())


# ───── max_wait ─────

def test_max_wait_fires_despite_continuous_typing():
    """Mensagens contínuas (intervalo < debounce) não adiam o disparo pra sempre."""
    async def run():
        buf = AsyncMessageBuffer(debounce_seconds=0.3, max_wait_seconds=0.6)
        rec = _Recorder()
        start = time.time()
        # 10 mensagens a cada 0.1s — sem max_wait, nunca haveria silêncio de 0.3s.
        for i in range(10):
            await buf.add_message("s1", f"m{i}", process_callback=rec)
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.6)  # deixa o lote residual disparar também

        assert len(rec.calls) >= 1
        # Primeiro disparo perto do teto (0.6s), não no fim do fluxo (1s+).
        assert rec.calls[0]["at"] - start < 0.95

    asyncio.run(run())


# ───── Generation / resposta obsoleta ─────

def test_generation_flags_stale_response():
    """Mensagem nova durante o processamento invalida a resposta em curso."""
    async def run():
        buf = AsyncMessageBuffer(debounce_seconds=0.1)
        results = []

        async def slow_cb(text, *, session_id, message_ids, generation, **kwargs):
            await asyncio.sleep(0.3)  # simula chamada de LLM lenta
            results.append((text, buf.is_current(session_id, generation)))

        await buf.add_message("s1", "quero a pochete", process_callback=slow_cb)
        await asyncio.sleep(0.2)  # debounce venceu; callback está "no LLM"
        await buf.add_message("s1", "na verdade quero a mochila", process_callback=slow_cb)
        await asyncio.sleep(1.2)

        assert len(results) == 2
        text1, current1 = results[0]
        assert "pochete" in text1
        assert current1 is False  # obsoleta: chegou msg nova durante o processamento
        text2, current2 = results[1]
        assert "mochila" in text2
        assert current2 is True

    asyncio.run(run())


# ───── Serialização por sessão ─────

def test_processing_is_serialized_per_session():
    """Dois lotes da mesma sessão nunca processam em paralelo."""
    async def run():
        buf = AsyncMessageBuffer(debounce_seconds=0.1)
        spans = []

        async def cb(text, **kwargs):
            start = time.time()
            await asyncio.sleep(0.25)
            spans.append((start, time.time()))

        await buf.add_message("s1", "lote1", process_callback=cb)
        await asyncio.sleep(0.18)  # lote1 disparou e está processando
        await buf.add_message("s1", "lote2", process_callback=cb)
        await asyncio.sleep(1.0)

        assert len(spans) == 2
        # O segundo só começa depois do primeiro terminar.
        assert spans[1][0] >= spans[0][1]

    asyncio.run(run())


# ───── is_new_batch ─────

def test_add_message_reports_new_batch():
    """True na 1ª mensagem do lote, False nas seguintes, True após disparo."""
    async def run():
        buf = AsyncMessageBuffer(debounce_seconds=0.1)

        async def cb(text, **kwargs):
            pass

        assert await buf.add_message("s1", "a", process_callback=cb) is True
        assert await buf.add_message("s1", "b", process_callback=cb) is False
        await asyncio.sleep(0.3)  # lote disparado
        assert await buf.add_message("s1", "c", process_callback=cb) is True
        await asyncio.sleep(0.3)

    asyncio.run(run())


# ───── Resiliência ─────

def test_callback_exception_does_not_break_next_batch():
    """Exception no callback não impede o lote seguinte de processar."""
    async def run():
        buf = AsyncMessageBuffer(debounce_seconds=0.1)
        ok_calls = []

        async def failing_cb(text, **kwargs):
            raise RuntimeError("boom")

        async def ok_cb(text, **kwargs):
            ok_calls.append(text)

        await buf.add_message("s1", "explode", process_callback=failing_cb)
        await asyncio.sleep(0.3)
        await buf.add_message("s1", "funciona", process_callback=ok_cb)
        await asyncio.sleep(0.3)

        assert ok_calls == ["funciona"]

    asyncio.run(run())
