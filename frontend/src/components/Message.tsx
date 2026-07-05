import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export interface ToolEvent {
  name: string;
  input?: unknown;
  output?: string;
}

export interface UiMessage {
  role: "user" | "assistant";
  content: string;
  reasoning?: string;
  tools?: ToolEvent[];
  streaming?: boolean;
  error?: string;
}

function Reasoning({
  text,
  streaming,
  hasContent,
}: {
  text: string;
  streaming?: boolean;
  hasContent?: boolean;
}) {
  // Auto-open only while actively thinking (streaming, before any answer).
  // Once the answer starts (or on reload) it collapses; a manual click overrides.
  const [userToggled, setUserToggled] = useState<boolean | null>(null);
  const auto = !!streaming && !hasContent;
  const open = userToggled ?? auto;
  const thinking = !!streaming && !hasContent;
  return (
    <div className={`reasoning ${open ? "open" : ""}`}>
      <button className="reasoning-toggle" onClick={() => setUserToggled(!open)}>
        <span className="spark">✦</span>
        {thinking ? "Thinking…" : "Reasoning"}
        <span className="chevron">{open ? "▾" : "▸"}</span>
      </button>
      {open && <div className="reasoning-body">{text}</div>}
    </div>
  );
}

function ToolChip({ tool }: { tool: ToolEvent }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="tool">
      <button className="tool-head" onClick={() => setOpen((o) => !o)}>
        <span className="tool-icon">🔧</span>
        <span className="tool-name">{tool.name}</span>
        <span className={`tool-status ${tool.output ? "done" : "running"}`}>
          {tool.output ? "done" : "running…"}
        </span>
        <span className="chevron">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="tool-body">
          <div className="tool-section">
            <span className="tool-label">input</span>
            <pre>{JSON.stringify(tool.input, null, 2)}</pre>
          </div>
          {tool.output && (
            <div className="tool-section">
              <span className="tool-label">output</span>
              <pre>{tool.output}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Message({ msg }: { msg: UiMessage }) {
  if (msg.role === "user") {
    return (
      <div className="msg user">
        <div className="bubble">{msg.content}</div>
      </div>
    );
  }

  return (
    <div className="msg assistant">
      <div className={`avatar ${msg.streaming ? "spinning" : ""}`}>✦</div>
      <div className="assistant-body">
        {msg.reasoning && (
          <Reasoning text={msg.reasoning} streaming={msg.streaming} hasContent={!!msg.content} />
        )}
        {msg.tools?.map((t, i) => (
          <ToolChip key={i} tool={t} />
        ))}
        {msg.content && (
          <div className="markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
          </div>
        )}
        {msg.streaming && !msg.content && !msg.reasoning && (
          <div className="typing">
            <span></span>
            <span></span>
            <span></span>
          </div>
        )}
        {msg.error && <div className="msg-error">⚠ {msg.error}</div>}
      </div>
    </div>
  );
}
