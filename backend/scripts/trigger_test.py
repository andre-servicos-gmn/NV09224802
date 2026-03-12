import requests
import json
import time

url = "http://localhost:8000/webhooks/whatsapp/demo"

# Mock Evolution API text payload
payload = {
    "event": "messages.upsert",
    "instance": "test_instance",
    "data": {
        "key": {
            "remoteJid": "5511999999999@s.whatsapp.net",
            "fromMe": False,
            "id": f"TEST_MSG_{int(time.time())}"
        },
        "pushName": "Test User",
        "status": "PENDING",
        "message": {
            "conversation": "Quero comprar um tênis azul"
        },
        "messageTimestamp": int(time.time()),
        "source": "api"
    }
}

print("Sending webhook payload...")
response = requests.post(url, json=payload)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
