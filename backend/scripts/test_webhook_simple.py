
import httpx

def test():
    url = "http://127.0.0.1:8000/webhooks/whatsapp/demo"
    print(f"Testing POST {url}...")
    try:
        resp = httpx.post(url, json={})
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
