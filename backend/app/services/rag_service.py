
# from app.schemas.query import QueryResponse, QueryDebugInfo, RetrievedChunkDebug
# from app.services.agent_service import AgentService
# from app.services.embedding_service import EmbeddingService


# class RAGService:
#     def __init__(self) -> None:
#         self.embedder = EmbeddingService()
#         self.agent = AgentService()

#     def query(self, question: str, session_id: str | None = None, debug: bool = False) -> QueryResponse:
#         language = self.embedder.detect_language(question)

#         if not question or not question.strip():
#             return QueryResponse(
#                 answer="Please provide a non-empty question.",
#                 sources=[],
#                 language=language,
#                 tool_used=None,
#                 confidence=0.0,
#                 debug=None,
#             )

#         result = self.agent.answer(question=question, session_id=session_id, debug=debug)

#         debug_payload = None
#         if result.get("debug"):
#             debug_payload = QueryDebugInfo(
#                 retrieved_chunks=[
#                     RetrievedChunkDebug(**item)
#                     for item in result["debug"].get("retrieved_chunks", [])
#                 ],
#                 top_k=result["debug"].get("top_k", 0),
#                 llm_context_preview=result["debug"].get("llm_context_preview"),
#             )

#         return QueryResponse(
#             answer=result["answer"],
#             sources=result.get("sources", []),
#             language=language,
#             tool_used=result.get("tool_used"),
#             confidence=result.get("confidence"),
#             debug=debug_payload,
#         )

import logging

from app.schemas.query import QueryDebugInfo, QueryResponse, RetrievedChunkDebug
from app.services.agent_service import AgentService
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class RAGService:
    def __init__(self) -> None:
        self.embedder = EmbeddingService()
        self.agent = AgentService()

    def query(
        self,
        question: str,
        session_id: str | None = None,
        debug: bool = False,
    ) -> QueryResponse:
        if not question or not question.strip():
            return QueryResponse(
                answer="Please provide a non-empty question.",
                sources=[],
                language="unknown",
                tool_used=None,
                confidence=0.0,
                debug=None,
            )

        language = self.embedder.detect_language(question)

        try:
            result = self.agent.answer(
                question=question,
                session_id=session_id,
                debug=debug,
            )
        except Exception as exc:
            logger.exception("RAG query failed: %s", exc)
            return QueryResponse(
                answer=(
                    "I ran into an internal error while processing your request. "
                    "Please try again."
                ),
                sources=[],
                language=language,
                tool_used=None,
                confidence=0.0,
                debug=None,
            )

        debug_payload = None
        debug_data = result.get("debug")

        if debug_data:
            debug_payload = QueryDebugInfo(
                retrieved_chunks=[
                    RetrievedChunkDebug(**item)
                    for item in debug_data.get("retrieved_chunks", [])
                ],
                top_k=debug_data.get("top_k", 0),
                llm_context_preview=debug_data.get("llm_context_preview"),
            )

        return QueryResponse(
            answer=result.get("answer", "I could not generate an answer."),
            sources=result.get("sources", []),
            language=language,
            tool_used=result.get("tool_used"),
            confidence=result.get("confidence", 0.0),
            debug=debug_payload,
        )