"""Plain text display for non-TUI environments (piped output, --plain flag)."""

from __future__ import annotations

from typing import List

from replay.processing.cluster import Session
from replay.processing.fix_detector import Fix
from replay.search.index import SearchResult


def render_sessions_plain(sessions: List[Session]) -> str:
    """Render sessions as plain text (no ANSI codes, no TUI borders)."""
    if not sessions:
        return "No sessions found."

    lines = []
    for session in sessions:
        if not session.commands:
            continue
        # Header: timestamp range + cwd + command count
        first_ts = _format_timestamp(session.commands[0].timestamp)
        cwd = session.primary_cwd or "unknown"
        count = session.command_count
        lines.append(f"Session ({count} commands) — {first_ts} — {cwd}")
        lines.append("-" * 60)

        for cmd in session.commands:
            exit_marker = "ok" if cmd.exit_status == 0 else f"exit:{cmd.exit_status}"
            lines.append(f"  [{exit_marker:>7}] {cmd.command}")

        lines.append("")

    return "\n".join(lines)


def render_session_list_plain(sessions: List[Session]) -> str:
    """Render a session listing as plain text."""
    if not sessions:
        return "No terminal history found."

    lines = [f"Found {len(sessions)} sessions:\n"]

    for i, session in enumerate(sessions, 1):
        if not session.commands:
            continue
        first_ts = _format_timestamp(session.commands[0].timestamp)
        cwd = session.primary_cwd or "unknown"
        count = session.command_count
        fix_count = sum(
            1 for c in session.commands
            if c.exit_status == 0
            and any(
                prev.exit_status != 0
                for prev in session.commands[:session.commands.index(c)]
            )
        )
        fix_str = f" ({fix_count} fixes)" if fix_count else ""
        lines.append(f"  {i:3}. {first_ts}  {cwd}  {count} commands{fix_str}")

    return "\n".join(lines)


def render_fixes_plain(fixes: List[Fix]) -> str:
    """Render detected fixes as plain text."""
    if not fixes:
        return "No fix patterns detected."

    lines = [f"Found {len(fixes)} fix patterns:\n"]

    for i, fix in enumerate(fixes, 1):
        lines.append(f"  {i:3}. {fix.description}")
        if fix.failure_commands:
            for fc in fix.failure_commands:
                ts = _format_timestamp(fc.timestamp)
                lines.append(f"       FAILED: exit:{fc.exit_status} | {fc.cwd} | {fc.command}")
        fc = fix.fix_command
        ts = _format_timestamp(fc.timestamp)
        lines.append(f"       FIXED:   exit:0 | {fc.cwd} | {fc.command}")
        lines.append("")

    return "\n".join(lines)


def render_search_results_plain(results: List[SearchResult], query: str) -> str:
    """Render search results as plain text."""
    if not results:
        return (
            f'No matches found for "{query}"\n'
            "Try:\n"
            "  - Broader query: use fewer words\n"
            "  - Lower threshold: --threshold 0.2\n"
            "  - Check index: replay list"
        )

    lines = [f'Found {len(results)} matches for "{query}":\n']

    for i, result in enumerate(results, 1):
        meta = result.metadata
        ts = _format_timestamp(meta.timestamp)
        score = result.score_pct
        cwd = meta.cwd or "unknown"
        exit_marker = "ok" if meta.exit_status == 0 else f"exit:{meta.exit_status}"
        cmd = _truncate(meta.command, 80)

        lines.append(f"  {i:3}. [{score:3d}%] {ts}  {cwd}")
        lines.append(f"       [{exit_marker:>7}] {cmd}")
        lines.append("")

    return "\n".join(lines)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _format_timestamp(ts_ns: int) -> str:
    """Format a nanosecond timestamp as a readable datetime string."""
    from datetime import datetime, timezone

    ts_s = ts_ns / 1_000_000_000
    dt = datetime.fromtimestamp(ts_s, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M")
