"""Read command history from bash and zsh history files."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from replay.capture.atuin import Command

BASH_HISTORY_PATH = Path.home() / ".bash_history"
ZSH_HISTORY_PATH = Path.home() / ".zsh_history"

# Zsh extended history format: : <timestamp>:<duration>;<command>
ZSH_EXTENDED_RE = re.compile(r"^: (\d+):(\d+);(.+)$")


class ShellHistoryReader:
    """Reads command history from bash and/or zsh history files."""

    def __init__(
        self,
        bash_path: Optional[Path] = None,
        zsh_path: Optional[Path] = None,
    ):
        self.bash_path = bash_path or BASH_HISTORY_PATH
        self.zsh_path = zsh_path or ZSH_HISTORY_PATH

    def read_history(self) -> List[Command]:
        """Read all commands from available shell history files.

        Merges bash and zsh history, sorted by timestamp.
        Commands without timestamps are assigned sequential timestamps.

        Returns:
            List of Command objects sorted by timestamp (oldest first).
        """
        commands: List[Command] = []
        commands.extend(self._read_bash())
        commands.extend(self._read_zsh())
        commands.sort(key=lambda c: c.timestamp)
        return commands

    def available_sources(self) -> dict[str, bool]:
        """Check which history sources are available."""
        return {
            "bash": self.bash_path.exists(),
            "zsh": self.zsh_path.exists(),
        }

    def _read_bash(self) -> List[Command]:
        """Read bash history file."""
        if not self.bash_path.exists():
            return []

        commands: List[Command] = []
        hostname = os.uname().nodename
        fallback_ts = int(time.time() * 1_000_000_000) - 1_000_000_000

        lines = self.bash_path.read_text(errors="replace").splitlines()
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Assign sequential timestamps (bash history has no timestamps by default)
            ts = fallback_ts + i * 1_000_000_000
            commands.append(
                Command(
                    id=f"bash-{i}",
                    timestamp=ts,
                    duration=0,
                    exit_status=0,  # Unknown
                    command=line,
                    cwd="",
                    hostname=hostname,
                    session="bash",
                )
            )
        return commands

    def _read_zsh(self) -> List[Command]:
        """Read zsh history file, supporting both extended and simple formats."""
        if not self.zsh_path.exists():
            return []

        commands: List[Command] = []
        hostname = os.uname().nodename
        fallback_ts = int(time.time() * 1_000_000_000) - 1_000_000_000
        simple_idx = 0

        lines = self.zsh_path.read_text(errors="replace").splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            match = ZSH_EXTENDED_RE.match(line)
            if match:
                # Extended history format
                ts_sec = int(match.group(1))
                duration = int(match.group(2))
                cmd_text = match.group(3)
                # Handle multi-line commands (lines ending with \)
                while cmd_text.endswith("\\") and i + 1 < len(lines):
                    i += 1
                    cmd_text = cmd_text[:-1] + "\n" + lines[i]
                commands.append(
                    Command(
                        id=f"zsh-{i}",
                        timestamp=ts_sec * 1_000_000_000,
                        duration=duration,
                        exit_status=0,
                        command=cmd_text,
                        cwd="",
                        hostname=hostname,
                        session="zsh",
                    )
                )
            else:
                # Simple format (no timestamp)
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    ts = fallback_ts + simple_idx * 1_000_000_000
                    commands.append(
                        Command(
                            id=f"zsh-simple-{simple_idx}",
                            timestamp=ts,
                            duration=0,
                            exit_status=0,
                            command=stripped,
                            cwd="",
                            hostname=hostname,
                            session="zsh",
                        )
                    )
                    simple_idx += 1
            i += 1

        return commands


def detect_history_source() -> str:
    """Auto-detect the best history source.

    Returns:
        "atuin" if Atuin DB exists, "bash" if bash_history exists,
        "zsh" if zsh_history exists, or "none".
    """
    from replay.capture.atuin import ATUIN_DB_PATH

    if ATUIN_DB_PATH.exists():
        return "atuin"
    if ZSH_HISTORY_PATH.exists():
        return "zsh"
    if BASH_HISTORY_PATH.exists():
        return "bash"
    return "none"


def read_history(
    source: str = "auto",
    bash_path: Optional[Path] = None,
    zsh_path: Optional[Path] = None,
    atuin_db_path: Optional[Path] = None,
) -> List[Command]:
    """Unified history reader that dispatches to the right source.

    Args:
        source: One of "auto", "atuin", "bash", "zsh", "all".
        bash_path: Custom bash history path.
        zsh_path: Custom zsh history path.
        atuin_db_path: Custom Atuin database path.

    Returns:
        List of Command objects sorted by timestamp.
    """
    if source == "auto":
        source = detect_history_source()

    if source == "atuin":
        from replay.capture.atuin import AtuinReader
        return AtuinReader(atuin_db_path).read_history()

    if source == "bash":
        reader = ShellHistoryReader(bash_path=bash_path)
        return reader._read_bash()

    if source == "zsh":
        reader = ShellHistoryReader(zsh_path=zsh_path)
        return reader._read_zsh()

    if source == "all":
        commands: List[Command] = []
        # Try Atuin first
        try:
            from replay.capture.atuin import AtuinReader
            commands.extend(AtuinReader().read_history())
        except (FileNotFoundError, Exception):
            pass
        # Add shell history
        reader = ShellHistoryReader(bash_path=bash_path, zsh_path=zsh_path)
        commands.extend(reader.read_history())
        # Deduplicate by command text + approximate timestamp (within 2s)
        commands = _deduplicate(commands)
        commands.sort(key=lambda c: c.timestamp)
        return commands

    raise ValueError(f"Unknown source: {source!r}. Use auto, atuin, bash, zsh, or all.")


def _deduplicate(commands: List[Command]) -> List[Command]:
    """Remove duplicate commands (same text within 2 seconds)."""
    if not commands:
        return []

    deduped: List[Command] = [commands[0]]
    TWO_SEC_NS = 2 * 1_000_000_000

    for cmd in commands[1:]:
        prev = deduped[-1]
        if cmd.command == prev.command and abs(cmd.timestamp - prev.timestamp) < TWO_SEC_NS:
            continue
        deduped.append(cmd)

    return deduped
