import json
import logging
import os
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class FAISSVectorStore:
    """
    Lightweight FAISS-backed vector store with sidecar JSON metadata.

    Design:
    - vectors are stored in FAISS IndexFlatIP
    - metadata is stored in a JSON file alongside the index
    - embeddings are normalized for cosine-like similarity
    - search supports optional metadata filtering

    Expected metadata examples:
        {
            "text": "...optional raw chunk text...",
            "document_id": "doc123",
            "version_id": "ver5",
            "logical_name": "RaSTA Spec",
            "file_type": ".pdf",
            "page": 4,
            "chunk_id": "doc123_ver5_s4_c1"
        }
    """

    METADATA_VERSION = 2

    def __init__(self, dimension: int) -> None:
        if dimension <= 0:
            raise ValueError("FAISS vector dimension must be greater than 0.")

        self.dimension = dimension
        self.index_path = settings.VECTOR_INDEX_PATH
        self.meta_path = settings.VECTOR_META_PATH
        self.index: faiss.IndexFlatIP
        self.metadata: list[dict[str, Any]]

        self._load()

    def _load(self) -> None:
        index_exists = os.path.exists(self.index_path)
        meta_exists = os.path.exists(self.meta_path)

        if not index_exists or not meta_exists:
            self.index = faiss.IndexFlatIP(self.dimension)
            self.metadata = []
            return

        try:
            self.index = faiss.read_index(self.index_path)

            with open(self.meta_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)

            if isinstance(raw, dict) and "items" in raw:
                self.metadata = raw.get("items", [])
                stored_dimension = raw.get("dimension")
                if stored_dimension is not None and int(stored_dimension) != self.dimension:
                    raise ValueError(
                        f"FAISS metadata dimension mismatch. "
                        f"Expected {self.dimension}, found {stored_dimension}."
                    )
            elif isinstance(raw, list):
                # Backward compatibility with older metadata-only list format
                self.metadata = raw
            else:
                raise ValueError("Invalid FAISS metadata format.")

            if not isinstance(self.metadata, list):
                raise ValueError("FAISS metadata payload 'items' must be a list.")

            if self.index.ntotal != len(self.metadata):
                raise ValueError(
                    f"FAISS index/metadata mismatch. "
                    f"Index has {self.index.ntotal} vectors, "
                    f"metadata has {len(self.metadata)} items."
                )

            if self.index.d != self.dimension:
                raise ValueError(
                    f"FAISS index dimension mismatch. "
                    f"Expected {self.dimension}, got {self.index.d}."
                )

        except Exception as exc:
            raise RuntimeError(
                f"Failed to load FAISS vector store. "
                f"Check {self.index_path} and {self.meta_path}."
            ) from exc

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.index_path) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(self.meta_path) or ".", exist_ok=True)

        faiss.write_index(self.index, self.index_path)

        payload = {
            "version": self.METADATA_VERSION,
            "dimension": self.dimension,
            "count": len(self.metadata),
            "items": self.metadata,
        }

        with open(self.meta_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def reset(self) -> None:
        logger.info("Resetting FAISS vector store.")
        self.index = faiss.IndexFlatIP(self.dimension)
        self.metadata = []
        self.save()

    def add(
        self,
        embeddings: list[list[float]],
        metadata: list[dict[str, Any]],
    ) -> None:
        """
        Add embeddings and matching metadata entries.

        Notes:
        - each metadata item must be a dict
        - metadata is stored as-is after validation/sanitization
        """
        if not embeddings:
            logger.info("No embeddings to add; skipping.")
            return

        if len(embeddings) != len(metadata):
            raise ValueError(
                f"Embedding/metadata length mismatch. "
                f"Got {len(embeddings)} embeddings and {len(metadata)} metadata items."
            )

        vectors = np.asarray(embeddings, dtype="float32")

        if vectors.ndim != 2:
            raise ValueError(f"Embeddings must be a 2D array. Got shape {vectors.shape}.")

        if vectors.shape[1] != self.dimension:
            raise ValueError(
                f"Embedding dimension mismatch. "
                f"Expected {self.dimension}, got {vectors.shape[1]}."
            )

        sanitized_metadata = [self._sanitize_metadata_item(item) for item in metadata]
        vectors = self._normalize_vectors(vectors)

        self.index.add(vectors)
        self.metadata.extend(sanitized_metadata)
        self.save()

        logger.info("Added %s embedding(s) to FAISS store.", len(sanitized_metadata))

    def add_texts_with_embeddings(
        self,
        *,
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
        store_text_in_metadata: bool = True,
    ) -> None:
        """
        Convenience wrapper when caller has texts + embeddings + metadatas.

        If store_text_in_metadata=True, the raw text is inserted into metadata["text"]
        if not already present.
        """
        if len(texts) != len(embeddings) or len(texts) != len(metadatas):
            raise ValueError(
                f"Texts/embeddings/metadatas length mismatch. "
                f"Got texts={len(texts)}, embeddings={len(embeddings)}, metadatas={len(metadatas)}."
            )

        merged_metadata: list[dict[str, Any]] = []
        for text, item in zip(texts, metadatas):
            merged = dict(item or {})
            if store_text_in_metadata and "text" not in merged:
                merged["text"] = text
            merged_metadata.append(merged)

        self.add(embeddings=embeddings, metadata=merged_metadata)

    def search(
        self,
        embedding: list[float],
        k: int = 5,
        *,
        filters: dict[str, Any] | None = None,
        fetch_k_multiplier: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Search by embedding with optional metadata filters.

        Args:
            embedding:
                Query embedding vector.
            k:
                Final number of results to return.
            filters:
                Exact-match metadata filters, e.g.
                {"file_type": ".pdf", "logical_name": "RaSTA Spec"}
            fetch_k_multiplier:
                Fetch more initial candidates before applying filters.

        Returns:
            A list of metadata dicts with appended "score".
        """
        if not self.metadata or self.index.ntotal == 0:
            return []

        if k <= 0:
            return []

        query = np.asarray([embedding], dtype="float32")

        if query.ndim != 2 or query.shape[1] != self.dimension:
            raise ValueError(
                f"Query embedding dimension mismatch. "
                f"Expected {self.dimension}, got shape {query.shape}."
            )

        query = self._normalize_vectors(query)

        candidate_k = min(max(k * max(fetch_k_multiplier, 1), k), len(self.metadata))
        distances, indices = self.index.search(query, candidate_k)

        results: list[dict[str, Any]] = []
        for score, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue

            item = dict(self.metadata[idx])

            if filters and not self._matches_filters(item, filters):
                continue

            item["score"] = float(score)
            results.append(item)

            if len(results) >= k:
                break

        return results

    def delete_by_filter(self, filters: dict[str, Any]) -> int:
        """
        Rebuild the store excluding entries that match all provided filters.

        Because IndexFlatIP does not support in-place deletion, this method rebuilds
        the entire index and metadata arrays.

        Returns:
            Number of deleted entries.
        """
        if not filters:
            raise ValueError("delete_by_filter requires at least one filter.")

        if not self.metadata:
            return 0

        kept_metadata: list[dict[str, Any]] = []
        kept_indices: list[int] = []
        deleted_count = 0

        for idx, item in enumerate(self.metadata):
            if self._matches_filters(item, filters):
                deleted_count += 1
            else:
                kept_indices.append(idx)
                kept_metadata.append(item)

        if deleted_count == 0:
            return 0

        self._rebuild_index_from_indices(kept_indices, kept_metadata)
        logger.info("Deleted %s item(s) from FAISS store using filters=%s", deleted_count, filters)
        return deleted_count

    def get_all_metadata(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.metadata]

    def count(self) -> int:
        return len(self.metadata)

    def _rebuild_index_from_indices(
        self,
        kept_indices: list[int],
        kept_metadata: list[dict[str, Any]],
    ) -> None:
        new_index = faiss.IndexFlatIP(self.dimension)

        if kept_indices:
            original_vectors = self._reconstruct_all_vectors()
            kept_vectors = original_vectors[kept_indices]
            new_index.add(kept_vectors.astype("float32"))

        self.index = new_index
        self.metadata = kept_metadata
        self.save()

    def _reconstruct_all_vectors(self) -> np.ndarray:
        """
        Reconstruct all stored vectors from FAISS.

        Note:
        IndexFlatIP supports reconstruction.
        """
        if self.index.ntotal == 0:
            return np.empty((0, self.dimension), dtype="float32")

        vectors = np.zeros((self.index.ntotal, self.dimension), dtype="float32")
        for i in range(self.index.ntotal):
            vectors[i] = self.index.reconstruct(i)
        return vectors

    def _sanitize_metadata_item(self, item: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("Each metadata item must be a dictionary.")

        sanitized: dict[str, Any] = {}
        for key, value in item.items():
            sanitized[str(key)] = self._make_json_safe(value)

        return sanitized

    def _make_json_safe(self, value: Any) -> Any:
        """
        Recursively convert values into JSON-serializable structures.
        """
        if value is None:
            return None

        if isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, Path):
            return str(value)

        if isinstance(value, dict):
            return {str(k): self._make_json_safe(v) for k, v in value.items()}

        if isinstance(value, (list, tuple)):
            return [self._make_json_safe(v) for v in value]

        if isinstance(value, set):
            return [self._make_json_safe(v) for v in sorted(value, key=lambda x: str(x))]

        return str(value)

    def _matches_filters(self, item: dict[str, Any], filters: dict[str, Any]) -> bool:
        """
        Exact-match filter semantics.
        """
        for key, expected in filters.items():
            actual = item.get(key)
            if actual != expected:
                return False
        return True

    def _normalize_vectors(self, vectors: np.ndarray) -> np.ndarray:
        """
        Normalize vectors for cosine-like retrieval using IndexFlatIP.
        """
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return vectors / norms