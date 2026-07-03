import { useEffect, useState } from "react";
import { getSettings, updateSettings } from "../api";

export default function SettingsModal({ onClose }: { onClose: () => void }) {
  const [prompt, setPrompt] = useState("");
  const [defaultPrompt, setDefaultPrompt] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getSettings()
      .then((s) => {
        setPrompt(s.system_prompt);
        setDefaultPrompt(s.default_prompt);
        setApiKey(s.ollama_api_key);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  async function save() {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      const s = await updateSettings(prompt, apiKey);
      setPrompt(s.system_prompt);
      setApiKey(s.ollama_api_key);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Settings</h2>
          <button className="icon-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        {loading ? (
          <div className="empty-note">Loading…</div>
        ) : (
          <>
            <div className="field">
              <div className="field-head">
                <label>System prompt</label>
                <button
                  className="link-btn"
                  onClick={() => setPrompt(defaultPrompt)}
                  disabled={prompt === defaultPrompt}
                >
                  Reset to default
                </button>
              </div>
              <p className="field-hint">Instructions that shape how the agent behaves in every chat.</p>
              <textarea
                className="prompt-area"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={8}
              />
            </div>

            <div className="field">
              <div className="field-head">
                <label>Ollama API key</label>
                <button className="link-btn" onClick={() => setShowKey((s) => !s)}>
                  {showKey ? "Hide" : "Show"}
                </button>
              </div>
              <p className="field-hint">
                Your personal Ollama key. Used for your requests. Leave blank to use the server default.
              </p>
              <input
                className="key-input"
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Paste your Ollama API key…"
                autoComplete="off"
              />
            </div>

            {error && <div className="modal-error">{error}</div>}

            <div className="modal-actions">
              {saved && <span className="saved-note">✓ Saved</span>}
              <button className="primary-btn" onClick={save} disabled={saving}>
                {saving ? "Saving…" : "Save changes"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
