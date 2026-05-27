# Contributing to Replay

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/midlaj-muhammed/Replay-AI_Memory_Layer_for_Humanity.git
cd Replay-AI_Memory_Layer_for_Humanity/replay
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest -q
# 160 passed in 0.80s
```

With coverage:

```bash
pytest --cov=replay --cov-report=term-missing
```

## Making Changes

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Add tests for any new functionality
4. Run the test suite and make sure everything passes
5. Submit a pull request

## Code Style

- Python 3.10+ with type hints
- Follow existing patterns in the codebase
- Keep functions focused and small
- Use the `--plain` / `--output json` / Rich TUI triple-output pattern for new CLI commands

## Adding a New CLI Command

Follow the pattern in `replay/cli.py`:

```python
@app.command()
def my_command(
    arg: str = typer.Argument(..., help="..."),
    plain: bool = typer.Option(False, "--plain", help="Plain text output (no TUI)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output format: json"),
) -> None:
    """Help text shown in --help."""
    config = ReplayConfig.load()
    
    # ... do work ...

    if output == "json":
        _output_json({"key": "value"})
    elif plain:
        print(render_my_command_plain(...))
    else:
        render_my_command(...)  # Rich TUI
```

## Adding Tests

Tests live in `tests/`. Follow existing patterns:

- Mock the OpenAI client at the import location: `@patch("replay.search.chat.OpenAI")`
- Use `typer.testing.CliRunner` for CLI tests
- Use `tmp_path` fixtures for file system tests
- Test both happy paths and error cases

## Reporting Bugs

Open an issue with:
- What you expected
- What actually happened
- Steps to reproduce
- Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
