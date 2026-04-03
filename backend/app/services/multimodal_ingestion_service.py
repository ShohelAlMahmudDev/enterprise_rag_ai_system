
# import logging
# from pathlib import Path

# from app.services.embedding_service import EmbeddingService
# from app.services.vision_service import VisionService
# from app.vector_store.faiss_store import FAISSVectorStore

# logger = logging.getLogger(__name__)

# SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


# class MultimodalIngestionService:
#     """
#     Turns image-only content into text descriptions, chunks it, embeds it, and
#     stores it in the same FAISS index used for normal RAG.
#     """

#     def __init__(self) -> None:
#         self.embedder = EmbeddingService()
#         self.vision = VisionService()
#         self.store = FAISSVectorStore(dimension=self.embedder.dimension)

#     def ingest_image(
#         self,
#         image_path: str | Path,
#         *,
#         document_id: str,
#         version: int,
#         logical_name: str,
#         filename: str,
#         active: bool = True,
#     ) -> int:
#         path = Path(image_path)
#         if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
#             raise ValueError(f"Unsupported image extension: {path.suffix}")

#         description = self.vision.describe_image(path, filename_hint=filename)
#         chunks = self.embedder.chunk_text(description)
#         vectors = self.embedder.embed(chunks)

#         metadata: list[dict] = []
#         for chunk_id, chunk in enumerate(chunks, start=1):
#             metadata.append(
#                 {
#                     "document_id": document_id,
#                     "version": version,
#                     "logical_name": logical_name,
#                     "filename": filename,
#                     "chunk_id": chunk_id,
#                     "text": chunk,
#                     "chunk": chunk,
#                     "active": active,
#                     "modality": "image",
#                     "vision_description": True,
#                 }
#             )

#         self.store.add(vectors, metadata)
#         logger.info(
#             "Indexed %s multimodal chunks for image document %s version %s",
#             len(metadata),
#             document_id,
#             version,
#         )
#         return len(metadata)


import logging
from pathlib import Path

from app.services.embedding_service import EmbeddingService
from app.services.vision_service import VisionService
from app.vector_store.faiss_store import FAISSVectorStore

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


class MultimodalIngestionService:
    """
    Turns image-only content into text descriptions, chunks it, embeds it, and
    stores it in the same FAISS index used for normal RAG.
    """

    def __init__(self) -> None:
        self.embedder = EmbeddingService()
        self.vision = VisionService()
        self.store = FAISSVectorStore(dimension=self.embedder.dimension)

    def ingest_image(
        self,
        image_path: str | Path,
        *,
        document_id: str,
        version_id: str, 
        version: int,
        logical_name: str,
        filename: str,
        active: bool = True,
        image_type: str = "unknown",
        ) -> int:
        path = Path(image_path)
        if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image extension: {path.suffix}")

        description = self.vision.describe_image(
            path,
            filename_hint=filename,
        )

        if not description.strip():
            raise ValueError("Vision model returned an empty description for the image.")

        chunks = self.embedder.chunk_text(description)
        if not chunks:
            raise ValueError("Image description produced no usable chunks.")

        vectors = self.embedder.embed(chunks)

        metadata: list[dict] = []
        for chunk_id, chunk in enumerate(chunks, start=1):
            metadata.append(
                {
                    "document_id": document_id,
                    "version_id": version_id,   # ✅ consistent with text docs
                    "version": version,
                    "logical_name": logical_name,
                    "filename": filename,
                    "chunk_id": chunk_id,
                    "text": chunk,
                    "chunk": chunk,
                    "active": active,
                    "modality": "image",
                    "vision_description": True,
                    "image_type": image_type,
                    "file_type": path.suffix.lower(),
                    "type": "image_description",
                }
            )

        self.store.add(vectors, metadata)

        logger.info(
            "Indexed %s multimodal chunks for image document %s version %s (image_type=%s)",
            len(metadata),
            document_id,
            version,
            image_type,
        )
        return len(metadata)