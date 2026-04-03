
# import math
# import re
# from collections import Counter
# from typing import Any

# from app.config import settings
# from app.services.embedding_service import EmbeddingService
# from app.vector_store.faiss_store import FAISSVectorStore


# class RetrievalService:
#     def __init__(self) -> None:
#         self.embedder = EmbeddingService()
#         self.store = FAISSVectorStore(dimension=self.embedder.dimension)

#     def search(self, question: str, k: int | None = None) -> list[dict[str, Any]]:
#         k = k or settings.TOP_K

#         query = (question or "").strip()
#         if not query:
#             return []

#         query_embedding_list = self.embedder.embed([query])
#         if not query_embedding_list:
#             return []

#         query_embedding = query_embedding_list[0]

#         # First-pass vector retrieval: get more than final K so reranking has room.
#         vector_hits = self.store.search(query_embedding, k=max(k * 4, 20))
#         active_hits = [item for item in vector_hits if item.get("active", True)]

#         reranked = self._rerank(query, active_hits)
#         return reranked[:k]

#     def _rerank(self, question: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
#         question_terms = _tokenize(question)
#         question_phrases = _phrases(question)
#         scored_items: list[dict[str, Any]] = []

#         for item in items:
#             text = (item.get("text") or item.get("chunk") or "").strip()
#             filename = (item.get("filename") or "").strip()
#             logical_name = (item.get("logical_name") or "").strip()

#             keyword_score = _keyword_score(question_terms, text)
#             phrase_boost = _phrase_boost(question_phrases, text)
#             metadata_boost = _metadata_boost(question_terms, filename, logical_name)

#             # FAISS distance/score naming may vary depending on your store output.
#             raw_vector_score = _normalize_vector_score(item)

#             final_score = (
#                 0.60 * raw_vector_score
#                 + 0.25 * keyword_score
#                 + 0.10 * phrase_boost
#                 + 0.05 * metadata_boost
#             )

#             enriched = dict(item)
#             enriched["vector_score"] = raw_vector_score
#             enriched["keyword_score"] = keyword_score
#             enriched["phrase_boost"] = phrase_boost
#             enriched["metadata_boost"] = metadata_boost
#             enriched["final_score"] = final_score

#             scored_items.append(enriched)

#         scored_items.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
#         return scored_items


# def _tokenize(text: str) -> set[str]:
#     tokens = re.findall(r"[\w-]{2,}", text.lower())
#     return {token for token in tokens if token.strip()}


# def _phrases(text: str) -> list[str]:
#     clean = " ".join(text.lower().split())
#     if not clean:
#         return []
#     words = clean.split()
#     if len(words) < 2:
#         return []
#     phrases: list[str] = []
#     for size in (2, 3):
#         for i in range(len(words) - size + 1):
#             phrases.append(" ".join(words[i : i + size]))
#     return phrases


# def _keyword_score(question_terms: set[str], text: str) -> float:
#     if not question_terms or not text:
#         return 0.0

#     text_terms = re.findall(r"[\w-]{2,}", text.lower())
#     if not text_terms:
#         return 0.0

#     counts = Counter(text_terms)
#     overlap = 0.0
#     for term in question_terms:
#         if term in counts:
#             # log-scaled bonus avoids giant chunks dominating too much
#             overlap += 1.0 + math.log1p(counts[term])

#     max_possible = max(len(question_terms), 1)
#     return min(overlap / max_possible, 1.0)


# def _phrase_boost(phrases: list[str], text: str) -> float:
#     if not phrases or not text:
#         return 0.0

#     lowered = text.lower()
#     matches = sum(1 for phrase in phrases if phrase in lowered)
#     if matches == 0:
#         return 0.0

#     return min(matches / max(len(phrases), 1), 1.0)


# def _metadata_boost(question_terms: set[str], filename: str, logical_name: str) -> float:
#     haystack = f"{filename} {logical_name}".lower()
#     if not haystack.strip() or not question_terms:
#         return 0.0

#     hits = sum(1 for term in question_terms if term in haystack)
#     return min(hits / max(len(question_terms), 1), 1.0)


# def _normalize_vector_score(item: dict[str, Any]) -> float:
#     """
#     Try to normalize different FAISS result formats into a 0..1 score.

#     Your FAISS store may return:
#     - score
#     - distance
#     - similarity

#     We handle the common cases safely.
#     """
#     if "vector_score" in item and isinstance(item["vector_score"], (int, float)):
#         return float(item["vector_score"])

#     if "score" in item and isinstance(item["score"], (int, float)):
#         score = float(item["score"])
#         # If already 0..1, keep it.
#         if 0.0 <= score <= 1.0:
#             return score
#         # Otherwise squash.
#         return 1.0 / (1.0 + abs(score))

#     if "similarity" in item and isinstance(item["similarity"], (int, float)):
#         sim = float(item["similarity"])
#         if 0.0 <= sim <= 1.0:
#             return sim
#         return 1.0 / (1.0 + abs(sim))

#     if "distance" in item and isinstance(item["distance"], (int, float)):
#         # Smaller distance is better.
#         distance = float(item["distance"])
#         return 1.0 / (1.0 + max(distance, 0.0))

#     return 0.0

import math
import re
from collections import Counter
from typing import Any

from app.config import settings
from app.services.embedding_service import EmbeddingService
from app.vector_store.faiss_store import FAISSVectorStore


class RetrievalService:
    def __init__(self) -> None:
        self.embedder = EmbeddingService()
        self.store = FAISSVectorStore(dimension=self.embedder.dimension)

    def search(self, question: str, k: int | None = None) -> list[dict[str, Any]]:
        k = k or settings.TOP_K

        query = _normalize_query(question)
        if not query:
            return []

        query_embedding_list = self.embedder.embed([query])
        if not query_embedding_list:
            return []

        query_embedding = query_embedding_list[0]

        # Pull more candidates first, then rerank down.
        vector_hits = self.store.search(query_embedding, k=max(k * 4, 20))
        active_hits = [item for item in vector_hits if item.get("active", True)]

        reranked = self._rerank(query, active_hits)
        deduplicated = self._deduplicate_results(reranked)

        return deduplicated[:k]

    def _rerank(self, question: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        question_terms = _tokenize(question)
        question_phrases = _phrases(question)
        scored_items: list[dict[str, Any]] = []

        for item in items:
            text = (item.get("text") or item.get("chunk") or "").strip()
            filename = (item.get("filename") or "").strip()
            logical_name = (item.get("logical_name") or "").strip()

            raw_vector_score = _normalize_vector_score(item)
            keyword_score = _keyword_score(question_terms, text)
            phrase_boost = _phrase_boost(question_phrases, text)
            metadata_boost = _metadata_boost(question_terms, item)
            structure_boost = _structure_boost(question_terms, item)

            final_score = (
                0.50 * raw_vector_score
                + 0.22 * keyword_score
                + 0.10 * phrase_boost
                + 0.10 * metadata_boost
                + 0.08 * structure_boost
            )

            enriched = dict(item)
            enriched["vector_score"] = raw_vector_score
            enriched["keyword_score"] = keyword_score
            enriched["phrase_boost"] = phrase_boost
            enriched["metadata_boost"] = metadata_boost
            enriched["structure_boost"] = structure_boost
            enriched["final_score"] = final_score

            scored_items.append(enriched)

        scored_items.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
        return scored_items

    def _deduplicate_results(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduplicated: list[dict[str, Any]] = []
        seen: set[str] = set()

        for item in items:
            text = (item.get("text") or item.get("chunk") or "").strip()
            filename = (item.get("filename") or "").strip()
            chunk_id = str(item.get("chunk_id", ""))

            dedupe_key = f"{filename}|{chunk_id}|{text[:220]}"
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            deduplicated.append(item)

        return deduplicated


def _normalize_query(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[\w-]{2,}", text.lower())
    return {token for token in tokens if token.strip()}


def _phrases(text: str) -> list[str]:
    clean = " ".join(text.lower().split())
    if not clean:
        return []

    words = clean.split()
    if len(words) < 2:
        return []

    phrases: list[str] = []
    for size in (2, 3):
        for i in range(len(words) - size + 1):
            phrases.append(" ".join(words[i : i + size]))
    return phrases


def _keyword_score(question_terms: set[str], text: str) -> float:
    if not question_terms or not text:
        return 0.0

    text_terms = re.findall(r"[\w-]{2,}", text.lower())
    if not text_terms:
        return 0.0

    counts = Counter(text_terms)
    overlap = 0.0

    for term in question_terms:
        if term in counts:
            overlap += 1.0 + math.log1p(counts[term])

    max_possible = max(len(question_terms), 1)
    return min(overlap / max_possible, 1.0)


def _phrase_boost(phrases: list[str], text: str) -> float:
    if not phrases or not text:
        return 0.0

    lowered = text.lower()
    matches = sum(1 for phrase in phrases if phrase in lowered)
    if matches == 0:
        return 0.0

    return min(matches / max(len(phrases), 1), 1.0)


def _metadata_boost(question_terms: set[str], item: dict[str, Any]) -> float:
    metadata_parts = [
        str(item.get("filename") or ""),
        str(item.get("logical_name") or ""),
        str(item.get("file_type") or ""),
        str(item.get("type") or ""),
        str(item.get("heading") or ""),
        str(item.get("sheet") or ""),
        str(item.get("slide") or ""),
        str(item.get("page") or ""),
        str(item.get("row") or ""),
    ]

    haystack = " ".join(metadata_parts).lower()
    if not haystack.strip() or not question_terms:
        return 0.0

    hits = sum(1 for term in question_terms if term in haystack)
    return min(hits / max(len(question_terms), 1), 1.0)


def _structure_boost(question_terms: set[str], item: dict[str, Any]) -> float:
    """
    Boost chunks when the question hints at a specific document structure.
    """
    if not question_terms:
        return 0.0

    boost = 0.0

    file_type = str(item.get("file_type") or "").lower()
    item_type = str(item.get("type") or "").lower()

    # PDF/page-aware retrieval
    if "page" in question_terms and (file_type == ".pdf" or item_type == "pdf_page"):
        boost += 0.35

    # DOCX heading/section-aware retrieval
    if any(term in question_terms for term in {"section", "chapter", "heading"}) and (
        item_type == "docx_section" or item.get("heading")
    ):
        boost += 0.30

    # XLSX sheet/row-aware retrieval
    if any(term in question_terms for term in {"sheet", "row", "column", "table"}) and (
        file_type == ".xlsx" or item_type.startswith("xlsx_")
    ):
        boost += 0.35

    # PPTX slide-aware retrieval
    if "slide" in question_terms and (file_type == ".pptx" or item_type == "pptx_slide"):
        boost += 0.35

    # Table-focused retrieval
    if "table" in question_terms and "table" in item_type:
        boost += 0.25

    return min(boost, 1.0)


def _normalize_vector_score(item: dict[str, Any]) -> float:
    """
    Normalize different FAISS result formats into a 0..1 score.
    """
    if "vector_score" in item and isinstance(item["vector_score"], (int, float)):
        return float(item["vector_score"])

    if "score" in item and isinstance(item["score"], (int, float)):
        score = float(item["score"])
        if 0.0 <= score <= 1.0:
            return score
        return 1.0 / (1.0 + abs(score))

    if "similarity" in item and isinstance(item["similarity"], (int, float)):
        sim = float(item["similarity"])
        if 0.0 <= sim <= 1.0:
            return sim
        return 1.0 / (1.0 + abs(sim))

    if "distance" in item and isinstance(item["distance"], (int, float)):
        distance = float(item["distance"])
        return 1.0 / (1.0 + max(distance, 0.0))

    return 0.0