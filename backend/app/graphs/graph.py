"""Build do graph — StateGraph + ToolNode + tools_condition + PostgresSaver."""

import os
from typing import Optional

from langgraph.graph import StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from app.graphs.state import AgentState
from app.graphs.supervisor import supervisor_node
from app.graphs.tools import ALL_TOOLS


# ─── Checkpointer (PostgresSaver via Supabase) ───

_DB_URI = os.getenv("SUPABASE_POSTGRES_URI")
_pool: Optional[ConnectionPool] = None
_checkpointer: Optional[PostgresSaver] = None


def _get_checkpointer() -> PostgresSaver:
    """Lazy init do checkpointer. Cria tabelas se não existirem."""
    global _pool, _checkpointer
    if _checkpointer is None:
        if not _DB_URI:
            raise RuntimeError(
                "SUPABASE_POSTGRES_URI não configurado. "
                "Setar no .env: SUPABASE_POSTGRES_URI=postgresql://..."
            )
        _pool = ConnectionPool(conninfo=_DB_URI, max_size=20, kwargs={"autocommit": True})
        _checkpointer = PostgresSaver(_pool)
        _checkpointer.setup()  # idempotente — cria tabelas se não existirem
    return _checkpointer


# ─── Graph build ───

def build_graph():
    """Constrói e compila o StateGraph."""
    builder = StateGraph(AgentState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("tools", ToolNode(ALL_TOOLS))

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        tools_condition,  # built-in: vai pra "tools" se houver tool_calls, senão END
    )
    builder.add_edge("tools", "supervisor")

    checkpointer = _get_checkpointer()
    return builder.compile(checkpointer=checkpointer)


# Compilado uma vez no import (módulo singleton)
_graph = None


def get_graph():
    """Lazy singleton do graph compilado."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def clear_session(tenant_id: str, session_id: str) -> None:
    """Apaga checkpoints da thread (=conversa) no PostgresSaver.

    Usado pelo /reset command do webhook WhatsApp. Após chamar, o próximo
    turno do user começa do zero (sem histórico, sem state).
    """
    if _pool is None:
        _get_checkpointer()  # força init do pool
    thread_id = f"{tenant_id}:{session_id}"
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            for tbl in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                cur.execute(f"DELETE FROM {tbl} WHERE thread_id = %s", (thread_id,))
