import { useCallback, useEffect, useState } from "react";
import {
  clearToken,
  Conversation,
  createConversation,
  getSettings,
  listConversations,
  listModels,
  me,
  ModelInfo,
  restoreSession,
  setModel as saveModel,
  User,
} from "./api";
import AmbientBackground from "./components/AmbientBackground";
import Chat from "./components/Chat";
import Login from "./components/Login";
import McpPanel from "./components/McpPanel";
import SettingsModal from "./components/SettingsModal";
import Sidebar from "./components/Sidebar";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [showMcp, setShowMcp] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [model, setModelState] = useState("");
  const [models, setModels] = useState<ModelInfo[]>([]);

  useEffect(() => {
    if (!user) return;
    getSettings().then((s) => setModelState(s.model)).catch(() => {});
    listModels().then(setModels).catch(() => {});
  }, [user]);

  async function selectModel(name: string) {
    setModelState(name);
    try {
      await saveModel(name);
    } catch {
      /* optimistic value kept until next reload */
    }
  }

  const refreshConversations = useCallback(async () => {
    const list = await listConversations();
    list.sort((a, b) => b.id - a.id);
    setConversations(list);
    return list;
  }, []);

  // Restore session on load — never block the login screen on conversation loading.
  useEffect(() => {
    let cancelled = false;

    restoreSession()
      .then((u) => {
        if (cancelled || !u) return;
        setUser(u);
        refreshConversations()
          .then((list) => {
            if (!cancelled && list.length > 0) setActiveId(list[0].id);
          })
          .catch(() => {});
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });

    return () => {
      cancelled = true;
    };
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

  if (!ready) {
    return (
      <div className="auth-shell">
        <AmbientBackground />
        <div className="boot">✦</div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="auth-shell">
        <AmbientBackground />
        <Login onLoggedIn={afterLogin} />
      </div>
    );
  }

  return (
    <>
      <AmbientBackground />
      <div className={`app${collapsed ? " sidebar-collapsed" : ""}`}>
        <Sidebar
          user={user}
          conversations={conversations}
          activeId={activeId}
          onSelect={setActiveId}
          onNewChat={newChat}
          onOpenMcp={() => setShowMcp(true)}
          onOpenSettings={() => setShowSettings(true)}
          onLogout={logout}
          onCollapse={() => setCollapsed(true)}
        />
        {collapsed && (
          <button className="sidebar-open-btn" title="Show sidebar" onClick={() => setCollapsed(false)}>
            ☰
          </button>
        )}
        <main className="main">
          {activeId ? (
            <Chat
              key={activeId}
              conversationId={activeId}
              onFirstMessage={refreshConversations}
              model={model}
              models={models}
              onSelectModel={selectModel}
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
        {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
      </div>
    </>
  );
}
