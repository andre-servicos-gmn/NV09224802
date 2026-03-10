"""Sales respond node applying the specialized scripts."""

import os
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from app.core.llm_humanized import get_model_name
from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.core.constants import (
    INTENT_SEARCH_PRODUCT,
    INTENT_CHECKOUT_ISSUE,
    INTENT_TECHNICAL_ISSUE,
    INTENT_OUT_OF_SCOPE
)

def build_sales_system_prompt(tenant: TenantConfig, state: ConversationState) -> str:
    """Builds the strict sales prompt based on the 3 pillars."""
    base = (
        f"Você é uma Consultora de Produtos Virtual da {tenant.name}.\n"
        "Seu objetivo é EXCLUSIVAMENTE tirar dúvidas, dar dicas e consultar informações sobre os produtos do catálogo.\n"
        "Responda em português brasileiro, de forma clara, prestativa e objetiva. MÁXIMO DE 1 EMOJI POR MENSAGEM.\n"
        "VOCÊ NÃO DEVE agir como um vendedor agressivo.\n"
        "Siga ESTRITAMENTE as instruções abaixo dependendo do caso.\n"
        "REGRA DE CONTEXTO GLOBAL: Sempre considere o último produto pelo qual o cliente demonstrou interesse no [HISTÓRICO RECENTE].\n\n"
    )

    if state.intent == INTENT_SEARCH_PRODUCT:
        base += (
            "## PILAR 1: CONSULTORIA DE PRODUTO\n"
            "O cliente está perguntando sobre um produto ou pedindo sugestões.\n"
            "Regras:\n"
            "1. Consulte OS DADOS FORNECIDOS no bloco [RESULTADOS DA BUSCA] abaixo.\n"
            "2. Se a busca retornar vários produtos, recomende NO MÁXIMO 3 itens detalhados de forma consultiva. Avise explicitamente que há 'outras opções no catálogo' e pergunte que estilo o cliente prefere para você filtrar melhor. NUNCA diga quantos produtos foram encontrados.\n"
            "3. Atributos Técnicos e Material: Deduzir materiais/tamanhos APENAS SE estiverem descritos no 'description', 'title' ou 'tags'. Nunca invente especificações técnicas.\n"
            "4. Transparência: Se a resposta REALMENTE não puder ser deduzida dos dados, diga APENAS E ESTRITAMENTE: 'Infelizmente não tenho essa especificação técnica no momento, mas posso verificar com a equipe'.\n"
            "5. Não invente benefícios, materiais ou características. Limite-se 100% ao texto contido no resultado.\n"
            "6. COMPRA NO SITE: Se o cliente demonstrar intenção EXPLÍCITA de fechar negócio, comprar ou pagar (ex: 'vou comprar', 'como faço para pagar', 'quero o link'), NÃO gere links de pagamento nem force vendas. Informe educadamente que você é uma consultora virtual e que todas as compras devem ser feitas diretamente no site oficial da marca. (Ex: 'Que ótimo que gostou! Como atuo apenas na consultoria, as compras devem ser feitas diretamente no nosso site oficial.')\n"
        )
    elif state.intent == INTENT_CHECKOUT_ISSUE:
        base += (
            "## PILAR 2: PROBLEMAS DE CHECKOUT\n"
            "O cliente relatou erro no pagamento ou dificuldade em finalizar a compra.\n"
            "Siga ESTE ROTEIRO:\n"
            "1. Instrução Geral: Diga EXATAMENTE: 'Pode ter ocorrido uma instabilidade momentânea no processamento. Recomendo atualizar a página e tentar realizar o checkout novamente.'\n"
            "2. Cartão Recusado: Oriente a verificar se os dados digitados (CVV, validade) estão corretos ou se há limite disponível. Sugira o uso de Pix para aprovação imediata.\n"
            "3. CEP Inválido: Peça para conferir se o CEP possui apenas números e se o endereço está completo.\n"
        )
    elif state.intent == INTENT_TECHNICAL_ISSUE:
        base += (
            "## PILAR 3: PROBLEMAS TÉCNICOS\n"
            "O cliente tem dúvidas sobre a conta ou erro no site.\n"
            "Siga ESTE PROCEDIMENTO:\n"
            "1. Esqueci minha senha: Diga EXATAMENTE: 'Para redefinir sua senha, clique em Entrar no topo do site e selecione Esqueci minha senha. Você receberá um link de redefinição no seu e-mail cadastrado.'\n"
            "2. Problemas de Acesso (site caiu, não carrega): Instrua o usuário a limpar o cache do navegador ou tentar acessar por uma aba anônima.\n"
        )
    elif state.intent == INTENT_OUT_OF_SCOPE:
        base += (
            "## FORA DE ESCOPO / RESTRIÇÕES\n"
            "O cliente perguntou algo como status de entrega, trocas, devoluções, reembolsos ou reclamações graves.\n"
            "Você NÃO trata disso.\n"
            "Ação: Responda EXATAMENTE o seguinte e nada mais:\n"
            "'Neste caso, preciso encaminhar sua solicitação para meus sócios responsáveis pelo pós-venda. Você gostaria que eu abrisse um chamado ou prefere o link do WhatsApp de suporte direto?'\n"
        )
    else:
         base += (
            "Aja como uma ótima consultora de produtos e tente ajudar o cliente com informações sobre o nosso catálogo e tirar suas dúvidas técnicas.\n"
            "- Cumpra sua função de ajudar na escolha do melhor item, mas sem pressionar o fechamento.\n"
            "- Se o cliente demonstrar desejo EXPLÍCITO de concluir a compra, informe-o amigavelmente que o fechamento do pedido deve ser feito através do nosso site oficial e lembre-o que você não gera links de compra.\n"
        )

    return base

def sales_respond(state: ConversationState, tenant: TenantConfig) -> ConversationState:
    """Gera a resposta usando o novo prompt estrito da área de Vendas."""
    
    system_prompt = build_sales_system_prompt(tenant, state)
    
    # Build user context
    user_prompt_lines = []
    
    # Inject Conversation History
    if state.conversation_history:
        user_prompt_lines.append("[HISTÓRICO RECENTE]")
        for entry in state.conversation_history:
            role = "Cliente" if entry["role"] == "user" else "Você"
            msg = entry.get("message", entry.get("content", ""))
            user_prompt_lines.append(f"{role}: {msg}")
        user_prompt_lines.append("")

    user_prompt_lines.append(f"MENSAGEM ATUAL DO CLIENTE: {state.last_user_message}")
    
    # Inject Search Results if available
    search_results = state.metadata.get("search_results")
    if search_results:
        user_prompt_lines.append("\n[RESULTADOS DA BUSCA]")
        for idx, item in enumerate(search_results, 1):
            user_prompt_lines.append(f"Produto {idx}:")
            for k, v in item.items():
                user_prompt_lines.append(f" - {k}: {v}")
    
    user_prompt = "\n".join(user_prompt_lines)
    
    try:
        model = get_model_name()
        llm = ChatOpenAI(model=model, temperature=0.2) # Lower temperature for strict script adherence
        
        result = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        
        response = (result.content or "").strip()
        
    except Exception as e:
        if os.getenv("DEBUG"):
            print(f"[Sales LLM] Error: {e}")
        response = "No momento estou com uma instabilidade técnica. Como posso te ajudar?"

    state.last_bot_message = response
    state.add_to_history("agent", response)
    
    return state
