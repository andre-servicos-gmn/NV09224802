"""Testes do sanitizer de markdown WhatsApp no evolution_adapter."""

import pytest

from app.adapters.evolution_adapter import _sanitize_for_whatsapp


def test_sanitizer_converts_double_asterisks():
    """**bold** vira *bold* (sintaxe WhatsApp)."""
    assert _sanitize_for_whatsapp("Olá **mundo** lindo") == "Olá *mundo* lindo"
    assert (
        _sanitize_for_whatsapp("**Óleo Solúvel** R$ 847,40")
        == "*Óleo Solúvel* R$ 847,40"
    )


def test_sanitizer_converts_markdown_links():
    """[texto](url) vira 'texto: url' (URL crua, WhatsApp transforma em clicável)."""
    result = _sanitize_for_whatsapp(
        "Clique aqui: [Finalizar Compra](https://shop.com/cart/123)"
    )
    assert result == "Clique aqui: Finalizar Compra: https://shop.com/cart/123"


def test_sanitizer_preserves_already_correct_format():
    """*bold* / _italic_ / quebras / emojis ficam como estão."""
    assert _sanitize_for_whatsapp("Tudo *certo* por aqui") == "Tudo *certo* por aqui"
    inp = "Texto com _itálico_ e quebra\nde linha 😊"
    assert _sanitize_for_whatsapp(inp) == inp


def test_sanitizer_handles_empty_or_none():
    """Empty string e None passam direto sem alteração nem crash."""
    assert _sanitize_for_whatsapp("") == ""
    assert _sanitize_for_whatsapp(None) is None
