import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.config import settings


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\w.-]{2,}", (text or "").lower())


class BM25Service:
    """
    Lightweight persistent BM25 index.

    Stored as JSON for simplicity and deployability.
    Suitable for small to medium enterprise RAG deployments.
    """

    def __init__(self, index_path: str | None = None) -> None:
        self.index_path = Path(index_path or settings.BM25_INDEX_PATH)
        self.k1 = 1.5
        self.b = 0.75
        self.documents: list[dict[str, Any]] = []
        self.doc_freq: dict[str, int] = {}
        self.avgdl: float = 0.0
        self._load()

    def add_documents(self, docs: list[dict[str, Any]]) -> None:
        if not docs:
            return

        self.documents.extend(docs)
        self._rebuild_statistics()
        self._save()

    def remove_by_version(self, version_id: str) -> None:
        if not version_id:
            return

        self.documents = [doc for doc in self.documents if str(doc.get("version_id")) != str(version_id)]
        self._rebuild_statistics()
        self._save()

    def search(
        self,
        query: str,
        *,
        k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        tokens = _tokenize(query)
        if not tokens or not self.documents:
            return []

        matched_docs: list[tuple[float, dict[str, Any]]] = []
        total_docs = max(len(self.documents), 1)

        for doc in self.documents:
            if filters and not self._matches_filters(doc, filters):
                continue
            if not doc.get("active", True):
                continue

            score = self._score_document(tokens, doc, total_docs)
            if score <= 0.0:
                continue

            enriched = dict(doc)
            enriched["bm25_score"] = score
            matched_docs.append((score, enriched))

        matched_docs.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in matched_docs[:k]]

    def _score_document(self, query_tokens: list[str], doc: dict[str, Any], total_docs: int) -> float:
        text = str(doc.get("text") or doc.get("chunk") or "")
        doc_tokens = _tokenize(text)
        if not doc_tokens:
            return 0.0

        freq = Counter(doc_tokens)
        dl = len(doc_tokens)
        score = 0.0

        for term in query_tokens:
            tf = freq.get(term, 0)
            if tf == 0:
                continue

            df = self.doc_freq.get(term, 0)
            idf = math.log(1.0 + ((total_docs - df + 0.5) / (df + 0.5)))
            denom = tf + self.k1 * (1.0 - self.b + self.b * (dl / max(self.avgdl, 1.0)))
            score += idf * ((tf * (self.k1 + 1.0)) / max(denom, 1e-9))

        return score

    def _rebuild_statistics(self) -> None:
        df_counter = defaultdict(int)
        total_len = 0

        for doc in self.documents:
            tokens = _tokenize(str(doc.get("text") or doc.get("chunk") or ""))
            total_len += len(tokens)

            seen_terms = set(tokens)
            for term in seen_terms:
                df_counter[term] += 1

        self.doc_freq = dict(df_counter)
        self.avgdl = total_len / len(self.documents) if self.documents else 0.0

    def _matches_filters(self, doc: dict[str, Any], filters: dict[str, Any]) -> bool:
        for key, expected in filters.items():
            if str(doc.get(key)) != str(expected):
                return False
        return True

    def _save(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "documents": self.documents,
            "doc_freq": self.doc_freq,
            "avgdl": self.avgdl,
        }
        self.index_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _load(self) -> None:
        if not self.index_path.exists():
            self.documents = []
            self.doc_freq = {}
            self.avgdl = 0.0
            return

        data = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.documents = list(data.get("documents", []))
        self.doc_freq = dict(data.get("doc_freq", {}))
        self.avgdl = float(data.get("avgdl", 0.0))