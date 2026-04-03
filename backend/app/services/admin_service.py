# from sqlalchemy import select

# from app.db.database import SessionLocal
# from app.db.models import Document, DocumentVersion
# from app.parsers.document_parser import parse_document
# from app.services.embedding_service import EmbeddingService
# from app.vector_store.faiss_store import FAISSVectorStore


# class AdminService:
#     def __init__(self) -> None:
#         self.embedder = EmbeddingService()
#         self.store = FAISSVectorStore(dimension=self.embedder.dimension)

#     def rebuild_index(self) -> dict:
#         with SessionLocal() as db:
#             self.store.reset()
#             docs = {doc.id: doc for doc in db.scalars(select(Document).where(Document.is_deleted.is_(False))).all()}
#             versions = db.scalars(select(DocumentVersion).where(DocumentVersion.status == 'active')).all()
#             indexed = 0
#             for version in versions:
#                 if version.document_id not in docs:
#                     continue
#                 text = parse_document(version.file_path)
#                 chunks = self.embedder.chunk_text(text)
#                 embeddings = self.embedder.embed(chunks)
#                 self.store.add(
#                     embeddings,
#                     [
#                         {
#                             'document_id': version.document_id,
#                             'version_id': version.id,
#                             'logical_name': docs[version.document_id].logical_name,
#                             'filename': version.filename,
#                             'language': version.language,
#                             'chunk_id': idx,
#                             'chunk': chunk,
#                             'active': True,
#                         }
#                         for idx, chunk in enumerate(chunks, start=1)
#                     ],
#                 )
#                 indexed += len(chunks)
#             return {'message': 'Vector index rebuilt successfully.', 'chunks_indexed': indexed}


# from sqlalchemy import select
# from sqlalchemy.orm import selectinload

# from app.db.database import SessionLocal
# from app.db.models import Document, DocumentVersion
# from app.parsers.document_parser import parse_document
# from app.services.embedding_service import EmbeddingService
# from app.services.multimodal_ingestion_service import MultimodalIngestionService
# from app.utils.image_utils import is_image_file, validate_image_file, classify_image_type
# from app.vector_store.faiss_store import FAISSVectorStore
# from app.config import settings


# class AdminService:
#     def __init__(self) -> None:
#         self.embedder = EmbeddingService()
#         self.store = FAISSVectorStore(dimension=self.embedder.dimension)
#         self.multimodal = (
#             MultimodalIngestionService()
#             if settings.ENABLE_MULTIMODAL_INGESTION
#             else None
#         )

#     def rebuild_index(self) -> dict:
#         self.store.reset()

#         indexed_chunks = 0
#         indexed_versions = 0

#         with SessionLocal() as db:
#             stmt = (
#                 select(DocumentVersion)
#                 .join(Document, Document.id == DocumentVersion.document_id)
#                 .options(selectinload(DocumentVersion.document))
#                 .where(Document.is_deleted == False)  # noqa: E712
#                 .where(DocumentVersion.status == "active")
#             )
#             versions = db.scalars(stmt).all()

#             for version in versions:
#                 file_path = version.file_path
#                 filename = version.filename or ""
#                 logical_name = version.document.logical_name if version.document else "Document"

#                 if is_image_file(file_path):
#                     if not self.multimodal:
#                         continue

#                     validate_image_file(file_path)
#                     image_type = classify_image_type(file_path)

#                     chunk_count = self.multimodal.ingest_image(
#                         file_path,
#                         document_id=version.document_id,
#                         version_id=version.id,
#                         version=version.version,
#                         logical_name=logical_name,
#                         filename=filename,
#                         active=True,
#                         image_type=image_type,
#                     )
#                     indexed_chunks += chunk_count
#                     indexed_versions += 1
#                     continue

#                 parsed = parse_document(file_path)
#                 if not parsed.text.strip():
#                     continue

#                 chunks_with_metadata = self._build_chunks_from_parsed_document(parsed)
#                 if not chunks_with_metadata:
#                     continue

#                 chunk_texts = [item["text"] for item in chunks_with_metadata]
#                 embeddings = self.embedder.embed(chunk_texts)

#                 payload = []
#                 for idx, item in enumerate(chunks_with_metadata, start=1):
#                     payload.append(
#                         {
#                             "document_id": version.document_id,
#                             "version_id": version.id,
#                             "logical_name": logical_name,
#                             "filename": filename,
#                             "language": version.language,
#                             "chunk_id": idx,
#                             "chunk": item["text"],
#                             "text": item["text"],
#                             "active": True,
#                             "file_type": parsed.file_type,
#                             **item["metadata"],
#                         }
#                     )

#                 self.store.add(embeddings, payload)
#                 indexed_chunks += len(payload)
#                 indexed_versions += 1

#         return {
#             "message": "Index rebuilt successfully.",
#             "indexed_versions": indexed_versions,
#             "indexed_chunks": indexed_chunks,
#         }

#     def _build_chunks_from_parsed_document(self, parsed) -> list[dict]:
#         output: list[dict] = []

#         for section in parsed.sections:
#             section_text = (section.text or "").strip()
#             if not section_text:
#                 continue

#             chunks = self.embedder.chunk_text(section_text)
#             for chunk in chunks:
#                 clean_chunk = chunk.strip()
#                 if not clean_chunk:
#                     continue

#                 output.append(
#                     {
#                         "text": clean_chunk,
#                         "metadata": dict(section.metadata),
#                     }
#                 )

#         return output


import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import Document, DocumentVersion
from app.parsers.document_parser import ParsedDocument, parse_document
from app.services.embedding_service import EmbeddingService
from app.services.multimodal_ingestion_service import MultimodalIngestionService
from app.utils.image_utils import classify_image_type, is_image_file, validate_image_file
from app.vector_store.faiss_store import FAISSVectorStore

logger = logging.getLogger(__name__)


class AdminService:
    def __init__(self) -> None:
        self.embedder = EmbeddingService()
        self.store = FAISSVectorStore(dimension=self.embedder.dimension)
        self.multimodal = (
            MultimodalIngestionService()
            if settings.ENABLE_MULTIMODAL_INGESTION
            else None
        )

    def rebuild_index(self) -> dict:
        self.store.reset()

        indexed_chunks = 0
        indexed_versions = 0
        skipped_versions = 0

        with SessionLocal() as db:
            stmt = (
                select(DocumentVersion)
                .join(Document, Document.id == DocumentVersion.document_id)
                .options(selectinload(DocumentVersion.document))
                .where(Document.is_deleted == False)  # noqa: E712
                .where(DocumentVersion.status == "active")
            )
            versions = db.scalars(stmt).all()

            logger.info("Starting full index rebuild for %s active versions", len(versions))

            for version in versions:
                try:
                    file_path = version.file_path
                    filename = version.filename or ""
                    logical_name = (
                        version.document.logical_name if version.document else "Document"
                    )

                    if not file_path or not Path(file_path).exists():
                        logger.warning(
                            "Skipping version %s because file is missing: %s",
                            version.id,
                            file_path,
                        )
                        skipped_versions += 1
                        continue

                    logger.info(
                        "Re-indexing version %s | file=%s | logical_name=%s",
                        version.id,
                        filename,
                        logical_name,
                    )

                    if is_image_file(file_path):
                        if not self.multimodal:
                            logger.warning(
                                "Skipping image version %s because multimodal ingestion is disabled",
                                version.id,
                            )
                            skipped_versions += 1
                            continue

                        validate_image_file(file_path)
                        image_type = classify_image_type(file_path)

                        chunk_count = self.multimodal.ingest_image(
                            file_path,
                            document_id=version.document_id,
                            version_id=version.id,
                            version=version.version,
                            logical_name=logical_name,
                            filename=filename,
                            active=True,
                            image_type=image_type,
                        )
                        indexed_chunks += chunk_count
                        indexed_versions += 1
                        continue

                    parsed = parse_document(file_path)
                    if not parsed.text.strip():
                        logger.warning(
                            "Skipping version %s because parsed text is empty",
                            version.id,
                        )
                        skipped_versions += 1
                        continue

                    chunks_with_metadata = self._build_chunks_from_parsed_document(parsed)
                    if not chunks_with_metadata:
                        logger.warning(
                            "Skipping version %s because no usable chunks were produced",
                            version.id,
                        )
                        skipped_versions += 1
                        continue

                    chunk_texts = [item["text"] for item in chunks_with_metadata]
                    embeddings = self.embedder.embed(chunk_texts)

                    payload = []
                    for idx, item in enumerate(chunks_with_metadata, start=1):
                        payload.append(
                            {
                                "document_id": version.document_id,
                                "version_id": version.id,
                                "logical_name": logical_name,
                                "filename": filename,
                                "language": version.language,
                                "chunk_id": idx,
                                "chunk": item["text"],
                                "text": item["text"],
                                "active": True,
                                "file_type": parsed.file_type,
                                **item["metadata"],
                            }
                        )

                    self.store.add(embeddings, payload)
                    indexed_chunks += len(payload)
                    indexed_versions += 1

                except Exception as exc:
                    logger.exception(
                        "Failed to rebuild index for version %s (%s): %s",
                        version.id,
                        version.filename,
                        exc,
                    )
                    skipped_versions += 1
                    continue

        logger.info(
            "Index rebuild completed | indexed_versions=%s | indexed_chunks=%s | skipped_versions=%s",
            indexed_versions,
            indexed_chunks,
            skipped_versions,
        )

        return {
            "message": "Index rebuilt successfully.",
            "indexed_versions": indexed_versions,
            "indexed_chunks": indexed_chunks,
            "skipped_versions": skipped_versions,
        }

    def _build_chunks_from_parsed_document(self, parsed: ParsedDocument) -> list[dict]:
        output: list[dict] = []

        for section in parsed.sections:
            section_text = (section.text or "").strip()
            if not section_text:
                continue

            chunks = self.embedder.chunk_text(section_text)
            for chunk in chunks:
                clean_chunk = chunk.strip()
                if not clean_chunk:
                    continue

                output.append(
                    {
                        "text": clean_chunk,
                        "metadata": dict(section.metadata),
                    }
                )

        return output