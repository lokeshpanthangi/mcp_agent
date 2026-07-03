import { useEffect, useRef, useState } from "react";
import { chat, getMessages } from "../api";
import Message, { UiMessage } from "./Message";

interface Props {
  conversationId: number;
  onFirstMessage: () => void;
}

export default function Chat({ conversationId, onFirstMessage }: Props) {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    getMessages(conversationId).then((history) => {
      if (!cancelled) setMessages(history.map((m) => ({ role: m.role, content: m.content })));
    });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Update the final (assistant) message in place as stream events arrive.
  function patchLast(fn: (m: UiMessage) => UiMessage) {
    setMessages((prev) => {
      const copy = [...prev];
      copy[copy.length - 1] = fn(copy[copy.length - 1]);
      return copy;
    });
  }

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
    const isFirst = messages.length === 0;
    setInput("");
    setStreaming(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: "", reasoning: "", tools: [], streaming: true },
    ]);

    await chat(conversationId, text, {
      onReasoning: (t) => patchLast((m) => ({ ...m, reasoning: (m.reasoning ?? "") + t })),
      onToken: (t) => patchLast((m) => ({ ...m, content: m.content + t })),
      onToolCall: (name, inp) =>
        patchLast((m) => ({ ...m, tools: [...(m.tools ?? []), { name, input: inp }] })),
      onToolResult: (name, output) =>
        patchLast((m) => {
          const tools = [...(m.tools ?? [])];
          for (let i = tools.length - 1; i >= 0; i--) {
            if (tools[i].name === name && !tools[i].output) {
              tools[i] = { ...tools[i], output };
              break;
            }
          }
          return { ...m, tools };
        }),
      onError: (message) => patchLast((m) => ({ ...m, error: message })),
      onDone: () => {
        patchLast((m) => ({ ...m, streaming: false }));
        setStreaming(false);
        if (isFirst) onFirstMessage();
      },
    });
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="chat">
      <div className="messages" ref={scrollRef}>
        <div className="messages-inner">
          {messages.length === 0 && (
            <div className="welcome">
              <div className="welcome-mark">✦</div>
              <h2>How can I help?</h2>
              <p>Ask anything. Attach an MCP server to give me tools.</p>
            </div>
          )}
          {messages.map((m, i) => (
            <Message key={i} msg={m} />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="composer">
        <div className="composer-inner">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Message the agent…"
            rows={1}
          />
          <button className="send-btn" onClick={send} disabled={streaming || !input.trim()}>
            {streaming ? "…" : "↑"}
          </button>
        </div>
      </div>
    </div>
  );
}
