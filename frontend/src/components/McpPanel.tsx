import { useEffect, useState } from "react";
import {
  attachMcp,
  connectConnector,
  connectMcp,
  Connector,
  detachMcp,
  inspectMcp,
  listConnectors,
  listMcp,
  McpInspect,
  McpServer,
  startServerOAuth,
  toggleTool,
} from "../api";

function ServerCard({ server, onDetach }: { server: McpServer; onDetach: (id: number) => void }) {
  const [data, setData] = useState<McpInspect | null>(null);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState("");
  const [connecting, setConnecting] = useState(false);

  async function inspect() {
    setLoading(true);
    try {
      setData(await inspectMcp(server.id));
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    inspect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [server.id]);

  async function connect() {
    if (!token.trim()) return;
    setConnecting(true);
    try {
      setData(await connectMcp(server.id, token.trim()));
      setToken("");
    } finally {
      setConnecting(false);
    }
  }

  async function login() {
    setConnecting(true);
    try {
      const { authorization_url } = await startServerOAuth(server.id);
      if (!authorization_url) {
        setConnecting(false);
        return;
      }
      // Open the provider's login in a new tab; re-inspect once it signals done.
      const tab = window.open(authorization_url, "_blank");
      const onMsg = (e: MessageEvent) => {
        if (e.data === "mcp-oauth-done") finish();
      };
      const finish = () => {
        window.removeEventListener("message", onMsg);
        clearInterval(poll);
        setConnecting(false);
        inspect();
      };
      window.addEventListener("message", onMsg);
      const poll = setInterval(() => {
        if (!tab || tab.closed) finish();
      }, 800);
    } catch {
      setConnecting(false);
    }
  }

  async function flip(name: string, enabled: boolean) {
    // optimistic
    setData((d) =>
      d ? { ...d, tools: d.tools.map((t) => (t.name === name ? { ...t, enabled } : t)) } : d,
    );
    await toggleTool(server.id, name, enabled);
  }

  const enabledCount = data?.tools.filter((t) => t.enabled).length ?? 0;

  return (
    <div className="server-card">
      <div className="server-card-head">
        <div className="server-card-info">
          <span className="mcp-name">{server.name}</span>
          <span className="mcp-url">{server.url}</span>
        </div>
        <div className="server-card-head-right">
          {data?.ok && (
            <span className="tool-count">
              {enabledCount}/{data.tools.length} tools on
            </span>
          )}
          <button className="icon-btn danger" title="Remove" onClick={() => onDetach(server.id)}>
            ✕
          </button>
        </div>
      </div>

      {loading && <div className="empty-note">Inspecting…</div>}

      {!loading && data?.needs_auth && (
        <div className="auth-box">
          <div className="auth-msg">🔒 This server requires authentication.</div>
          {data.supports_oauth && (
            <div className="auth-row">
              <button className="primary-btn small" onClick={login} disabled={connecting}>
                {connecting ? "Connecting…" : "Login"}
              </button>
              <span className="dim">Sign in with the provider in a new tab.</span>
            </div>
          )}
          <div className="auth-row">
            <input
              type="password"
              placeholder={data.supports_oauth ? "…or paste an access token" : "Paste access token…"}
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
            <button className="primary-btn small" onClick={connect} disabled={connecting}>
              {connecting ? "Connecting…" : "Connect"}
            </button>
          </div>
        </div>
      )}

      {!loading && data && !data.needs_auth && !data.ok && (
        <div className="modal-error">Couldn’t connect: {data.error}</div>
      )}

      {!loading && data?.ok && (
        <>
          <div className="section-label">
            Tools <span className="dim">({data.tools.length})</span>
          </div>
          {data.tools.length === 0 && <div className="empty-note">No tools exposed.</div>}
          <div className="tool-toggle-list">
            {data.tools.map((t) => (
              <label className="tool-toggle" key={t.name}>
                <input
                  type="checkbox"
                  checked={t.enabled}
                  onChange={(e) => flip(t.name, e.target.checked)}
                />
                <span className="switch" />
                <span className="tool-toggle-text">
                  <span className="tool-toggle-name">{t.name}</span>
                  {t.description && <span className="tool-toggle-desc">{t.description}</span>}
                </span>
              </label>
            ))}
          </div>

          {data.prompts.length > 0 && (
            <>
              <div className="section-label">
                Prompts <span className="dim">({data.prompts.length})</span>
              </div>
              <div className="prompt-list">
                {data.prompts.map((p) => (
                  <div className="prompt-item" key={p.name}>
                    <span className="prompt-name">{p.name}</span>
                    {p.description && <span className="prompt-desc">{p.description}</span>}
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

export default function McpPanel({ onClose }: { onClose: () => void }) {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const [s, c] = await Promise.all([listMcp(), listConnectors()]);
      setServers(s);
      setConnectors(c);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function connect(c: Connector) {
    setConnecting(c.key);
    setError("");
    try {
      const { authorization_url } = await connectConnector(c.key);
      // Token connectors have no auth URL — a server row was created; refresh so
      // its card appears and prompts for a personal access token.
      if (!authorization_url) {
        setConnecting(null);
        await refresh();
        return;
      }
      const tab = window.open(authorization_url, "_blank");
      // When the callback page signals completion, refresh and stop.
      const onMsg = (e: MessageEvent) => {
        if (e.data === "mcp-oauth-done") finish();
      };
      const finish = () => {
        window.removeEventListener("message", onMsg);
        clearInterval(poll);
        setConnecting(null);
        refresh();
      };
      window.addEventListener("message", onMsg);
      // Fallback: also poll for the auth tab closing.
      const poll = setInterval(() => {
        if (!tab || tab.closed) finish();
      }, 800);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start OAuth");
      setConnecting(null);
    }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !url.trim()) return;
    setBusy(true);
    setError("");
    try {
      await attachMcp(name.trim(), url.trim());
      setName("");
      setUrl("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to attach");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    await detachMcp(id);
    await refresh();
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>MCP Servers</h2>
          <button className="icon-btn" onClick={onClose}>
            ✕
          </button>
        </div>
        <p className="modal-sub">
          Connect a service in one click, or attach any MCP server by URL. Its tools and prompts
          are shown below — toggle exactly which tools the agent may use.
        </p>

        <div className="section-label">Connectors</div>
        <div className="connector-grid">
          {connectors.map((c) => (
            <button
              key={c.key}
              className={`connector-card ${c.connected ? "connected" : ""}`}
              disabled={connecting !== null}
              onClick={() => (c.connected ? undefined : connect(c))}
              title={c.description}
            >
              <span className="connector-name">{c.name}</span>
              <span className="connector-desc">{c.description}</span>
              <span className="connector-status">
                {c.connected ? "✓ Connected" : connecting === c.key ? "Connecting…" : "Connect"}
              </span>
            </button>
          ))}
        </div>

        <div className="section-label">Add by URL</div>
        <form className="mcp-form" onSubmit={add}>
          <input placeholder="Name (e.g. weather)" value={name} onChange={(e) => setName(e.target.value)} />
          <input placeholder="https://server/mcp" value={url} onChange={(e) => setUrl(e.target.value)} />
          <button type="submit" disabled={busy}>
            {busy ? "Attaching…" : "Attach"}
          </button>
        </form>
        {error && <div className="modal-error">{error}</div>}

        <div className="server-list">
          {servers.length === 0 && <div className="empty-note">No MCP servers attached yet.</div>}
          {servers.map((s) => (
            <ServerCard key={s.id} server={s} onDetach={remove} />
          ))}
        </div>
      </div>
    </div>
  );
}
