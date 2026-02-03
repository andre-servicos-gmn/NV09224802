"""Script para capturar e analisar payloads da Evolution API."""
import asyncio
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()

@app.post("/webhooks/whatsapp/{tenant_id}")
async def capture_webhook(request: Request, tenant_id: str):
    """Capture and log the full webhook payload."""
    payload = await request.json()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"captured_payload_{timestamp}.json"
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    
    print("\n" + "="*60)
    print(f"📥 PAYLOAD CAPTURADO: {filename}")
    print("="*60)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("="*60 + "\n")
    
    # Analyze important fields
    data = payload.get("data", {})
    key = data.get("key", {})
    
    print("🔍 ANÁLISE DO PAYLOAD:")
    print(f"   event: {payload.get('event')}")
    print(f"   remoteJid: {key.get('remoteJid')}")
    print(f"   fromMe: {key.get('fromMe')}")
    print(f"   sender (root): {payload.get('sender')}")
    print(f"   senderPn (data): {data.get('senderPn')}")
    print(f"   pushName: {data.get('pushName')}")
    print(f"   participant: {key.get('participant')}")
    
    return {"success": True, "captured": filename}

if __name__ == "__main__":
    print("🎯 Iniciando servidor de captura de payloads...")
    print("   Envie uma mensagem no WhatsApp para capturar o payload.")
    print("   Pressione Ctrl+C para parar.\n")
    uvicorn.run(app, host="0.0.0.0", port=8001)
