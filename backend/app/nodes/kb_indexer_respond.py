"""KB Indexer Respond Node.

Respond node communicates results to the operator.
Follows AGENT.md: Respond Node apenas comunica, sem lógica de decisão.
"""

from app.core.kb_indexer_state import KBIndexerState


def kb_indexer_respond(state: KBIndexerState) -> KBIndexerState:
    """Generate response message for the operator.
    
    Response format (per spec):
    - Confirmação curta
    - Resultado objetivo
    - Próxima ação clara
    
    This node does NOT execute logic or make decisions.
    """
    
    # Error case
    if state.last_strategy == "error_stop":
        state.response_message = (
            f"Erro durante indexação. "
            f"Último action: {state.last_action}. "
            f"Erro: {state.error_message or 'desconhecido'}. "
            f"Processados antes do erro: {state.processed_count}."
        )
        return state
    
    # All done - no pending records
    if state.last_strategy == "noop_done" and state.processed_count == 0:
        state.response_message = (
            "Não encontrei registros pendentes para indexação. "
            "Sua base já está pronta."
        )
        return state
    
    # Successfully processed records
    if state.processed_count > 0:
        state.response_message = (
            f"Pronto. Indexei {state.processed_count} registros da base. "
            f"Erros: {state.error_count}. "
            "Quer que eu rode o próximo lote?"
        )
        return state
    
    # Fallback
    state.response_message = "Indexação concluída."
    return state
