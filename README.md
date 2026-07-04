# MCP Agent

A chat agent that works like a normal LLM assistant, but when you attach an
**MCP (Model Context Protocol) server** it gains that server's tools and calls
them based on the system prompt. Multi-user, persistent, streaming.

- **Backend** — FastAPI + SQLite (SQLModel), LangChain + LangGraph, Ollama LLM.
- **Frontend** — Vite + React (TypeScript), streaming chat with visible reasoning.
- Architecture rules live in [RULES.md](RULES.md).

## Features

- **Email-only login** (no password) — anyone can use it.
- **Streaming chat** with the model's **internal reasoning** shown live and saved.
- **Conversations** you can switch between; history persists across restarts.
- **MCP servers** attached per user:
  - Inspect any server to see **all its tools and prompts** (nothing hidden).
  - **Per-tool on/off toggles** — the agent only gets the tools you enable.
  - **Connect** flow for servers that require an auth token.
- **Settings** — edit the system prompt and set your own Ollama API key.

## Run it

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # (Scripts/ on Windows, bin/ on *nix)
cp .env.example .env        # then fill in OLLAMA_* values
.venv/Scripts/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

All configuration is in `backend/.env` (see `.env.example`). The system prompt
default lives in `backend/prompts.py`; users can override it per-account in Settings.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_URL, defaults to http://localhost:8000
npm run dev                 # http://localhost:5173
```

## Notes

- `test_mcp_server.py` is a throwaway MCP server for local testing (a couple of
  tools + a prompt). Run it with the backend venv:
  `.venv/Scripts/python ../test_mcp_server.py` — it listens on `:9100`.
- The LLM is Ollama. The configured model **must support tool calling**
  (e.g. `gpt-oss:20b`, `qwen2.5`, `llama3.1`) or MCP tools won't fire.
