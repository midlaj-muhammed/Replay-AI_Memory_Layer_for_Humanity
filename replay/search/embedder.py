"""OpenAI embedding API wrapper with batching and retry."""

from __future__ import annotations

import hashlib
import time
from typing import List

import numpy as np
from openai import OpenAI

from replay.processing.secret_filter import filter_secrets, filter_secrets_batch

EMBEDDING_MODEL = "jina-embeddings-v3"
EMBEDDING_DIMENSIONS = 1024
BATCH_SIZE = 100
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds, doubles on each retry

JINA_BASE_URL = "https://api.jina.ai/v1"

# Model -> dimensions mapping
MODEL_DIMENSIONS = {
    "jina-embeddings-v3": 1024,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class EmbeddingError(Exception):
    """Raised when embedding fails after all retries."""


def local_embed(text: str, dim: int = 1024) -> list[float]:
    """Deterministic hash-based embedding for offline use. Same text → same vector."""
    h = hashlib.sha512(text.encode()).digest()
    raw = h * (dim // len(h) + 1)
    vec = np.array([b / 255.0 * 2 - 1 for b in raw[:dim]], dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


def local_embed_batch(texts: list[str], dim: int = 1024) -> list[list[float]]:
    """Batch version of local_embed."""
    return [local_embed(t, dim) for t in texts]


class Embedder:
    """Wraps the Jina AI / OpenAI-compatible embedding API with batching and retry."""

    def __init__(self, api_key: str, model: str = EMBEDDING_MODEL, base_url: str | None = None):
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        elif model.startswith("jina"):
            kwargs["base_url"] = JINA_BASE_URL
        self.client = OpenAI(**kwargs)
        self.model = model
        self.dimensions = MODEL_DIMENSIONS.get(model, EMBEDDING_DIMENSIONS)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts, automatically batching and filtering secrets.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (each a list of floats).

        Raises:
            EmbeddingError: If the API fails after all retries.
        """
        if not texts:
            return []

        # Filter secrets from all texts before embedding
        filtered = filter_secrets_batch(texts)

        all_embeddings: List[List[float]] = []
        for i in range(0, len(filtered), BATCH_SIZE):
            batch = filtered[i : i + BATCH_SIZE]
            embeddings = self._embed_batch(batch)
            all_embeddings.extend(embeddings)

        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string.

        Args:
            text: The query text to embed.

        Returns:
            Embedding vector as a list of floats.

        Raises:
            EmbeddingError: If the API fails after all retries.
        """
        filtered = filter_secrets(text)
        return self._embed_batch([filtered])[0]

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a single batch with exponential backoff retry."""
        delay = RETRY_DELAY
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=texts,
                )
                return [item.embedding for item in response.data]
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise EmbeddingError(
                        f"Embedding failed after {MAX_RETRIES} attempts: {e}"
                    ) from e
                time.sleep(delay)
                delay *= 2
        return []  # unreachable, but satisfies type checker
