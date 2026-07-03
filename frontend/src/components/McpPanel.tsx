import { useEffect, useState } from "react";
import { attachMcp, detachMcp, listMcp, McpServer } from "../api";

export default function McpPanel({ onClose }: { onClose: () => void }) {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      setServers(await listMcp());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

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
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>MCP Servers</h2>
          <button className="icon-btn" onClick={onClose}>
            ✕
          </button>
        </div>
        <p className="modal-sub">
          Attach a Model Context Protocol server to give the agent its tools. They apply to every
          chat.
        </p>

        <form className="mcp-form" onSubmit={add}>
          <input placeholder="Name (e.g. weather)" value={name} onChange={(e) => setName(e.target.value)} />
          <input placeholder="https://server/mcp" value={url} onChange={(e) => setUrl(e.target.value)} />
          <button type="submit" disabled={busy}>
            {busy ? "Attaching…" : "Attach"}
          </button>
        </form>
        {error && <div className="modal-error">{error}</div>}

        <div className="mcp-list">
          {servers.length === 0 && <div className="empty-note">No MCP servers attached yet.</div>}
          {servers.map((s) => (
            <div className="mcp-item" key={s.id}>
              <div className="mcp-info">
                <span className="mcp-name">{s.name}</span>
                <span className="mcp-url">{s.url}</span>
              </div>
              <button className="icon-btn danger" onClick={() => remove(s.id)}>
                ✕
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
