#!/usr/bin/env python
"""
Script para testar o webhook localmente.

Simula um webhook da Shopify com HMAC válido.

Usage:
    python scripts/test_webhook_local.py --tenant demo --secret SUA_CHAVE
"""

import argparse
import base64
import hashlib
import hmac
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from dotenv import load_dotenv
load_dotenv()


def generate_hmac(payload: bytes, secret: str) -> str:
    """Generate Shopify-style HMAC signature."""
    digest = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode()


def main():
    parser = argparse.ArgumentParser(description="Test webhook locally")
    parser.add_argument("--tenant", required=True, help="Tenant ID")
    parser.add_argument("--secret", required=True, help="Webhook secret")
    parser.add_argument("--shop-domain", default="tfhamg-gk.myshopify.com", help="Shop domain")
    parser.add_argument("--topic", default="products/update", help="Event topic")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    
    args = parser.parse_args()
    
    # Sample product payload
    product = {
        "id": 9999999999,
        "title": "Produto Teste Webhook",
        "body_html": "<p>Descrição do produto de teste</p>",
        "vendor": "Nouvaris Test",
        "product_type": "Teste",
        "tags": "teste, webhook, sync",
        "handle": "produto-teste-webhook",
        "variants": [
            {
                "id": 1,
                "price": "149.90",
                "inventory_quantity": 5,
            }
        ],
        "images": [
            {"src": "https://via.placeholder.com/300x300.png?text=Produto+Teste"}
        ],
    }
    
    payload = json.dumps(product).encode()
    signature = generate_hmac(payload, args.secret)
    
    print(f"Testing webhook:")
    print(f"  Tenant: {args.tenant}")
    print(f"  Topic: {args.topic}")
    print(f"  Product: {product['title']}")
    print()
    
    # Make request
    try:
        response = httpx.post(
            f"{args.url}/webhooks/shopify/{args.tenant}",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Topic": args.topic,
                "X-Shopify-Hmac-SHA256": signature,
                "X-Shopify-Shop-Domain": args.shop_domain,
            },
            timeout=30,
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200 and response.json().get("success"):
            print("\n✅ Webhook funcionando perfeitamente!")
        else:
            print("\n⚠️  Algo deu errado, verifique os logs do servidor")
            
    except httpx.ConnectError:
        print("❌ Erro: Servidor não está rodando em", args.url)
        print("   Execute: uvicorn app.api.main:app --reload --port 8000")
    except Exception as e:
        print(f"❌ Erro: {e}")


if __name__ == "__main__":
    main()
