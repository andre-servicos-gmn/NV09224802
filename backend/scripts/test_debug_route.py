import requests

url = "http://127.0.0.1:8000/webhooks/test-debug"

print(f"GET {url}")
try:
    response = requests.get(url)
    print(f"Status: {response.status_code}")
    print(f"Body: {response.text}")
except Exception as e:
    print(f"Error: {e}")
