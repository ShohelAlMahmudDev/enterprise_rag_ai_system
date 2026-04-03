export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
  meta?: {
    language?: string;
    tool_used?: string;
    confidence?: number;
    sources?: string[];
    debug?: {
      top_k?: number;
      llm_context_preview?: string;
      retrieved_chunks?: Array<{
        filename?: string;
        logical_name?: string;
        chunk_id?: number | string;
        score?: number;
        preview?: string;
      }>;
    } | null;
  };
};

const KEY = "enterprise_rag_chat_messages";

type MessageMap = Record<string, ChatMessage[]>;

function readStore(): MessageMap {
  const raw = localStorage.getItem(KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeStore(store: MessageMap): void {
  localStorage.setItem(KEY, JSON.stringify(store));
}

export function getMessages(sessionId: string): ChatMessage[] {
  const store = readStore();
  return store[sessionId] ?? [];
}

export function addMessage(sessionId: string, message: ChatMessage): ChatMessage[] {
  const store = readStore();
  const existing = store[sessionId] ?? [];
  const next = [...existing, message];
  store[sessionId] = next;
  writeStore(store);
  return next;
}

export function replaceMessages(sessionId: string, messages: ChatMessage[]): ChatMessage[] {
  const store = readStore();
  store[sessionId] = messages;
  writeStore(store);
  return messages;
}

export function clearMessages(sessionId: string): void {
  const store = readStore();
  delete store[sessionId];
  writeStore(store);
}