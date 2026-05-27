"""Semantic search query handler — ties embedder + index together."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from replay.capture.atuin import AtuinReader, Command
from replay.config import ReplayConfig
from replay.processing.chunker import Chunk, chunk_sessions
from replay.processing.cluster import cluster_commands
from replay.search.embedder import Embedder, EmbeddingError, local_embed, local_embed_batch
from replay.search.index import SearchIndex, SearchResult, ChunkMetadata


class SearchError(Exception):
    """Raised when search fails."""


def ensure_index(config: ReplayConfig) -> SearchIndex:
    """Load or auto-build the search index."""
    index = SearchIndex(config.index_path)

    if index.exists():
        index.load()
        return index

    # Auto-build (uses local embeddings if no API key)
    return _build_index(config, index)


def build_index(config: ReplayConfig) -> SearchIndex:
    """Build a fresh search index from Atuin history."""
    index = SearchIndex(config.index_path)
    index.clear()
    return _build_index(config, index)


def refresh_index(config: ReplayConfig, source: str = "auto") -> tuple[SearchIndex, int]:
    """Incrementally update the index with new commands."""
    from replay.capture.bash import read_history

    index = SearchIndex(config.index_path)
    if not index.exists():
        raise SearchError("No index found. Run `replay init` first.")

    index.load()

    if index.metadata:
        latest_ts = max(m.timestamp for m in index.metadata)
    else:
        latest_ts = 0

    all_commands = read_history(source=source)
    new_commands = [c for c in all_commands if c.timestamp > latest_ts]

    if not new_commands:
        return index, 0

    new_sessions = cluster_commands(new_commands)
    chunks = chunk_sessions(new_sessions)

    if not chunks:
        return index, 0

    existing_ts = {m.timestamp for m in index.metadata}
    new_chunks = [c for c in chunks if c.timestamp not in existing_ts]

    if not new_chunks:
        return index, 0

    texts = [c.chunk_text for c in new_chunks]
    if config.openai_api_key:
        embedder = Embedder(api_key=config.openai_api_key, model=config.embedding_model, base_url=config.openai_base_url)
        embeddings = embedder.embed_texts(texts)
    else:
        embeddings = local_embed_batch(texts)

    metadata = [
        ChunkMetadata(
            chunk_text=c.chunk_text,
            command=c.command.command,
            exit_status=c.command.exit_status,
            cwd=c.command.cwd,
            timestamp=c.command.timestamp,
            session_id=c.session_id,
        )
        for c in new_chunks
    ]

    index.add(embeddings, metadata)
    index.save()

    return index, len(new_chunks)


def search_query(
    config: ReplayConfig,
    query: str,
    threshold: float = 0.3,
    top_k: int = 5,
) -> List[SearchResult]:
    """Run a semantic search query.

    Args:
        config: Replay configuration.
        query: Natural language search query.
        threshold: Minimum similarity score (0-1).
        top_k: Maximum number of results.

    Returns:
        List of SearchResult objects above the threshold, sorted by score.

    Raises:
        SearchError: If the index doesn't exist or embedding fails.
    """
    index = ensure_index(config)

    if config.openai_api_key and config.openai_base_url is None:
        # Only use API embedder when we have a key with no incompatible base URL
        # (i.e. Jina key or direct OpenAI key, not a proxy gateway)
        try:
            embedder = Embedder(api_key=config.openai_api_key, model=config.embedding_model, base_url=config.openai_base_url)
            query_vector = embedder.embed_query(query)
        except (EmbeddingError, Exception):
            query_vector = local_embed(query)
    else:
        query_vector = local_embed(query)

    results = index.search(query_vector, top_k=top_k * 3)  # Over-fetch for filtering

    # Filter by threshold
    filtered = [r for r in results if r.score >= threshold]

    return filtered[:top_k]


def _build_index(config: ReplayConfig, index: SearchIndex, source: str = "auto") -> SearchIndex:
    """Internal: build index from history."""
    from replay.capture.bash import read_history
    commands = read_history(source=source)

    sessions = cluster_commands(commands)
    chunks = chunk_sessions(sessions)

    if not chunks:
        raise SearchError("No commands found to index.")

    texts = [c.chunk_text for c in chunks]
    if config.openai_api_key:
        embedder = Embedder(api_key=config.openai_api_key, model=config.embedding_model, base_url=config.openai_base_url)
        embeddings = embedder.embed_texts(texts)
    else:
        embeddings = local_embed_batch(texts)

    metadata = [
        ChunkMetadata(
            chunk_text=c.chunk_text,
            command=c.command.command,
            exit_status=c.command.exit_status,
            cwd=c.command.cwd,
            timestamp=c.command.timestamp,
            session_id=c.session_id,
        )
        for c in chunks
    ]

    index.build(embeddings, metadata)
    index.save()

    return index
