from langgraph.graph import END, StateGraph

from app.core.state import ConversationState
from app.nodes.action_generate_link import action_generate_link
from app.nodes.action_resolve_product import action_resolve_product
from app.nodes.decide import decide
from app.nodes.handoff import handoff
from app.nodes.respond import respond


def _build_graph(tenant):
    graph = StateGraph(ConversationState)
    graph.add_node("decide", lambda state: decide(state, tenant))
    graph.add_node("action_resolve_product", lambda state: action_resolve_product(state, tenant))
    graph.add_node("action_generate_link", lambda state: action_generate_link(state, tenant))
    graph.add_node("respond", lambda state: respond(state, tenant))
    graph.add_node("handoff", lambda state: handoff(state, tenant))

    graph.set_entry_point("decide")

    graph.add_conditional_edges(
        "decide",
        lambda state: state.next_step,
        {
            "action_resolve_product": "action_resolve_product",
            "action_generate_link": "action_generate_link",
            "respond": "respond",
            "handoff": "handoff",
        },
    )

    graph.add_edge("action_resolve_product", "respond")
    graph.add_edge("action_generate_link", "respond")
    graph.add_edge("respond", END)
    graph.add_edge("handoff", END)

    return graph.compile()


def run_sales_graph(state: ConversationState, tenant):
    graph = _build_graph(tenant)
    result = graph.invoke(state)
    if isinstance(result, dict):
        return ConversationState(**result)
    return result
