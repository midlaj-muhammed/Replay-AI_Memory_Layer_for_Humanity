"""Tests for the embedder module (OpenAI API wrapper)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from replay.search.embedder import (
    BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    Embedder,
    EmbeddingError,
)


def _fake_embedding(dim: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Generate a fake embedding vector."""
    return [0.1] * dim


def _make_mock_response(n: int = 1, dim: int = EMBEDDING_DIMENSIONS):
    """Create a mock OpenAI embedding response."""
    data = []
    for i in range(n):
        item = MagicMock()
        item.embedding = _fake_embedding(dim)
        data.append(item)
    response = MagicMock()
    response.data = data
    return response


class TestEmbedTexts:
    """Test batch embedding of texts."""

    @patch("replay.search.embedder.OpenAI")
    def test_single_batch(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.embeddings.create.return_value = _make_mock_response(3)

        embedder = Embedder(api_key="sk-test")
        result = embedder.embed_texts(["hello", "world", "foo"])

        assert len(result) == 3
        assert len(result[0]) == EMBEDDING_DIMENSIONS
        mock_client.embeddings.create.assert_called_once()

    @patch("replay.search.embedder.OpenAI")
    def test_multiple_batches(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.embeddings.create.side_effect = [
            _make_mock_response(BATCH_SIZE),
            _make_mock_response(10),
        ]

        embedder = Embedder(api_key="sk-test")
        texts = [f"text-{i}" for i in range(BATCH_SIZE + 10)]
        result = embedder.embed_texts(texts)

        assert len(result) == BATCH_SIZE + 10
        assert mock_client.embeddings.create.call_count == 2

    @patch("replay.search.embedder.OpenAI")
    def test_empty_texts(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        embedder = Embedder(api_key="sk-test")
        result = embedder.embed_texts([])

        assert result == []
        mock_client.embeddings.create.assert_not_called()

    @patch("replay.search.embedder.OpenAI")
    def test_filters_secrets_before_embedding(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.embeddings.create.return_value = _make_mock_response(1)

        embedder = Embedder(api_key="sk-test")
        embedder.embed_texts(["curl -H 'Authorization: Bearer sk-abc123def456ghi789jkl012mno345'"])

        # Check the input passed to the API has [REDACTED], not the secret
        call_args = mock_client.embeddings.create.call_args
        input_texts = call_args.kwargs.get("input") or call_args[1].get("input") or call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["input"]
        assert any("[REDACTED]" in t for t in input_texts)


class TestEmbedQuery:
    """Test single query embedding."""

    @patch("replay.search.embedder.OpenAI")
    def test_returns_single_vector(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.embeddings.create.return_value = _make_mock_response(1)

        embedder = Embedder(api_key="sk-test")
        result = embedder.embed_query("how did I fix Docker?")

        assert len(result) == EMBEDDING_DIMENSIONS
        mock_client.embeddings.create.assert_called_once()

    @patch("replay.search.embedder.OpenAI")
    def test_filters_query_secret(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.embeddings.create.return_value = _make_mock_response(1)

        embedder = Embedder(api_key="sk-test")
        embedder.embed_query("set API_KEY=supersecretkey123456789abcdef")

        call_args = mock_client.embeddings.create.call_args
        input_texts = call_args.kwargs.get("input") or call_args[1].get("input") or call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["input"]
        assert any("[REDACTED]" in t for t in input_texts)


class TestRetry:
    """Test retry logic on API failures."""

    @patch("replay.search.embedder.OpenAI")
    @patch("replay.search.embedder.time.sleep")
    def test_retries_on_failure(self, mock_sleep, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        # Fail twice, succeed on third
        mock_client.embeddings.create.side_effect = [
            Exception("rate limit"),
            Exception("rate limit"),
            _make_mock_response(1),
        ]

        embedder = Embedder(api_key="sk-test")
        result = embedder.embed_query("test")

        assert len(result) == EMBEDDING_DIMENSIONS
        assert mock_client.embeddings.create.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("replay.search.embedder.OpenAI")
    @patch("replay.search.embedder.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.embeddings.create.side_effect = Exception("permanent failure")

        embedder = Embedder(api_key="sk-test")
        with pytest.raises(EmbeddingError, match="failed after"):
            embedder.embed_query("test")

        assert mock_client.embeddings.create.call_count == 3
