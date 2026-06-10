"""Message buffer (debounce) para rajadas de mensagens do WhatsApp.

Usuários de WhatsApp frequentemente enviam múltiplas mensagens curtas em
sequência ("oi" / "queria saber" / "do meu pedido"). Este buffer consolida
a rajada e só dispara o processamento após `debounce_seconds` de silêncio,
com teto máximo de espera (`max_wait_seconds`) contado a partir da primeira
mensagem do lote — assim um cliente que digita continuamente não fica sem
resposta indefinidamente.

Garantias:
- Um watcher por sessão; processamento estritamente serializado por sessão
  (lock por sessão — lotes nunca se sobrepõem).
- Cada add_message incrementa a "generation" da sessão. O callback recebe a
  generation do lote disparado; antes de ENVIAR a resposta, o caller deve
  conferir `is_current(session_id, generation)` — se chegou mensagem nova
  durante o processamento (ex: durante a chamada de LLM), a resposta está
  obsoleta e não deve ser enviada. O próximo lote responde com o contexto
  completo do checkpoint.

Limitação conhecida: todo o estado vive na memória do processo. Funciona
com 1 worker uvicorn; para múltiplos workers/réplicas, migrar para Redis
(ver core/redis_client.py — padrão ZSET + consumer).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class _BufferedItem:
    text: str
    message_id: str | None = None


@dataclass
class _SessionBatch:
    """Lote de mensagens pendentes de uma sessão."""

    callback: Callable[..., Coroutine]
    kwargs: dict[str, Any]
    items: list[_BufferedItem] = field(default_factory=list)
    first_at: float = 0.0
    last_at: float = 0.0


class AsyncMessageBuffer:
    def __init__(
        self,
        debounce_seconds: float = 2.5,
        max_wait_seconds: float = 10.0,
        processing_timeout: float = 60.0,
        max_tracked_sessions: int = 10_000,
    ):
        self.debounce_seconds = debounce_seconds
        self.max_wait_seconds = max_wait_seconds
        self.processing_timeout = processing_timeout
        self.max_tracked_sessions = max_tracked_sessions

        self._batches: dict[str, _SessionBatch] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._generation: dict[str, int] = {}
        self._processing_locks: dict[str, asyncio.Lock] = {}
        self._processing: set[str] = set()
        self._lock = asyncio.Lock()  # protege as estruturas internas

    # ── Generation (detecção de resposta obsoleta) ──────────────────

    def current_generation(self, session_id: str) -> int:
        return self._generation.get(session_id, 0)

    def is_current(self, session_id: str, generation: int) -> bool:
        """True se nenhuma mensagem nova chegou desde o disparo do lote."""
        return self._generation.get(session_id, 0) == generation

    # ── Entrada de mensagens ─────────────────────────────────────────

    async def add_message(
        self,
        session_id: str,
        text: str,
        message_id: str | None = None,
        process_callback: Callable[..., Coroutine] | None = None,
        **callback_kwargs,
    ) -> bool:
        """Adiciona mensagem ao lote da sessão e garante um watcher ativo.

        O callback será invocado como:
            callback(full_text, session_id=..., message_ids=[...],
                     generation=..., **callback_kwargs)

        Retorna True se esta mensagem INICIOU um lote novo (útil pra sinais
        imediatos como "digitando..." antes do debounce vencer).
        """
        if process_callback is None:
            raise ValueError("process_callback é obrigatório")

        now = time.time()
        async with self._lock:
            self._prune_idle_sessions()

            batch = self._batches.get(session_id)
            is_new_batch = batch is None
            if batch is None:
                batch = _SessionBatch(
                    callback=process_callback,
                    kwargs=callback_kwargs,
                    first_at=now,
                )
                self._batches[session_id] = batch

            batch.items.append(_BufferedItem(text=text, message_id=message_id))
            batch.last_at = now
            # Mantém callback/kwargs mais recentes (constantes na prática).
            batch.callback = process_callback
            batch.kwargs = callback_kwargs

            self._generation[session_id] = self._generation.get(session_id, 0) + 1

            logger.info(
                f"[BUFFER] +1 msg p/ {session_id[-4:]} "
                f"(lote: {len(batch.items)}, gen: {self._generation[session_id]})"
            )

            task = self._tasks.get(session_id)
            if task is None or task.done():
                self._tasks[session_id] = asyncio.create_task(
                    self._watch_and_process(session_id)
                )

        return is_new_batch

    # ── Watcher ──────────────────────────────────────────────────────

    async def _watch_and_process(self, session_id: str):
        try:
            # Fase 1: espera silêncio (debounce) ou o teto máximo (max_wait).
            while True:
                async with self._lock:
                    batch = self._batches.get(session_id)
                    if batch is None:
                        return  # lote já foi consumido por outro watcher
                    fire_at = min(
                        batch.last_at + self.debounce_seconds,
                        batch.first_at + self.max_wait_seconds,
                    )
                remaining = fire_at - time.time()
                if remaining <= 0.05:
                    break
                await asyncio.sleep(remaining)

            async with self._lock:
                session_lock = self._processing_locks.setdefault(
                    session_id, asyncio.Lock()
                )

            # Fase 2: processamento serializado por sessão.
            try:
                async with asyncio.timeout(self.processing_timeout):
                    async with session_lock:
                        async with self._lock:
                            # Pop atômico: mensagens que chegaram enquanto
                            # esperávamos o lock entram neste lote.
                            batch = self._batches.pop(session_id, None)
                            self._tasks.pop(session_id, None)
                            gen_at_fire = self._generation.get(session_id, 0)
                            if batch is not None:
                                self._processing.add(session_id)

                        if batch is None or not batch.items:
                            return

                        try:
                            full_text = "\n".join(
                                it.text.strip()
                                for it in batch.items
                                if it.text and it.text.strip()
                            )
                            message_ids = [
                                it.message_id for it in batch.items if it.message_id
                            ]
                            logger.info(
                                f"[BUFFER] Disparando {session_id[-4:]}: "
                                f"{len(batch.items)} msgs (gen {gen_at_fire})"
                            )
                            await batch.callback(
                                full_text,
                                session_id=session_id,
                                message_ids=message_ids,
                                generation=gen_at_fire,
                                **batch.kwargs,
                            )
                        except Exception as e:
                            logger.error(
                                f"[BUFFER] Callback falhou p/ {session_id[-4:]}: {e}",
                                exc_info=True,
                            )
                        finally:
                            # Sem await aqui: precisa rodar mesmo durante
                            # cancelamento (timeout).
                            self._processing.discard(session_id)

            except TimeoutError:
                logger.error(
                    f"⚠️ [BUFFER] Timeout ({self.processing_timeout}s) "
                    f"processando {session_id[-4:]}"
                )
                self._processing.discard(session_id)
                # Não limpa _batches/_tasks: se mensagens novas chegaram
                # durante o processamento travado, pertencem a um lote novo
                # com watcher próprio.

        except Exception as e:
            logger.error(
                f"[BUFFER] Watcher falhou p/ {session_id[-4:]}: {e}", exc_info=True
            )
            self._processing.discard(session_id)
            # Mensagens ainda em _batches são recuperadas pelo próximo
            # add_message (verá a task .done() e criará watcher novo).

    # ── Manutenção ───────────────────────────────────────────────────

    def _prune_idle_sessions(self):
        """Evita crescimento sem limite de _generation/_processing_locks.

        Remove apenas sessões totalmente ociosas (sem lote pendente, sem
        watcher, sem processamento em andamento e lock livre). Para essas
        não existe is_current() pendente, então zerar a generation é seguro.
        Chamar sob self._lock.
        """
        if len(self._generation) <= self.max_tracked_sessions:
            return
        for sid in list(self._generation.keys()):
            if sid in self._batches or sid in self._tasks or sid in self._processing:
                continue
            lock = self._processing_locks.get(sid)
            if lock is not None and lock.locked():
                continue
            self._generation.pop(sid, None)
            self._processing_locks.pop(sid, None)


# Global singleton
message_buffer = AsyncMessageBuffer(debounce_seconds=2.5, max_wait_seconds=10.0)
