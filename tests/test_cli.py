"""Tests for the CLI commands."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from replay.cli import app

runner = CliRunner()


def _seed_db(db_path: Path, commands: list[tuple]):
    """Seed a test Atuin database with commands."""
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


class TestReplayList:
    """Tests for `replay list`."""

    def test_list_with_data(self, tmp_path: Path):
        """Should display sessions from a seeded database."""
        db = tmp_path / "history.db"
        _seed_db(db, [
            ("1", 1000, 100, 0, "git status", "/home/dev", "laptop", "s1"),
            ("2", 2000, 200, 1, "docker build .", "/home/dev", "laptop", "s1"),
            ("3", 3000, 50, 0, "ls", "/tmp", "laptop", "s2"),
        ])

        result = runner.invoke(app, ["list", "--db", str(db)])

        assert result.exit_code == 0
        assert "2 sessions" in result.output or "Found 2" in result.output

    def test_list_empty_db(self, tmp_path: Path):
        """Should handle empty database gracefully."""
        db = tmp_path / "history.db"
        _seed_db(db, [])

        result = runner.invoke(app, ["list", "--db", str(db)])

        assert result.exit_code == 0
        assert "No" in result.output

    def test_list_missing_db(self, tmp_path: Path):
        """Should show error for missing database."""
        db = tmp_path / "nonexistent.db"

        result = runner.invoke(app, ["list", "--db", str(db)])

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_list_plain_output(self, tmp_path: Path):
        """--plain flag should produce text without Rich markup."""
        db = tmp_path / "history.db"
        _seed_db(db, [
            ("1", 1000, 100, 0, "git status", "/home/dev", "laptop", "s1"),
        ])

        result = runner.invoke(app, ["list", "--db", str(db), "--plain"])

        assert result.exit_code == 0
        # Plain output should not have Rich markup characters
        assert "\x1b[" not in result.output

    def test_list_limit(self, tmp_path: Path):
        """--limit should cap the number of sessions shown."""
        db = tmp_path / "history.db"
        _seed_db(db, [
            ("1", 1000, 100, 0, "cmd1", "/a", "h", "s1"),
            ("2", 2000, 100, 0, "cmd2", "/b", "h", "s2"),
            ("3", 3000, 100, 0, "cmd3", "/c", "h", "s3"),
        ])

        result = runner.invoke(app, ["list", "--db", str(db), "--plain", "--limit", "2"])

        assert result.exit_code == 0
