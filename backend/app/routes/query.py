
from functools import lru_cache

from fastapi import APIRouter
from pydantic import BaseModel

from app.schemas.query import (
    ChatHistoryItem,
    ChatHistoryResponse,
    QueryRequest,
    QueryResponse,
)
from app.services.rag_service import RAGService

router = APIRouter(tags=["query"])


@lru_cache(maxsize=1)
def get_rag_service() -> RAGService:
    return RAGService()


class ClearSessionRequest(BaseModel):
    session_id: str


@router.post("/query", response_model=QueryResponse)
def query_documents(payload: QueryRequest) -> QueryResponse:
    rag_service = get_rag_service()
    return rag_service.query(
        question=payload.question,
        session_id=payload.session_id,
        debug=payload.debug,
    )


@router.post("/query/clear-session")
def clear_session(payload: ClearSessionRequest) -> dict:
    rag_service = get_rag_service()
    rag_service.agent.memory.clear_session(payload.session_id)
    return {
        "message": "Session memory cleared successfully.",
        "session_id": payload.session_id,
    }


@router.get("/query/history/{session_id}", response_model=ChatHistoryResponse)
def get_chat_history(session_id: str) -> ChatHistoryResponse:
    rag_service = get_rag_service()
    rows = rag_service.agent.memory.get_full_history(session_id)

    return ChatHistoryResponse(
        session_id=session_id,
        items=[ChatHistoryItem(**row) for row in rows],
    )