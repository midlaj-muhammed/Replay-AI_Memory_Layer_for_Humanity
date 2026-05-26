"""Shared test fixtures for Replay tests."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import List

import pytest

from replay.capture.atuin import Command


@pytest.fixture
def tmp_db(tmp_path: Path):
    """Create a temporary Atuin-style SQLite database."""
    db_path = tmp_path / "history.db"
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
    return conn, db_path


@pytest.fixture
def sample_commands() -> List[Command]:
    """Create sample commands for testing."""
    return [
        Command(
            id="cmd-1",
            timestamp=1779727275310187008,
            duration=602877792,
            exit_status=0,
            command="git status",
            cwd="/home/dev/api",
            hostname="laptop",
            session="session-1",
        ),
        Command(
            id="cmd-2",
            timestamp=1779727375310187008,
            duration=4667372431,
            exit_status=1,
            command="docker build -t webapp .",
            cwd="/home/dev/api",
            hostname="laptop",
            session="session-1",
        ),
        Command(
            id="cmd-3",
            timestamp=1779727475310187008,
            duration=1543741129,
            exit_status=0,
            command="docker build -t webapp .",
            cwd="/home/dev/api",
            hostname="laptop",
            session="session-1",
        ),
        Command(
            id="cmd-4",
            timestamp=1779728575310187008,
            duration=929403963,
            exit_status=0,
            command="ls -la",
            cwd="/home/dev/frontend",
            hostname="laptop",
            session="session-2",
        ),
    ]
