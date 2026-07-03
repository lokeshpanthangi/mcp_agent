# MCP Agent — Build Plan

A chat agent that behaves like a normal LLM assistant, but when a user attaches an
**MCP server URL** it gains that server's tools and calls them based on the system
prompt. Backend acts as the **MCP client**; the LLM is **Ollama** (via LangChain).
Real accounts via **email-only login** (no password); data persisted in **SQLite**.

## Guiding principles

- **Minimum code.** Lean on libraries (`langchain-mcp-adapters` +
  `langgraph.prebuilt.create_react_agent`, `SQLModel` for DB, stdlib `secrets` for
  auth tokens) instead of hand-writing what they already solve.
- **No hardcoding.** Every value (model, base URL, key, prompt, ports, CORS, DB
  path) comes from `.env` via a single typed `Settings` object.
- **Dynamic tools.** No MCP attached → `tools=[]` → plain chat. MCP attached →
  agent gains that server's tools.
- **Persisted, per-user.** SQLite is the source of truth — no in-memory state.
  MCP servers and chat history belong to the logged-in user, not a transient
  session, so they survive restarts and are usable across devices.

## Tech stack

| Concern            | Choice                                                     |
| ------------------- | ----------------------------------------------------------- |
| API / server        | FastAPI + uvicorn                                           |
| Database             | SQLite via **SQLModel** (SQLAlchemy + Pydantic in one, minimal code) |
| Auth                 | Email-only. Opaque bearer token (`secrets.token_urlsafe`), no password, no JWT dependency needed |
| LLM                  | Ollama via `langchain-ollama.ChatOllama`                    |
| Agent loop            | `langgraph.prebuilt.create_react_agent`                     |
| MCP client + tools    | `langchain-mcp-adapters.MultiServerMCPClient`                |
| Config                | `pydantic-settings` reading `.env`                          |
| Frontend              | Vite + React (TypeScript), SSE for streaming                 |

---

## Data model (SQLite, 5 tables)

```
User          id, email (unique), created_at
AuthToken     token (PK), user_id (FK), created_at
McpServer     id, user_id (FK), name, url, transport, headers_json, created_at
Conversation  id, user_id (FK), title, created_at
Message       id, conversation_id (FK), role, content, created_at
```

- **Auth**: `POST /auth/login {email}` → find-or-create `User` → issue a random
  `AuthToken` row → return the token. Client sends it as `Authorization: Bearer
  <token>` on every request after. No password, no email verification — identity
  is just "whoever holds this email."
- **MCP servers are per-user**, not per-conversation: attach once, available in
  every chat you start. Simpler UX, simpler code than a join table.
- **Conversations/Messages are per-user**: history persists across restarts and
  is scoped so User A can never see User B's data.

---

## Data flow (one chat turn)

```
UI ──POST /chat {conversation_id, message} + Bearer token──► chat route
        │
        ▼
   auth.get_current_user(token)  → user
        │
        ▼
   load user's McpServer rows → build MultiServerMCPClient config
        │
        ▼
   agent_factory.get_agent(user_id, mcp_config)   (cached; rebuilt on MCP change)
        │  ChatOllama + MultiServerMCPClient.get_tools() → create_react_agent
        ▼
   agent.astream_events(...)  → token / tool_call / tool_result events
        │                              │
        │                              └─ persist user msg + assistant msg → Message table
        ▼
   SSE stream ──────────────────────────► UI renders live
```

---

## Backend files — what goes in each

### `backend/app/config.py`
- One `Settings(BaseSettings)` (pydantic-settings), `env_file=".env"`.
- Fields: `DATABASE_URL` (e.g. `sqlite:///./mcp_agent.db`), `OLLAMA_MODEL`,
  `OLLAMA_BASE_URL`, `OLLAMA_API_KEY` (optional), `SYSTEM_PROMPT`, `MAX_TOKENS`,
  `TOOL_TIMEOUT_SECONDS`, `HOST`, `PORT`, `CORS_ORIGINS`.
- Export `settings = Settings()`. Missing required var → app fails loudly at
  startup. **No logic beyond field declarations.**

### `backend/app/models.py`
- `SQLModel` table classes: `User`, `AuthToken`, `McpServer`, `Conversation`,
  `Message` — fields as in the Data model section above. No methods, just schema.

### `backend/app/db.py`
- `engine = create_engine(settings.DATABASE_URL)`.
- `create_db_and_tables()` — called once on startup.
- `get_session()` — FastAPI `Depends`-able generator yielding a `Session`.
- **No business logic** — just engine/session plumbing.

### `backend/app/auth.py`
- `create_token_for_user(email, db) -> str`: find-or-create `User` by email,
  insert an `AuthToken`, return the token string.
- `get_current_user(token, db) -> User`: FastAPI dependency — looks up the token,
  404/401s if missing/invalid. Used by every protected route via `Depends`.
- This is the only place auth logic lives.

### `backend/app/agent_factory.py`
- Builds and **caches** a LangGraph agent per user, keyed by a hash of that
  user's current MCP server set (rebuild only when it changes).
- `make_model()` → `ChatOllama(model=..., base_url=..., client_kwargs=... )` — all
  from `settings`.
- `async get_agent(user_id, mcp_servers: list[McpServer])`:
  - if empty → `tools = []`
  - else → build `MultiServerMCPClient` config from the rows, `tools =
    await client.get_tools()`
  - return `create_react_agent(make_model(), tools, prompt=settings.SYSTEM_PROMPT)`
- Stays ~30 lines — the libraries do the work.

### `backend/app/routes/auth.py`
- `POST /auth/login` → body `{email}` → calls `auth.create_token_for_user` →
  returns `{token, user_id, email}`. The only unauthenticated route besides
  `/health`.

### `backend/app/routes/mcp.py`
- All routes require `Depends(get_current_user)`.
- `POST /mcp` → attach `{name, url, transport?, headers?}` to the current user;
  invalidate their cached agent.
- `GET /mcp` → list the current user's servers.
- `DELETE /mcp/{id}` → detach (must belong to the current user); invalidate cache.

### `backend/app/routes/conversations.py`
- `GET /conversations` → list the current user's conversations.
- `GET /conversations/{id}/messages` → full message history for one
  conversation (404 if it doesn't belong to the current user).
- `POST /conversations` → create a new empty conversation, returns its id.

### `backend/app/routes/chat.py`
- `POST /chat` → body `{conversation_id, message}`, requires auth.
- Persist the user message, load the user's MCP servers, get the cached agent,
  stream `agent.astream_events(...)` as SSE:
  - `on_chat_model_stream` → `event: token`
  - `on_tool_start` → `event: tool_call`
  - `on_tool_end` → `event: tool_result`
  - end → persist the assistant message, `event: done`

### `backend/app/main.py`
- Create `FastAPI` app, CORS from `settings.CORS_ORIGINS`.
- `on_startup` → `create_db_and_tables()`.
- Include routers: `auth`, `mcp`, `conversations`, `chat`.
- `GET /health`.

### `backend/app/__init__.py`, `backend/app/routes/__init__.py`
- Empty package markers.

### `backend/requirements.txt`
```
fastapi
uvicorn[standard]
pydantic-settings
sqlmodel
langchain
langchain-ollama
langchain-mcp-adapters
langgraph
```
(No JWT/password-hashing library — not needed for email-only auth.)

### `backend/.env.example`
- All keys from `config.py`, safe local defaults; `OLLAMA_API_KEY` blank;
  `DATABASE_URL=sqlite:///./mcp_agent.db`.

### `backend/.gitignore`
- `.env`, `__pycache__/`, `.venv/`, `*.pyc`, `*.db`.

---

## Frontend files — what goes in each

Unchanged in shape, but `api.ts` now stores the bearer token (e.g. `localStorage`)
after `/auth/login` and attaches it to every request; `App.tsx` gates the UI
behind a simple "enter your email" screen until a token exists.

### `frontend/src/api.ts`
- `login(email) -> token` (stores it), `sendMessage(conversationId, message,
  handlers)` (SSE, `Authorization` header), `listMcp` / `attachMcp` / `detachMcp`,
  `listConversations` / `getMessages`.

### `frontend/src/components/Login.tsx` *(new)*
- Single email input + submit. Calls `api.login`, then reveals the app.

### `frontend/src/components/Chat.tsx`, `McpPanel.tsx`, `App.tsx`, `main.tsx`,
`styles.css`, `index.html`, `package.json`, `.env.example`, `.gitignore`
- Same roles as before; `App.tsx` now also owns auth state and conversation id
  instead of a random session id.

---

## Phases (backend first) — what & how to test

### Phase 0 — Project skeleton & config
**Build:** `requirements.txt`, `.env.example`, `config.py`.
**Test:** `uvicorn app.main:app --reload` boots; `GET /health` → 200. Temporarily
remove a required `.env` var → app refuses to start with a clear error (proves
no hardcoded fallback).

### Phase 1 — Database layer
**Build:** `db.py`, `models.py`; `create_db_and_tables()` runs on startup.
**Test:** start the app, confirm `mcp_agent.db` is created; run
`sqlite3 mcp_agent.db ".tables"` and see all 5 tables; open a Python shell,
insert a `User`, query it back.

### Phase 2 — Auth (email-only login)
**Build:** `auth.py`, `routes/auth.py`.
**Test (curl):**
- `POST /auth/login {"email": "a@x.com"}` → 200 + token.
- Same email again → same `user_id`, a fresh valid token.
- A protected test route with `Authorization: Bearer <token>` → 200.
- Same route with no header / garbage token → 401.

### Phase 3 — MCP server management (per-user CRUD)
**Build:** `routes/mcp.py`.
**Test:** attach a server as user A → `GET /mcp` shows it. Log in as user B
(different email) → `GET /mcp` is empty (isolation). Delete it as A → gone.
Verify rows directly with `sqlite3 mcp_agent.db "select * from mcpserver;"`.

### Phase 4 — Conversations & core chat (no tools yet)
**Build:** `agent_factory.py` (`tools=[]` path), `routes/conversations.py`,
`routes/chat.py`.
**Test:** `POST /conversations` → get an id. `POST /chat` with a message and no
MCP attached → SSE token stream → final answer. `GET
/conversations/{id}/messages` shows both user and assistant messages. **Restart
the server** and re-fetch — history is still there (proves persistence, not
memory).

### Phase 5 — MCP-powered tool calling
**Build:** extend `agent_factory.get_agent` to pull the user's `McpServer` rows
into `MultiServerMCPClient`, rebuild the cached agent when the set changes.
**Test:** attach a real/test MCP server, ask a question that needs it → SSE
shows `tool_call` / `tool_result` events and the final answer reflects the
tool's output. Ask an unrelated question → answered directly, no spurious tool
call.

### Phase 6 — Hardening & polish
**Build:** tool-call timeout (`settings.TOOL_TIMEOUT_SECONDS`), MCP URL
validation, structured error responses, CORS check against the real frontend
origin.
**Test:** attach a garbage URL → clean 4xx, not a crash. Simulate a hanging MCP
tool → request times out gracefully instead of hanging forever. Bad/garbage
token → 401. Call `/chat` from the Vite dev origin in a browser → no CORS error
in the console.

---

## Open decisions / assumptions made (flag if you want it different)

- **MCP servers scoped to the user**, not the conversation — attach once, used
  everywhere. (Simpler than a per-conversation join table; easy to add later if
  you want per-chat toggling.)
- **Auth tokens don't expire** in v1 (Phase 6 candidate if needed later).
- **Model + local vs. Ollama Cloud** still needed to set `.env.example`
  defaults — model **must support tool calling** (e.g. `llama3.1`, `qwen2.5`) or
  MCP tools won't fire.
