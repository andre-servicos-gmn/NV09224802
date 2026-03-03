import sys
import os
import asyncio

# Setup path so we can import from `app.core`
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.core.session_store_v2 import get_session, save_session, clear_session
from app.core.state import ConversationState

from app.core.database import get_or_create_conversation

def test_sync():
    TENANT = 'c35fe360-dc69-4997-9d1f-ae57f4d8a135' # Demo tenant UUID
    SESSION = 'test-session-001'

    print('Criando conversa...')
    get_or_create_conversation(TENANT, SESSION, 'whatsapp', '12345678')

    print('Testando save_session...')
    state = ConversationState(tenant_id=TENANT, session_id=SESSION)
    state.last_user_message = 'Quero uma camiseta azul M'
    state.search_query = 'camiseta azul'
    save_session(TENANT, SESSION, state)
    print('  ✓ save_session OK')

    print('Testando get_session (deve retornar estado salvo)...')
    recovered = get_session(TENANT, SESSION)
    assert recovered is not None, 'FALHOU: get_session retornou None'
    assert recovered.search_query == 'camiseta azul', 'FALHOU: search_query não preservado'
    print('  ✓ get_session OK')

    print('Testando clear_session...')
    clear_session(TENANT, SESSION)
    after_clear = get_session(TENANT, SESSION)
    assert after_clear is None or not after_clear.search_query, 'FALHOU: sessão não foi limpa'
    print('  ✓ clear_session OK')

    print('\n✅ Todos os testes sync passaram!')

if __name__ == '__main__':
    from dotenv import load_dotenv
    # Load .env variables so SUPABASE_URL and REDIS_URL are available
    load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env')))
    test_sync()
