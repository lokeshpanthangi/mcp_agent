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
  const [authError, setAuthError] = useState("");

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
    setAuthError("");
    try {
      const { authorization_url } = await startServerOAuth(server.id);
      if (!authorization_url) {
        setConnecting(false);
        return;
      }
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
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "OAuth login failed");
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
          <div className="auth-msg">
            {data.supports_oauth
              ? "🔒 This server requires authentication. Sign in with the provider or paste a token."
              : "🔒 This server requires authentication."}
          </div>
          {data.supports_oauth && (
            <div className="auth-row">
              <button className="primary-btn small" onClick={login} disabled={connecting}>
                {connecting ? "Connecting…" : "Login"}
              </button>
              <span className="dim">Opens the provider&apos;s sign-in page in a new tab.</span>
            </div>
          )}
          {authError && <div className="modal-error">{authError}</div>}
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
                Slash commands <span className="dim">({data.prompts.length})</span>
              </div>
              <div className="prompt-list">
                {data.prompts.map((p) => {
                  const req = (p.arguments ?? []).filter((a) => a.required).map((a) => a.name);
                  const usage =
                    req.length === 1
                      ? `/${p.name} <${req[0]}>`
                      : req.length > 1
                        ? `/${p.name} ${req.map((n) => `${n}=...`).join(" ")}`
                        : `/${p.name}`;
                  return (
                    <div className="prompt-item" key={p.name}>
                      <span className="prompt-name">{usage}</span>
                      {p.description && <span className="prompt-desc">{p.description}</span>}
                    </div>
                  );
                })}
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
  const [connectorPage, setConnectorPage] = useState(1);
  const [connectorPages, setConnectorPages] = useState(1);
  const [connectorTotal, setConnectorTotal] = useState(0);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function refresh(page = connectorPage) {
    try {
      const [s, c] = await Promise.all([listMcp(), listConnectors(page)]);
      setServers(s);
      setConnectors(c.items);
      setConnectorPage(c.page);
      setConnectorPages(c.pages);
      setConnectorTotal(c.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }

  useEffect(() => {
    refresh(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function goToPage(page: number) {
    if (page < 1 || page > connectorPages || page === connectorPage) return;
    refresh(page);
  }

  async function connect(c: Connector) {
    setConnecting(c.key);
    setError("");
    try {
      const { authorization_url } = await connectConnector(c.key);
      if (!authorization_url) {
        setConnecting(null);
        await refresh(connectorPage);
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
        refresh(connectorPage);
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
      await refresh(connectorPage);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to attach");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    await detachMcp(id);
    await refresh(connectorPage);
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

        <div className="section-label">
          Connectors{" "}
          <span className="dim">
            ({connectorTotal} total · page {connectorPage} of {connectorPages})
          </span>
        </div>
        <div className="connector-grid">
          {connectors.map((c) => (
            <button
              key={c.key}
              className={`connector-card ${c.connected ? "connected" : ""}`}
              disabled={connecting !== null}
              onClick={() => (c.connected ? undefined : connect(c))}
              title={c.description}
            >
              {c.category && <span className="connector-cat">{c.category}</span>}
              <span className="connector-name">{c.name}</span>
              <span className="connector-desc">{c.description}</span>
              <span className="connector-status">
                {c.connected ? "✓ Connected" : connecting === c.key ? "Connecting…" : "Connect"}
              </span>
            </button>
          ))}
        </div>
        {connectorPages > 1 && (
          <div className="connector-pager">
            <button
              className="pager-btn"
              disabled={connectorPage <= 1 || connecting !== null}
              onClick={() => goToPage(connectorPage - 1)}
            >
              ← Previous
            </button>
            <span className="pager-info">
              Page {connectorPage} of {connectorPages}
            </span>
            <button
              className="pager-btn"
              disabled={connectorPage >= connectorPages || connecting !== null}
              onClick={() => goToPage(connectorPage + 1)}
            >
              Next →
            </button>
          </div>
        )}

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
