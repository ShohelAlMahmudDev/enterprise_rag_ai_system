import logging
import re
from typing import Any

from app.services.comparison_service import ComparisonService
from app.services.llm_service import LocalLLM
from app.services.memory_service import MemoryService
from app.services.query_rewrite_service import QueryRewriteService
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)

try:
    from app.services.vision_service import VisionService
except Exception as exc:
    logger.warning("VisionService import failed: %s", exc)
    VisionService = None


class AgentService:
    """
    Main orchestration service for answer generation.

    Responsibilities:
    - choose the appropriate retrieval/tool strategy
    - rewrite technical/table lookup queries when useful
    - incorporate recent conversation context only when it helps
    - retrieve relevant chunks
    - call the LLM with grounded context
    - return answer, structured sources, confidence, and optional debug data
    """

    def __init__(
        self,
        *,
        retrieval: RetrievalService | None = None,
        compare: ComparisonService | None = None,
        memory: MemoryService | None = None,
        llm: LocalLLM | None = None,
        query_rewriter: QueryRewriteService | None = None,
    ) -> None:
        self.retrieval = retrieval or RetrievalService()
        self.compare = compare or ComparisonService()
        self.memory = memory or MemoryService()
        self.llm = llm or LocalLLM()
        self.query_rewriter = query_rewriter or QueryRewriteService()

        try:
            self.vision = VisionService() if VisionService is not None else None
        except Exception as exc:
            logger.warning("Vision service initialization failed: %s", exc)
            self.vision = None

    def answer(
        self,
        question: str,
        session_id: str | None = None,
        debug: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cleaned_question = (question or "").strip()
        if not cleaned_question:
            return self._empty_answer(debug=debug)

        tool = self._choose_tool(cleaned_question)

        try:
            history = self.memory.get_recent_messages(session_id) if session_id else []
            rewritten = self.query_rewriter.rewrite(cleaned_question)

            retrieval_query = self._build_retrieval_query(
                question=cleaned_question,
                rewritten_query=rewritten.rewritten,
                history=history,
                is_lookup=rewritten.is_lookup,
            )

            generation_question = self._build_generation_question(
                question=cleaned_question,
                history=history,
                is_lookup=rewritten.is_lookup,
            )

            results = self._run_tool(
                tool=tool,
                retrieval_query=retrieval_query,
                filters=filters,
            )

            if not results:
                answer = self._build_no_evidence_answer(cleaned_question)
                response = {
                    "answer": answer,
                    "tool_used": tool,
                    "sources": [],
                    "confidence": 0.0,
                }

                if session_id:
                    self._store_session_messages(session_id, cleaned_question, answer)

                if debug:
                    response["debug"] = {
                        "retrieved_chunks": [],
                        "top_k": 0,
                        "llm_context_preview": "",
                        "rewritten_query": rewritten.rewritten,
                        "is_lookup_query": rewritten.is_lookup,
                    }

                return response

            answer, llm_context_preview = self._generate_with_context(results, generation_question)

            if session_id:
                self._store_session_messages(session_id, cleaned_question, answer)

            response = {
                "answer": answer,
                "tool_used": tool,
                "sources": self._build_sources(results),
                "confidence": self._estimate_confidence(results),
            }

            if debug:
                debug_payload = self._build_debug_payload(results, llm_context_preview)
                debug_payload["rewritten_query"] = rewritten.rewritten
                debug_payload["is_lookup_query"] = rewritten.is_lookup
                debug_payload["detected_numbers"] = rewritten.detected_numbers
                debug_payload["detected_fields"] = rewritten.detected_fields
                response["debug"] = debug_payload

            return response

        except Exception as exc:
            logger.exception("Agent answer flow failed: %s", exc)

            return {
                "answer": (
                    "I ran into an internal problem while processing your request. "
                    "Please try again."
                ),
                "tool_used": tool,
                "sources": [],
                "confidence": 0.0,
                "debug": {
                    "retrieved_chunks": [],
                    "top_k": 0,
                    "llm_context_preview": "",
                } if debug else None,
            }

    def _run_tool(
        self,
        *,
        tool: str,
        retrieval_query: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if tool == "compare":
            return self.compare.run(retrieval_query)

        if tool == "vision":
            return self._run_retrieval(retrieval_query, filters=filters)

        return self._run_retrieval(retrieval_query, filters=filters)

    def _run_retrieval(
        self,
        retrieval_query: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return self.retrieval.search(retrieval_query, filters=filters)
        except TypeError:
            return self.retrieval.search(retrieval_query)

    def _generate_with_context(
        self,
        results: list[dict[str, Any]],
        question: str,
    ) -> tuple[str, str]:
        context_blocks: list[str] = []

        for idx, item in enumerate(results, start=1):
            content = (item.get("text") or item.get("chunk") or "").strip()
            if not content:
                continue

            source_label = self._build_source_label(item=item, default_index=idx)
            retrieval_sources = ", ".join(item.get("retrieval_sources", [])) or "retrieval"

            structured_line = ""
            if item.get("structured_score") or item.get("record_type"):
                structured_line = (
                    f"\nStructured: yes"
                    f"\nRecord type: {item.get('record_type') or 'unknown'}"
                )

            block = (
                f"Source {idx}\n"
                f"{source_label}\n"
                f"Retrieval sources: {retrieval_sources}"
                f"{structured_line}\n\n"
                f"Content:\n{content}"
            )
            context_blocks.append(block)

        context_text = "\n\n".join(context_blocks).strip()

        try:
            answer = self.llm.generate(results, question)
        except Exception as exc:
            logger.exception("LLM generation failed: %s", exc)
            answer = (
                "I found relevant information, but I could not generate a final answer "
                "at the moment."
            )

        return answer, context_text

    def _choose_tool(self, question: str) -> str:
        q = question.lower()

        if any(x in q for x in ["compare", "difference", "differences", "changed between"]):
            return "compare"

        if any(
            x in q
            for x in ["diagram", "flow chart", "flowchart", "state machine", "picture", "image", "screenshot"]
        ):
            return "vision"

        return "retrieval"

    # def _build_retrieval_query(
    #     self,
    #     *,
    #     question: str,
    #     rewritten_query: str,
    #     history: list[dict[str, Any]],
    #     is_lookup: bool,
    # ) -> str:
    #     """
    #     Keep exact lookup queries clean and explicit.
    #     Use conversation history only when the question is conversational/ambiguous.
    #     """
    #     if is_lookup:
    #         return rewritten_query or question

    #     if not history:
    #         return rewritten_query or question

    #     recent_user_messages = [
    #         (msg.get("content") or "").strip()
    #         for msg in history[-4:]
    #         if msg.get("role") == "user" and (msg.get("content") or "").strip()
    #     ]

    #     if not recent_user_messages:
    #         return rewritten_query or question

    #     previous_user_context = " | ".join(recent_user_messages[-2:])
    #     base_query = rewritten_query or question
    #     return f"Previous user context: {previous_user_context}\nCurrent question: {base_query}"

    def _build_retrieval_query(
        self,
        *,
        question: str,
        rewritten_query: str,
        history: list[dict[str, Any]],
        is_lookup: bool,
    ) -> str:

        # 🔥 KEY FIX: Always keep original query FIRST
        if is_lookup:
            return f"{question} || {rewritten_query}"

        if not history:
            return f"{question} || {rewritten_query}"

        recent_user_messages = [
            (msg.get("content") or "").strip()
            for msg in history[-4:]
            if msg.get("role") == "user" and (msg.get("content") or "").strip()
        ]

        if not recent_user_messages:
            return f"{question} || {rewritten_query}"

        previous_user_context = " | ".join(recent_user_messages[-2:])

        return (
            f"Previous context: {previous_user_context}\n"
            f"Query: {question} || {rewritten_query}"
        )

    def _build_generation_question(
        self,
        *,
        question: str,
        history: list[dict[str, Any]],
        is_lookup: bool,
    ) -> str:
        if is_lookup:
            return question

        if not history:
            return question

        history_lines: list[str] = []
        for msg in history[-4:]:
            role = msg.get("role", "unknown")
            content = (msg.get("content") or "").strip()
            if content:
                history_lines.append(f"{role}: {content}")

        if not history_lines:
            return question

        return (
            "Previous conversation:\n"
            + "\n".join(history_lines)
            + f"\n\nCurrent user question: {question}"
        )

    def _build_sources(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        seen: set[str] = set()

        for item in results:
            source = {
                "logical_name": item.get("logical_name"),
                "filename": item.get("filename") or item.get("source_file"),
                "file_type": item.get("file_type"),
                "page": item.get("page"),
                "page_number": item.get("page_number"),
                "slide": item.get("slide"),
                "slide_number": item.get("slide_number"),
                "sheet": item.get("sheet"),
                "sheet_name": item.get("sheet_name"),
                "row": item.get("row"),
                "heading": item.get("heading"),
                "title": item.get("title"),
                "chunk_id": item.get("chunk_id"),
                "document_id": item.get("document_id"),
                "version_id": item.get("version_id"),
                "diagram_type": item.get("diagram_type"),
                "has_structured_extraction": item.get("has_structured_extraction"),
                "source_modality": item.get("source_modality"),
                "content_type": item.get("content_type"),
                "record_type": item.get("record_type"),
                "attribute_name": item.get("attribute_name"),
                "code": item.get("code"),
                "structured_score": item.get("structured_score"),
                "bm25_score": item.get("bm25_score"),
                "score": item.get("score"),
                "final_score": item.get("final_score"),
            }

            dedupe_key = (
                f"{source.get('filename')}|"
                f"{source.get('page') or source.get('page_number')}|"
                f"{source.get('slide') or source.get('slide_number')}|"
                f"{source.get('sheet') or source.get('sheet_name')}|"
                f"{source.get('row')}|"
                f"{source.get('chunk_id')}|"
                f"{source.get('code')}"
            )

            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            sources.append(source)

        return sources

    def _build_source_label(self, *, item: dict[str, Any], default_index: int) -> str:
        logical_name = item.get("logical_name") or "Unknown"
        filename = item.get("filename") or item.get("source_file") or "Unknown"

        location_parts: list[str] = []

        if item.get("page") is not None:
            location_parts.append(f"page {item['page']}")
        elif item.get("page_number") is not None:
            location_parts.append(f"page {item['page_number']}")

        if item.get("slide") is not None:
            location_parts.append(f"slide {item['slide']}")
        elif item.get("slide_number") is not None:
            location_parts.append(f"slide {item['slide_number']}")

        if item.get("sheet"):
            location_parts.append(f"sheet {item['sheet']}")
        elif item.get("sheet_name"):
            location_parts.append(f"sheet {item['sheet_name']}")

        if item.get("row") is not None:
            location_parts.append(f"row {item['row']}")

        if item.get("attribute_name"):
            location_parts.append(f"field {item['attribute_name']}")

        if item.get("code"):
            location_parts.append(f"code {item['code']}")

        chunk_id = item.get("chunk_id")
        if chunk_id is not None:
            location_parts.append(f"chunk {chunk_id}")
        else:
            location_parts.append(f"chunk {default_index}")

        location_text = ", ".join(location_parts)
        return f"{logical_name} / {filename} ({location_text})"

    def _build_debug_payload(
        self,
        results: list[dict[str, Any]],
        llm_context_preview: str,
    ) -> dict[str, Any]:
        return {
            "retrieved_chunks": [
                {
                    "filename": item.get("filename") or item.get("source_file"),
                    "logical_name": item.get("logical_name"),
                    "chunk_id": item.get("chunk_id"),
                    "record_type": item.get("record_type"),
                    "attribute_name": item.get("attribute_name"),
                    "code": item.get("code"),
                    "score": round(
                        float(item.get("final_score", item.get("score", 0.0)) or 0.0),
                        3,
                    ),
                    "vector_score": round(float(item.get("vector_score", 0.0) or 0.0), 3),
                    "bm25_score": round(float(item.get("bm25_score", 0.0) or 0.0), 3),
                    "structured_score": round(float(item.get("structured_score", 0.0) or 0.0), 3),
                    "numeric_boost": round(float(item.get("numeric_boost", 0.0) or 0.0), 3),
                    "mapping_boost": round(float(item.get("mapping_boost", 0.0) or 0.0), 3),
                    "column_boost": round(float(item.get("column_boost", 0.0) or 0.0), 3),
                    "preview": ((item.get("text") or item.get("chunk") or "").strip())[:240],
                }
                for item in results
            ],
            "top_k": len(results),
            "llm_context_preview": llm_context_preview[:1200] if llm_context_preview else "",
        }

    def _estimate_confidence(self, results: list[dict[str, Any]]) -> float:
        if not results:
            return 0.0

        scores: list[float] = []
        for item in results[:3]:
            try:
                score = float(item.get("final_score", item.get("score", 0.0)) or 0.0)
            except Exception:
                score = 0.0
            scores.append(score)

        if not scores:
            return 0.0

        confidence = sum(scores) / len(scores)
        return round(max(0.0, min(confidence, 1.0)), 3)

    def _build_no_evidence_answer(self, question: str) -> str:
        if self._looks_like_lookup(question):
            return (
                "I could not find a reliable exact match for that value or field "
                "in the indexed documents."
            )

        return (
            "I could not find enough relevant information in the indexed documents "
            "to answer that question reliably."
        )

    def _looks_like_lookup(self, question: str) -> bool:
        q = (question or "").strip().lower()
        if not q:
            return False

        if any(char.isdigit() for char in q):
            return True

        patterns = [
            r"\baction\b",
            r"\bstatus\b",
            r"\bmessagehandle\b",
            r"\bdatatype\b",
            r"\bdata type\b",
            r"\btype of\b",
            r"\bfield\b",
            r"\bcode\b",
            r"\bvalue\b",
        ]
        return any(re.search(pattern, q) for pattern in patterns)

    def _store_session_messages(self, session_id: str, user_question: str, assistant_answer: str) -> None:
        try:
            self.memory.add_message(session_id, "user", user_question)
            self.memory.add_message(session_id, "assistant", assistant_answer)
            self.memory.trim_session(session_id, keep_last=20)
        except Exception as exc:
            logger.warning("Failed to store session memory for %s: %s", session_id, exc)

    def _empty_answer(self, *, debug: bool) -> dict[str, Any]:
        return {
            "answer": "Please provide a non-empty question.",
            "tool_used": None,
            "sources": [],
            "confidence": 0.0,
            "debug": {
                "retrieved_chunks": [],
                "top_k": 0,
                "llm_context_preview": "",
            } if debug else None,
        }