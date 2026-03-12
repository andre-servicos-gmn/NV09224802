"""
message_buffer_redis.py — buffer de mensagens com Redis

Estratégia:
  - Mensagens são armazenadas em uma lista Redis: buffer:{buffer_id}
  - buffer_id é um identificador composto (tenant:channel:session) para
    evitar colisões entre tenants que compartilham o mesmo número/telefone.
  - Um 'lock' Redis impede que múltiplos workers processem o mesmo buffer
  - Debounce: o worker espera silêncio de N segundos antes de processar
  - Um índice Redis (SET) rastreia buffer_ids ativos para que um sweeper
    em background possa descobrir e processar buffers órfãos após restarts.
"""
import asyncio
import hashlib
import json
import logging
import time
import uuid
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

import redis.exceptions as redis_exc

from app.core.redis_client import get_redis_async
from app.core.message_buffer import AsyncMessageBuffer

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 2.5
BUFFER_TTL = 300  # 5 minutos de TTL para chaves Redis
LOCK_TTL = 120    # 2 minutos de TTL para o lock
SWEEP_INTERVAL = 10  # Intervalo do sweeper em segundos
ACTIVE_BUFFERS_SET = "msgbuf:active_ids"  # Redis SET que indexa buffer_ids ativos

# Lua script that atomically enqueues a message with dedup check.
# KEYS: [1] buffer_key, [2] ts_key, [3] meta_key, [4] active_set, [5] dedup_key
# ARGV: [1] message_text, [2] timestamp, [3] meta_json, [4] buffer_id,
#        [5] buffer_ttl, [6] op_id
# Returns: 1 if enqueued, 0 if duplicate (op_id already seen)
_ENQUEUE_LUA = """
local dedup_key = KEYS[5]
local op_id     = ARGV[6]
local ttl       = tonumber(ARGV[5])

-- Dedup check: skip if this operation was already persisted
if redis.call('SISMEMBER', dedup_key, op_id) == 1 then
    return 0
end

-- Atomic enqueue: append message, refresh metadata, register active buffer
redis.call('RPUSH',   KEYS[1], ARGV[1])
redis.call('EXPIRE',  KEYS[1], ttl)
redis.call('SET',     KEYS[2], ARGV[2])
redis.call('EXPIRE',  KEYS[2], ttl)
redis.call('SET',     KEYS[3], ARGV[3])
redis.call('EXPIRE',  KEYS[3], ttl)
redis.call('SADD',    KEYS[4], ARGV[4])

-- Record op_id for dedup; expire set with buffer
redis.call('SADD',   dedup_key, op_id)
redis.call('EXPIRE', dedup_key, ttl)

return 1
"""


class EnqueueOutcome(str, Enum):
    """Result of an add_message() call."""
    CONFIRMED = "confirmed"   # Lua returned 1 — message is in Redis
    DUPLICATE = "duplicate"   # Lua returned 0 — op already seen (safe)
    FAILED    = "failed"      # ConnectionError — definitively not persisted
    UNKNOWN   = "unknown"     # TimeoutError — may or may not be persisted


class RedisMessageBuffer:
    """Buffer de mensagens com estado no Redis.
    
    Buffers são discoverable via um Redis SET (ACTIVE_BUFFERS_SET) para que
    qualquer worker (inclusive o background sweeper) possa processá-los.
    
    Enqueue é atômico via Lua script com dedup por op_id para evitar
    mensagens duplicadas em ambos Redis e fallback in-memory buffer.
    """
    
    def __init__(self, debounce_seconds: float = DEBOUNCE_SECONDS):
        self.debounce_seconds = debounce_seconds
        self._local_tasks: dict[str, asyncio.Task] = {}
        self._default_callback: Optional[Callable] = None
        self._sweeper_task: Optional[asyncio.Task] = None
        # In-process fallback buffer for when Redis is unhealthy.
        # Preserves debounce and serialization in degraded mode.
        self._fallback_buffer = AsyncMessageBuffer(debounce_seconds=debounce_seconds)
        # Cached Lua script SHA (registered on first use)
        self._enqueue_sha: Optional[str] = None

    def register_callback(self, callback: Callable) -> None:
        """Registra o callback padrão usado pelo sweeper para processar
        buffers órfãos. Deve ser chamado na inicialização do app."""
        self._default_callback = callback

    def _buffer_key(self, buffer_id: str) -> str:
        return f"msgbuf:{buffer_id}"

    def _timestamp_key(self, buffer_id: str) -> str:
        return f"msgts:{buffer_id}"

    def _lock_key(self, buffer_id: str) -> str:
        return f"msglk:{buffer_id}"

    def _meta_key(self, buffer_id: str) -> str:
        """Armazena metadados (args do callback) para o sweeper."""
        return f"msgmeta:{buffer_id}"

    def _dedup_key(self, buffer_id: str) -> str:
        """SET of operation IDs already persisted for this buffer."""
        return f"msgdedup:{buffer_id}"

    async def _get_enqueue_sha(self, r) -> str:
        """Register the Lua script on first use, cache the SHA."""
        if not self._enqueue_sha:
            self._enqueue_sha = await r.script_load(_ENQUEUE_LUA)
        return self._enqueue_sha

    async def add_message(
        self,
        buffer_id: str,
        message_text: str,
        process_callback: Callable,
        *args,
        message_id: str = "",
        **kwargs
    ) -> EnqueueOutcome:
        """Adiciona mensagem ao buffer Redis atomicamente via Lua script.
        
        Args:
            buffer_id: Composite key (e.g. 'tenant:channel:session') that
                       uniquely identifies the conversation buffer.
            message_id: Provider message ID used to derive a deterministic
                        idempotency key.  When a timeout makes the outcome
                        ambiguous the same key lets a retry be reconciled
                        instead of duplicating the message.
        
        Returns:
            EnqueueOutcome indicating whether the message was confirmed,
            is a duplicate, definitively failed, or has unknown status.
        """
        r = get_redis_async()
        if not r:
            logger.warning('[BUFFER-REDIS] Redis indisponível, usando fallback in-memory buffer')
            await self._fallback_buffer.add_message(
                buffer_id, message_text, process_callback, *args, **kwargs
            )
            return EnqueueOutcome.CONFIRMED
        
        # Deterministic idempotency key derived from the provider message ID.
        # A SHA-256 prefix keeps the key short while avoiding collisions.
        if message_id:
            op_id = f"msg:{hashlib.sha256(message_id.encode()).hexdigest()[:16]}"
        else:
            op_id = str(uuid.uuid4())

        meta = json.dumps(list(args), ensure_ascii=False)
        now_ts = str(time.time())

        try:
            sha = await self._get_enqueue_sha(r)
            result = await r.evalsha(
                sha,
                5,  # number of KEYS
                self._buffer_key(buffer_id),
                self._timestamp_key(buffer_id),
                self._meta_key(buffer_id),
                ACTIVE_BUFFERS_SET,
                self._dedup_key(buffer_id),
                # ARGV
                message_text,
                now_ts,
                meta,
                buffer_id,
                str(BUFFER_TTL),
                op_id,
            )
            if result == 0:
                logger.debug(f'[BUFFER-REDIS] Dedup: op_id {op_id} already seen for {buffer_id}')
                return EnqueueOutcome.DUPLICATE
        except redis_exc.NoScriptError:
            # Script cache flushed (e.g. after SCRIPT FLUSH), re-register
            self._enqueue_sha = None
            try:
                sha = await self._get_enqueue_sha(r)
                result = await r.evalsha(
                    sha, 5,
                    self._buffer_key(buffer_id),
                    self._timestamp_key(buffer_id),
                    self._meta_key(buffer_id),
                    ACTIVE_BUFFERS_SET,
                    self._dedup_key(buffer_id),
                    message_text, now_ts, meta, buffer_id, str(BUFFER_TTL), op_id,
                )
                if result == 0:
                    return EnqueueOutcome.DUPLICATE
            except redis_exc.ConnectionError as e:
                logger.warning(f'[BUFFER-REDIS] Redis ConnectionError on retry: {e}. Routing to fallback.')
                await self._fallback_buffer.add_message(
                    buffer_id, message_text, process_callback, *args, **kwargs
                )
                return EnqueueOutcome.FAILED
            except redis_exc.TimeoutError as e:
                logger.error(
                    f'[BUFFER-REDIS] Timeout on enqueue retry (unknown outcome) — '
                    f'NOT routing to fallback to avoid duplicate. op_id={op_id}'
                )
                return EnqueueOutcome.UNKNOWN
        except redis_exc.ConnectionError as e:
            # Definitive failure — Redis did NOT persist the message.
            logger.warning(f'[BUFFER-REDIS] Redis ConnectionError on add_message: {e}. Routing to fallback buffer.')
            await self._fallback_buffer.add_message(
                buffer_id, message_text, process_callback, *args, **kwargs
            )
            return EnqueueOutcome.FAILED
        except redis_exc.TimeoutError as e:
            # Ambiguous — Redis MAY have persisted the message.
            # Do NOT route to fallback to avoid duplicate processing.
            logger.error(
                f'[BUFFER-REDIS] Timeout on enqueue (unknown outcome) — '
                f'NOT routing to fallback to avoid duplicate. op_id={op_id} err={e}'
            )
            return EnqueueOutcome.UNKNOWN
        
        # Iniciar watcher local se não existe
        if buffer_id not in self._local_tasks or self._local_tasks[buffer_id].done():
            self._local_tasks[buffer_id] = asyncio.create_task(
                self._watch_and_process(buffer_id, process_callback, *args, **kwargs)
            )

        return EnqueueOutcome.CONFIRMED

    async def _watch_and_process(
        self, buffer_id: str, callback: Callable, *args, **kwargs
    ):
        """Watcher: aguarda silêncio e tenta adquirir lock para processar."""
        r = get_redis_async()
        if not r:
            logger.warning('[BUFFER-REDIS] Redis indisponível no watcher, abortando')
            return  # Messages stay in Redis for sweeper; no in-memory fallback needed here
        
        try:
            while True:
                ts_str = await r.get(self._timestamp_key(buffer_id))
                if not ts_str:
                    return
                    
                elapsed = time.time() - float(ts_str)
                remaining = self.debounce_seconds - elapsed
                
                if remaining > 0.05:
                    await asyncio.sleep(remaining)
                    continue
                    
                break
                
            # Tentar adquirir lock atômico
            lock_val = str(uuid.uuid4())
            acquired = await r.set(
                self._lock_key(buffer_id), lock_val,
                nx=True,  # NX = só seta se não existe
                ex=LOCK_TTL
            )
            
            if not acquired:
                return  # Outro worker já está processando

            # Clear local task gate BEFORE running callback so new
            # messages arriving during processing can start a fresh watcher.
            self._local_tasks.pop(buffer_id, None)
                
            try:
                # Coletar e limpar mensagens
                messages = await r.lrange(self._buffer_key(buffer_id), 0, -1)
                await r.delete(self._buffer_key(buffer_id))
                await r.delete(self._timestamp_key(buffer_id))
                await r.delete(self._meta_key(buffer_id))
                await r.delete(self._dedup_key(buffer_id))
                await r.srem(ACTIVE_BUFFERS_SET, buffer_id)
                
                if messages:
                    full_text = '. '.join(m.strip() for m in messages)
                    logger.info(f'[BUFFER-REDIS] Processando {len(messages)} msgs de {buffer_id}')
                    await callback(full_text, *args, **kwargs)
            finally:
                # Liberar lock somente se ainda é nosso
                try:
                    current = await r.get(self._lock_key(buffer_id))
                    if current == lock_val:
                        await r.delete(self._lock_key(buffer_id))
                except Exception:
                    pass  # Falha ao liberar lock — TTL cuidará
        except (redis_exc.ConnectionError, redis_exc.TimeoutError) as e:
            logger.error(f'[BUFFER-REDIS] Redis connection/timeout in watcher for {buffer_id}: {e}')
            # Only release the lock — do NOT delete buffer/timestamp keys
            # so queued messages survive for a future retry attempt.
            try:
                r2 = get_redis_async()
                if r2:
                    await r2.delete(self._lock_key(buffer_id))
            except Exception:
                pass  # Lock TTL will expire on its own
        except Exception as e:
            logger.error(f'[BUFFER-REDIS] Unexpected error in watcher for {buffer_id}: {e}', exc_info=True)

    # ── BACKGROUND SWEEPER ─────────────────────────────────────────

    async def start_sweeper(self) -> None:
        """Inicia o background sweeper que descobre e processa buffers órfãos.
        Chamado no lifespan startup do FastAPI."""
        if self._sweeper_task and not self._sweeper_task.done():
            return
        self._sweeper_task = asyncio.create_task(self._sweeper_loop())
        logger.info('[SWEEPER] Background buffer sweeper iniciado')

    async def stop_sweeper(self) -> None:
        """Para o background sweeper. Chamado no lifespan shutdown."""
        if self._sweeper_task and not self._sweeper_task.done():
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except asyncio.CancelledError:
                pass
            logger.info('[SWEEPER] Background buffer sweeper parado')

    async def _sweeper_loop(self) -> None:
        """Loop contínuo que escaneia Redis por buffers due e os processa."""
        while True:
            try:
                await asyncio.sleep(SWEEP_INTERVAL)
                await self.sweep_due_buffers()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f'[SWEEPER] Error in sweep loop: {e}', exc_info=True)
                await asyncio.sleep(SWEEP_INTERVAL)

    async def sweep_due_buffers(self) -> int:
        """Escaneia o índice de buffers ativos e processa os que estão due.
        
        Returns:
            Número de buffers processados.
        """
        if not self._default_callback:
            return 0

        r = get_redis_async()
        if not r:
            return 0

        processed = 0
        try:
            # Obter todos os buffer_ids registrados
            active_ids = await r.smembers(ACTIVE_BUFFERS_SET)
            if not active_ids:
                return 0

            now = time.time()

            for buffer_id in active_ids:
                try:
                    # Verificar se o buffer existe e está due
                    ts_str = await r.get(self._timestamp_key(buffer_id))
                    buf_exists = await r.exists(self._buffer_key(buffer_id))

                    if not buf_exists:
                        # Buffer já foi consumido — limpar índice
                        await r.srem(ACTIVE_BUFFERS_SET, buffer_id)
                        await r.delete(self._timestamp_key(buffer_id))
                        await r.delete(self._meta_key(buffer_id))
                        await r.delete(self._dedup_key(buffer_id))
                        continue

                    if not ts_str:
                        # Sem timestamp mas com buffer — considerar due
                        elapsed = self.debounce_seconds + 1
                    else:
                        elapsed = now - float(ts_str)

                    if elapsed < self.debounce_seconds:
                        continue  # Ainda não está due (debounce ativo)

                    # Skip se já tem um watcher local ativo para este buffer
                    task = self._local_tasks.get(buffer_id)
                    if task and not task.done():
                        continue

                    # Tentar adquirir lock
                    lock_val = str(uuid.uuid4())
                    acquired = await r.set(
                        self._lock_key(buffer_id), lock_val,
                        nx=True, ex=LOCK_TTL
                    )
                    if not acquired:
                        continue  # Outro worker processando

                    try:
                        messages = await r.lrange(self._buffer_key(buffer_id), 0, -1)
                        meta_raw = await r.get(self._meta_key(buffer_id))
                        await r.delete(self._buffer_key(buffer_id))
                        await r.delete(self._timestamp_key(buffer_id))
                        await r.delete(self._meta_key(buffer_id))
                        await r.delete(self._dedup_key(buffer_id))
                        await r.srem(ACTIVE_BUFFERS_SET, buffer_id)

                        if messages:
                            full_text = '. '.join(m.strip() for m in messages)
                            # Recuperar args do callback dos metadados
                            cb_args = json.loads(meta_raw) if meta_raw else []
                            logger.info(
                                f'[SWEEPER] Processando {len(messages)} msgs órfãs de {buffer_id}'
                            )
                            try:
                                await self._default_callback(full_text, *cb_args)
                            except Exception as cb_err:
                                logger.error(f'[SWEEPER] Callback error for {buffer_id}: {cb_err}', exc_info=True)
                            processed += 1
                    finally:
                        try:
                            current = await r.get(self._lock_key(buffer_id))
                            if current == lock_val:
                                await r.delete(self._lock_key(buffer_id))
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning(f'[SWEEPER] Error processing buffer {buffer_id}: {e}')
        except (redis_exc.ConnectionError, redis_exc.TimeoutError) as e:
            logger.warning(f'[SWEEPER] Redis unavailable during sweep: {e}')
        except Exception as e:
            logger.error(f'[SWEEPER] Unexpected error: {e}', exc_info=True)

        return processed
