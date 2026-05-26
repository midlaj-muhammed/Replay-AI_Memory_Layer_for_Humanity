# Replay — AI Memory Layer for Humanity

> Semantic search over your terminal history. Never re-derive a fix you've already found.

```
$ replay search "how did I fix Docker"
Found 3 matches for "how did I fix Docker":

  1. [87%] 3 weeks ago  | /home/dev/api
     [exit:0] sudo docker build -t app .

  2. [72%] yesterday    | /home/dev/web
     [exit:0] docker compose up -d

  3. [65%] 2 days ago   | /home/dev
     [exit:1] docker build .
```

## Requirements

- **Python 3.10+** (tested on 3.13)
- **[Atuin](https://atuin.sh/)** — terminal history engine (provides the data)
- **[Jina AI API key](https://jina.ai/)** — free, for semantic embeddings (or OpenAI API key)

## Quick Start

### 1. Install Atuin

Atuin captures and stores your terminal history in a local SQLite database.

```bash
# macOS
brew install atuin

# Linux (curl)
curl --proto '=https' --tlsv1.2 -sSf https://setup.atuin.sh | bash

# Then initialize for your shell
atuin init zsh >> ~/.zshrc   # or bash / fish
source ~/.zshrc

# Start recording history (Atuin replaces your shell history)
atuin sync
```

Verify Atuin is working:

```bash
atuin history list
# You should see your recent commands
```

### 2. Install Replay

```bash
# From PyPI (once published)
pip install replay-ai

# From source (development)
git clone <repo-url>
cd replay
pip install -e ".[dev]"
```

### 3. Get a Free Embedding API Key

Replay uses **Jina AI** for semantic embeddings — free, fast, and no credit card required.

**Option A — Jina AI (free, recommended):**

1. Go to [https://jina.ai](https://jina.ai) and sign up (free)
2. Copy your API key from the dashboard
3. Set it:

```bash
export JINA_API_KEY="jina_your-key-here"

# Add to your shell profile to persist:
echo 'export JINA_API_KEY="jina_your-key-here"' >> ~/.zshrc
```

**Option B — OpenAI (paid, also works):**

```bash
export OPENAI_API_KEY="sk-your-key-here"
```

**Option C — Config file (either provider):**

```bash
mkdir -p ~/.replay
cat > ~/.replay/config.toml << 'EOF'
[replay]
openai_api_key = "your-api-key-here"
EOF
```

### 4. Build the Index

```bash
replay init
```

This reads your Atuin history, chunks it, filters secrets, and builds a FAISS vector index. Takes ~10-30 seconds depending on history size.

```
Embedding chunks...  246/246
Index built: 246 chunks from 268 commands
```

### 5. Search!

```bash
# Semantic search
replay search "how did I fix that Docker thing"
replay search "nginx SSL config"
replay search "database migration rollback"

# With options
replay search "docker build" --threshold 0.5 --limit 10
replay search "git rebase" --plain    # no TUI, for piping
```

## All Commands

| Command | Description |
|---------|-------------|
| `replay search "query"` | Semantic search (auto-inits if needed) |
| `replay init` | Build search index from Atuin history |
| `replay refresh` | Incremental update with new commands |
| `replay list` | List all terminal sessions |
| `replay history` | Detailed command history by session |
| `replay fixes` | Show bug-fix patterns (failure to success) |
| `replay stats` | Index and history statistics |
| `replay config` | Show current configuration |
| `replay export` | Export index as JSON |

### Global Options

```bash
--plain     # Plain text output (no Rich TUI, for SSH/CI/piping)
--limit -n  # Max results to show
--db        # Custom Atuin database path
```

## How It Works

```
Atuin DB -> Reader -> Cluster -> Chunker -> Secret Filter -> Embedder -> FAISS Index
                          |
                    Fix Detector (metadata enrichment)
```

1. **Capture** -- Reads commands from Atuin's SQLite database
2. **Cluster** -- Groups commands into sessions (by Atuin session ID, 15-min gap, directory change)
3. **Chunk** -- Structures each command: `"exit:0 | /home/dev/api | docker build -t app ."`
4. **Filter** -- Redacts 16 types of secrets (API keys, tokens, passwords) before embedding
5. **Embed** -- Jina AI `jina-embeddings-v3` (1024 dimensions, batched 100/call)
6. **Index** -- FAISS with cosine similarity, atomic writes (temp + rename)
7. **Search** -- Embed query -> FAISS search -> threshold filter -> rank by score

## Privacy and Security

**Your data never leaves your machine** (except for the embedding API call).

- Index stored locally at `~/.replay/index/`
- 16 secret patterns redacted before embedding:
  - OpenAI keys (`sk-`), GitHub tokens (`ghp_`, `gho_`, `github_pat_`)
  - AWS keys (`AKIA`), Slack tokens (`xoxb-`, `xoxp-`)
  - Bearer tokens, `password=`, `passwd=`, `PASS=`, `SECRET=`, `API_KEY=`
  - Authorization headers, long hex/base64 strings
- Config file stores API key locally at `~/.replay/config.toml`
- No telemetry, no analytics, no cloud storage

## Demo: Fix Detection

```bash
$ replay fixes --plain

Found 3 fix patterns:

  1. 'docker build -t webapp .' failed, then 'sudo docker build -t webapp .' succeeded
     FAILED: exit:1 | /home/dev/webapp | docker build -t webapp .
     FIXED:   exit:0 | /home/dev/webapp | sudo docker build -t webapp .

  2. 'docker compose up' failed, then 'sudo docker compose up -d' succeeded
     FAILED: exit:1 | /home/dev | docker compose up
     FIXED:   exit:0 | /home/dev | sudo docker compose up -d
```

## Stats

```bash
$ replay stats --plain

Replay Stats
========================================
  Commands:     268
  Sessions:     212
  Fixes found:  18
  Index chunks: 246
  Index size:   5.8 MB
```

## Development

```bash
# Clone and install
git clone <repo-url>
cd replay
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest -q
# 149 passed in 0.96s

# Run with coverage
pytest --cov=replay --cov-report=term-missing
```

## Architecture

```
replay/
+-- capture/
|   +-- atuin.py          # Atuin SQLite reader
+-- processing/
|   +-- cluster.py        # Session clustering
|   +-- chunker.py        # Structured chunk format
|   +-- fix_detector.py   # Failure->success patterns
|   +-- secret_filter.py  # Secret redaction (16 patterns)
+-- search/
|   +-- embedder.py       # Jina AI embeddings (batched)
|   +-- index.py          # FAISS index + JSON sidecar
|   +-- query.py          # Semantic search orchestration
+-- display/
|   +-- tui.py            # Rich TUI output
|   +-- plain.py          # Plain text (--plain)
+-- cli.py                # 9 Typer commands
+-- config.py             # Config loading (TOML + env)
```

## License

MIT

---

*Built at the Codex AI Builder Hackathon (OpenAI x Outskill) by Muhammed Midlaj*
*Part of the "AI Memory Layer for Humanity" vision*
