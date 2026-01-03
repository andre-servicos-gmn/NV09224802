"""Store FAQ operations using Supabase database."""

from app.core.database import resolve_tenant_uuid, search_knowledge_base_by_category

# Map intents to knowledge base categories
INTENT_TO_CATEGORY = {
    "shipping_question": "shipping",
    "payment_question": "payment",
    "return_exchange": "return",
    "store_question": "store",
}


def get_faq_answer(tenant_id: str, question_intent: str) -> str:
    """Get FAQ answer from knowledge base by intent category."""
    category = INTENT_TO_CATEGORY.get(question_intent)
    if not category:
        return ""

    try:
        tenant_uuid = resolve_tenant_uuid(tenant_id)
        results = search_knowledge_base_by_category(tenant_uuid, category)
        if results:
            # Return first matching answer
            return results[0].get("answer", "")
        return ""
    except Exception:
        return ""


def get_all_faqs_for_category(tenant_id: str, category: str) -> list[dict]:
    """Get all FAQs for a category (for RAG context)."""
    try:
        tenant_uuid = resolve_tenant_uuid(tenant_id)
        return search_knowledge_base_by_category(tenant_uuid, category)
    except Exception:
        return []


def get_faq_context(tenant_id: str, question_intent: str) -> str:
    """Get combined FAQ context for LLM response generation."""
    category = INTENT_TO_CATEGORY.get(question_intent)
    if not category:
        return ""

    try:
        tenant_uuid = resolve_tenant_uuid(tenant_id)
        results = search_knowledge_base_by_category(tenant_uuid, category)
        if not results:
            return ""

        # Build context from all matching FAQs
        context_parts = []
        for faq in results:
            q = faq.get("question", "")
            a = faq.get("answer", "")
            if q and a:
                context_parts.append(f"P: {q}\nR: {a}")

        return "\n\n".join(context_parts)
    except Exception:
        return ""
