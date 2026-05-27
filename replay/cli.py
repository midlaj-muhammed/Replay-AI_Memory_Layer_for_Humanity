"""Replay CLI — semantic search over your terminal history."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from replay.capture.bash import ShellHistoryReader, detect_history_source, read_history
from replay.config import ReplayConfig, AVAILABLE_MODELS
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


def _get_commands(source: str, db_path: Optional[str] = None):
    """Load commands from the specified source."""
    from pathlib import Path
    try:
        path = Path(db_path) if db_path else None
        return read_history(
            source=source,
            bash_path=path if db_path and source == "bash" else None,
            zsh_path=path if db_path and source == "zsh" else None,
            atuin_db_path=path if db_path and source in ("auto", "atuin") else None,
        )
    except FileNotFoundError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        err_console.print(f"[red]Error reading history:[/red] {e}")
        raise typer.Exit(1) from e


def _output_json(data: object) -> None:
    """Print JSON to stdout."""
    print(json.dumps(data, indent=2, default=str))


@app.command()
def list(
    source: str = typer.Option("auto", "--source", "-s", help="History source: auto, atuin, bash, zsh, all"),
    plain: bool = typer.Option(False, "--plain", help="Plain text output (no TUI)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output format: json"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max sessions to show"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Custom history file/database path"),
) -> None:
    """List terminal sessions from history."""
    commands = _get_commands(source, db_path)
    sessions = cluster_commands(commands)

    if limit:
        sessions = sessions[:limit]

    if output == "json":
        data = []
        for s in sessions:
            data.append({
                "session_id": s.session_id,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "command_count": s.command_count,
                "primary_cwd": s.primary_cwd,
                "hostname": s.hostname,
                "commands": [
                    {"command": c.command, "exit_status": c.exit_status, "cwd": c.cwd, "timestamp": c.timestamp}
                    for c in s.commands
                ],
            })
        _output_json({"sessions": data, "total": len(data)})
    elif plain:
        print(render_session_list_plain(sessions))
    else:
        render_session_list(sessions)


@app.command()
def history(
    source: str = typer.Option("auto", "--source", "-s", help="History source: auto, atuin, bash, zsh, all"),
    plain: bool = typer.Option(False, "--plain", help="Plain text output (no TUI)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output format: json"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max sessions to show"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Custom history file/database path"),
) -> None:
    """Show detailed command history grouped by session."""
    commands = _get_commands(source, db_path)
    sessions = cluster_commands(commands)

    if limit:
        sessions = sessions[:limit]

    if output == "json":
        data = []
        for s in sessions:
            data.append({
                "session_id": s.session_id,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "command_count": s.command_count,
                "primary_cwd": s.primary_cwd,
                "commands": [
                    {"command": c.command, "exit_status": c.exit_status, "cwd": c.cwd, "timestamp": c.timestamp}
                    for c in s.commands
                ],
            })
        _output_json({"sessions": data, "total": len(data)})
    elif plain:
        print(render_sessions_plain(sessions))
    else:
        render_sessions_detail(sessions)


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural language search query"),
    threshold: float = typer.Option(0.3, "--threshold", "-t", help="Minimum similarity score (0-1)"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max results to show"),
    plain: bool = typer.Option(False, "--plain", help="Plain text output (no TUI)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output format: json"),
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

    if output == "json":
        data = {
            "query": query,
            "threshold": threshold,
            "results": [
                {
                    "score": round(r.score, 4),
                    "score_pct": r.score_pct,
                    "command": r.metadata.command,
                    "exit_status": r.metadata.exit_status,
                    "cwd": r.metadata.cwd,
                    "timestamp": r.metadata.timestamp,
                    "session_id": r.metadata.session_id,
                    "chunk_text": r.metadata.chunk_text,
                }
                for r in results
            ],
            "total": len(results),
        }
        _output_json(data)
    elif plain:
        print(render_search_results_plain(results, query))
    else:
        render_search_results(results, query)


@app.command()
def init(
    source: str = typer.Option("auto", "--source", "-s", help="History source: auto, atuin, bash, zsh, all"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Custom history file/database path"),
) -> None:
    """Build the search index from history."""
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    from replay.processing.chunker import chunk_sessions
    from replay.search.index import SearchIndex, ChunkMetadata
    from replay.search.embedder import Embedder, local_embed_batch

    config = ReplayConfig.load()

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Reading history...", total=None)

            commands = _get_commands(source, db_path)
            sessions = cluster_commands(commands)
            chunks = chunk_sessions(sessions)
            progress.update(task, total=len(chunks), description="Embedding chunks...")

            index = SearchIndex(config.index_path)
            index.clear()

            if config.openai_api_key:
                embedder = Embedder(api_key=config.openai_api_key, model=config.embedding_model, base_url=config.openai_base_url)

            all_embeddings = []
            all_metadata = []
            for i in range(0, len(chunks), 100):
                batch = chunks[i : i + 100]
                texts = [c.chunk_text for c in batch]
                if config.openai_api_key:
                    embeddings = embedder.embed_texts(texts)
                else:
                    embeddings = local_embed_batch(texts)
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
    source: str = typer.Option("auto", "--source", "-s", help="History source: auto, atuin, bash, zsh, all"),
    plain: bool = typer.Option(False, "--plain", help="Plain text output (no TUI)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output format: json"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max fixes to show"),
    db_path: Optional[str] = typer.Option(None, "--db", help="Custom history file/database path"),
) -> None:
    """Show sessions where bug fixes were detected."""
    commands = _get_commands(source, db_path)
    sessions = cluster_commands(commands)
    all_fixes = detect_fixes_all(sessions)

    if limit:
        all_fixes = all_fixes[:limit]

    if output == "json":
        data = {
            "fixes": [
                {
                    "description": f.description,
                    "failure_commands": [
                        {"command": c.command, "exit_status": c.exit_status, "cwd": c.cwd, "timestamp": c.timestamp}
                        for c in f.failure_commands
                    ],
                    "fix_command": {
                        "command": f.fix_command.command,
                        "exit_status": f.fix_command.exit_status,
                        "cwd": f.fix_command.cwd,
                        "timestamp": f.fix_command.timestamp,
                    },
                }
                for f in all_fixes
            ],
            "total": len(all_fixes),
        }
        _output_json(data)
    elif plain:
        print(render_fixes_plain(all_fixes))
    else:
        render_fixes(all_fixes)


@app.command()
def stats(
    source: str = typer.Option("auto", "--source", "-s", help="History source: auto, atuin, bash, zsh, all"),
    plain: bool = typer.Option(False, "--plain", help="Plain text output (no TUI)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output format: json"),
) -> None:
    """Show index and history statistics."""
    from replay.search.index import SearchIndex

    config = ReplayConfig.load()
    index = SearchIndex(config.index_path)

    # History stats
    try:
        commands = _get_commands(source)
        sessions = cluster_commands(commands)
        fix_count = len(detect_fixes_all(sessions))
    except Exception:
        commands = []
        sessions = []
        fix_count = 0

    # Index stats
    idx_chunks = 0
    total_size = 0
    size_str = "(no index)"
    if index.exists():
        index.load()
        idx_chunks = index.total_chunks
        idx_file = index.index_path
        idx_size = idx_file.stat().st_size if idx_file.exists() else 0
        meta_file = index.sidecar_path
        meta_size = meta_file.stat().st_size if meta_file.exists() else 0
        total_size = idx_size + meta_size
        size_str = f"{total_size / 1024:.1f} KB" if total_size < 1024 * 1024 else f"{total_size / (1024*1024):.1f} MB"

    if output == "json":
        _output_json({
            "commands": len(commands),
            "sessions": len(sessions),
            "fixes": fix_count,
            "index_chunks": idx_chunks,
            "index_size_bytes": total_size,
            "embedding_model": config.embedding_model,
            "source": source,
        })
    elif plain:
        print("Replay Stats")
        print("=" * 40)
        print(f"  Commands:     {len(commands)}")
        print(f"  Sessions:     {len(sessions)}")
        print(f"  Fixes found:  {fix_count}")
        print(f"  Index chunks: {idx_chunks}")
        print(f"  Index size:   {size_str}")
        print(f"  Model:        {config.embedding_model}")
    else:
        table = Table(title="[bold]Replay Stats[/bold]", show_header=False, padding=(0, 2))
        table.add_column("Metric", style="dim")
        table.add_column("Value", style="bold")
        table.add_row("Commands", str(len(commands)))
        table.add_row("Sessions", str(len(sessions)))
        table.add_row("Fixes found", str(fix_count))
        table.add_row("Index chunks", str(idx_chunks))
        table.add_row("Index size", size_str)
        table.add_row("Model", config.embedding_model)
        console.print(table)


config_app = typer.Typer(help="View and modify configuration.")
app.add_typer(config_app, name="config")


@config_app.callback(invoke_without_command=True)
def config_show(
    ctx: typer.Context,
    plain: bool = typer.Option(False, "--plain", help="Plain text output (no TUI)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output format: json"),
) -> None:
    """Show current configuration."""
    if ctx.invoked_subcommand is not None:
        return

    config = ReplayConfig.load()

    if output == "json":
        _output_json({
            "embedding_model": config.embedding_model,
            "openai_base_url": config.openai_base_url,
            "index_path": str(config.index_path),
            "atuin_db_path": str(config.atuin_db_path) if config.atuin_db_path else None,
            "api_key_set": bool(config.openai_api_key),
            "available_models": AVAILABLE_MODELS,
        })
    else:
        lines = config.summary_lines()
        if plain:
            print("Replay Config")
            print("=" * 40)
            for line in lines:
                print(line)
        else:
            panel_content = "\n".join(lines)
            console.print(Panel(panel_content, title="[bold]Replay Config[/bold]", border_style="cyan"))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key: model, api_key, base_url"),
    value: str = typer.Argument(..., help="New value"),
) -> None:
    """Set a configuration value."""
    config = ReplayConfig.load()

    if key == "model":
        if value not in AVAILABLE_MODELS:
            err_console.print(f"[red]Unknown model:[/red] {value}")
            err_console.print(f"Available: {', '.join(AVAILABLE_MODELS.keys())}")
            raise typer.Exit(1)
        old_model = config.embedding_model
        config.embedding_model = value
        config.save()
        console.print(f"[green]Model:[/green] {old_model} -> {value}")
        if old_model != value:
            console.print("[yellow]Run `replay init` to rebuild the index with the new model.[/yellow]")
    elif key == "api_key":
        config.openai_api_key = value
        config.save()
        console.print("[green]API key saved.[/green]")
    elif key == "base_url":
        config.openai_base_url = value if value != "default" else None
        config.save()
        console.print(f"[green]Base URL:[/green] {config.openai_base_url or '(default)'}")
    else:
        err_console.print(f"[red]Unknown key:[/red] {key}")
        err_console.print("Available keys: model, api_key, base_url")
        raise typer.Exit(1)


@config_app.command("models")
def config_models() -> None:
    """List available embedding models."""
    table = Table(title="[bold]Available Embedding Models[/bold]", show_header=True)
    table.add_column("Model", style="cyan")
    table.add_column("Dimensions", justify="right")
    table.add_column("Provider")

    for name, info in AVAILABLE_MODELS.items():
        table.add_row(name, str(info["dimensions"]), info["provider"])

    console.print(table)


@app.command()
def export(
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path (default: stdout)"),
) -> None:
    """Export the search index as JSON."""
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
        "embedding_model": config.embedding_model,
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
def refresh(
    source: str = typer.Option("auto", "--source", "-s", help="History source: auto, atuin, bash, zsh, all"),
) -> None:
    """Incrementally update the search index with new commands."""
    config = ReplayConfig.load()

    try:
        index, added = refresh_index(config, source=source)
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


@app.command()
def watch(
    source: str = typer.Option("auto", "--source", "-s", help="History source: auto, atuin, bash, zsh, all"),
    interval: int = typer.Option(5, "--interval", "-i", help="Poll interval in seconds"),
) -> None:
    """Watch for new commands and update the index in real-time."""
    from replay.processing.chunker import chunk_sessions
    from replay.search.index import SearchIndex, ChunkMetadata
    from replay.search.embedder import Embedder, local_embed_batch

    config = ReplayConfig.load()
    console.print(f"[bold]Replay Watch[/bold] — polling every {interval}s (Ctrl+C to stop)\n")

    # Load or build index
    index = SearchIndex(config.index_path)
    if index.exists():
        index.load()
        console.print(f"[green]Loaded index:[/green] {index.total_chunks} chunks")
    else:
        console.print("[yellow]No index found. Building initial index...[/yellow]")
        commands = read_history(source=source)
        sessions = cluster_commands(commands)
        from replay.processing.chunker import chunk_sessions as cs
        chunks = cs(sessions)
        if chunks:
            texts = [c.chunk_text for c in chunks]
            if config.openai_api_key:
                embedder = Embedder(api_key=config.openai_api_key, model=config.embedding_model, base_url=config.openai_base_url)
                embeddings = embedder.embed_texts(texts)
            else:
                from replay.search.embedder import local_embed_batch as leb
                embeddings = leb(texts)
            metadata = [
                ChunkMetadata(
                    chunk_text=c.chunk_text,
                    command=c.command.command,
                    exit_status=c.command.exit_status,
                    cwd=c.command.cwd,
                    timestamp=c.command.timestamp,
                    session_id=c.session_id,
                )
                for c in chunks
            ]
            index.build(embeddings, metadata)
            index.save()
            console.print(f"[green]Index built:[/green] {index.total_chunks} chunks")
        else:
            console.print("[yellow]No commands found to index.[/yellow]")

    # Get the latest timestamp in the index
    if index.metadata:
        latest_ts = max(m.timestamp for m in index.metadata)
    else:
        latest_ts = 0

    if config.openai_api_key:
        embedder = Embedder(api_key=config.openai_api_key, model=config.embedding_model, base_url=config.openai_base_url)

    console.print(f"\n[dim]Watching for new commands...[/dim]\n")

    try:
        while True:
            time.sleep(interval)

            # Read history and find new commands
            commands = read_history(source=source)
            new_commands = [c for c in commands if c.timestamp > latest_ts]

            if not new_commands:
                continue

            new_sessions = cluster_commands(new_commands)
            chunks = chunk_sessions(new_sessions)

            if not chunks:
                continue

            # Filter out already-indexed timestamps
            existing_ts = {m.timestamp for m in index.metadata}
            new_chunks = [c for c in chunks if c.timestamp not in existing_ts]

            if not new_chunks:
                continue

            # Embed and add
            texts = [c.chunk_text for c in new_chunks]
            if config.openai_api_key:
                embeddings = embedder.embed_texts(texts)
            else:
                from replay.search.embedder import local_embed_batch as leb
                embeddings = leb(texts)

            metadata = [
                ChunkMetadata(
                    chunk_text=c.chunk_text,
                    command=c.command.command,
                    exit_status=c.command.exit_status,
                    cwd=c.command.cwd,
                    timestamp=c.command.timestamp,
                    session_id=c.session_id,
                )
                for c in new_chunks
            ]

            index.add(embeddings, metadata)
            index.save()
            latest_ts = max(m.timestamp for m in index.metadata)

            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).strftime("%H:%M:%S")
            console.print(f"[{now}] [green]+{len(new_chunks)} chunks[/green] (total: {index.total_chunks})")

    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/dim]")


if __name__ == "__main__":
    app()
