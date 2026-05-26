"""Tests for the chunker module."""

from __future__ import annotations

import pytest

from replay.capture.atuin import Command
from replay.processing.chunker import (
    CONTEXT_WINDOW,
    TRIVIAL_COMMANDS,
    Chunk,
    _build_chunk_text,
    _is_trivial,
    chunk_session,
    chunk_sessions,
)
from replay.processing.cluster import Session


def _cmd(
    id: str,
    command: str,
    exit_status: int = 0,
    cwd: str = "/home/dev",
    timestamp: int = 1000,
    session: str = "s1",
) -> Command:
    return Command(
        id=id,
        timestamp=timestamp,
        duration=0,
        exit_status=exit_status,
        command=command,
        cwd=cwd,
        hostname="laptop",
        session=session,
    )


def _session(commands: list[Command], session_id: str = "s1") -> Session:
    return Session(session_id=session_id, commands=commands)


class TestIsTrivial:
    """Test _is_trivial command detection."""

    @pytest.mark.parametrize("cmd_text", sorted(TRIVIAL_COMMANDS))
    def test_trivial_exact_matches(self, cmd_text):
        cmd = _cmd("1", cmd_text)
        assert _is_trivial(cmd) is True

    def test_cd_with_path_is_trivial(self):
        assert _is_trivial(_cmd("1", "cd /tmp")) is True

    def test_echo_no_args_is_trivial(self):
        assert _is_trivial(_cmd("1", "echo")) is True

    def test_echo_with_args_is_not_trivial(self):
        assert _is_trivial(_cmd("1", "echo hello")) is False

    def test_git_status_is_not_trivial(self):
        assert _is_trivial(_cmd("1", "git status")) is False

    def test_docker_build_is_not_trivial(self):
        assert _is_trivial(_cmd("1", "docker build .")) is False

    def test_trailing_whitespace_still_trivial(self):
        # _is_trivial strips whitespace, so "ls  " becomes "ls"
        assert _is_trivial(_cmd("1", "ls  ")) is True

    def test_non_trivial_commands(self):
        non_trivial = [
            "docker build -t app .",
            "git commit -m 'fix'",
            "npm install",
            "python manage.py runserver",
            "curl https://example.com",
        ]
        for cmd_text in non_trivial:
            assert _is_trivial(_cmd("1", cmd_text)) is False, f"'{cmd_text}' should not be trivial"


class TestBuildChunkText:
    """Test _build_chunk_text structured format."""

    def test_single_command_no_context(self):
        cmd = _cmd("1", "docker build .", exit_status=0, cwd="/home/dev/api")
        text = _build_chunk_text(cmd, [], [])
        assert text == "exit:0 | /home/dev/api | docker build ."

    def test_failed_command(self):
        cmd = _cmd("1", "pytest tests/", exit_status=1, cwd="/home/dev/api")
        text = _build_chunk_text(cmd, [], [])
        assert text == "exit:1 | /home/dev/api | pytest tests/"

    def test_with_context_before(self):
        ctx = [_cmd("0", "cd /home/dev/api", cwd="/home/dev")]
        cmd = _cmd("1", "docker build .", exit_status=0, cwd="/home/dev/api")
        text = _build_chunk_text(cmd, ctx, [])
        assert text == "exit:0 | /home/dev | cd /home/dev/api ; exit:0 | /home/dev/api | docker build ."

    def test_with_context_after(self):
        cmd = _cmd("1", "pytest", exit_status=1, cwd="/home/dev/api")
        ctx = [_cmd("2", "pytest --fix", exit_status=0, cwd="/home/dev/api")]
        text = _build_chunk_text(cmd, [], ctx)
        assert text == "exit:1 | /home/dev/api | pytest ; exit:0 | /home/dev/api | pytest --fix"

    def test_with_context_both(self):
        before = [_cmd("0", "git pull", cwd="/home/dev/api")]
        cmd = _cmd("1", "docker build .", exit_status=1, cwd="/home/dev/api")
        after = [_cmd("2", "docker build -t app .", exit_status=0, cwd="/home/dev/api")]
        text = _build_chunk_text(cmd, before, after)
        assert "git pull" in text
        assert "docker build ." in text
        assert "docker build -t app ." in text
        # Should be semicolon-separated
        parts = text.split(" ; ")
        assert len(parts) == 3

    def test_context_commands_preserve_exit_status(self):
        before = [_cmd("0", "failing-cmd", exit_status=1)]
        cmd = _cmd("1", "fix-cmd", exit_status=0)
        text = _build_chunk_text(cmd, before, [])
        assert "exit:1 |" in text
        assert "exit:0 |" in text


class TestChunkSession:
    """Test chunk_session function."""

    def test_empty_session_returns_empty(self):
        session = _session([])
        assert chunk_session(session) == []

    def test_all_trivial_returns_empty(self):
        commands = [_cmd("1", "cd"), _cmd("2", "ls"), _cmd("3", "pwd")]
        session = _session(commands)
        assert chunk_session(session) == []

    def test_single_non_trivial_command(self):
        commands = [_cmd("1", "docker build .")]
        session = _session(commands)
        chunks = chunk_session(session)
        assert len(chunks) == 1
        assert chunks[0].command.command == "docker build ."
        assert chunks[0].session_id == "s1"

    def test_skips_trivial_as_primary(self):
        commands = [
            _cmd("1", "cd /tmp"),
            _cmd("2", "git status"),
            _cmd("3", "ls"),
            _cmd("4", "docker build ."),
        ]
        session = _session(commands)
        chunks = chunk_session(session)
        assert len(chunks) == 2
        assert chunks[0].command.command == "git status"
        assert chunks[1].command.command == "docker build ."

    def test_trivial_included_as_context(self):
        commands = [
            _cmd("1", "cd /home/dev/api"),
            _cmd("2", "docker build ."),
        ]
        session = _session(commands)
        chunks = chunk_session(session)
        assert len(chunks) == 1
        # cd should appear as context before
        assert len(chunks[0].context_before) == 1
        assert chunks[0].context_before[0].command == "cd /home/dev/api"

    def test_context_window_respected(self):
        # Create 5 non-trivial commands, verify context window limit
        commands = [
            _cmd("1", f"cmd-{i}", timestamp=1000 + i * 100)
            for i in range(5)
        ]
        session = _session(commands)
        chunks = chunk_session(session)

        # Middle command should have exactly CONTEXT_WINDOW before/after
        mid = chunks[2]
        assert len(mid.context_before) <= CONTEXT_WINDOW
        assert len(mid.context_after) <= CONTEXT_WINDOW

    def test_chunk_preserves_command_reference(self):
        cmd = _cmd("1", "npm install", timestamp=42)
        session = _session([cmd])
        chunks = chunk_session(session)
        assert chunks[0].command is cmd
        assert chunks[0].timestamp == 42
        assert chunks[0].cwd == "/home/dev"
        assert chunks[0].exit_status == 0

    def test_chunk_text_format(self):
        commands = [_cmd("1", "docker build -t app .", exit_status=0, cwd="/home/dev/api")]
        session = _session(commands)
        chunks = chunk_session(session)
        assert chunks[0].chunk_text == "exit:0 | /home/dev/api | docker build -t app ."


class TestChunkSessions:
    """Test chunk_sessions (plural) function."""

    def test_empty_sessions(self):
        assert chunk_sessions([]) == []

    def test_multiple_sessions(self):
        s1 = _session([_cmd("1", "git status")], "s1")
        s2 = _session([_cmd("2", "npm install")], "s2")
        chunks = chunk_sessions([s1, s2])
        assert len(chunks) == 2
        assert chunks[0].session_id == "s1"
        assert chunks[1].session_id == "s2"

    def test_preserves_order(self):
        s1 = _session([_cmd("1", "first")], "s1")
        s2 = _session([_cmd("2", "second")], "s2")
        chunks = chunk_sessions([s1, s2])
        assert chunks[0].command.command == "first"
        assert chunks[1].command.command == "second"


class TestChunkDataclass:
    """Test Chunk dataclass properties."""

    def test_properties(self):
        cmd = _cmd("1", "test", exit_status=1, cwd="/tmp", timestamp=9999)
        chunk = Chunk(
            command=cmd,
            chunk_text="test",
            context_before=[],
            context_after=[],
            session_id="sess",
        )
        assert chunk.timestamp == 9999
        assert chunk.cwd == "/tmp"
        assert chunk.exit_status == 1
        assert chunk.session_id == "sess"
