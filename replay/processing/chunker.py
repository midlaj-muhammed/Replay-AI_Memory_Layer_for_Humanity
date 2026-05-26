"""Split command sessions into searchable chunks with structured format."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from replay.capture.atuin import Command
from replay.processing.cluster import Session

# Commands to skip — trivial navigation that adds no search value
TRIVIAL_COMMANDS = {"cd", "ls", "ls -la", "ls -l", "pwd", "clear", "exit", "history", "alias"}

# Max commands to include as context before/after the main command
CONTEXT_WINDOW = 2


@dataclass
class Chunk:
    """A searchable unit derived from a command session."""

    command: Command
    chunk_text: str
    context_before: List[Command]
    context_after: List[Command]
    session_id: str = ""

    @property
    def timestamp(self) -> int:
        return self.command.timestamp

    @property
    def cwd(self) -> str:
        return self.command.cwd

    @property
    def exit_status(self) -> int:
        return self.command.exit_status


def _is_trivial(cmd: Command) -> bool:
    """Check if a command is trivial (should be skipped as primary chunk)."""
    stripped = cmd.command.strip()
    # Exact match
    if stripped in TRIVIAL_COMMANDS:
        return True
    # echo with no args (just 'echo' or 'echo ' with nothing after)
    if stripped == "echo" or stripped == "echo ":
        return True
    # cd with a path still counts as trivial for search purposes
    if stripped.startswith("cd "):
        return True
    return False


def _build_chunk_text(cmd: Command, context_before: List[Command], context_after: List[Command]) -> str:
    """Build structured chunk text from a command and its context.

    Format: "exit:<status> | <cwd> | <command>"
    With context: "exit:<status> | <cwd> | <prev_cmd> ; <prev_cmd> ; <command> ; <next_cmd>"
    """
    parts = []

    # Context before (if any)
    for ctx in context_before:
        exit_str = f"exit:{ctx.exit_status}"
        parts.append(f"{exit_str} | {ctx.cwd} | {ctx.command}")

    # Main command
    exit_str = f"exit:{cmd.exit_status}"
    parts.append(f"{exit_str} | {cmd.cwd} | {cmd.command}")

    # Context after (if any)
    for ctx in context_after:
        exit_str = f"exit:{ctx.exit_status}"
        parts.append(f"{exit_str} | {ctx.cwd} | {ctx.command}")

    return " ; ".join(parts)


def chunk_session(session: Session) -> List[Chunk]:
    """Split a session into searchable chunks.

    Rules:
    - Each non-trivial command produces one chunk
    - Trivial commands (cd, ls, pwd) are skipped as primary but included as context
    - Each chunk includes CONTEXT_WINDOW commands before and after for context
    - Chunk text uses structured format: "exit:0 | /path | command"

    Args:
        session: A Session containing grouped commands.

    Returns:
        List of Chunk objects, one per non-trivial command.
    """
    if not session.commands:
        return []

    chunks: List[Chunk] = []
    commands = session.commands

    for i, cmd in enumerate(commands):
        if _is_trivial(cmd):
            continue

        # Gather context (includes trivial commands — they're useful context)
        start = max(0, i - CONTEXT_WINDOW)
        end = min(len(commands), i + CONTEXT_WINDOW + 1)
        context_before = commands[start:i]
        context_after = commands[i + 1:end]

        chunk_text = _build_chunk_text(cmd, context_before, context_after)

        chunks.append(
            Chunk(
                command=cmd,
                chunk_text=chunk_text,
                context_before=context_before,
                context_after=context_after,
                session_id=session.session_id,
            )
        )

    return chunks


def chunk_sessions(sessions: List[Session]) -> List[Chunk]:
    """Chunk all sessions."""
    all_chunks: List[Chunk] = []
    for session in sessions:
        all_chunks.extend(chunk_session(session))
    return all_chunks
