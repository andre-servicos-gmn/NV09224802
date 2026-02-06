from pydantic import BaseModel, Field
from typing import List, Dict, Optional

class ConversationState(BaseModel):
    # --- IDENTIFICAÇÃO ---
    tenant_id: str
    session_id: str
    personality_id: str = "professional"
    channel: str = "whatsapp"
    
    # --- CÉREBRO E INTENÇÃO ---
    domain: Optional[str] = None          # sales | support | store_qa
    intent: str = "general"               # checkout_error, search_product, etc.
    confidence_score: float = 0.0         # 0.0 a 1.0 (Para decidir Handoff)
    
    # --- MEMÓRIA DE VENDAS (SALES CONTEXT) ---
    search_query: Optional[str] = None
    selected_products: List[dict] = Field(default_factory=list)
    available_variants: List[dict] = Field(default_factory=list)
    cart_items: List[dict] = Field(default_factory=list)
    
    # [NOVO] O Link Sagrado - Diferente de tracking_url!
    checkout_link: Optional[str] = None   
    
    # --- MEMÓRIA DE SUPORTE (SUPPORT CONTEXT) ---
    order_id: Optional[str] = None
    customer_email: Optional[str] = None
    tracking_url: Optional[str] = None    # Link dos Correios/Loggi
    refund_status: Optional[str] = None   # [NOVO] Para o agente saber se foi aprovado
    original_complaint: Optional[str] = None
    
    # --- MEMÓRIA COGNITIVA (A Mágica Nova) ---
    # Fatos Rígidos (CPF, CEP, IDs) - O que o prompt de memória extrai como 'hard_facts'
    facts: Dict = Field(default_factory=dict) 
    
    # [NOVO] Contexto Suave (Motivação, Urgência) - O que o prompt de memória extrai como 'soft_context'
    soft_context: Dict = Field(default_factory=dict) 
    
    # [NOVO] O que falta para fechar a ação (Ex: ["tamanho", "cor"])
    blocking_info: List[str] = Field(default_factory=list)
    
    # [NOVO] Texto recuperado do RAG (Supabase) para o Humanizer ler
    rag_context: Optional[str] = None 
    
    # --- ESTADO EMOCIONAL E CONTROLE ---
    frustration_level: int = 0
    sentiment_level: str = "calm"         # calm | frustrated | angry
    sentiment_score: float = 0.0          # -1.0 (Fúria) a 1.0 (Amor)
    needs_handoff: bool = False
    handoff_reason: Optional[str] = None
    
    # --- FLUXO DE MENSAGEM ---
    last_user_message: Optional[str] = None
    last_bot_message: Optional[str] = None
    
    # [NOVO] Erro técnico do sistema (Ex: "API Checkout Timeout"). 
    # Diferente de erro do usuário. O Humanizer usa isso para pedir desculpas.
    system_error: Optional[str] = None    
    
    # --- FLUXO DO GRAFO (Graph Flow) ---
    next_step: Optional[str] = None         # Para decidir qual nó executar
    last_action: Optional[str] = None       # Último nó/ação executada
    last_strategy: Optional[str] = None     # Estratégia atual (ex: "permalink", "add_to_cart")
    
    last_action_success: Optional[bool] = None
    
    # --- CAMPOS LEGADOS (Para retrocompatibilidade) ---
    tracking_last_update_days: Optional[int] = None  # Usado em router.py
    
    # Histórico para o LLM (Janela deslizante)
    conversation_history: List[dict] = Field(default_factory=list)

    # --- MÉTODOS UTILITÁRIOS ---

    def bump_frustration(self) -> None:
        self.frustration_level += 1

    def add_to_history(self, role: str, message: str) -> None:
        """Adiciona mensagem e mantém a janela de contexto limpa (últimas 20)."""
        self.conversation_history.append({"role": role, "message": message})
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]
            
        # Captura de reclamação persistente (Lógica mantida, é boa)
        if role == "user" and not self.original_complaint:
            keywords = ["errado", "problema", "reclamação", "atrasado", "não chegou", "defeito", "quebrado"]
            if any(w in message.lower() for w in keywords):
                self.original_complaint = message

    def clear_rag_context(self):
        """Limpa o contexto RAG para não contaminar a próxima resposta"""
        self.rag_context = None

    def set_intent(self, intent: str) -> None:
        """Define a intenção e limpa estados incompatíveis se necessário."""
        self.intent = intent
        # Se mudar para uma intenção que não seja de suporte, podemos limpar erros antigos de pedido
        if intent not in ["order_status", "order_tracking", "order_complaint"]:
             if "order_error" in self.soft_context:
                 del self.soft_context["order_error"]
