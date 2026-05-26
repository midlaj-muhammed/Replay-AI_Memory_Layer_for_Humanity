"""Detect bug-fix patterns in command sessions.

A fix is detected when a non-zero exit code is followed by a zero exit code
in the same session, indicating the developer resolved the issue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from replay.capture.atuin import Command
from replay.processing.cluster import Session


@dataclass
class Fix:
    """A detected bug-fix pattern."""

    session_id: str
    failure_commands: List[Command]
    fix_command: Command

    @property
    def description(self) -> str:
        """Human-readable description of the fix."""
        if self.failure_commands:
            failed_cmd = self.failure_commands[-1].command
            return f"'{failed_cmd}' failed, then '{self.fix_command.command}' succeeded"
        return f"Fix: '{self.fix_command.command}'"


def detect_fixes(session: Session) -> List[Fix]:
    """Detect fix patterns in a session.

    Algorithm:
    - Track a `seen_failure` flag
    - When exit_status != 0: set flag, accumulate failure commands
    - When exit_status == 0 AND flag is set: record as fix, reset flag
    - Consecutive failures are grouped (all failures before the fix are included)

    Args:
        session: A Session containing grouped commands.

    Returns:
        List of Fix objects describing detected fix patterns.
    """
    if not session.commands:
        return []

    fixes: List[Fix] = []
    seen_failure = False
    failure_commands: List[Command] = []

    for cmd in session.commands:
        if cmd.exit_status != 0:
            seen_failure = True
            failure_commands.append(cmd)
        elif seen_failure and cmd.exit_status == 0:
            # Fix detected: failure(s) followed by success
            fixes.append(
                Fix(
                    session_id=session.session_id,
                    failure_commands=list(failure_commands),
                    fix_command=cmd,
                )
            )
            seen_failure = False
            failure_commands = []

    return fixes


def detect_fixes_all(sessions: List[Session]) -> List[Fix]:
    """Detect fix patterns across all sessions."""
    all_fixes: List[Fix] = []
    for session in sessions:
        all_fixes.extend(detect_fixes(session))
    return all_fixes
