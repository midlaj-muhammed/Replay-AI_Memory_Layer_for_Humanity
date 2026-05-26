"""Tests for the query module (semantic search)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from replay.config import ReplayConfig
from replay.search.index import ChunkMetadata, SearchIndex
from replay.search.query import SearchError, build_index, ensure_index, refresh_index, search_query


def _fake_embedding(dim: int = 1024, seed: int = 0) -> list[float]:
    rng = np.random.RandomState(seed)
    vec = rng.randn(dim).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec.tolist()


def _seed_db(db_path: Path, commands: list[tuple]):
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE history (
            id TEXT PRIMARY KEY,
            timestamp INTEGER NOT NULL,
            duration INTEGER DEFAULT 0,
            exit_status INTEGER DEFAULT 0,
            command TEXT NOT NULL,
            cwd TEXT DEFAULT '',
            hostname TEXT DEFAULT '',
            session TEXT DEFAULT ''
        )
    """)
    for cmd in commands:
        conn.execute(
            "INSERT INTO history (id, timestamp, duration, exit_status, command, cwd, hostname, session) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            cmd,
        )
    conn.commit()
    conn.close()


class TestEnsureIndex:
    """Test auto-loading / auto-building index."""

    @patch("replay.search.query.Embedder")
    def test_loads_existing_index(self, mock_embedder_cls, tmp_path: Path):
        """If index exists on disk, should load it."""
        index_dir = tmp_path / "index"
        index = SearchIndex(index_dir)
        index.build([_fake_embedding()], [ChunkMetadata(
            chunk_text="exit:0 | /dev | ls",
            command="ls", exit_status=0, cwd="/dev", timestamp=1000, session_id="s1",
        )])
        index.save()

        config = ReplayConfig(index_path=index_dir, openai_api_key="sk-test")
        loaded = ensure_index(config)
        assert loaded.total_chunks == 1

    @patch("replay.search.query.Embedder")
    @patch("replay.search.query.AtuinReader")
    def test_auto_builds_when_missing(self, mock_reader_cls, mock_embedder_cls, tmp_path: Path):
        """If index doesn't exist, should auto-build."""
        # Mock Atuin reader
        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        from replay.capture.atuin import Command
        mock_reader.read_history.return_value = [
            Command(id="1", timestamp=1000, duration=0, exit_status=0,
                    command="git status", cwd="/dev", hostname="laptop", session="s1"),
        ]

        # Mock embedder
        mock_embedder = MagicMock()
        mock_embedder_cls.return_value = mock_embedder
        mock_embedder.embed_texts.return_value = [_fake_embedding()]

        config = ReplayConfig(
            index_path=tmp_path / "index",
            openai_api_key="sk-test",
        )
        index = ensure_index(config)
        assert index.total_chunks == 1

    def test_raises_on_missing_api_key(self, tmp_path: Path):
        config = ReplayConfig(index_path=tmp_path / "index", openai_api_key="")
        with pytest.raises(SearchError, match="No API key found"):
            ensure_index(config)


class TestBuildIndex:
    """Test explicit index build."""

    @patch("replay.search.query.Embedder")
    @patch("replay.search.query.AtuinReader")
    def test_builds_and_saves(self, mock_reader_cls, mock_embedder_cls, tmp_path: Path):
        from replay.capture.atuin import Command
        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.read_history.return_value = [
            Command(id="1", timestamp=1000, duration=0, exit_status=0,
                    command="git status", cwd="/dev", hostname="laptop", session="s1"),
            Command(id="2", timestamp=2000, duration=0, exit_status=1,
                    command="docker build .", cwd="/dev", hostname="laptop", session="s1"),
        ]

        mock_embedder = MagicMock()
        mock_embedder_cls.return_value = mock_embedder
        mock_embedder.embed_texts.return_value = [_fake_embedding(seed=0), _fake_embedding(seed=1)]

        config = ReplayConfig(
            index_path=tmp_path / "index",
            openai_api_key="sk-test",
        )
        index = build_index(config)
        assert index.total_chunks >= 1
        assert index.exists()

    def test_raises_without_api_key(self, tmp_path: Path):
        config = ReplayConfig(index_path=tmp_path / "index", openai_api_key="")
        with pytest.raises(SearchError, match="No API key found"):
            build_index(config)


class TestRefreshIndex:
    """Test incremental index refresh."""

    @patch("replay.search.query.Embedder")
    @patch("replay.search.query.AtuinReader")
    def test_adds_new_commands(self, mock_reader_cls, mock_embedder_cls, tmp_path: Path):
        from replay.capture.atuin import Command

        # Build initial index with one chunk
        index_dir = tmp_path / "index"
        index = SearchIndex(index_dir)
        index.build(
            [_fake_embedding(seed=0)],
            [ChunkMetadata(
                chunk_text="exit:0 | /dev | git status",
                command="git status", exit_status=0, cwd="/dev",
                timestamp=1000, session_id="s1",
            )],
        )
        index.save()

        # Mock reader returning old + new commands
        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.read_history.return_value = [
            Command(id="1", timestamp=1000, duration=0, exit_status=0,
                    command="git status", cwd="/dev", hostname="laptop", session="s1"),
            Command(id="2", timestamp=2000, duration=0, exit_status=0,
                    command="docker build .", cwd="/dev", hostname="laptop", session="s1"),
        ]

        mock_embedder = MagicMock()
        mock_embedder_cls.return_value = mock_embedder
        mock_embedder.embed_texts.return_value = [_fake_embedding(seed=1)]

        config = ReplayConfig(index_path=index_dir, openai_api_key="sk-test")
        idx, added = refresh_index(config)
        assert added >= 1
        assert idx.total_chunks > 1

    def test_raises_without_existing_index(self, tmp_path: Path):
        config = ReplayConfig(
            index_path=tmp_path / "nonexistent",
            openai_api_key="sk-test",
        )
        with pytest.raises(SearchError, match="No index found"):
            refresh_index(config)

    def test_raises_without_api_key(self, tmp_path: Path):
        config = ReplayConfig(index_path=tmp_path / "index", openai_api_key="")
        with pytest.raises(SearchError, match="No API key found"):
            refresh_index(config)


class TestSearchQuery:
    """Test the search_query function end-to-end."""

    @patch("replay.search.query.Embedder")
    def test_returns_filtered_results(self, mock_embedder_cls, tmp_path: Path):
        # Build a real index
        embeddings = [_fake_embedding(seed=i) for i in range(3)]
        metadata = [
            ChunkMetadata(
                chunk_text=f"exit:0 | /dev | cmd-{i}",
                command=f"cmd-{i}", exit_status=0, cwd="/dev",
                timestamp=1000 + i, session_id="s1",
            )
            for i in range(3)
        ]

        index_dir = tmp_path / "index"
        index = SearchIndex(index_dir)
        index.build(embeddings, metadata)
        index.save()

        mock_embedder = MagicMock()
        mock_embedder_cls.return_value = mock_embedder
        mock_embedder.embed_query.return_value = _fake_embedding(seed=0)

        config = ReplayConfig(index_path=index_dir, openai_api_key="sk-test")
        results = search_query(config, "test query", threshold=0.0, top_k=5)

        assert len(results) > 0
        assert all(r.score >= 0.0 for r in results)
