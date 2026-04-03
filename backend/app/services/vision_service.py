
# import base64
# import logging
# from pathlib import Path
# from typing import Iterable

# import requests

# from app.config import settings

# logger = logging.getLogger(__name__)


# class VisionService:
#     """
#     Uses a local Ollama vision-capable model to describe diagrams, flow charts,
#     screenshots, and other images. The description can then be chunked and indexed
#     like normal text for RAG.
#     """

#     def __init__(self) -> None:
#         self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
#         self.model = settings.OLLAMA_VISION_MODEL
#         self.timeout = settings.OLLAMA_TIMEOUT_SECONDS
#         self.keep_alive = getattr(settings, "OLLAMA_KEEP_ALIVE", "30m")

#     def describe_image(self, image_path: str | Path, filename_hint: str | None = None) -> str:
#         path = Path(image_path)
#         if not path.exists() or not path.is_file():
#             raise FileNotFoundError(f"Image not found: {path}")

#         image_b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
#         prompt = self._build_prompt(filename_hint or path.name)

#         logger.info("Analyzing image with vision model: %s", path.name)
#         response = requests.post(
#             f"{self.base_url}/api/chat",
#             json={
#                 "model": self.model,
#                 "messages": [
#                     {
#                         "role": "system",
#                         "content": (
#                             "You are an enterprise document analysis assistant. "
#                             "Extract structured meaning from diagrams, screenshots, state machines, and flow charts. "
#                             "Be faithful to the image. Do not invent unreadable labels."
#                         ),
#                     },
#                     {
#                         "role": "user",
#                         "content": prompt,
#                         "images": [image_b64],
#                     },
#                 ],
#                 "stream": False,
#                 "keep_alive": self.keep_alive,
#                 "options": {
#                     "temperature": 0.1,
#                 },
#             },
#             timeout=self.timeout,
#         )
#         response.raise_for_status()
#         data = response.json()
#         content = (data.get("message") or {}).get("content", "").strip()
#         if not content:
#             raise RuntimeError("Vision model returned an empty response.")
#         return content

#     def describe_many(self, image_paths: Iterable[str | Path]) -> list[dict[str, str]]:
#         results: list[dict[str, str]] = []
#         for image_path in image_paths:
#             try:
#                 description = self.describe_image(image_path)
#                 results.append({
#                     "path": str(image_path),
#                     "description": description,
#                 })
#             except Exception as exc:
#                 logger.exception("Vision processing failed for %s: %s", image_path, exc)
#                 results.append({
#                     "path": str(image_path),
#                     "description": "",
#                     "error": str(exc),
#                 })
#         return results

#     def _build_prompt(self, name: str) -> str:
#         return f"""
# Analyze the uploaded image named '{name}'.

# Return a structured plain-text description using these sections exactly:
# 1. Image Type
# 2. Visible Text
# 3. Main Components
# 4. Relationships / Arrows / Transitions
# 5. State Logic or Process Flow
# 6. Important Labels / IDs / Values
# 7. Engineering Summary

# Rules:
# - If the image is a state machine diagram, list states and transitions clearly.
# - If the image is a flow chart, describe the process in order, including decisions.
# - If the image is a screenshot or UI image, describe visible controls, panels, and important messages.
# - If text is unreadable, say 'Unreadable' instead of guessing.
# - Be concise but informative.
# - Output plain text only.
# """.strip()

import base64
import logging
import textwrap
from pathlib import Path
from typing import Iterable

import requests

from app.config import settings

logger = logging.getLogger(__name__)


class VisionService:
    """
    Uses a local Ollama vision-capable model to describe diagrams, flow charts,
    screenshots, scanned documents, and other images. The description can then
    be chunked and indexed like normal text for RAG.
    """

    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_VISION_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT_SECONDS
        self.keep_alive = getattr(settings, "OLLAMA_KEEP_ALIVE", "30m")

    def describe_image(
        self,
        image_path: str | Path,
        filename_hint: str | None = None,
        image_type: str = "unknown",
    ) -> str:
        path = Path(image_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Image not found: {path}")

        image_b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        prompt = self._build_prompt(
            name=filename_hint or path.name,
            image_type=image_type,
        )

        logger.info(
            "Analyzing image with vision model: %s | image_type=%s",
            path.name,
            image_type,
        )

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": self._system_prompt(),
                        },
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [image_b64],
                        },
                    ],
                    "stream": False,
                    "keep_alive": self.keep_alive,
                    "options": {
                        "temperature": 0.1,
                    },
                },
                timeout=self.timeout,
            )
            response.raise_for_status()

            data = response.json()
            content = (data.get("message") or {}).get("content", "").strip()

            if not content:
                raise RuntimeError("Vision model returned an empty response.")

            return self._post_process_response(content)

        except requests.RequestException as exc:
            logger.exception("Vision request failed for %s: %s", path.name, exc)
            raise RuntimeError(f"Vision request failed for {path.name}") from exc

    def describe_many(
        self,
        image_paths: Iterable[str | Path],
        image_type: str = "unknown",
    ) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []

        for image_path in image_paths:
            try:
                description = self.describe_image(
                    image_path,
                    image_type=image_type,
                )
                results.append(
                    {
                        "path": str(image_path),
                        "description": description,
                    }
                )
            except Exception as exc:
                logger.exception("Vision processing failed for %s: %s", image_path, exc)
                results.append(
                    {
                        "path": str(image_path),
                        "description": "",
                        "error": str(exc),
                    }
                )

        return results

    def _system_prompt(self) -> str:
        return textwrap.dedent(
            """\
            You are an enterprise document and diagram analysis assistant.

            Your job is to extract structured meaning from images such as:
            - state machine diagrams
            - flow charts
            - architecture diagrams
            - screenshots
            - scanned documents

            Rules:
            - Be faithful to the image.
            - Do not invent unreadable labels.
            - If text is unclear, write "Unreadable".
            - Prefer structured, engineering-friendly output.
            - Focus on what is visible.
            - Output plain text only.
            """
        ).strip()

    def _build_prompt(self, name: str, image_type: str) -> str:
        type_hint = self._build_type_hint(image_type)

        return textwrap.dedent(
            f"""\
            Analyze the uploaded image named "{name}".

            Detected image type: {image_type}

            Return a structured plain-text description using these sections exactly:
            1. Image Type
            2. Visible Text
            3. Main Components
            4. Relationships / Arrows / Transitions
            5. State Logic or Process Flow
            6. Important Labels / IDs / Values
            7. Engineering Summary

            {type_hint}

            General rules:
            - If text is unreadable, say "Unreadable" instead of guessing.
            - Be concise but informative.
            - Output plain text only.
            """
        ).strip()

    def _build_type_hint(self, image_type: str) -> str:
        image_type = (image_type or "unknown").lower()

        if image_type == "diagram":
            return textwrap.dedent(
                """\
                Diagram-specific rules:
                - Identify boxes, nodes, states, components, and connectors.
                - If it is a state machine, list states and transitions clearly.
                - If it is a flow chart, describe the process in order, including decisions.
                - Pay close attention to arrows, branching, and labels.
                """
            ).strip()

        if image_type == "screenshot":
            return textwrap.dedent(
                """\
                Screenshot-specific rules:
                - Describe visible panels, controls, forms, tables, buttons, and messages.
                - Extract important visible text.
                - Mention warnings, errors, statuses, or values if present.
                """
            ).strip()

        if image_type == "document":
            return textwrap.dedent(
                """\
                Document-specific rules:
                - Focus on extracting visible text and document structure.
                - Preserve headings, labels, and important values.
                - If it looks like a scanned page, summarize the main written content.
                """
            ).strip()

        if image_type == "photo":
            return textwrap.dedent(
                """\
                Photo-specific rules:
                - Describe the main visible objects and any readable labels or text.
                - Focus on content that could be useful for enterprise or engineering understanding.
                """
            ).strip()

        return textwrap.dedent(
            """\
            Generic rules:
            - Describe the visible content faithfully.
            - Focus on any readable text, structure, and relationships.
            """
        ).strip()

    def _post_process_response(self, text: str) -> str:
        cleaned = text.strip()

        while "\n\n\n" in cleaned:
            cleaned = cleaned.replace("\n\n\n", "\n\n")

        return cleaned