"""
Cliente real da Shopify Admin API.
Substitui shopify_stub.py com chamadas HTTP reais.

Este cliente é instanciado com credenciais do tenant (vindas do Supabase)
e faz chamadas HTTP para a Shopify Admin API.
"""

import re
from typing import Optional

import requests


class ShopifyClient:
    """
    Cliente para Shopify Admin API.
    
    Instanciado com credenciais específicas de cada tenant.
    Tokens vêm do Supabase via TenantConfig, NUNCA de variáveis de ambiente.
    """
    
    def __init__(
        self,
        store_domain: str,
        access_token: str,
        api_version: str = "2024-01"
    ) -> None:
        """
        Inicializa cliente Shopify.
        
        Args:
            store_domain: Domínio da loja (ex: mystore.myshopify.com)
            access_token: Token de acesso da Shopify Admin API
            api_version: Versão da API (default: 2024-01)
        """
        self.store_domain = store_domain
        self.access_token = access_token
        self.api_version = api_version
        self.base_url = f"https://{store_domain}/admin/api/{api_version}"
        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json"
        }
    
    def _extract_handle_from_url(self, url: str) -> Optional[str]:
        """
        Extrai handle do produto da URL.
        
        Args:
            url: URL completa do produto
            
        Returns:
            Handle do produto ou None se não encontrar
            
        Examples:
            https://loja.com/products/colar-dourado -> "colar-dourado"
            https://loja.com/products/colar?variant=123 -> "colar"
        """
        match = re.search(r'/products/([^/?#]+)', url)
        return match.group(1) if match else None
    
    def get_product_by_url(self, product_url: str) -> dict:
        """
        Busca produto por URL completa.
        
        Args:
            product_url: URL completa do produto Shopify
            
        Returns:
            dict com product_id, variant_id, title, price
            
        Raises:
            ValueError: Se URL inválida ou produto não encontrado
            requests.RequestException: Se falha na comunicação com API
        """
        handle = self._extract_handle_from_url(product_url)
        if not handle:
            raise ValueError(f"Invalid product URL: {product_url}")
        
        # GET /products.json?handle={handle}
        response = requests.get(
            f"{self.base_url}/products.json",
            params={"handle": handle},
            headers=self.headers,
            timeout=10
        )
        response.raise_for_status()
        
        data = response.json()
        if not data.get("products"):
            raise ValueError(f"Product not found: {handle}")
        
        product = data["products"][0]
        variant = product["variants"][0]  # Primeira variante
        
        return {
            "product_id": str(product["id"]),
            "variant_id": str(variant["id"]),
            "title": product["title"],
            "price": variant["price"]
        }
    
    def build_checkout_link(
        self,
        variant_id: str,
        quantity: int,
        strategy: str
    ) -> str:
        """
        Gera link de checkout conforme estratégia.
        
        Args:
            variant_id: ID da variante do produto
            quantity: Quantidade
            strategy: Estratégia de link (permalink, add_to_cart, checkout_direct, human_handoff)
            
        Returns:
            URL de checkout ou string vazia para human_handoff
        """
        if strategy == "permalink":
            return f"https://{self.store_domain}/cart/{variant_id}:{quantity}"
        elif strategy == "add_to_cart":
            return (
                f"https://{self.store_domain}/cart/add?id={variant_id}&quantity={quantity}"
                "&return_to=%2Fcheckout"
            )
        elif strategy == "checkout_direct":
            return f"https://{self.store_domain}/checkout?variant={variant_id}&quantity={quantity}"
        elif strategy == "human_handoff":
            return ""
        return ""
