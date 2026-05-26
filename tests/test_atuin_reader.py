"""Tests for the Atuin SQLite reader."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from replay.capture.atuin import ATUIN_INSTALL_URL, AtuinReader, Command


class TestReadValidDb:
    """Test reading commands from a valid Atuin database."""

    def test_read_returns_commands(self, tmp_db):
        """Should parse commands from a valid SQLite database."""
        conn, db_path = tmp_db
        conn.execute(
            "INSERT INTO history (id, timestamp, duration, exit_status, command, cwd, hostname, session) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("cmd-1", 1779727275310187008, 602877792, 0, "git status", "/home/dev", "laptop", "sess-1"),
        )
        conn.execute(
            "INSERT INTO history (id, timestamp, duration, exit_status, command, cwd, hostname, session) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("cmd-2", 1779727375310187008, 4667372431, 1, "docker build .", "/home/dev", "laptop", "sess-1"),
        )
        conn.commit()
        conn.close()

        reader = AtuinReader(db_path)
        commands = reader.read_history()

        assert len(commands) == 2
        assert isinstance(commands[0], Command)
        assert commands[0].command == "git status"
        assert commands[0].exit_status == 0
        assert commands[1].command == "docker build ."
        assert commands[1].exit_status == 1

    def test_read_sorted_by_timestamp(self, tmp_db):
        """Commands should be sorted oldest-first."""
        conn, db_path = tmp_db
        # Insert in reverse order
        conn.execute(
            "INSERT INTO history (id, timestamp, exit_status, command) VALUES (?, ?, ?, ?)",
            ("cmd-2", 2000, 0, "second"),
        )
        conn.execute(
            "INSERT INTO history (id, timestamp, exit_status, command) VALUES (?, ?, ?, ?)",
            ("cmd-1", 1000, 0, "first"),
        )
        conn.commit()
        conn.close()

        reader = AtuinReader(db_path)
        commands = reader.read_history()

        assert commands[0].command == "first"
        assert commands[1].command == "second"

    def test_read_preserves_metadata(self, tmp_db):
        """Should preserve cwd, hostname, session fields."""
        conn, db_path = tmp_db
        conn.execute(
            "INSERT INTO history (id, timestamp, duration, exit_status, command, cwd, hostname, session) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("cmd-1", 1000, 500, 0, "ls", "/tmp", "myhost", "mysess"),
        )
        conn.commit()
        conn.close()

        reader = AtuinReader(db_path)
        commands = reader.read_history()

        assert commands[0].cwd == "/tmp"
        assert commands[0].hostname == "myhost"
        assert commands[0].session == "mysess"
        assert commands[0].duration == 500


class TestReadMissingDb:
    """Test behavior when the Atuin database doesn't exist."""

    def test_raises_file_not_found(self, tmp_path: Path):
        """Should raise FileNotFoundError with install instructions."""
        missing = tmp_path / "nonexistent" / "history.db"
        reader = AtuinReader(missing)

        with pytest.raises(FileNotFoundError) as exc_info:
            reader.read_history()

        assert ATUIN_INSTALL_URL in str(exc_info.value)

    def test_error_message_includes_path(self, tmp_path: Path):
        """Error message should include the database path."""
        missing = tmp_path / "history.db"
        reader = AtuinReader(missing)

        with pytest.raises(FileNotFoundError) as exc_info:
            reader.read_history()

        assert str(missing) in str(exc_info.value)


class TestReadCorruptedDb:
    """Test behavior when the database is corrupted."""

    def test_raises_database_error(self, tmp_path: Path):
        """Should raise DatabaseError with rebuild instructions."""
        corrupted = tmp_path / "history.db"
        corrupted.write_bytes(b"not a valid sqlite database")

        reader = AtuinReader(corrupted)

        with pytest.raises(sqlite3.DatabaseError) as exc_info:
            reader.read_history()

        assert "corrupted" in str(exc_info.value).lower()
        assert "atuin history rebuild" in str(exc_info.value).lower()


class TestSessionGrouping:
    """Test that commands with session IDs are preserved."""

    def test_commands_have_session_ids(self, tmp_db):
        """Session IDs from Atuin should be preserved in Command objects."""
        conn, db_path = tmp_db
        conn.execute(
            "INSERT INTO history (id, timestamp, exit_status, command, session) VALUES (?, ?, ?, ?, ?)",
            ("cmd-1", 1000, 0, "ls", "session-abc"),
        )
        conn.execute(
            "INSERT INTO history (id, timestamp, exit_status, command, session) VALUES (?, ?, ?, ?, ?)",
            ("cmd-2", 2000, 0, "pwd", "session-abc"),
        )
        conn.execute(
            "INSERT INTO history (id, timestamp, exit_status, command, session) VALUES (?, ?, ?, ?, ?)",
            ("cmd-3", 3000, 0, "cd", "session-xyz"),
        )
        conn.commit()
        conn.close()

        reader = AtuinReader(db_path)
        commands = reader.read_history()

        assert commands[0].session == "session-abc"
        assert commands[1].session == "session-abc"
        assert commands[2].session == "session-xyz"

    def test_empty_session_handled(self, tmp_db):
        """Commands without session IDs should have empty session string."""
        conn, db_path = tmp_db
        conn.execute(
            "INSERT INTO history (id, timestamp, exit_status, command, session) VALUES (?, ?, ?, ?, ?)",
            ("cmd-1", 1000, 0, "ls", ""),
        )
        conn.commit()
        conn.close()

        reader = AtuinReader(db_path)
        commands = reader.read_history()

        assert commands[0].session == ""
