"""
Diagnóstico: verifica se o state persistence está falhando por mismatch
entre tenant_id (slug vs UUID) no filtro do UPDATE em conversations.

Uso: cd backend && python scripts/diagnose_state_persistence.py
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.supabase_client import get_supabase
from app.core.state import ConversationState

UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)

def is_uuid(value: str) -> bool:
    return bool(UUID_RE.match(value or ""))


def fetch_empty_state_conversations(limit: int = 20) -> list[dict]:
    supabase = get_supabase()
    result = (
        supabase.table("conversations")
        .select("id, tenant_id, session_id, state, created_at")
        .eq("state", {})
        .order("created_at", ascending=False)
        .limit(limit)
        .execute()
    )
    return result.data or []


def count_messages(conversation_id: str) -> int:
    supabase = get_supabase()
    result = (
        supabase.table("messages")
        .select("id", count="exact")
        .eq("conversation_id", conversation_id)
        .execute()
    )
    return result.count or 0


def uuid_to_slug(tenant_uuid: str) -> str | None:
    supabase = get_supabase()
    try:
        result = (
            supabase.table("tenants")
            .select("slug")
            .eq("id", tenant_uuid)
            .single()
            .execute()
        )
        if result.data:
            return result.data.get("slug")
    except Exception:
        pass
    return None


def slug_to_uuid(slug: str) -> str | None:
    supabase = get_supabase()
    try:
        result = (
            supabase.table("tenants")
            .select("id")
            .eq("slug", slug)
            .single()
            .execute()
        )
        if result.data:
            return result.data.get("id")
    except Exception:
        pass
    return None


def simulate_save(tenant_id: str, session_id: str) -> int:
    """Chama _supabase_set internamente e retorna quantas rows foram atualizadas."""
    from datetime import datetime, timezone
    supabase = get_supabase()

    fake_state = ConversationState(tenant_id=tenant_id, session_id=session_id)
    # Lê estado atual para não sobrescrever nada real — vamos checar rows_updated
    # sem alterar o conteúdo: usamos o state vazio que já está lá (state = {})
    # Portanto fazemos um UPDATE com o mesmo {} que já existe.
    result = (
        supabase.table("conversations")
        .update({
            "state": {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("tenant_id", tenant_id)
        .eq("session_id", session_id)
        .execute()
    )
    rows = result.data if result.data else []
    if isinstance(rows, dict):
        rows = [rows]
    return len(rows)


def main():
    print("Buscando conversations com state vazio...")
    convs = fetch_empty_state_conversations(20)

    uuid_count = 0
    slug_count = 0
    real_cases: list[dict] = []  # conversations com >= 2 mensagens

    for c in convs:
        tid = c.get("tenant_id", "")
        sid = c.get("session_id", "")
        msg_count = count_messages(c.get("id", ""))
        fmt = "uuid" if is_uuid(tid) else "slug"

        if fmt == "uuid":
            uuid_count += 1
        else:
            slug_count += 1

        entry = {
            "tenant_id": tid,
            "session_id": sid,
            "fmt": fmt,
            "msg_count": msg_count,
        }

        if fmt == "uuid":
            entry["slug"] = uuid_to_slug(tid)
        else:
            entry["uuid"] = slug_to_uuid(tid)

        if msg_count >= 2:
            real_cases.append(entry)

    print(f"  Analisadas: {len(convs)} conversations")
    print(f"  Com >= 2 mensagens (casos reais): {len(real_cases)}")

    # ── Teste de simulação ───────────────────────────────────────────
    slug_result = None
    uuid_result = None
    test_session = None
    test_slug = None
    test_uuid = None

    # Escolhe o primeiro caso real, ou qualquer caso se não houver real
    candidate = real_cases[0] if real_cases else (convs[0] if convs else None)

    if candidate:
        test_session = candidate["session_id"]
        if candidate["fmt"] == "uuid":
            test_uuid = candidate["tenant_id"]
            test_slug = candidate.get("slug")
        else:
            test_slug = candidate["tenant_id"]
            test_uuid = candidate.get("uuid")

        print(f"\nTestando save com session_id: {test_session}")

        if test_slug:
            rows = simulate_save(test_slug, test_session)
            slug_result = rows
            print(f"  UPDATE com slug '{test_slug}': {rows} rows updated")

        if test_uuid:
            rows = simulate_save(test_uuid, test_session)
            uuid_result = rows
            print(f"  UPDATE com UUID '{test_uuid}': {rows} rows updated")

    # ── Relatório final ──────────────────────────────────────────────
    print("\n" + "=" * 42)
    print("=== DIAGNÓSTICO: STATE PERSISTENCE ===")
    print("=" * 42)
    print()
    print(f"Conversations vazias analisadas: {len(convs)}")
    print()
    print("Padrão de tenant_id em conversations:")
    print(f"  - UUID format: {uuid_count}")
    print(f"  - Slug format: {slug_count}")
    print()

    if test_session:
        print("Teste de save_session:")
        if test_slug is not None:
            slug_label = "SUCESSO" if slug_result == 1 else f"FALHA"
            print(f"  - Com slug \"{test_slug}\": {slug_label} (rows updated: {slug_result})")
        else:
            print("  - Com slug: não foi possível determinar slug do tenant")

        if test_uuid is not None:
            uuid_label = "SUCESSO" if uuid_result == 1 else f"FALHA"
            print(f"  - Com UUID \"{test_uuid[:8]}...\": {uuid_label} (rows updated: {uuid_result})")
        else:
            print("  - Com UUID: não foi possível determinar UUID do tenant")
    else:
        print("Teste de save_session: sem dados para testar")

    print()
    print("CONCLUSÃO:")

    if candidate is None:
        print(
            "  Não foi possível encontrar conversations para analisar. "
            "Verifique a conexão com o Supabase."
        )
    elif uuid_count > 0 and slug_count == 0:
        # Conversations usam UUID; testamos se save com slug falha
        slug_fail = slug_result == 0 or slug_result is None
        uuid_ok = uuid_result == 1

        if slug_fail and uuid_ok:
            print(
                "  HIPÓTESE CONFIRMADA: as conversations armazenam tenant_id como UUID,\n"
                "  mas save_session() é chamado com slug. O filtro .eq('tenant_id', slug)\n"
                "  não encontra nenhuma row => 0 rows updated => estado descartado silenciosamente.\n"
                "  FIX: resolver o tenant slug para UUID antes de chamar _supabase_set()."
            )
        elif slug_fail and not uuid_ok:
            print(
                "  PARCIAL: conversations usam UUID e save com slug falha (0 rows), mas\n"
                "  save com UUID também falhou. Pode haver outro problema (RLS, schema, etc)."
            )
        elif not slug_fail:
            print(
                "  HIPÓTESE REFUTADA: save com slug funcionou (rows updated = 1).\n"
                "  O tenant_id na conversations coincide com o slug. Investigar outra causa."
            )
        else:
            print("  Resultado inconclusivo — verifique os valores acima manualmente.")

    elif slug_count > 0 and uuid_count == 0:
        print(
            "  Conversations já armazenam slug. O mismatch slug/UUID provavelmente não é a causa.\n"
            "  Investigar se save_session() está sendo chamado em algum momento, ou se o estado\n"
            "  é construído mas o grafo encerra sem chamar save_session()."
        )
    else:
        print(
            "  Formato misto (UUID e slug) detectado nas conversations — inconsistência no\n"
            "  preenchimento do campo tenant_id. Revisar onde conversations são criadas."
        )

    print()


if __name__ == "__main__":
    main()
