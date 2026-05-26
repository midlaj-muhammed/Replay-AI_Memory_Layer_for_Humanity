"""Semantic search query handler — ties embedder + index together."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from replay.capture.atuin import AtuinReader, Command
from replay.config import ReplayConfig
from replay.processing.chunker import Chunk, chunk_sessions
from replay.processing.cluster import cluster_commands
from replay.search.embedder import Embedder, EmbeddingError
from replay.search.index import SearchIndex, SearchResult, ChunkMetadata


class SearchError(Exception):
    """Raised when search fails."""


def ensure_index(config: ReplayConfig) -> SearchIndex:
    """Load or auto-build the search index.

    If the index exists on disk, loads it. Otherwise, builds it from
    Atuin history (equivalent to `replay init`).

    Args:
        config: Replay configuration.

    Returns:
        A loaded SearchIndex ready for queries.

    Raises:
        SearchError: If the API key is missing or building fails.
    """
    index = SearchIndex(config.index_path)

    if index.exists():
        index.load()
        return index

    # Auto-build
    if not config.openai_api_key:
        raise SearchError(
            "No API key found.\n"
            "Set JINA_API_KEY (free, recommended) or OPENAI_API_KEY:\n"
            "  export JINA_API_KEY='your-key'  # https://jina.ai\n"
            "  export OPENAI_API_KEY='sk-...'"
        )

    return _build_index(config, index)


def build_index(config: ReplayConfig) -> SearchIndex:
    """Build a fresh search index from Atuin history.

    Args:
        config: Replay configuration.

    Returns:
        A newly built SearchIndex.

    Raises:
        SearchError: If the API key is missing or building fails.
    """
    if not config.openai_api_key:
        raise SearchError(
            "No API key found.\n"
            "Set JINA_API_KEY (free, recommended) or OPENAI_API_KEY:\n"
            "  export JINA_API_KEY='your-key'  # https://jina.ai\n"
            "  export OPENAI_API_KEY='sk-...'"
        )

    index = SearchIndex(config.index_path)
    index.clear()  # Remove any stale index
    return _build_index(config, index)


def refresh_index(config: ReplayConfig) -> tuple[SearchIndex, int]:
    """Incrementally update the index with new commands.

    Finds commands added since the last index build and adds only those.

    Args:
        config: Replay configuration.

    Returns:
        Tuple of (loaded index, number of new chunks added).

    Raises:
        SearchError: If the API key is missing, no index exists, or update fails.
    """
    if not config.openai_api_key:
        raise SearchError(
            "No API key found.\n"
            "Set JINA_API_KEY (free, recommended) or OPENAI_API_KEY:\n"
            "  export JINA_API_KEY='your-key'  # https://jina.ai\n"
            "  export OPENAI_API_KEY='sk-...'"
        )

    index = SearchIndex(config.index_path)
    if not index.exists():
        raise SearchError(
            "No index found. Run `replay init` first."
        )

    index.load()

    # Find the latest timestamp in the existing index
    if index.metadata:
        latest_ts = max(m.timestamp for m in index.metadata)
    else:
        latest_ts = 0

    # Read all commands and filter to new ones
    db_path = config.atuin_db_path
    reader = AtuinReader(db_path)
    all_commands = reader.read_history()
    new_commands = [c for c in all_commands if c.timestamp > latest_ts]

    if not new_commands:
        return index, 0

    # Cluster and chunk only new commands
    new_sessions = cluster_commands(new_commands)
    chunks = chunk_sessions(new_sessions)

    if not chunks:
        return index, 0

    # Filter out chunks we already have (by timestamp)
    existing_ts = {m.timestamp for m in index.metadata}
    new_chunks = [c for c in chunks if c.timestamp not in existing_ts]

    if not new_chunks:
        return index, 0

    # Embed and add
    embedder = Embedder(api_key=config.openai_api_key, model=config.embedding_model, base_url=config.openai_base_url)
    texts = [c.chunk_text for c in new_chunks]
    embeddings = embedder.embed_texts(texts)

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

    embedder = Embedder(api_key=config.openai_api_key, model=config.embedding_model, base_url=config.openai_base_url)
    query_vector = embedder.embed_query(query)

    results = index.search(query_vector, top_k=top_k * 3)  # Over-fetch for filtering

    # Filter by threshold
    filtered = [r for r in results if r.score >= threshold]

    return filtered[:top_k]


def _build_index(config: ReplayConfig, index: SearchIndex) -> SearchIndex:
    """Internal: build index from Atuin history."""
    db_path = config.atuin_db_path
    reader = AtuinReader(db_path)
    commands = reader.read_history()

    sessions = cluster_commands(commands)
    chunks = chunk_sessions(sessions)

    if not chunks:
        raise SearchError("No commands found to index.")

    embedder = Embedder(api_key=config.openai_api_key, model=config.embedding_model, base_url=config.openai_base_url)
    texts = [c.chunk_text for c in chunks]
    embeddings = embedder.embed_texts(texts)

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
