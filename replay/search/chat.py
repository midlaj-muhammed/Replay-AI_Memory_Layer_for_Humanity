"""OpenAI chat completions wrapper for AI-powered command explanations."""

from __future__ import annotations

import time
from typing import List, Optional

from openai import OpenAI

from replay.processing.secret_filter import filter_secrets, filter_secrets_batch

DEFAULT_MODEL = "gpt-4o-mini"
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds, doubles on each retry

EXPLAIN_SYSTEM = (
    "You are a terminal command expert. Explain shell commands concisely for developers. "
    "Focus on: what the command does, what the flags mean, why it might have been used in this context. "
    "Keep explanations under 4 sentences. Be direct and technical."
)

SUMMARIZE_SYSTEM = (
    "You are a developer productivity analyst. Summarize terminal sessions concisely. "
    "Focus on: what the developer was working on, what went wrong, how they fixed it. "
    "Keep summaries under 6 sentences. Be specific about commands and outcomes."
)


class ChatError(Exception):
    """Raised when chat completion fails."""


class Chat:
    """Wraps the OpenAI chat completions API with retry."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, base_url: Optional[str] = None):
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def explain(
        self,
        command: str,
        exit_status: int = 0,
        cwd: str = "",
        duration_ms: int = 0,
        context_commands: Optional[List[dict]] = None,
    ) -> str:
        """Explain a shell command using AI.

        Args:
            command: The shell command to explain.
            exit_status: Exit code of the command.
            cwd: Working directory where command was run.
            duration_ms: Duration in milliseconds.
            context_commands: Optional list of similar past commands for context.

        Returns:
            AI-generated explanation string.

        Raises:
            ChatError: If the API fails after all retries.
        """
        command = filter_secrets(command)

        user_parts = [f"Command: {command}"]
        if exit_status != 0:
            user_parts.append(f"Exit status: {exit_status} (failed)")
        if cwd:
            user_parts.append(f"Working directory: {cwd}")
        if duration_ms > 0:
            user_parts.append(f"Duration: {duration_ms}ms")

        if context_commands:
            user_parts.append("\nSimilar past commands used in this project:")
            for ctx in context_commands[:5]:
                ctx_cmd = filter_secrets(ctx.get("command", ""))
                ctx_exit = ctx.get("exit_status", 0)
                ctx_cwd = ctx.get("cwd", "")
                user_parts.append(f"  - {ctx_cmd} (exit:{ctx_exit}, {ctx_cwd})")

        return self._chat(EXPLAIN_SYSTEM, "\n".join(user_parts))

    def summarize(
        self,
        commands: List[dict],
        primary_cwd: str = "",
        duration_s: float = 0,
        fixes: Optional[List[dict]] = None,
    ) -> str:
        """Summarize a terminal session using AI.

        Args:
            commands: List of command dicts with 'command', 'exit_status', 'cwd'.
            primary_cwd: Primary working directory of the session.
            duration_s: Session duration in seconds.
            fixes: Optional list of fix dicts with 'description'.

        Returns:
            AI-generated summary string.

        Raises:
            ChatError: If the API fails after all retries.
        """
        duration_min = duration_s / 60 if duration_s else 0
        header = f"Session"
        if primary_cwd:
            header += f" in {primary_cwd}"
        if duration_min > 0:
            header += f" ({duration_min:.0f}min"
            if commands:
                header += f", {len(commands)} commands"
            header += ")"
        elif commands:
            header += f" ({len(commands)} commands)"

        lines = [header + ":\n"]
        for cmd in commands[:50]:  # Cap at 50 commands to stay within token limits
            text = filter_secrets(cmd.get("command", ""))
            status = cmd.get("exit_status", 0)
            lines.append(f"  exit:{status} | {text}")

        if fixes:
            lines.append("\nFixes detected:")
            for fix in fixes[:10]:
                desc = fix.get("description", "")
                lines.append(f"  - {filter_secrets(desc)}")

        return self._chat(SUMMARIZE_SYSTEM, "\n".join(lines))

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request with exponential backoff retry.

        Args:
            system_prompt: System message content.
            user_prompt: User message content.

        Returns:
            The assistant's response text.

        Raises:
            ChatError: If the API fails after all retries.
        """
        delay = RETRY_DELAY
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=500,
                    temperature=0.3,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise ChatError(
                        f"Chat completion failed after {MAX_RETRIES} attempts: {e}"
                    ) from e
                time.sleep(delay)
                delay *= 2
        return ""  # unreachable
