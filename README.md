# Nouvaris

A monorepo containing the Nouvaris AI Agent Platform.

## Structure

```
nouvaris/
├── backend/      # Python AI agents (FastAPI, LangGraph)
└── frontend/     # Next.js dashboard
```

## Getting Started

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e .
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Documentation

- Backend agent documentation: `backend/AGENT.md`
