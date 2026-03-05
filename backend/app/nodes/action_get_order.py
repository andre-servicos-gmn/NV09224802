"""
Action Get Order Node — WISMO Feature

Responsabilidade: Buscar dados do pedido via Shopify API e, se houver código de rastreio,
consultar a transportadora/gateway logístico para obter a última movimentação.

Segue o contrato do AGENT.md:
- Atualiza o estado com os dados encontrados
- NÃO decide fluxo
- NÃO gera texto ao usuário
"""
import os
import logging
import requests

from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.tools.shopify_client import ShopifyClient

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURAÇÃO DO GATEWAY LOGÍSTICO (17Track)
# =============================================================================

def _fetch_tracking_event(tracking_code: str, tracking_company: str | None = None) -> dict:
    """
    Consulta o gateway logístico 17Track para obter a última movimentação.

    Fluxo em 2 etapas:
      1. POST /register  → registra o tracking number no 17Track (idempotente)
      2. POST /gettrackinfo → busca a última movimentação

    Returns:
        dict com:
          - last_event (str): Descrição da última movimentação
          - delivered (bool): Se o pacote foi entregue
          - error (str | None): Mensagem de erro se falhou
    """
    track17_token = os.getenv("TRACK17_TOKEN")

    if not track17_token:
        logger.info("[17Track] Token não configurado; pulando rastreio em tempo real.")
        return {"last_event": None, "delivered": False, "error": "tracking_not_configured"}

    headers = {
        "17token": track17_token,
        "Content-Type": "application/json",
    }
    payload = [{"number": tracking_code}]

    # ---------- Etapa 1: Registrar o tracking number (idempotente) ----------
    try:
        reg_resp = requests.post(
            "https://api.17track.net/track/v2.2/register",
            headers=headers,
            json=payload,
            timeout=8,
        )
        reg_resp.raise_for_status()
        reg_data = reg_resp.json()
        logger.info(f"[17Track] Register response code={reg_data.get('code')}: {tracking_code}")

        # code 0 = ok, code -18010012 = already registered (both are fine)
        rejected = reg_data.get("data", {}).get("rejected", [])
        if rejected:
            rej_code = rejected[0].get("error", {}).get("code", 0)
            # -18010012 = "Item already exists" → ok, proceed
            if rej_code != -18010012:
                logger.warning(f"[17Track] Register rejected code={rej_code}: {rejected[0]}")
    except Exception as e:
        logger.warning(f"[17Track] Register failed for {tracking_code}: {e}")
        # Continue anyway — maybe it was registered before

    # ---------- Etapa 2: Buscar informações de rastreio ----------
    try:
        response = requests.post(
            "https://api.17track.net/track/v2.2/gettrackinfo",
            headers=headers,
            json=payload,
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
        logger.info(f"[17Track] GetTrackInfo response code={data.get('code')} for {tracking_code}")

        # 17Track returns results in 'data.accepted'
        accepted = data.get("data", {}).get("accepted", [])

        if not accepted:
            logger.info(f"[17Track] No accepted results for {tracking_code}")
            return {"last_event": "Aguardando atualização da transportadora.", "delivered": False, "error": None}

        track_info = accepted[0].get("track", {})
        events = track_info.get("z1", [])  # z1 = newest events list

        # 17Track status codes:
        # 0: NotFound, 10: InTransit, 20: Expired, 30: PickedUp
        # 40: Undelivered, 50: Delivered, 60: Alert
        status_code = track_info.get("e", 0)
        delivered = status_code == 50

        if events:
            latest = events[0]  # events ordered newest → oldest
            description = latest.get("z", "")
            location = latest.get("c", "")  # city/location if available
            event_time = latest.get("a", "")  # timestamp

            if location and description:
                full_event = f"{description} ({location})"
            else:
                full_event = description or "Movimentação registrada."

            logger.info(f"[17Track] Last event: {full_event} | delivered={delivered} | status={status_code}")
            return {"last_event": full_event, "delivered": delivered, "error": None}

        # No events yet
        status_messages = {
            0: "Código de rastreio registrado. Aguardando primeira movimentação.",
            10: "Em trânsito.",
            20: "Informações de rastreio expiradas.",
            30: "Pacote coletado pela transportadora.",
            40: "Tentativa de entrega sem sucesso.",
            50: "Pedido entregue!",
            60: "Alerta na entrega. Verifique com a transportadora.",
        }
        fallback_msg = status_messages.get(status_code, "Aguardando atualização da transportadora.")
        return {"last_event": fallback_msg, "delivered": delivered, "error": None}

    except Exception as e:
        logger.warning(f"[17Track] GetTrackInfo failed for {tracking_code}: {e}")
        return {"last_event": None, "delivered": False, "error": str(e)}


# =============================================================================
# MAPEAMENTO DE STATUS SHOPIFY → PORTUGUÊS HUMANIZADO
# =============================================================================

FINANCIAL_STATUS_MAP = {
    "pending": "aguardando pagamento",
    "authorized": "pagamento autorizado",
    "partially_paid": "pagamento parcial",
    "paid": "pagamento confirmado",
    "partially_refunded": "parcialmente reembolsado",
    "refunded": "reembolsado",
    "voided": "cancelado",
}

FULFILLMENT_STATUS_MAP = {
    None: "em processamento",
    "unfulfilled": "em processamento",
    "partial": "enviado parcialmente",
    "fulfilled": "enviado",
    "restocked": "devolvido ao estoque",
}


def _humanize_status(order: dict) -> str:
    """Converte status técnicos da Shopify em texto humanizado em português."""
    financial = FINANCIAL_STATUS_MAP.get(
        order.get("financial_status"), order.get("financial_status") or "desconhecido"
    )
    fulfillment = FULFILLMENT_STATUS_MAP.get(
        order.get("fulfillment_status"), order.get("fulfillment_status") or "em processamento"
    )

    if order.get("tracking_code"):
        return f"enviado ({financial})"
    return f"{fulfillment} — {financial}"


# =============================================================================
# NÓ PRINCIPAL
# =============================================================================

def action_get_order(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """
    Busca o pedido do cliente via Shopify e enriquece com dados de rastreio.

    Ordem de identificação:
    1. Telefone do WhatsApp (invisível)
    2. E-mail (se cliente informou)
    3. Número do pedido (se cliente informou)
    4. Sem dados → solicita e-mail

    Ao final, sempre seta wismo_lookup_done = True para evitar loop.
    """
    logger.info(f"[action_get_order] tenant={tenant.tenant_id} session={state.session_id}")

    # Guard: se não tem credenciais Shopify configuradas para o tenant, falha graciosamente
    if not tenant.shopify_access_token or not tenant.store_domain:
        logger.warning("[action_get_order] Tenant sem credenciais Shopify configuradas.")
        state.wismo_lookup_done = True
        state.last_action = "action_get_order"
        state.last_action_success = False
        state.metadata["wismo_error"] = "shopify_not_configured"
        return state

    client = ShopifyClient(
        store_domain=tenant.store_domain,
        access_token=tenant.shopify_access_token,
        api_version=tenant.shopify_api_version,
    )

    order = None
    identified_by = None

    # --- Estratégia 1: Telefone do WhatsApp (abordagem invisível) ---
    phone = state.customer_phone or state.metadata.get("customer_phone_raw")
    if phone and not order:
        try:
            orders = client.get_orders_by_phone(phone)
            if orders:
                # Se encontrou mais de um, usa o mais recente (primeiro da lista)
                order = orders[0]
                identified_by = "phone"
                logger.info(f"[action_get_order] Pedido encontrado por telefone: #{order['order_number']}")
        except Exception as e:
            logger.warning(f"[action_get_order] Busca por telefone falhou: {e}")

    # --- Estratégia 2: E-mail ---
    if not order and state.customer_email:
        try:
            orders = client.get_orders_by_email(state.customer_email)
            if orders:
                order = orders[0]
                identified_by = "email"
                logger.info(f"[action_get_order] Pedido encontrado por e-mail: #{order['order_number']}")
        except Exception as e:
            logger.warning(f"[action_get_order] Busca por e-mail falhou: {e}")

    # --- Estratégia 3: Número do pedido informado pelo cliente ---
    if not order and state.order_id:
        try:
            order = client.get_order_by_number(state.order_id)
            identified_by = "order_id"
            logger.info(f"[action_get_order] Pedido encontrado por order_id: #{order['order_number']}")
        except Exception as e:
            logger.warning(f"[action_get_order] Busca por order_id falhou: {e}")

    # --- Nenhum dado disponível: pedir e-mail ao cliente ---
    if not order and not phone and not state.customer_email and not state.order_id:
        state.missing_info_needed = ["email"]
        state.wismo_lookup_done = True
        state.last_action = "action_get_order"
        state.last_action_success = False
        state.metadata["wismo_needs"] = "email_or_order_id"
        logger.info("[action_get_order] Sem dados suficientes, solicitando e-mail.")
        return state

    # --- Pedido não encontrado (dados fornecidos mas sem resultado) ---
    if not order:
        state.wismo_lookup_done = True
        state.last_action = "action_get_order"
        state.last_action_success = False
        state.metadata["wismo_error"] = "order_not_found"
        logger.info("[action_get_order] Pedido não encontrado com os dados disponíveis.")
        return state

    # =========================================================================
    # PEDIDO ENCONTRADO — enriquecer o estado
    # =========================================================================

    state.order_id = order["order_number"]        # sempre salvar o order_number visível
    state.customer_email = order.get("customer_email") or state.customer_email
    state.order_status = _humanize_status(order)
    state.tracking_code = order.get("tracking_code")
    state.tracking_url = order.get("tracking_url")
    state.estimated_delivery = order.get("estimated_delivery_at")
    state.wismo_identified_by = identified_by

    # Guardar status raw no metadata para o LLM ter contexto completo
    state.metadata["order_raw"] = {
        "financial_status": order.get("financial_status"),
        "fulfillment_status": order.get("fulfillment_status"),
        "tracking_company": order.get("tracking_company"),
        "created_at": order.get("created_at"),
    }

    # --- Consulta logística (se pedido tem código de rastreio) ---
    if state.tracking_code:
        tracking_result = _fetch_tracking_event(
            state.tracking_code,
            order.get("tracking_company"),
        )
        if tracking_result.get("last_event"):
            state.tracking_last_event = tracking_result["last_event"]
            if tracking_result.get("delivered"):
                state.order_status = "entregue"
        elif tracking_result.get("error") == "tracking_not_configured":
            logger.info("[action_get_order] Gateway logístico não configurado, usando dados da Shopify.")
        else:
            logger.warning(f"[action_get_order] Tracking error: {tracking_result.get('error')}")

    state.wismo_lookup_done = True
    state.last_action = "action_get_order"
    state.last_action_success = True

    logger.info(
        f"[action_get_order] Concluído. order={state.order_id}, "
        f"status={state.order_status}, tracking={state.tracking_code}, "
        f"last_event={state.tracking_last_event}"
    )

    return state
