
# import json
# import os
# from typing import Any

# import faiss
# import numpy as np

# from app.config import settings


# class FAISSVectorStore:
#     def __init__(self, dimension: int) -> None:
#         self.dimension = dimension
#         self.index_path = settings.VECTOR_INDEX_PATH
#         self.meta_path = settings.VECTOR_META_PATH
#         self.index: faiss.IndexFlatIP
#         self.metadata: list[dict[str, Any]]
#         self._load()

#     def _load(self) -> None:
#         if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
#             self.index = faiss.read_index(self.index_path)
#             with open(self.meta_path, 'r', encoding='utf-8') as handle:
#                 self.metadata = json.load(handle)
#         else:
#             self.index = faiss.IndexFlatIP(self.dimension)
#             self.metadata = []

#     def save(self) -> None:
#         os.makedirs(os.path.dirname(self.index_path) or '.', exist_ok=True)
#         faiss.write_index(self.index, self.index_path)
#         with open(self.meta_path, 'w', encoding='utf-8') as handle:
#             json.dump(self.metadata, handle, ensure_ascii=False, indent=2)

#     def reset(self) -> None:
#         self.index = faiss.IndexFlatIP(self.dimension)
#         self.metadata = []-
#         self.save()

#     def add(self, embeddings: list[list[float]], metadata: list[dict[str, Any]]) -> None:
#         if not embeddings:
#             return
#         vectors = np.asarray(embeddings, dtype='float32')
#         if vectors.shape[1] != self.dimension:
#             raise ValueError(f'Embedding dimension mismatch. Expected {self.dimension}, got {vectors.shape[1]}.')
#         self.index.add(vectors)
#         self.metadata.extend(metadata)
#         self.save()

#     def search(self, embedding: list[float], k: int = 5) -> list[dict[str, Any]]:
#         if not self.metadata or self.index.ntotal == 0:
#             return []
#         query = np.asarray([embedding], dtype='float32')
#         distances, indices = self.index.search(query, min(k, len(self.metadata)))
#         results: list[dict[str, Any]] = []
#         for score, idx in zip(distances[0], indices[0]):
#             if idx < 0:
#                 continue
#             item = dict(self.metadata[idx])
#             item['score'] = float(score)
#             results.append(item)
#         return results


import json
import os
from typing import Any

import faiss
import numpy as np

from app.config import settings


class FAISSVectorStore:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.index_path = settings.VECTOR_INDEX_PATH
        self.meta_path = settings.VECTOR_META_PATH
        self.index: faiss.IndexFlatIP
        self.metadata: list[dict[str, Any]]
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
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
                    # Backward compatibility with old metadata format
                    self.metadata = raw
                else:
                    raise ValueError("Invalid FAISS metadata format.")

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

        else:
            self.index = faiss.IndexFlatIP(self.dimension)
            self.metadata = []

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.index_path) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(self.meta_path) or ".", exist_ok=True)

        faiss.write_index(self.index, self.index_path)

        payload = {
            "version": 1,
            "dimension": self.dimension,
            "items": self.metadata,
        }

        with open(self.meta_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def reset(self) -> None:
        self.index = faiss.IndexFlatIP(self.dimension)
        self.metadata = []
        self.save()

    def add(self, embeddings: list[list[float]], metadata: list[dict[str, Any]]) -> None:
        if not embeddings:
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

        vectors = self._normalize_vectors(vectors)

        self.index.add(vectors)
        self.metadata.extend(metadata)
        self.save()

    def search(self, embedding: list[float], k: int = 5) -> list[dict[str, Any]]:
        if not self.metadata or self.index.ntotal == 0:
            return []

        query = np.asarray([embedding], dtype="float32")

        if query.ndim != 2 or query.shape[1] != self.dimension:
            raise ValueError(
                f"Query embedding dimension mismatch. "
                f"Expected {self.dimension}, got shape {query.shape}."
            )

        query = self._normalize_vectors(query)

        distances, indices = self.index.search(query, min(k, len(self.metadata)))

        results: list[dict[str, Any]] = []
        for score, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue

            item = dict(self.metadata[idx])
            item["score"] = float(score)
            results.append(item)

        return results

    def _normalize_vectors(self, vectors: np.ndarray) -> np.ndarray:
        """
        Normalize vectors for cosine-like retrieval using IndexFlatIP.
        """
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return vectors / norms