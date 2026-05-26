"""Tests for Day 5 polish features: stats, config, export commands."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner

import pytest
import numpy as np

from replay.cli import app
from replay.config import ReplayConfig
from replay.search.index import SearchIndex, ChunkMetadata


runner = CliRunner()


def _fake_embedding(dim: int = 1024, seed: int = 0) -> list[float]:
    rng = np.random.RandomState(seed)
    vec = rng.randn(dim).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec.tolist()


def _seed_db(db_path: Path):
    """Create a minimal Atuin-compatible DB."""
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
    conn.execute(
        "INSERT INTO history VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("t1", 1000, 0, 0, "git status", "/dev", "laptop", "s1"),
    )
    conn.execute(
        "INSERT INTO history VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("t2", 2000, 0, 1, "docker build .", "/dev", "laptop", "s1"),
    )
    conn.execute(
        "INSERT INTO history VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("t3", 3000, 0, 0, "docker build -t app .", "/dev", "laptop", "s1"),
    )
    conn.commit()
    conn.close()


class TestStatsCommand:
    """Test the `replay stats` command."""

    def test_stats_without_index(self, tmp_path: Path, monkeypatch):
        """Stats command works when no index exists."""
        db_path = tmp_path / "history.db"
        _seed_db(db_path)

        # Redirect config to use temp paths
        config = ReplayConfig(
            atuin_db_path=db_path,
            index_path=tmp_path / "index",
        )
        monkeypatch.setattr(ReplayConfig, "load", classmethod(lambda cls: config))

        result = runner.invoke(app, ["stats", "--plain"])
        assert result.exit_code == 0
        assert "Commands:" in result.output
        assert "Sessions:" in result.output
        assert "no index" in result.output

    def test_stats_with_index(self, tmp_path: Path, monkeypatch):
        """Stats command shows index info when index exists."""
        db_path = tmp_path / "history.db"
        _seed_db(db_path)

        # Build a small index
        index_dir = tmp_path / "index"
        index = SearchIndex(index_dir)
        index.build(
            [_fake_embedding(seed=0), _fake_embedding(seed=1)],
            [
                ChunkMetadata(
                    chunk_text="exit:0 | /dev | git status",
                    command="git status", exit_status=0, cwd="/dev",
                    timestamp=1000, session_id="s1",
                ),
                ChunkMetadata(
                    chunk_text="exit:1 | /dev | docker build .",
                    command="docker build .", exit_status=1, cwd="/dev",
                    timestamp=2000, session_id="s1",
                ),
            ],
        )
        index.save()

        config = ReplayConfig(
            atuin_db_path=db_path,
            index_path=index_dir,
        )
        monkeypatch.setattr(ReplayConfig, "load", classmethod(lambda cls: config))

        result = runner.invoke(app, ["stats", "--plain"])
        assert result.exit_code == 0
        assert "2" in result.output  # 2 chunks
        assert "KB" in result.output

    def test_stats_rich_output(self, tmp_path: Path, monkeypatch):
        """Stats command with Rich TUI output."""
        db_path = tmp_path / "history.db"
        _seed_db(db_path)

        config = ReplayConfig(
            atuin_db_path=db_path,
            index_path=tmp_path / "index",
        )
        monkeypatch.setattr(ReplayConfig, "load", classmethod(lambda cls: config))

        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "Replay Stats" in result.output


class TestConfigCommand:
    """Test the `replay config` command."""

    def test_config_plain(self, monkeypatch):
        """Config command shows configuration."""
        config = ReplayConfig(
            openai_api_key="sk-test123456789abcdef",
            embedding_model="jina-embeddings-v3",
            index_path=Path("/tmp/test-index"),
        )
        monkeypatch.setattr(ReplayConfig, "load", classmethod(lambda cls: config))

        result = runner.invoke(app, ["config", "--plain"])
        assert result.exit_code == 0
        assert "Replay Config" in result.output
        assert "sk-test1..." in result.output  # masked key (first 8 chars)
        assert "jina-embeddings-v3" in result.output

    def test_config_no_api_key(self, monkeypatch):
        """Config command handles missing API key."""
        config = ReplayConfig(openai_api_key="")
        monkeypatch.setattr(ReplayConfig, "load", classmethod(lambda cls: config))

        result = runner.invoke(app, ["config", "--plain"])
        assert result.exit_code == 0
        assert "not set" in result.output

    def test_config_rich_output(self, monkeypatch):
        """Config command with Rich panel output."""
        config = ReplayConfig(openai_api_key="sk-test123456789")
        monkeypatch.setattr(ReplayConfig, "load", classmethod(lambda cls: config))

        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "Replay Config" in result.output


class TestExportCommand:
    """Test the `replay export` command."""

    def test_export_no_index(self, tmp_path: Path, monkeypatch):
        """Export fails gracefully when no index exists."""
        config = ReplayConfig(index_path=tmp_path / "nonexistent")
        monkeypatch.setattr(ReplayConfig, "load", classmethod(lambda cls: config))

        result = runner.invoke(app, ["export"])
        assert result.exit_code == 1
        assert "No index found" in result.output

    def test_export_to_stdout(self, tmp_path: Path, monkeypatch):
        """Export prints JSON to stdout."""
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

        config = ReplayConfig(index_path=index_dir)
        monkeypatch.setattr(ReplayConfig, "load", classmethod(lambda cls: config))

        result = runner.invoke(app, ["export"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_chunks"] == 1
        assert data["chunks"][0]["command"] == "git status"

    def test_export_to_file(self, tmp_path: Path, monkeypatch):
        """Export writes JSON to a file."""
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

        output_file = tmp_path / "export.json"
        config = ReplayConfig(index_path=index_dir)
        monkeypatch.setattr(ReplayConfig, "load", classmethod(lambda cls: config))

        result = runner.invoke(app, ["export", "--output", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()

        data = json.loads(output_file.read_text())
        assert data["total_chunks"] == 1


class TestConfigSummary:
    """Test ReplayConfig.summary_lines()."""

    def test_with_api_key(self):
        config = ReplayConfig(openai_api_key="sk-abcdefgh123456789")
        lines = config.summary_lines()
        assert any("sk-abcde..." in line for line in lines)
        # Should mask the key
        assert not any("123456789" in line for line in lines)

    def test_without_api_key(self):
        config = ReplayConfig(openai_api_key="")
        lines = config.summary_lines()
        assert any("not set" in line for line in lines)

    def test_with_base_url(self):
        config = ReplayConfig(openai_base_url="https://custom.api.com/v1")
        lines = config.summary_lines()
        assert any("custom.api.com" in line for line in lines)

    def test_without_base_url(self):
        config = ReplayConfig(openai_base_url=None)
        lines = config.summary_lines()
        assert any("default" in line for line in lines)
