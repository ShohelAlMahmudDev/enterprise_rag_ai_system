# import logging
# import uuid
# from dataclasses import dataclass
# from pathlib import Path
# from typing import Any

# from app.config import settings
# from app.parsers.document_parser import ParsedDocument, ParsedSection, parse_document

# logger = logging.getLogger(__name__)


# @dataclass(slots=True)
# class ChunkRecord:
#     """
#     Normalized chunk record ready for vector indexing or DB persistence.
#     """

#     text: str
#     metadata: dict[str, Any]

#     def to_dict(self) -> dict[str, Any]:
#         return {
#             "text": self.text,
#             "metadata": self.metadata,
#         }


# class DocumentChunkingService:
#     """
#     Converts parsed documents into chunked, metadata-rich records for indexing.

#     Responsibilities:
#     - parse supported files into structured sections
#     - chunk oversized sections into smaller retrieval units
#     - preserve section-level metadata
#     - attach document-level metadata
#     - return FAISS-ready text and metadata arrays
#     """

#     def __init__(
#         self,
#         *,
#         default_chunk_size: int | None = None,
#         default_chunk_overlap: int | None = None,
#     ) -> None:
#         self.default_chunk_size = default_chunk_size or settings.DEFAULT_CHUNK_SIZE
#         self.default_chunk_overlap = default_chunk_overlap or settings.DEFAULT_CHUNK_OVERLAP

#         if self.default_chunk_size <= 0:
#             raise ValueError("DEFAULT_CHUNK_SIZE must be greater than 0.")
#         if self.default_chunk_overlap < 0:
#             raise ValueError("DEFAULT_CHUNK_OVERLAP cannot be negative.")
#         if self.default_chunk_overlap >= self.default_chunk_size:
#             raise ValueError("DEFAULT_CHUNK_OVERLAP must be smaller than DEFAULT_CHUNK_SIZE.")

#     def build_chunks_from_file(
#         self,
#         file_path: str | Path,
#         *,
#         document_id: str | None = None,
#         version_id: str | None = None,
#         logical_name: str | None = None,
#         extra_metadata: dict[str, Any] | None = None,
#     ) -> list[ChunkRecord]:
#         """
#         Parse a file and build chunk records with preserved metadata.
#         """
#         path = Path(file_path)
#         parsed = parse_document(str(path))

#         return self.build_chunks_from_parsed_document(
#             parsed_document=parsed,
#             source_path=path,
#             document_id=document_id,
#             version_id=version_id,
#             logical_name=logical_name,
#             extra_metadata=extra_metadata,
#         )

#     def build_chunks_from_parsed_document(
#         self,
#         *,
#         parsed_document: ParsedDocument,
#         source_path: str | Path,
#         document_id: str | None = None,
#         version_id: str | None = None,
#         logical_name: str | None = None,
#         extra_metadata: dict[str, Any] | None = None,
#     ) -> list[ChunkRecord]:
#         """
#         Build chunk records from an already parsed document.
#         """
#         path = Path(source_path)
#         file_type = parsed_document.file_type or path.suffix.lower()
#         base_metadata = self._build_base_metadata(
#             source_path=path,
#             file_type=file_type,
#             document_id=document_id,
#             version_id=version_id,
#             logical_name=logical_name,
#             extra_metadata=extra_metadata,
#         )

#         chunk_records: list[ChunkRecord] = []
#         section_counter = 0

#         for section in parsed_document.sections:
#             section_counter += 1
#             section_records = self._chunk_section(
#                 section=section,
#                 base_metadata=base_metadata,
#                 section_index=section_counter,
#             )
#             chunk_records.extend(section_records)

#         logger.info(
#             "Built %s chunk(s) from %s (%s sections)",
#             len(chunk_records),
#             path.name,
#             len(parsed_document.sections),
#         )

#         return chunk_records

#     def to_vector_store_payload(
#         self,
#         chunks: list[ChunkRecord],
#     ) -> tuple[list[str], list[dict[str, Any]]]:
#         """
#         Convert chunk records into vector-store-ready arrays.
#         """
#         texts = [chunk.text for chunk in chunks]
#         metadatas = [chunk.metadata for chunk in chunks]
#         return texts, metadatas

#     def build_vector_store_payload_from_file(
#         self,
#         file_path: str | Path,
#         *,
#         document_id: str | None = None,
#         version_id: str | None = None,
#         logical_name: str | None = None,
#         extra_metadata: dict[str, Any] | None = None,
#     ) -> tuple[list[str], list[dict[str, Any]]]:
#         """
#         Convenience wrapper for:
#         parse -> chunk -> vector-store payload
#         """
#         chunks = self.build_chunks_from_file(
#             file_path=file_path,
#             document_id=document_id,
#             version_id=version_id,
#             logical_name=logical_name,
#             extra_metadata=extra_metadata,
#         )
#         return self.to_vector_store_payload(chunks)

#     def _chunk_section(
#         self,
#         *,
#         section: ParsedSection,
#         base_metadata: dict[str, Any],
#         section_index: int,
#     ) -> list[ChunkRecord]:
#         """
#         Chunk a single parsed section while preserving metadata.
#         """
#         text = (section.text or "").strip()
#         if not text:
#             return []

#         section_metadata = dict(section.metadata or {})
#         chunk_texts = self._split_text(
#             text=text,
#             chunk_size=self.default_chunk_size,
#             chunk_overlap=self.default_chunk_overlap,
#         )

#         records: list[ChunkRecord] = []
#         total_chunks = len(chunk_texts)

#         for chunk_index, chunk_text in enumerate(chunk_texts, start=1):
#             metadata = dict(base_metadata)
#             metadata.update(section_metadata)
#             metadata.update(
#                 {
#                     "section_index": section_index,
#                     "chunk_index": chunk_index,
#                     "chunks_in_section": total_chunks,
#                     "chunk_id": self._build_chunk_id(
#                         document_id=base_metadata.get("document_id"),
#                         version_id=base_metadata.get("version_id"),
#                         section_index=section_index,
#                         chunk_index=chunk_index,
#                     ),
#                 }
#             )

#             records.append(
#                 ChunkRecord(
#                     text=chunk_text,
#                     metadata=metadata,
#                 )
#             )

#         return records

#     def _build_base_metadata(
#         self,
#         *,
#         source_path: Path,
#         file_type: str,
#         document_id: str | None,
#         version_id: str | None,
#         logical_name: str | None,
#         extra_metadata: dict[str, Any] | None,
#     ) -> dict[str, Any]:
#         metadata: dict[str, Any] = {
#             "source_file": source_path.name,
#             "source_path": str(source_path),
#             "filename": source_path.name,
#             "file_type": file_type,
#             "logical_name": logical_name or source_path.stem,
#             "document_id": document_id,
#             "version_id": version_id,
#         }

#         if extra_metadata:
#             metadata.update(extra_metadata)

#         return metadata

#     def _build_chunk_id(
#         self,
#         *,
#         document_id: str | None,
#         version_id: str | None,
#         section_index: int,
#         chunk_index: int,
#     ) -> str:
#         """
#         Build a stable-enough chunk identifier.
#         """
#         prefix_parts = [
#             document_id or "doc",
#             version_id or "ver",
#             f"s{section_index}",
#             f"c{chunk_index}",
#         ]
#         return "_".join(prefix_parts)

#     def _split_text(
#         self,
#         *,
#         text: str,
#         chunk_size: int,
#         chunk_overlap: int,
#     ) -> list[str]:
#         """
#         Split text into overlapping chunks.

#         Strategy:
#         - first try paragraph-aware grouping
#         - if a paragraph is too large, split it by character window
#         """
#         normalized = text.strip()
#         if not normalized:
#             return []

#         paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]
#         if not paragraphs:
#             paragraphs = [normalized]

#         chunks: list[str] = []
#         current = ""

#         for paragraph in paragraphs:
#             if not current:
#                 if len(paragraph) <= chunk_size:
#                     current = paragraph
#                 else:
#                     chunks.extend(
#                         self._split_large_block(
#                             block=paragraph,
#                             chunk_size=chunk_size,
#                             chunk_overlap=chunk_overlap,
#                         )
#                     )
#                 continue

#             candidate = f"{current}\n\n{paragraph}"
#             if len(candidate) <= chunk_size:
#                 current = candidate
#             else:
#                 chunks.append(current.strip())

#                 if len(paragraph) <= chunk_size:
#                     current = paragraph
#                 else:
#                     chunks.extend(
#                         self._split_large_block(
#                             block=paragraph,
#                             chunk_size=chunk_size,
#                             chunk_overlap=chunk_overlap,
#                         )
#                     )
#                     current = ""

#         if current.strip():
#             chunks.append(current.strip())

#         return [chunk for chunk in chunks if chunk.strip()]

#     def _split_large_block(
#         self,
#         *,
#         block: str,
#         chunk_size: int,
#         chunk_overlap: int,
#     ) -> list[str]:
#         """
#         Split a large text block by sliding character window.
#         """
#         text = block.strip()
#         if not text:
#             return []

#         results: list[str] = []
#         start = 0
#         text_length = len(text)

#         while start < text_length:
#             end = min(start + chunk_size, text_length)
#             piece = text[start:end].strip()
#             if piece:
#                 results.append(piece)

#             if end >= text_length:
#                 break

#             start = max(end - chunk_overlap, start + 1)

#         return results

import logging
import re
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

    ENUM_MAPPING_PATTERN = re.compile(r"^\d+\s*=\s*.+$")
    ATTRIBUTE_PATTERN = re.compile(r'^\["[^"]+"\]')
    PAGE_PREFIX_PATTERN = re.compile(r"^Page\s+\d+(?:\s+\(OCR\))?$", re.IGNORECASE)

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
        text = (section.text or "").strip()
        if not text:
            return []

        section_metadata = dict(section.metadata or {})
        section_type = section_metadata.get("type", "")
        is_structured = bool(section_metadata.get("is_structured"))

        chunk_texts = self._split_section_by_type(
            text=text,
            section_type=section_type,
            is_structured=is_structured,
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

    def _split_section_by_type(
        self,
        *,
        text: str,
        section_type: str,
        is_structured: bool,
    ) -> list[str]:
        """
        Use structured splitting first for tables / mappings / technical specs.
        """
        if section_type == "xlsx_row":
            return [text]

        if section_type == "docx_table":
            chunks = self._split_docx_table_rows(text)
            return chunks if chunks else [text]

        if section_type in {"pdf_page", "image"} or is_structured:
            structured_chunks = self._split_structured_technical_block(text)
            if structured_chunks:
                return structured_chunks

        return self._split_text(
            text=text,
            chunk_size=self.default_chunk_size,
            chunk_overlap=self.default_chunk_overlap,
        )

    def _split_docx_table_rows(self, text: str) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return []

        table_heading = lines[0]
        rows = lines[1:] if len(lines) > 1 else []

        chunks: list[str] = []
        for index, row in enumerate(rows, start=1):
            chunks.append(f"{table_heading}\nRow {index}\n{row}")

        return chunks or [text]

    def _split_structured_technical_block(self, text: str) -> list[str]:
        """
        Split technical blocks into logical retrieval units.

        Handles:
        - numbered mappings like '26 = Request geo position information'
        - attribute blocks like ["action"], ["status"], ["messageHandle"]
        - mixed OCR/PDF technical tables
        """
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return []

        context_lines: list[str] = []
        index = 0

        while index < len(lines):
            line = lines[index]
            if self._is_context_line(line):
                context_lines.append(line)
                index += 1
            else:
                break

        if index >= len(lines):
            return [text]

        chunks: list[str] = []
        current_attribute: str | None = None
        current_attribute_lines: list[str] = []
        current_mappings: list[str] = []
        context_prefix = "\n".join(context_lines).strip()

        def flush_mapping_chunks() -> None:
            nonlocal current_mappings
            if not current_attribute or not current_mappings:
                current_mappings = []
                return

            attribute_header = "\n".join(current_attribute_lines).strip()
            for mapping_line in current_mappings:
                parts = [part for part in (context_prefix, attribute_header, mapping_line) if part]
                chunks.append("\n".join(parts).strip())
            current_mappings = []

        def flush_attribute_block() -> None:
            nonlocal current_attribute, current_attribute_lines, current_mappings

            flush_mapping_chunks()

            if current_attribute and current_attribute_lines:
                has_mapping_line = any(self._is_enum_mapping_line(item) for item in current_attribute_lines)
                if not has_mapping_line:
                    parts = [part for part in (context_prefix, "\n".join(current_attribute_lines).strip()) if part]
                    block_text = "\n".join(parts).strip()
                    if block_text:
                        chunks.append(block_text)

            current_attribute = None
            current_attribute_lines = []

        for line in lines[index:]:
            if self._is_attribute_line(line):
                flush_attribute_block()
                current_attribute = line
                current_attribute_lines = [line]
                continue

            if current_attribute is None:
                context_lines.append(line)
                context_prefix = "\n".join(context_lines).strip()
                continue

            if self._is_enum_mapping_line(line):
                current_mappings.append(line)
                continue

            current_attribute_lines.append(line)

        flush_attribute_block()

        chunks = [chunk for chunk in chunks if chunk.strip()]
        if chunks:
            return self._merge_small_chunks(chunks)

        return []

    def _merge_small_chunks(self, chunks: list[str]) -> list[str]:
        """
        Merge very small neighboring chunks, but keep mappings intact.
        """
        if not chunks:
            return []

        merged: list[str] = []
        buffer = chunks[0]

        for item in chunks[1:]:
            if len(buffer) < 180 and len(buffer) + 2 + len(item) <= self.default_chunk_size:
                buffer = f"{buffer}\n\n{item}"
            else:
                merged.append(buffer.strip())
                buffer = item

        if buffer.strip():
            merged.append(buffer.strip())

        return merged

    def _is_context_line(self, line: str) -> bool:
        if not line:
            return False
        if self.PAGE_PREFIX_PATTERN.match(line):
            return True
        if self.ATTRIBUTE_PATTERN.match(line):
            return False
        if self.ENUM_MAPPING_PATTERN.match(line):
            return False
        if "|" in line:
            return True
        if len(line.split()) <= 8:
            return True
        return False

    def _is_attribute_line(self, line: str) -> bool:
        return bool(self.ATTRIBUTE_PATTERN.match(line))

    def _is_enum_mapping_line(self, line: str) -> bool:
        return bool(self.ENUM_MAPPING_PATTERN.match(line))

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
                        self._split_large_block_by_lines_then_window(
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
                        self._split_large_block_by_lines_then_window(
                            block=paragraph,
                            chunk_size=chunk_size,
                            chunk_overlap=chunk_overlap,
                        )
                    )
                    current = ""

        if current.strip():
            chunks.append(current.strip())

        return [chunk for chunk in chunks if chunk.strip()]

    def _split_large_block_by_lines_then_window(
        self,
        *,
        block: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[str]:
        """
        Prefer line-aware splitting before falling back to character window.
        """
        text = block.strip()
        if not text:
            return []

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > 1:
            chunks: list[str] = []
            current = ""

            for line in lines:
                candidate = f"{current}\n{line}".strip() if current else line
                if len(candidate) <= chunk_size:
                    current = candidate
                else:
                    if current:
                        chunks.append(current.strip())
                    if len(line) <= chunk_size:
                        current = line
                    else:
                        chunks.extend(
                            self._split_large_block_window_only(
                                block=line,
                                chunk_size=chunk_size,
                                chunk_overlap=chunk_overlap,
                            )
                        )
                        current = ""

            if current.strip():
                chunks.append(current.strip())

            return [chunk for chunk in chunks if chunk.strip()]

        return self._split_large_block_window_only(
            block=text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def _split_large_block_window_only(
        self,
        *,
        block: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[str]:
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