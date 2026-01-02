from pathlib import Path

import yaml


def _load_faq() -> dict:
    path = Path("store_faq.yaml")
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def get_faq_answer(tenant_id: str, question_intent: str) -> str:
    data = _load_faq()
    tenant_data = (data.get("tenants") or {}).get(tenant_id, {})
    return tenant_data.get(question_intent, "")
