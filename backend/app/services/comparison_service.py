
import re
from typing import Any

from app.services.retrieval_service import RetrievalService


class ComparisonService:
    """Minimal comparison mode.

    It extracts likely comparison targets from the user's question and asks retrieval
    for a slightly broader result window so the LLM can synthesize differences.
    """

    def __init__(self) -> None:
        self.retrieval = RetrievalService()

    def run(self, question: str) -> list[dict[str, Any]]:
        expanded_query = self._expand_comparison_query(question)
        return self.retrieval.search(expanded_query, k=8)

    def _expand_comparison_query(self, question: str) -> str:
        cleaned = " ".join(question.split())
        # Light heuristic for common comparison patterns.
        versions = re.findall(r"v?\d+(?:\.\d+)+", cleaned, flags=re.IGNORECASE)
        if len(versions) >= 2:
            return (
                f"Compare differences between {versions[0]} and {versions[1]}. "
                f"Focus on changed behavior, states, interfaces, and technical notes. Original question: {cleaned}"
            )
        return f"Compare the relevant items and identify differences. Original question: {cleaned}"
