import requests

base_url = "http://localhost:8000/webhooks/whatsapp/demo"
routes = ["/messages-update", "/send-message"]

for r in routes:
    url = f"{base_url}{r}"
    print(f"POST {url}...")
    try:
        # Empty payload or minimal dummy data
        resp = requests.post(url, json={"event": "TEST_EVENT", "data": {}})
        print(f"Status: {resp.status_code}")
    except Exception as e:
        print(f"Error: {e}")
