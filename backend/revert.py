import requests, json

SUPABASE_URL = 'https://dzahhgzycqdujhhceosr.supabase.co'
SUPABASE_SERVICE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR6YWhoZ3p5Y3FkdWpoaGNlb3NyIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NzEzNzUxOCwiZXhwIjoyMDgyNzEzNTE4fQ.sG6j31bBJOGjgjMvOB_Q_cqDTHm6_pSSY9nEIFz65kk'

headers = {
    'apikey': SUPABASE_SERVICE_KEY,
    'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

# Clear state and status in Supabase
url = f'{SUPABASE_URL}/rest/v1/conversations?tenant_id=eq.c35fe360-dc69-4997-9d1f-ae57f4d8a135&session_id=eq.5511954499030'
update_data = {
    'state': {},
    'status': 'active'
}
r = requests.patch(url, headers=headers, json=update_data)
print(f'Supabase state cleared. Status: {r.status_code}')

# Also clear Redis
import redis
REDIS_URL = 'redis://default:PBwpY9gyei4bepy1AHx5CvwMNaETQfG8@redis-18688.crce207.sa-east-1-2.ec2.cloud.redislabs.com:18688'
try:
    r_client = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2.0)
    # Delete ALL possible keys for this session (both demo and uuid tenant)
    keys_deleted = 0
    for tid in ['demo', 'c35fe360-dc69-4997-9d1f-ae57f4d8a135']:
        key = f'session:{tid}:5511954499030'
        deleted = r_client.delete(key)
        keys_deleted += deleted
        print(f'Redis key {key}: deleted={deleted}')
    print(f'Total Redis keys deleted: {keys_deleted}')
except Exception as e:
    print(f'Redis error: {e}')
