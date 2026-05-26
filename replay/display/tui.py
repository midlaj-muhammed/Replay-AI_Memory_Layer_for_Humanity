"""Rich-based TUI display for interactive terminal output."""

from __future__ import annotations

from typing import List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from replay.processing.cluster import Session
from replay.processing.fix_detector import Fix
from replay.search.index import SearchResult


console = Console()


def render_session_list(sessions: List[Session]) -> None:
    """Render a session listing as a Rich table."""
    if not sessions:
        console.print("[dim]No terminal history found.[/dim]")
        return

    table = Table(
        title=f"[bold]Found {len(sessions)} sessions[/bold]",
        show_header=True,
        header_style="bold",
        title_style="bold",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Time", style="dim")
    table.add_column("Directory", style="cyan")
    table.add_column("Commands", justify="right")
    table.add_column("Fixes", justify="right", style="green")

    for i, session in enumerate(sessions, 1):
        if not session.commands:
            continue
        first_ts = _format_timestamp(session.commands[0].timestamp)
        cwd = session.primary_cwd or "unknown"
        count = session.command_count
        fix_count = _count_fixes(session)
        fix_str = str(fix_count) if fix_count else "[dim]-[/dim]"

        table.add_row(str(i), first_ts, cwd, str(count), fix_str)

    console.print(table)


def render_sessions_detail(sessions: List[Session]) -> None:
    """Render detailed session view with commands."""
    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return

    for session in sessions:
        if not session.commands:
            continue

        first_ts = _format_timestamp(session.commands[0].timestamp)
        cwd = session.primary_cwd or "unknown"
        count = session.command_count

        # Session header
        header = Text()
        header.append(f" {first_ts} ", style="dim")
        header.append(f" {cwd} ", style="cyan")
        header.append(f" {count} commands ", style="dim")

        # Command list
        lines = Text()
        for cmd in session.commands:
            if cmd.exit_status == 0:
                lines.append(f"  exit:0  ", style="green")
            else:
                lines.append(f"  exit:{cmd.exit_status}  ", style="red")
            lines.append(f"{cmd.command}\n")

        panel = Panel(
            lines,
            title=header,
            border_style="dim",
            padding=(0, 1),
        )
        console.print(panel)


def _count_fixes(session: Session) -> int:
    """Count fix patterns (exit:1 followed by exit:0) in a session."""
    count = 0
    seen_failure = False
    for cmd in session.commands:
        if cmd.exit_status != 0:
            seen_failure = True
        elif seen_failure and cmd.exit_status == 0:
            count += 1
            seen_failure = False
    return count


def render_fixes(fixes: List[Fix]) -> None:
    """Render detected fixes as a Rich panel."""
    if not fixes:
        console.print("[dim]No fix patterns detected.[/dim]")
        return

    console.print(f"[bold]Found {len(fixes)} fix patterns[/bold]\n")

    for i, fix in enumerate(fixes, 1):
        # Build fix panel content
        lines = Text()
        for fc in fix.failure_commands:
            lines.append("  FAILED  ", style="red bold")
            lines.append(f"exit:{fc.exit_status} | {fc.cwd} | {fc.command}\n", style="red")
        lines.append("  FIXED   ", style="green bold")
        lines.append(f"exit:0 | {fix.fix_command.cwd} | {fix.fix_command.command}\n", style="green")

        panel = Panel(
            lines,
            title=f"[bold]Fix #{i}[/bold] — {fix.description}",
            border_style="green",
            padding=(0, 1),
        )
        console.print(panel)


def render_search_results(results: List[SearchResult], query: str) -> None:
    """Render semantic search results as a Rich panel."""
    if not results:
        console.print(f'[dim]No matches found for "{query}"[/dim]')
        console.print("[dim]Try:[/dim]")
        console.print("[dim]  • Broader query: use fewer words[/dim]")
        console.print("[dim]  • Lower threshold: --threshold 0.2[/dim]")
        console.print("[dim]  • Check index: replay list[/dim]")
        return

    console.print(
        f'[bold]Found {len(results)} matches[/bold] for "[yellow]{query}[/yellow]"\n'
    )

    for i, result in enumerate(results, 1):
        meta = result.metadata
        ts = _format_timestamp(meta.timestamp)
        score = result.score_pct
        cwd = meta.cwd or "unknown"
        cmd = _truncate(meta.command, 80)

        # Header: timestamp + directory + score
        header = Text()
        header.append(f" {ts} ", style="dim")
        header.append(f" {cwd} ", style="cyan")
        header.append(f" {score}% ", style="yellow bold")

        # Command line
        lines = Text()
        if meta.exit_status == 0:
            lines.append("  exit:0  ", style="green")
        else:
            lines.append(f"  exit:{meta.exit_status}  ", style="red")
        lines.append(f"{cmd}\n")

        # Fix marker
        if meta.exit_status == 0:
            lines.append("  ✅ Possible fix\n", style="green dim")

        panel = Panel(
            lines,
            title=header,
            border_style="yellow",
            padding=(0, 1),
        )
        console.print(panel)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _format_timestamp(ts_ns: int) -> str:
    """Format a nanosecond timestamp as a readable datetime string."""
    from datetime import datetime, timezone

    ts_s = ts_ns / 1_000_000_000
    dt = datetime.fromtimestamp(ts_s, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M")
