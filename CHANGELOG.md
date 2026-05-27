# Changelog

All notable changes to Replay will be documented in this file.

## [0.2.0] - 2026-05-28

### Added
- **AI-powered `replay explain`** — explains any shell command using OpenAI chat completions
  - `--context` flag searches history for similar past commands as context
  - Supports `--plain` and `--output json`
- **AI-powered `replay summarize`** — generates natural language session summaries
  - `--session N` flag to select specific session
  - Includes detected fix patterns in the prompt
- **Direct bash/zsh history support** — no Atuin required
  - `--source auto/atuin/bash/zsh/all` flag on all commands
  - Reads `~/.bash_history` and `~/.zsh_history` directly
  - Merges and deduplicates when using `--source all`
- **`replay watch`** — real-time index updates, polls for new commands
- **`replay config set`** — set config values (model, api_key, base_url)
- **`replay config models`** — list available embedding models
- **`--output json`** on all commands for programmatic use
- **Embedding model switching** via `replay config set model <name>`
  - Supports jina-embeddings-v3, text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002
- Chat completions wrapper (`replay/search/chat.py`) with retry and secret filtering
- 11 new tests for chat module (160 total)

### Changed
- README rewritten with new commands, Codex integration docs, bash/zsh setup
- Website updated with AI features, typing animation, interactive stats, OG tags

## [0.1.0] - 2026-05-27

### Added
- Initial release
- Semantic search over terminal history using Jina AI embeddings + FAISS
- 9 CLI commands: search, init, refresh, list, history, fixes, stats, config, export
- Atuin SQLite integration for history capture
- Session clustering (Atuin session IDs + heuristic fallback)
- Fix detection (failure-then-success patterns)
- Secret filtering (16 regex patterns)
- Rich TUI and plain text output modes
- Local hash-based embedding fallback for offline use
- Landing page deployed on Vercel
- Published to PyPI as `replay-ai`
- 149 tests across 10 test files
