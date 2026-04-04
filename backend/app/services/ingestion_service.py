import logging
from pathlib import Path
from typing import Any

from app.services.diagram_extractor import DiagramExtractor
from app.services.multimodal_chunk_builder import MultimodalChunk, MultimodalChunkBuilder
from app.services.vision_service import VisionService

logger = logging.getLogger(__name__)


class ImageIngestionService:
    """
    Service for image-based multimodal ingestion.

    Responsibilities:
    - build retrieval-ready multimodal chunks from image files
    - encapsulate VisionService + DiagramExtractor + MultimodalChunkBuilder wiring
    - provide single-image and batch-image ingestion helpers
    - optionally expose FAISS-ready text/metadata payloads

    Typical usage:
        service = ImageIngestionService()
        result = service.ingest_image(
            image_path="data/uploads/diagram.png",
            logical_name="RaSTA Spec",
            filename_hint="rasta_spec.pdf",
            image_type="diagram",
            page_number=4,
            chunk_id="doc123_chunk_17",
        )
    """

    def __init__(
        self,
        *,
        vision_service: VisionService | None = None,
        diagram_extractor: DiagramExtractor | None = None,
        chunk_builder: MultimodalChunkBuilder | None = None,
    ) -> None:
        self.vision_service = vision_service or VisionService()
        self.diagram_extractor = diagram_extractor or DiagramExtractor(
            vision_service=self.vision_service,
        )
        self.chunk_builder = chunk_builder or MultimodalChunkBuilder(
            vision_service=self.vision_service,
            diagram_extractor=self.diagram_extractor,
        )

    def ingest_image(
        self,
        image_path: str | Path,
        *,
        logical_name: str | None = None,
        filename_hint: str | None = None,
        image_type: str = "unknown",
        page_number: int | None = None,
        slide_number: int | None = None,
        sheet_name: str | None = None,
        extra_context: str | None = None,
        chunk_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Ingest a single image and return a normalized chunk dictionary.

        Returns:
            {
                "text": "...",
                "chunk_type": "multimodal_image",
                "source_modality": "vision",
                "metadata": {...}
            }
        """
        path = self._validate_image_path(image_path)

        logger.info(
            "Ingesting image: %s | image_type=%s | logical_name=%s | chunk_id=%s",
            path.name,
            image_type,
            logical_name,
            chunk_id,
        )

        chunk = self.chunk_builder.build_image_chunk(
            image_path=path,
            logical_name=logical_name,
            filename_hint=filename_hint or path.name,
            image_type=image_type,
            page_number=page_number,
            slide_number=slide_number,
            sheet_name=sheet_name,
            extra_context=extra_context,
            chunk_id=chunk_id,
        )

        result = chunk.to_dict()

        logger.info(
            "Image ingested successfully: %s | chunk_type=%s | has_structured_extraction=%s",
            path.name,
            result.get("chunk_type"),
            result.get("metadata", {}).get("has_structured_extraction"),
        )

        return result

    def ingest_image_as_chunk(
        self,
        image_path: str | Path,
        *,
        logical_name: str | None = None,
        filename_hint: str | None = None,
        image_type: str = "unknown",
        page_number: int | None = None,
        slide_number: int | None = None,
        sheet_name: str | None = None,
        extra_context: str | None = None,
        chunk_id: str | None = None,
    ) -> MultimodalChunk:
        """
        Ingest a single image and return the native MultimodalChunk object.
        Useful when the caller wants stronger typing before serialization.
        """
        path = self._validate_image_path(image_path)

        return self.chunk_builder.build_image_chunk(
            image_path=path,
            logical_name=logical_name,
            filename_hint=filename_hint or path.name,
            image_type=image_type,
            page_number=page_number,
            slide_number=slide_number,
            sheet_name=sheet_name,
            extra_context=extra_context,
            chunk_id=chunk_id,
        )

    def ingest_many(
        self,
        image_paths: list[str | Path],
        *,
        logical_name: str | None = None,
        filename_hint: str | None = None,
        image_type: str = "unknown",
        page_number_start: int | None = None,
        slide_number_start: int | None = None,
        sheet_name: str | None = None,
        extra_context: str | None = None,
        chunk_id_prefix: str | None = None,
        continue_on_error: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Ingest multiple images.

        Notes:
        - page_number_start and slide_number_start are optional conveniences.
        - if provided, the index is incremented per image.
        """
        results: list[dict[str, Any]] = []

        for index, image_path in enumerate(image_paths):
            page_number = page_number_start + index if page_number_start is not None else None
            slide_number = slide_number_start + index if slide_number_start is not None else None
            chunk_id = f"{chunk_id_prefix}_{index + 1}" if chunk_id_prefix else None

            try:
                result = self.ingest_image(
                    image_path=image_path,
                    logical_name=logical_name,
                    filename_hint=filename_hint,
                    image_type=image_type,
                    page_number=page_number,
                    slide_number=slide_number,
                    sheet_name=sheet_name,
                    extra_context=extra_context,
                    chunk_id=chunk_id,
                )
                results.append(result)

            except Exception as exc:
                logger.exception("Failed to ingest image %s", image_path)

                error_result = {
                    "text": "",
                    "chunk_type": "multimodal_image",
                    "source_modality": "vision",
                    "metadata": {
                        "content_type": "image",
                        "image_path": str(image_path),
                        "filename": Path(image_path).name,
                        "logical_name": logical_name,
                        "image_type": image_type,
                        "page_number": page_number,
                        "slide_number": slide_number,
                        "sheet_name": sheet_name,
                        "chunk_id": chunk_id,
                        "ingestion_error": str(exc),
                        "has_structured_extraction": False,
                    },
                }

                if continue_on_error:
                    results.append(error_result)
                else:
                    raise

        return results

    def ingest_for_vector_store(
        self,
        image_path: str | Path,
        *,
        logical_name: str | None = None,
        filename_hint: str | None = None,
        image_type: str = "unknown",
        page_number: int | None = None,
        slide_number: int | None = None,
        sheet_name: str | None = None,
        extra_context: str | None = None,
        chunk_id: str | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """
        Return vector-store-ready payload:
            texts: [chunk_text]
            metadatas: [chunk_metadata]

        This is convenient when your FAISS layer expects separate arrays.
        """
        result = self.ingest_image(
            image_path=image_path,
            logical_name=logical_name,
            filename_hint=filename_hint,
            image_type=image_type,
            page_number=page_number,
            slide_number=slide_number,
            sheet_name=sheet_name,
            extra_context=extra_context,
            chunk_id=chunk_id,
        )

        return [result["text"]], [result["metadata"]]

    def _validate_image_path(self, image_path: str | Path) -> Path:
        path = Path(image_path)

        if not path.exists():
            raise FileNotFoundError(f"Image file does not exist: {path}")

        if not path.is_file():
            raise FileNotFoundError(f"Image path is not a file: {path}")

        return path