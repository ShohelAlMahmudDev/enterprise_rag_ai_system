const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export interface QueryRequest {
  question: string;
  session_id?: string;
  debug?: boolean;
}

export interface RetrievedChunkDebug {
  filename?: string;
  logical_name?: string;
  chunk_id?: number | string;
  score?: number;
  preview?: string;
}

export interface QueryDebugInfo {
  retrieved_chunks: RetrievedChunkDebug[];
  top_k: number;
  llm_context_preview?: string;
}

export interface QueryResponse {
  answer: string;
  language?: string;
  sources: string[];
  tool_used?: string;
  confidence?: number;
  debug?: QueryDebugInfo | null;
}

export interface ChatHistoryItem {
  id: string;
  role: string;
  content: string;
  created_at?: string | null;
}

export interface ChatHistoryResponse {
  session_id: string;
  items: ChatHistoryItem[];
}

export async function askQuestion(payload: QueryRequest): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE_URL}/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Query failed: ${response.status} ${text}`);
  }

  return response.json();
}

export async function clearSession(sessionId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/query/clear-session`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ session_id: sessionId }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Clear session failed: ${response.status} ${text}`);
  }
}

export async function getChatHistory(sessionId: string): Promise<ChatHistoryResponse> {
  const response = await fetch(`${API_BASE_URL}/query/history/${sessionId}`);

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`History load failed: ${response.status} ${text}`);
  }

  return response.json();
}