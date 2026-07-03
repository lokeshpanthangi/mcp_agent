# Backend Architecture Rules

Non-negotiable. Applies to every file under `backend/`, present and future. Read
this before writing any backend code — if new code doesn't fit this pattern,
the pattern gets discussed and this file gets updated first, not the other
way around.

## Folder structure

```
backend/
├── main.py              FastAPI app entrypoint. Mounts every feature's router. Nothing else.
├── config.py             Settings (.env) — shared across all features.
├── database.py            Core DB adapter ONLY: engine, session/connection helpers,
│                           create_db_and_tables(). No feature-specific queries here.
├── core/                 Core agent engine — NOT HTTP-facing, no DB access.
│   └── engine.py           Builds the LLM + LangGraph agent (ChatOllama, create_react_agent,
│                           MCP tool wiring). Pure Python in, agent out.
├── security/              Shared, non-HTTP security utilities.
│   └── auth.py              get_current_user() dependency, token generation. Orchestrates
│                           calls to api/auth/database.py — never writes raw queries itself.
└── api/                  HTTP layer. One folder per feature. Nothing loose at this level.
    ├── auth/               Feature: login
    │   ├── routes.py         HTTP wiring only: POST /auth/login, GET /auth/me
    │   ├── logic.py           Business logic the routes call
    │   └── database.py       User + AuthToken tables & queries
    ├── mcp/                Feature: MCP server management
    │   ├── routes.py         HTTP wiring only: POST/GET/DELETE /mcp
    │   ├── logic.py           Business logic the routes call
    │   └── database.py       McpServer table & queries
    ├── agent/              Feature: chat + conversations
    │   ├── routes.py         HTTP wiring only: POST /chat (SSE), conversation CRUD
    │   ├── logic.py           Business logic the routes call (calls core/engine.py)
    │   └── database.py       Conversation + Message tables & queries
    └── settings/           Feature: per-user system prompt + Ollama API key
        ├── routes.py         HTTP wiring only: GET/PUT /settings
        ├── logic.py           Effective/display/save with defaults from prompts.py + .env
        └── database.py       UserSettings table & queries
```

Adding a new feature (e.g. "billing") means adding `api/billing/{routes.py,
logic.py, database.py}` and mounting the router in `main.py`. Nothing else
should need to change.

## The rule for every feature folder in `api/`

Exactly three files. Each has one job.

### `routes.py` — HTTP only

- The FastAPI router, its endpoints, and the Pydantic request/response models
  used for input validation.
- Each route handler does exactly three things: **validate input** (Pydantic
  does this for you), **call the matching function in `logic.py`**, **return
  the result.** Nothing else lives in the handler body — no business logic,
  no DB calls, no `select(...)`.

### `logic.py` — business logic only

- One function per route, named for what it does (`create_conversation`,
  `attach_mcp_server`), not `handle_x`/`do_x`.
- This is where the actual work happens: talking to this feature's
  `database.py`, calling `core/engine.py` if needed, applying any rules
  (e.g. "404 if this MCP server doesn't belong to the current user").
- **No raw SQL, no ORM session objects, no `select(...)` here either.** Need
  data? Call a function from this feature's `database.py`.

### `database.py` — DB only

- Defines the SQLModel table class(es) this feature owns.
- Defines every query/persistence function this feature needs
  (`get_user_by_email`, `create_message`, `list_mcp_servers_for_user`) as
  plain functions.
- Imports connection/session primitives from the root `backend/database.py`
  adapter — **never creates its own engine or connection.**
- These functions are this feature's public interface. Other features may
  call them directly to read data they need (see Cross-feature imports
  below) — don't reach into another feature's models to hand-roll a query
  instead of calling its `database.py` function.

### `backend/database.py` — infrastructure only

- `engine`, `get_session()` / connection helper, `create_db_and_tables()`.
- Never contains a feature-specific query or table definition.
- `create_db_and_tables()` needs every feature's tables registered on
  `SQLModel.metadata` first — `main.py` guarantees this by importing every
  feature's `routes.py` (which imports its `database.py`) before startup.

## Where things that aren't routes+logic+DB live

- **Core agent/LLM logic** (`backend/core/engine.py`): pure Python, no
  FastAPI, no direct DB access. Takes plain data in (e.g. a list of MCP
  server configs), returns a runnable agent. `api/agent/logic.py` is the only
  caller, after fetching the user's MCP servers via `api/mcp/database.py`.
- **Security that IS an HTTP endpoint** (login, token issuance) → lives in
  `api/auth/` like any other feature.
- **Security that ISN'T an HTTP endpoint** (verifying a bearer token on every
  protected route) → `backend/security/auth.py`, imported by any feature's
  `routes.py` that needs `Depends(get_current_user)`.

## Cross-feature imports — what's allowed

| From → To                                                | Allowed? |
| ----------------------------------------------------------| :------: |
| `api/<feature>/routes.py` → its own `logic.py`            | ✅       |
| `api/<feature>/logic.py` → its own `database.py`          | ✅       |
| `api/<feature>/logic.py` → another feature's `database.py`| ✅ (public interface) |
| `api/<feature>/logic.py` → another feature's `logic.py`   | ✅ (compose resolved logic, e.g. agent→settings) |
| `api/<feature>/routes.py` → its own `database.py` directly | ❌ (must go through `logic.py`) |
| `api/<feature>/*` → another feature's `routes.py`          | ❌  |
| any feature → `backend/database.py` (root adapter)        | ✅       |
| any feature → `backend/security/auth.py`                  | ✅       |
| `api/agent/logic.py` → `backend/core/engine.py`            | ✅ (the point of the split) |
| `backend/core/engine.py` → any `api/*` or `database.py`    | ❌ (must stay DB/HTTP-agnostic) |

## Naming

- Table classes: PascalCase singular (`User`, `McpServer`, `Message`).
- Query functions in `database.py`: `verb_noun` (`get_user_by_email`,
  `create_conversation`, `list_mcp_servers_for_user`).
- Logic functions in `logic.py`: same convention, no `handle_`/`do_` prefixes.

## Unchanged from before

- **No hardcoding** — everything configurable via `.env` through `config.py`.
- **Minimum code** — prefer library features over hand-rolled logic, but not
  at the cost of collapsing this separation into fewer files.
- SQLite via SQLModel. Email-only auth via opaque bearer tokens (no JWT, no
  password).
