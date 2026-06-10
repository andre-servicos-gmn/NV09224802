"""
Webhook handlers for e-commerce platform integrations.

Receives product events from platforms (Shopify, WooCommerce, etc.) and
syncs them to the RAG vector store.

Also handles WhatsApp webhooks via Evolution API.

Security measures:
- HMAC signature validation (timing-safe)
- Tenant existence and active status verification
- Rate limiting per tenant
- Secure logging (no sensitive data exposure)
"""

import logging
import os
import time
import re
import asyncio
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.adapters.shopify_adapter import ShopifyAdapter
from app.adapters.evolution_adapter import EvolutionAdapter
from app.adapters.whatsapp_base import WhatsAppAdapterBase
from app.core.tenancy import TenantRegistry
from app.sync.sync_service import SyncService
from app.core.message_buffer import message_buffer
from app.core.turn_processor import process_message
from app.graphs.graph import clear_session


# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])



# Simple in-memory rate limiter
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 100  # per tenant per window

# Caches for loop prevention (Anti-Echo)
SENT_MESSAGE_HASHES: list[tuple[float, int]] = []
PROCESSED_MESSAGE_IDS: set[str] = set()
_processed_ids_list: list[str] = []
MAX_PROCESSED_IDS = 1000


def _check_rate_limit(tenant_id: str) -> bool:
    """Check if tenant is within rate limits."""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    
    # Clean old entries
    _rate_limit_store[tenant_id] = [
        t for t in _rate_limit_store[tenant_id] if t > window_start
    ]
    
    # Check limit
    if len(_rate_limit_store[tenant_id]) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    
    # Record request
    _rate_limit_store[tenant_id].append(now)
    return True


def _get_tenant_credentials(tenant_id: str) -> Optional[dict]:
    """Get tenant credentials from registry."""
    try:
        registry = TenantRegistry()
        tenant = registry.get(tenant_id, use_cache=False)  # No cache for security
        
        if not tenant.active:
            return None
            
        return {
            "tenant_uuid": tenant.uuid,
            "store_domain": tenant.store_domain,
            "access_token": tenant.shopify_access_token,
            "api_version": tenant.shopify_api_version,
            "webhook_secret": getattr(tenant, "webhook_secret", None),
        }
    except ValueError:
        return None


# --- WhatsApp Helper Functions ---

def _check_deduplication(message_id: str) -> bool:
    """Check if message ID was already processed. Returns True if duplicate."""
    if not message_id:
        return False
    if message_id in PROCESSED_MESSAGE_IDS:
        return True
    
    PROCESSED_MESSAGE_IDS.add(message_id)
    _processed_ids_list.append(message_id)
    
    if len(_processed_ids_list) > MAX_PROCESSED_IDS:
        removed = _processed_ids_list.pop(0)
        PROCESSED_MESSAGE_IDS.discard(removed)
        
    return False


def _normalize_for_loop_check(text: str) -> str:
    """Normalize text for echo detection - remove emojis, punctuation, spaces. (Adjustment 3)"""
    # Remove emojis (Unicode ranges)
    text = re.sub(r'[\U0001F600-\U0001F64F]', '', text)  # Emoticons
    text = re.sub(r'[\U0001F300-\U0001F5FF]', '', text)  # Symbols & pictographs
    text = re.sub(r'[\U0001F680-\U0001F6FF]', '', text)  # Transport & map
    text = re.sub(r'[\U0001F1E0-\U0001F1FF]', '', text)  # Flags
    text = re.sub(r'[\U00002702-\U000027B0]', '', text)  # Dingbats
    
    # Remove punctuation and spaces
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', '', text)
    
    return text.lower()


def _record_sent_message(text: str):
    """Record a sent message hash to prevent echoing it back."""
    global SENT_MESSAGE_HASHES
    now = time.time()
    # Clean old hashes (keep for 60s)
    SENT_MESSAGE_HASHES = [(exp, h) for exp, h in SENT_MESSAGE_HASHES if exp > now]
    
    norm_text = _normalize_for_loop_check(text)
    text_hash = hash(norm_text)
    SENT_MESSAGE_HASHES.append((now + 60, text_hash))


def _is_echo_message(text: str) -> bool:
    """Check if text matches a recently sent message."""
    global SENT_MESSAGE_HASHES
    
    norm_text = _normalize_for_loop_check(text)
    text_hash = hash(norm_text)
    
    now = time.time()
    # Clean old ones during check too
    SENT_MESSAGE_HASHES = [(exp, h) for exp, h in SENT_MESSAGE_HASHES if exp > now]
    
    return any(h == text_hash for _, h in SENT_MESSAGE_HASHES)


def _get_whatsapp_adapter(tenant) -> WhatsAppAdapterBase | None:
    """Get WhatsApp adapter based on tenant configuration."""
    if not getattr(tenant, "whatsapp_provider", None):
        return None
    
    if tenant.whatsapp_provider == "evolution":
        return EvolutionAdapter(
            instance_url=tenant.whatsapp_instance_url,
            api_key=tenant.whatsapp_api_key,
            instance_name=tenant.whatsapp_instance_name or "default",
        )
    
    return None


def _split_message(text: str) -> list[str]:
    """
    Split a message into natural conversation chunks for WhatsApp.
    
    Always splits on paragraph boundaries (double newline) to simulate
    a human sending multiple messages. Bullet lists stay with their intro.
    Very short adjacent paragraphs get merged to avoid spammy single-word messages.
    """
    if not text:
        return []
    
    text = text.strip()
    
    # Split by paragraph breaks
    paragraphs = re.split(r'\n\n+', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    # Single paragraph or no breaks — send as-is
    if len(paragraphs) <= 1:
        return [text]
    
    # Group: attach bullet lists to their preceding intro line
    chunks: list[str] = []
    current_chunk = ""
    
    for para in paragraphs:
        # Check if this paragraph starts with bullet points
        is_bullet = bool(re.match(r'^[\-•\*\d]', para))
        
        if not current_chunk:
            current_chunk = para
        elif is_bullet and current_chunk and not re.match(r'^[\-•\*\d]', current_chunk.split('\n')[-1]):
            # Bullet list right after a non-bullet intro → keep together
            current_chunk += "\n\n" + para
        elif len(current_chunk) < 60 and len(para) < 60:
            # Both very short → merge to avoid spammy tiny messages
            current_chunk += "\n\n" + para
        else:
            # Different paragraphs → separate messages
            chunks.append(current_chunk)
            current_chunk = para
    
    if current_chunk:
        chunks.append(current_chunk)
    
    # Final safety: never return empty chunks
    return [c.strip() for c in chunks if c.strip()]


async def process_consolidated_message(
    text: str,
    *,
    tenant_id: str,
    from_number: str,
    session_id: str,
    message_ids: list[str] | None = None,
    generation: int | None = None,
):
    """Processa mensagens consolidadas do buffer WhatsApp.

    Camada fina: toda orquestração de turno (tenant, conversation,
    state, router, graph, persistência) mora em
    turn_processor.process_message. Aqui só fica:
    - Refetch de tenant para recriar o adapter de envio.
    - Comando /reset (caso especial — antes do processamento de turno).
    - Anti-eco + mark_as_read + split em chunks + send via adapter.

    `generation` é a versão do lote no buffer. Se mensagem nova da mesma
    sessão chegou durante o processamento (ex: durante a chamada de LLM),
    a resposta está obsoleta e NÃO é enviada — o turno fica persistido no
    checkpoint e o próximo lote responde com o contexto completo.
    `generation=None` desativa a checagem (chamadas diretas/testes).
    """
    message_ids = message_ids or []

    def _superseded() -> bool:
        return generation is not None and not message_buffer.is_current(
            session_id, generation
        )

    try:
        # Refetch tenant pra recriar adapter de envio.
        registry = TenantRegistry()
        tenant = registry.get(tenant_id, use_cache=True)
        adapter = _get_whatsapp_adapter(tenant)

        if not adapter:
            logger.error(f"WhatsApp adapter could not be recreated for {tenant_id}")
            return

        tenant_uuid = tenant.uuid or tenant.tenant_id

        # Sinaliza "digitando..." imediatamente (best-effort, não-crítico).
        try:
            await adapter.send_typing(to=from_number)
        except Exception as e:
            logger.warning(f"send_typing falhou (não-crítico): {e}")

        # /reset command — caso especial, antes do turn_processor.
        if text.strip().lower() in ["/reset", "/clear", "/reiniciar"]:
            clear_session(tenant_uuid, session_id)
            logger.info(f"🔄 Session reset requested for {session_id}")
            await adapter.send_text_message(
                to=from_number,
                text="🔄 Sessão reiniciada com sucesso. Pode começar de novo!",
            )
            return

        # Delega TODA a orquestração de turno ao turn_processor.
        result = await asyncio.to_thread(
            process_message,
            tenant_id=tenant_id,
            session_id=session_id,
            user_message=text,
            channel="whatsapp",
            is_playground=False,
            number=from_number,
        )

        # Sem mensagem → silêncio (ex: status closed, human_active sem msg).
        if not result.bot_message:
            return

        # Resposta obsoleta: chegou mensagem nova durante o processamento.
        # O turno já está no checkpoint; o próximo lote responde tudo junto.
        if _superseded():
            logger.info(
                f"[BUFFER] Resposta obsoleta descartada p/ sessão "
                f"...{session_id[-4:]} (gen {generation})"
            )
            return

        # Anti-eco: registra o que vamos enviar.
        _record_sent_message(result.bot_message)

        # Mark as read de todas as mensagens do lote, antes do envio.
        for mid in message_ids:
            await adapter.mark_as_read(mid)

        # Split em chunks naturais e envia com delay humano.
        chunks = _split_message(result.bot_message)
        for i, chunk in enumerate(chunks):
            if i > 0 and _superseded():
                logger.info(
                    f"[BUFFER] Envio interrompido no chunk {i+1}/{len(chunks)} "
                    f"p/ sessão ...{session_id[-4:]} — chegou mensagem nova"
                )
                break
            send_result = await adapter.send_text_message(
                to=from_number,
                text=chunk,
            )
            if not send_result.success:
                logger.error(
                    f"Failed to send WhatsApp chunk {i+1}/{len(chunks)}: "
                    f"{send_result.error}"
                )
                break
            if i < len(chunks) - 1:
                delay = min(1.0 + len(chunk) / 200, 2.5)
                await asyncio.sleep(delay)

    except Exception as e:
        logger.error(f"Error processing WhatsApp message: {e}", exc_info=True)


# --- Endpoints ---

@router.post(
    "/shopify/{tenant_id}",
    status_code=status.HTTP_200_OK,
    summary="Receive Shopify product webhooks",
    description="Endpoint for Shopify to send product create/update/delete events.",
)
async def shopify_webhook(
    request: Request,
    tenant_id: str,
    x_shopify_topic: str = Header(..., alias="X-Shopify-Topic"),
    x_shopify_hmac_sha256: str = Header(..., alias="X-Shopify-Hmac-SHA256"),
    x_shopify_shop_domain: str = Header(None, alias="X-Shopify-Shop-Domain"),
):
    """Handle Shopify webhook for product sync."""
    # ... Existing Shopify logic ...
    # Get raw body for HMAC validation
    raw_body = await request.body()
    
    # Rate limiting
    if not _check_rate_limit(tenant_id):
        logger.warning(f"Rate limit exceeded for tenant: {tenant_id[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    
    # Get tenant credentials
    credentials = _get_tenant_credentials(tenant_id)
    if not credentials:
        logger.warning(f"Unknown or inactive tenant: {tenant_id[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    # Validate webhook secret is configured
    webhook_secret = credentials.get("webhook_secret")
    if not webhook_secret:
        logger.error(f"Webhook secret not configured for tenant: {tenant_id[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )
    
    # Validate HMAC signature
    adapter = ShopifyAdapter(
        tenant_id=credentials["tenant_uuid"],
        store_domain=credentials["store_domain"],
        access_token=credentials["access_token"],
        api_version=credentials["api_version"],
        webhook_secret=webhook_secret,
    )
    
    if not adapter.validate_webhook_signature(raw_body, x_shopify_hmac_sha256):
        logger.warning(
            f"Invalid HMAC signature for tenant: {tenant_id[:8]}... "
            f"topic: {x_shopify_topic}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )
    
    # Validate shop domain matches (extra security layer)
    if x_shopify_shop_domain and credentials["store_domain"]:
        if x_shopify_shop_domain.lower() != credentials["store_domain"].lower():
            logger.warning(
                f"Shop domain mismatch for tenant: {tenant_id[:8]}... "
                f"expected: {credentials['store_domain']}, got: {x_shopify_shop_domain}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )
    
    # Parse JSON payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )
    
    # Process webhook
    sync_service = SyncService()
    
    try:
        result = sync_service.process_webhook(
            tenant_id=credentials["tenant_uuid"],
            platform="shopify",
            credentials={
                "store_domain": credentials["store_domain"],
                "access_token": credentials["access_token"],
                "api_version": credentials["api_version"],
                "webhook_secret": webhook_secret,
            },
            event_type=x_shopify_topic,
            payload=payload,
        )
        
        logger.info(
            f"Webhook processed: tenant={tenant_id[:8]}... "
            f"topic={x_shopify_topic} result={result.get('status')}"
        )
        
        return {
            "success": True,
            "event": x_shopify_topic,
            "result": result,
        }
        
    except Exception as e:
        import traceback
        print(f"[WEBHOOK ERROR] {e}")
        traceback.print_exc()
        logger.error(
            f"Error processing webhook for tenant {tenant_id[:8]}...: {e}",
            exc_info=True,
        )
        return {
            "success": False,
            "event": x_shopify_topic,
            "message": "Processing error",
        }


@router.post("/whatsapp/{tenant_id}/messages-upsert", status_code=status.HTTP_200_OK, include_in_schema=False)
@router.post(
    "/whatsapp/{tenant_id}",
    status_code=status.HTTP_200_OK,
    summary="Receive WhatsApp webhook events",
)
async def whatsapp_webhook(request: Request, tenant_id: str):
    """Handle WhatsApp webhook for AI agent conversations."""
    # Rate limiting
    if not _check_rate_limit(tenant_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    # Get tenant config (Async)
    try:
        if tenant_id == "demo":
            # Tenant demo para debug local — credenciais via env, sem hardcode.
            demo_url = os.getenv("EVOLUTION_DEMO_INSTANCE_URL")
            demo_key = os.getenv("EVOLUTION_DEMO_API_KEY")
            if not demo_url or not demo_key:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Demo tenant não configurado — defina "
                        "EVOLUTION_DEMO_INSTANCE_URL e EVOLUTION_DEMO_API_KEY"
                    ),
                )
            from app.core.tenancy import TenantConfig
            tenant = TenantConfig(
                tenant_id="demo",
                name="Demo Store",
                whatsapp_provider="evolution",
                whatsapp_instance_url=demo_url,
                whatsapp_api_key=demo_key,
                whatsapp_instance_name=os.getenv(
                    "EVOLUTION_DEMO_INSTANCE_NAME", "default"
                ),
                active=True
            )
        else:
            registry = TenantRegistry()
            tenant = await registry.get_async(tenant_id, use_cache=True)
    except ValueError:
        logger.error(f"❌ Tenant not found in registry: {tenant_id}")
        raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_id}")
    
    # Get WhatsApp adapter
    adapter = _get_whatsapp_adapter(tenant)
    if not adapter:
        return {"success": False, "error": "WhatsApp not configured for this tenant"}
    
    # Validate webhook
    if not await adapter.validate_webhook(request):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse payload
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Parse incoming message
    message = adapter.parse_incoming_message(payload)
    if not message:
        return {"success": True, "event": "non_message_event"}
    
    # Anti-loop & Deduplication checks
    if _is_echo_message(message.text):
        logger.info(f"Echo detected and dropped: {message.text[:50]}")
        return {"success": True, "event": "echo_dropped"}
    
    if _check_deduplication(message.message_id):
        logger.info(f"Duplicate message dropped: {message.message_id}")
        return {"success": True, "event": "duplicate_dropped"}
    
    # Normalize session ID
    raw_id = adapter.get_session_id() or message.from_number
    session_id = "".join(filter(str.isdigit, str(raw_id)))
    
    # Buffer message (debounce). Retorna True se iniciou um lote novo.
    is_new_batch = await message_buffer.add_message(
        session_id=session_id,
        text=message.text,
        message_id=message.message_id,
        process_callback=process_consolidated_message,
        tenant_id=tenant_id,
        from_number=message.from_number,
    )

    # Sinal de vida imediato: "digitando..." já na primeira mensagem do
    # lote, antes do debounce vencer (best-effort, não-crítico).
    if is_new_batch:
        try:
            await adapter.send_typing(to=message.from_number)
        except Exception as e:
            logger.debug(f"send_typing inicial falhou (não-crítico): {e}")

    return {
        "success": True,
        "event": "message_buffered",
        "status": "processing_async"
    }


# --- Catch-All: Silently ignore all other Evolution API event sub-routes ---
@router.post("/whatsapp/{tenant_id}/{event_type}", status_code=status.HTTP_200_OK, include_in_schema=False)
async def whatsapp_ignore_event(tenant_id: str, event_type: str):
    """Silently ignore non-message events (presence-update, messages-update, send-message, etc.)."""
    return {"success": True, "event": "ignored", "type": event_type}


@router.get("/health", summary="Health check for webhook service")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "service": "webhooks"}
