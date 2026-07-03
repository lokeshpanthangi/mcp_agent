import { useState } from "react";
import { login } from "../api";

export default function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    setError("");
    try {
      await login(email.trim());
      onLoggedIn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-mark">✦</div>
        <h1>MCP Agent</h1>
        <p className="login-sub">Sign in with your email — no password needed.</p>
        <form onSubmit={submit}>
          <input
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoFocus
          />
          <button type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Continue"}
          </button>
        </form>
        {error && <div className="login-error">{error}</div>}
      </div>
    </div>
  );
}
