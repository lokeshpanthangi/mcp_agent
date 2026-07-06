import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { chat, getMessages, McpCommand, ModelInfo } from "../api";
import { playComplete, playSend } from "../sound";
import Message, { UiMessage } from "./Message";
import ModelSelector from "./ModelSelector";
import SlashCommandMenu from "./SlashCommandMenu";
import { filterCommands, loadMcpCommands, missingPromptArgs, slashQuery } from "./slashCommands";

interface Props {
  conversationId: number;
  onFirstMessage: () => void;
  model: string;
  models: ModelInfo[];
  onSelectModel: (name: string) => void;
}

export default function Chat({
  conversationId,
  onFirstMessage,
  model,
  models,
  onSelectModel,
}: Props) {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [commands, setCommands] = useState<McpCommand[]>([]);
  const [activeCmd, setActiveCmd] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const refreshCommands = useCallback(() => {
    loadMcpCommands().then(setCommands);
  }, []);

  useEffect(() => {
    refreshCommands();
  }, [refreshCommands]);

  useEffect(() => {
    let cancelled = false;
    getMessages(conversationId).then((history) => {
      if (!cancelled)
        setMessages(
          history.map((m) => ({
            role: m.role,
            content: m.content,
            reasoning: m.reasoning ?? undefined,
          })),
        );
    });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const query = slashQuery(input, commands);
  const menuOpen = query !== null && !streaming;
  const filtered = useMemo(
    () => (menuOpen ? filterCommands(commands, query) : []),
    [commands, menuOpen, query],
  );

  useEffect(() => {
    setActiveCmd(0);
  }, [query, filtered.length]);

  useEffect(() => {
    if (query === "") refreshCommands();
  }, [query, refreshCommands]);

  function patchLast(fn: (m: UiMessage) => UiMessage) {
    setMessages((prev) => {
      const copy = [...prev];
      copy[copy.length - 1] = fn(copy[copy.length - 1]);
      return copy;
    });
  }

  function pickCommand(cmd: McpCommand) {
    setInput(`${cmd.slash} `);
    setActiveCmd(0);
    textareaRef.current?.focus();
  }

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;

    const argError = missingPromptArgs(text, commands);
    if (argError) {
      setMessages((prev) => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: "", error: argError },
      ]);
      setInput("");
      return;
    }

    const isFirst = messages.length === 0;
    setInput("");
    setStreaming(true);
    playSend();
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
      onMcpPrompt: (name, server) =>
        patchLast((m) => ({
          ...m,
          tools: [...(m.tools ?? []), { name, kind: "prompt", server }],
        })),
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
        playComplete();
        if (isFirst) onFirstMessage();
      },
    });
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (menuOpen && filtered.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveCmd((i) => (i + 1) % filtered.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveCmd((i) => (i - 1 + filtered.length) % filtered.length);
        return;
      }
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        pickCommand(filtered[activeCmd]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setInput("");
        return;
      }
    }

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
              <p>Ask anything. Type / for MCP slash-commands.</p>
            </div>
          )}
          {messages.map((m, i) => (
            <Message key={i} msg={m} />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="composer">
        <div className="composer-bar">
          <ModelSelector model={model} models={models} onSelect={onSelectModel} />
        </div>
        <div className="composer-wrap">
          {menuOpen && (
            <SlashCommandMenu
              commands={filtered}
              query={query}
              activeIndex={activeCmd}
              onSelect={pickCommand}
            />
          )}
          <div className="composer-inner">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Message the agent…  type / for commands"
              rows={1}
            />
            <button className="send-btn" onClick={send} disabled={streaming || !input.trim()}>
              {streaming ? "…" : "↑"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
