# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Replay, please report it responsibly.

**Do not open a public issue.** Instead, email the maintainer directly or use GitHub's private vulnerability reporting.

### What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

### What to expect

- Acknowledgment within 48 hours
- A fix or mitigation plan within 7 days for critical issues
- Credit in the release notes (unless you prefer to remain anonymous)

## Security Design

Replay handles sensitive data (terminal commands may contain secrets). Here's how we protect it:

### Secret Filtering

16 regex patterns redact secrets before they leave your machine:

- OpenAI API keys (`sk-`)
- GitHub tokens (`ghp_`, `gho_`, `github_pat_`)
- AWS access keys (`AKIA`)
- Slack tokens (`xoxb-`, `xoxp-`)
- Bearer tokens
- Password fields (`password=`, `passwd=`, `PASS=`, `SECRET=`, `API_KEY=`)
- Authorization headers
- Long hex and base64 strings

### Local-First Architecture

- The search index is stored locally at `~/.replay/index/`
- Config with API keys is stored at `~/.replay/config.toml`
- Only the embedding API call sends text off-machine (and only after secret filtering)
- The `replay explain` and `replay summarize` commands also filter secrets before sending to the LLM API

### What Never Leaves Your Machine

- Raw command history
- Working directories
- Session data
- Exit codes
- Hostnames

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes |
| 0.1.x   | Yes |
| < 0.1   | No |
