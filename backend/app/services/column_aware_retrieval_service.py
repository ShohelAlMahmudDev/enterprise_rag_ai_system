import re
from typing import Any


class ColumnAwareRetrievalService:
    """
    Scores whether a chunk/record matches the requested field/column semantics.
    """

    FIELD_ALIASES = {
        "action": {"action", "code", "id"},
        "status": {"status", "state"},
        "datatype": {"datatype", "data type", "type"},
        "messagehandle": {"messagehandle", "message handle"},
        "value": {"value", "meaning", "description"},
    }

    def score(self, question: str, item: dict[str, Any]) -> float:
        lowered = (question or "").lower()
        if not lowered:
            return 0.0

        requested_fields = self._detect_requested_fields(lowered)
        if not requested_fields:
            return 0.0

        candidate_parts = [
            str(item.get("attribute_name") or ""),
            str(item.get("heading") or ""),
            str(item.get("title") or ""),
            str(item.get("type") or ""),
            str(item.get("text") or item.get("chunk") or ""),
        ]

        columns = item.get("columns") or {}
        candidate_parts.extend([f"{k} {v}" for k, v in columns.items()])

        haystack = " ".join(candidate_parts).lower()

        score = 0.0
        for field in requested_fields:
            aliases = self.FIELD_ALIASES.get(field, {field})
            if any(alias in haystack for alias in aliases):
                score += 0.25

        return min(score, 1.0)

    def _detect_requested_fields(self, lowered: str) -> set[str]:
        detected: set[str] = set()
        for canonical, aliases in self.FIELD_ALIASES.items():
            if any(alias in lowered for alias in aliases):
                detected.add(canonical)
        return detected