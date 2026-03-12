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
        buffer_id: str, 
        message_text: str, 
        process_callback: Callable[[str, Any], Coroutine], 
        *args,
        **kwargs
    ):
        """Add a message to the buffer and ensure a watcher task is running.
        
        Args:
            buffer_id: Composite key (e.g. 'tenant:channel:session') that
                       uniquely identifies the conversation buffer.
        """
        async with self._lock:
            if buffer_id not in self._buffers:
                self._buffers[buffer_id] = []
            
            self._buffers[buffer_id].append(message_text)
            self._last_update[buffer_id] = time.time()
            
            logger.info(f"[BUFFER] Added msg for {buffer_id}. Size: {len(self._buffers[buffer_id])}")
            
            # Start watcher if not running
            if buffer_id not in self._tasks or self._tasks[buffer_id].done():
                self._tasks[buffer_id] = asyncio.create_task(
                    self._watch_and_process(buffer_id, process_callback, *args, **kwargs)
                )
                logger.info(f"[BUFFER] Started watcher task for {buffer_id}")

    async def _get_processing_lock(self, buffer_id: str) -> asyncio.Lock:
        """Get or create a lock for the buffer."""
        async with self._lock:
            if buffer_id not in self._processing_locks:
                self._processing_locks[buffer_id] = asyncio.Lock()
            return self._processing_locks[buffer_id]

    async def _watch_and_process(self, buffer_id: str, callback: Callable, *args, **kwargs):
        """Loop that sleeps until the silence duration is met, then executes securely."""
        try:
            while True:
                # Check silence duration
                last_ts = self._last_update.get(buffer_id, 0)
                now = time.time()
                elapsed = now - last_ts
                remaining = self.debounce_seconds - elapsed
                
                if remaining <= 0.05:
                    # Silence achieved!
                    break
                
                await asyncio.sleep(remaining)
            
            # Processing Phase
            session_lock = await self._get_processing_lock(buffer_id)
            
            try:
                # Adjustment 4: Add timeout
                async with asyncio.timeout(60.0):  # 60s timeout
                    async with session_lock:
                        async with self._lock:
                            messages = self._buffers.pop(buffer_id, [])
                            # Clear task gate BEFORE callback so new messages
                            # arriving during processing can start a fresh watcher.
                            self._tasks.pop(buffer_id, None)
                            self._last_update.pop(buffer_id, None)
                        
                        if messages:
                            logger.info(f"[BUFFER] FIRING {buffer_id} with {len(messages)} messages")
                            
                            full_text = ". ".join(msg.strip() for msg in messages)
                            
                            # Execute callback
                            try:
                                await callback(full_text, *args, **kwargs)
                            except Exception as e:
                                logger.error(f"Callback error for {buffer_id}: {e}")
            
            except asyncio.TimeoutError:
                logger.error(f"⚠️ Processing timeout (60s) for {buffer_id}")
                # Clean resources
                async with self._lock:
                    self._buffers.pop(buffer_id, None)
                    self._tasks.pop(buffer_id, None)
                    self._last_update.pop(buffer_id, None)
                    self._processing_locks.pop(buffer_id, None)
                
        except Exception as e:
            logger.error(f"Error in buffer watcher for {buffer_id}: {e}")
            async with self._lock:
                self._buffers.pop(buffer_id, None)
                self._tasks.pop(buffer_id, None)
                self._last_update.pop(buffer_id, None)

# Global singleton
message_buffer = AsyncMessageBuffer(debounce_seconds=2.5)
