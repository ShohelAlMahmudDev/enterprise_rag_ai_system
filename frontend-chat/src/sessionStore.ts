export type ChatSession = {
  id: string;
  title: string;
  createdAt: string;
};

const STORAGE_KEY = "enterprise_rag_chat_sessions";
const ACTIVE_KEY = "enterprise_rag_active_session_id";

function safeParse(value: string | null): ChatSession[] {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function getSessions(): ChatSession[] {
  return safeParse(localStorage.getItem(STORAGE_KEY));
}

export function saveSessions(sessions: ChatSession[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

export function getActiveSessionId(): string | null {
  return localStorage.getItem(ACTIVE_KEY);
}

export function setActiveSessionId(sessionId: string): void {
  localStorage.setItem(ACTIVE_KEY, sessionId);
}

export function createSession(title = "New Chat"): ChatSession {
  return {
    id: crypto.randomUUID(),
    title,
    createdAt: new Date().toISOString(),
  };
}

export function ensureInitialSession(): ChatSession {
  const sessions = getSessions();
  const activeId = getActiveSessionId();

  if (sessions.length > 0 && activeId) {
    const active = sessions.find((s) => s.id === activeId);
    if (active) return active;
  }

  const newSession = createSession();
  const nextSessions = [newSession, ...sessions];
  saveSessions(nextSessions);
  setActiveSessionId(newSession.id);
  return newSession;
}

export function addSession(session: ChatSession): ChatSession[] {
  const sessions = getSessions();
  const next = [session, ...sessions];
  saveSessions(next);
  setActiveSessionId(session.id);
  return next;
}

export function removeSession(sessionId: string): ChatSession[] {
  const sessions = getSessions().filter((s) => s.id !== sessionId);
  saveSessions(sessions);

  const currentActive = getActiveSessionId();
  if (currentActive === sessionId) {
    if (sessions.length > 0) {
      setActiveSessionId(sessions[0].id);
    } else {
      const fresh = createSession();
      saveSessions([fresh]);
      setActiveSessionId(fresh.id);
      return [fresh];
    }
  }

  return getSessions();
}

export function renameSession(sessionId: string, title: string): ChatSession[] {
  const sessions = getSessions().map((s) =>
    s.id === sessionId ? { ...s, title } : s
  );
  saveSessions(sessions);
  return sessions;
}