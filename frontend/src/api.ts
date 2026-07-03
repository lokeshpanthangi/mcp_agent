const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "mcp_agent_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function req<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Types ────────────────────────────────
export interface User {
  user_id: number;
  email: string;
}
export interface Conversation {
  id: number;
  title: string;
}
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}
export interface McpServer {
  id: number;
  name: string;
  url: string;
  transport: string;
}

// ── Auth ─────────────────────────────────
export async function login(email: string): Promise<User> {
  const data = await req<{ token: string; user_id: number; email: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
  setToken(data.token);
  return { user_id: data.user_id, email: data.email };
}
export function me(): Promise<User> {
  return req<User>("/auth/me");
}

// ── Conversations ────────────────────────
export function listConversations(): Promise<Conversation[]> {
  return req<Conversation[]>("/conversations");
}
export function createConversation(): Promise<Conversation> {
  return req<Conversation>("/conversations", { method: "POST" });
}
export function getMessages(conversationId: number): Promise<ChatMessage[]> {
  return req<ChatMessage[]>(`/conversations/${conversationId}/messages`);
}

// ── MCP servers ──────────────────────────
export function listMcp(): Promise<McpServer[]> {
  return req<McpServer[]>("/mcp");
}
export function attachMcp(name: string, url: string): Promise<McpServer> {
  return req<McpServer>("/mcp", { method: "POST", body: JSON.stringify({ name, url }) });
}
export function detachMcp(id: number): Promise<void> {
  return req<void>(`/mcp/${id}`, { method: "DELETE" });
}

// ── Chat (SSE over fetch) ────────────────
export interface ChatHandlers {
  onReasoning?: (text: string) => void;
  onToken?: (text: string) => void;
  onToolCall?: (name: string, input: unknown) => void;
  onToolResult?: (name: string, output: string) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

export async function chat(
  conversationId: number,
  message: string,
  handlers: ChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ conversation_id: conversationId, message }),
    signal,
  });
  if (!res.ok || !res.body) {
    const body = await res.text().catch(() => "");
    handlers.onError?.(`${res.status}: ${body}`);
    handlers.onDone?.();
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      let event = "message";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data && event === "message") continue;
      const payload = data ? JSON.parse(data) : {};
      switch (event) {
        case "reasoning":
          handlers.onReasoning?.(payload.text);
          break;
        case "token":
          handlers.onToken?.(payload.text);
          break;
        case "tool_call":
          handlers.onToolCall?.(payload.name, payload.input);
          break;
        case "tool_result":
          handlers.onToolResult?.(payload.name, payload.output);
          break;
        case "error":
          handlers.onError?.(payload.message);
          break;
        case "done":
          handlers.onDone?.();
          break;
      }
    }
  }
}
