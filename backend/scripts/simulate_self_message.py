import requests
import json
import time

url = "http://localhost:8000/webhooks/whatsapp/demo/messages-upsert"

# Payload simulating a message sent BY the bot (fromMe=True)
payload = {
  "event": "messages.upsert",
  "instance": "nouvaris",
  "data": {
    "key": {
      "remoteJid": "5511999999999@s.whatsapp.net",
      "fromMe": True,  # This is the key field
      "id": "BAE5CAF"
    },
    "pushName": "Nouvaris Bot",
    "message": {
      "conversation": "This is a bot reply"
    },
    "messageType": "conversation",
    "messageTimestamp": int(time.time()),
    "source": "ios"
  },
  "sender": "5511999999999@s.whatsapp.net"
}

print(f"Sending SELF-MESSAGE to {url}...")
try:
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.text}")
except Exception as e:
    print(f"Request failed: {e}")
