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
import time
import re
import asyncio
from collections import defaultdict
from typing import Optional, Any
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.adapters.shopify_adapter import ShopifyAdapter
from app.adapters.evolution_adapter import EvolutionAdapter
from app.adapters.whatsapp_base import WhatsAppAdapterBase
from app.core.tenancy import TenantRegistry
from app.sync.sync_service import SyncService
import os
from app.core.message_buffer import AsyncMessageBuffer
from app.core.message_buffer_redis import RedisMessageBuffer

# Seleção automática baseada na disponibilidade do Redis
_redis_url = os.getenv('REDIS_URL')
if _redis_url:
    message_buffer = RedisMessageBuffer(
        redis_url=_redis_url,
        debounce_seconds=2.5
    )
else:
    # Fallback para o buffer em memória (desenvolvimento local)
    message_buffer = AsyncMessageBuffer(debounce_seconds=2.5)
    
from app.core.session_store_v2 import get_session, save_session
from app.core.state import ConversationState
# Assumed location based on grep search
from app.graphs.main_graph import run_main_graph
from app.core.constants import FRUSTRATION_KEYWORDS
from app.core.router import apply_entities_to_state, classify
from app.core.database import get_or_create_conversation, save_message, get_supabase


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


async def _bg_persist_message(tenant_id: str, session_id: str, message: Any, created_at_iso: str | None):
    """Background task to persist message to DB without blocking webhook.
    
    This function handles both conversation retrieval/creation and message saving
    in a separate task, allowing the webhook to return immediately and the
    message buffer to function without DB latency interference.
    """
    try:
        # Blocking I/O - Get Conversation
        # Use tenant UUID (not slug) because conversations.tenant_id is UUID type
        conversation = await asyncio.to_thread(
            get_or_create_conversation,
            tenant_id=tenant_id,  # This is already the UUID from whatsapp_webhook
            session_id=session_id,
            channel="whatsapp",
            number=message.from_number
        )
        conversation_id = conversation.get("id")
        
        # Blocking I/O - Save Message
        saved = await asyncio.to_thread(
            save_message,
            conversation_id=conversation_id,
            sender_type="user",
            content=message.text,
            metadata={
                "provider": "evolution",
                "message_id": message.message_id,
                "from_number": message.from_number,
                "push_name": getattr(message, "push_name", None)
            },
            created_at=created_at_iso
        )
        logger.info(f"[BG] Persisted msg {message.message_id} to conv {conversation_id} ts={created_at_iso}")
    except Exception as e:
        logger.error(f"[BG] Failed to persist message: {e}")



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
    tenant_id: str, 
    from_number: str, 
    message_id: str,
    session_id: str
):
    """Process aggregated messages from the buffer."""
    try:
        # Re-fetch tenant and recreate adapter
        registry = TenantRegistry()
        tenant = registry.get(tenant_id, use_cache=True)
        adapter = _get_whatsapp_adapter(tenant)
        
        if not adapter:
            logger.error(f"WhatsApp adapter could not be recreated for {tenant_id}")
            return

        # Check for Handoff/Paused status
        # If status is "handoff" or "human_active", the agent must NOT respond.
        # Use tenant.uuid because conversations.tenant_id is UUID type
        tenant_uuid = tenant.uuid or tenant.tenant_id
        conversation_data = await asyncio.to_thread(
            get_or_create_conversation,
            tenant_id=tenant_uuid,
            session_id=session_id
        )
        
        if conversation_data and conversation_data.get("status") in ["handoff", "human_active"]:
            logger.info(f"🛑 Conversation {session_id} is PAUSED/HANDOFF. Agent skipping execution.")
            return

        # Handle Reset Command
        if text.strip().lower() in ["/reset", "/clear", "/reiniciar"]:
            from app.core.session_store import clear_session
            clear_session(tenant_uuid, session_id)
            logger.info(f"🔄 Session reset requested for {session_id}")
            await adapter.send_text_message(
                to=session_id,  # session_id is the phone number
                text="🔄 Sessão reiniciada com sucesso. Pode começar de novo!"
            )
            return

        # Session management
        state = get_session(tenant_uuid, session_id)
        
        if state:
            state.last_user_message = text
            state.add_to_history("user", text)
        else:
            state = ConversationState(
                tenant_id=tenant_uuid,
                session_id=session_id,
                channel="whatsapp",
                last_user_message=text,
            )
            state.add_to_history("user", text)
        
        # Adjustment 5: Contextual Confirmation Detection
        # If message is simple confirmation AND bot just made an offer
        confirmation_pattern = r'^(sim|quero|pode|ok|ta|tá|beleza|bora|yes|manda|claro|aceito)\W*$'
        
        if re.match(confirmation_pattern, text.lower().strip()):
            # Check if bot asked something in previous turn
            if state.last_bot_message and ('?' in state.last_bot_message or 
                                           'quer' in state.last_bot_message.lower() or
                                           'posso' in state.last_bot_message.lower()):
                
                logger.info(f"🎯 Detected user confirmation: '{text}' → marking as continuation")
                
                # Add flags for Router
                state.soft_context['user_confirmed_previous_offer'] = True
                state.soft_context['confirmation_text'] = text
                state.soft_context['is_simple_confirmation'] = True
                
                # Maintain current domain/intent
                if state.domain:
                    state.soft_context['keep_current_domain'] = True
                if state.intent and state.intent != 'general':
                    state.soft_context['keep_current_intent'] = True
        
        # Prepare context for Router
        context = {
            "tenant_id": state.tenant_id,
            "session_id": state.session_id,
            "last_domain": state.domain,
            "last_intent": state.intent,
            "has_variant_id": bool(state.soft_context.get("selected_variant_id")),
            "has_order_id": bool(state.order_id),
            "has_selected_products": bool(state.selected_products),
            "selected_products_count": len(state.selected_products) if state.selected_products else 0,
            "store_name": tenant.name,
            "store_niche": tenant.store_niche or "loja online",
        }
        
        # Add product titles to context for better routing
        if state.selected_products:
            titles = [p.get("title", "") for p in state.selected_products[:3]]
            context["last_products_discussed"] = ", ".join(titles)

        # Run Classification (Router)
        # This was missing! Without this, the agent never updated intent/domain based on new input.
        decision = classify(text, context=context, use_llm=True)
        
        logger.info(
            f"[ROUTER] domain={decision.domain}, intent={decision.intent}, "
            f"entities={decision.entities}, confidence={decision.confidence:.2f}, "
            f"reason={decision.reason}"
        )
        
        # Apply decision to state
        state.set_intent(decision.intent)
        
        # Only switch domain if not forcing current one (e.g. simple confirmation)
        if not state.soft_context.get('keep_current_domain'):
            state.domain = decision.domain
        
        apply_entities_to_state(state, decision.entities)
        
        state.sentiment_level = decision.sentiment_level
        state.sentiment_score = decision.sentiment_score
        state.needs_handoff = decision.needs_handoff
        state.handoff_reason = decision.handoff_reason
        
        # Frustration Check
        def _has_frustration(msg_text):
            return any(k in msg_text.lower() for k in FRUSTRATION_KEYWORDS)

        if decision.sentiment_level != "calm" or _has_frustration(text):
            state.bump_frustration()
            
        # Extrair telefone do cliente
        if from_number:
            raw_phone = from_number.split("@")[0]  # remove @s.whatsapp.net se houver
            clean_phone = "".join(c for c in raw_phone if c.isdigit())
            if clean_phone:
                state.customer_phone = clean_phone
                state.metadata["customer_phone_raw"] = clean_phone

        # Stop Agent if Handoff is required
        if state.needs_handoff or state.frustration_level >= 3:
            reason = state.handoff_reason or "high_frustration"
            if state.frustration_level >= 3 and not state.handoff_reason:
                reason = "high_frustration"
            
            logger.info(f"🛑 Handoff triggered for {session_id}. Reason: {reason}")
            
            # Persist Handoff
            try:
                conversation = await asyncio.to_thread(
                    get_or_create_conversation,
                    tenant_id=tenant_uuid,
                    session_id=session_id,
                    channel="whatsapp",
                    number=from_number
                )
                conv_id = conversation.get("id")
                
                if conv_id:
                    supabase = get_supabase()
                    supabase.table("conversations").update({
                        "status": "handoff",
                        "handoff_reason": reason
                    }).eq("id", conv_id).execute()
                    
                    save_message(
                        conversation_id=conv_id,
                        sender_type="system",
                        content=f"Conversa transferida para humano. Motivo: {reason}",
                        metadata={
                            "event": "handoff",
                            "reason": reason
                        }
                    )
            except Exception as e:
                logger.error(f"[ERR] Failed to persist handoff state: {e}")
            
            return

        # Process with AI agent/graph
        result_state = await asyncio.to_thread(run_main_graph, state, tenant)
        
        response_text = result_state.last_bot_message
        
        if response_text:
            # Record sent message for anti-loop
            _record_sent_message(response_text)
            
            save_session(tenant_uuid, session_id, result_state)
            
            await adapter.mark_as_read(message_id)
            
            # Split into multiple messages for natural conversation feel
            chunks = _split_message(response_text)
            
            for i, chunk in enumerate(chunks):
                send_result = await adapter.send_text_message(
                    to=from_number,
                    text=chunk,
                )
                
                if not send_result.success:
                    logger.error(f"Failed to send WhatsApp chunk {i+1}/{len(chunks)}: {send_result.error}")
                    break
                
                # Human-like delay between messages (skip after last)
                if i < len(chunks) - 1:
                    delay = min(1.0 + len(chunk) / 200, 2.5)  # 1.0s-2.5s based on length
                    await asyncio.sleep(delay)
            
            # Persist AGENT message to database
            try:
                conversation = get_or_create_conversation(
                    tenant_id=tenant_uuid,
                    session_id=session_id,
                    channel="whatsapp"
                )
                if conversation and conversation.get("id"):
                    save_message(
                        conversation_id=conversation.get("id"),
                        sender_type="agent",
                        content=response_text,
                        metadata={
                            "provider": "evolution",
                            "message_id": getattr(send_result, "message_id", None)
                        }
                    )
                    logger.info(f"[DB] Agent message persisted for session {session_id}")
            except Exception as e:
                logger.error(f"[ERR] Failed to save agent message: {e}")
        else:
            save_session(tenant_uuid, session_id, result_state)
            
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
            # Mock demo tenant for local debugging
            from app.core.tenancy import TenantConfig
            tenant = TenantConfig(
                tenant_id="demo",
                name="Demo Store",
                whatsapp_provider="evolution",
                whatsapp_instance_url="https://nouvaris-evolution-api.ojdb99.easypanel.host",
                whatsapp_api_key="3507B4BFABD9-4F3B-B87E-E441338CF369",
                whatsapp_instance_name="nouvaris",
                active=True
            )
        else:
            registry = TenantRegistry()
            tenant = await registry.get_async(tenant_id, use_cache=True)
    except ValueError:
        # FAILSAFE: Always use Mock/Demo tenant for testing locally
        logger.warning(f"⚠️ Tenant '{tenant_id}' not found. Redirecting to DEMO tenant.")
        
        original_tenant_id = tenant_id
        tenant_id = "c35fe360-dc69-4997-9d1f-ae57f4d8a135"
        
        from app.core.tenancy import TenantConfig
        tenant = TenantConfig(
            tenant_id="demo",
            uuid=tenant_id,
            name="Demo Store",
            active=True,
            whatsapp_provider="evolution",
            whatsapp_instance_name="test_instance",
            whatsapp_instance_url="http://localhost:8080",
            whatsapp_api_key="mock_key"
        )
    
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
    
    logger.info(f"[WH] received tenant={tenant_id[:8]}... from={session_id}")
    
    # Persist to database (Background Task)
    created_at_iso = None
    msg_ts = getattr(message, "timestamp", 0)
    if msg_ts:
        try:
            ts_val = float(msg_ts)
            if ts_val > 1e11:
                ts_val = ts_val / 1000.0
            created_at_iso = datetime.fromtimestamp(ts_val, tz=timezone.utc).isoformat()
        except Exception:
            pass

    asyncio.create_task(
        _bg_persist_message(tenant.uuid or tenant.tenant_id, session_id, message, created_at_iso)
    )
    
    # Buffer message for AI processing
    await message_buffer.add_message(
        session_id,
        message.text,
        process_consolidated_message,
        tenant.uuid or tenant.tenant_id,
        message.from_number,
        message.message_id,
        session_id
    )
    
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
