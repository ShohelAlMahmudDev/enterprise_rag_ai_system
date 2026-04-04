import logging

from fastapi import APIRouter

from app.schemas.query import ChatHistoryResponse, QueryRequest, QueryResponse
from app.services.memory_service import MemoryService
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])

rag_service = RAGService()
memory_service = MemoryService()


@router.post("", response_model=QueryResponse)
def query_documents(request: QueryRequest) -> QueryResponse:
    logger.info(
        "Received query request | session_id=%s | debug=%s | has_filters=%s",
        request.session_id,
        request.debug,
        bool(request.filters),
    )

    return rag_service.query(
        question=request.question,
        session_id=request.session_id,
        debug=request.debug,
        filters=request.filters,
    )


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
def get_chat_history(session_id: str) -> ChatHistoryResponse:
    items = memory_service.get_recent_messages(session_id) or []

    normalized_items = []
    for item in items:
        normalized_items.append(
            {
                "id": str(item.get("id") or ""),
                "role": str(item.get("role") or "unknown"),
                "content": str(item.get("content") or ""),
                "created_at": item.get("created_at"),
            }
        )

    return ChatHistoryResponse(
        session_id=session_id,
        items=normalized_items,
    )