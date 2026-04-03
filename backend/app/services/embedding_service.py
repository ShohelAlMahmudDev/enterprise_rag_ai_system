
import logging
from functools import lru_cache

import requests
from langdetect import detect

from app.config import settings

logger = logging.getLogger(__name__)


class OllamaEmbeddingClient:
    def __init__(self, base_url: str, model_name: str, timeout: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = requests.post(
            f"{self.base_url}/api/embed",
            json={
                "model": self.model_name,
                "input": texts,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        embeddings = data.get("embeddings", [])

        if not embeddings:
            raise ValueError("Ollama returned no embeddings.")

        if len(embeddings) != len(texts):
            raise ValueError(
                f"Embedding count mismatch. Expected {len(texts)}, got {len(embeddings)}."
            )

        return embeddings


@lru_cache(maxsize=1)
def get_embedding_client() -> OllamaEmbeddingClient:
    logger.info(
        "Loading Ollama embedding client. base_url=%s model=%s",
        settings.OLLAMA_BASE_URL,
        settings.OLLAMA_EMBED_MODEL,
    )
    return OllamaEmbeddingClient(
        base_url=settings.OLLAMA_BASE_URL,
        model_name=settings.OLLAMA_EMBED_MODEL,
        timeout=settings.OLLAMA_TIMEOUT_SECONDS,
    )


class EmbeddingService:
    def __init__(self) -> None:
        self.client = get_embedding_client()
        self.dimension = self._detect_dimension()

    def _detect_dimension(self) -> int:
        test_vector = self.client.embed(["dimension check"])[0]
        if not test_vector:
            raise ValueError("Failed to detect embedding dimension from Ollama.")
        return len(test_vector)

    def detect_language(self, text: str) -> str:
        try:
            return detect(text[:5000]) if text.strip() else "unknown"
        except Exception:
            return "unknown"

    def chunk_text(
        self,
        text: str,
        chunk_size: int | None = None,
        overlap: int | None = None,
    ) -> list[str]:
        chunk_size = chunk_size or settings.DEFAULT_CHUNK_SIZE
        overlap = overlap or settings.DEFAULT_CHUNK_OVERLAP

        clean = " ".join(text.split())
        if not clean:
            return []

        if len(clean) <= chunk_size:
            return [clean]

        chunks: list[str] = []
        start = 0

        while start < len(clean):
            end = min(start + chunk_size, len(clean))

            if end < len(clean):
                boundary = clean.rfind(" ", start, end)
                if boundary > start + 50:
                    end = boundary

            chunk = clean[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= len(clean):
                break

            start = max(end - overlap, 0)

        return chunks

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        return self.client.embed(texts)