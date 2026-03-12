"""
redis_cli.py — Ferramenta interativa de diagnóstico Redis

Usa o módulo centralizado redis_client para conexão.
"""
import os
import sys
import json
import asyncio
from dotenv import load_dotenv

# Load environment variables
dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
load_dotenv(dotenv_path)

# Add backend to path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.redis_client import get_redis_async

async def main():
    r = get_redis_async()
    if not r:
        print("❌ REDIS_URL não encontrado no .env ou conexão falhou")
        return

    try:
        await r.ping()
        print("✅ Conectado com sucesso!\n")
    except Exception as e:
        print(f"❌ Falha ao conectar: {e}")
        return

    while True:
        try:
            print("-" * 50)
            print("Comandos disponíveis:")
            print("1. Listar todas as chaves (Sessões e Buffers)")
            print("2. Ver conteúdo de uma chave (GET/LRANGE)")
            print("3. Limpar toda a base (FLUSHDB) - CUIDADO!")
            print("0. Sair")
            
            choice = input("\nEscolha uma opção: ").strip()
            
            if choice == "0":
                break
                
            elif choice == "1":
                keys = await r.keys("*")
                if not keys:
                    print("\n📭 Banco Redis está vazio.")
                else:
                    print(f"\nEncontradas {len(keys)} chaves:")
                    for idx, key in enumerate(keys, 1):
                        ttl = await r.ttl(key)
                        key_type = await r.type(key)
                        ttl_str = f"Expira em {ttl}s" if ttl > 0 else "Sem expiração"
                        print(f"  {idx}. {key} ({key_type}) - {ttl_str}")
                        
            elif choice == "2":
                key = input("Digite o nome exato da chave: ").strip()
                if not await r.exists(key):
                    print("❌ Chave não encontrada.")
                    continue
                    
                key_type = await r.type(key)
                print(f"\nTipo: {key_type.upper()}")
                
                if key_type == "string":
                    val = await r.get(key)
                    try:
                        # Tenta formatar como JSON se possível
                        parsed = json.loads(val)
                        print(json.dumps(parsed, indent=2, ensure_ascii=False))
                    except:
                        print(val)
                elif key_type == "list":
                    vals = await r.lrange(key, 0, -1)
                    for i, v in enumerate(vals):
                        print(f"[{i}]: {v}")
                else:
                    print(f"⚠️ Impossível ler tipo: {key_type}")
                    
            elif choice == "3":
                confirm = input("⚠️ TEM CERTEZA? Isso apagará TODAS as sessões ativas (S/N): ").strip().upper()
                if confirm == "S":
                    await r.flushdb()
                    print("✅ Banco limpo.")
                else:
                    print("Operação cancelada.")
            else:
                print("❌ Opção inválida.")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Erro na operação: {e}")

    await r.aclose()
    print("\nDesconectado.")

if __name__ == "__main__":
    asyncio.run(main())
