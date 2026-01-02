from langgraph.graph import END, StateGraph

from app.core.state import ConversationState
from app.nodes.action_lookup_order import action_lookup_order
from app.nodes.action_open_ticket import action_open_ticket
from app.nodes.support_decide import support_decide
from app.nodes.support_respond import support_respond


def _build_graph(tenant):
    graph = StateGraph(ConversationState)
    graph.add_node("support_decide", lambda state: support_decide(state, tenant))
    graph.add_node("action_lookup_order", lambda state: action_lookup_order(state, tenant))
    graph.add_node("action_open_ticket", lambda state: action_open_ticket(state, tenant))
    graph.add_node("support_respond", lambda state: support_respond(state, tenant))

    graph.set_entry_point("support_decide")

    graph.add_conditional_edges(
        "support_decide",
        lambda state: state.next_step,
        {
            "action_lookup_order": "action_lookup_order",
            "action_open_ticket": "action_open_ticket",
            "support_respond": "support_respond",
        },
    )

    graph.add_edge("action_lookup_order", "support_decide")
    graph.add_edge("action_open_ticket", "support_respond")
    graph.add_edge("support_respond", END)

    return graph.compile()


def run_support_graph(state: ConversationState, tenant):
    graph = _build_graph(tenant)
    result = graph.invoke(state)
    if isinstance(result, dict):
        return ConversationState(**result)
    return result
