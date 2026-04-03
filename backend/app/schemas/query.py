from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str
    session_id: str | None = None
    debug: bool = False


class RetrievedChunkDebug(BaseModel):
    filename: str | None = None
    logical_name: str | None = None
    chunk_id: int | str | None = None
    score: float = 0.0
    preview: str = ""


class QueryDebugInfo(BaseModel):
    retrieved_chunks: list[RetrievedChunkDebug] = Field(default_factory=list)
    top_k: int = 0
    llm_context_preview: str | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)
    language: str = "unknown"
    tool_used: str | None = None
    confidence: float | None = None
    debug: QueryDebugInfo | None = None


class ChatHistoryItem(BaseModel):
    id: str
    role: str
    content: str
    created_at: str | None = None


class ChatHistoryResponse(BaseModel):
    session_id: str
    items: list[ChatHistoryItem] = Field(default_factory=list)