"""
Script de teste manual do Sales Agent.
Simula fluxos de vendas sem depender de API real da Shopify.
"""
from app.core.state import ConversationState
from app.core.constants import (
    INTENT_PRODUCT_LINK,
    INTENT_SEARCH_PRODUCT,
    INTENT_SELECT_PRODUCT,
    INTENT_SELECT_VARIANT,
    INTENT_PURCHASE_INTENT,
    INTENT_CART_RETRY,
    INTENT_CHECKOUT_ERROR,
)
from app.nodes.decide import decide
from app.core.tenancy import TenantRegistry


def test_decide_logic():
    """Testa a lógica de decisão do Sales Agent."""
    print("\n=== TESTE 1: Lógica de Decisão ===\n")
    
    # Mock tenant simples
    class MockTenant:
        tenant_id = "demo"
        store_domain = "example.myshopify.com"
        shopify_access_token = "fake-token"
        shopify_api_version = "2024-01"
        default_link_strategy = "permalink"
    
    tenant = MockTenant()
    
    # Teste 1: INTENT_PRODUCT_LINK deve ir para action_resolve_product
    state = ConversationState(tenant_id="demo", session_id="test")
    state.intent = INTENT_PRODUCT_LINK
    result = decide(state, tenant)
    assert result.next_step == "action_resolve_product", f"Esperado 'action_resolve_product', obtido '{result.next_step}'"
    print("✓ INTENT_PRODUCT_LINK → action_resolve_product")
    
    # Teste 2: INTENT_SEARCH_PRODUCT deve ir para action_search_products
    state = ConversationState(tenant_id="demo", session_id="test")
    state.intent = INTENT_SEARCH_PRODUCT
    result = decide(state, tenant)
    assert result.next_step == "action_search_products", f"Esperado 'action_search_products', obtido '{result.next_step}'"
    print("✓ INTENT_SEARCH_PRODUCT → action_search_products")
    
    # Teste 3: INTENT_SELECT_PRODUCT com produtos disponíveis
    state = ConversationState(tenant_id="demo", session_id="test")
    state.intent = INTENT_SELECT_PRODUCT
    state.selected_products = [{"product_id": "123", "title": "Produto Teste"}]
    result = decide(state, tenant)
    assert result.next_step == "action_select_product", f"Esperado 'action_select_product', obtido '{result.next_step}'"
    print("✓ INTENT_SELECT_PRODUCT (com produtos) → action_select_product")
    
    # Teste 4: INTENT_SELECT_PRODUCT sem produtos disponíveis
    state = ConversationState(tenant_id="demo", session_id="test")
    state.intent = INTENT_SELECT_PRODUCT
    state.selected_products = []
    result = decide(state, tenant)
    assert result.next_step == "respond", f"Esperado 'respond', obtido '{result.next_step}'"
    print("✓ INTENT_SELECT_PRODUCT (sem produtos) → respond")
    
    # Teste 5: INTENT_SELECT_VARIANT com variantes disponíveis
    state = ConversationState(tenant_id="demo", session_id="test")
    state.intent = INTENT_SELECT_VARIANT
    state.available_variants = [{"variant_id": "456", "title": "P"}]
    result = decide(state, tenant)
    assert result.next_step == "action_select_variant", f"Esperado 'action_select_variant', obtido '{result.next_step}'"
    print("✓ INTENT_SELECT_VARIANT (com variantes) → action_select_variant")
    
    # Teste 6: INTENT_PURCHASE_INTENT com variante selecionada
    state = ConversationState(tenant_id="demo", session_id="test")
    state.intent = INTENT_PURCHASE_INTENT
    state.selected_variant_id = "789"
    result = decide(state, tenant)
    assert result.next_step == "action_generate_link", f"Esperado 'action_generate_link', obtido '{result.next_step}'"
    print("✓ INTENT_PURCHASE_INTENT (com variante) → action_generate_link")
    
    # Teste 7: INTENT_PURCHASE_INTENT sem variante selecionada
    state = ConversationState(tenant_id="demo", session_id="test")
    state.intent = INTENT_PURCHASE_INTENT
    state.selected_variant_id = None
    result = decide(state, tenant)
    assert result.next_step == "respond", f"Esperado 'respond', obtido '{result.next_step}'"
    print("✓ INTENT_PURCHASE_INTENT (sem variante) → respond")
    
    # Teste 8: Frustração alta deve ir para handoff
    state = ConversationState(tenant_id="demo", session_id="test")
    state.frustration_level = 3
    result = decide(state, tenant)
    assert result.next_step == "handoff", f"Esperado 'handoff', obtido '{result.next_step}'"
    print("✓ frustration_level >= 3 → handoff")
    
    # Teste 9: needs_handoff deve ir para handoff
    state = ConversationState(tenant_id="demo", session_id="test")
    state.needs_handoff = True
    result = decide(state, tenant)
    assert result.next_step == "handoff", f"Esperado 'handoff', obtido '{result.next_step}'"
    print("✓ needs_handoff = True → handoff")
    
    print("\n✅ Todos os testes de decisão passaram!\n")


def test_strategy_escalation():
    """Testa a escalação de estratégias de checkout."""
    print("\n=== TESTE 2: Escalação de Estratégias ===\n")
    
    from app.core.strategies import next_strategy
    
    # Teste sequência de estratégias
    assert next_strategy(None) == "permalink"
    print("✓ None → permalink")
    
    assert next_strategy("permalink") == "add_to_cart"
    print("✓ permalink → add_to_cart")
    
    assert next_strategy("add_to_cart") == "checkout_direct"
    print("✓ add_to_cart → checkout_direct")
    
    assert next_strategy("checkout_direct") == "human_handoff"
    print("✓ checkout_direct → human_handoff")
    
    assert next_strategy("human_handoff") == "human_handoff"
    print("✓ human_handoff → human_handoff (permanece)")
    
    print("\n✅ Escalação de estratégias funciona corretamente!\n")


def test_state_management():
    """Testa o gerenciamento de estado."""
    print("\n=== TESTE 3: Gerenciamento de Estado ===\n")
    
    state = ConversationState(tenant_id="demo", session_id="test")
    
    # Teste valores padrão
    assert state.frustration_level == 0
    assert state.quantity == 1
    assert state.selected_products == []
    assert state.available_variants == []
    print("✓ Valores padrão corretos")
    
    # Teste bump_frustration
    state.bump_frustration()
    assert state.frustration_level == 1
    state.bump_frustration()
    assert state.frustration_level == 2
    print("✓ bump_frustration() incrementa corretamente")
    
    # Teste set_intent
    state.set_intent(INTENT_SEARCH_PRODUCT)
    assert state.intent == INTENT_SEARCH_PRODUCT
    print("✓ set_intent() funciona")
    
    # Teste metadata
    state.metadata["test_key"] = "test_value"
    assert state.metadata["test_key"] == "test_value"
    print("✓ metadata funciona")
    
    print("\n✅ Gerenciamento de estado funciona corretamente!\n")


def test_checkout_link_generation():
    """Testa a geração de links de checkout."""
    print("\n=== TESTE 4: Geração de Links de Checkout ===\n")
    
    from app.tools.shopify_client import ShopifyClient
    
    client = ShopifyClient(
        store_domain="example.myshopify.com",
        access_token="fake-token",
        api_version="2024-01"
    )
    
    variant_id = "12345"
    quantity = 2
    
    # Teste permalink
    link = client.build_checkout_link(variant_id, quantity, "permalink")
    assert link == "https://example.myshopify.com/cart/12345:2"
    print(f"✓ permalink: {link}")
    
    # Teste add_to_cart
    link = client.build_checkout_link(variant_id, quantity, "add_to_cart")
    assert "https://example.myshopify.com/cart/add" in link
    assert "id=12345" in link
    assert "quantity=2" in link
    assert "return_to=%2Fcheckout" in link
    print(f"✓ add_to_cart: {link}")
    
    # Teste checkout_direct
    link = client.build_checkout_link(variant_id, quantity, "checkout_direct")
    assert link == "https://example.myshopify.com/checkout?variant=12345&quantity=2"
    print(f"✓ checkout_direct: {link}")
    
    # Teste human_handoff
    link = client.build_checkout_link(variant_id, quantity, "human_handoff")
    assert link == ""
    print("✓ human_handoff: (string vazia)")
    
    print("\n✅ Geração de links funciona corretamente!\n")


def test_url_handle_extraction():
    """Testa extração de handle de URLs."""
    print("\n=== TESTE 5: Extração de Handle de URLs ===\n")
    
    from app.tools.shopify_client import ShopifyClient
    
    client = ShopifyClient(
        store_domain="example.myshopify.com",
        access_token="fake-token"
    )
    
    # Teste URLs válidas
    assert client._extract_handle_from_url("https://loja.com/products/colar-dourado") == "colar-dourado"
    print("✓ URL simples: colar-dourado")
    
    assert client._extract_handle_from_url("https://loja.com/products/colar?variant=123") == "colar"
    print("✓ URL com query string: colar")
    
    assert client._extract_handle_from_url("https://loja.com/products/produto-teste#section") == "produto-teste"
    print("✓ URL com fragment: produto-teste")
    
    # Teste URL inválida
    assert client._extract_handle_from_url("https://loja.com/invalid") is None
    print("✓ URL inválida: None")
    
    print("\n✅ Extração de handle funciona corretamente!\n")


def test_variant_selection_extraction():
    """Testa extração de número de seleção."""
    print("\n=== TESTE 6: Extração de Número de Seleção ===\n")
    
    from app.nodes.action_select_product import _extract_selection
    
    # Teste números válidos (1-99)
    assert _extract_selection("1") == 1
    assert _extract_selection("quero o 12") == 12
    assert _extract_selection("99") == 99
    print("✓ Números 1-99 extraídos corretamente")
    
    # Teste números inválidos
    assert _extract_selection("0") is None
    assert _extract_selection("100") is None  # Regex limita a 2 digitos
    assert _extract_selection("abc") is None
    print("✓ Números inválidos retornam None")
    
    print("\n✅ Extração de seleção funciona corretamente!\n")


def test_link_duplication_fix():
    """Testa a correção de duplicação de links."""
    print("\n=== TESTE 7: Correção de Duplicação de Links ===\n")
    
    from app.nodes.respond import _ensure_link_once
    
    link = "https://loja.com/cart/123"
    
    # Caso 1: Link não presente
    msg = "Olá"
    assert _ensure_link_once(msg, link) == f"Olá\n\n{link}"
    print("✓ Adiciona link se não existir")
    
    # Caso 2: Link já presente uma vez
    msg = f"Olá, aqui o link: {link}"
    assert _ensure_link_once(msg, link) == msg
    print("✓ Mantém se existir uma vez")
    
    # Caso 3: Link duplicado
    msg = f"Olá {link} e aqui de novo {link}"
    expected = f"Olá {link} e aqui de novo"
    # A implementação mantém a primeira ocorrência e remove as outras
    # "Olá {link} e aqui de novo {link}" -> split -> ["Olá ", " e aqui de novo ", ""]
    # result = "Olá " + link + " e aqui de novo " + "" -> "Olá {link} e aqui de novo "
    assert _ensure_link_once(msg, link).strip() == expected.strip()
    print("✓ Remove duplicatas extras")
    
    print("\n✅ Deduplicação de links funciona corretamente!\n")




def test_metadata_clearing():
    """Testa se metadados de outros domínios são limpos na busca."""
    print("\n=== TESTE 8: Limpeza de Metadados (Search) ===\n")
    
    from app.nodes.action_search_products import action_search_products
    
    # Mock Tenant
    class MockTenant:
        store_domain = "example.myshopify.com"
        shopify_access_token = "fake"
        shopify_api_version = "2024-01"

    tenant = MockTenant()
    
    # Estado com lixo de outros domínios
    state = ConversationState(tenant_id="demo", session_id="test")
    state.search_query = "camiseta"
    state.metadata = {
        "tracking_url": "http://track.me",
        "order_id": "123",
        "ticket_id": "999",
        "order_status": "delivered",
        "other_key": "keep_me"
    }
    
    # Mock ShopifyClient para evitar chamada real
    import app.nodes.action_search_products
    original_client = app.nodes.action_search_products.ShopifyClient
    
    class MockClient:
        def __init__(self, *args, **kwargs): pass
        def search_products(self, query, limit): return []

    app.nodes.action_search_products.ShopifyClient = MockClient
    
    try:
        new_state = action_search_products(state, tenant)
        
        # Verifica se limpou chaves específicas
        assert "tracking_url" not in new_state.metadata
        assert "order_id" not in new_state.metadata
        assert "ticket_id" not in new_state.metadata
        assert "order_status" not in new_state.metadata
        
        # Verifica se manteve outras chaves e adicionou novas
        assert new_state.metadata.get("other_key") == "keep_me"
        assert new_state.metadata.get("search_query") == "camiseta"
        assert new_state.metadata.get("search_results_count") == 0
        
        print("✓ Metadados de suporte limpos corretamente")
        print("✓ Metadados de busca adicionados corretamente")
        
    finally:
        # Restore mock
        app.nodes.action_search_products.ShopifyClient = original_client

    print("\n✅ Limpeza de metadados funciona corretamente!\n")


def test_support_fallback_response():
    """Testa lógica de fallback para suporte."""
    print("\n=== TESTE 9: Fallback de Suporte ===\n")
    
    from app.nodes.respond import _fallback_response
    
    # Caso 1: Support com tracking
    state = ConversationState(tenant_id="demo", session_id="test")
    state.domain = "support"
    state.tracking_url = "http://track.me/123"
    resp = _fallback_response(state)
    assert "Segue o link" in resp.last_bot_message
    assert "http://track.me/123" in resp.last_bot_message
    print("✓ Support: Tracking link retornado")
    
    # Caso 2: Support sem tracking, mas conhecido
    state = ConversationState(tenant_id="demo", session_id="test")
    state.domain = "support"
    state.order_id = "1001"
    resp = _fallback_response(state)
    assert "Consigo verificar seu pedido" in resp.last_bot_message
    print("✓ Support: Confirmação de pedido")
    
    # Caso 3: Support desconhecido
    state = ConversationState(tenant_id="demo", session_id="test")
    state.domain = "support"
    resp = _fallback_response(state)
    assert "preciso do numero do pedido" in resp.last_bot_message
    print("✓ Support: Pedido de info")

    print("\n✅ Fallback de suporte funciona corretamente!\n")


def run_all_tests():
    """Executa todos os testes."""
    print("\n" + "="*60)
    print("TESTES MANUAIS DO SALES AGENT")
    print("="*60)
    
    try:
        test_decide_logic()
        test_strategy_escalation()
        test_state_management()
        test_checkout_link_generation()
        test_url_handle_extraction()
        test_variant_selection_extraction()
        test_link_duplication_fix()
        test_metadata_clearing()
        test_support_fallback_response()
        
        print("\n" + "="*60)
        print("✅ TODOS OS TESTES PASSARAM COM SUCESSO!")
        print("="*60 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ ERRO: {e}\n")
        raise
    except Exception as e:
        print(f"\n❌ ERRO INESPERADO: {e}\n")
        raise


if __name__ == "__main__":
    run_all_tests()
