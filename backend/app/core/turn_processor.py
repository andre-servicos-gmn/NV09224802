"""Ponto único de processamento de turno do Nouva.

`process_message()` é o único lugar do sistema que orquestra um turno
completo: resolve tenant, checa active/playground, invoca o graph
LangGraph (que tem checkpointer PostgreSaver fazendo persistência
end-to-end), e mapeia o resultado para o contrato HTTP esperado pelos
entrypoints (chat.py, webhooks.py).

Pós-cutover da Fase 2: este arquivo virou camada fina sobre `app.graphs.invoke`.
Nada de save_message, get_or_create_conversation, router, ou state custom —
PostgresSaver é a fonte única de verdade do state conversacional.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from app.core.tenancy import TenantRegistry, TenantConfig
from app.graphs.invoke import invoke

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    """Resultado de um turno processado (contrato externo do entrypoint)."""

    bot_message: str
    session_id: str
    intent: Optional[str] = None
    domain: Optional[str] = None
    status: str = "active"  # active | handoff | blocked | error
    action: Optional[str] = None
    error: Optional[str] = None


def process_message(
    tenant_id: str,
    session_id: str,
    user_message: str,
    channel: str = "whatsapp",
    is_playground: bool = False,
    number: Optional[str] = None,
) -> ProcessResult:
    """Processa uma mensagem do usuário e retorna ProcessResult.

    Fluxo:
    1. Resolve tenant via TenantRegistry. Tenant inválido → status="error".
    2. Checa tenant.active (a menos que is_playground). Inativo → status="blocked".
    3. Invoca o graph LangGraph com checkpointer (state persiste cross-turn).
    4. Mapeia AgentResult.handoff_triggered/error → ProcessResult.status.

    `number` (telefone WhatsApp) e `channel` vão pro state inicial do graph
    mas não alteram orquestração no nível do turn_processor.
    """
    # 1. Tenant resolution
    try:
        tenant: TenantConfig = TenantRegistry().get(tenant_id, use_cache=True)
    except ValueError:
        return ProcessResult(
            bot_message="Tenant inválido",
            session_id=session_id,
            status="error",
            error="tenant_not_found",
        )

    # 2. Active check (playground bypassa)
    if not is_playground and tenant.active is False:
        return ProcessResult(
            bot_message=(
                "O agente está temporariamente desativado. "
                "Tente novamente mais tarde."
            ),
            session_id=session_id,
            status="blocked",
            action="agent_disabled",
        )

    # 3. Invocação do graph
    result = invoke(
        tenant_id=tenant_id,
        session_id=session_id,
        user_message=user_message,
        channel=channel,
    )

    # 4. Mapeamento AgentResult → ProcessResult
    if result.error:
        return ProcessResult(
            bot_message=result.bot_message
            or "Desculpe, tive um problema técnico. Pode repetir?",
            session_id=session_id,
            status="error",
            error=result.error,
        )

    if result.handoff_triggered:
        return ProcessResult(
            bot_message=result.bot_message or "",
            session_id=session_id,
            status="handoff",
            action="escalate_handoff",
        )

    last_action = result.tool_calls[-1] if result.tool_calls else None
    return ProcessResult(
        bot_message=result.bot_message or "",
        session_id=session_id,
        status="active",
        action=last_action,
    )
