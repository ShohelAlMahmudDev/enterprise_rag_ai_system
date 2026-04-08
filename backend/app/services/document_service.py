
# # import logging
# # import os
# # from pathlib import Path
# # from uuid import uuid4

# # from fastapi import UploadFile
# # from sqlalchemy import select
# # from sqlalchemy.orm import selectinload

# # from app.config import settings
# # from app.db.database import SessionLocal
# # from app.db.models import Document, DocumentVersion
# # from app.parsers.document_parser import ParsedDocument, parse_document
# # from app.schemas.document import DocumentOut, DocumentVersionOut
# # from app.services.embedding_service import EmbeddingService
# # from app.services.multimodal_ingestion_service import MultimodalIngestionService
# # from app.utils.file_utils import safe_join_upload, validate_extension, validate_file_size
# # from app.utils.image_utils import is_image_file
# # from app.vector_store.faiss_store import FAISSVectorStore
# # from app.utils.image_utils import (
# #     is_image_file,
# #     validate_image_file,
# #     classify_image_type,
# #     should_apply_ocr,
# # )

# # logger = logging.getLogger(__name__)


# # class DocumentService:
# #     def __init__(self) -> None:
# #         self.embedder = EmbeddingService()
# #         self.store = FAISSVectorStore(dimension=self.embedder.dimension)
# #         self.multimodal = (
# #             MultimodalIngestionService()
# #             if settings.ENABLE_MULTIMODAL_INGESTION
# #             else None
# #         )

# #     async def create_document(
# #         self,
# #         file: UploadFile,
# #         logical_name: str | None = None,
# #         notes: str | None = None,
# #     ):
# #         resolved_name = (logical_name or "").strip() or Path(file.filename or "document").stem

# #         with SessionLocal() as db:
# #             document = Document(
# #                 logical_name=resolved_name,
# #                 current_version=1,
# #                 is_deleted=False,
# #             )
# #             db.add(document)
# #             db.flush()

# #             version = await self._create_version_record(
# #                 db=db,
# #                 document=document,
# #                 file=file,
# #                 version_number=1,
# #                 notes=notes,
# #             )

# #             db.commit()
# #             db.refresh(document)
# #             db.refresh(version)

# #             return self._map_document(document, version), self._map_version(version)

# #     async def create_new_version(
# #         self,
# #         document_id: str,
# #         file: UploadFile,
# #         notes: str | None = None,
# #     ):
# #         with SessionLocal() as db:
# #             document = db.get(Document, document_id)
# #             if not document or document.is_deleted:
# #                 raise ValueError("Document not found.")

# #             for version in document.versions:
# #                 if version.status == "active":
# #                     version.status = "superseded"

# #             new_version_number = document.current_version + 1

# #             version = await self._create_version_record(
# #                 db=db,
# #                 document=document,
# #                 file=file,
# #                 version_number=new_version_number,
# #                 notes=notes,
# #             )

# #             document.current_version = new_version_number
# #             db.commit()
# #             db.refresh(document)
# #             db.refresh(version)

# #             return self._map_document(document, version), self._map_version(version)

# #     def list_documents(self) -> list[DocumentOut]:
# #         with SessionLocal() as db:
# #             stmt = (
# #                 select(Document)
# #                 .options(selectinload(Document.versions))
# #                 .order_by(Document.updated_at.desc())
# #             )
# #             docs = db.scalars(stmt).all()
# #             return [self._map_document(doc, self._get_latest_version(doc)) for doc in docs]

# #     def get_versions(self, document_id: str) -> list[DocumentVersionOut]:
# #         with SessionLocal() as db:
# #             stmt = (
# #                 select(DocumentVersion)
# #                 .where(DocumentVersion.document_id == document_id)
# #                 .order_by(DocumentVersion.version.desc())
# #             )
# #             versions = db.scalars(stmt).all()
# #             return [self._map_version(item) for item in versions]

# #     def soft_delete_document(self, document_id: str) -> bool:
# #         with SessionLocal() as db:
# #             document = db.get(Document, document_id)
# #             if not document:
# #                 return False

# #             document.is_deleted = True
# #             for version in document.versions:
# #                 if version.status == "active":
# #                     version.status = "deleted"

# #             db.commit()
# #             return True

# #     async def _create_version_record(
# #         self,
# #         db,
# #         document: Document,
# #         file: UploadFile,
# #         version_number: int,
# #         notes: str | None,
# #     ):
# #         ext = validate_extension(file.filename or "")
# #         content = await file.read()
# #         validate_file_size(len(content))

# #         version_id = str(uuid4())
# #         # target_name = f"{version_id}_{os.path.basename(file.filename or 'document')}"
# #         # target_path = safe_join_upload(target_name)
# #         target_path = safe_join_upload(file.filename or "document")
# #         target_name = Path(target_path).name
# #         with open(target_path, "wb") as handle:
# #             handle.write(content)

# #         if is_image_file(target_path):
# #             if not self.multimodal:
# #                 Path(target_path).unlink(missing_ok=True)
# #                 raise ValueError(
# #                     "Image upload is enabled only when multimodal ingestion is configured."
# #                 )

# #             validate_image_file(target_path)
# #             image_type = classify_image_type(target_path)

# #             chunk_count = self.multimodal.ingest_image(
# #                 target_path,
# #                 document_id=document.id,
# #                 version_id=version_id,
# #                 version=version_number,
# #                 logical_name=document.logical_name,
# #                 filename=file.filename or target_name,
# #                 active=True,
# #                 image_type=image_type,
# #             )
# #             language = "vision"

# #         else:
# #             parsed = parse_document(target_path)

# #             if not parsed.text.strip():
# #                 Path(target_path).unlink(missing_ok=True)
# #                 raise ValueError("Document contains no extractable text.")

# #             language = self.embedder.detect_language(parsed.text)

# #             chunks_with_metadata = self._build_chunks_from_parsed_document(parsed)

# #             if not chunks_with_metadata:
# #                 Path(target_path).unlink(missing_ok=True)
# #                 raise ValueError("Document parsing produced no usable chunks.")

# #             chunk_texts = [item["text"] for item in chunks_with_metadata]
# #             embeddings = self.embedder.embed(chunk_texts)

# #             faiss_payload = []
# #             for idx, item in enumerate(chunks_with_metadata, start=1):
# #                 payload = {
# #                     "document_id": document.id,
# #                     "version_id": version_id,
# #                     "logical_name": document.logical_name,
# #                     "filename": file.filename,
# #                     "language": language,
# #                     "chunk_id": idx,
# #                     "chunk": item["text"],
# #                     "text": item["text"],
# #                     "active": True,
# #                     "file_type": parsed.file_type,
# #                     **item["metadata"],
# #                 }
# #                 faiss_payload.append(payload)

# #             self.store.add(embeddings, faiss_payload)
# #             chunk_count = len(faiss_payload)

# #         version = DocumentVersion(
# #             id=version_id,
# #             document_id=document.id,
# #             version=version_number,
# #             filename=file.filename or target_name,
# #             file_type=ext,
# #             language=language,
# #             chunk_count=chunk_count,
# #             file_path=target_path,
# #             status="active",
# #             notes=notes,
# #         )
# #         db.add(version)

# #         logger.info(
# #             "Indexed %s chunks for document %s version %s",
# #             chunk_count,
# #             document.id,
# #             version_number,
# #         )

# #         return version

# #     def _build_chunks_from_parsed_document(self, parsed: ParsedDocument) -> list[dict]:
# #         """
# #         Build chunk texts while preserving section metadata.
# #         """
# #         output: list[dict] = []

# #         for section in parsed.sections:
# #             section_text = (section.text or "").strip()
# #             if not section_text:
# #                 continue

# #             chunks = self.embedder.chunk_text(section_text)
# #             for chunk in chunks:
# #                 clean_chunk = chunk.strip()
# #                 if not clean_chunk:
# #                     continue

# #                 output.append(
# #                     {
# #                         "text": clean_chunk,
# #                         "metadata": dict(section.metadata),
# #                     }
# #                 )

# #         return output

# #     def _get_latest_version(self, doc: Document) -> DocumentVersion | None:
# #         if not getattr(doc, "versions", None):
# #             return None
# #         return max(doc.versions, key=lambda item: item.version, default=None)

# #     def _map_document(
# #         self,
# #         doc: Document,
# #         version: DocumentVersion | None = None,
# #     ) -> DocumentOut:
# #         version = version or self._get_latest_version(doc)

# #         return DocumentOut(
# #             id=doc.id,
# #             logical_name=doc.logical_name,
# #             current_version=doc.current_version,
# #             is_deleted=doc.is_deleted,
# #             created_at=doc.created_at.isoformat(),
# #             updated_at=doc.updated_at.isoformat(),
# #             filename=version.filename if version else None,
# #             file_type=version.file_type if version else None,
# #             language=version.language if version else None,
# #             chunk_count=version.chunk_count if version else None,
# #             status=version.status if version else ("deleted" if doc.is_deleted else "unknown"),
# #             uploaded_at=version.created_at.isoformat() if version else doc.created_at.isoformat(),
# #             active=(not doc.is_deleted) and (version.status == "active" if version else True),
# #         )

# #     def _map_version(self, version: DocumentVersion) -> DocumentVersionOut:
# #         return DocumentVersionOut(
# #             version_id=version.id,
# #             document_id=version.document_id,
# #             version=version.version,
# #             filename=version.filename,
# #             file_type=version.file_type,
# #             language=version.language,
# #             chunk_count=version.chunk_count,
# #             status=version.status,
# #             created_at=version.created_at.isoformat(),
# #             notes=version.notes,
# #         )

# import logging
# from pathlib import Path
# from uuid import uuid4

# from fastapi import UploadFile
# from sqlalchemy import select
# from sqlalchemy.orm import selectinload

# from app.config import settings
# from app.db.database import SessionLocal
# from app.db.models import Document, DocumentVersion
# from app.schemas.document import DocumentOut, DocumentVersionOut
# from app.services.document_chunking_service import DocumentChunkingService
# from app.services.embedding_service import EmbeddingService
# from app.services.multimodal_ingestion_service import MultimodalIngestionService
# from app.utils.file_utils import safe_join_upload, validate_extension, validate_file_size
# from app.utils.image_utils import classify_image_type, is_image_file, validate_image_file
# from app.vector_store.faiss_store import FAISSVectorStore

# logger = logging.getLogger(__name__)


# class DocumentService:
#     def __init__(self) -> None:
#         self.embedder = EmbeddingService()
#         self.store = FAISSVectorStore(dimension=self.embedder.dimension)
#         self.chunking_service = DocumentChunkingService(
#             default_chunk_size=settings.DEFAULT_CHUNK_SIZE,
#             default_chunk_overlap=settings.DEFAULT_CHUNK_OVERLAP,
#         )
#         self.multimodal = (
#             MultimodalIngestionService()
#             if settings.ENABLE_MULTIMODAL_INGESTION
#             else None
#         )

#     async def create_document(
#         self,
#         file: UploadFile,
#         logical_name: str | None = None,
#         notes: str | None = None,
#     ):
#         resolved_name = (logical_name or "").strip() or Path(file.filename or "document").stem

#         with SessionLocal() as db:
#             document = Document(
#                 logical_name=resolved_name,
#                 current_version=1,
#                 is_deleted=False,
#             )
#             db.add(document)
#             db.flush()

#             version = await self._create_version_record(
#                 db=db,
#                 document=document,
#                 file=file,
#                 version_number=1,
#                 notes=notes,
#             )

#             db.commit()
#             db.refresh(document)
#             db.refresh(version)

#             return self._map_document(document, version), self._map_version(version)

#     async def create_new_version(
#         self,
#         document_id: str,
#         file: UploadFile,
#         notes: str | None = None,
#     ):
#         with SessionLocal() as db:
#             document = db.get(Document, document_id)
#             if not document or document.is_deleted:
#                 raise ValueError("Document not found.")

#             for version in document.versions:
#                 if version.status == "active":
#                     version.status = "superseded"

#             new_version_number = document.current_version + 1

#             version = await self._create_version_record(
#                 db=db,
#                 document=document,
#                 file=file,
#                 version_number=new_version_number,
#                 notes=notes,
#             )

#             document.current_version = new_version_number
#             db.commit()
#             db.refresh(document)
#             db.refresh(version)

#             return self._map_document(document, version), self._map_version(version)

#     def list_documents(self) -> list[DocumentOut]:
#         with SessionLocal() as db:
#             stmt = (
#                 select(Document)
#                 .options(selectinload(Document.versions))
#                 .order_by(Document.updated_at.desc())
#             )
#             docs = db.scalars(stmt).all()
#             return [self._map_document(doc, self._get_latest_version(doc)) for doc in docs]

#     def get_versions(self, document_id: str) -> list[DocumentVersionOut]:
#         with SessionLocal() as db:
#             stmt = (
#                 select(DocumentVersion)
#                 .where(DocumentVersion.document_id == document_id)
#                 .order_by(DocumentVersion.version.desc())
#             )
#             versions = db.scalars(stmt).all()
#             return [self._map_version(item) for item in versions]

#     def soft_delete_document(self, document_id: str) -> bool:
#         with SessionLocal() as db:
#             document = db.get(Document, document_id)
#             if not document:
#                 return False

#             document.is_deleted = True
#             for version in document.versions:
#                 if version.status == "active":
#                     version.status = "deleted"

#             db.commit()
#             return True

#     async def _create_version_record(
#         self,
#         db,
#         document: Document,
#         file: UploadFile,
#         version_number: int,
#         notes: str | None,
#     ):
#         ext = validate_extension(file.filename or "")
#         content = await file.read()
#         validate_file_size(len(content))

#         version_id = str(uuid4())
#         original_filename = file.filename or "document"
#         target_filename = f"{version_id}_{original_filename}"
#         target_path = safe_join_upload(target_filename, unique=False)
#         target_name = Path(target_path).name

#         with open(target_path, "wb") as handle:
#             handle.write(content)

#         if is_image_file(target_path):
#             if not self.multimodal:
#                 Path(target_path).unlink(missing_ok=True)
#                 raise ValueError(
#                     "Image upload is enabled only when multimodal ingestion is configured."
#                 )

#             validate_image_file(target_path)
#             image_type = classify_image_type(target_path)

#             chunk_count = self.multimodal.ingest_image(
#                 target_path,
#                 document_id=document.id,
#                 version_id=version_id,
#                 version=version_number,
#                 logical_name=document.logical_name,
#                 filename=original_filename,
#                 active=True,
#                 image_type=image_type,
#             )
#             language = "vision"

#         else:
#             chunk_records = self.chunking_service.build_chunks_from_file(
#                 file_path=target_path,
#                 document_id=document.id,
#                 version_id=version_id,
#                 logical_name=document.logical_name,
#                 extra_metadata={
#                     "active": True,
#                     "version": version_number,
#                 },
#             )

#             if not chunk_records:
#                 Path(target_path).unlink(missing_ok=True)
#                 raise ValueError("Document parsing produced no usable chunks.")

#             chunk_texts = [item.text for item in chunk_records]
#             combined_text = "\n\n".join(chunk_texts).strip()

#             if not combined_text:
#                 Path(target_path).unlink(missing_ok=True)
#                 raise ValueError("Document contains no extractable text.")

#             language = self.embedder.detect_language(combined_text)
#             embeddings = self.embedder.embed(chunk_texts)

#             faiss_payload: list[dict] = []
#             for item in chunk_records:
#                 payload = {
#                     "document_id": document.id,
#                     "version_id": version_id,
#                     "logical_name": document.logical_name,
#                     "filename": original_filename,
#                     "language": language,
#                     "chunk": item.text,
#                     "text": item.text,
#                     "active": True,
#                     "file_type": ext,
#                     **item.metadata,
#                 }
#                 faiss_payload.append(payload)

#             self.store.add(embeddings, faiss_payload)
#             chunk_count = len(faiss_payload)

#         version = DocumentVersion(
#             id=version_id,
#             document_id=document.id,
#             version=version_number,
#             filename=original_filename,
#             file_type=ext,
#             language=language,
#             chunk_count=chunk_count,
#             file_path=target_path,
#             status="active",
#             notes=notes,
#         )
#         db.add(version)

#         logger.info(
#             "Indexed %s chunks for document %s version %s",
#             chunk_count,
#             document.id,
#             version_number,
#         )

#         return version

#     def _get_latest_version(self, doc: Document) -> DocumentVersion | None:
#         if not getattr(doc, "versions", None):
#             return None
#         return max(doc.versions, key=lambda item: item.version, default=None)

#     def _map_document(
#         self,
#         doc: Document,
#         version: DocumentVersion | None = None,
#     ) -> DocumentOut:
#         version = version or self._get_latest_version(doc)

#         return DocumentOut(
#             id=doc.id,
#             logical_name=doc.logical_name,
#             current_version=doc.current_version,
#             is_deleted=doc.is_deleted,
#             created_at=doc.created_at.isoformat(),
#             updated_at=doc.updated_at.isoformat(),
#             filename=version.filename if version else None,
#             file_type=version.file_type if version else None,
#             language=version.language if version else None,
#             chunk_count=version.chunk_count if version else None,
#             status=version.status if version else ("deleted" if doc.is_deleted else "unknown"),
#             uploaded_at=version.created_at.isoformat() if version else doc.created_at.isoformat(),
#             active=(not doc.is_deleted) and (version.status == "active" if version else True),
#         )

#     def _map_version(self, version: DocumentVersion) -> DocumentVersionOut:
#         return DocumentVersionOut(
#             version_id=version.id,
#             document_id=version.document_id,
#             version=version.version,
#             filename=version.filename,
#             file_type=version.file_type,
#             language=version.language,
#             chunk_count=version.chunk_count,
#             status=version.status,
#             created_at=version.created_at.isoformat(),
#             notes=version.notes,
#         )
import logging
import os
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import Document, DocumentVersion
from app.parsers.document_parser import ParsedDocument, parse_document
from app.schemas.document import DocumentOut, DocumentVersionOut
from app.services.embedding_service import EmbeddingService
from app.services.multimodal_ingestion_service import MultimodalIngestionService
from app.services.bm25_service import BM25Service
from app.services.structured_index_service import StructuredIndexService
from app.utils.file_utils import safe_join_upload, validate_extension, validate_file_size
from app.utils.image_utils import is_image_file, validate_image_file, classify_image_type
from app.vector_store.faiss_store import FAISSVectorStore

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self) -> None:
        self.embedder = EmbeddingService()
        self.store = FAISSVectorStore(dimension=self.embedder.dimension)
        self.bm25 = BM25Service()
        self.structured_index = StructuredIndexService()

        self.multimodal = (
            MultimodalIngestionService()
            if settings.ENABLE_MULTIMODAL_INGESTION
            else None
        )

    async def create_document(
        self,
        file: UploadFile,
        logical_name: str | None = None,
        notes: str | None = None,
    ):
        resolved_name = (logical_name or "").strip() or Path(file.filename or "document").stem

        with SessionLocal() as db:
            document = Document(
                logical_name=resolved_name,
                current_version=1,
                is_deleted=False,
            )
            db.add(document)
            db.flush()

            version = await self._create_version_record(
                db=db,
                document=document,
                file=file,
                version_number=1,
                notes=notes,
            )

            db.commit()
            db.refresh(document)
            db.refresh(version)

            return self._map_document(document, version), self._map_version(version)

    async def create_new_version(
        self,
        document_id: str,
        file: UploadFile,
        notes: str | None = None,
    ):
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if not document or document.is_deleted:
                raise ValueError("Document not found.")

            # 🔥 CLEAN OLD VERSIONS FROM BM25 + STRUCTURED INDEX
            for version in document.versions:
                if version.status == "active":
                    self._remove_version_from_indexes(version.id)
                    version.status = "superseded"

            new_version_number = document.current_version + 1

            version = await self._create_version_record(
                db=db,
                document=document,
                file=file,
                version_number=new_version_number,
                notes=notes,
            )

            document.current_version = new_version_number
            db.commit()
            db.refresh(document)
            db.refresh(version)

            return self._map_document(document, version), self._map_version(version)

    def list_documents(self) -> list[DocumentOut]:
        with SessionLocal() as db:
            stmt = (
                select(Document)
                .options(selectinload(Document.versions))
                .order_by(Document.updated_at.desc())
            )
            docs = db.scalars(stmt).all()
            return [self._map_document(doc, self._get_latest_version(doc)) for doc in docs]

    def get_versions(self, document_id: str) -> list[DocumentVersionOut]:
        with SessionLocal() as db:
            stmt = (
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.version.desc())
            )
            versions = db.scalars(stmt).all()
            return [self._map_version(item) for item in versions]

    def soft_delete_document(self, document_id: str) -> bool:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if not document:
                return False

            document.is_deleted = True

            for version in document.versions:
                if version.status == "active":
                    self._remove_version_from_indexes(version.id)
                    version.status = "deleted"

            db.commit()
            return True

    async def _create_version_record(
        self,
        db,
        document: Document,
        file: UploadFile,
        version_number: int,
        notes: str | None,
    ):
        ext = validate_extension(file.filename or "")
        content = await file.read()
        validate_file_size(len(content))

        version_id = str(uuid4())
        target_path = safe_join_upload(file.filename or "document")
        target_name = Path(target_path).name

        with open(target_path, "wb") as handle:
            handle.write(content)

        # ---------------- IMAGE PIPELINE ----------------
        if is_image_file(target_path):
            if not self.multimodal:
                Path(target_path).unlink(missing_ok=True)
                raise ValueError("Image upload requires multimodal ingestion.")

            validate_image_file(target_path)
            image_type = classify_image_type(target_path)

            chunk_count = self.multimodal.ingest_image(
                target_path,
                document_id=document.id,
                version_id=version_id,
                version=version_number,
                logical_name=document.logical_name,
                filename=file.filename or target_name,
                active=True,
                image_type=image_type,
            )

            language = "vision"

        # ---------------- DOCUMENT PIPELINE ----------------
        else:
            parsed = parse_document(target_path)

            if not parsed.text.strip():
                Path(target_path).unlink(missing_ok=True)
                raise ValueError("Document contains no extractable text.")

            language = self.embedder.detect_language(parsed.text)

            chunks_with_metadata = self._build_chunks_from_parsed_document(parsed)

            if not chunks_with_metadata:
                Path(target_path).unlink(missing_ok=True)
                raise ValueError("No usable chunks produced.")

            chunk_texts = [item["text"] for item in chunks_with_metadata]
            embeddings = self.embedder.embed(chunk_texts)

            faiss_payload = []
            for idx, item in enumerate(chunks_with_metadata, start=1):
                payload = {
                    "document_id": document.id,
                    "version_id": version_id,
                    "logical_name": document.logical_name,
                    "filename": file.filename,
                    "language": language,
                    "chunk_id": idx,
                    "chunk": item["text"],
                    "text": item["text"],
                    "active": True,
                    "file_type": parsed.file_type,
                    **item["metadata"],
                }
                faiss_payload.append(payload)

            # 🔥 FAISS
            self.store.add(embeddings, faiss_payload)

            # 🔥 BM25
            if settings.ENABLE_BM25_RETRIEVAL:
                self.bm25.add_documents(faiss_payload)

            # 🔥 STRUCTURED INDEX
            if settings.ENABLE_STRUCTURED_RETRIEVAL:
                structured_chunks = [
                    {
                        "text": item["text"],
                        "metadata": item,
                    }
                    for item in faiss_payload
                ]
                self.structured_index.add_records_from_chunks(structured_chunks)

            chunk_count = len(faiss_payload)

        # ---------------- SAVE VERSION ----------------
        version = DocumentVersion(
            id=version_id,
            document_id=document.id,
            version=version_number,
            filename=file.filename or target_name,
            file_type=ext,
            language=language,
            chunk_count=chunk_count,
            file_path=target_path,
            status="active",
            notes=notes,
        )
        db.add(version)

        logger.info(
            "Indexed %s chunks for document %s version %s",
            chunk_count,
            document.id,
            version_number,
        )

        return version

    def _remove_version_from_indexes(self, version_id: str) -> None:
        try:
            self.bm25.remove_by_version(version_id)
            self.structured_index.remove_by_version(version_id)
        except Exception as exc:
            logger.warning("Failed to clean indexes for version %s: %s", version_id, exc)

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

    def _get_latest_version(self, doc: Document) -> DocumentVersion | None:
        if not getattr(doc, "versions", None):
            return None
        return max(doc.versions, key=lambda item: item.version, default=None)

    def _map_document(
        self,
        doc: Document,
        version: DocumentVersion | None = None,
    ) -> DocumentOut:
        version = version or self._get_latest_version(doc)

        return DocumentOut(
            id=doc.id,
            logical_name=doc.logical_name,
            current_version=doc.current_version,
            is_deleted=doc.is_deleted,
            created_at=doc.created_at.isoformat(),
            updated_at=doc.updated_at.isoformat(),
            filename=version.filename if version else None,
            file_type=version.file_type if version else None,
            language=version.language if version else None,
            chunk_count=version.chunk_count if version else None,
            status=version.status if version else ("deleted" if doc.is_deleted else "unknown"),
            uploaded_at=version.created_at.isoformat() if version else doc.created_at.isoformat(),
            active=(not doc.is_deleted) and (version.status == "active" if version else True),
        )

    def _map_version(self, version: DocumentVersion) -> DocumentVersionOut:
        return DocumentVersionOut(
            version_id=version.id,
            document_id=version.document_id,
            version=version.version,
            filename=version.filename,
            file_type=version.file_type,
            language=version.language,
            chunk_count=version.chunk_count,
            status=version.status,
            created_at=version.created_at.isoformat(),
            notes=version.notes,
        )