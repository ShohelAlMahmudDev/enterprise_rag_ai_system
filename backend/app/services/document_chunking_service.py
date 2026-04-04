import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.parsers.document_parser import ParsedDocument, ParsedSection, parse_document

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ChunkRecord:
    """
    Normalized chunk record ready for vector indexing or DB persistence.
    """

    text: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "metadata": self.metadata,
        }


class DocumentChunkingService:
    """
    Converts parsed documents into chunked, metadata-rich records for indexing.

    Responsibilities:
    - parse supported files into structured sections
    - chunk oversized sections into smaller retrieval units
    - preserve section-level metadata
    - attach document-level metadata
    - return FAISS-ready text and metadata arrays
    """

    def __init__(
        self,
        *,
        default_chunk_size: int | None = None,
        default_chunk_overlap: int | None = None,
    ) -> None:
        self.default_chunk_size = default_chunk_size or settings.DEFAULT_CHUNK_SIZE
        self.default_chunk_overlap = default_chunk_overlap or settings.DEFAULT_CHUNK_OVERLAP

        if self.default_chunk_size <= 0:
            raise ValueError("DEFAULT_CHUNK_SIZE must be greater than 0.")
        if self.default_chunk_overlap < 0:
            raise ValueError("DEFAULT_CHUNK_OVERLAP cannot be negative.")
        if self.default_chunk_overlap >= self.default_chunk_size:
            raise ValueError("DEFAULT_CHUNK_OVERLAP must be smaller than DEFAULT_CHUNK_SIZE.")

    def build_chunks_from_file(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
        version_id: str | None = None,
        logical_name: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> list[ChunkRecord]:
        """
        Parse a file and build chunk records with preserved metadata.
        """
        path = Path(file_path)
        parsed = parse_document(str(path))

        return self.build_chunks_from_parsed_document(
            parsed_document=parsed,
            source_path=path,
            document_id=document_id,
            version_id=version_id,
            logical_name=logical_name,
            extra_metadata=extra_metadata,
        )

    def build_chunks_from_parsed_document(
        self,
        *,
        parsed_document: ParsedDocument,
        source_path: str | Path,
        document_id: str | None = None,
        version_id: str | None = None,
        logical_name: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> list[ChunkRecord]:
        """
        Build chunk records from an already parsed document.
        """
        path = Path(source_path)
        file_type = parsed_document.file_type or path.suffix.lower()
        base_metadata = self._build_base_metadata(
            source_path=path,
            file_type=file_type,
            document_id=document_id,
            version_id=version_id,
            logical_name=logical_name,
            extra_metadata=extra_metadata,
        )

        chunk_records: list[ChunkRecord] = []
        section_counter = 0

        for section in parsed_document.sections:
            section_counter += 1
            section_records = self._chunk_section(
                section=section,
                base_metadata=base_metadata,
                section_index=section_counter,
            )
            chunk_records.extend(section_records)

        logger.info(
            "Built %s chunk(s) from %s (%s sections)",
            len(chunk_records),
            path.name,
            len(parsed_document.sections),
        )

        return chunk_records

    def to_vector_store_payload(
        self,
        chunks: list[ChunkRecord],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """
        Convert chunk records into vector-store-ready arrays.
        """
        texts = [chunk.text for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]
        return texts, metadatas

    def build_vector_store_payload_from_file(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
        version_id: str | None = None,
        logical_name: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """
        Convenience wrapper for:
        parse -> chunk -> vector-store payload
        """
        chunks = self.build_chunks_from_file(
            file_path=file_path,
            document_id=document_id,
            version_id=version_id,
            logical_name=logical_name,
            extra_metadata=extra_metadata,
        )
        return self.to_vector_store_payload(chunks)

    def _chunk_section(
        self,
        *,
        section: ParsedSection,
        base_metadata: dict[str, Any],
        section_index: int,
    ) -> list[ChunkRecord]:
        """
        Chunk a single parsed section while preserving metadata.
        """
        text = (section.text or "").strip()
        if not text:
            return []

        section_metadata = dict(section.metadata or {})
        chunk_texts = self._split_text(
            text=text,
            chunk_size=self.default_chunk_size,
            chunk_overlap=self.default_chunk_overlap,
        )

        records: list[ChunkRecord] = []
        total_chunks = len(chunk_texts)

        for chunk_index, chunk_text in enumerate(chunk_texts, start=1):
            metadata = dict(base_metadata)
            metadata.update(section_metadata)
            metadata.update(
                {
                    "section_index": section_index,
                    "chunk_index": chunk_index,
                    "chunks_in_section": total_chunks,
                    "chunk_id": self._build_chunk_id(
                        document_id=base_metadata.get("document_id"),
                        version_id=base_metadata.get("version_id"),
                        section_index=section_index,
                        chunk_index=chunk_index,
                    ),
                }
            )

            records.append(
                ChunkRecord(
                    text=chunk_text,
                    metadata=metadata,
                )
            )

        return records

    def _build_base_metadata(
        self,
        *,
        source_path: Path,
        file_type: str,
        document_id: str | None,
        version_id: str | None,
        logical_name: str | None,
        extra_metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "source_file": source_path.name,
            "source_path": str(source_path),
            "filename": source_path.name,
            "file_type": file_type,
            "logical_name": logical_name or source_path.stem,
            "document_id": document_id,
            "version_id": version_id,
        }

        if extra_metadata:
            metadata.update(extra_metadata)

        return metadata

    def _build_chunk_id(
        self,
        *,
        document_id: str | None,
        version_id: str | None,
        section_index: int,
        chunk_index: int,
    ) -> str:
        """
        Build a stable-enough chunk identifier.
        """
        prefix_parts = [
            document_id or "doc",
            version_id or "ver",
            f"s{section_index}",
            f"c{chunk_index}",
        ]
        return "_".join(prefix_parts)

    def _split_text(
        self,
        *,
        text: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[str]:
        """
        Split text into overlapping chunks.

        Strategy:
        - first try paragraph-aware grouping
        - if a paragraph is too large, split it by character window
        """
        normalized = text.strip()
        if not normalized:
            return []

        paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [normalized]

        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs:
            if not current:
                if len(paragraph) <= chunk_size:
                    current = paragraph
                else:
                    chunks.extend(
                        self._split_large_block(
                            block=paragraph,
                            chunk_size=chunk_size,
                            chunk_overlap=chunk_overlap,
                        )
                    )
                continue

            candidate = f"{current}\n\n{paragraph}"
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                chunks.append(current.strip())

                if len(paragraph) <= chunk_size:
                    current = paragraph
                else:
                    chunks.extend(
                        self._split_large_block(
                            block=paragraph,
                            chunk_size=chunk_size,
                            chunk_overlap=chunk_overlap,
                        )
                    )
                    current = ""

        if current.strip():
            chunks.append(current.strip())

        return [chunk for chunk in chunks if chunk.strip()]

    def _split_large_block(
        self,
        *,
        block: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[str]:
        """
        Split a large text block by sliding character window.
        """
        text = block.strip()
        if not text:
            return []

        results: list[str] = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = min(start + chunk_size, text_length)
            piece = text[start:end].strip()
            if piece:
                results.append(piece)

            if end >= text_length:
                break

            start = max(end - chunk_overlap, start + 1)

        return results