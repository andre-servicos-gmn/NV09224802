from langgraph.graph import END, StateGraph

from app.core.state import ConversationState
from app.nodes.action_answer_faq import action_answer_faq
from app.nodes.handoff import handoff
from app.nodes.store_qa_decide import store_qa_decide
from app.nodes.store_qa_respond import store_qa_respond


def _build_graph(tenant):
    graph = StateGraph(ConversationState)
    graph.add_node("store_qa_decide", lambda state: store_qa_decide(state, tenant))
    graph.add_node("action_answer_faq", lambda state: action_answer_faq(state, tenant))
    graph.add_node("handoff", lambda state: handoff(state, tenant))
    graph.add_node("store_qa_respond", lambda state: store_qa_respond(state, tenant))

    graph.set_entry_point("store_qa_decide")

    graph.add_conditional_edges(
        "store_qa_decide",
        lambda state: state.next_step,
        {
            "action_answer_faq": "action_answer_faq",
            "handoff": "handoff",
            "store_qa_respond": "store_qa_respond",
        },
    )

    graph.add_edge("action_answer_faq", "store_qa_respond")
    graph.add_edge("handoff", END)
    graph.add_edge("store_qa_respond", END)

    return graph.compile()


def run_store_qa_graph(state: ConversationState, tenant):
    graph = _build_graph(tenant)
    result = graph.invoke(state)
    if isinstance(result, dict):
        return ConversationState(**result)
    return result
