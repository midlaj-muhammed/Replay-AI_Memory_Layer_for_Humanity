"""Read command history from Atuin's SQLite database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

ATUIN_DB_PATH = Path.home() / ".local" / "share" / "atuin" / "history.db"
ATUIN_INSTALL_URL = "https://atuin.sh/docs/installation"


@dataclass
class Command:
    """A single command from Atuin history."""

    id: str
    timestamp: int
    duration: int
    exit_status: int
    command: str
    cwd: str
    hostname: str
    session: str


class AtuinReader:
    """Reads command history from Atuin's SQLite database."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or ATUIN_DB_PATH

    def read_history(self) -> List[Command]:
        """Read all commands from Atuin history.

        Returns:
            List of Command objects sorted by timestamp (oldest first).

        Raises:
            FileNotFoundError: If the Atuin database doesn't exist.
            sqlite3.DatabaseError: If the database is corrupted.
        """
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Atuin database not found at {self.db_path}\n"
                f"Install Atuin: {ATUIN_INSTALL_URL}"
            )

        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, timestamp, duration, exit_status, command, cwd, hostname, session "
                "FROM history ORDER BY timestamp ASC"
            )
            commands = [
                Command(
                    id=row["id"],
                    timestamp=row["timestamp"],
                    duration=row["duration"],
                    exit_status=row["exit_status"],
                    command=row["command"],
                    cwd=row["cwd"] or "",
                    hostname=row["hostname"] or "",
                    session=row["session"] or "",
                )
                for row in cursor.fetchall()
            ]
            conn.close()
            return commands
        except sqlite3.DatabaseError as e:
            raise sqlite3.DatabaseError(
                f"Atuin database is corrupted: {e}\n"
                f"Try: atuin history rebuild"
            ) from e
