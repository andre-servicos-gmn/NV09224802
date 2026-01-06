"""Support response generation.

Responsabilidade: gerar mensagem humana sem executar logica de negocio.

REGRAS DE GROUNDING:
====================
1. NUNCA inventar SLA de entrega, status ou tracking.
2. Usar apenas dados presentes no state (vindos da API).
3. Se tracking_url ausente → "ainda não há rastreio disponível".

FLUXO DE SOLICITAÇÃO DE DADOS:
==============================
Se NÃO houver order_id NEM customer_email no state, este node
pede ao cliente: "me manda o número do pedido ou o email da compra".
Isso garante que o Decide não cria dados — apenas roteia.
"""
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig


def support_respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    # Se não há order_id nem email, pedir ao cliente (não inventar dados)
    if not state.order_id and not state.customer_email:
        state.last_bot_message = (
            "Pra eu localizar seu pedido, me manda o numero do pedido ou o email da compra."
        )
        return state

    if state.last_action_success is False:
        if state.last_action == "open_ticket":
            state.last_bot_message = (
                "Sinto muito, nao consegui abrir o ticket agora. "
                "Pode me passar o email da compra ou o numero do pedido?"
            )
        else:
            state.last_bot_message = (
                "Sinto muito, tive um problema ao localizar o pedido. "
                "Pode me passar o email da compra ou o numero do pedido?"
            )
        return state

    if state.ticket_opened:
        state.last_bot_message = "Pronto, abri um ticket pra este pedido. Se precisar de algo, me avisa."
        return state

    if state.tracking_url:
        state.last_bot_message = (
            "Achei o rastreio do seu pedido. Segue o link:\n\n" + state.tracking_url
        )
        return state

    tracking_number = state.metadata.get("tracking_number")
    if tracking_number:
        state.last_bot_message = f"Encontrei o codigo de rastreio: {tracking_number}."
        return state

    state.last_bot_message = "Seu pedido ainda nao foi enviado ou ainda nao ha rastreio disponivel."
    return state
