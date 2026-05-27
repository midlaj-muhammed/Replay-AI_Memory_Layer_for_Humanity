"""Tests for the chat module (AI-powered explanations)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from replay.search.chat import Chat, ChatError, EXPLAIN_SYSTEM, SUMMARIZE_SYSTEM


def _make_chat_response(content: str = "test response"):
    """Build a mock OpenAI chat completion response."""
    mock = MagicMock()
    mock.choices = [MagicMock()]
    mock.choices[0].message.content = content
    return mock


class TestChatExplain:
    """Test the explain() method."""

    @patch("replay.search.chat.OpenAI")
    def test_explain_basic(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_chat_response(
            "git log shows commit history. The --oneline flag condenses output to one line per commit. "
            "-5 limits to the last 5 commits."
        )

        chat = Chat(api_key="sk-test")
        result = chat.explain("git log --oneline -5")

        assert "git log" in result
        assert "oneline" in result
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs["messages"][0]["role"] == "system"
        assert "git log --oneline -5" in call_args.kwargs["messages"][1]["content"]

    @patch("replay.search.chat.OpenAI")
    def test_explain_with_exit_status(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_chat_response("This command failed.")

        chat = Chat(api_key="sk-test")
        result = chat.explain("docker build .", exit_status=1, cwd="/app")

        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "Exit status: 1" in user_msg
        assert "Working directory: /app" in user_msg

    @patch("replay.search.chat.OpenAI")
    def test_explain_with_context(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_chat_response("Explanation with context.")

        chat = Chat(api_key="sk-test")
        context = [
            {"command": "git status", "exit_status": 0, "cwd": "/dev"},
            {"command": "git add .", "exit_status": 0, "cwd": "/dev"},
        ]
        result = chat.explain("git commit -m 'fix'", context_commands=context)

        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "Similar past commands" in user_msg
        assert "git status" in user_msg

    @patch("replay.search.chat.OpenAI")
    def test_explain_filters_secrets(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_chat_response("Filtered.")

        chat = Chat(api_key="sk-test")
        chat.explain("curl -H 'Authorization: Bearer sk-proj_abc123def456ghi789jkl012mno345' https://api.example.com")

        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "sk-proj_abc123def456ghi789jkl012mno345" not in user_msg
        assert "[REDACTED" in user_msg


class TestChatSummarize:
    """Test the summarize() method."""

    @patch("replay.search.chat.OpenAI")
    def test_summarize_basic(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_chat_response(
            "The developer was working on a Docker deployment. They built the image and started containers."
        )

        chat = Chat(api_key="sk-test")
        commands = [
            {"command": "docker build -t app .", "exit_status": 0, "cwd": "/app"},
            {"command": "docker compose up -d", "exit_status": 0, "cwd": "/app"},
        ]
        result = chat.summarize(commands, primary_cwd="/app", duration_s=300)

        assert "Docker" in result
        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "/app" in user_msg
        assert "5min" in user_msg

    @patch("replay.search.chat.OpenAI")
    def test_summarize_with_fixes(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_chat_response("Fixed by adding sudo.")

        chat = Chat(api_key="sk-test")
        commands = [
            {"command": "docker build .", "exit_status": 1, "cwd": "/app"},
            {"command": "sudo docker build .", "exit_status": 0, "cwd": "/app"},
        ]
        fixes = [{"description": "'docker build .' failed, then 'sudo docker build .' succeeded"}]
        result = chat.summarize(commands, primary_cwd="/app", fixes=fixes)

        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "Fixes detected" in user_msg

    @patch("replay.search.chat.OpenAI")
    def test_summarize_caps_at_50_commands(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_chat_response("Summary.")

        chat = Chat(api_key="sk-test")
        commands = [{"command": f"cmd{i}", "exit_status": 0, "cwd": "/app"} for i in range(100)]
        chat.summarize(commands, primary_cwd="/app")

        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "cmd0" in user_msg
        assert "cmd49" in user_msg
        assert "cmd50" not in user_msg  # capped at 50


class TestChatRetry:
    """Test retry behavior."""

    @patch("replay.search.chat.OpenAI")
    @patch("replay.search.chat.time.sleep")
    def test_retry_on_failure(self, mock_sleep, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = [
            Exception("API error"),
            Exception("API error"),
            _make_chat_response("Success after retry"),
        ]

        chat = Chat(api_key="sk-test")
        result = chat.explain("ls -la")

        assert result == "Success after retry"
        assert mock_client.chat.completions.create.call_count == 3
        assert mock_sleep.call_count == 2  # Two retries

    @patch("replay.search.chat.OpenAI")
    @patch("replay.search.chat.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")

        chat = Chat(api_key="sk-test")
        with pytest.raises(ChatError, match="failed after 3 attempts"):
            chat.explain("ls -la")

        assert mock_client.chat.completions.create.call_count == 3


class TestChatInit:
    """Test client initialization."""

    @patch("replay.search.chat.OpenAI")
    def test_default_model(self, mock_openai_cls):
        chat = Chat(api_key="sk-test")
        assert chat.model == "gpt-4o-mini"

    @patch("replay.search.chat.OpenAI")
    def test_custom_model_and_base_url(self, mock_openai_cls):
        chat = Chat(api_key="sk-test", model="gpt-4o", base_url="https://custom.api.com/v1")
        mock_openai_cls.assert_called_once_with(api_key="sk-test", base_url="https://custom.api.com/v1")
        assert chat.model == "gpt-4o"
