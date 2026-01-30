
import httpx

def test():
    url = "http://127.0.0.1:8000/health"
    print(f"Testing GET {url}...")
    try:
        resp = httpx.get(url, timeout=5)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
