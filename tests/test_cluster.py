"""Tests for session clustering."""

from __future__ import annotations

from typing import List

import pytest

from replay.capture.atuin import Command
from replay.processing.cluster import GAP_THRESHOLD_NS, Session, cluster_commands


def _make_command(
    id: str,
    timestamp: int,
    command: str = "ls",
    exit_status: int = 0,
    cwd: str = "/home/dev",
    hostname: str = "laptop",
    session: str = "",
) -> Command:
    return Command(
        id=id,
        timestamp=timestamp,
        duration=0,
        exit_status=exit_status,
        command=command,
        cwd=cwd,
        hostname=hostname,
        session=session,
    )


class TestClusterBySessionId:
    """Test clustering when Atuin session IDs are present."""

    def test_groups_by_session_id(self):
        """Commands with the same session ID should be grouped together."""
        commands = [
            _make_command("1", 1000, session="sess-a"),
            _make_command("2", 2000, session="sess-a"),
            _make_command("3", 3000, session="sess-b"),
        ]

        sessions = cluster_commands(commands)

        assert len(sessions) == 2
        assert sessions[0].session_id == "sess-a"
        assert sessions[0].command_count == 2
        assert sessions[1].session_id == "sess-b"
        assert sessions[1].command_count == 1

    def test_preserves_command_order(self):
        """Commands within a session should maintain timestamp order."""
        commands = [
            _make_command("1", 1000, "first", session="sess-a"),
            _make_command("2", 2000, "second", session="sess-a"),
            _make_command("3", 3000, "third", session="sess-a"),
        ]

        sessions = cluster_commands(commands)

        assert len(sessions) == 1
        assert sessions[0].commands[0].command == "first"
        assert sessions[0].commands[1].command == "second"
        assert sessions[0].commands[2].command == "third"


class TestClusterByHeuristic:
    """Test clustering when no session IDs are present."""

    def test_splits_on_time_gap(self):
        """Commands with >15 min gap should be split into separate sessions."""
        base = 1000
        gap = GAP_THRESHOLD_NS + 1  # just over 15 min

        commands = [
            _make_command("1", base, "cmd1"),
            _make_command("2", base + gap, "cmd2"),
        ]

        sessions = cluster_commands(commands)

        assert len(sessions) == 2
        assert sessions[0].command_count == 1
        assert sessions[1].command_count == 1

    def test_splits_on_directory_change(self):
        """Commands in different directories should be split."""
        commands = [
            _make_command("1", 1000, "cmd1", cwd="/home/dev/api"),
            _make_command("2", 2000, "cmd2", cwd="/home/dev/frontend"),
        ]

        sessions = cluster_commands(commands)

        assert len(sessions) == 2

    def test_splits_on_hostname_change(self):
        """Commands from different hostnames should be split."""
        commands = [
            _make_command("1", 1000, "cmd1", hostname="laptop"),
            _make_command("2", 2000, "cmd2", hostname="server"),
        ]

        sessions = cluster_commands(commands)

        assert len(sessions) == 2

    def test_same_session_within_threshold(self):
        """Commands within 15 min and same dir should stay together."""
        commands = [
            _make_command("1", 1000, "cmd1", cwd="/home/dev"),
            _make_command("2", 2000, "cmd2", cwd="/home/dev"),
        ]

        sessions = cluster_commands(commands)

        assert len(sessions) == 1
        assert sessions[0].command_count == 2


class TestEmptyInput:
    """Test edge cases."""

    def test_empty_commands_returns_empty(self):
        """Empty input should return empty output."""
        assert cluster_commands([]) == []

    def test_single_command(self):
        """Single command should produce one session."""
        commands = [_make_command("1", 1000)]
        sessions = cluster_commands(commands)

        assert len(sessions) == 1
        assert sessions[0].command_count == 1


class TestSessionProperties:
    """Test Session dataclass properties."""

    def test_primary_cwd(self):
        """Primary CWD should be the most frequently used directory."""
        session = Session(session_id="test")
        session.commands = [
            _make_command("1", 1000, cwd="/home/dev/api"),
            _make_command("2", 2000, cwd="/home/dev/api"),
            _make_command("3", 3000, cwd="/tmp"),
        ]

        assert session.primary_cwd == "/home/dev/api"

    def test_start_end_time(self):
        """Start/end time should reflect first/last commands."""
        session = Session(session_id="test")
        session.commands = [
            _make_command("1", 1000),
            _make_command("2", 5000),
        ]

        assert session.start_time == 1000
        assert session.end_time == 5000
