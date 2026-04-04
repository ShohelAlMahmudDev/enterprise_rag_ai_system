import logging
from typing import Any

from app.schemas.query import (
    QueryDebugInfo,
    QueryResponse,
    QuerySource,
    RetrievedChunkDebug,
)
from app.services.agent_service import AgentService
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class RAGService:
    """
    High-level RAG query service.

    Responsibilities:
    - validate incoming queries
    - detect query language
    - delegate answering to AgentService
    - normalize returned structured sources/debug payloads
    - provide safe fallback responses on failure
    """

    def __init__(
        self,
        *,
        embedder: EmbeddingService | None = None,
        agent: AgentService | None = None,
    ) -> None:
        self.embedder = embedder or EmbeddingService()
        self.agent = agent or AgentService()

    def query(
        self,
        question: str,
        session_id: str | None = None,
        debug: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> QueryResponse:
        cleaned_question = self._clean_question(question)
        if not cleaned_question:
            return self._build_empty_question_response()

        language = self._detect_language(cleaned_question)

        try:
            result = self.agent.answer(
                question=cleaned_question,
                session_id=session_id,
                debug=debug,
                filters=filters,
            )
        except TypeError:
            try:
                result = self.agent.answer(
                    question=cleaned_question,
                    session_id=session_id,
                    debug=debug,
                )
            except Exception as exc:
                logger.exception("RAG query failed: %s", exc)
                return self._build_error_response(language=language)
        except Exception as exc:
            logger.exception("RAG query failed: %s", exc)
            return self._build_error_response(language=language)

        if not isinstance(result, dict):
            logger.warning("AgentService returned non-dict result: %r", type(result))
            return self._build_invalid_result_response(language=language)

        debug_payload = self._build_debug_payload(result.get("debug"))
        sources = self._normalize_sources(result.get("sources"))

        answer = self._safe_text(result.get("answer")) or "I could not generate an answer."
        confidence = self._normalize_confidence(result.get("confidence"))
        tool_used = self._safe_text(result.get("tool_used"))

        return QueryResponse(
            answer=answer,
            sources=sources,
            language=language,
            tool_used=tool_used,
            confidence=confidence,
            debug=debug_payload,
        )

    def _build_debug_payload(self, debug_data: Any) -> QueryDebugInfo | None:
        if not debug_data or not isinstance(debug_data, dict):
            return None

        retrieved_chunks_raw = debug_data.get("retrieved_chunks", [])
        retrieved_chunks: list[RetrievedChunkDebug] = []

        if isinstance(retrieved_chunks_raw, list):
            for item in retrieved_chunks_raw:
                if not isinstance(item, dict):
                    continue
                try:
                    retrieved_chunks.append(RetrievedChunkDebug(**item))
                except Exception as exc:
                    logger.warning("Skipping invalid debug chunk payload: %s | item=%r", exc, item)

        top_k = debug_data.get("top_k", 0)
        if not isinstance(top_k, int):
            top_k = 0

        llm_context_preview = debug_data.get("llm_context_preview")
        if llm_context_preview is not None and not isinstance(llm_context_preview, str):
            llm_context_preview = str(llm_context_preview)

        try:
            return QueryDebugInfo(
                retrieved_chunks=retrieved_chunks,
                top_k=top_k,
                llm_context_preview=llm_context_preview,
            )
        except Exception as exc:
            logger.warning("Failed to build QueryDebugInfo: %s", exc)
            return None

    def _normalize_sources(self, raw_sources: Any) -> list[QuerySource]:
        if raw_sources is None:
            return []

        if not isinstance(raw_sources, list):
            logger.warning("Expected sources to be a list, got %r", type(raw_sources))
            return []

        normalized: list[QuerySource] = []

        for item in raw_sources:
            if item is None:
                continue

            if isinstance(item, QuerySource):
                normalized.append(item)
                continue

            if isinstance(item, dict):
                try:
                    normalized.append(QuerySource(**self._normalize_source_dict(item)))
                except Exception as exc:
                    logger.warning("Skipping invalid source payload: %s | item=%r", exc, item)
                continue

            if isinstance(item, str):
                try:
                    normalized.append(QuerySource(label=item))
                except Exception as exc:
                    logger.warning("Skipping invalid string source payload: %s | item=%r", exc, item)
                continue

            logger.warning("Skipping unsupported source payload type: %r", type(item))

        return normalized

    def _normalize_source_dict(self, source: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(source)

        for key in ("score", "final_score"):
            if key in normalized:
                try:
                    normalized[key] = float(normalized[key]) if normalized[key] is not None else None
                except Exception:
                    normalized[key] = None

        string_like_fields = (
            "logical_name",
            "filename",
            "file_type",
            "sheet",
            "sheet_name",
            "heading",
            "title",
            "document_id",
            "version_id",
            "diagram_type",
            "source_modality",
            "content_type",
            "label",
        )

        for key in string_like_fields:
            if key in normalized and normalized[key] is not None and not isinstance(normalized[key], str):
                normalized[key] = str(normalized[key])

        return normalized

    def _build_empty_question_response(self) -> QueryResponse:
        return QueryResponse(
            answer="Please provide a non-empty question.",
            sources=[],
            language="unknown",
            tool_used=None,
            confidence=0.0,
            debug=None,
        )

    def _build_error_response(self, *, language: str) -> QueryResponse:
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

    def _build_invalid_result_response(self, *, language: str) -> QueryResponse:
        return QueryResponse(
            answer="I could not generate an answer.",
            sources=[],
            language=language,
            tool_used=None,
            confidence=0.0,
            debug=None,
        )

    def _detect_language(self, text: str) -> str:
        try:
            return self.embedder.detect_language(text)
        except Exception as exc:
            logger.warning("Language detection failed: %s", exc)
            return "unknown"

    def _clean_question(self, question: str | None) -> str:
        if question is None:
            return ""
        return question.strip()

    def _normalize_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except Exception:
            return 0.0

        if confidence < 0.0:
            return 0.0
        if confidence > 1.0:
            return 1.0
        return confidence

    def _safe_text(self, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        value = value.strip()
        return value or None