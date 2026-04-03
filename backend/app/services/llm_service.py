
# import logging

# import requests

# from app.config import settings

# logger = logging.getLogger(__name__)


# class LocalLLM:
#     def __init__(self) -> None:
#         self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
#         self.model = settings.OLLAMA_CHAT_MODEL
#         self.timeout = settings.OLLAMA_TIMEOUT_SECONDS

#     def generate(self, context_items: list[dict], question: str) -> str:
#         if not context_items:
#             return (
#                 "I could not find enough relevant information in the uploaded documents "
#                 "to answer confidently. Please try rephrasing your question or make sure "
#                 "the relevant document has been uploaded and indexed."
#             )

#         context_blocks: list[str] = []

#         for idx, item in enumerate(context_items, start=1):
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

#         if not context_blocks:
#             return (
#                 "I found related document entries, but their text content was empty. "
#                 "Please check whether document extraction and indexing worked correctly."
#             )

#         context_text = "\n\n".join(context_blocks)
#         context_text = context_text[:7000]

#         system_prompt = """
#         You are an enterprise AI assistant helping users understand internal documents.

#         Rules:
#         - Write in a professional, readable, user-friendly style.
#         - Start with a direct answer.
#         - Keep the answer concise but complete.
#         - Use short paragraphs.
#         - When the user asks for steps, use a numbered list.
#         - When the user asks for key points, use bullet points.
#         - Avoid repeating the same idea.
#         - Do not mention internal retrieval details such as:
#         - "Source 1"
#         - "according to the context"
#         - "the documents provide"
#         - "this is implied"
#         - Do not copy raw document text unless necessary.
#         - Use only the provided context.
#         - If the context is incomplete, say so briefly and politely.
#         """

#         user_prompt = f"""
#         Use the following context to answer the user's question.

#         Context:
#         {context_text}

#         Question:
#         {question}

#         Formatting instructions:
#         - Give a short direct answer first.
#         - If the answer contains steps, format them as a numbered list.
#         - If the answer contains several points, format them as bullet points.
#         - Keep the wording natural and professional.
#         - Remove weak, repeated, or overly technical phrasing.
#         - Do not include source labels or internal reasoning notes.
#         - Return only the final answer.
#         """

#         try:
#             response = requests.post(
#                 f"{self.base_url}/api/chat",
#                 json={
#                     "model": self.model,
#                     "messages": [
#                         {"role": "system", "content": system_prompt.strip()},
#                         {"role": "user", "content": user_prompt.strip()},
#                     ],
#                     "stream": False,
#                     "options": {
#                         "temperature": 0.2,
#                     },
#                 },
#                 timeout=self.timeout,
#             )
#             response.raise_for_status()

#             data = response.json()
#             content = data.get("message", {}).get("content", "").strip()

#             if content:
#                 return content

#             logger.warning("Ollama returned an empty response. Using fallback answer.")
#             return self._fallback_answer(context_items)

#         except Exception as exc:
#             logger.exception("Ollama generation failed: %s", exc)
#             return self._fallback_answer(context_items)

#     def _fallback_answer(self, context_items: list[dict]) -> str:
#         snippets: list[str] = []
#         for item in context_items[:2]:
#             content = (item.get("text") or item.get("chunk") or "").strip()
#             if content:
#                 snippets.append(content[:350].strip())

#         if not snippets:
#             return (
#                 "I found related document entries, but I could not build a clear answer "
#                 "from them. Please try asking a more specific question."
#             )

#         joined = " ".join(snippets)
#         return (
#             "Based on the uploaded documents, here is the most relevant information I found: "
#             f"{joined}"
#         )

import logging
import textwrap

import requests

from app.config import settings

logger = logging.getLogger(__name__)


class LocalLLM:
    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_CHAT_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT_SECONDS

    def generate(self, context_items: list[dict], question: str) -> str:
        if not context_items:
            return (
                "I could not find enough relevant information in the uploaded documents "
                "to answer confidently. Please try rephrasing your question or make sure "
                "the relevant document has been uploaded and indexed."
            )

        filtered_items = self._deduplicate_context_items(context_items)

        context_blocks: list[str] = []

        for idx, item in enumerate(filtered_items, start=1):
            content = (item.get("text") or item.get("chunk") or "").strip()
            if not content:
                continue

            logical_name = item.get("logical_name", "Document")
            filename = item.get("filename", "Unknown")
            chunk_id = item.get("chunk_id", idx)

            block = textwrap.dedent(
                f"""\
                Source {idx}
                Document: {logical_name}
                File: {filename}
                Chunk: {chunk_id}

                Content:
                {content}
                """
            ).strip()

            context_blocks.append(block)

        if not context_blocks:
            return (
                "I found related document entries, but their text content was empty. "
                "Please check whether document extraction and indexing worked correctly."
            )

        context_text = "\n\n".join(context_blocks)
        context_text = context_text[:5000]

        format_hint = self._build_format_hint(question)

        system_prompt = textwrap.dedent(
            """\
            You are an enterprise AI assistant helping users understand internal documents.

            Rules:
            - Write in a professional, readable, user-friendly style.
            - Start with a direct answer.
            - Keep the answer concise but complete.
            - Use short paragraphs.
            - Use numbered steps for procedures.
            - Use bullet points for lists of key items.
            - Avoid repeating the same idea.
            - Do not mention internal retrieval details such as:
              - "Source 1"
              - "according to the context"
              - "the documents provide"
              - "this is implied"
            - Do not copy raw document text unless necessary.
            - Use only the provided context.
            - If the context is incomplete, say so briefly and politely.
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
                        "num_predict": 400,
                    },
                },
                timeout=self.timeout,
            )
            response.raise_for_status()

            data = response.json()
            content = data.get("message", {}).get("content", "").strip()

            if content:
                return self._post_process_answer(content)

            logger.warning("Ollama returned an empty response. Using fallback answer.")
            return self._fallback_answer(filtered_items, question)

        except requests.RequestException as exc:
            logger.exception("Ollama request failed: %s", exc)
            return self._fallback_answer(filtered_items, question)
        except Exception as exc:
            logger.exception("Unexpected LLM generation failure: %s", exc)
            return self._fallback_answer(filtered_items, question)

    def _deduplicate_context_items(self, context_items: list[dict]) -> list[dict]:
        unique_items: list[dict] = []
        seen: set[str] = set()

        for item in context_items:
            content = (item.get("text") or item.get("chunk") or "").strip()
            if not content:
                continue

            key = content[:220]
            if key in seen:
                continue

            seen.add(key)
            unique_items.append(item)

            if len(unique_items) >= 5:
                break

        return unique_items

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
                - A bullet list of the main points
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

        return textwrap.dedent(
            """\
            Preferred format:
            - One short introductory paragraph
            - One or two short follow-up paragraphs if needed
            """
        ).strip()

    def _post_process_answer(self, text: str) -> str:
        cleaned = text.strip()

        replacements = [
            ("According to the context,", ""),
            ("According to the provided context,", ""),
            ("The documents provide", "Here’s how it works"),
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

    def _fallback_answer(self, context_items: list[dict], question: str) -> str:
        snippets: list[str] = []
        for item in context_items[:2]:
            content = (item.get("text") or item.get("chunk") or "").strip()
            if content:
                snippets.append(content[:300].strip())

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