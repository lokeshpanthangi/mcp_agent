import { Conversation, User } from "../api";

interface Props {
  user: User;
  conversations: Conversation[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onNewChat: () => void;
  onOpenMcp: () => void;
  onLogout: () => void;
}

export default function Sidebar({
  user,
  conversations,
  activeId,
  onSelect,
  onNewChat,
  onOpenMcp,
  onLogout,
}: Props) {
  return (
    <aside className="sidebar">
      <div className="sidebar-top">
        <div className="brand">
          <span className="brand-mark">✦</span>
          <span className="brand-name">MCP Agent</span>
        </div>
        <button className="new-chat" onClick={onNewChat}>
          <span>＋</span> New chat
        </button>
      </div>

      <div className="conv-list">
        {conversations.length === 0 && <div className="empty-note">No conversations yet.</div>}
        {conversations.map((c) => (
          <button
            key={c.id}
            className={`conv-item ${c.id === activeId ? "active" : ""}`}
            onClick={() => onSelect(c.id)}
            title={c.title}
          >
            <span className="conv-dot" />
            <span className="conv-title">{c.title}</span>
          </button>
        ))}
      </div>

      <div className="sidebar-bottom">
        <button className="mcp-btn" onClick={onOpenMcp}>
          <span>🔧</span> MCP Servers
        </button>
        <div className="user-row">
          <div className="user-avatar">{user.email[0].toUpperCase()}</div>
          <span className="user-email">{user.email}</span>
          <button className="icon-btn" title="Log out" onClick={onLogout}>
            ⏻
          </button>
        </div>
      </div>
    </aside>
  );
}
