import { useEffect, useMemo, useRef, useState } from "react";
import {
  askQuestion,
  clearSession,
  getChatHistory,
  type QueryResponse,
} from "./api";
import { Sidebar } from "./components/Sidebar";
import {
  addSession,
  createSession,
  ensureInitialSession,
  getActiveSessionId,
  getSessions,
  removeSession,
  renameSession,
  setActiveSessionId,
  type ChatSession,
} from "./sessionStore";
import { type ChatMessage } from "./chatStore";

function makeLocalMessage(
  role: ChatMessage["role"],
  content: string,
  meta?: ChatMessage["meta"]
): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    createdAt: new Date().toISOString(),
    meta,
  };
}

function mapBackendRole(role: string): ChatMessage["role"] {
  if (role === "user") return "user";
  if (role === "assistant") return "assistant";
  return "system";
}

function renderInlineText(text: string) {
  const parts = text.split(/(\*\*.*?\*\*)/g);

  return parts.map((part, index) => {
    const boldMatch = part.match(/^\*\*(.*?)\*\*$/);
    if (boldMatch) {
      return <strong key={index}>{boldMatch[1]}</strong>;
    }
    return <span key={index}>{part}</span>;
  });
}

function AssistantFormattedContent({ content }: { content: string }) {
  const lines = content.split("\n");
  const elements: JSX.Element[] = [];

  let bulletBuffer: string[] = [];
  let numberBuffer: string[] = [];

  const flushBullets = (keyPrefix: string) => {
    if (bulletBuffer.length > 0) {
      elements.push(
        <ul
          key={`${keyPrefix}-bullets-${elements.length}`}
          style={{
            margin: "10px 0 14px 0",
            paddingLeft: 22,
          }}
        >
          {bulletBuffer.map((item, idx) => (
            <li key={idx} style={{ marginBottom: 6 }}>
              {renderInlineText(item)}
            </li>
          ))}
        </ul>
      );
      bulletBuffer = [];
    }
  };

  const flushNumbers = (keyPrefix: string) => {
    if (numberBuffer.length > 0) {
      elements.push(
        <ol
          key={`${keyPrefix}-numbers-${elements.length}`}
          style={{
            margin: "10px 0 14px 0",
            paddingLeft: 22,
          }}
        >
          {numberBuffer.map((item, idx) => (
            <li key={idx} style={{ marginBottom: 6 }}>
              {renderInlineText(item)}
            </li>
          ))}
        </ol>
      );
      numberBuffer = [];
    }
  };

  lines.forEach((rawLine, idx) => {
    const line = rawLine.trim();

    if (!line) {
      flushBullets(`line-${idx}`);
      flushNumbers(`line-${idx}`);
      return;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    const altHeadingMatch = line.match(/^([A-Z][A-Za-z0-9\s/&()-]{2,}):$/);
    const bulletMatch = line.match(/^[-*•]\s+(.*)$/);
    const numberMatch = line.match(/^\d+\.\s+(.*)$/);

    if (headingMatch) {
      flushBullets(`line-${idx}`);
      flushNumbers(`line-${idx}`);

      elements.push(
        <div
          key={`heading-${idx}`}
          style={{
            fontWeight: 700,
            fontSize: 18,
            marginTop: idx === 0 ? 0 : 18,
            marginBottom: 10,
            color: "#f9fafb",
          }}
        >
          {renderInlineText(headingMatch[2])}
        </div>
      );
      return;
    }

    if (altHeadingMatch) {
      flushBullets(`line-${idx}`);
      flushNumbers(`line-${idx}`);

      elements.push(
        <div
          key={`alt-heading-${idx}`}
          style={{
            fontWeight: 700,
            fontSize: 16,
            marginTop: idx === 0 ? 0 : 16,
            marginBottom: 8,
            color: "#f9fafb",
          }}
        >
          {renderInlineText(altHeadingMatch[1])}
        </div>
      );
      return;
    }

    if (bulletMatch) {
      flushNumbers(`line-${idx}`);
      bulletBuffer.push(bulletMatch[1]);
      return;
    }

    if (numberMatch) {
      flushBullets(`line-${idx}`);
      numberBuffer.push(numberMatch[1]);
      return;
    }

    flushBullets(`line-${idx}`);
    flushNumbers(`line-${idx}`);

    elements.push(
      <div
        key={`paragraph-${idx}`}
        style={{
          marginBottom: 12,
          color: "#f3f4f6",
        }}
      >
        {renderInlineText(line)}
      </div>
    );
  });

  flushBullets("final");
  flushNumbers("final");

  return <div>{elements}</div>;
}

export default function App() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSession] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [debugMode, setDebugMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState("");
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [expandedDebugIds, setExpandedDebugIds] = useState<Record<string, boolean>>(
    {}
  );

  const threadRef = useRef<HTMLDivElement | null>(null);

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeSessionId) ?? null,
    [sessions, activeSessionId]
  );

  const toggleDebugPanel = (messageId: string) => {
    setExpandedDebugIds((prev) => ({
      ...prev,
      [messageId]: !prev[messageId],
    }));
  };

  const handleCopyMessage = async (messageId: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageId(messageId);

      window.setTimeout(() => {
        setCopiedMessageId((current) => (current === messageId ? null : current));
      }, 2000);
    } catch {
      setError("Failed to copy the answer to the clipboard.");
    }
  };

  const loadHistory = async (sessionId: string) => {
    setHistoryLoading(true);
    setError("");

    try {
      const history = await getChatHistory(sessionId);

      const mapped: ChatMessage[] = history.items.map((item: any) => ({
        id: item.id,
        role: mapBackendRole(item.role),
        content: item.content,
        createdAt: item.created_at || new Date().toISOString(),
        meta:
          item.role === "assistant"
            ? {
                language: item.language,
                tool_used: item.tool_used,
                confidence: item.confidence,
                sources: item.sources,
                debug: item.debug,
              }
            : undefined,
      }));

      setMessages(mapped);
    } catch (err) {
      setMessages([]);
      setError(err instanceof Error ? err.message : "Failed to load chat history");
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    const initial = ensureInitialSession();
    setSessions(getSessions());
    setActiveSession(initial.id);
    loadHistory(initial.id);
  }, []);

  useEffect(() => {
    if (!threadRef.current) return;
    threadRef.current.scrollTo({
      top: threadRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, loading, error, historyLoading]);

  const appendAssistantMessage = (result: QueryResponse) => {
    const assistantMessage = makeLocalMessage("assistant", result.answer, {
      language: result.language,
      tool_used: result.tool_used,
      confidence: result.confidence,
      sources: result.sources,
      debug: result.debug ?? undefined,
    });

    setMessages((prev) => [...prev, assistantMessage]);
  };

  const updateTitleIfNeeded = (userText: string) => {
    const existing = sessions.find((s) => s.id === activeSessionId);
    if (existing && existing.title === "New Chat") {
      const newTitle =
        userText.length > 40 ? `${userText.slice(0, 40)}...` : userText;
      const nextSessions = renameSession(activeSessionId, newTitle);
      setSessions(nextSessions);
    }
  };

  const handleAsk = async () => {
    if (!question.trim() || !activeSessionId || loading) return;

    const userText = question.trim();
    setQuestion("");
    setError("");
    setLoading(true);

    const tempUser = makeLocalMessage("user", userText);
    setMessages((prev) => [...prev, tempUser]);

    try {
      const result: QueryResponse = await askQuestion({
        question: userText,
        session_id: activeSessionId,
        debug: debugMode,
      });

      appendAssistantMessage(result);
      updateTitleIfNeeded(userText);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);

      const errorMessage = makeLocalMessage(
        "system",
        `There was a problem while processing your request.\n${msg}`
      );
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const getLastUserMessage = () => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === "user") {
        return messages[i];
      }
    }
    return null;
  };

  const getLastAssistantMessageId = () => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === "assistant") {
        return messages[i].id;
      }
    }
    return null;
  };

  // const handleRegenerateLastAnswer = async () => {
  //   if (!activeSessionId || loading) return;

  //   const lastUserMessage = getLastUserMessage();
  //   if (!lastUserMessage?.content.trim()) return;

  //   setError("");
  //   setLoading(true);

  //   try {
  //     const result: QueryResponse = await askQuestion({
  //       question: lastUserMessage.content,
  //       session_id: activeSessionId,
  //       debug: debugMode,
  //     });

  //     appendAssistantMessage(result);
  //   } catch (err) {
  //     const msg = err instanceof Error ? err.message : "Unknown error";
  //     setError(msg);

  //     const errorMessage = makeLocalMessage(
  //       "system",
  //       `There was a problem while regenerating the answer.\n${msg}`
  //     );
  //     setMessages((prev) => [...prev, errorMessage]);
  //   } finally {
  //     setLoading(false);
  //   }
  // };

  const handleNewChat = () => {
    const session = createSession();
    const next = addSession(session);
    setSessions(next);
    setActiveSession(session.id);
    setMessages([]);
    setQuestion("");
    setError("");
    setCopiedMessageId(null);
    setExpandedDebugIds({});
  };

  const handleSelectSession = (sessionId: string) => {
    setActiveSessionId(sessionId);
    setActiveSession(sessionId);
    setQuestion("");
    setError("");
    setCopiedMessageId(null);
    setExpandedDebugIds({});
    loadHistory(sessionId);
  };

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await clearSession(sessionId);
    } catch {
      // keep local behavior
    }

    const next = removeSession(sessionId);
    setSessions(next);

    const nextActive = getActiveSessionId();
    if (nextActive) {
      setActiveSession(nextActive);
      setCopiedMessageId(null);
      setExpandedDebugIds({});
      loadHistory(nextActive);
    } else {
      setMessages([]);
    }

    setQuestion("");
    setError("");
  };

  const handleClearCurrentChat = async () => {
    if (!activeSessionId) return;

    try {
      setLoading(true);
      setError("");
      await clearSession(activeSessionId);
      setMessages([]);
      setQuestion("");
      setCopiedMessageId(null);
      setExpandedDebugIds({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear current chat");
    } finally {
      setLoading(false);
    }
  };

  const handleQuestionKeyDown = async (
    e: React.KeyboardEvent<HTMLTextAreaElement>
  ) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      await handleAsk();
    }
  };

  const renderTechnicalDetails = (message: ChatMessage) => {
    if (!debugMode || message.role !== "assistant" || !message.meta) return null;

    const hasMeta =
      message.meta.language ||
      message.meta.tool_used ||
      typeof message.meta.confidence === "number" ||
      (message.meta.sources && message.meta.sources.length > 0) ||
      message.meta.debug;

    if (!hasMeta) return null;

    const isExpanded = !!expandedDebugIds[message.id];

    return (
      <div style={{ marginTop: 16 }}>
        <button
          onClick={() => toggleDebugPanel(message.id)}
          style={{
            padding: "8px 12px",
            borderRadius: 10,
            border: "1px solid #4b5563",
            background: "#111827",
            color: "#f9fafb",
            cursor: "pointer",
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          {isExpanded ? "Hide technical details" : "Show technical details"}
        </button>

        {isExpanded && (
          <div
            style={{
              marginTop: 12,
              border: "1px solid #374151",
              borderRadius: 14,
              background: "#111827",
              padding: 14,
            }}
          >
            <div
              style={{
                display: "flex",
                gap: 14,
                flexWrap: "wrap",
                fontSize: 13,
                color: "#d1d5db",
              }}
            >
              {message.meta.language && (
                <div>
                  <strong>Language:</strong> {message.meta.language}
                </div>
              )}
              {message.meta.tool_used && (
                <div>
                  <strong>Tool:</strong> {message.meta.tool_used}
                </div>
              )}
              {typeof message.meta.confidence === "number" && (
                <div>
                  <strong>Confidence:</strong> {message.meta.confidence}
                </div>
              )}
            </div>

            {message.meta.sources && message.meta.sources.length > 0 && (
              <div style={{ marginTop: 14 }}>
                <div
                  style={{
                    fontWeight: 700,
                    marginBottom: 8,
                    color: "#f9fafb",
                  }}
                >
                  Sources
                </div>
                <ul style={{ margin: 0, paddingLeft: 18, color: "#d1d5db" }}>
                  {message.meta.sources.map((source, idx) => (
                    <li key={idx}>{source}</li>
                  ))}
                </ul>
              </div>
            )}

            {message.meta.debug && (
              <div style={{ marginTop: 16 }}>
                <div
                  style={{
                    fontWeight: 700,
                    marginBottom: 10,
                    color: "#f9fafb",
                  }}
                >
                  Debug Information
                </div>

                <div style={{ color: "#d1d5db", marginBottom: 12 }}>
                  <strong>Top K:</strong> {message.meta.debug.top_k ?? 0}
                </div>

                {message.meta.debug.retrieved_chunks &&
                  message.meta.debug.retrieved_chunks.length > 0 && (
                    <div style={{ marginBottom: 14 }}>
                      <div
                        style={{
                          fontWeight: 700,
                          marginBottom: 10,
                          color: "#f9fafb",
                        }}
                      >
                        Retrieved Chunks
                      </div>

                      {message.meta.debug.retrieved_chunks.map((chunk, idx) => (
                        <div
                          key={idx}
                          style={{
                            border: "1px solid #4b5563",
                            borderRadius: 12,
                            padding: 12,
                            marginBottom: 10,
                            background: "#0b1220",
                            color: "#f9fafb",
                          }}
                        >
                          <div>
                            <strong>Document:</strong> {chunk.logical_name || "-"}
                          </div>
                          <div>
                            <strong>File:</strong> {chunk.filename || "-"}
                          </div>
                          <div>
                            <strong>Chunk:</strong> {String(chunk.chunk_id ?? "-")}
                          </div>
                          <div>
                            <strong>Score:</strong> {chunk.score ?? 0}
                          </div>
                          <div
                            style={{
                              marginTop: 8,
                              color: "#d1d5db",
                              whiteSpace: "pre-wrap",
                            }}
                          >
                            <strong style={{ color: "#f9fafb" }}>Preview:</strong>
                            <div style={{ marginTop: 4 }}>{chunk.preview || "-"}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                {message.meta.debug.llm_context_preview && (
                  <div>
                    <div
                      style={{
                        fontWeight: 700,
                        marginBottom: 10,
                        color: "#f9fafb",
                      }}
                    >
                      LLM Context Preview
                    </div>
                    <div
                      style={{
                        border: "1px solid #4b5563",
                        borderRadius: 12,
                        padding: 12,
                        background: "#0b1220",
                        color: "#d1d5db",
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      {message.meta.debug.llm_context_preview}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const lastAssistantMessageId = getLastAssistantMessageId();
  // const canRegenerate =
  //   !loading &&
  //   !historyLoading &&
  //   !!activeSessionId &&
  //   !!getLastUserMessage()?.content?.trim();

  return (
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        background: "#111827",
        color: "#f9fafb",
      }}
    >
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
      />

      <main
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          height: "100vh",
          background: "#111827",
          color: "#f9fafb",
        }}
      >
        <div
          style={{
            padding: "18px 24px",
            borderBottom: "1px solid #374151",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>Enterprise RAG Chat</div>
            <div style={{ color: "#9ca3af", fontSize: 13, marginTop: 4 }}>
              {activeSession?.title || "New Chat"}
            </div>
          </div>

          <div
            style={{
              display: "flex",
              gap: 12,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <label
              style={{
                display: "flex",
                gap: 8,
                alignItems: "center",
                color: "#e5e7eb",
                fontSize: 14,
              }}
            >
              <input
                type="checkbox"
                checked={debugMode}
                onChange={(e) => setDebugMode(e.target.checked)}
              />
              Show technical details
            </label>

            {/* <button
              onClick={handleRegenerateLastAnswer}
              disabled={!canRegenerate}
              style={{
                padding: "10px 14px",
                borderRadius: 10,
                border: "1px solid #374151",
                background: canRegenerate ? "#1f2937" : "#111827",
                color: canRegenerate ? "#f9fafb" : "#6b7280",
                cursor: canRegenerate ? "pointer" : "not-allowed",
                fontWeight: 600,
              }}
            >
              Regenerate Last Answer
            </button> */}

            <button
              onClick={handleClearCurrentChat}
              disabled={loading || !activeSessionId}
              style={{
                padding: "10px 14px",
                borderRadius: 10,
                border: "1px solid #374151",
                background: "#1f2937",
                color: "#f9fafb",
                cursor: "pointer",
              }}
            >
              Clear Current Chat
            </button>
          </div>
        </div>

        <div
          ref={threadRef}
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "24px 24px 8px 24px",
          }}
        >
          {historyLoading && (
            <div style={{ maxWidth: 860, margin: "0 auto", color: "#9ca3af" }}>
              Loading conversation...
            </div>
          )}

          {!historyLoading && messages.length === 0 && !loading && (
            <div
              style={{
                maxWidth: 760,
                margin: "48px auto 0 auto",
                textAlign: "center",
                color: "#9ca3af",
              }}
            >
              <div style={{ fontSize: 28, fontWeight: 700, color: "#f9fafb" }}>
                How can I help?
              </div>
              <div style={{ marginTop: 12, fontSize: 15 }}>
                Ask about your indexed documents, diagrams, or internal knowledge.
              </div>
            </div>
          )}

          <div style={{ maxWidth: 860, margin: "0 auto" }}>
            {messages.map((message) => {
              const isUser = message.role === "user";
              const isAssistant = message.role === "assistant";
              const isSystem = message.role === "system";
              const isLastAssistant = message.id === lastAssistantMessageId;

              return (
                <div
                  key={message.id}
                  style={{
                    display: "flex",
                    justifyContent: isUser ? "flex-end" : "flex-start",
                    marginBottom: 18,
                  }}
                >
                  <div
                    style={{
                      width: "100%",
                      maxWidth: isUser ? 720 : 860,
                      display: "flex",
                      justifyContent: isUser ? "flex-end" : "flex-start",
                    }}
                  >
                    <div
                      style={{
                        maxWidth: isUser ? "78%" : "100%",
                        border: isSystem
                          ? "1px solid #7f1d1d"
                          : "1px solid #374151",
                        background: isUser
                          ? "#2563eb"
                          : isSystem
                          ? "#7f1d1d"
                          : "linear-gradient(180deg, #1f2937 0%, #18212f 100%)",
                        color: "#f9fafb",
                        borderRadius: 16,
                        padding: "14px 16px",
                        whiteSpace: "pre-wrap",
                        lineHeight: 1.7,
                        boxShadow: isUser
                          ? "0 8px 24px rgba(37, 99, 235, 0.25)"
                          : "0 8px 24px rgba(0, 0, 0, 0.22)",
                      }}
                    >
                      <div style={{ fontSize: 12, color: "#d1d5db", marginBottom: 8 }}>
                        {isUser ? "You" : isSystem ? "System" : "Assistant"}
                      </div>

                      <div>
                        {isAssistant ? (
                          <AssistantFormattedContent content={message.content} />
                        ) : (
                          <div style={{ whiteSpace: "pre-wrap" }}>{message.content}</div>
                        )}
                      </div>

                      {isAssistant && (
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "flex-end",
                            gap: 10,
                            marginTop: 12,
                            flexWrap: "wrap",
                          }}
                        >
                          <button
                            onClick={() => handleCopyMessage(message.id, message.content)}
                            style={{
                              padding: "8px 12px",
                              borderRadius: 10,
                              border: "1px solid #4b5563",
                              background: "#111827",
                              color: "#f9fafb",
                              cursor: "pointer",
                              fontSize: 13,
                              fontWeight: 600,
                            }}
                          >
                            {copiedMessageId === message.id ? "Copied" : "Copy answer"}
                          </button>

                          {/* {isLastAssistant && (
                            <button
                              onClick={handleRegenerateLastAnswer}
                              disabled={!canRegenerate}
                              style={{
                                padding: "8px 12px",
                                borderRadius: 10,
                                border: "1px solid #4b5563",
                                background: canRegenerate ? "#111827" : "#0f172a",
                                color: canRegenerate ? "#f9fafb" : "#6b7280",
                                cursor: canRegenerate ? "pointer" : "not-allowed",
                                fontSize: 13,
                                fontWeight: 600,
                              }}
                            >
                              Regenerate answer
                            </button>
                          )} */}
                        </div>
                      )}

                      <div style={{ marginTop: 10 }}>{renderTechnicalDetails(message)}</div>
                    </div>
                  </div>
                </div>
              );
            })}

            {loading && (
              <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 18 }}>
                <div
                  style={{
                    border: "1px solid #374151",
                    background: "#1f2937",
                    color: "#d1d5db",
                    borderRadius: 16,
                    padding: "14px 16px",
                  }}
                >
                  Thinking...
                </div>
              </div>
            )}

            {error && <div style={{ marginTop: 12, color: "#fecaca" }}>{error}</div>}
          </div>
        </div>

        <div
          style={{
            borderTop: "1px solid #374151",
            padding: "16px 24px 20px 24px",
            background: "#111827",
          }}
        >
          <div style={{ maxWidth: 860, margin: "0 auto" }}>
            <div
              style={{
                border: "1px solid #374151",
                borderRadius: 18,
                background: "#1f2937",
                padding: 12,
              }}
            >
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleQuestionKeyDown}
                placeholder="Message Enterprise RAG Chat..."
                rows={3}
                style={{
                  width: "100%",
                  border: "none",
                  outline: "none",
                  resize: "none",
                  background: "transparent",
                  color: "#f9fafb",
                  fontSize: 15,
                  lineHeight: 1.6,
                  boxSizing: "border-box",
                }}
              />

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginTop: 10,
                  gap: 12,
                  flexWrap: "wrap",
                }}
              >
                <div style={{ color: "#9ca3af", fontSize: 12 }}>
                  Enter to send • Shift+Enter for new line
                </div>

                <button
                  onClick={handleAsk}
                  disabled={loading || !question.trim()}
                  style={{
                    padding: "10px 16px",
                    borderRadius: 12,
                    border: "1px solid #1d4ed8",
                    background: "#2563eb",
                    color: "#ffffff",
                    cursor: "pointer",
                    fontWeight: 700,
                  }}
                >
                  Send
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}