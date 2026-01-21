# Nouvaris

Plataforma de agentes de IA com dashboard de métricas.

## Estrutura do Monorepo

```
nouvaris/
├── backend/          # Agentes Python (LangGraph)
└── frontend/         # Dashboard Next.js
```

## Setup

### Backend (Agentes Python)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]

# Rodar CLI
python scripts\cli_chat.py --debug
```

### Frontend (Dashboard)

```bash
# Instalar dependências
npm install

# Rodar em modo dev
npm run dev
```

Acesse o dashboard em [http://localhost:3000](http://localhost:3000)
