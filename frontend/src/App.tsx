import { useCallback, useEffect, useState } from "react";
import {
  clearToken,
  Conversation,
  createConversation,
  getToken,
  listConversations,
  me,
  User,
} from "./api";
import Chat from "./components/Chat";
import Login from "./components/Login";
import McpPanel from "./components/McpPanel";
import Sidebar from "./components/Sidebar";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [showMcp, setShowMcp] = useState(false);

  const refreshConversations = useCallback(async () => {
    const list = await listConversations();
    // newest first
    list.sort((a, b) => b.id - a.id);
    setConversations(list);
    return list;
  }, []);

  // On load, if we have a token, verify it and load conversations.
  useEffect(() => {
    if (!getToken()) {
      setReady(true);
      return;
    }
    me()
      .then(async (u) => {
        setUser(u);
        const list = await refreshConversations();
        if (list.length > 0) setActiveId(list[0].id);
      })
      .catch(() => clearToken())
      .finally(() => setReady(true));
  }, [refreshConversations]);

  async function afterLogin() {
    const u = await me();
    setUser(u);
    const list = await refreshConversations();
    if (list.length > 0) setActiveId(list[0].id);
    else await newChat();
  }

  async function newChat() {
    const conv = await createConversation();
    await refreshConversations();
    setActiveId(conv.id);
  }

  function logout() {
    clearToken();
    setUser(null);
    setConversations([]);
    setActiveId(null);
  }

  if (!ready) return <div className="boot">✦</div>;
  if (!user) return <Login onLoggedIn={afterLogin} />;

  return (
    <div className="app">
      <Sidebar
        user={user}
        conversations={conversations}
        activeId={activeId}
        onSelect={setActiveId}
        onNewChat={newChat}
        onOpenMcp={() => setShowMcp(true)}
        onLogout={logout}
      />
      <main className="main">
        {activeId ? (
          <Chat
            key={activeId}
            conversationId={activeId}
            onFirstMessage={refreshConversations}
          />
        ) : (
          <div className="empty-main">
            <button className="new-chat big" onClick={newChat}>
              ＋ Start a new chat
            </button>
          </div>
        )}
      </main>
      {showMcp && <McpPanel onClose={() => setShowMcp(false)} />}
    </div>
  );
}
