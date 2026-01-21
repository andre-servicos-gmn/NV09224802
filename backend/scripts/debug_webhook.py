#!/usr/bin/env python
"""Debug script to test webhook processing directly."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['DEBUG'] = 'true'

from dotenv import load_dotenv
load_dotenv()

from app.core.tenancy import TenantRegistry
from app.sync.sync_service import SyncService

# Get tenant
print("Loading tenant...")
registry = TenantRegistry()
tenant = registry.get('demo')
print(f'Tenant: {tenant.name}')
print(f'UUID: {tenant.uuid}')
print(f'Store: {tenant.store_domain}')
print(f'Has webhook_secret: {bool(tenant.webhook_secret)}')
print()

# Test sync
print("Testing webhook processing...")
sync = SyncService()
credentials = {
    'store_domain': tenant.store_domain,
    'access_token': tenant.shopify_access_token,
    'api_version': tenant.shopify_api_version,
    'webhook_secret': tenant.webhook_secret,
}

payload = {
    'id': 9999999999,
    'title': 'Produto Teste Webhook',
    'body_html': '<p>Teste de descricao</p>',
    'vendor': 'Nouvaris Test',
    'product_type': 'Teste',
    'tags': 'teste, webhook',
    'handle': 'produto-teste-webhook',
    'variants': [
        {
            'id': 1,
            'price': '149.90',
            'inventory_quantity': 5,
        }
    ],
    'images': [],
}

try:
    result = sync.process_webhook(
        tenant_id=tenant.uuid,
        platform='shopify',
        credentials=credentials,
        event_type='products/update',
        payload=payload,
    )
    print(f'Success! Result: {result}')
except Exception as e:
    import traceback
    print(f'ERROR: {e}')
    traceback.print_exc()
