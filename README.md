# MCP Agent

A chat agent that behaves like a normal LLM assistant, but when you attach a
**Model Context Protocol (MCP) server** it gains that server's tools and calls
them automatically based on the system prompt. Multi-user, persistent, and
fully streaming — with the model's internal reasoning shown live.

The agent is built on **[Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview)**
(LangChain), so on top of your MCP tools it also gets built-in planning, a
virtual filesystem, and subagent delegation.

---

## Features

- **Email-only login** — no password. Enter an email, get a session. Anyone can use it.
- **Streaming chat** — tokens stream live; the model's **reasoning/thinking** is
  shown in a collapsible panel and saved with each message.
- **Conversations** — create, switch between, and revisit chats. History is
  stored in SQLite and survives restarts. Titles auto-generate from the first message.
- **MCP servers** (attached per user):
  - **Inspect** any server to see **all of its tools and prompts** — nothing hidden.
  - **Per-tool on/off toggles** — the agent is only given the tools you enable,
    so you don't dump dozens of tools into its context at once.
  - **Connect** flow — if a server needs auth, paste a token to connect, then its
    tools appear.
- **Settings** — edit the system prompt (with reset-to-default) and set your own
  Ollama API key, both per account.

---

## Tech stack

| Layer     | Choice                                                                 |
| --------- | ---------------------------------------------------------------------- |
| Backend   | FastAPI + Uvicorn                                                      |
| Agent     | Deep Agents (`deepagents`) on LangGraph + `langchain-mcp-adapters`     |
| LLM       | Ollama via `langchain-ollama` (model must support tool calling)       |
| Database  | SQLite via SQLModel                                                    |
| Auth      | Email-only, opaque bearer tokens (`secrets`) — no password, no JWT     |
| Frontend  | Vite + React + TypeScript, SSE streaming                              |

---

## Project structure

The backend follows a strict feature-folder layout (see **[RULES.md](RULES.md)**
for the full contract):

```
backend/
├── main.py              FastAPI app, CORS, router mounting, startup
├── config.py             Settings loaded from .env (single source of config)
├── database.py            Core DB adapter: engine, session, table creation
├── prompts.py             Default system prompt (content, not config)
├── core/                 Non-HTTP, non-DB engine code
│   ├── engine.py           Builds the Deep Agent (Ollama + tools + prompt)
│   └── mcp_client.py        Connects to MCP servers to list tools + prompts
├── security/
│   └── auth.py             Bearer-token verification dependency
└── api/                  One folder per feature — each has routes/logic/database
    ├── auth/               Email login + "who am I"
    ├── mcp/                MCP server CRUD, inspection, connect, tool toggles
    ├── agent/              Conversations + streaming chat (SSE)
    └── settings/           Per-user system prompt + Ollama API key

frontend/src/
├── App.tsx               Top-level state + auth gate
├── api.ts                API client + SSE stream parser
└── components/           Login, Sidebar, Chat, Message, McpPanel, SettingsModal
```

Every feature folder splits into three files with one job each:
**`routes.py`** (HTTP wiring only) → **`logic.py`** (business logic) → **`database.py`**
(tables + queries).

---

## Getting started

### 1. Backend

```bash
cd backend
python -m venv .venv
# activate the venv, or call it directly (Scripts/ on Windows, bin/ on macOS/Linux)
.venv/Scripts/python -m pip install -r requirements.txt

cp .env.example .env        # then fill in the values (see below)

.venv/Scripts/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

The API runs at `http://localhost:8000` (docs at `/docs`). The SQLite database
(`mcp_agent.db`) is created automatically on first start.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_URL defaults to http://localhost:8000
npm run dev                 # http://localhost:5173
```

---

## Configuration

All backend config lives in `backend/.env` (copy from `.env.example`):

| Variable               | Description                                                        |
| ---------------------- | ----------------------------------------------------------------- |
| `DATABASE_URL`         | e.g. `sqlite:///./mcp_agent.db`                                   |
| `OLLAMA_MODEL`         | Model name — **must support tool calling** (e.g. `gpt-oss:20b`)   |
| `OLLAMA_BASE_URL`      | `http://localhost:11434` (local) or `https://ollama.com` (cloud) |
| `OLLAMA_API_KEY`       | Blank for local Ollama; set for Ollama Cloud (or per-user in Settings) |
| `MAX_TOKENS`           | Max output tokens                                                 |
| `TOOL_TIMEOUT_SECONDS` | Bound on tool loading / per-step streaming                       |
| `CORS_ORIGINS`         | Allowed frontend origin(s)                                        |

The **default system prompt** lives in `backend/prompts.py` (it's content, not
config); each user can override it in Settings. Frontend config is
`frontend/.env` → `VITE_API_URL`.

> **Note on the model:** the Ollama model must support tool/function calling
> (`gpt-oss:20b`, `qwen2.5`, `llama3.1`, …) or the MCP tools will never fire.
> A reasoning model (like `gpt-oss`) is what makes the live "thinking" panel work.

---

## Testing MCP tools locally

`test_mcp_server.py` (repo root) is a throwaway MCP server with a couple of tools
and a prompt, for exercising the MCP features:

```bash
backend/.venv/Scripts/python test_mcp_server.py   # listens on http://127.0.0.1:9100/mcp
```

Then in the app: **MCP Servers → Attach** `http://127.0.0.1:9100/mcp`, and you'll
see its tools (with toggles) and prompt.

---

## How it works

1. You log in with an email → get a bearer token stored in the browser.
2. You chat. The backend loads your MCP servers' tools (minus any you disabled),
   builds a Deep Agent with your Ollama model + system prompt, and streams the run
   back over Server-Sent Events.
3. The stream carries typed events — `reasoning`, `token`, `tool_call`,
   `tool_result` — which the UI renders as live thinking, streamed text, and tool chips.
4. Messages (and their reasoning) are saved to SQLite so conversations persist.
