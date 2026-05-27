# Replay — AI Memory Layer for Humanity

> Semantic search over your terminal history. Never re-derive a fix you've already found.

[![PyPI version](https://img.shields.io/pypi/v/replay-ai)](https://pypi.org/project/replay-ai/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-160%20passed-brightgreen)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**[Website](https://replay-ai-memory-layer-for-humanity.vercel.app)** | **[PyPI](https://pypi.org/project/replay-ai/)** | **[GitHub](https://github.com/midlaj-muhammed/Replay-AI_Memory_Layer_for_Humanity)**

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

## Quick Start

```bash
pip install replay-ai
```

Set an API key (pick one):

```bash
# Jina AI — free, recommended
export JINA_API_KEY="jina_your-key-here"

# OpenAI — also works
export OPENAI_API_KEY="sk-your-key-here"

# Or save to config file
replay config set api_key jina_your-key-here
```

Build the index and search:

```bash
replay init
replay search "how did I fix that Docker thing"
```

**No Atuin? No problem.** Replay reads directly from `~/.bash_history` and `~/.zsh_history` too. Atuin is optional but gives richer data (timestamps, exit codes, session IDs).

```bash
replay init --source bash    # use bash history directly
replay init --source zsh     # use zsh history directly
replay init --source all     # merge all available sources
```

## All Commands

| Command | Description |
|---------|-------------|
| `replay search "query"` | Semantic search (auto-inits if needed) |
| `replay explain <command>` | AI explains what a command does and why |
| `replay summarize` | AI summarizes a terminal session |
| `replay init` | Build search index from history |
| `replay refresh` | Incremental update with new commands |
| `replay watch` | Real-time index updates (polls for new commands) |
| `replay list` | List all terminal sessions |
| `replay history` | Detailed command history by session |
| `replay fixes` | Show bug-fix patterns (failure to success) |
| `replay stats` | Index and history statistics |
| `replay config` | Show current configuration |
| `replay config set <key> <value>` | Set a config value (model, api_key, base_url) |
| `replay config models` | List available embedding models |
| `replay export` | Export index as JSON |

### Global Options

```bash
--source -s   # History source: auto, atuin, bash, zsh, all (default: auto)
--output -o   # Output format: json (for programmatic use)
--plain       # Plain text output (no Rich TUI, for SSH/CI/piping)
--limit -n    # Max results to show
--db          # Custom history file/database path
```

## AI-Powered Commands

### `replay explain` — Understand any command

```bash
$ replay explain "docker build -t app --no-cache ."

  explain  docker build -t app --no-cache .
  Builds a Docker image named "app" from the current directory. The --no-cache flag
  forces a fresh build by ignoring cached layers, useful when dependencies or base
  images have changed. The -t flag tags the image with the name "app".
```

With context from your history:

```bash
$ replay explain "git rebase -i HEAD~3" --context

  explain  git rebase -i HEAD~3
  Starts an interactive rebase of the last 3 commits. The -i flag opens your editor
  to reorder, squash, or edit commits. Based on your history, you've used this 12
  times — typically after finishing a feature branch before merging.
```

### `replay summarize` — Session recap

```bash
$ replay summarize

  session summary  /home/dev/api  8 cmds  15min
  The developer was debugging a Docker networking issue. They tried building the
  image, which failed due to a missing dependency. After installing the dependency
  with apt, the build succeeded. They then started the container with docker compose
  and verified it was running on port 8080.
```

### JSON output for scripting

```bash
replay search "docker" --output json | jq '.results[].command'
replay stats --output json | jq '.index_chunks'
replay explain "npm install" --output json | jq '.explanation'
```

## Codex Integration

Replay uses the **OpenAI Chat Completions API** to power its AI commands: `explain` and `summarize`. This gives you AI-generated explanations of any terminal command and natural language summaries of your sessions.

### Setup

You need an **OpenAI API key** for the AI commands (separate from the Jina key used for embeddings):

```bash
# Option 1: Environment variable
export OPENAI_API_KEY="sk-your-key-here"

# Option 2: Save to Replay config (recommended)
replay config set api_key sk-your-key-here
```

If you only have a Jina key, semantic search still works — but `explain` and `summarize` will show an error asking for an OpenAI key.

### What it does

**`replay explain`** sends the command (with optional context from your history) to GPT-4o-mini and returns a concise explanation of what the command does, what the flags mean, and why it might have been used:

```bash
# Basic explanation
replay explain "docker build -t app --no-cache ."

# With context from your history (searches for similar past commands)
replay explain "kubectl apply -f deployment.yaml" --context
```

**`replay summarize`** sends a session's command sequence to GPT-4o-mini and returns a natural language summary of what you were working on, what went wrong, and how you fixed it:

```bash
# Summarize the most recent session
replay summarize

# Summarize a specific session by index
replay summarize --session 5

# JSON output for scripting
replay summarize --output json | jq '.summary'
```

### How it works

1. Commands are filtered through the **secret redaction** layer (16 patterns) before being sent to the API
2. The `explain --context` flag uses FAISS semantic search to find similar past commands and includes them in the prompt
3. The `summarize` command detects fix patterns (failure-then-success) and includes them in the prompt
4. Both commands use exponential backoff retry (3 attempts) on API failures
5. The chat client reuses the same `openai_api_key` and `openai_base_url` config as the embedding client

### Custom base URL

If you're using an OpenAI-compatible proxy or a different provider:

```bash
replay config set base_url https://your-proxy.com/v1
```

## How It Works

```
History Sources -> Reader -> Cluster -> Chunker -> Secret Filter -> Embedder -> FAISS Index
(bash/zsh/Atuin)                |
                          Fix Detector (metadata enrichment)
```

1. **Capture** -- Reads commands from Atuin SQLite, `~/.bash_history`, or `~/.zsh_history`
2. **Cluster** -- Groups commands into sessions (by Atuin session ID, 15-min gap, directory change)
3. **Chunk** -- Structures each command: `"exit:0 | /home/dev/api | docker build -t app ."`
4. **Filter** -- Redacts 16 types of secrets (API keys, tokens, passwords) before embedding
5. **Embed** -- Jina AI `jina-embeddings-v3` (1024 dimensions, batched 100/call)
6. **Index** -- FAISS with cosine similarity, atomic writes (temp + rename)
7. **Search** -- Embed query -> FAISS search -> threshold filter -> rank by score

## Embedding Models

Switch models with `replay config set model <name>`:

| Model | Dimensions | Provider |
|-------|-----------|----------|
| `jina-embeddings-v3` | 1024 | Jina AI (free) |
| `text-embedding-3-small` | 1536 | OpenAI |
| `text-embedding-3-large` | 3072 | OpenAI |
| `text-embedding-ada-002` | 1536 | OpenAI (legacy) |

```bash
replay config set model text-embedding-3-small
replay init  # rebuild index with new model
```

## Privacy and Security

**Your data never leaves your machine** (except for embedding/API calls).

- Index stored locally at `~/.replay/index/`
- 16 secret patterns redacted before embedding:
  - OpenAI keys (`sk-`), GitHub tokens (`ghp_`, `gho_`, `github_pat_`)
  - AWS keys (`AKIA`), Slack tokens (`xoxb-`, `xoxp-`)
  - Bearer tokens, `password=`, `passwd=`, `PASS=`, `SECRET=`, `API_KEY=`
  - Authorization headers, long hex/base64 strings
- Config file stores API key locally at `~/.replay/config.toml`
- Secrets redacted before AI explain/summarize commands too
- No telemetry, no analytics, no cloud storage

## Development

```bash
git clone https://github.com/midlaj-muhammed/Replay-AI_Memory_Layer_for_Humanity.git
cd Replay-AI_Memory_Layer_for_Humanity/replay
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest -q
# 160 passed in 0.80s

# Run with coverage
pytest --cov=replay --cov-report=term-missing
```

## Architecture

```
replay/
+-- capture/
|   +-- atuin.py          # Atuin SQLite reader
|   +-- bash.py           # Bash/zsh history reader + unified dispatcher
+-- processing/
|   +-- cluster.py        # Session clustering
|   +-- chunker.py        # Structured chunk format
|   +-- fix_detector.py   # Failure->success patterns
|   +-- secret_filter.py  # Secret redaction (16 patterns)
+-- search/
|   +-- embedder.py       # Jina AI embeddings (batched)
|   +-- index.py          # FAISS index + JSON sidecar
|   +-- query.py          # Semantic search orchestration
|   +-- chat.py           # AI-powered explain/summarize
+-- display/
|   +-- tui.py            # Rich TUI output
|   +-- plain.py          # Plain text (--plain)
+-- cli.py                # 12 Typer commands
+-- config.py             # Config loading (TOML + env)
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and how to submit changes.

## License

[MIT](LICENSE)

---

*Built at the Codex AI Builder Hackathon (OpenAI x Outskill) by Muhammed Midlaj*
*Part of the "AI Memory Layer for Humanity" vision*
