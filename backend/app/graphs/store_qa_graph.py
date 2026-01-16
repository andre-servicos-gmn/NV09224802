"""Store Q&A graph - with memory update and RAG."""

from langgraph.graph import END, StateGraph

from app.core.state import ConversationState
from app.nodes.handoff import handoff
from app.nodes.store_qa_decide import store_qa_decide
from app.nodes.store_qa_respond import store_qa_respond
from app.nodes.store_qa_update_memory import store_qa_update_memory


def _build_graph(tenant):
    graph = StateGraph(ConversationState)
    graph.add_node("update_memory", lambda state: store_qa_update_memory(state, tenant))
    graph.add_node("store_qa_decide", lambda state: store_qa_decide(state, tenant))
    graph.add_node("handoff", lambda state: handoff(state, tenant))
    graph.add_node("store_qa_respond", lambda state: store_qa_respond(state, tenant))

    # Flow: Entry → update_memory → decide → [handoff | respond]
    graph.set_entry_point("update_memory")
    graph.add_edge("update_memory", "store_qa_decide")

    graph.add_conditional_edges(
        "store_qa_decide",
        lambda state: state.next_step,
        {
            "handoff": "handoff",
            "store_qa_respond": "store_qa_respond",
        },
    )

    graph.add_edge("handoff", END)
    graph.add_edge("store_qa_respond", END)

    return graph.compile()


def run_store_qa_graph(state: ConversationState, tenant):
    graph = _build_graph(tenant)
    result = graph.invoke(state)
    if isinstance(result, dict):
        return ConversationState(**result)
    return result

