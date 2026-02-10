import requests
import json

INSTANCE_URL = "https://nouvaris-evolution-api.ojdb99.easypanel.host"
API_KEY = "3507B4BFABD9-4F3B-B87E-E441338CF369"
INSTANCE_NAME = "nouvaris"

headers = {
    "apikey": API_KEY,
    "Content-Type": "application/json"
}

def check_config():
    # Try multiple endpoints as Evolution API versions vary
    endpoints = [
        f"/instance/fetchInstances",
        f"/webhook/find/{INSTANCE_NAME}",
        f"/instance/fetch/{INSTANCE_NAME}"
    ]

    for endpoint in endpoints:
        url = f"{INSTANCE_URL}{endpoint}"
        print(f"--- Checking {url} ---")
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Status: {response.status_code}")
            try:
                data = response.json()
                print(json.dumps(data, indent=2))
            except:
                print(response.text)
        except Exception as e:
            print(f"Error: {e}")
        print("\n")

if __name__ == "__main__":
    check_config()
