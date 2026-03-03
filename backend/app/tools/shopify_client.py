# Modified: add product search, variant listing, and inventory checks.
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
            "price": variant["price"],
            "description": product.get("body_html") or "",
            "tags": product.get("tags") or "",
            "product_type": product.get("product_type") or "",
            "vendor": product.get("vendor") or "",
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

    def search_products(self, query: str, limit: int = 5) -> list[dict]:
        """
        Busca produtos publicados usando a Shopify Admin API.

        Args:
            query: Termo de busca do usuario
            limit: Numero maximo de resultados

        Returns:
            Lista de produtos com campos essenciais para listagem
        """
        # Shopify REST API não suporta busca fuzzy por título.
        # Solução: buscar todos os produtos publicados e filtrar localmente
        response = requests.get(
            f"{self.base_url}/products.json",
            params={
                "limit": 50,  # Buscar mais para ter margem de filtragem
                "published_status": "published",
            },
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        products = data.get("products", [])
        results: list[dict] = []
        
        # Normalizar query para busca case-insensitive
        query_lower = query.lower().strip()
        query_terms = query_lower.split()

        for product in products:
            # Filtrar por correspondência no título, tags ou tipo
            title = (product.get("title") or "").lower()
            tags = (product.get("tags") or "").lower()
            product_type = (product.get("product_type") or "").lower()
            description = (product.get("body_html") or "").lower()
            
            # Verifica se algum termo da query está presente
            matches = any(
                term in title or term in tags or term in product_type or term in description
                for term in query_terms
            )
            
            # Se query é vazia ou genérica (termos que indicam busca ampla), incluir todos
            generic_queries = [
                "produtos", "produtos da loja", "top", "top 5", "todos", 
                "joias", "jóias", "jewelry", "acessorios", "acessórios",
                "loja", "catálogo", "catalogo", "ver tudo", "mostrar tudo",
                "o que tem", "o que vocês tem", "o que voces tem"
            ]
            if not query_terms or any(q in query_lower for q in generic_queries):
                matches = True
            
            if not matches:
                continue
                
            variants = product.get("variants", []) or []
            if not variants:
                continue
            first_variant = variants[0]
            in_stock = any((v.get("inventory_quantity") or 0) > 0 for v in variants)
            results.append(
                {
                    "product_id": str(product.get("id")),
                    "title": product.get("title", ""),
                    "price": str(first_variant.get("price", "")),
                    "image_url": (product.get("image") or {}).get("src"),
                    "has_variants": len(variants) > 1,
                    "in_stock": in_stock,
                }
            )
            
            # Limitar ao número solicitado
            if len(results) >= limit:
                break

        return results

    def get_product_variants(self, product_id: str) -> list[dict]:
        """
        Busca variantes de um produto especifico.

        Args:
            product_id: ID do produto na Shopify

        Returns:
            Lista de variantes com estoque e disponibilidade
        """
        response = requests.get(
            f"{self.base_url}/products/{product_id}.json",
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        product = data.get("product")
        if not product:
            raise ValueError(f"Product not found: {product_id}")

        variants = product.get("variants", []) or []
        result: list[dict] = []
        for variant in variants:
            inventory_quantity = int(variant.get("inventory_quantity") or 0)
            result.append(
                {
                    "variant_id": str(variant.get("id")),
                    "title": variant.get("title", ""),
                    "price": str(variant.get("price", "")),
                    "inventory_quantity": inventory_quantity,
                    "available": inventory_quantity > 0,
                }
            )

        return result

    def check_inventory(self, variant_id: str) -> dict:
        """
        Verifica estoque de uma variante.

        Args:
            variant_id: ID da variante na Shopify

        Returns:
            dict com inventory_quantity e available
        """
        response = requests.get(
            f"{self.base_url}/variants/{variant_id}.json",
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        variant = data.get("variant")
        if not variant:
            raise ValueError(f"Variant not found: {variant_id}")

        inventory_quantity = int(variant.get("inventory_quantity") or 0)
        return {
            "inventory_quantity": inventory_quantity,
            "available": inventory_quantity > 0,
        }

    def get_order_by_number(self, order_number: str) -> dict:
        """
        Busca pedido pelo número visível ao cliente (ex: "1001").

        A Shopify diferencia:
          - order_number (ex: 1001) → visível ao cliente, campo `order_number`
          - id (ex: 5832700123) → ID interno, nunca expor

        Args:
            order_number: Número do pedido informado pelo cliente

        Returns:
            dict com campos padronizados do pedido

        Raises:
            ValueError: Se pedido não encontrado
            requests.RequestException: Falha na comunicação
        """
        response = requests.get(
            f"{self.base_url}/orders.json",
            params={
                "name": f"#{order_number}",   # Shopify aceita "#1001"
                "status": "any",
                "fields": "id,order_number,name,email,phone,financial_status,fulfillment_status,fulfillments,created_at,estimated_delivery_at",
            },
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        orders = data.get("orders", [])

        # Fallback: buscar sem o "#" se não encontrar
        if not orders:
            response2 = requests.get(
                f"{self.base_url}/orders.json",
                params={
                    "name": order_number,
                    "status": "any",
                    "fields": "id,order_number,name,email,phone,financial_status,fulfillment_status,fulfillments,created_at,estimated_delivery_at",
                },
                headers=self.headers,
                timeout=10,
            )
            response2.raise_for_status()
            data = response2.json()
            orders = data.get("orders", [])

        if not orders:
            raise ValueError(f"Pedido #{order_number} não encontrado.")

        order = orders[0]
        fulfillments = order.get("fulfillments") or []

        # Extrair tracking code e carrier da primeira fulfillment com tracking
        tracking_code = None
        tracking_url = None
        tracking_company = None
        for f in fulfillments:
            if f.get("tracking_number"):
                tracking_code = f["tracking_number"]
                tracking_url = f.get("tracking_url")
                tracking_company = f.get("tracking_company")
                break

        return {
            "shopify_order_id": str(order.get("id")),       # interno, não expor ao cliente
            "order_number": str(order.get("order_number")), # ex: "1001"
            "order_name": order.get("name"),                # ex: "#1001"
            "customer_email": order.get("email"),
            "customer_phone": order.get("phone"),
            "financial_status": order.get("financial_status"),   # paid, pending, refunded
            "fulfillment_status": order.get("fulfillment_status"), # fulfilled, partial, null
            "tracking_code": tracking_code,
            "tracking_url": tracking_url,
            "tracking_company": tracking_company,
            "created_at": order.get("created_at"),
            "estimated_delivery_at": order.get("estimated_delivery_at"),
        }

    def get_orders_by_phone(self, phone: str) -> list[dict]:
        """
        Busca pedidos pelo telefone do cliente usando busca em 2 etapas.

        IMPORTANTE: Não usar /orders.json com filtro em memória — isso só busca os
        últimos N pedidos da loja inteira e perde pedidos mais antigos.

        Etapa 1: GET /customers/search.json?query=phone:{phone} → acha o customer_id
        Etapa 2: GET /orders.json?customer_id={id}&status=any → pedidos desse cliente

        DDI: O Evolution manda "5511999998888" mas a Shopify pode ter gravado "11999998888".
        Testamos ambos os formatos para garantir o match.

        Args:
            phone: Número de telefone (somente dígitos, com ou sem DDI 55)
                   Ex: "5511999998888" ou "11999998888"

        Returns:
            Lista de pedidos recentes (máx 3), ordenados por data decrescente
        """
        def _digits_only(p: str) -> str:
            return "".join(c for c in p if c.isdigit())

        def _phone_variants(p: str) -> list[str]:
            """Gera variantes do telefone com e sem DDI 55 para bater na Shopify."""
            digits = _digits_only(p)
            variants = [digits]
            # Se começa com 55 (DDI Brasil), testar também sem ele
            if digits.startswith("55") and len(digits) > 11:
                variants.append(digits[2:])
            # Se não começa com 55, testar também com ele
            elif not digits.startswith("55"):
                variants.append("55" + digits)
            return variants

        customer_id = None
        for phone_variant in _phone_variants(phone):
            try:
                resp = requests.get(
                    f"{self.base_url}/customers/search.json",
                    params={"query": f"phone:{phone_variant}", "fields": "id,email,phone"},
                    headers=self.headers,
                    timeout=10,
                )
                resp.raise_for_status()
                customers = resp.json().get("customers", [])
                if customers:
                    customer_id = customers[0]["id"]
                    break  # Achou, não precisa testar outras variantes
            except Exception:
                continue

        if not customer_id:
            return []  # Cliente não encontrado por nenhuma variante do telefone

        # Etapa 2: buscar pedidos do cliente pelo customer_id
        response = requests.get(
            f"{self.base_url}/orders.json",
            params={
                "customer_id": customer_id,
                "status": "any",
                "limit": 3,
                "fields": "id,order_number,name,email,phone,financial_status,fulfillment_status,fulfillments,created_at",
            },
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()

        orders = response.json().get("orders", [])
        result = []
        for order in orders:
            fulfillments = order.get("fulfillments") or []
            tracking_code = None
            tracking_url = None
            for f in fulfillments:
                if f.get("tracking_number"):
                    tracking_code = f["tracking_number"]
                    tracking_url = f.get("tracking_url")
                    break
            result.append({
                "shopify_order_id": str(order.get("id")),
                "order_number": str(order.get("order_number")),
                "order_name": order.get("name"),
                "customer_email": order.get("email"),
                "financial_status": order.get("financial_status"),
                "fulfillment_status": order.get("fulfillment_status"),
                "tracking_code": tracking_code,
                "tracking_url": tracking_url,
                "created_at": order.get("created_at"),
            })
        return result

    def get_orders_by_email(self, email: str) -> list[dict]:
        """
        Busca pedidos pelo e-mail do cliente.
        Usado como fallback quando o telefone não encontrar nada.

        Args:
            email: E-mail do cliente

        Returns:
            Lista de pedidos recentes (máx 3)
        """
        response = requests.get(
            f"{self.base_url}/orders.json",
            params={
                "email": email.lower().strip(),
                "status": "any",
                "limit": 3,
                "fields": "id,order_number,name,email,phone,financial_status,fulfillment_status,fulfillments,created_at",
            },
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()

        orders = response.json().get("orders", [])
        result = []
        for order in orders:
            fulfillments = order.get("fulfillments") or []
            tracking_code = None
            tracking_url = None
            for f in fulfillments:
                if f.get("tracking_number"):
                    tracking_code = f["tracking_number"]
                    tracking_url = f.get("tracking_url")
                    break
            result.append({
                "shopify_order_id": str(order.get("id")),
                "order_number": str(order.get("order_number")),
                "order_name": order.get("name"),
                "customer_email": order.get("email"),
                "financial_status": order.get("financial_status"),
                "fulfillment_status": order.get("fulfillment_status"),
                "tracking_code": tracking_code,
                "tracking_url": tracking_url,
                "created_at": order.get("created_at"),
            })
        return result
