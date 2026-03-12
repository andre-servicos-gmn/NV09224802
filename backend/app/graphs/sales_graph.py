# Sales graph — Consultant mode (search + respond only).
from langgraph.graph import END, StateGraph

from app.core.state import ConversationState
from app.nodes.action_search_products import action_search_products
from app.nodes.decide import decide
from app.nodes.handoff import handoff
from app.nodes.respond import respond


def _build_graph(tenant):
    graph = StateGraph(ConversationState)
    graph.add_node("decide", lambda state: decide(state, tenant))
    graph.add_node("action_search_products", lambda state: action_search_products(state, tenant))
    graph.add_node("respond", lambda state: respond(state, tenant))
    graph.add_node("handoff", lambda state: handoff(state, tenant))

    graph.set_entry_point("decide")

    graph.add_conditional_edges(
        "decide",
        lambda state: state.next_step,
        {
            "action_search_products": "action_search_products",
            "respond": "respond",
            "handoff": "handoff",
        },
    )

    graph.add_edge("action_search_products", "respond")
    graph.add_edge("respond", END)
    graph.add_edge("handoff", END)

    return graph.compile()


def run_sales_graph(state: ConversationState, tenant):
    graph = _build_graph(tenant)
    result = graph.invoke(state)
    if isinstance(result, dict):
        return ConversationState(**result)
    return result
