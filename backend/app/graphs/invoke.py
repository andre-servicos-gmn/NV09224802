"""Entrypoint do graph — `invoke()` roda um turno e retorna AgentResult."""

from dataclasses import dataclass, field
from typing import Optional
from langchain_core.messages import HumanMessage, AIMessage

from app.graphs.graph import get_graph


@dataclass
class AgentResult:
    """Resultado de um turno do agente."""
    bot_message: str
    tool_calls: list = field(default_factory=list)  # nomes de tools chamadas
    iterations: int = 0  # quantas vezes o supervisor rodou
    error: Optional[str] = None
    handoff_triggered: bool = False  # True se escalate_handoff foi chamado neste turno


def invoke(
    tenant_id: str,
    session_id: str,
    user_message: str,
    channel: str = "web",
) -> AgentResult:
    """Invoca o graph para um turno de conversação.

    Cria/recupera state via checkpointer (thread_id = tenant_id:session_id),
    adiciona a mensagem do user em messages, roda o graph, retorna
    a última resposta do bot.
    """
    try:
        graph = get_graph()

        # config: thread_id é o que o checkpointer usa pra isolar conversas
        config = {"configurable": {"thread_id": f"{tenant_id}:{session_id}"}}

        # Input: só os campos que vão pro state inicial deste turno.
        # MessagesState faz append automático via add_messages reducer.
        input_state = {
            "messages": [HumanMessage(content=user_message)],
            "tenant_id": tenant_id,
            "session_id": session_id,
            "channel": channel,
            # Demais campos têm default None / {} / 0 e ficam preservados
            # pelo checkpointer entre turnos.
            "facts": {},
            "soft_context": {},
            "frustration_level": 0,
        }

        result_state = graph.invoke(input_state, config=config)

        # Extrai última mensagem do bot (AIMessage final)
        last_msg = result_state["messages"][-1]
        bot_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        # Conta tool calls feitas neste turno (heurística: AIMessages com tool_calls)
        tool_calls = []
        for msg in result_state["messages"]:
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    tool_calls.append(tc["name"])

        return AgentResult(
            bot_message=bot_message,
            tool_calls=tool_calls,
            iterations=len([m for m in result_state["messages"] if isinstance(m, AIMessage)]),
            handoff_triggered=("escalate_handoff" in tool_calls),
        )

    except Exception as e:
        return AgentResult(
            bot_message="",
            tool_calls=[],
            iterations=0,
            error=str(e),
        )
