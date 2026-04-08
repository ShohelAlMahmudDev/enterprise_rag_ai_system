import re
from dataclasses import dataclass


@dataclass(slots=True)
class RewrittenQuery:
    original: str
    rewritten: str
    is_lookup: bool
    detected_numbers: list[str]
    detected_fields: list[str]


class QueryRewriteService:
    """
    Deterministic query rewriting for technical/table lookups.

    Goals:
    - preserve exact values and field names
    - expand vague short queries into retrieval-friendly form
    - avoid LLM dependency for rewriting
    """

    FIELD_PATTERNS = [
        "action",
        "status",
        "messagehandle",
        "datatype",
        "data type",
        "field",
        "code",
        "value",
        "row",
        "column",
        "sheet",
        "table",
        "page",
    ]

    def rewrite(self, question: str) -> RewrittenQuery:
        original = (question or "").strip()
        if not original:
            return RewrittenQuery(
                original="",
                rewritten="",
                is_lookup=False,
                detected_numbers=[],
                detected_fields=[],
            )

        lowered = original.lower()
        numbers = re.findall(r"\b\d+\b", lowered)
        detected_fields = [field for field in self.FIELD_PATTERNS if field in lowered]
        is_lookup = self._is_lookup_query(lowered, numbers, detected_fields)

        rewritten = original
        if is_lookup:
            rewritten = self._rewrite_lookup_query(original, lowered, numbers, detected_fields)

        return RewrittenQuery(
            original=original,
            rewritten=rewritten,
            is_lookup=is_lookup,
            detected_numbers=numbers,
            detected_fields=detected_fields,
        )

    def _is_lookup_query(self, lowered: str, numbers: list[str], fields: list[str]) -> bool:
        if numbers and len(lowered) <= 120:
            return True

        patterns = [
            r"\bwhat is action\s+\d+\b",
            r"\baction\s+\d+\b",
            r"\bstatus\s+\d+\b",
            r"\btype of\b",
            r"\bdatatype\b",
            r"\bdata type\b",
            r"\bwhat does\b",
            r"\bmeaning of\b",
            r"\bvalue of\b",
            r"\bfield\b",
        ]
        if any(re.search(pattern, lowered) for pattern in patterns):
            return True

        return bool(fields) and len(lowered.split()) <= 12

    def _rewrite_lookup_query(
        self,
        original: str,
        lowered: str,
        numbers: list[str],
        detected_fields: list[str],
    ) -> str:
        parts: list[str] = [original]

        if numbers:
            parts.append("exact numeric match")
            parts.append("exact mapping")
            parts.append("exact code value")

        if "action" in lowered:
            parts.append("action mapping meaning")
        if "status" in lowered:
            parts.append("status field meaning")
        if "messagehandle" in lowered:
            parts.append("messageHandle field datatype definition")
        if "datatype" in lowered or "data type" in lowered or "type of" in lowered:
            parts.append("exact datatype field type")
        if "table" in lowered or "column" in lowered or "row" in lowered:
            parts.append("table row column exact match")

        return " | ".join(dict.fromkeys(parts))