"""
Import de produtos via XML Google Shopping para o tenant demo.

USO:
    cd backend
    python scripts/import_xml_demo.py [--dry-run] [--limit 100]

FLUXO:
    1. Baixa XML do feed
    2. Parseia items (Google Shopping format, namespace g:)
    3. Distribui N produtos proporcionalmente por categoria
    4. DELETA produtos antigos do tenant demo
    5. Insere novos com embedding + tenant_id
"""

import argparse
import logging
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from decimal import Decimal
from html.parser import HTMLParser
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

TENANT_DEMO_UUID = "c35fe360-dc69-4997-9d1f-ae57f4d8a135"
PLATFORM_NAME = "google_shopping_xml"
XML_URL = "https://www.lojadoprofissional.com.br/api/comparador/produtos-gratuitos"
GOOGLE_NS = {"g": "http://base.google.com/ns/1.0"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)

    def handle_entityref(self, name):
        entities = {"ndash": "–", "amp": "&", "quot": '"', "apos": "'", "lt": "", "gt": "", "nbsp": " "}
        self.text.append(entities.get(name, ""))

    def get_text(self):
        return " ".join("".join(self.text).split())


def strip_html(html: str) -> str:
    if not html:
        return ""
    s = HTMLStripper()
    s.feed(html)
    return s.get_text()


def parse_price(price_str: str) -> Optional[Decimal]:
    """Converte '129 BRL' ou '1829.7 BRL' em Decimal."""
    if not price_str:
        return None
    parts = price_str.strip().split()
    if not parts:
        return None
    try:
        return Decimal(parts[0])
    except Exception:
        return None


def fetch_xml() -> bytes:
    logger.info(f"Baixando XML de {XML_URL}...")
    req = urllib.request.Request(XML_URL, headers={"User-Agent": "Nouva-Importer/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        content = resp.read()
    logger.info(f"XML baixado: {len(content) / 1024:.1f} KB")
    return content


def parse_items(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = root.findall(".//item")

    parsed = []
    for item in items:
        avail = item.findtext("g:availability", namespaces=GOOGLE_NS) or ""
        in_stock = "in stock" in avail.lower()

        sale_price = parse_price(item.findtext("g:sale_price", namespaces=GOOGLE_NS) or "")
        regular_price = parse_price(item.findtext("g:price", namespaces=GOOGLE_NS) or "")
        price = sale_price if sale_price and (not regular_price or sale_price < regular_price) else regular_price

        parsed.append({
            "external_id": item.findtext("g:id", namespaces=GOOGLE_NS) or "",
            "title": (item.findtext("g:title", namespaces=GOOGLE_NS) or "").strip(),
            "description": strip_html(item.findtext("g:description", namespaces=GOOGLE_NS) or "")[:500],
            "url": item.findtext("g:link", namespaces=GOOGLE_NS),
            "image_url": item.findtext("g:image_link", namespaces=GOOGLE_NS),
            "price": float(price) if price else 0.0,
            "currency": "BRL",
            "category": item.findtext("g:product_type", namespaces=GOOGLE_NS) or "Geral",
            "brand": item.findtext("g:brand", namespaces=GOOGLE_NS) or "",
            "in_stock": in_stock,
        })
    return parsed


def select_distributed(items: list[dict], target: int) -> list[dict]:
    """Distribui `target` items proporcionalmente por categoria."""
    by_category = defaultdict(list)
    for item in items:
        if item["in_stock"]:
            by_category[item["category"]].append(item)

    total_in_stock = sum(len(v) for v in by_category.values())
    if total_in_stock == 0:
        return []

    quota = {}
    for cat, cat_items in by_category.items():
        proportional = round(target * len(cat_items) / total_in_stock)
        if len(cat_items) >= 5:
            quota[cat] = max(1, proportional)
        else:
            quota[cat] = proportional

    total_quota = sum(quota.values())
    if total_quota > target:
        scale = target / total_quota
        quota = {k: max(1, int(v * scale)) for k, v in quota.items() if v > 0}

    selected = []
    for cat, qty in sorted(quota.items(), key=lambda x: -len(by_category[x[0]])):
        if qty <= 0:
            continue
        cat_items = by_category[cat]
        selected.extend(cat_items[:qty])
        if len(selected) >= target:
            break

    return selected[:target]


def build_embedding_text(item: dict) -> str:
    parts = [
        item["title"],
        item["description"][:500] if item["description"] else "",
        f"Preço: R$ {item['price']:.2f}" if item["price"] else "",
        f"Categoria: {item['category']}" if item["category"] else "",
        f"Marca: {item['brand']}" if item["brand"] else "",
    ]
    return "\n".join(p for p in parts if p).strip()


def main(dry_run: bool, limit: int) -> int:
    from app.core.supabase_client import get_supabase
    from langchain_openai import OpenAIEmbeddings

    sb = get_supabase()

    xml_bytes = fetch_xml()
    all_items = parse_items(xml_bytes)
    logger.info(f"Parseados {len(all_items)} items do XML")

    in_stock_count = sum(1 for i in all_items if i["in_stock"])
    logger.info(f"In stock: {in_stock_count}")

    selected = select_distributed(all_items, target=limit)
    logger.info(f"Selecionados {len(selected)} items pra importar")

    final_dist = defaultdict(int)
    for item in selected:
        final_dist[item["category"]] += 1
    logger.info("Distribuição final por categoria:")
    for cat, qty in sorted(final_dist.items(), key=lambda x: -x[1]):
        logger.info(f"  {qty:>3}x {cat[:60]}")

    if dry_run:
        logger.warning("--dry-run ativo. Não tocando no Supabase. Encerrando.")
        return 0

    logger.info(f"Deletando produtos antigos do tenant {TENANT_DEMO_UUID}...")
    deleted = sb.table("product_embeddings").delete().eq("tenant_id", TENANT_DEMO_UUID).execute()
    logger.info(f"Deletados: {len(deleted.data) if deleted.data else 0} produtos antigos")

    logger.info("Gerando embeddings via OpenAI (text-embedding-3-small)...")
    embedder = OpenAIEmbeddings(model="text-embedding-3-small")
    texts = [build_embedding_text(item) for item in selected]
    embeddings = embedder.embed_documents(texts)
    logger.info(f"Embeddings gerados: {len(embeddings)}")

    logger.info("Inserindo no Supabase...")
    success = 0
    errors = 0
    for item, emb in zip(selected, embeddings):
        try:
            sb.table("product_embeddings").insert({
                "tenant_id": TENANT_DEMO_UUID,
                "platform": PLATFORM_NAME,
                "external_id": item["external_id"],
                "title": item["title"],
                "description": item["description"],
                "price": item["price"],
                "currency": item["currency"],
                "tags": [item["brand"]] if item["brand"] else [],
                "categories": [item["category"]],
                "product_type": item["category"],
                "vendor": item["brand"],
                "image_url": item["image_url"],
                "url": item["url"],
                "in_stock": item["in_stock"],
                "variants_count": 1,
                "raw_data": {"source": "xml_import"},
                "embedding": emb,
            }).execute()
            success += 1
        except Exception as e:
            logger.error(f"Falha ao inserir {item['external_id']}: {e}")
            errors += 1

    logger.info(f"✅ Concluído. Sucesso: {success} | Erros: {errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Simula sem tocar no Supabase")
    parser.add_argument("--limit", type=int, default=100, help="Quantos produtos importar")
    args = parser.parse_args()

    sys.exit(main(dry_run=args.dry_run, limit=args.limit))
