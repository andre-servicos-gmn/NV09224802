from langgraph.graph import END, StateGraph

from app.core.state import ConversationState
from app.graphs.sales_graph import run_sales_graph
from app.graphs.store_qa_graph import run_store_qa_graph
from app.graphs.support_graph import run_support_graph


def _select_domain(state: ConversationState) -> str:
    if state.domain in {"sales", "support", "store_qa"}:
        return state.domain
    return "store_qa"


def _build_graph(tenant):
    graph = StateGraph(ConversationState)
    graph.add_node("route", lambda state: state)
    graph.add_node("sales", lambda state: run_sales_graph(state, tenant))
    graph.add_node("support", lambda state: run_support_graph(state, tenant))
    graph.add_node("store_qa", lambda state: run_store_qa_graph(state, tenant))

    graph.set_entry_point("route")

    graph.add_conditional_edges(
        "route",
        _select_domain,
        {
            "sales": "sales",
            "support": "support",
            "store_qa": "store_qa",
        },
    )

    graph.add_edge("sales", END)
    graph.add_edge("support", END)
    graph.add_edge("store_qa", END)

    return graph.compile()


def run_main_graph(state: ConversationState, tenant):
    graph = _build_graph(tenant)
    result = graph.invoke(state)
    if isinstance(result, dict):
        return ConversationState(**result)
    return result
