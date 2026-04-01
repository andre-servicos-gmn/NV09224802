"""
Cache genérico Redis para lookups externos (Shopify, 17Track, etc.).

Usa o mesmo cliente Redis de session_store_v2.
Falhas são silenciosas — o cache é best-effort, nunca bloqueia o fluxo principal.
"""
import json
import logging
import os
from typing import Any, Optional

import redis

logger = logging.getLogger(__name__)

_TTL_SHOPIFY_ORDER = int(os.getenv("CACHE_TTL_SHOPIFY_ORDER", "300"))   # 5 min
_TTL_TRACKING = int(os.getenv("CACHE_TTL_TRACKING", "300"))             # 5 min
_TTL_INVENTORY = int(os.getenv("CACHE_TTL_INVENTORY", "60"))            # 1 min

_redis_client: Optional[redis.Redis] = None


def _get_redis() -> Optional[redis.Redis]:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        client = redis.from_url(url, decode_responses=True, socket_timeout=2.0)
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception as e:
        logger.warning(f"[cache] Redis indisponível: {e}")
        return None


def cache_get(key: str) -> Optional[Any]:
    """Retorna valor cacheado ou None se ausente/expirado/erro."""
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.debug(f"[cache] get error key={key}: {e}")
        return None


def cache_set(key: str, value: Any, ttl: int) -> None:
    """Armazena valor no cache com TTL em segundos. Falha silenciosa."""
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
    except Exception as e:
        logger.debug(f"[cache] set error key={key}: {e}")


def cache_delete(key: str) -> None:
    """Remove entrada do cache. Falha silenciosa."""
    r = _get_redis()
    if not r:
        return
    try:
        r.delete(key)
    except Exception as e:
        logger.debug(f"[cache] delete error key={key}: {e}")


# ---------------------------------------------------------------------------
# Helpers com chaves padronizadas
# ---------------------------------------------------------------------------

def shopify_order_key(tenant_id: str, identifier: str) -> str:
    return f"shopify:order:{tenant_id}:{identifier}"


def tracking_key(tracking_code: str) -> str:
    return f"17track:{tracking_code}"


def inventory_key(variant_id: str) -> str:
    return f"shopify:inventory:{variant_id}"


def get_cached_order(tenant_id: str, identifier: str) -> Optional[dict]:
    return cache_get(shopify_order_key(tenant_id, identifier))


def set_cached_order(tenant_id: str, identifier: str, order: dict) -> None:
    cache_set(shopify_order_key(tenant_id, identifier), order, _TTL_SHOPIFY_ORDER)


def get_cached_tracking(tracking_code: str) -> Optional[dict]:
    return cache_get(tracking_key(tracking_code))


def set_cached_tracking(tracking_code: str, result: dict) -> None:
    # Não cachear erros para que a próxima tentativa vá para a API
    if result.get("error"):
        return
    cache_set(tracking_key(tracking_code), result, _TTL_TRACKING)


def get_cached_inventory(variant_id: str) -> Optional[dict]:
    return cache_get(inventory_key(variant_id))


def set_cached_inventory(variant_id: str, result: dict) -> None:
    cache_set(inventory_key(variant_id), result, _TTL_INVENTORY)
