import requests
import json
import time

url = "http://localhost:8000/webhooks/whatsapp/demo/messages-upsert"

payload = {
  "event": "messages.upsert",
  "instance": "nouvaris",
  "data": {
    "key": {
      "remoteJid": "5511999999999@s.whatsapp.net",
      "fromMe": False,
      "id": "TEST_ID_" + str(int(time.time()))
    },
    "pushName": "Test Simulator",
    "message": {
      "conversation": "oi"
    },
    "messageType": "conversation",
    "messageTimestamp": int(time.time()),
    "source": "ios"
  },
  "sender": "5511999999999@s.whatsapp.net"
}

print(f"Sending POST to {url}...")
try:
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.text}")
except Exception as e:
    print(f"Request failed: {e}")
