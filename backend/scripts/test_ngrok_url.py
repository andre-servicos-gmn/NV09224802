import httpx
import time

def test_url():
    url = "https://stereoscopic-immutably-emely.ngrok-free.dev/health"
    print(f"Testing GET {url}...")
    try:
        response = httpx.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_url()
