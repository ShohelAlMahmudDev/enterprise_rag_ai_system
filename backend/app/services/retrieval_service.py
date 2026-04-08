# import math
# import re
# from collections import Counter
# from typing import Any

# from app.config import settings
# from app.services.embedding_service import EmbeddingService
# from app.vector_store.faiss_store import FAISSVectorStore


# class RetrievalService:
#     """
#     Retrieval layer for enterprise RAG.

#     Responsibilities:
#     - normalize the user query
#     - compute query embeddings
#     - retrieve initial candidates from FAISS
#     - apply metadata filters
#     - apply active-record filtering
#     - rerank results using lexical and structure-aware signals
#     - deduplicate overlapping results

#     Notes:
#     - FAISS remains the first-stage retriever
#     - reranking is lightweight and local
#     - exact metadata filters are supported when provided
#     """

#     def __init__(
#         self,
#         *,
#         embedder: EmbeddingService | None = None,
#         store: FAISSVectorStore | None = None,
#     ) -> None:
#         self.embedder = embedder or EmbeddingService()
#         self.store = store or FAISSVectorStore(dimension=self.embedder.dimension)

#     def search(
#         self,
#         question: str,
#         k: int | None = None,
#         filters: dict[str, Any] | None = None,
#     ) -> list[dict[str, Any]]:
#         """
#         Retrieve and rerank relevant chunks for a question.

#         Args:
#             question:
#                 User question or retrieval query.
#             k:
#                 Final number of results to return.
#             filters:
#                 Optional exact-match metadata filters, e.g.
#                     {"file_type": ".pdf"}
#                     {"logical_name": "RaSTA Spec"}
#                     {"document_id": "doc_001", "version_id": "ver_002"}

#         Returns:
#             List of reranked result dictionaries.
#         """
#         final_k = k or settings.TOP_K

#         query = _normalize_query(question)
#         if not query:
#             return []

#         query_embedding_list = self.embedder.embed([query])
#         if not query_embedding_list:
#             return []

#         query_embedding = query_embedding_list[0]

#         # Pull more candidates first, then rerank down.
#         fetch_k = max(final_k * 4, 20)
#         vector_hits = self.store.search(
#             query_embedding,
#             k=fetch_k,
#             filters=filters,
#         )

#         active_hits = self._filter_active_hits(vector_hits)

#         reranked = self._rerank(query, active_hits)
#         deduplicated = self._deduplicate_results(reranked)

#         return deduplicated[:final_k]

#     def _filter_active_hits(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
#         """
#         Keep only active items by default.

#         Current behavior:
#         - if 'active' is missing, assume True
#         - if 'is_active' is present, respect it
#         - if 'deleted' is True, exclude it
#         - if 'is_deleted' is True, exclude it
#         """
#         active_items: list[dict[str, Any]] = []

#         for item in items:
#             if not item.get("active", True):
#                 continue
#             if not item.get("is_active", True):
#                 continue
#             if item.get("deleted", False):
#                 continue
#             if item.get("is_deleted", False):
#                 continue
#             active_items.append(item)

#         return active_items

#     def _rerank(self, question: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
#         """
#         Lightweight local reranking with semantic + lexical + metadata features.
#         """
#         question_terms = _tokenize(question)
#         question_phrases = _phrases(question)
#         scored_items: list[dict[str, Any]] = []

#         for item in items:
#             text = (item.get("text") or item.get("chunk") or "").strip()

#             raw_vector_score = _normalize_vector_score(item)
#             keyword_score = _keyword_score(question_terms, text)
#             phrase_boost = _phrase_boost(question_phrases, text)
#             metadata_boost = _metadata_boost(question_terms, item)
#             structure_boost = _structure_boost(question_terms, item)
#             multimodal_boost = _multimodal_boost(question_terms, item)
#             numeric_boost = _numeric_exact_match_boost(question, text)
#             mapping_boost = _mapping_pattern_boost(question, text)

#             final_score = (
#                 0.38 * raw_vector_score
#                 + 0.18 * keyword_score
#                 + 0.10 * phrase_boost
#                 + 0.08 * metadata_boost
#                 + 0.06 * structure_boost
#                 + 0.05 * multimodal_boost
#                 + 0.15 * numeric_boost
#                 + 0.12 * mapping_boost
#             )

#             enriched = dict(item)
#             enriched["vector_score"] = raw_vector_score
#             enriched["keyword_score"] = keyword_score
#             enriched["phrase_boost"] = phrase_boost
#             enriched["metadata_boost"] = metadata_boost
#             enriched["structure_boost"] = structure_boost
#             enriched["multimodal_boost"] = multimodal_boost
#             enriched["final_score"] = round(final_score, 6)
#             enriched["numeric_boost"] = numeric_boost
#             enriched["mapping_boost"] = mapping_boost

#             scored_items.append(enriched)

#         scored_items.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
#         return scored_items

#     def _deduplicate_results(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
#         """
#         Remove near-duplicate results to improve diversity.

#         Preference order is preserved from the reranked list.
#         """
#         deduplicated: list[dict[str, Any]] = []
#         seen: set[str] = set()

#         for item in items:
#             text = (item.get("text") or item.get("chunk") or "").strip()
#             filename = (item.get("filename") or item.get("source_file") or "").strip()
#             chunk_id = str(item.get("chunk_id", "")).strip()
#             page = str(item.get("page", item.get("page_number", ""))).strip()
#             slide = str(item.get("slide", item.get("slide_number", ""))).strip()
#             sheet = str(item.get("sheet", item.get("sheet_name", ""))).strip()

#             dedupe_key = f"{filename}|{sheet}|{page}|{slide}|{chunk_id}|{text[:220]}"
#             if dedupe_key in seen:
#                 continue

#             seen.add(dedupe_key)
#             deduplicated.append(item)

#         return deduplicated


# def _normalize_query(text: str) -> str:
#     return " ".join((text or "").split()).strip()


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


# def _metadata_boost(question_terms: set[str], item: dict[str, Any]) -> float:
#     metadata_parts = [
#         str(item.get("filename") or ""),
#         str(item.get("logical_name") or ""),
#         str(item.get("file_type") or ""),
#         str(item.get("type") or ""),
#         str(item.get("heading") or ""),
#         str(item.get("sheet") or item.get("sheet_name") or ""),
#         str(item.get("slide") or item.get("slide_number") or ""),
#         str(item.get("page") or item.get("page_number") or ""),
#         str(item.get("row") or ""),
#         str(item.get("diagram_type") or ""),
#     ]

#     haystack = " ".join(metadata_parts).lower()
#     if not haystack.strip() or not question_terms:
#         return 0.0

#     hits = sum(1 for term in question_terms if term in haystack)
#     return min(hits / max(len(question_terms), 1), 1.0)


# def _structure_boost(question_terms: set[str], item: dict[str, Any]) -> float:
#     """
#     Boost chunks when the question hints at a specific document structure.
#     """
#     if not question_terms:
#         return 0.0

#     boost = 0.0

#     file_type = str(item.get("file_type") or "").lower()
#     item_type = str(item.get("type") or "").lower()

#     # PDF/page-aware retrieval
#     if "page" in question_terms and (file_type == ".pdf" or item_type == "pdf_page"):
#         boost += 0.35

#     # DOCX heading/section-aware retrieval
#     if any(term in question_terms for term in {"section", "chapter", "heading"}) and (
#         item_type == "docx_section" or item.get("heading")
#     ):
#         boost += 0.30

#     # XLSX sheet/row-aware retrieval
#     if any(term in question_terms for term in {"sheet", "row", "column", "table"}) and (
#         file_type == ".xlsx" or item_type.startswith("xlsx_")
#     ):
#         boost += 0.35

#     # PPTX slide-aware retrieval
#     if "slide" in question_terms and (file_type == ".pptx" or item_type == "pptx_slide"):
#         boost += 0.35

#     # Table-focused retrieval
#     if "table" in question_terms and "table" in item_type:
#         boost += 0.25

#     # Diagram-focused retrieval
#     if any(term in question_terms for term in {"diagram", "state", "transition", "flowchart", "flow", "sequence"}):
#         if item.get("diagram_type") or item.get("has_structured_extraction"):
#             boost += 0.25

#     return min(boost, 1.0)


# def _multimodal_boost(question_terms: set[str], item: dict[str, Any]) -> float:
#     """
#     Boost multimodal image/diagram chunks when the query suggests visual or structured intent.
#     """
#     if not question_terms:
#         return 0.0

#     boost = 0.0

#     source_modality = str(item.get("source_modality") or "").lower()
#     content_type = str(item.get("content_type") or "").lower()
#     diagram_type = str(item.get("diagram_type") or "").lower()
#     has_structured_extraction = bool(item.get("has_structured_extraction"))

#     visual_terms = {
#         "diagram",
#         "image",
#         "picture",
#         "screenshot",
#         "flow",
#         "flowchart",
#         "state",
#         "transition",
#         "component",
#         "architecture",
#         "network",
#         "sequence",
#         "ui",
#         "table",
#     }

#     if question_terms.intersection(visual_terms):
#         if source_modality == "vision":
#             boost += 0.35
#         if content_type == "image":
#             boost += 0.20
#         if has_structured_extraction:
#             boost += 0.25
#         if diagram_type:
#             boost += 0.20

#     return min(boost, 1.0)


# def _normalize_vector_score(item: dict[str, Any]) -> float:
#     """
#     Normalize different FAISS result formats into a 0..1 score.
#     """
#     if "final_score" in item and isinstance(item["final_score"], (int, float)):
#         return float(item["final_score"])

#     if "vector_score" in item and isinstance(item["vector_score"], (int, float)):
#         return float(item["vector_score"])

#     if "score" in item and isinstance(item["score"], (int, float)):
#         score = float(item["score"])
#         if 0.0 <= score <= 1.0:
#             return score
#         return 1.0 / (1.0 + abs(score))

#     if "similarity" in item and isinstance(item["similarity"], (int, float)):
#         sim = float(item["similarity"])
#         if 0.0 <= sim <= 1.0:
#             return sim
#         return 1.0 / (1.0 + abs(sim))

#     if "distance" in item and isinstance(item["distance"], (int, float)):
#         distance = float(item["distance"])
#         return 1.0 / (1.0 + max(distance, 0.0))

#     return 0.0

# def _numeric_exact_match_boost(question: str, text: str) -> float:
#     """
#     Strong boost when exact numeric values match.
#     Critical for table lookups like 'action 26'.
#     """
#     if not question or not text:
#         return 0.0

#     q_numbers = re.findall(r"\b\d+\b", question)
#     if not q_numbers:
#         return 0.0

#     text_numbers = set(re.findall(r"\b\d+\b", text))
#     if not text_numbers:
#         return 0.0

#     matches = sum(1 for num in q_numbers if num in text_numbers)

#     if matches == 0:
#         return 0.0

#     return min(matches / len(q_numbers), 1.0)

# def _mapping_pattern_boost(question: str, text: str) -> float:
#     q_numbers = re.findall(r"\b\d+\b", question)
#     if not q_numbers:
#         return 0.0

#     boost = 0.0
#     for num in q_numbers:
#         pattern = rf"\b{re.escape(num)}\s*=\s*"
#         if re.search(pattern, text):
#             boost += 1.0

#     return min(boost / len(q_numbers), 1.0)

import math
import re
from collections import Counter
from typing import Any

from app.config import settings
from app.services.bm25_service import BM25Service
from app.services.column_aware_retrieval_service import ColumnAwareRetrievalService
from app.services.embedding_service import EmbeddingService
from app.services.query_rewrite_service import QueryRewriteService
from app.services.structured_index_service import StructuredIndexService
from app.vector_store.faiss_store import FAISSVectorStore


class RetrievalService:
    """
    Hybrid retrieval service.

    Retrieval stages:
    - deterministic query rewrite for technical/table queries
    - FAISS semantic retrieval
    - BM25 lexical retrieval
    - structured key-value index lookup
    - column-aware reranking
    - exact numeric / mapping boosts
    """

    def __init__(
        self,
        *,
        embedder: EmbeddingService | None = None,
        store: FAISSVectorStore | None = None,
        bm25: BM25Service | None = None,
        structured_index: StructuredIndexService | None = None,
        query_rewriter: QueryRewriteService | None = None,
        column_service: ColumnAwareRetrievalService | None = None,
    ) -> None:
        self.embedder = embedder or EmbeddingService()
        self.store = store or FAISSVectorStore(dimension=self.embedder.dimension)
        self.bm25 = bm25 or BM25Service()
        self.structured_index = structured_index or StructuredIndexService()
        self.query_rewriter = query_rewriter or QueryRewriteService()
        self.column_service = column_service or ColumnAwareRetrievalService()

    def search(
        self,
        question: str,
        k: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        final_k = k or settings.TOP_K

        normalized_question = _normalize_query(question)
        if not normalized_question:
            return []

        rewritten = (
            self.query_rewriter.rewrite(normalized_question)
            if settings.ENABLE_QUERY_REWRITE
            else None
        )
        retrieval_query = rewritten.rewritten if rewritten else normalized_question

        vector_hits = self._search_vector(retrieval_query, final_k, filters)
        bm25_hits = self._search_bm25(retrieval_query, filters)
        structured_hits = self._search_structured(normalized_question, filters)

        merged_candidates = self._merge_candidates(
            vector_hits=vector_hits,
            bm25_hits=bm25_hits,
            structured_hits=structured_hits,
        )

        active_hits = self._filter_active_hits(merged_candidates)
        reranked = self._rerank(normalized_question, active_hits, rewritten_is_lookup=bool(rewritten and rewritten.is_lookup))
        deduplicated = self._deduplicate_results(reranked)

        return deduplicated[:final_k]

    def _search_vector(
        self,
        query: str,
        final_k: int,
        filters: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        query_embedding_list = self.embedder.embed([query])
        if not query_embedding_list:
            return []

        query_embedding = query_embedding_list[0]
        fetch_k = max(final_k * settings.RETRIEVAL_CANDIDATE_MULTIPLIER, 20)

        return self.store.search(
            query_embedding,
            k=fetch_k,
            filters=filters,
        )

    def _search_bm25(self, query: str, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not settings.ENABLE_BM25_RETRIEVAL:
            return []
        return self.bm25.search(query, k=settings.BM25_TOP_K, filters=filters)

    def _search_structured(self, question: str, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not settings.ENABLE_STRUCTURED_RETRIEVAL:
            return []
        return self.structured_index.search(question, k=settings.STRUCTURED_TOP_K, filters=filters)

    def _merge_candidates(
        self,
        *,
        vector_hits: list[dict[str, Any]],
        bm25_hits: list[dict[str, Any]],
        structured_hits: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}

        for source_name, items in (
            ("vector", vector_hits),
            ("bm25", bm25_hits),
            ("structured", structured_hits),
        ):
            for item in items:
                key = self._candidate_key(item)
                existing = merged.get(key)

                enriched = dict(item)
                enriched.setdefault("retrieval_sources", [])
                if source_name not in enriched["retrieval_sources"]:
                    enriched["retrieval_sources"].append(source_name)

                if existing is None:
                    merged[key] = enriched
                    continue

                existing_sources = set(existing.get("retrieval_sources", []))
                existing_sources.add(source_name)
                existing["retrieval_sources"] = sorted(existing_sources)

                for field in (
                    "bm25_score",
                    "structured_score",
                    "score",
                    "vector_score",
                    "text",
                    "chunk",
                    "columns",
                    "attribute_name",
                    "code",
                    "value",
                    "row_text",
                ):
                    if enriched.get(field) not in (None, "", {}, []):
                        existing[field] = enriched[field]

        return list(merged.values())

    def _candidate_key(self, item: dict[str, Any]) -> str:
        filename = str(item.get("filename") or item.get("source_file") or "")
        chunk_id = str(item.get("chunk_id") or "")
        code = str(item.get("code") or "")
        row = str(item.get("row") or "")
        page = str(item.get("page") or item.get("page_number") or "")
        text_head = str(item.get("text") or item.get("chunk") or "")[:200]
        return f"{filename}|{chunk_id}|{code}|{row}|{page}|{text_head}"

    def _filter_active_hits(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        active_items: list[dict[str, Any]] = []

        for item in items:
            if not item.get("active", True):
                continue
            if not item.get("is_active", True):
                continue
            if item.get("deleted", False):
                continue
            if item.get("is_deleted", False):
                continue
            active_items.append(item)

        return active_items

    def _rerank(
        self,
        question: str,
        items: list[dict[str, Any]],
        *,
        rewritten_is_lookup: bool,
    ) -> list[dict[str, Any]]:
        question_terms = _tokenize(question)
        question_phrases = _phrases(question)
        scored_items: list[dict[str, Any]] = []

        for item in items:
            text = (item.get("text") or item.get("chunk") or "").strip()

            raw_vector_score = _normalize_vector_score(item)
            bm25_score = _normalize_bm25_score(item)
            structured_score = _normalize_structured_score(item)
            keyword_score = _keyword_score(question_terms, text)
            phrase_boost = _phrase_boost(question_phrases, text)
            metadata_boost = _metadata_boost(question_terms, item)
            structure_boost = _structure_boost(question_terms, item)
            multimodal_boost = _multimodal_boost(question_terms, item)
            numeric_boost = _numeric_exact_match_boost(question, text)
            mapping_boost = _mapping_pattern_boost(question, text)
            column_boost = self.column_service.score(question, item)
            source_boost = _retrieval_source_boost(item)

            final_score = (
                settings.VECTOR_WEIGHT * raw_vector_score
                + settings.BM25_WEIGHT * bm25_score
                + settings.STRUCTURED_WEIGHT * structured_score
                + settings.KEYWORD_WEIGHT * keyword_score
                + settings.PHRASE_WEIGHT * phrase_boost
                + settings.METADATA_WEIGHT * metadata_boost
                + settings.STRUCTURE_WEIGHT * structure_boost
                + settings.MULTIMODAL_WEIGHT * multimodal_boost
                + settings.NUMERIC_WEIGHT * numeric_boost
                + settings.MAPPING_WEIGHT * mapping_boost
                + settings.COLUMN_WEIGHT * column_boost
                + 0.05 * source_boost
            )

            if rewritten_is_lookup:
                final_score += 0.04 * numeric_boost
                final_score += 0.04 * mapping_boost
                final_score += 0.03 * column_boost

            enriched = dict(item)
            enriched["vector_score"] = round(raw_vector_score, 6)
            enriched["bm25_score"] = round(bm25_score, 6)
            enriched["structured_score"] = round(structured_score, 6)
            enriched["keyword_score"] = round(keyword_score, 6)
            enriched["phrase_boost"] = round(phrase_boost, 6)
            enriched["metadata_boost"] = round(metadata_boost, 6)
            enriched["structure_boost"] = round(structure_boost, 6)
            enriched["multimodal_boost"] = round(multimodal_boost, 6)
            enriched["numeric_boost"] = round(numeric_boost, 6)
            enriched["mapping_boost"] = round(mapping_boost, 6)
            enriched["column_boost"] = round(column_boost, 6)
            enriched["source_boost"] = round(source_boost, 6)
            enriched["final_score"] = round(final_score, 6)

            scored_items.append(enriched)

        scored_items.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
        return scored_items

    def _deduplicate_results(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduplicated: list[dict[str, Any]] = []
        seen: set[str] = set()

        for item in items:
            text = (item.get("text") or item.get("chunk") or "").strip()
            filename = (item.get("filename") or item.get("source_file") or "").strip()
            chunk_id = str(item.get("chunk_id", "")).strip()
            page = str(item.get("page", item.get("page_number", ""))).strip()
            slide = str(item.get("slide", item.get("slide_number", ""))).strip()
            sheet = str(item.get("sheet", item.get("sheet_name", ""))).strip()
            code = str(item.get("code", "")).strip()

            dedupe_key = f"{filename}|{sheet}|{page}|{slide}|{chunk_id}|{code}|{text[:220]}"
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            deduplicated.append(item)

        return deduplicated


def _normalize_query(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[\w.-]{2,}", (text or "").lower())
    return {token for token in tokens if token.strip()}


def _phrases(text: str) -> list[str]:
    clean = " ".join((text or "").lower().split())
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

    text_terms = re.findall(r"[\w.-]{2,}", text.lower())
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
        str(item.get("sheet") or item.get("sheet_name") or ""),
        str(item.get("slide") or item.get("slide_number") or ""),
        str(item.get("page") or item.get("page_number") or ""),
        str(item.get("row") or ""),
        str(item.get("attribute_name") or ""),
        str(item.get("code") or ""),
    ]

    haystack = " ".join(metadata_parts).lower()
    if not haystack.strip() or not question_terms:
        return 0.0

    hits = sum(1 for term in question_terms if term in haystack)
    return min(hits / max(len(question_terms), 1), 1.0)


def _structure_boost(question_terms: set[str], item: dict[str, Any]) -> float:
    if not question_terms:
        return 0.0

    boost = 0.0
    file_type = str(item.get("file_type") or "").lower()
    item_type = str(item.get("type") or item.get("record_type") or "").lower()

    if "page" in question_terms and (file_type == ".pdf" or item_type == "pdf_page"):
        boost += 0.35

    if any(term in question_terms for term in {"section", "chapter", "heading"}) and (
        item_type == "docx_section" or item.get("heading")
    ):
        boost += 0.30

    if any(term in question_terms for term in {"sheet", "row", "column", "table"}) and (
        file_type == ".xlsx" or item_type.startswith("xlsx_") or item_type in {"row_columns", "table_row"}
    ):
        boost += 0.35

    if "slide" in question_terms and (file_type == ".pptx" or item_type == "pptx_slide"):
        boost += 0.35

    if "table" in question_terms and "table" in item_type:
        boost += 0.25

    return min(boost, 1.0)


def _multimodal_boost(question_terms: set[str], item: dict[str, Any]) -> float:
    if not question_terms:
        return 0.0

    boost = 0.0

    source_modality = str(item.get("source_modality") or "").lower()
    content_type = str(item.get("content_type") or "").lower()
    has_structured_extraction = bool(item.get("has_structured_extraction"))

    visual_terms = {
        "diagram",
        "image",
        "picture",
        "screenshot",
        "flow",
        "flowchart",
        "state",
        "transition",
        "component",
        "architecture",
        "network",
        "sequence",
        "ui",
        "table",
    }

    if question_terms.intersection(visual_terms):
        if source_modality == "vision":
            boost += 0.35
        if content_type == "image":
            boost += 0.20
        if has_structured_extraction:
            boost += 0.25

    return min(boost, 1.0)


def _normalize_vector_score(item: dict[str, Any]) -> float:
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


def _normalize_bm25_score(item: dict[str, Any]) -> float:
    score = float(item.get("bm25_score", 0.0) or 0.0)
    if score <= 0.0:
        return 0.0
    return score / (score + 5.0)


def _normalize_structured_score(item: dict[str, Any]) -> float:
    score = float(item.get("structured_score", 0.0) or 0.0)
    return min(max(score, 0.0), 1.0)


def _numeric_exact_match_boost(question: str, text: str) -> float:
    if not question or not text:
        return 0.0

    q_numbers = re.findall(r"\b\d+\b", question)
    if not q_numbers:
        return 0.0

    text_numbers = set(re.findall(r"\b\d+\b", text))
    if not text_numbers:
        return 0.0

    matches = sum(1 for num in q_numbers if num in text_numbers)
    return min(matches / len(q_numbers), 1.0) if matches else 0.0


def _mapping_pattern_boost(question: str, text: str) -> float:
    if not question or not text:
        return 0.0

    q_numbers = re.findall(r"\b\d+\b", question)
    if not q_numbers:
        return 0.0

    boost = 0.0
    for num in q_numbers:
        pattern = rf"\b{re.escape(num)}\s*=\s*"
        if re.search(pattern, text):
            boost += 1.0

    return min(boost / len(q_numbers), 1.0)


def _retrieval_source_boost(item: dict[str, Any]) -> float:
    sources = set(item.get("retrieval_sources", []))
    boost = 0.0

    if "structured" in sources:
        boost += 0.40
    if "bm25" in sources:
        boost += 0.25
    if "vector" in sources:
        boost += 0.20

    return min(boost, 1.0)