"""Testes do esqueleto do graph. Validam estrutura, não comportamento de produção.

Usam MemorySaver via monkeypatch (NÃO PostgresSaver), e FakeLLM em vez de OpenAI real.
"""

import pytest
from langchain_core.messages import HumanMessage, AIMessage


class FakeLLM:
    """Fake do LLM bind_tools. Retorna respostas pré-programadas em sequência."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    def invoke(self, messages):
        if self.call_count >= len(self.responses):
            raise RuntimeError(
                f"FakeLLM esgotou respostas (chamou {self.call_count + 1}x)"
            )
        response = self.responses[self.call_count]
        self.call_count += 1
        if isinstance(response, Exception):
            raise response
        return response


def _ai_with_tool(name: str, args: dict, tool_id: str = "tool_1") -> AIMessage:
    """Helper: AIMessage com 1 tool_call estruturado."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": tool_id}],
    )


def _setup_graph(monkeypatch, llm_responses):
    """Patcha checkpointer + LLM + TenantRegistry e zera singleton do graph."""
    from langgraph.checkpoint.memory import MemorySaver
    from app.tests.fakes import FakeTenantConfig, FakeTenantRegistry

    # Singleton de checkpointer compartilhado entre invocações de invoke
    # neste teste — assim o estado persiste entre chamadas.
    memory_saver = MemorySaver()
    monkeypatch.setattr(
        "app.graphs.graph._get_checkpointer", lambda: memory_saver
    )
    monkeypatch.setattr("app.graphs.graph._graph", None)
    monkeypatch.setattr(
        "app.graphs.supervisor._llm_with_tools", FakeLLM(llm_responses)
    )
    # supervisor_node agora resolve tenant a cada turno → mockar TenantRegistry
    # pra não bater no Supabase real.
    fake_tenant = FakeTenantConfig(name="Loja Teste", store_niche="testes")
    monkeypatch.setattr(
        "app.graphs.supervisor.TenantRegistry",
        lambda: FakeTenantRegistry(tenant=fake_tenant),
    )


def test_invoke_returns_direct_response_without_tools(monkeypatch):
    """LLM responde direto (sem tool_calls) → AgentResult com a resposta como bot_message."""
    _setup_graph(monkeypatch, [AIMessage(content="Olá! Como posso ajudar?")])
    from app.graphs import invoke

    result = invoke("t1", "s1", "oi")

    assert result.bot_message == "Olá! Como posso ajudar?"
    assert result.tool_calls == []
    assert result.iterations == 1
    assert result.error is None


def test_invoke_calls_single_tool_then_responds(monkeypatch):
    """LLM chama 1 tool, ToolNode executa stub, LLM responde final."""
    _setup_graph(
        monkeypatch,
        [
            _ai_with_tool("search_products", {"query": "corrente"}),
            AIMessage(content="Achei alguns produtos pra você!"),
        ],
    )
    from app.graphs import invoke

    result = invoke("t1", "s1", "queria ver corrente")

    assert result.tool_calls == ["search_products"]
    assert result.bot_message == "Achei alguns produtos pra você!"
    assert result.iterations == 2
    assert result.error is None


def test_invoke_chains_two_tools_serially(monkeypatch):
    """LLM chama search_products, depois get_product_variants, depois responde."""
    _setup_graph(
        monkeypatch,
        [
            _ai_with_tool("search_products", {"query": "colar"}, tool_id="t1"),
            _ai_with_tool("get_product_variants", {"product_id": "p1"}, tool_id="t2"),
            AIMessage(content="Aqui está, tem em vários tamanhos."),
        ],
    )
    from app.graphs import invoke

    result = invoke("t1", "s1", "quero colar com tamanhos")

    assert result.tool_calls == ["search_products", "get_product_variants"]
    assert result.iterations == 3
    assert result.error is None


def test_invoke_persists_state_between_invocations(monkeypatch):
    """Mesmo session_id em 2 chamadas: messages do state acumula via checkpointer."""
    _setup_graph(
        monkeypatch,
        [
            AIMessage(content="Oi João!"),
            AIMessage(content="Claro, posso ajudar."),
        ],
    )
    from app.graphs import invoke
    from app.graphs.graph import get_graph

    r1 = invoke("t1", "s_persist", "oi, sou o João")
    assert r1.bot_message == "Oi João!"
    assert r1.error is None

    r2 = invoke("t1", "s_persist", "pode me ajudar?")
    assert r2.bot_message == "Claro, posso ajudar."
    assert r2.error is None

    # Inspeção do state via checkpointer: deve ter 4 messages (2 user + 2 AI)
    graph = get_graph()
    config = {"configurable": {"thread_id": "t1:s_persist"}}
    snapshot = graph.get_state(config)
    msgs = snapshot.values["messages"]
    assert len(msgs) == 4
    human_msgs = [m for m in msgs if isinstance(m, HumanMessage)]
    ai_msgs = [m for m in msgs if isinstance(m, AIMessage)]
    assert len(human_msgs) == 2
    assert len(ai_msgs) == 2


def test_invoke_isolates_state_by_session_id(monkeypatch):
    """Sessions diferentes têm threads independentes — state de A não vaza pra B."""
    _setup_graph(
        monkeypatch,
        [
            AIMessage(content="Resposta A"),
            AIMessage(content="Resposta B"),
        ],
    )
    from app.graphs import invoke
    from app.graphs.graph import get_graph

    invoke("t1", "session_A", "mensagem A")
    invoke("t1", "session_B", "mensagem B")

    graph = get_graph()
    state_a = graph.get_state({"configurable": {"thread_id": "t1:session_A"}})
    state_b = graph.get_state({"configurable": {"thread_id": "t1:session_B"}})

    msgs_a = state_a.values["messages"]
    msgs_b = state_b.values["messages"]

    # Cada thread tem só 2 msgs (1 user + 1 AI) — não vazou entre threads
    assert len(msgs_a) == 2
    assert len(msgs_b) == 2
    assert any("mensagem A" in m.content for m in msgs_a if isinstance(m, HumanMessage))
    assert any("mensagem B" in m.content for m in msgs_b if isinstance(m, HumanMessage))
    # Cross-check: thread A não tem "mensagem B"
    assert not any(
        "mensagem B" in m.content for m in msgs_a if isinstance(m, HumanMessage)
    )


def test_invoke_handles_llm_exception_gracefully(monkeypatch):
    """Exception no LLM é capturada — AgentResult com error preenchido, sem propagar."""
    _setup_graph(monkeypatch, [RuntimeError("simulated LLM crash")])
    from app.graphs import invoke

    result = invoke("t1", "s_err", "oi")

    assert result.error is not None
    assert "simulated LLM crash" in result.error
    assert result.bot_message == ""
    assert result.iterations == 0


# ─── System prompt dinâmico por tenant (Fase 3) ───────────────────────

def test_system_prompt_uses_store_name_and_niche():
    """_build_system_prompt injeta name e store_niche no template."""
    from app.graphs.supervisor import _build_system_prompt
    from app.tests.fakes import FakeTenantConfig

    tenant = FakeTenantConfig(name="Loja XYZ", store_niche="joias premium")
    prompt = _build_system_prompt(tenant)

    assert "Loja XYZ" in prompt
    assert "joias premium" in prompt


def test_system_prompt_uses_custom_brand_voice_when_set():
    """brand_voice preenchido sobrescreve o default voice section."""
    from app.graphs.supervisor import _build_system_prompt
    from app.tests.fakes import FakeTenantConfig

    tenant = FakeTenantConfig(brand_voice="Bem informal, gírias OK")
    prompt = _build_system_prompt(tenant)

    assert "Bem informal, gírias OK" in prompt
    # Default não aparece (substring única do default)
    assert "cordial, direto" not in prompt


def test_system_prompt_falls_back_to_default_voice_when_none():
    """brand_voice=None → prompt usa _DEFAULT_BRAND_VOICE_SECTION."""
    from app.graphs.supervisor import _build_system_prompt
    from app.tests.fakes import FakeTenantConfig

    tenant = FakeTenantConfig(brand_voice=None)
    prompt = _build_system_prompt(tenant)

    assert "cordial, direto" in prompt


def test_system_prompt_injects_store_policies_when_set():
    """store_policies_summary preenchido aparece literalmente no prompt."""
    from app.graphs.supervisor import _build_system_prompt
    from app.tests.fakes import FakeTenantConfig

    policies = "Frete grátis acima R$200. Troca em 15 dias."
    tenant = FakeTenantConfig(store_policies_summary=policies)
    prompt = _build_system_prompt(tenant)

    assert "Frete grátis acima R$200" in prompt
    assert "Troca em 15 dias" in prompt


def test_supervisor_node_uses_dynamic_system_prompt_per_tenant(monkeypatch):
    """Cada turno resolve tenant fresh e injeta system prompt customizado."""
    from app.graphs.supervisor import supervisor_node
    from app.tests.fakes import FakeTenantConfig, FakeTenantRegistry

    # 2 tenants com brand_voice distintos
    tenants = {
        "tenantA": FakeTenantConfig(name="A", brand_voice="formal e técnico"),
        "tenantB": FakeTenantConfig(name="B", brand_voice="descontraído e direto"),
    }

    class _RoutingRegistry:
        def get(self, tenant_id, use_cache=True):
            return tenants[tenant_id]

    monkeypatch.setattr(
        "app.graphs.supervisor.TenantRegistry", lambda: _RoutingRegistry()
    )

    # FakeLLM que captura messages recebidas
    captured = []

    class _CapturingLLM:
        def invoke(self, messages):
            captured.append(messages)
            return AIMessage(content="ok")

    monkeypatch.setattr(
        "app.graphs.supervisor._llm_with_tools", _CapturingLLM()
    )

    # Chamada 1: tenantA
    supervisor_node({
        "tenant_id": "tenantA",
        "messages": [HumanMessage(content="oi")],
    })

    # Chamada 2: tenantB
    supervisor_node({
        "tenant_id": "tenantB",
        "messages": [HumanMessage(content="oi")],
    })

    # SystemMessage é a primeira de cada chamada
    sys_msg_a = captured[0][0]
    sys_msg_b = captured[1][0]

    assert "formal e técnico" in sys_msg_a.content
    assert "descontraído e direto" in sys_msg_b.content
    # Cross-check: não vazou entre tenants
    assert "descontraído" not in sys_msg_a.content
    assert "formal" not in sys_msg_b.content


# ─── Escopo de atuação (anti off-topic) ────────────────────────────────

def test_system_prompt_includes_scope_restriction_section():
    """Template inclui seção ESCOPO DE ATUAÇÃO com restrições + exceção de saudação."""
    from app.graphs.supervisor import _build_system_prompt
    from app.tests.fakes import FakeTenantConfig

    tenant = FakeTenantConfig()
    prompt = _build_system_prompt(tenant)

    assert "ESCOPO DE ATUAÇÃO" in prompt
    assert "NÃO responde sobre" in prompt
    assert "entretenimento" in prompt.lower() or "filmes" in prompt.lower()
    assert (
        "SAUDAÇÕES SOCIAIS" in prompt.upper()
        or "saudações sociais" in prompt.lower()
    )


def test_system_prompt_scope_uses_store_name_placeholder():
    """store_name aparece >= 2x: na identificação inicial E na seção de escopo."""
    from app.graphs.supervisor import _build_system_prompt
    from app.tests.fakes import FakeTenantConfig

    tenant = FakeTenantConfig(name="Loja XYZ")
    prompt = _build_system_prompt(tenant)

    assert prompt.count("Loja XYZ") >= 2


# ─── Formato de resposta (anti UUID-leak + WhatsApp markdown) ──────────

def test_system_prompt_includes_no_id_exposure_rule():
    """Template instrui o LLM a NÃO expor UUIDs/IDs internos ao cliente."""
    from app.graphs.supervisor import _build_system_prompt
    from app.tests.fakes import FakeTenantConfig

    tenant = FakeTenantConfig()
    prompt = _build_system_prompt(tenant)

    assert (
        "IDs internos" in prompt
        or "UUID" in prompt
        or "NUNCA exiba IDs" in prompt
    )
    assert "USO INTERNO" in prompt or "uso interno" in prompt


def test_system_prompt_includes_whatsapp_markdown_rule():
    """Template instrui sintaxe markdown do WhatsApp (1 asterisco), não Markdown padrão."""
    from app.graphs.supervisor import _build_system_prompt
    from app.tests.fakes import FakeTenantConfig

    tenant = FakeTenantConfig()
    prompt = _build_system_prompt(tenant)

    assert "WhatsApp" in prompt
    assert "UM asterisco" in prompt or "*uma palavra*" in prompt
    assert "negrito duplo" in prompt.lower() or "**negrito**" in prompt


# ─── Estilo de conversa (anti-robô / anti-telemarketing) ───────────────

def test_system_prompt_includes_conversation_style_section():
    """Template inclui seção ESTILO DE CONVERSA com regras de tamanho e anti-meta."""
    from app.graphs.supervisor import _build_system_prompt
    from app.tests.fakes import FakeTenantConfig

    tenant = FakeTenantConfig()
    prompt = _build_system_prompt(tenant)

    assert "ESTILO DE CONVERSA" in prompt
    # Regra de tamanho pra conversa casual
    assert "1-2 frases" in prompt
    # Regra anti-meta (não narrar o próprio entendimento)
    assert "não consegui entender" in prompt.lower()
    # Regra anti-telemarketing (limite de exclamação)
    assert "ANTI-TELEMARKETING" in prompt
    assert "UMA exclamação" in prompt
    # Tolerância a typo sem comentar
    assert "digitação" in prompt.lower()


def test_system_prompt_includes_style_fewshots():
    """Template inclui few-shots RUIM/BOM cobrindo saudação, typo e despedida."""
    from app.graphs.supervisor import _build_system_prompt
    from app.tests.fakes import FakeTenantConfig

    tenant = FakeTenantConfig(name="Loja XYZ")
    prompt = _build_system_prompt(tenant)

    assert "EXEMPLOS DE ESTILO" in prompt
    assert prompt.count("RUIM:") >= 3
    assert prompt.count("BOM:") >= 3
    # Exemplos cobrem os casos-chave
    assert "pdoruis" in prompt  # typo absorvido em silêncio
    assert "obrigado" in prompt.lower()  # despedida sem efusividade
    # Few-shot usa o nome real da loja (placeholder resolvido)
    assert "Seja muito bem-vindo à Loja XYZ" in prompt
