"""
message_buffer_redis.py — buffer de mensagens com Redis

Estratégia:
  - Mensagens são armazenadas em uma lista Redis: buffer:{session_id}
  - Um 'lock' Redis impede que múltiplos workers processem o mesmo buffer
  - Debounce: o worker espera silêncio de N segundos antes de processar
"""
import asyncio
import json
import logging
import time
from typing import Any, Callable, Coroutine
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 2.5
BUFFER_TTL = 300  # 5 minutos de TTL para chaves Redis
LOCK_TTL = 120    # 2 minutos de TTL para o lock

class RedisMessageBuffer:
    """Buffer de mensagens com estado no Redis."""
    
    def __init__(self, redis_url: str, debounce_seconds: float = DEBOUNCE_SECONDS):
        self.redis_url = redis_url
        self.debounce_seconds = debounce_seconds
        self._redis: aioredis.Redis = None
        self._local_tasks: dict[str, asyncio.Task] = {}

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(
                self.redis_url, 
                decode_responses=True,
                health_check_interval=30,
                retry_on_timeout=True
            )
        return self._redis

    def _buffer_key(self, session_id: str) -> str:
        return f"msgbuf:{session_id}"

    def _timestamp_key(self, session_id: str) -> str:
        return f"msgts:{session_id}"

    def _lock_key(self, session_id: str) -> str:
        return f"msglk:{session_id}"

    async def add_message(
        self,
        session_id: str,
        message_text: str,
        process_callback: Callable,
        *args,
        **kwargs
    ):
        """Adiciona mensagem ao buffer Redis e inicia watcher local."""
        r = await self._get_redis()
        
        # Empurrar mensagem para lista Redis
        await r.rpush(self._buffer_key(session_id), message_text)
        await r.expire(self._buffer_key(session_id), BUFFER_TTL)
        
        # Atualizar timestamp da última mensagem
        await r.set(self._timestamp_key(session_id), str(time.time()))
        await r.expire(self._timestamp_key(session_id), BUFFER_TTL)
        
        # Iniciar watcher local se não existe
        if session_id not in self._local_tasks or self._local_tasks[session_id].done():
            self._local_tasks[session_id] = asyncio.create_task(
                self._watch_and_process(session_id, process_callback, *args, **kwargs)
            )

    async def _watch_and_process(
        self, session_id: str, callback: Callable, *args, **kwargs
    ):
        """Watcher: aguarda silêncio e tenta adquirir lock para processar."""
        r = await self._get_redis()
        
        while True:
            ts_str = await r.get(self._timestamp_key(session_id))
            if not ts_str:
                return
                
            elapsed = time.time() - float(ts_str)
            remaining = self.debounce_seconds - elapsed
            
            if remaining > 0.05:
                await asyncio.sleep(remaining)
                continue
                
            break
            
        # Tentar adquirir lock atômico
        import uuid
        lock_val = str(uuid.uuid4())
        acquired = await r.set(
            self._lock_key(session_id), lock_val,
            nx=True,  # NX = só seta se não existe
            ex=LOCK_TTL
        )
        
        if not acquired:
            return  # Outro worker já está processando
            
        try:
            # Coletar e limpar mensagens
            messages = await r.lrange(self._buffer_key(session_id), 0, -1)
            await r.delete(self._buffer_key(session_id))
            await r.delete(self._timestamp_key(session_id))
            
            if messages:
                full_text = '. '.join(m.strip() for m in messages)
                logger.info(f'[BUFFER-REDIS] Processando {len(messages)} msgs de {session_id[-4:]}')
                await callback(full_text, *args, **kwargs)
        finally:
            # Liberar lock somente se ainda é nosso
            current = await r.get(self._lock_key(session_id))
            if current == lock_val:
                await r.delete(self._lock_key(session_id))
