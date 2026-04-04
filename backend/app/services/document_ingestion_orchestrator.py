from pathlib import Path
from typing import Any

from app.services.document_chunking_service import DocumentChunkingService


class DocumentIngestionOrchestrator:
    """
    High-level orchestration:
    file -> parsed sections -> chunk records -> vector-store payload
    """

    def __init__(
        self,
        *,
        chunking_service: DocumentChunkingService | None = None,
    ) -> None:
        self.chunking_service = chunking_service or DocumentChunkingService()

    def prepare_index_payload(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
        version_id: str | None = None,
        logical_name: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        return self.chunking_service.build_vector_store_payload_from_file(
            file_path=file_path,
            document_id=document_id,
            version_id=version_id,
            logical_name=logical_name,
            extra_metadata=extra_metadata,
        )