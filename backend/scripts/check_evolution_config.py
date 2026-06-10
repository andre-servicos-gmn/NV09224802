import os
import sys
import requests
import json

from dotenv import load_dotenv

load_dotenv()

INSTANCE_URL = os.getenv("EVOLUTION_DEMO_INSTANCE_URL")
API_KEY = os.getenv("EVOLUTION_DEMO_API_KEY")
INSTANCE_NAME = os.getenv("EVOLUTION_DEMO_INSTANCE_NAME", "default")

if not INSTANCE_URL or not API_KEY:
    sys.exit(
        "Defina EVOLUTION_DEMO_INSTANCE_URL e EVOLUTION_DEMO_API_KEY "
        "(no .env ou no ambiente) antes de rodar este script."
    )

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
