import logging
import re
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
        question_guidance = self._build_question_guidance(question)

        system_prompt = textwrap.dedent(
            """\
            You are an enterprise AI assistant helping users understand internal documents.

            Rules:
            - Answer using only the provided context.
            - Start with a direct answer.
            - Keep the answer concise, clear, and professional.
            - Keep wording concrete and precise.
            - For technical tables, codes, values, fields, datatypes, rows, and mappings:
              - prefer exact matches over general similarity
              - use the exact number, key, field name, or mapped value from the context
              - do not guess nearby values
              - do not merge multiple mappings unless the context clearly does so
            - If a structured entry directly answers the question, prefer it over general prose.
            - If multiple candidate values appear, choose only the one best supported by the context.
            - If the context is incomplete or conflicting, say so clearly and briefly.
            - Do not invent facts that are not supported by the context.
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

            Special guidance:
            {question_guidance}

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
                        "temperature": 0.1,
                        "num_predict": 450,
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
        Build compact structured context blocks for the LLM.
        Keep whole blocks intact instead of cutting raw text mid-block.
        """
        context_blocks: list[str] = []
        max_total_chars = 7000
        current_total = 0

        for idx, item in enumerate(context_items, start=1):
            content = (item.get("text") or item.get("chunk") or "").strip()
            if not content:
                continue

            logical_name = item.get("logical_name") or "Document"
            filename = item.get("filename") or item.get("source_file") or "Unknown"
            location = self._build_location_hint(item=item, default_index=idx)
            section_type = item.get("type") or item.get("record_type") or "unknown"
            heading = item.get("heading") or item.get("title") or ""
            is_structured = bool(item.get("is_structured")) or bool(item.get("structured_score"))
            attribute_name = item.get("attribute_name")
            code = item.get("code")
            value = item.get("value")
            columns = item.get("columns") or {}

            metadata_lines = [
                f"Document: {logical_name}",
                f"File: {filename}",
                f"Location: {location}",
                f"Section type: {section_type}",
            ]

            if heading:
                metadata_lines.append(f"Heading: {heading}")
            if is_structured:
                metadata_lines.append("Structured content: yes")
            if attribute_name:
                metadata_lines.append(f"Field: {attribute_name}")
            if code:
                metadata_lines.append(f"Code: {code}")
            if value:
                metadata_lines.append(f"Value: {value}")

            if columns:
                metadata_lines.append("Columns:")
                for key, val in list(columns.items())[:8]:
                    metadata_lines.append(f"- {key}: {val}")

            block = textwrap.dedent(
                f"""\
                Item {idx}
                {"\n".join(metadata_lines)}

                Content:
                {content}
                """
            ).strip()

            projected_total = current_total + len(block) + 2
            if projected_total > max_total_chars:
                break

            context_blocks.append(block)
            current_total = projected_total

        return "\n\n".join(context_blocks).strip()

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
            code = str(item.get("code") or "")
            key = f"{filename}|{chunk_id}|{code}|{content[:220]}"

            if key in seen:
                continue

            seen.add(key)
            unique_items.append(item)

            if len(unique_items) >= 6:
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

    def _build_question_guidance(self, question: str) -> str:
        q = question.lower()

        if self._is_exact_lookup_question(q):
            return (
                "This looks like an exact lookup question. "
                "Match exact numbers, field names, datatypes, row values, and key-value mappings carefully. "
                "If the question asks for a specific code or value, answer with that exact mapped meaning only."
            )

        if any(word in q for word in ["type", "datatype", "data type"]):
            return (
                "Focus on the datatype or declared field type. "
                "Do not describe general behavior unless the context explicitly includes it."
            )

        if any(word in q for word in ["action", "status", "code", "value", "field"]):
            return (
                "Focus on the exact field or mapping requested. "
                "Prefer the most explicit row, entry, or mapping from the context."
            )

        return (
            "Answer from the most directly relevant retrieved entries. "
            "Prefer explicit statements over general summaries."
        )

    def _is_exact_lookup_question(self, question: str) -> bool:
        if any(char.isdigit() for char in question):
            return True

        patterns = [
            r"\baction\b",
            r"\bstatus\b",
            r"\bmessagehandle\b",
            r"\bdatatype\b",
            r"\bdata type\b",
            r"\btype of\b",
            r"\bvalue\b",
            r"\bcode\b",
            r"\bfield\b",
        ]

        return any(re.search(pattern, question) for pattern in patterns)

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
        is_lookup_question = self._is_exact_lookup_question(q)

        if is_lookup_question:
            return textwrap.dedent(
                """\
                Preferred format:
                - One short direct answer first
                - Then one short clarification sentence only if needed
                - If a datatype, code, or mapped value exists, state it exactly
                """
            ).strip()

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

        leading_patterns = [
            r"^\s*According to the context,?\s*",
            r"^\s*According to the provided context,?\s*",
            r"^\s*Based on the context,?\s*",
            r"^\s*Based on the provided context,?\s*",
        ]

        for pattern in leading_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(r"\bSource\s+[1-9]\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        return cleaned.strip()

    def _fallback_answer(self, context_items: list[dict[str, Any]], question: str) -> str:
        """
        Build a deterministic answer when the LLM call fails.
        """
        if self._is_exact_lookup_question(question.lower()):
            best = context_items[0] if context_items else None
            if best:
                value = (best.get("value") or "").strip()
                attribute_name = (best.get("attribute_name") or "").strip()
                code = str(best.get("code") or "").strip()
                if value and (attribute_name or code):
                    parts: list[str] = []
                    if attribute_name:
                        parts.append(attribute_name)
                    if code:
                        parts.append(code)
                    label = " ".join(parts).strip()
                    if label:
                        return f"{label}: {value}"
                    return value

                content = (best.get("text") or best.get("chunk") or "").strip()
                if content:
                    return content[:500].strip()

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