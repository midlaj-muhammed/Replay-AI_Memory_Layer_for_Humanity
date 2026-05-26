"""OpenAI embedding API wrapper with batching and retry."""

from __future__ import annotations

import time
from typing import List

from openai import OpenAI

from replay.processing.secret_filter import filter_secrets, filter_secrets_batch

EMBEDDING_MODEL = "jina-embeddings-v3"
EMBEDDING_DIMENSIONS = 1024
BATCH_SIZE = 100
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds, doubles on each retry

JINA_BASE_URL = "https://api.jina.ai/v1"


class EmbeddingError(Exception):
    """Raised when embedding fails after all retries."""


class Embedder:
    """Wraps the Jina AI / OpenAI-compatible embedding API with batching and retry."""

    def __init__(self, api_key: str, model: str = EMBEDDING_MODEL, base_url: str | None = None):
        kwargs: dict = {"api_key": api_key}
        kwargs["base_url"] = base_url or JINA_BASE_URL
        self.client = OpenAI(**kwargs)
        self.model = model

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
