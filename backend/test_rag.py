import os, sys
sys.path.append(os.getcwd())
from dotenv import load_dotenv
load_dotenv('../.env')

from app.core.state import ConversationState
from app.core.tenancy import TenantConfig
from app.nodes.action_search_products import action_search_products

tenant = TenantConfig(
    id=1,
    uuid='c35fe360-dc69-4997-9d1f-ae57f4d8a135',
    name='Test',
    whatsapp_number='123',
    openai_api_key=os.getenv('OPENAI_API_KEY')
)

state = ConversationState(
    tenant_id='c35fe360-dc69-4997-9d1f-ae57f4d8a135',
    session_id='test',
    search_query='quero outros produtos',
    soft_context={'disliked_terms': ['suplementos', 'whey']}
)

new_state = action_search_products(state, tenant)
print(f'Products found: {len(new_state.selected_products)}')
for p in new_state.selected_products:
    print(f'- {p.get("title")}')
