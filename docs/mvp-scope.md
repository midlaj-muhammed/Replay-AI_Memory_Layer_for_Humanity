# AI Memory Layer for Humanity — MVP Scope

## MVP Definition

**One sentence:** A CLI tool that lets developers search their terminal history using natural language.

**Demo moment:** `replay search "how did I fix that Docker thing"` → instant result from 3 weeks ago.

## What's IN the MVP (Must-Have)

### Core Features (built, tested)

| Feature | Status | Tests |
|---------|--------|-------|
| Atuin history capture | Done | 8 |
| Session clustering | Done | 10 |
| Command chunking (structured format) | Done | 34 |
| Fix detection (failure→success) | Done | 15 |
| Secret filtering (16 patterns) | Done | 28 |
| OpenAI embeddings (batched) | Done | 8 |
| FAISS vector index | Done | 26 |
| Semantic search with threshold | Done | 10 |
| Auto-init on first search | Done | - |
| Incremental refresh | Done | - |
| `replay search "query"` | Done | - |
| `replay list` | Done | 5 |
| `replay history` | Done | - |
| `replay fixes` | Done | - |
| `replay stats` | Done | 13 |
| `replay config` | Done | - |
| `replay export` | Done | - |
| Rich TUI display | Done | - |
| `--plain` mode (SSH/CI) | Done | - |
| Config file + env vars | Done | - |

**Total: 149 tests passing, 9 CLI commands**

### Polish (Day 5, done)

- Error messages with actionable guidance
- Masked API key in config display
- Atomic writes (no index corruption on crash)
- Graceful handling of missing DB, corrupted DB, empty history

## What's OUT of MVP (Future)

### v2 — Team Memory
- Shared indexes across team
- Git commit + PR context integration
- Slack/Teams integration for decision capture
- Web dashboard

### v3 — Cross-Tool Memory
- Browser history integration
- Email context
- Meeting transcripts
- Phone/wearable capture

### v4 — Universal Memory
- Cross-device sync
- Privacy-preserving federated learning
- API for third-party AI tools
- Mobile app

## Architecture Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| History source | Atuin | Already structured, SQLite, cross-platform, open source |
| Embedding model | text-embedding-3-small | Fast, cheap ($0.02/1M tokens), 1536-dim, good quality |
| Vector store | FAISS | Local, no cloud dependency, fast, battle-tested |
| CLI framework | Typer + Rich | Python-native, beautiful TUI, great DX |
| Package manager | uv | 10-100x faster than pip, Kali-compatible |
| Python version | 3.13 | 3.14 breaks ML packages (learned the hard way) |
| Build system | setuptools | hatchling fails on this directory layout in Kali |
| Chunk format | Structured `"exit:0 \| /path \| cmd"` | Preserves exit_status signal for relevance |
| Similarity metric | Cosine (via normalized inner product) | Standard for text embeddings, FAISS native |
| Index persistence | FAISS binary + JSON sidecar | Atomic writes, human-readable metadata |

## Demo Script (3 minutes)

### Setup
- Terminal with Atuin installed (268 real commands)
- Replay installed and indexed

### Demo Flow

**0:00 — The Problem** (30s)
> "Every developer wastes 30 minutes a day re-finding solutions they've already discovered. Your terminal history has the answers, but it's buried."

**0:30 — The Solution** (60s)
```bash
# Show what we're searching through
$ replay list --plain | head -5
# 212 sessions, 268 commands

# The money shot
$ replay search "how did I fix Docker"
# → Instant results, ranked by similarity

# Show fix detection
$ replay fixes --plain
# → "docker build . failed, then sudo docker build . succeeded"
```

**1:30 — How It Works** (45s)
> "Under the hood: Atuin captures history → chunker structures it → secret filter redacts keys → OpenAI embeds → FAISS indexes. All local. Your data never leaves your machine."

**2:15 — The Numbers** (30s)
```bash
$ replay stats --plain
# Commands: 268
# Sessions: 212
# Fixes found: 18
# Tests: 149 passing

$ replay config --plain
# Shows: API key masked, model, paths
```

**2:45 — The Vision** (15s)
> "Terminal history is just the start. The AI Memory Layer will remember everything — across tools, across time, across contexts. You should never explain the same thing twice to an AI."

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| No Atuin installed | Clear error with install instructions |
| No OpenAI API key | Clear error with setup instructions |
| Empty history | Graceful message with suggestion |
| Corrupted DB | Catches and reports cleanly |
| API rate limiting | Exponential backoff retry (3 attempts) |
| Index corruption | Atomic writes (temp + rename) |
| Secrets in embeddings | 16 regex patterns redact before embedding |
| Slow embedding | Batched 100/call, ~250 chunks in ~10s |
| Bad search results | Threshold filtering (default 0.3) |

## Success Metrics for Hackathon

| Metric | Target | Current |
|--------|--------|---------|
| Tests passing | 100+ | 149 |
| CLI commands | 8+ | 9 |
| Real data demo | Yes | 268 commands, 18 fixes |
| Privacy-first | Yes | Local FAISS, secret filtering |
| Cross-platform | Linux + Mac | Tested on Kali Linux |
| Install complexity | 1 command | `pip install replay` (planned) |
