import type { ChatSession } from "../sessionStore";

type SidebarProps = {
  sessions: ChatSession[];
  activeSessionId: string;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  onDeleteSession: (sessionId: string) => void;
};

export function Sidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
}: SidebarProps) {
  return (
    <aside
      style={{
        width: 280,
        borderRight: "1px solid #374151",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        background: "#0f172a",
        color: "#f9fafb",
        minHeight: "100vh",
        boxSizing: "border-box",
      }}
    >
      <button
        onClick={onNewChat}
        style={{
          padding: "12px 14px",
          borderRadius: 10,
          border: "1px solid #374151",
          background: "#1f2937",
          color: "#f9fafb",
          cursor: "pointer",
          fontWeight: 600,
        }}
      >
        + New Chat
      </button>

      <div
        style={{
          fontSize: 13,
          fontWeight: 700,
          color: "#9ca3af",
          marginTop: 4,
        }}
      >
        Conversations
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 8,
          overflowY: "auto",
        }}
      >
        {sessions.map((session) => {
          const active = session.id === activeSessionId;

          return (
            <div
              key={session.id}
              style={{
                border: active ? "1px solid #60a5fa" : "1px solid #374151",
                background: active ? "#1e3a8a" : "#111827",
                borderRadius: 12,
                padding: 10,
                color: "#f9fafb",
              }}
            >
              <button
                onClick={() => onSelectSession(session.id)}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  padding: 0,
                  color: "inherit",
                }}
              >
                <div
                  style={{
                    fontWeight: 600,
                    fontSize: 14,
                    color: "#f9fafb",
                    marginBottom: 4,
                  }}
                >
                  {session.title}
                </div>

                <div style={{ fontSize: 12, color: "#9ca3af" }}>
                  {new Date(session.createdAt).toLocaleString()}
                </div>
              </button>

              <div style={{ marginTop: 8 }}>
                <button
                  onClick={() => onDeleteSession(session.id)}
                  style={{
                    border: "none",
                    background: "transparent",
                    color: "#fca5a5",
                    cursor: "pointer",
                    fontSize: 12,
                    padding: 0,
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}