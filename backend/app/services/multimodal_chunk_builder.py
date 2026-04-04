import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.schemas.diagram_schema import DiagramExtractionResult
from app.services.diagram_extractor import DiagramExtractor
from app.services.vision_service import VisionService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MultimodalChunk:
    """
    Normalized chunk object for multimodal ingestion.

    This can later be converted into:
    - DB rows
    - FAISS metadata entries
    - API response source objects
    """

    text: str
    chunk_type: str
    source_modality: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "chunk_type": self.chunk_type,
            "source_modality": self.source_modality,
            "metadata": self.metadata,
        }


class MultimodalChunkBuilder:
    """
    Builds retrieval-ready chunks from image inputs.

    Strategy:
    - always create a generic vision description
    - optionally create structured diagram extraction for diagram-like content
    - merge everything into one normalized retrieval text block
    """

    DIAGRAM_IMAGE_TYPES = {
        "diagram",
        "architecture",
        "network",
        "flowchart",
        "state_machine",
        "sequence",
    }

    def __init__(
        self,
        *,
        vision_service: VisionService,
        diagram_extractor: DiagramExtractor,
    ) -> None:
        self.vision_service = vision_service
        self.diagram_extractor = diagram_extractor

    def build_image_chunk(
        self,
        image_path: str | Path,
        *,
        filename_hint: str | None = None,
        logical_name: str | None = None,
        image_type: str = "unknown",
        page_number: int | None = None,
        slide_number: int | None = None,
        sheet_name: str | None = None,
        extra_context: str | None = None,
        chunk_id: str | None = None,
    ) -> MultimodalChunk:
        """
        Build one retrieval-ready chunk from an image.

        Returns:
            MultimodalChunk
        """
        path = Path(image_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Image not found: {path}")

        logger.info(
            "Building multimodal chunk for image=%s | image_type=%s",
            path.name,
            image_type,
        )

        description = self._describe_image(
            image_path=path,
            filename_hint=filename_hint,
            image_type=image_type,
        )

        diagram_result: DiagramExtractionResult | None = None
        if self._should_run_diagram_extraction(image_type=image_type, filename_hint=filename_hint):
            diagram_result = self._extract_diagram(
                image_path=path,
                filename_hint=filename_hint,
                page_number=page_number,
                slide_number=slide_number,
                sheet_name=sheet_name,
                image_type=image_type,
                extra_context=extra_context,
            )

        text = self._compose_retrieval_text(
            description=description,
            diagram_result=diagram_result,
        )

        metadata = self._build_metadata(
            image_path=str(path),
            filename_hint=filename_hint or path.name,
            logical_name=logical_name,
            image_type=image_type,
            page_number=page_number,
            slide_number=slide_number,
            sheet_name=sheet_name,
            chunk_id=chunk_id,
            description=description,
            diagram_result=diagram_result,
        )

        return MultimodalChunk(
            text=text,
            chunk_type="multimodal_image",
            source_modality="vision",
            metadata=metadata,
        )

    def _describe_image(
        self,
        *,
        image_path: str | Path,
        filename_hint: str | None,
        image_type: str,
    ) -> str:
        try:
            return self.vision_service.describe_image(
                image_path=image_path,
                filename_hint=filename_hint,
                image_type=image_type,
            )
        except Exception as exc:
            logger.exception("Generic vision description failed for %s", image_path)
            return f"Vision description unavailable. Error: {exc}"

    def _extract_diagram(
        self,
        *,
        image_path: str | Path,
        filename_hint: str | None,
        page_number: int | None,
        slide_number: int | None,
        sheet_name: str | None,
        image_type: str,
        extra_context: str | None,
    ) -> DiagramExtractionResult | None:
        try:
            return self.diagram_extractor.extract_from_image(
                image_path=image_path,
                filename_hint=filename_hint,
                page_number=page_number,
                slide_number=slide_number,
                sheet_name=sheet_name,
                image_type=image_type,
                extra_context=extra_context,
            )
        except Exception:
            logger.exception("Diagram extraction failed for %s", image_path)
            return None

    def _should_run_diagram_extraction(
        self,
        *,
        image_type: str,
        filename_hint: str | None,
    ) -> bool:
        normalized_type = (image_type or "unknown").strip().lower()
        if normalized_type in self.DIAGRAM_IMAGE_TYPES:
            return True

        if filename_hint:
            lowered = filename_hint.lower()
            keywords = ("diagram", "flow", "state", "sequence", "architecture", "network")
            if any(keyword in lowered for keyword in keywords):
                return True

        return False

    def _compose_retrieval_text(
        self,
        *,
        description: str,
        diagram_result: DiagramExtractionResult | None,
    ) -> str:
        parts: list[str] = []

        if description:
            parts.append("Vision Description:")
            parts.append(description.strip())

        if diagram_result and diagram_result.extraction:
            structured_text = diagram_result.extraction.to_retrieval_text()
            if structured_text:
                parts.append("")
                parts.append("Structured Diagram Extraction:")
                parts.append(structured_text)

            if diagram_result.warnings:
                parts.append("")
                parts.append("Extraction Warnings:")
                for warning in diagram_result.warnings:
                    parts.append(f"- {warning}")

        text = "\n".join(parts).strip()

        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")

        return text

    def _build_metadata(
        self,
        *,
        image_path: str,
        filename_hint: str,
        logical_name: str | None,
        image_type: str,
        page_number: int | None,
        slide_number: int | None,
        sheet_name: str | None,
        chunk_id: str | None,
        description: str,
        diagram_result: DiagramExtractionResult | None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "content_type": "image",
            "chunk_type": "multimodal_image",
            "source_modality": "vision",
            "image_path": image_path,
            "filename": filename_hint,
            "logical_name": logical_name,
            "image_type": image_type,
            "chunk_id": chunk_id,
            "page_number": page_number,
            "slide_number": slide_number,
            "sheet_name": sheet_name,
            "vision_description": description,
        }

        if diagram_result:
            metadata["diagram_extraction"] = diagram_result.extraction.model_dump(mode="json")
            metadata["diagram_type"] = diagram_result.extraction.diagram_type.value
            metadata["diagram_warnings"] = list(diagram_result.warnings)
            metadata["has_structured_extraction"] = diagram_result.extraction.has_structured_content
        else:
            metadata["diagram_extraction"] = None
            metadata["diagram_type"] = None
            metadata["diagram_warnings"] = []
            metadata["has_structured_extraction"] = False

        return metadata

    @staticmethod
    def serialize_metadata(metadata: dict[str, Any]) -> str:
        """
        Optional helper if you want to store metadata as JSON text.
        """
        return json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))