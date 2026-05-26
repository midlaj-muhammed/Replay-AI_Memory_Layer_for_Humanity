"""Tests for the FAISS index module."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from replay.search.index import ChunkMetadata, SearchIndex, SearchResult


def _fake_embedding(dim: int = 1024, seed: int = 0) -> list[float]:
    """Generate a deterministic fake embedding."""
    rng = np.random.RandomState(seed)
    vec = rng.randn(dim).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec.tolist()


def _make_metadata(
    command: str = "docker build .",
    exit_status: int = 0,
    cwd: str = "/home/dev",
    timestamp: int = 1000,
    session_id: str = "s1",
) -> ChunkMetadata:
    return ChunkMetadata(
        chunk_text=f"exit:{exit_status} | {cwd} | {command}",
        command=command,
        exit_status=exit_status,
        cwd=cwd,
        timestamp=timestamp,
        session_id=session_id,
    )


class TestBuildIndex:
    """Test building a new index."""

    def test_build_and_search(self, tmp_path: Path):
        embeddings = [_fake_embedding(seed=i) for i in range(5)]
        metadata = [_make_metadata(command=f"cmd-{i}", timestamp=1000 + i) for i in range(5)]

        index = SearchIndex(tmp_path / "index")
        index.build(embeddings, metadata)

        assert index.total_chunks == 5
        assert len(index.metadata) == 5

    def test_build_empty_raises(self, tmp_path: Path):
        index = SearchIndex(tmp_path / "index")
        with pytest.raises(ValueError, match="empty"):
            index.build([], [])

    def test_build_mismatched_lengths_raises(self, tmp_path: Path):
        index = SearchIndex(tmp_path / "index")
        with pytest.raises(ValueError, match="mismatch"):
            index.build([_fake_embedding()], [_make_metadata(), _make_metadata()])


class TestSaveLoad:
    """Test atomic save and load persistence."""

    def test_save_and_load(self, tmp_path: Path):
        embeddings = [_fake_embedding(seed=i) for i in range(3)]
        metadata = [_make_metadata(command=f"cmd-{i}", timestamp=1000 + i) for i in range(3)]

        index_dir = tmp_path / "index"
        index = SearchIndex(index_dir)
        index.build(embeddings, metadata)
        index.save()

        assert (index_dir / "vectors.faiss").exists()
        assert (index_dir / "metadata.json").exists()

        # Load in a fresh instance
        index2 = SearchIndex(index_dir)
        index2.load()

        assert index2.total_chunks == 3
        assert len(index2.metadata) == 3
        assert index2.metadata[0].command == "cmd-0"
        assert index2.metadata[2].command == "cmd-2"

    def test_exists_returns_false_when_missing(self, tmp_path: Path):
        index = SearchIndex(tmp_path / "nonexistent")
        assert index.exists() is False

    def test_exists_returns_true_when_saved(self, tmp_path: Path):
        index = SearchIndex(tmp_path / "index")
        index.build([_fake_embedding()], [_make_metadata()])
        index.save()
        assert index.exists() is True

    def test_load_missing_raises(self, tmp_path: Path):
        index = SearchIndex(tmp_path / "nonexistent")
        with pytest.raises(FileNotFoundError, match="No index found"):
            index.load()


class TestSearch:
    """Test vector similarity search."""

    def test_search_returns_ranked_results(self, tmp_path: Path):
        # Create 3 embeddings, query should be closest to the one with matching seed
        embeddings = [_fake_embedding(seed=i) for i in range(3)]
        metadata = [
            _make_metadata(command="git status", timestamp=1000),
            _make_metadata(command="docker build .", timestamp=2000),
            _make_metadata(command="npm install", timestamp=3000),
        ]

        index = SearchIndex(tmp_path / "index")
        index.build(embeddings, metadata)

        # Query with same seed as first embedding
        query_vec = _fake_embedding(seed=0)
        results = index.search(query_vec, top_k=3)

        assert len(results) == 3
        assert all(isinstance(r, SearchResult) for r in results)
        # Scores should be descending
        assert results[0].score >= results[1].score >= results[2].score
        # First result should be exact match (seed=0)
        assert results[0].metadata.command == "git status"

    def test_search_top_k_limit(self, tmp_path: Path):
        embeddings = [_fake_embedding(seed=i) for i in range(10)]
        metadata = [_make_metadata(command=f"cmd-{i}", timestamp=1000 + i) for i in range(10)]

        index = SearchIndex(tmp_path / "index")
        index.build(embeddings, metadata)

        results = index.search(_fake_embedding(seed=0), top_k=3)
        assert len(results) == 3

    def test_search_empty_index(self, tmp_path: Path):
        index = SearchIndex(tmp_path / "index")
        # No build — index is None
        results = index.search(_fake_embedding(), top_k=5)
        assert results == []

    def test_search_result_properties(self, tmp_path: Path):
        embeddings = [_fake_embedding(seed=0)]
        metadata = [_make_metadata(command="test", exit_status=1, cwd="/tmp", timestamp=42)]

        index = SearchIndex(tmp_path / "index")
        index.build(embeddings, metadata)

        results = index.search(_fake_embedding(seed=0), top_k=1)
        assert len(results) == 1

        r = results[0]
        assert r.metadata.exit_status == 1
        assert r.metadata.cwd == "/tmp"
        assert r.metadata.timestamp == 42
        assert 0 <= r.score_pct <= 100


class TestAdd:
    """Test incremental add to existing index."""

    def test_add_to_existing(self, tmp_path: Path):
        embeddings = [_fake_embedding(seed=i) for i in range(2)]
        metadata = [_make_metadata(command=f"cmd-{i}", timestamp=1000 + i) for i in range(2)]

        index = SearchIndex(tmp_path / "index")
        index.build(embeddings, metadata)
        assert index.total_chunks == 2

        # Add more
        new_embeddings = [_fake_embedding(seed=i + 10) for i in range(3)]
        new_metadata = [_make_metadata(command=f"new-{i}", timestamp=2000 + i) for i in range(3)]
        total = index.add(new_embeddings, new_metadata)

        assert total == 5
        assert index.total_chunks == 5

    def test_add_empty_is_noop(self, tmp_path: Path):
        index = SearchIndex(tmp_path / "index")
        index.build([_fake_embedding()], [_make_metadata()])
        total = index.add([], [])
        assert total == 1

    def test_add_without_build_raises(self, tmp_path: Path):
        index = SearchIndex(tmp_path / "index")
        with pytest.raises(RuntimeError, match="not loaded"):
            index.add([_fake_embedding()], [_make_metadata()])


class TestClear:
    """Test index clearing."""

    def test_clear_removes_files(self, tmp_path: Path):
        index = SearchIndex(tmp_path / "index")
        index.build([_fake_embedding()], [_make_metadata()])
        index.save()

        assert index.exists()
        index.clear()
        assert not index.exists()
        assert index.total_chunks == 0


class TestSearchResultScore:
    """Test SearchResult score properties."""

    def test_score_pct_high(self):
        sr = SearchResult(score=0.87, metadata=_make_metadata())
        assert sr.score_pct == 87

    def test_score_pct_low(self):
        sr = SearchResult(score=0.12, metadata=_make_metadata())
        assert sr.score_pct == 12

    def test_score_pct_clamped_above(self):
        sr = SearchResult(score=1.5, metadata=_make_metadata())
        assert sr.score_pct == 100

    def test_score_pct_clamped_below(self):
        sr = SearchResult(score=-0.1, metadata=_make_metadata())
        assert sr.score_pct == 0
