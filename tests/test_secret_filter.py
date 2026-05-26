"""Tests for the secret filter module."""

from __future__ import annotations

import pytest

from replay.processing.secret_filter import (
    SECRET_PATTERNS,
    filter_secrets,
    filter_secrets_batch,
)


class TestFilterSecrets:
    """Test individual secret pattern detection and redaction."""

    def test_openai_api_key(self):
        text = "curl -H 'Authorization: Bearer sk-abc123def456ghi789jkl012mno345'"
        result = filter_secrets(text)
        assert "sk-abc123def456ghi789jkl012mno345" not in result
        assert "[REDACTED]" in result

    def test_github_pat(self):
        text = "git clone https://ghp_abcdefghijklmnopqrst:github.com/user/repo"
        result = filter_secrets(text)
        assert "ghp_abcdefghijklmnopqrst" not in result
        assert "[REDACTED]" in result

    def test_github_oauth_token(self):
        text = "gho_abcdefghijklmnopqrst123456"
        result = filter_secrets(text)
        assert "gho_abcdefghijklmnopqrst123456" not in result

    def test_github_fine_grained_token(self):
        text = "github_pat_11ABCDEFGHijklmnop_abcdefghijklmnop"
        result = filter_secrets(text)
        assert "github_pat_" not in result
        assert "[REDACTED]" in result

    def test_aws_access_key(self):
        text = "export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        result = filter_secrets(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[REDACTED]" in result

    def test_slack_bot_token(self):
        text = "token=xoxb-123456789012-1234567890123-abcdefghij"
        result = filter_secrets(text)
        assert "xoxb-" not in result
        assert "[REDACTED]" in result

    def test_slack_user_token(self):
        text = "token=xoxp-123456789012-1234567890123-abcdefghij"
        result = filter_secrets(text)
        assert "xoxp-" not in result
        assert "[REDACTED]" in result

    def test_bearer_token(self):
        text = 'curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"'
        result = filter_secrets(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "Bearer [REDACTED]" in result

    def test_password_equals(self):
        text = "mysql -u root -p'mypassword123' should not be matched"
        # password= pattern
        text2 = "DB password=supersecretvalue123 connect"
        result = filter_secrets(text2)
        assert "supersecretvalue123" not in result
        assert "password=[REDACTED]" in result

    def test_passwd_equals(self):
        text = "passwd=abc123def456ghi789"
        result = filter_secrets(text)
        assert "abc123def456ghi789" not in result
        assert "passwd=[REDACTED]" in result

    def test_pass_equals(self):
        text = "PASS=mysupersecretvalue123"
        result = filter_secrets(text)
        assert "mysupersecretvalue123" not in result
        assert "PASS=[REDACTED]" in result

    def test_secret_equals(self):
        text = "SECRET=my-api-secret-value-12345"
        result = filter_secrets(text)
        assert "my-api-secret-value-12345" not in result
        assert "SECRET=[REDACTED]" in result

    def test_api_key_equals(self):
        text = "API_KEY=sk-proj-abc123def456ghi789"
        result = filter_secrets(text)
        assert "sk-proj-abc123def456ghi789" not in result
        assert "API_KEY=[REDACTED]" in result

    def test_authorization_header(self):
        # Token must match [A-Za-z0-9_\-\.]{20,} (no = padding)
        text = "Authorization: Basic dGhpc0lzQUxvbmdUb2tlbldpdGhvdXRQYWRkaW5n"
        result = filter_secrets(text)
        assert "dGhpc0lzQUxvbmdUb2tlbldpdGhvdXRQYWRkaW5n" not in result
        assert "Authorization: [REDACTED]" in result

    def test_long_hex_string(self):
        text = "commit abc123def456abc123def456abc123def456abc1"
        result = filter_secrets(text)
        assert "abc123def456abc123def456abc123def456abc1" not in result
        assert "[REDACTED]" in result

    def test_long_base64_string(self):
        text = "token dGhpc0lzQVZlcnlMb25nQmFzZTY0U3RyaW5nSGVyZQ=="
        result = filter_secrets(text)
        assert "dGhpc0lzQVZlcnlMb25nQmFzZTY0U3RyaW5nSGVyZQ==" not in result
        assert "[REDACTED]" in result


class TestFilterSecretsClean:
    """Test that clean text passes through unchanged."""

    def test_clean_command_passes_through(self):
        text = "exit:0 | /home/dev | docker build -t app ."
        assert filter_secrets(text) == text

    def test_git_command_passes_through(self):
        text = "exit:0 | /home/dev | git commit -m 'initial commit'"
        assert filter_secrets(text) == text

    def test_npm_command_passes_through(self):
        text = "exit:0 | /home/dev | npm install express"
        assert filter_secrets(text) == text

    def test_short_strings_not_redacted(self):
        """Short alphanumeric strings should not be redacted."""
        text = "exit:0 | /tmp | echo hello world"
        assert filter_secrets(text) == text

    def test_exit_status_preserved(self):
        text = "exit:1 | /home/dev/api | pytest tests/"
        assert filter_secrets(text) == text

    def test_structured_chunk_preserved(self):
        text = "exit:1 | /home/dev | cmd1 ; exit:0 | /home/dev | cmd2"
        assert filter_secrets(text) == text


class TestFilterSecretsMultiple:
    """Test multiple secrets in a single string."""

    def test_two_secrets_in_one_line(self):
        text = "curl -H 'Bearer sk-abc123def456ghi789jkl012' -d 'key=AKIAIOSFODNN7EXAMPLE'"
        result = filter_secrets(text)
        assert "sk-abc123def456ghi789jkl012" not in result
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert result.count("[REDACTED]") >= 2


class TestFilterSecretsBatch:
    """Test batch filtering."""

    def test_batch_returns_same_length(self):
        texts = ["clean text", "sk-abc123def456ghi789jkl012", "exit:0 | /tmp | ls"]
        results = filter_secrets_batch(texts)
        assert len(results) == len(texts)

    def test_batch_filters_each(self):
        texts = [
            "sk-abc123def456ghi789jkl012",
            "ghp_abcdefghijklmnopqrst",
        ]
        results = filter_secrets_batch(texts)
        for result in results:
            assert "[REDACTED]" in result

    def test_batch_empty(self):
        assert filter_secrets_batch([]) == []


class TestSecretPatternCount:
    """Verify we have all expected patterns."""

    def test_minimum_pattern_count(self):
        """Should have at least 15 secret patterns."""
        assert len(SECRET_PATTERNS) >= 15

    def test_patterns_are_compiled(self):
        """Each pattern should be a (compiled_regex, replacement) tuple."""
        for pattern, replacement in SECRET_PATTERNS:
            assert hasattr(pattern, "sub"), "Pattern should be compiled regex"
            assert isinstance(replacement, str), "Replacement should be a string"
