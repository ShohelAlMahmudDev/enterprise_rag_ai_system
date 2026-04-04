import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from app.schemas.diagram_schema import (
    DiagramEdge,
    DiagramExtraction,
    DiagramExtractionResult,
    DiagramMessage,
    DiagramNode,
    DiagramStep,
)
from app.schemas.diagram_types import DiagramType
from app.services.vision_service import VisionService

logger = logging.getLogger(__name__)


class DiagramExtractor:
    """
    Extracts structured diagram information from an image using a vision-capable LLM.

    Responsibilities:
    - classify the diagram/image into a normalized DiagramType
    - ask the vision model for structured JSON
    - parse and validate model output
    - return a safe DiagramExtractionResult with warnings on partial failures
    """

    def __init__(self, vision_service: VisionService) -> None:
        self.vision_service = vision_service

    def extract_from_image(
        self,
        image_path: str | Path,
        *,
        filename_hint: str | None = None,
        page_number: int | None = None,
        slide_number: int | None = None,
        sheet_name: str | None = None,
        image_type: str | None = None,
        extra_context: str | None = None,
    ) -> DiagramExtractionResult:
        warnings: list[str] = []
        path = Path(image_path)

        if not path.exists() or not path.is_file():
            logger.warning("DiagramExtractor: image file not found: %s", path)
            fallback = self._build_fallback_extraction(
                raw_text=None,
                summary="Image file not found during diagram extraction.",
                diagram_type=DiagramType.GENERIC_IMAGE,
                metadata=self._build_source_metadata(
                    filename_hint=filename_hint,
                    page_number=page_number,
                    slide_number=slide_number,
                    sheet_name=sheet_name,
                    image_type=image_type,
                    image_path=str(path),
                ),
            )
            return DiagramExtractionResult(
                extraction=fallback,
                warnings=["Image file not found."],
                classifier_source="fallback",
                extractor_source="fallback",
            )

        try:
            classification_prompt = self._build_classification_prompt(
                filename_hint=filename_hint,
                page_number=page_number,
                slide_number=slide_number,
                sheet_name=sheet_name,
                image_type=image_type,
                extra_context=extra_context,
            )
            raw_classification = self.vision_service.describe_image(
                image_path=path,
                prompt=classification_prompt,
                filename_hint=filename_hint,
                image_type=image_type or "unknown",
            )
        except Exception as exc:
            logger.exception("Diagram classification failed for image %s", path)
            warnings.append(f"Diagram classification failed: {exc}")
            raw_classification = None

        diagram_type = self._parse_classification(raw_classification)

        try:
            extraction_prompt = self._build_extraction_prompt(
                diagram_type=diagram_type,
                filename_hint=filename_hint,
                page_number=page_number,
                slide_number=slide_number,
                sheet_name=sheet_name,
                image_type=image_type,
                extra_context=extra_context,
            )
            raw_extraction = self.vision_service.describe_image(
                image_path=path,
                prompt=extraction_prompt,
                filename_hint=filename_hint,
                image_type=image_type or "unknown",
            )
        except Exception as exc:
            logger.exception("Diagram extraction failed for image %s", path)
            warnings.append(f"Diagram extraction failed: {exc}")
            raw_extraction = None

        parsed = self._parse_extraction_response(
            raw_response=raw_extraction,
            diagram_type=diagram_type,
            source_metadata=self._build_source_metadata(
                filename_hint=filename_hint,
                page_number=page_number,
                slide_number=slide_number,
                sheet_name=sheet_name,
                image_type=image_type,
                image_path=str(path),
            ),
        )

        warnings.extend(parsed["warnings"])
        extraction = parsed["extraction"]

        if not extraction.is_meaningful:
            extraction = self._build_fallback_extraction(
                raw_text=self._safe_text(raw_extraction),
                summary="Best-effort visual extraction produced limited structured information.",
                diagram_type=diagram_type,
                metadata=self._build_source_metadata(
                    filename_hint=filename_hint,
                    page_number=page_number,
                    slide_number=slide_number,
                    sheet_name=sheet_name,
                    image_type=image_type,
                    image_path=str(path),
                ),
            )
            warnings.append("Structured extraction was empty; fallback extraction created.")

        return DiagramExtractionResult(
            extraction=extraction,
            warnings=warnings,
            classifier_source="ollama_vision",
            extractor_source="ollama_vision",
        )

    def _build_classification_prompt(
        self,
        *,
        filename_hint: str | None,
        page_number: int | None,
        slide_number: int | None,
        sheet_name: str | None,
        image_type: str | None,
        extra_context: str | None,
    ) -> str:
        context = self._format_context(
            filename_hint=filename_hint,
            page_number=page_number,
            slide_number=slide_number,
            sheet_name=sheet_name,
            image_type=image_type,
            extra_context=extra_context,
        )

        return f"""
You are classifying an enterprise document image for a multimodal RAG system.

Your task:
Return exactly one diagram type from this list and nothing else:

- state_machine
- flowchart
- sequence
- architecture
- network
- table_screenshot
- ui_screenshot
- generic_image

Classification rules:
- state_machine: states and transitions
- flowchart: process steps, decisions, arrows
- sequence: participants and ordered messages
- architecture: components, systems, interfaces, services
- network: hosts, devices, links, topology, connectivity
- table_screenshot: screenshot or image of a table/grid/spreadsheet
- ui_screenshot: application screen, form, dashboard, web UI
- generic_image: none of the above

{context}
""".strip()

    def _build_extraction_prompt(
        self,
        *,
        diagram_type: DiagramType,
        filename_hint: str | None,
        page_number: int | None,
        slide_number: int | None,
        sheet_name: str | None,
        image_type: str | None,
        extra_context: str | None,
    ) -> str:
        context = self._format_context(
            filename_hint=filename_hint,
            page_number=page_number,
            slide_number=slide_number,
            sheet_name=sheet_name,
            image_type=image_type,
            extra_context=extra_context,
        )

        return f"""
You are extracting structured information from an enterprise document image for a multimodal RAG system.

The image has been classified as: {diagram_type.value}

Return ONLY valid JSON.
Do not wrap the JSON in markdown.
Do not add explanations.

Schema rules:
- Output a single JSON object.
- Use these keys exactly:
  diagram_type, title, summary, nodes, edges, participants, messages,
  steps, decisions, components, interfaces, protocols, keywords, raw_text, confidence, metadata
- diagram_type must be one of:
  state_machine, flowchart, sequence, architecture, network, table_screenshot, ui_screenshot, generic_image
- Use empty arrays if a field does not apply.
- Use null only for optional scalar fields that are not available.
- confidence must be a number between 0.0 and 1.0 if provided.

Node format:
{{
  "id": "n1",
  "label": "Connected",
  "type": "state",
  "description": "optional",
  "metadata": {{}}
}}

Edge format:
{{
  "source": "n1",
  "target": "n2",
  "label": "connect request",
  "condition": "optional",
  "direction": "optional",
  "metadata": {{}}
}}

Message format:
{{
  "order": 1,
  "sender": "Client",
  "receiver": "Server",
  "label": "Connect()",
  "condition": "optional",
  "metadata": {{}}
}}

Step format:
{{
  "order": 1,
  "label": "Validate request",
  "step_type": "process",
  "description": "optional",
  "metadata": {{}}
}}

Extraction guidance:
- Prefer faithful extraction over guessing.
- If text is hard to read, include the best-effort text in raw_text.
- For architecture/network diagrams, extract components, interfaces, and protocols where visible.
- For flowcharts, extract steps and decisions.
- For sequence diagrams, extract participants and messages.
- For state diagrams, extract nodes and transitions.
- For table screenshots, summarize headers, visible structure, and important keywords.
- For UI screenshots, summarize visible sections, buttons, fields, and labels in summary/raw_text.

{context}

Return valid JSON only.
""".strip()

    def _parse_classification(self, raw_classification: str | None) -> DiagramType:
        if not raw_classification:
            return DiagramType.GENERIC_IMAGE

        text = raw_classification.strip().strip("`").strip()

        direct = DiagramType.from_value(text)
        if direct != DiagramType.GENERIC_IMAGE or text.lower().replace("-", "_").replace(" ", "_") == "generic_image":
            return direct

        candidate_json = self._extract_json_object(text)
        if candidate_json:
            try:
                parsed = json.loads(candidate_json)
                if isinstance(parsed, dict):
                    for key in ("diagram_type", "type", "classification", "label"):
                        if key in parsed:
                            return DiagramType.from_value(str(parsed[key]))
            except Exception:
                logger.debug("Classification JSON parse failed.")

        lowered = text.lower()
        for item in DiagramType:
            if item.value in lowered:
                return item

        return DiagramType.GENERIC_IMAGE

    def _parse_extraction_response(
        self,
        *,
        raw_response: str | None,
        diagram_type: DiagramType,
        source_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        warnings: list[str] = []

        if not raw_response:
            warnings.append("Vision model returned empty extraction response.")
            return {
                "warnings": warnings,
                "extraction": self._build_fallback_extraction(
                    raw_text=None,
                    summary="Vision model returned empty extraction response.",
                    diagram_type=diagram_type,
                    metadata=source_metadata,
                ),
            }

        payload = self._load_best_effort_json(raw_response.strip())
        if payload is None:
            warnings.append("Could not parse extraction response as JSON.")
            return {
                "warnings": warnings,
                "extraction": self._build_fallback_extraction(
                    raw_text=self._safe_text(raw_response),
                    summary="Failed to parse structured JSON from vision response.",
                    diagram_type=diagram_type,
                    metadata=source_metadata,
                ),
            }

        extraction = self._coerce_payload_to_extraction(
            payload=payload,
            fallback_diagram_type=diagram_type,
            source_metadata=source_metadata,
            warnings=warnings,
        )

        return {"warnings": warnings, "extraction": extraction}

    def _coerce_payload_to_extraction(
        self,
        *,
        payload: dict[str, Any],
        fallback_diagram_type: DiagramType,
        source_metadata: dict[str, Any],
        warnings: list[str],
    ) -> DiagramExtraction:
        normalized_payload = dict(payload)

        normalized_payload["diagram_type"] = DiagramType.from_value(
            str(normalized_payload.get("diagram_type") or fallback_diagram_type.value)
        )

        normalized_payload["nodes"] = self._sanitize_nodes(normalized_payload.get("nodes"))
        normalized_payload["edges"] = self._sanitize_edges(normalized_payload.get("edges"))
        normalized_payload["messages"] = self._sanitize_messages(normalized_payload.get("messages"))
        normalized_payload["steps"] = self._sanitize_steps(normalized_payload.get("steps"))
        normalized_payload["participants"] = self._sanitize_string_list(normalized_payload.get("participants"))
        normalized_payload["decisions"] = self._sanitize_string_list(normalized_payload.get("decisions"))
        normalized_payload["components"] = self._sanitize_string_list(normalized_payload.get("components"))
        normalized_payload["interfaces"] = self._sanitize_string_list(normalized_payload.get("interfaces"))
        normalized_payload["protocols"] = self._sanitize_string_list(normalized_payload.get("protocols"))
        normalized_payload["keywords"] = self._sanitize_string_list(normalized_payload.get("keywords"))

        metadata = normalized_payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        metadata.update(source_metadata)
        normalized_payload["metadata"] = metadata

        try:
            return DiagramExtraction.model_validate(normalized_payload)
        except ValidationError as exc:
            logger.warning("DiagramExtraction validation failed: %s", exc)
            warnings.append("Structured extraction validation failed; using fallback extraction.")
            return self._build_fallback_extraction(
                raw_text=self._safe_text(payload.get("raw_text"))
                or self._safe_text(json.dumps(payload, ensure_ascii=False)),
                summary=self._safe_text(payload.get("summary")) or "Validation fallback for structured extraction.",
                diagram_type=fallback_diagram_type,
                metadata=source_metadata,
            )
        except Exception as exc:
            logger.exception("Unexpected extraction validation error")
            warnings.append(f"Unexpected extraction validation failure: {exc}")
            return self._build_fallback_extraction(
                raw_text=self._safe_text(json.dumps(payload, ensure_ascii=False)),
                summary="Unexpected structured extraction failure.",
                diagram_type=fallback_diagram_type,
                metadata=source_metadata,
            )

    def _build_fallback_extraction(
        self,
        *,
        raw_text: str | None,
        summary: str | None,
        diagram_type: DiagramType,
        metadata: dict[str, Any],
    ) -> DiagramExtraction:
        return DiagramExtraction(
            diagram_type=diagram_type,
            title=None,
            summary=summary,
            nodes=[],
            edges=[],
            participants=[],
            messages=[],
            steps=[],
            decisions=[],
            components=[],
            interfaces=[],
            protocols=[],
            keywords=[],
            raw_text=raw_text,
            confidence=0.25 if raw_text or summary else 0.0,
            metadata=metadata,
        )

    def _build_source_metadata(
        self,
        *,
        filename_hint: str | None,
        page_number: int | None,
        slide_number: int | None,
        sheet_name: str | None,
        image_type: str | None,
        image_path: str,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "source_modality": "vision",
            "image_path": image_path,
        }
        if filename_hint:
            metadata["filename_hint"] = filename_hint
        if page_number is not None:
            metadata["page_number"] = page_number
        if slide_number is not None:
            metadata["slide_number"] = slide_number
        if sheet_name:
            metadata["sheet_name"] = sheet_name
        if image_type:
            metadata["image_type"] = image_type
        return metadata

    def _format_context(
        self,
        *,
        filename_hint: str | None,
        page_number: int | None,
        slide_number: int | None,
        sheet_name: str | None,
        image_type: str | None,
        extra_context: str | None,
    ) -> str:
        lines: list[str] = ["Context:"]
        if filename_hint:
            lines.append(f"- filename_hint: {filename_hint}")
        if page_number is not None:
            lines.append(f"- page_number: {page_number}")
        if slide_number is not None:
            lines.append(f"- slide_number: {slide_number}")
        if sheet_name:
            lines.append(f'- sheet_name: "{sheet_name}"')
        if image_type:
            lines.append(f"- image_type: {image_type}")
        if extra_context:
            lines.append(f"- extra_context: {extra_context}")
        return "\n".join(lines)

    def _load_best_effort_json(self, raw_response: str) -> Optional[dict[str, Any]]:
        text = raw_response.strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        unfenced = self._strip_markdown_fence(text)
        if unfenced != text:
            try:
                parsed = json.loads(unfenced)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        candidate = self._extract_json_object(unfenced)
        if candidate:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        return None

    def _extract_json_object(self, text: str) -> Optional[str]:
        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape = False

        for index in range(start, len(text)):
            ch = text[index]

            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]

        return None

    def _strip_markdown_fence(self, text: str) -> str:
        pattern = r"^```(?:json)?\s*(.*?)\s*```$"
        match = re.match(pattern, text, flags=re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return text

    def _sanitize_nodes(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []

        cleaned: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for index, item in enumerate(value, start=1):
            if not isinstance(item, dict):
                continue

            node_id = self._safe_text(item.get("id")) or f"n{index}"
            label = self._safe_text(item.get("label")) or node_id
            node_type = self._safe_text(item.get("type")) or "node"
            description = self._safe_text(item.get("description"))
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}

            if node_id.casefold() in seen_ids:
                continue
            seen_ids.add(node_id.casefold())

            cleaned.append(
                DiagramNode(
                    id=node_id,
                    label=label,
                    type=node_type,
                    description=description,
                    metadata=metadata,
                ).model_dump()
            )

        return cleaned

    def _sanitize_edges(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []

        cleaned: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue

            source = self._safe_text(item.get("source"))
            target = self._safe_text(item.get("target"))
            if not source or not target:
                continue

            label = self._safe_text(item.get("label"))
            condition = self._safe_text(item.get("condition"))
            direction = self._safe_text(item.get("direction"))
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}

            cleaned.append(
                DiagramEdge(
                    source=source,
                    target=target,
                    label=label,
                    condition=condition,
                    direction=direction,
                    metadata=metadata,
                ).model_dump()
            )

        return cleaned

    def _sanitize_messages(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []

        cleaned: list[dict[str, Any]] = []
        next_order = 1

        for item in value:
            if not isinstance(item, dict):
                continue

            sender = self._safe_text(item.get("sender"))
            receiver = self._safe_text(item.get("receiver"))
            label = self._safe_text(item.get("label"))
            if not sender or not receiver or not label:
                continue

            order = item.get("order")
            if not isinstance(order, int) or order < 1:
                order = next_order

            condition = self._safe_text(item.get("condition"))
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}

            cleaned.append(
                DiagramMessage(
                    order=order,
                    sender=sender,
                    receiver=receiver,
                    label=label,
                    condition=condition,
                    metadata=metadata,
                ).model_dump()
            )
            next_order = max(next_order, order + 1)

        cleaned.sort(key=lambda x: x["order"])
        return cleaned

    def _sanitize_steps(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []

        cleaned: list[dict[str, Any]] = []
        next_order = 1

        for item in value:
            if not isinstance(item, dict):
                continue

            label = self._safe_text(item.get("label"))
            if not label:
                continue

            order = item.get("order")
            if not isinstance(order, int) or order < 1:
                order = next_order

            step_type = self._safe_text(item.get("step_type"))
            description = self._safe_text(item.get("description"))
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}

            cleaned.append(
                DiagramStep(
                    order=order,
                    label=label,
                    step_type=step_type,
                    description=description,
                    metadata=metadata,
                ).model_dump()
            )
            next_order = max(next_order, order + 1)

        cleaned.sort(key=lambda x: x["order"])
        return cleaned

    def _sanitize_string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []

        cleaned: list[str] = []
        seen: set[str] = set()

        for item in value:
            text = self._safe_text(item)
            if not text:
                continue

            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)

        return cleaned

    def _safe_text(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        value = value.strip()
        return value or None