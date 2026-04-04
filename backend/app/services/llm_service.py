import logging
import textwrap
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)


class LocalLLM:
    """
    Local Ollama-backed LLM service for grounded answer generation.

    Responsibilities:
    - build compact grounded context from retrieved items
    - send a controlled prompt to the local chat model
    - post-process model output
    - provide deterministic fallback answers when generation fails
    """

    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_CHAT_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT_SECONDS

    def generate(self, context_items: list[dict[str, Any]], question: str) -> str:
        """
        Generate an answer grounded in retrieved context items.
        """
        if not context_items:
            return (
                "I could not find enough relevant information in the indexed documents "
                "to answer that confidently. Please try rephrasing your question or "
                "make sure the relevant document has been uploaded and indexed."
            )

        filtered_items = self._deduplicate_context_items(context_items)
        context_text = self._build_context_text(filtered_items)

        if not context_text:
            return (
                "I found related document entries, but their extracted text content was empty. "
                "Please check whether document parsing and indexing completed correctly."
            )

        format_hint = self._build_format_hint(question)

        system_prompt = textwrap.dedent(
            """\
            You are an enterprise AI assistant helping users understand internal documents.

            Rules:
            - Answer using only the provided context.
            - Start with a direct answer.
            - Keep the answer concise, clear, and professional.
            - Use short paragraphs.
            - Use numbered steps for procedures.
            - Use bullets only when they genuinely improve clarity.
            - Do not invent facts that are not supported by the context.
            - If the context is incomplete or insufficient, say so briefly and clearly.
            - Do not mention internal retrieval details such as:
              - "Source 1"
              - "according to the context"
              - "the documents provide"
              - "this is implied"
            - Do not reveal internal reasoning.
            - Do not quote long raw passages unless necessary.
            - Return only the final answer for the user.
            """
        ).strip()

        user_prompt = textwrap.dedent(
            f"""\
            Use the following context to answer the user's question.

            Context:
            {context_text}

            Question:
            {question}

            Formatting instructions:
            - Give a short direct answer first.
            - Keep the wording natural, practical, and professional.
            - Remove weak, repeated, or overly technical phrasing.
            - Do not include source labels or internal reasoning notes.
            - Do not use phrases like:
              - "According to the context"
              - "The documents provide"
              - "This is implied"
            - If the answer is uncertain because the context is incomplete, say that clearly.
            - Return only the final answer.

            {format_hint}
            """
        ).strip()

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "num_predict": 500,
                    },
                },
                timeout=self.timeout,
            )
            response.raise_for_status()

            data = response.json()
            content = (data.get("message") or {}).get("content", "")
            if isinstance(content, str) and content.strip():
                return self._post_process_answer(content)

            logger.warning("Ollama returned an empty response. Using fallback answer.")
            return self._fallback_answer(filtered_items, question)

        except requests.RequestException as exc:
            logger.exception("Ollama request failed: %s", exc)
            return self._fallback_answer(filtered_items, question)
        except Exception as exc:
            logger.exception("Unexpected LLM generation failure: %s", exc)
            return self._fallback_answer(filtered_items, question)

    def _build_context_text(self, context_items: list[dict[str, Any]]) -> str:
        """
        Build compact, citation-friendly context blocks for the LLM.
        """
        context_blocks: list[str] = []

        for idx, item in enumerate(context_items, start=1):
            content = (item.get("text") or item.get("chunk") or "").strip()
            if not content:
                continue

            logical_name = item.get("logical_name") or "Document"
            filename = item.get("filename") or item.get("source_file") or "Unknown"
            location = self._build_location_hint(item=item, default_index=idx)

            block = textwrap.dedent(
                f"""\
                Source {idx}
                Document: {logical_name}
                File: {filename}
                Location: {location}

                Content:
                {content}
                """
            ).strip()

            context_blocks.append(block)

        if not context_blocks:
            return ""

        context_text = "\n\n".join(context_blocks)

        # Keep context bounded for local model reliability.
        return context_text[:7000].strip()

    def _deduplicate_context_items(self, context_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Keep the best few non-duplicate items for prompt context.
        """
        unique_items: list[dict[str, Any]] = []
        seen: set[str] = set()

        sorted_items = sorted(
            context_items,
            key=lambda item: float(item.get("final_score", item.get("score", 0.0)) or 0.0),
            reverse=True,
        )

        for item in sorted_items:
            content = (item.get("text") or item.get("chunk") or "").strip()
            if not content:
                continue

            filename = str(item.get("filename") or item.get("source_file") or "")
            chunk_id = str(item.get("chunk_id") or "")
            key = f"{filename}|{chunk_id}|{content[:220]}"

            if key in seen:
                continue

            seen.add(key)
            unique_items.append(item)

            if len(unique_items) >= 5:
                break

        return unique_items

    def _build_location_hint(self, *, item: dict[str, Any], default_index: int) -> str:
        parts: list[str] = []

        page = item.get("page", item.get("page_number"))
        slide = item.get("slide", item.get("slide_number"))
        sheet = item.get("sheet", item.get("sheet_name"))
        row = item.get("row")
        chunk_id = item.get("chunk_id")

        if page is not None:
            parts.append(f"page {page}")
        if slide is not None:
            parts.append(f"slide {slide}")
        if sheet:
            parts.append(f"sheet {sheet}")
        if row is not None:
            parts.append(f"row {row}")
        if chunk_id is not None:
            parts.append(f"chunk {chunk_id}")

        if not parts:
            parts.append(f"chunk {default_index}")

        return ", ".join(parts)

    def _build_format_hint(self, question: str) -> str:
        q = question.lower()

        is_step_question = any(
            word in q
            for word in ["how", "steps", "process", "procedure", "configure", "install", "create"]
        )
        is_list_question = any(
            word in q
            for word in ["list", "key points", "main points", "benefits", "features"]
        )
        is_compare_question = any(
            word in q
            for word in ["compare", "difference", "differences", "changed between"]
        )
        is_diagram_question = any(
            word in q
            for word in ["diagram", "flowchart", "flow chart", "state machine", "sequence", "architecture", "network"]
        )

        if is_step_question:
            return textwrap.dedent(
                """\
                Preferred format:
                1. One short introductory sentence
                2. A numbered list of practical steps
                3. A brief closing note only if needed
                """
            ).strip()

        if is_list_question:
            return textwrap.dedent(
                """\
                Preferred format:
                - One short introductory sentence
                - A short list of the main points
                - A brief closing note only if needed
                """
            ).strip()

        if is_compare_question:
            return textwrap.dedent(
                """\
                Preferred format:
                - One short introductory sentence
                - A clear comparison using short bullets or short sections
                - Highlight the most important differences first
                """
            ).strip()

        if is_diagram_question:
            return textwrap.dedent(
                """\
                Preferred format:
                - One short direct answer first
                - Then briefly explain the main visible structure, flow, states, steps, components, or relationships as relevant
                - Keep wording concrete and engineering-friendly
                """
            ).strip()

        return textwrap.dedent(
            """\
            Preferred format:
            - One short introductory paragraph
            - One or two short follow-up paragraphs if needed
            """
        ).strip()

    def _post_process_answer(self, text: str) -> str:
        """
        Clean common unwanted phrases without distorting the answer.
        """
        cleaned = text.strip()

        replacements = [
            ("According to the context,", ""),
            ("According to the provided context,", ""),
            ("Based on the context,", ""),
            ("The documents provide", "Here’s what I found"),
            ("This is implied", ""),
            ("Source 1", ""),
            ("Source 2", ""),
            ("Source 3", ""),
            ("Source 4", ""),
            ("Source 5", ""),
        ]

        for old, new in replacements:
            cleaned = cleaned.replace(old, new)

        while "\n\n\n" in cleaned:
            cleaned = cleaned.replace("\n\n\n", "\n\n")

        return cleaned.strip()

    def _fallback_answer(self, context_items: list[dict[str, Any]], question: str) -> str:
        """
        Build a deterministic answer when the LLM call fails.
        """
        snippets: list[str] = []

        for item in context_items[:2]:
            content = (item.get("text") or item.get("chunk") or "").strip()
            if not content:
                continue

            location = self._build_location_hint(item=item, default_index=1)
            logical_name = item.get("logical_name") or "Document"
            filename = item.get("filename") or item.get("source_file") or "Unknown"

            snippet = (
                f"{logical_name} / {filename} ({location})\n"
                f"{content[:320].strip()}"
            )
            snippets.append(snippet)

        if not snippets:
            return (
                "I found related document entries, but I could not build a clear answer "
                "from them. Please try asking a more specific question."
            )

        q = question.lower()
        intro = "Here is the most relevant information I found:"

        if any(word in q for word in ["how", "steps", "process", "procedure"]):
            intro = "Here’s the most relevant information I found for the process:"

        return f"{intro}\n\n" + "\n\n".join(snippets)