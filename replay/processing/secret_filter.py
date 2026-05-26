"""Filter secrets from command text before sending to embedding API.

Scans for common secret patterns and replaces them with [REDACTED].
Handles inline secrets in curl headers, env vars, and command arguments.
"""

from __future__ import annotations

import re
from typing import List

# Secret patterns to detect and redact.
# Each pattern matches a known secret prefix + a long alphanumeric suffix.
SECRET_PATTERNS = [
    # OpenAI API keys
    (re.compile(r'sk-[A-Za-z0-9]{20,}'), '[REDACTED]'),
    # GitHub personal access tokens
    (re.compile(r'ghp_[A-Za-z0-9]{20,}'), '[REDACTED]'),
    # GitHub OAuth tokens
    (re.compile(r'gho_[A-Za-z0-9]{20,}'), '[REDACTED]'),
    # GitHub fine-grained tokens
    (re.compile(r'github_pat_[A-Za-z0-9_]{20,}'), '[REDACTED]'),
    # AWS access key IDs
    (re.compile(r'AKIA[A-Z0-9]{16}'), '[REDACTED]'),
    # Slack tokens
    (re.compile(r'xoxb-[A-Za-z0-9-]{20,}'), '[REDACTED]'),
    (re.compile(r'xoxp-[A-Za-z0-9-]{20,}'), '[REDACTED]'),
    # Bearer tokens in headers (e.g., curl -H "Authorization: Bearer sk-abc123")
    (re.compile(r'Bearer\s+[A-Za-z0-9_\-\.]{20,}'), 'Bearer [REDACTED]'),
    # password= patterns
    (re.compile(r'password=\S+'), 'password=[REDACTED]'),
    # passwd= patterns
    (re.compile(r'passwd=\S+'), 'passwd=[REDACTED]'),
    # PASS= patterns
    (re.compile(r'PASS=\S+'), 'PASS=[REDACTED]'),
    # SECRET= patterns
    (re.compile(r'SECRET=\S+'), 'SECRET=[REDACTED]'),
    # API_KEY= patterns
    (re.compile(r'API_KEY=\S+'), 'API_KEY=[REDACTED]'),
    # Authorization: headers
    (re.compile(r'Authorization:\s*\S+\s+[A-Za-z0-9_\-\.]{20,}'), 'Authorization: [REDACTED]'),
    # Generic long hex strings (40+ chars) that look like tokens
    (re.compile(r'\b[A-Fa-f0-9]{40,}\b'), '[REDACTED]'),
    # Generic long base64-like strings (40+ chars, no spaces)
    (re.compile(r'\b[A-Za-z0-9+/]{40,}={0,2}\b'), '[REDACTED]'),
]


def filter_secrets(text: str) -> str:
    """Redact secrets from text.

    Scans for known secret patterns and replaces them with [REDACTED].
    Preserves the semantic meaning of the chunk (exit status, cwd, command
    structure) while preventing secret exfiltration to the embedding API.

    Args:
        text: Chunk text that may contain secrets.

    Returns:
        Text with secrets replaced by [REDACTED].
    """
    result = text
    for pattern, replacement in SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def filter_secrets_batch(texts: List[str]) -> List[str]:
    """Redact secrets from a batch of texts."""
    return [filter_secrets(text) for text in texts]
