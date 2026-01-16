"""Shopify orders client.

Responsabilidade: buscar pedidos e extrair rastreio apenas da Shopify Admin API.

TERMINOLOGIA DE IDS (Shopify):
==============================
- order_number: ID visível ao cliente (ex: 1001).
  É o que aparece no email de confirmação. Usar para perguntas ao cliente.

- order_name: Formato com "#" (ex: "#1001").
  Campo "name" na API Shopify. Usado para filtrar pedidos.

- shopify_order_id (ou "id"): ID interno longo (ex: 5832749012345).
  Usado em endpoints /orders/{id}.json.
  NUNCA pedir ao cliente — é interno do sistema.
"""
from typing import Tuple

import requests


class ShopifyOrdersClient:
    """Cliente para pedidos na Shopify Admin API.
    
    Métodos de lookup:
    - get_order_by_number(order_number): Busca por número visível (#1001).
    - get_order_by_id(shopify_order_id): Busca por ID interno.
    - get_latest_order_by_email(email): Fallback por email.
    """

    def __init__(
        self,
        store_domain: str,
        access_token: str,
        api_version: str = "2024-01",
    ) -> None:
        self.store_domain = store_domain
        self.access_token = access_token
        self.api_version = api_version
        self.base_url = f"https://{store_domain}/admin/api/{api_version}"
        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }

    def get_order_by_id(self, order_id: str) -> dict | None:
        if not order_id:
            return None
        response = requests.get(
            f"{self.base_url}/orders/{order_id}.json",
            params={"status": "any"},
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("order")

    def get_latest_order_by_email(self, email: str) -> dict | None:
        if not email:
            return None
        response = requests.get(
            f"{self.base_url}/orders.json",
            params={
                "status": "any",
                "email": email,
                "limit": 1,
                "order": "created_at desc",
            },
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        orders = data.get("orders") or []
        return orders[0] if orders else None

    def get_order_by_number(self, order_number: str) -> dict | None:
        """
        Busca pedido pelo order_number visível ao cliente.
        
        IMPORTANTE: Este é o número que o cliente vê (ex: 1001, #1001).
        Internamente, busca pelo campo "name" da Shopify (que inclui "#").
        
        Normalização aplicada:
        - Remove "#" se presente: "#1001" → "1001"
        - Não remove zeros à esquerda
        
        Args:
            order_number: Número do pedido (ex: "1001" ou "#1001")
            
        Returns:
            dict com dados do pedido ou None se não encontrado
            
        Não usar para:
            shopify_order_id (ID interno longo) — use get_order_by_id().
        """
        if not order_number:
            return None
        
        # Normalizar: remover "#" se presente
        order_number = order_number.lstrip("#")
        
        response = requests.get(
            f"{self.base_url}/orders.json",
            params={
                "status": "any",
                "name": order_number,  # Shopify filtra por "name" (order_name)
                "limit": 1,
            },
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        orders = data.get("orders") or []
        return orders[0] if orders else None

    def extract_tracking(self, order: dict) -> Tuple[str | None, str | None]:
        fulfillments = order.get("fulfillments") or []
        for fulfillment in fulfillments:
            tracking_number = fulfillment.get("tracking_number")
            if not tracking_number:
                tracking_numbers = fulfillment.get("tracking_numbers") or []
                tracking_number = tracking_numbers[0] if tracking_numbers else None

            tracking_url = fulfillment.get("tracking_url")
            if not tracking_url:
                tracking_urls = fulfillment.get("tracking_urls") or []
                tracking_url = tracking_urls[0] if tracking_urls else None

            if tracking_number or tracking_url:
                return tracking_number, tracking_url

        return None, None
