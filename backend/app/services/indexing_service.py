from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.services.document_chunking_service import ChunkRecord, DocumentChunkingService
from app.services.embedding_service import EmbeddingService
from app.services.faiss_store import FAISSVectorStore

logger = logging.getLogger(__name__)


class IndexingService:
    """
    High-level indexing service for enterprise RAG.

    Responsibilities:
    - parse and chunk supported files
    - enrich chunk metadata
    - generate embeddings
    - persist vectors and metadata into FAISS

    This service is intentionally focused on vector indexing only.
    DB persistence of documents/versions can be layered on top later.
    """

    def __init__(
        self,
        *,
        embedding_service: EmbeddingService | None = None,
        chunking_service: DocumentChunkingService | None = None,
        vector_store: FAISSVectorStore | None = None,
    ) -> None:
        self.embedding_service = embedding_service or EmbeddingService()
        self.chunking_service = chunking_service or DocumentChunkingService()
        self.vector_store = vector_store or FAISSVectorStore(
            dimension=self.embedding_service.dimension
        )

    def index_file(
        self,
        file_path: str | Path,
        *,
        document_id: str | None = None,
        version_id: str | None = None,
        logical_name: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
        store_text_in_metadata: bool = True,
    ) -> dict[str, Any]:
        """
        Parse, chunk, embed, and index a file into FAISS.

        Returns a summary payload suitable for API responses or logs.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File does not exist: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"Path is not a file: {path}")

        logger.info(
            "Indexing file: %s | document_id=%s | version_id=%s | logical_name=%s",
            path.name,
            document_id,
            version_id,
            logical_name,
        )

        chunks = self.chunking_service.build_chunks_from_file(
            file_path=path,
            document_id=document_id,
            version_id=version_id,
            logical_name=logical_name,
            extra_metadata=extra_metadata,
        )

        if not chunks:
            logger.warning("No chunks produced for file: %s", path.name)
            return {
                "file_path": str(path),
                "filename": path.name,
                "document_id": document_id,
                "version_id": version_id,
                "logical_name": logical_name or path.stem,
                "file_type": path.suffix.lower(),
                "chunk_count": 0,
                "indexed_count": 0,
                "languages": [],
                "status": "skipped",
                "reason": "No chunks produced from document.",
            }

        enriched_chunks = self._enrich_chunks_with_language(chunks)
        texts, metadatas = self.chunking_service.to_vector_store_payload(enriched_chunks)

        embeddings = self.embedding_service.embed(texts)

        self.vector_store.add_texts_with_embeddings(
            texts=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            store_text_in_metadata=store_text_in_metadata,
        )

        languages = sorted(
            {
                chunk.metadata.get("language", "unknown")
                for chunk in enriched_chunks
                if chunk.metadata.get("language")
            }
        )

        result = {
            "file_path": str(path),
            "filename": path.name,
            "document_id": document_id,
            "version_id": version_id,
            "logical_name": logical_name or path.stem,
            "file_type": path.suffix.lower(),
            "chunk_count": len(chunks),
            "indexed_count": len(texts),
            "languages": languages,
            "status": "indexed",
        }

        logger.info(
            "Indexed file successfully: %s | indexed_count=%s",
            path.name,
            len(texts),
        )

        return result

    def index_files(
        self,
        file_paths: list[str | Path],
        *,
        logical_name: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
        continue_on_error: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Index multiple files in sequence.

        Notes:
        - document_id/version_id are not auto-generated here because in a real
          enterprise flow these usually come from the DB/service layer.
        - use extra_metadata for shared tagging if needed.
        """
        results: list[dict[str, Any]] = []

        for file_path in file_paths:
            path = Path(file_path)

            try:
                result = self.index_file(
                    file_path=path,
                    logical_name=logical_name,
                    extra_metadata=extra_metadata,
                )
                results.append(result)

            except Exception as exc:
                logger.exception("Failed to index file: %s", path)

                error_result = {
                    "file_path": str(path),
                    "filename": path.name,
                    "document_id": None,
                    "version_id": None,
                    "logical_name": logical_name or path.stem,
                    "file_type": path.suffix.lower(),
                    "chunk_count": 0,
                    "indexed_count": 0,
                    "languages": [],
                    "status": "error",
                    "error": str(exc),
                }

                if continue_on_error:
                    results.append(error_result)
                else:
                    raise

        return results

    def replace_document_version(
        self,
        file_path: str | Path,
        *,
        document_id: str,
        version_id: str,
        logical_name: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
        delete_existing_for_document: bool = False,
        delete_existing_for_version: bool = True,
        store_text_in_metadata: bool = True,
    ) -> dict[str, Any]:
        """
        Replace existing indexed entries for a document/version and then index the new file.

        Typical usage:
        - delete_existing_for_version=True for re-indexing the same version
        - delete_existing_for_document=True if you want only one active indexed version
          inside FAISS at a time and handle versioning externally
        """
        if not document_id:
            raise ValueError("document_id is required for replace_document_version.")
        if not version_id:
            raise ValueError("version_id is required for replace_document_version.")

        deleted_count = 0

        if delete_existing_for_document:
            deleted_count += self.vector_store.delete_by_filter({"document_id": document_id})

        elif delete_existing_for_version:
            deleted_count += self.vector_store.delete_by_filter(
                {
                    "document_id": document_id,
                    "version_id": version_id,
                }
            )

        result = self.index_file(
            file_path=file_path,
            document_id=document_id,
            version_id=version_id,
            logical_name=logical_name,
            extra_metadata=extra_metadata,
            store_text_in_metadata=store_text_in_metadata,
        )
        result["deleted_before_index"] = deleted_count
        return result

    def search_similar(
        self,
        query_text: str,
        *,
        k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Convenience wrapper for vector search from raw text query.
        """
        cleaned_query = (query_text or "").strip()
        if not cleaned_query:
            return []

        embedding = self.embedding_service.embed([cleaned_query])[0]
        return self.vector_store.search(
            embedding=embedding,
            k=k,
            filters=filters,
        )

    def _enrich_chunks_with_language(self, chunks: list[ChunkRecord]) -> list[ChunkRecord]:
        """
        Detect language per chunk and inject it into metadata.
        """
        enriched: list[ChunkRecord] = []

        for chunk in chunks:
            metadata = dict(chunk.metadata)
            if "language" not in metadata:
                metadata["language"] = self.embedding_service.detect_language(chunk.text)

            enriched.append(
                ChunkRecord(
                    text=chunk.text,
                    metadata=metadata,
                )
            )

        return enriched