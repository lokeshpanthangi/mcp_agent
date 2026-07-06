import { McpCommand } from "../api";

interface Props {
  commands: McpCommand[];
  query: string;
  activeIndex: number;
  onSelect: (cmd: McpCommand) => void;
}

export default function SlashCommandMenu({ commands, query, activeIndex, onSelect }: Props) {
  if (commands.length === 0) {
    return (
      <div className="slash-menu">
        <div className="slash-menu-empty">
          {query
            ? `No commands match “/${query}”`
            : "No MCP slash-commands yet. Connect a server that exposes prompts."}
        </div>
      </div>
    );
  }

  return (
    <div className="slash-menu" role="listbox" aria-label="MCP slash commands">
      <div className="slash-menu-head">MCP commands</div>
      {commands.map((cmd, i) => (
        <button
          key={`${cmd.server}:${cmd.name}`}
          type="button"
          role="option"
          aria-selected={i === activeIndex}
          className={`slash-menu-item${i === activeIndex ? " active" : ""}`}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onSelect(cmd)}
        >
          <span className="slash-menu-cmd">{cmd.usage || cmd.slash}</span>
          <span className="slash-menu-meta">
            {cmd.server}
            {cmd.description ? ` · ${cmd.description}` : ""}
          </span>
        </button>
      ))}
    </div>
  );
}
