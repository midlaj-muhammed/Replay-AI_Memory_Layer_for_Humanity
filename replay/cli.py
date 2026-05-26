"""Replay CLI — semantic search over your terminal history."""

from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from replay.capture.atuin import AtuinReader
from replay.config import ReplayConfig
from replay.display.plain import render_fixes_plain, render_search_results_plain, render_session_list_plain, render_sessions_plain
from replay.display.tui import render_fixes, render_search_results, render_session_list, render_sessions_detail
from replay.processing.cluster import Session, cluster_commands
from replay.processing.fix_detector import detect_fixes_all, Fix
from replay.search.query import SearchError, build_index, refresh_index, search_query

app = typer.Typer(
    name="replay",
    help="Semantic search over your terminal history.",
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


@app.command()
def list(
    plain: bool = typer.Option(False, "--plain", help="Plain text output (no TUI)"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max sessions to show"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Path to Atuin database"),
) -> None:
    """List terminal sessions from Atuin history."""
    from pathlib import Path

    try:
        reader = AtuinReader(Path(db_path) if db_path else None)
        commands = reader.read_history()
    except FileNotFoundError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        err_console.print(f"[red]Error reading Atuin database:[/red] {e}")
        raise typer.Exit(1) from e

    sessions = cluster_commands(commands)

    if limit:
        sessions = sessions[:limit]

    if plain:
        print(render_session_list_plain(sessions))
    else:
        render_session_list(sessions)


@app.command()
def history(
    plain: bool = typer.Option(False, "--plain", help="Plain text output (no TUI)"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max sessions to show"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Path to Atuin database"),
) -> None:
    """Show detailed command history grouped by session."""
    from pathlib import Path

    try:
        reader = AtuinReader(Path(db_path) if db_path else None)
        commands = reader.read_history()
    except FileNotFoundError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        err_console.print(f"[red]Error reading Atuin database:[/red] {e}")
        raise typer.Exit(1) from e

    sessions = cluster_commands(commands)

    if limit:
        sessions = sessions[:limit]

    if plain:
        print(render_sessions_plain(sessions))
    else:
        render_sessions_detail(sessions)


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural language search query"),
    threshold: float = typer.Option(0.3, "--threshold", "-t", help="Minimum similarity score (0-1)"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max results to show"),
    plain: bool = typer.Option(False, "--plain", help="Plain text output (no TUI)"),
) -> None:
    """Search terminal history using natural language."""
    config = ReplayConfig.load()

    try:
        results = search_query(config, query, threshold=threshold, top_k=limit)
    except SearchError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    except FileNotFoundError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        console.print("[yellow]Run `replay init` to build the search index.[/yellow]")
        raise typer.Exit(1) from e
    except Exception as e:
        err_console.print(f"[red]Search failed:[/red] {e}")
        raise typer.Exit(1) from e

    if plain:
        print(render_search_results_plain(results, query))
    else:
        render_search_results(results, query)


@app.command()
def init(
    db_path: Optional[str] = typer.Option(None, "--db", help="Path to Atuin database"),
) -> None:
    """Build the search index from Atuin history."""
    from pathlib import Path
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

    config = ReplayConfig.load()

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Reading Atuin history...", total=None)

            reader = AtuinReader(Path(db_path) if db_path else None)
            commands = reader.read_history()
            sessions = cluster_commands(commands)

            from replay.processing.chunker import chunk_sessions
            chunks = chunk_sessions(sessions)
            progress.update(task, total=len(chunks), description="Embedding chunks...")

            # Build in chunks of 100 to show progress
            from replay.search.index import SearchIndex, ChunkMetadata
            from replay.search.embedder import Embedder

            index = SearchIndex(config.index_path)
            index.clear()

            embedder = Embedder(api_key=config.openai_api_key, model=config.embedding_model, base_url=config.openai_base_url)

            all_embeddings = []
            all_metadata = []
            for i in range(0, len(chunks), 100):
                batch = chunks[i : i + 100]
                texts = [c.chunk_text for c in batch]
                embeddings = embedder.embed_texts(texts)
                all_embeddings.extend(embeddings)
                all_metadata.extend([
                    ChunkMetadata(
                        chunk_text=c.chunk_text,
                        command=c.command.command,
                        exit_status=c.command.exit_status,
                        cwd=c.command.cwd,
                        timestamp=c.command.timestamp,
                        session_id=c.session_id,
                    )
                    for c in batch
                ])
                progress.update(task, completed=i + len(batch))

            index.build(all_embeddings, all_metadata)
            index.save()

        console.print(f"[green]Index built:[/green] {index.total_chunks} chunks from {len(commands)} commands")
    except SearchError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    except FileNotFoundError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        err_console.print(f"[red]Failed to build index:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def fixes(
    plain: bool = typer.Option(False, "--plain", help="Plain text output (no TUI)"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max fixes to show"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Path to Atuin database"),
) -> None:
    """Show sessions where bug fixes were detected."""
    from pathlib import Path

    try:
        reader = AtuinReader(Path(db_path) if db_path else None)
        commands = reader.read_history()
    except FileNotFoundError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        err_console.print(f"[red]Error reading Atuin database:[/red] {e}")
        raise typer.Exit(1) from e

    sessions = cluster_commands(commands)
    all_fixes = detect_fixes_all(sessions)

    if limit:
        all_fixes = all_fixes[:limit]

    if plain:
        print(render_fixes_plain(all_fixes))
    else:
        render_fixes(all_fixes)


@app.command()
def stats(
    plain: bool = typer.Option(False, "--plain", help="Plain text output (no TUI)"),
) -> None:
    """Show index and history statistics."""
    from pathlib import Path
    from replay.search.index import SearchIndex

    config = ReplayConfig.load()
    index = SearchIndex(config.index_path)

    # Atuin stats
    try:
        reader = AtuinReader(config.atuin_db_path)
        commands = reader.read_history()
        sessions = cluster_commands(commands)
        fix_count = len(detect_fixes_all(sessions))
    except Exception:
        commands = []
        sessions = []
        fix_count = 0

    # Index stats
    if index.exists():
        index.load()
        idx_chunks = index.total_chunks
        idx_file = index.index_path
        idx_size = idx_file.stat().st_size if idx_file.exists() else 0
        meta_file = index.sidecar_path
        meta_size = meta_file.stat().st_size if meta_file.exists() else 0
        total_size = idx_size + meta_size
        size_str = f"{total_size / 1024:.1f} KB" if total_size < 1024 * 1024 else f"{total_size / (1024*1024):.1f} MB"
    else:
        idx_chunks = 0
        size_str = "(no index)"

    if plain:
        print(f"Replay Stats")
        print(f"{'='*40}")
        print(f"  Commands:     {len(commands)}")
        print(f"  Sessions:     {len(sessions)}")
        print(f"  Fixes found:  {fix_count}")
        print(f"  Index chunks: {idx_chunks}")
        print(f"  Index size:   {size_str}")
    else:
        table = Table(title="[bold]Replay Stats[/bold]", show_header=False, padding=(0, 2))
        table.add_column("Metric", style="dim")
        table.add_column("Value", style="bold")
        table.add_row("Commands", str(len(commands)))
        table.add_row("Sessions", str(len(sessions)))
        table.add_row("Fixes found", str(fix_count))
        table.add_row("Index chunks", str(idx_chunks))
        table.add_row("Index size", size_str)
        console.print(table)


@app.command(name="config")
def config_cmd(
    plain: bool = typer.Option(False, "--plain", help="Plain text output (no TUI)"),
) -> None:
    """Show current configuration."""
    config = ReplayConfig.load()
    lines = config.summary_lines()

    if plain:
        print("Replay Config")
        print("=" * 40)
        for line in lines:
            print(line)
    else:
        panel_content = "\n".join(lines)
        console.print(Panel(panel_content, title="[bold]Replay Config[/bold]", border_style="cyan"))


@app.command()
def export(
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path (default: stdout)"),
) -> None:
    """Export the search index as JSON."""
    import json
    from dataclasses import asdict
    from replay.search.index import SearchIndex

    config = ReplayConfig.load()
    index = SearchIndex(config.index_path)

    if not index.exists():
        err_console.print("[red]Error:[/red] No index found. Run `replay init` first.")
        raise typer.Exit(1)

    index.load()

    data = {
        "version": 1,
        "total_chunks": index.total_chunks,
        "chunks": [asdict(m) for m in index.metadata],
    }

    json_str = json.dumps(data, indent=2)

    if output:
        from pathlib import Path
        Path(output).write_text(json_str)
        console.print(f"[green]Exported:[/green] {index.total_chunks} chunks to {output}")
    else:
        print(json_str)


@app.command()
def refresh() -> None:
    """Incrementally update the search index with new commands."""
    config = ReplayConfig.load()

    try:
        index, added = refresh_index(config)
        if added == 0:
            console.print("[dim]Index is already up to date.[/dim]")
        else:
            console.print(f"[green]Index updated:[/green] {added} new chunks added (total: {index.total_chunks})")
    except SearchError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        err_console.print(f"[red]Refresh failed:[/red] {e}")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
