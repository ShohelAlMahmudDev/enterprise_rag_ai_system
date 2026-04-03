
# from app.services.comparison_service import ComparisonService
# from app.services.llm_service import LocalLLM
# from app.services.memory_service import MemoryService
# from app.services.retrieval_service import RetrievalService

# try:
#     from app.services.vision_service import VisionService
# except Exception:
#     VisionService = None


# class AgentService:
#     def __init__(self) -> None:
#         self.retrieval = RetrievalService()
#         self.compare = ComparisonService()
#         self.memory = MemoryService()
#         self.llm = LocalLLM()

#         try:
#             self.vision = VisionService() if VisionService is not None else None
#         except Exception:
#             self.vision = None

#     def answer(self, question: str, session_id: str | None = None, debug: bool = False) -> dict:
#         tool = self._choose_tool(question)
#         history = self.memory.get_recent_messages(session_id) if session_id else []

#         effective_question = self._build_effective_question(question, history)

#         if tool == "compare":
#             results = self.compare.run(effective_question)
#         elif tool == "vision" and self.vision is not None:
#             results = self.vision.search_related(effective_question)
#         else:
#             results = self.retrieval.search(effective_question)

#         answer, llm_context_preview = self._generate_with_context(results, effective_question)

#         if session_id:
#             self.memory.add_message(session_id, "user", question)
#             self.memory.add_message(session_id, "assistant", answer)
#             self.memory.trim_session(session_id, keep_last=20)

#         response = {
#             "answer": answer,
#             "tool_used": tool,
#             "sources": self._build_sources(results),
#             "confidence": self._estimate_confidence(results),
#         }

#         if debug:
#             response["debug"] = {
#                 "retrieved_chunks": [
#                     {
#                         "filename": item.get("filename"),
#                         "logical_name": item.get("logical_name"),
#                         "chunk_id": item.get("chunk_id"),
#                         "score": round(float(item.get("final_score", item.get("score", 0.0)) or 0.0), 3),
#                         "preview": ((item.get("text") or item.get("chunk") or "").strip())[:240],
#                     }
#                     for item in results
#                 ],
#                 "top_k": len(results),
#                 "llm_context_preview": llm_context_preview[:1200] if llm_context_preview else "",
#             }

#         return response

#     def _generate_with_context(self, results: list[dict], question: str) -> tuple[str, str]:
#         context_blocks: list[str] = []

#         for idx, item in enumerate(results, start=1):
#             content = (item.get("text") or item.get("chunk") or "").strip()
#             if not content:
#                 continue

#             logical_name = item.get("logical_name", "Document")
#             filename = item.get("filename", "Unknown")
#             chunk_id = item.get("chunk_id", idx)

#             block = f"""Source {idx}
# Document: {logical_name}
# File: {filename}
# Chunk: {chunk_id}

# Content:
# {content}
# """
#             context_blocks.append(block)

#         context_text = "\n\n".join(context_blocks)
#         answer = self.llm.generate(results, question)
#         return answer, context_text

#     def _choose_tool(self, question: str) -> str:
#         q = question.lower()

#         if any(x in q for x in ["compare", "difference", "changed between"]):
#             return "compare"

#         if any(x in q for x in ["diagram", "flow chart", "state machine", "picture", "image", "screenshot"]):
#             return "vision"

#         return "retrieval"

#     def _build_effective_question(self, question: str, history: list[dict]) -> str:
#         if not history:
#             return question

#         history_lines: list[str] = []
#         for msg in history[-4:]:
#             role = msg.get("role", "unknown")
#             content = (msg.get("content") or "").strip()
#             if content:
#                 history_lines.append(f"{role}: {content}")

#         if not history_lines:
#             return question

#         return (
#             "Previous conversation:\n"
#             + "\n".join(history_lines)
#             + f"\n\nCurrent user question: {question}"
#         )

#     def _build_sources(self, results: list[dict]) -> list[str]:
#         sources: list[str] = []
#         for item in results:
#             source = (
#                 f"{item.get('logical_name', 'Unknown')} / "
#                 f"{item.get('filename', 'Unknown')} "
#                 f"(chunk {item.get('chunk_id', '-')})"
#             )
#             if source not in sources:
#                 sources.append(source)
#         return sources

#     def _estimate_confidence(self, results: list[dict]) -> float:
#         if not results:
#             return 0.0

#         scores: list[float] = []
#         for item in results[:3]:
#             score = float(item.get("final_score", item.get("score", 0.0)) or 0.0)
#             scores.append(score)

#         if not scores:
#             return 0.0

#         confidence = sum(scores) / len(scores)
#         return round(max(0.0, min(confidence, 1.0)), 3)

import logging

from app.services.comparison_service import ComparisonService
from app.services.llm_service import LocalLLM
from app.services.memory_service import MemoryService
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)

try:
    from app.services.vision_service import VisionService
except Exception as exc:
    logger.warning("VisionService import failed: %s", exc)
    VisionService = None


class AgentService:
    def __init__(self) -> None:
        self.retrieval = RetrievalService()
        self.compare = ComparisonService()
        self.memory = MemoryService()
        self.llm = LocalLLM()

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
    ) -> dict:
        tool = self._choose_tool(question)

        try:
            history = self.memory.get_recent_messages(session_id) if session_id else []

            retrieval_query = self._build_retrieval_query(question, history)
            generation_question = self._build_generation_question(question, history)

            if tool == "compare":
                results = self.compare.run(retrieval_query)
            elif tool == "vision" and self.vision is not None:
                results = self.vision.search_related(retrieval_query)
            else:
                results = self.retrieval.search(retrieval_query)

            answer, llm_context_preview = self._generate_with_context(results, generation_question)

            if session_id:
                self.memory.add_message(session_id, "user", question)
                self.memory.add_message(session_id, "assistant", answer)
                self.memory.trim_session(session_id, keep_last=20)

            response = {
                "answer": answer,
                "tool_used": tool,
                "sources": self._build_sources(results),
                "confidence": self._estimate_confidence(results),
            }

            if debug:
                response["debug"] = self._build_debug_payload(results, llm_context_preview)

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

    def _generate_with_context(self, results: list[dict], question: str) -> tuple[str, str]:
        context_blocks: list[str] = []

        for idx, item in enumerate(results, start=1):
            content = (item.get("text") or item.get("chunk") or "").strip()
            if not content:
                continue

            logical_name = item.get("logical_name", "Document")
            filename = item.get("filename", "Unknown")
            chunk_id = item.get("chunk_id", idx)

            block = (
                f"Source {idx}\n"
                f"Document: {logical_name}\n"
                f"File: {filename}\n"
                f"Chunk: {chunk_id}\n\n"
                f"Content:\n{content}"
            )
            context_blocks.append(block)

        context_text = "\n\n".join(context_blocks)
        answer = self.llm.generate(results, question)
        return answer, context_text

    def _choose_tool(self, question: str) -> str:
        q = question.lower()

        if any(x in q for x in ["compare", "difference", "differences", "changed between"]):
            return "compare"

        if any(
            x in q
            for x in ["diagram", "flow chart", "state machine", "picture", "image", "screenshot"]
        ):
            return "vision"

        return "retrieval"

    def _build_retrieval_query(self, question: str, history: list[dict]) -> str:
        """
        Keep retrieval query focused. Use only recent user messages if helpful.
        """
        if not history:
            return question

        recent_user_messages = [
            (msg.get("content") or "").strip()
            for msg in history[-4:]
            if msg.get("role") == "user" and (msg.get("content") or "").strip()
        ]

        if not recent_user_messages:
            return question

        # Use just a light conversational hint instead of the full history transcript.
        previous_user_context = " | ".join(recent_user_messages[-2:])
        return f"Previous user context: {previous_user_context}\nCurrent question: {question}"

    def _build_generation_question(self, question: str, history: list[dict]) -> str:
        """
        Generation can benefit from slightly richer conversation context.
        """
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

    def _build_sources(self, results: list[dict]) -> list[str]:
        sources: list[str] = []

        for item in results:
            source = (
                f"{item.get('logical_name', 'Unknown')} / "
                f"{item.get('filename', 'Unknown')} "
                f"(chunk {item.get('chunk_id', '-')})"
            )
            if source not in sources:
                sources.append(source)

        return sources

    def _build_debug_payload(self, results: list[dict], llm_context_preview: str) -> dict:
        return {
            "retrieved_chunks": [
                {
                    "filename": item.get("filename"),
                    "logical_name": item.get("logical_name"),
                    "chunk_id": item.get("chunk_id"),
                    "score": round(
                        float(item.get("final_score", item.get("score", 0.0)) or 0.0),
                        3,
                    ),
                    "preview": ((item.get("text") or item.get("chunk") or "").strip())[:240],
                }
                for item in results
            ],
            "top_k": len(results),
            "llm_context_preview": llm_context_preview[:1200] if llm_context_preview else "",
        }

    def _estimate_confidence(self, results: list[dict]) -> float:
        if not results:
            return 0.0

        scores: list[float] = []
        for item in results[:3]:
            score = float(item.get("final_score", item.get("score", 0.0)) or 0.0)
            scores.append(score)

        if not scores:
            return 0.0

        confidence = sum(scores) / len(scores)
        return round(max(0.0, min(confidence, 1.0)), 3)