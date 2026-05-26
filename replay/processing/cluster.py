"""Group commands into sessions based on session ID, time gaps, or directory changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from replay.capture.atuin import Command

# 15 minutes in nanoseconds (Atuin timestamps are nanoseconds)
GAP_THRESHOLD_NS = 15 * 60 * 1_000_000_000


@dataclass
class Session:
    """A group of related commands forming a terminal session."""

    session_id: str
    commands: List[Command] = field(default_factory=list)
    hostname: str = ""

    @property
    def start_time(self) -> int:
        return self.commands[0].timestamp if self.commands else 0

    @property
    def end_time(self) -> int:
        return self.commands[-1].timestamp if self.commands else 0

    @property
    def command_count(self) -> int:
        return len(self.commands)

    @property
    def primary_cwd(self) -> str:
        """Most frequently used working directory in this session."""
        if not self.commands:
            return ""
        dirs = [c.cwd for c in self.commands if c.cwd]
        if not dirs:
            return ""
        return max(set(dirs), key=dirs.count)


def cluster_commands(commands: List[Command]) -> List[Session]:
    """Group commands into sessions.

    Strategy (in priority order):
    1. Use Atuin's session field if present
    2. Fall back to time-gap + directory-change clustering

    Args:
        commands: List of Command objects sorted by timestamp.

    Returns:
        List of Session objects, each containing grouped commands.
    """
    if not commands:
        return []

    # Check if any commands have session IDs
    has_session_ids = any(c.session for c in commands)

    if has_session_ids:
        return _cluster_by_session_id(commands)
    else:
        return _cluster_by_heuristic(commands)


def _cluster_by_session_id(commands: List[Command]) -> List[Session]:
    """Cluster using Atuin's built-in session field."""
    session_map: dict[str, Session] = {}
    order: list[str] = []

    for cmd in commands:
        sid = cmd.session or _make_session_key(cmd)
        if sid not in session_map:
            session_map[sid] = Session(session_id=sid, hostname=cmd.hostname)
            order.append(sid)
        session_map[sid].commands.append(cmd)

    return [session_map[sid] for sid in order]


def _cluster_by_heuristic(commands: List[Command]) -> List[Session]:
    """Cluster using time gaps and directory changes."""
    if not commands:
        return []

    sessions: List[Session] = []
    current = Session(session_id=_make_session_key(commands[0]), hostname=commands[0].hostname)
    current.commands.append(commands[0])

    for i in range(1, len(commands)):
        prev = commands[i - 1]
        curr = commands[i]

        # New session if: time gap > 15 min OR directory changed OR hostname changed
        time_gap = curr.timestamp - prev.timestamp
        dir_changed = curr.cwd and prev.cwd and curr.cwd != prev.cwd
        host_changed = curr.hostname and prev.hostname and curr.hostname != prev.hostname

        if time_gap > GAP_THRESHOLD_NS or dir_changed or host_changed:
            sessions.append(current)
            current = Session(
                session_id=_make_session_key(curr),
                hostname=curr.hostname,
            )

        current.commands.append(curr)

    sessions.append(current)
    return sessions


def _make_session_key(cmd: Command) -> str:
    """Generate a fallback session key from timestamp + hostname."""
    return f"{cmd.hostname}-{cmd.timestamp}"
