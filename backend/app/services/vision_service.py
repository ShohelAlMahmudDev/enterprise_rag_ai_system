import base64
import logging
import textwrap
from pathlib import Path
from typing import Any, Iterable

import requests

from app.config import settings

logger = logging.getLogger(__name__)


class VisionService:
    """
    Uses a local Ollama vision-capable model to analyze diagrams, flow charts,
    screenshots, scanned documents, and other images.

    Supported modes:
    - default descriptive extraction for multimodal RAG ingestion
    - custom prompt-driven extraction for structured workflows such as
      diagram classification and diagram JSON extraction
    """

    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_VISION_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT_SECONDS
        self.keep_alive = getattr(settings, "OLLAMA_KEEP_ALIVE", "30m")

    def describe_image(
        self,
        image_path: str | Path,
        *,
        prompt: str | None = None,
        filename_hint: str | None = None,
        image_type: str = "unknown",
    ) -> str:
        """
        Analyze a single image using the configured Ollama vision model.

        Args:
            image_path:
                Local filesystem path to the image.
            prompt:
                Optional custom user prompt. If omitted, a default prompt
                is generated based on filename_hint and image_type.
            filename_hint:
                Optional original file name or source identifier.
            image_type:
                High-level image type hint used by the default prompt builder.

        Returns:
            Model output as cleaned plain text.

        Raises:
            FileNotFoundError:
                If the image file does not exist.
            RuntimeError:
                If the Ollama request fails or returns an invalid response.
        """
        path = Path(image_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Image not found: {path}")

        user_prompt = prompt or self._build_prompt(
            name=filename_hint or path.name,
            image_type=image_type,
        )

        image_b64 = self._encode_image(path)

        logger.info(
            "Analyzing image with vision model: %s | image_type=%s | custom_prompt=%s",
            path.name,
            image_type,
            bool(prompt),
        )

        try:
            data = self._post_chat_request(
                prompt=user_prompt,
                image_b64=image_b64,
            )
            content = self._extract_message_content(data)

            if not content:
                raise RuntimeError("Vision model returned an empty response.")

            return self._post_process_response(content)

        except requests.RequestException as exc:
            logger.exception("Vision request failed for %s: %s", path.name, exc)
            raise RuntimeError(f"Vision request failed for {path.name}") from exc
        except RuntimeError:
            raise
        except Exception as exc:
            logger.exception("Unexpected vision processing failure for %s: %s", path.name, exc)
            raise RuntimeError(f"Unexpected vision processing failure for {path.name}") from exc

    def describe_many(
        self,
        image_paths: Iterable[str | Path],
        *,
        image_type: str = "unknown",
        prompt: str | None = None,
    ) -> list[dict[str, str]]:
        """
        Analyze multiple images sequentially.

        Args:
            image_paths:
                Iterable of image file paths.
            image_type:
                Default image type hint for all images.
            prompt:
                Optional custom prompt applied to every image.

        Returns:
            List of result dictionaries. Each entry contains:
            - path
            - description
            - optional error
        """
        results: list[dict[str, str]] = []

        for image_path in image_paths:
            try:
                description = self.describe_image(
                    image_path=image_path,
                    prompt=prompt,
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

    def _post_chat_request(self, *, prompt: str, image_b64: str) -> dict[str, Any]:
        """
        Send a vision request to Ollama chat API and return parsed JSON.
        """
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
        if not isinstance(data, dict):
            raise RuntimeError("Vision model returned a non-object JSON response.")

        return data

    def _extract_message_content(self, data: dict[str, Any]) -> str:
        """
        Extract assistant content from Ollama /api/chat response.
        """
        message = data.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Vision model response missing 'message' object.")

        content = message.get("content", "")
        if not isinstance(content, str):
            raise RuntimeError("Vision model response field 'content' is not a string.")

        return content.strip()

    def _encode_image(self, path: Path) -> str:
        """
        Base64-encode the image file for Ollama multimodal input.
        """
        return base64.b64encode(path.read_bytes()).decode("utf-8")

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
            - Output plain text only unless the user explicitly requests JSON.
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
        normalized_type = (image_type or "unknown").lower()

        if normalized_type == "diagram":
            return textwrap.dedent(
                """\
                Diagram-specific rules:
                - Identify boxes, nodes, states, components, and connectors.
                - If it is a state machine, list states and transitions clearly.
                - If it is a flow chart, describe the process in order, including decisions.
                - Pay close attention to arrows, branching, and labels.
                """
            ).strip()

        if normalized_type == "screenshot":
            return textwrap.dedent(
                """\
                Screenshot-specific rules:
                - Describe visible panels, controls, forms, tables, buttons, and messages.
                - Extract important visible text.
                - Mention warnings, errors, statuses, or values if present.
                """
            ).strip()

        if normalized_type == "document":
            return textwrap.dedent(
                """\
                Document-specific rules:
                - Focus on extracting visible text and document structure.
                - Preserve headings, labels, and important values.
                - If it looks like a scanned page, summarize the main written content.
                """
            ).strip()

        if normalized_type == "photo":
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
        """
        Normalize line breaks and trim whitespace without altering content meaning.
        """
        cleaned = text.strip()

        while "\n\n\n" in cleaned:
            cleaned = cleaned.replace("\n\n\n", "\n\n")

        return cleaned