"""Message buffer for handling burst messages.
Usuários de WhatsApp frequentemente enviam múltiplas mensagens curtas em sequência.
Este buffer consolida essas mensagens antes de processar, evitando múltiplas respostas.
"""
import asyncio
import time
import logging
from typing import Callable, Any, Coroutine

logger = logging.getLogger(__name__)


class AsyncMessageBuffer:
    """
    Buffers incoming messages for a short window to handle "burst" messages.
    Uses a single watcher task loop per session to avoid race conditions.
    Enforces STRICT serialization using locks to prevent state corruption.
    """
    
    def __init__(self, debounce_seconds: float = 2.5):
        self.debounce_seconds = debounce_seconds
        self._buffers: dict[str, list[str]] = {}
        self._last_update: dict[str, float] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()  # To protect internal dicts
        
        # Lock to ensure only ONE callback runs at a time per session
        self._processing_locks: dict[str, asyncio.Lock] = {} 

    async def add_message(
        self, 
        session_id: str, 
        message_text: str, 
        process_callback: Callable[[str, Any], Coroutine], 
        *args,
        **kwargs
    ):
        """Add a message to the buffer and ensure a watcher task is running."""
        async with self._lock:
            # Adjustment: Intelligent logic check if message exists during processing handled in watcher
            if session_id not in self._buffers:
                self._buffers[session_id] = []
            
            self._buffers[session_id].append(message_text)
            self._last_update[session_id] = time.time()
            
            logger.info(f"[BUFFER] Added msg for {session_id[-4:]}. Size: {len(self._buffers[session_id])}")
            
            # Start watcher if not running
            if session_id not in self._tasks or self._tasks[session_id].done():
                self._tasks[session_id] = asyncio.create_task(
                    self._watch_and_process(session_id, process_callback, *args, **kwargs)
                )
                logger.info(f"[BUFFER] Started watcher task for {session_id[-4:]}")

    async def _get_processing_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create a lock for the session."""
        async with self._lock:
            if session_id not in self._processing_locks:
                self._processing_locks[session_id] = asyncio.Lock()
            return self._processing_locks[session_id]

    async def _watch_and_process(self, session_id: str, callback: Callable, *args, **kwargs):
        """Loop that sleeps until the silence duration is met, then executes securely."""
        try:
            while True:
                # Check silence duration
                last_ts = self._last_update.get(session_id, 0)
                now = time.time()
                elapsed = now - last_ts
                remaining = self.debounce_seconds - elapsed
                
                if remaining <= 0.05:
                    # Silence achieved!
                    break
                
                await asyncio.sleep(remaining)
            
            # Processing Phase
            session_lock = await self._get_processing_lock(session_id)
            
            try:
                # Adjustment 4: Add timeout
                async with asyncio.timeout(60.0):  # 60s timeout
                    async with session_lock:
                        async with self._lock:
                            # Re-check if new messages arrived while we were waiting for lock
                            # Note: In this simple design, we just process what we have. 
                            # The strict serialization means next watcher will pick up new stuffs if any added.
                            messages = self._buffers.pop(session_id, [])
                            self._tasks.pop(session_id, None)
                            self._last_update.pop(session_id, None)
                        
                        if messages:
                            logger.info(f"[BUFFER] FIRING {session_id[-4:]} with {len(messages)} messages")
                            
                            full_text = ". ".join(msg.strip() for msg in messages)
                            
                            # Execute callback
                            try:
                                await callback(full_text, *args, **kwargs)
                            except Exception as e:
                                logger.error(f"Callback error for {session_id}: {e}")
            
            except asyncio.TimeoutError:
                logger.error(f"⚠️ Processing timeout (60s) for {session_id[-4:]}")
                # Clean resources
                async with self._lock:
                    self._buffers.pop(session_id, None)
                    self._tasks.pop(session_id, None)
                    self._last_update.pop(session_id, None)
                    self._processing_locks.pop(session_id, None)
                
        except Exception as e:
            logger.error(f"Error in buffer watcher for {session_id}: {e}")
            async with self._lock:
                self._buffers.pop(session_id, None)
                self._tasks.pop(session_id, None)
                self._last_update.pop(session_id, None)

# Global singleton
message_buffer = AsyncMessageBuffer(debounce_seconds=2.5)
