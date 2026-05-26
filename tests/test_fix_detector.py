"""Tests for the fix detector module."""

from __future__ import annotations

import pytest

from replay.capture.atuin import Command
from replay.processing.cluster import Session
from replay.processing.fix_detector import Fix, detect_fixes, detect_fixes_all


def _cmd(id: str, command: str, exit_status: int = 0) -> Command:
    return Command(
        id=id,
        timestamp=1000,
        duration=0,
        exit_status=exit_status,
        command=command,
        cwd="/home/dev",
        hostname="laptop",
        session="s1",
    )


def _session(commands: list[Command], session_id: str = "s1") -> Session:
    return Session(session_id=session_id, commands=commands)


class TestDetectFixes:
    """Test fix detection within a single session."""

    def test_no_fixes_all_success(self):
        commands = [_cmd("1", "ls"), _cmd("2", "pwd")]
        session = _session(commands)
        assert detect_fixes(session) == []

    def test_no_fixes_all_failure(self):
        commands = [_cmd("1", "bad1", 1), _cmd("2", "bad2", 1)]
        session = _session(commands)
        assert detect_fixes(session) == []

    def test_single_fix(self):
        commands = [
            _cmd("1", "docker build .", 1),
            _cmd("2", "docker build -t app .", 0),
        ]
        session = _session(commands)
        fixes = detect_fixes(session)
        assert len(fixes) == 1
        assert fixes[0].failure_commands[0].command == "docker build ."
        assert fixes[0].fix_command.command == "docker build -t app ."
        assert fixes[0].session_id == "s1"

    def test_consecutive_failures_grouped(self):
        commands = [
            _cmd("1", "pytest", 1),
            _cmd("2", "pytest -x", 1),
            _cmd("3", "pytest --fix", 0),
        ]
        session = _session(commands)
        fixes = detect_fixes(session)
        assert len(fixes) == 1
        assert len(fixes[0].failure_commands) == 2
        assert fixes[0].failure_commands[0].command == "pytest"
        assert fixes[0].failure_commands[1].command == "pytest -x"
        assert fixes[0].fix_command.command == "pytest --fix"

    def test_multiple_fixes_in_session(self):
        commands = [
            _cmd("1", "cmd1", 1),
            _cmd("2", "cmd2", 0),
            _cmd("3", "cmd3", 1),
            _cmd("4", "cmd4", 0),
        ]
        session = _session(commands)
        fixes = detect_fixes(session)
        assert len(fixes) == 2
        assert fixes[0].fix_command.command == "cmd2"
        assert fixes[1].fix_command.command == "cmd4"

    def test_fix_requires_failure_first(self):
        """Success followed by success is NOT a fix."""
        commands = [
            _cmd("1", "ls", 0),
            _cmd("2", "pwd", 0),
        ]
        session = _session(commands)
        assert detect_fixes(session) == []

    def test_empty_session(self):
        session = _session([])
        assert detect_fixes(session) == []

    def test_single_failure_no_fix(self):
        commands = [_cmd("1", "bad", 1)]
        session = _session(commands)
        assert detect_fixes(session) == []

    def test_single_success_no_failure(self):
        commands = [_cmd("1", "good", 0)]
        session = _session(commands)
        assert detect_fixes(session) == []

    def test_fix_description(self):
        commands = [
            _cmd("1", "npm run build", 1),
            _cmd("2", "npm run build:prod", 0),
        ]
        session = _session(commands)
        fixes = detect_fixes(session)
        desc = fixes[0].description
        assert "npm run build" in desc
        assert "npm run build:prod" in desc
        assert "failed" in desc.lower() or "succeeded" in desc.lower()

    def test_fix_description_no_failures_edge_case(self):
        """Edge case: Fix with empty failure_commands."""
        fix = Fix(session_id="s1", failure_commands=[], fix_command=_cmd("1", "ok", 0))
        assert "Fix" in fix.description


class TestDetectFixesAll:
    """Test fix detection across multiple sessions."""

    def test_empty_sessions(self):
        assert detect_fixes_all([]) == []

    def test_fixes_across_sessions(self):
        s1 = _session([_cmd("1", "fail1", 1), _cmd("2", "fix1", 0)], "s1")
        s2 = _session([_cmd("3", "fail2", 1), _cmd("4", "fix2", 0)], "s2")
        fixes = detect_fixes_all([s1, s2])
        assert len(fixes) == 2
        assert fixes[0].session_id == "s1"
        assert fixes[1].session_id == "s2"

    def test_mixed_sessions(self):
        s1 = _session([_cmd("1", "fail", 1), _cmd("2", "fix", 0)], "s1")
        s2 = _session([_cmd("3", "ok", 0)], "s2")  # no fix
        fixes = detect_fixes_all([s1, s2])
        assert len(fixes) == 1

    def test_preserves_order(self):
        s1 = _session([_cmd("1", "a", 1), _cmd("2", "b", 0)], "s1")
        s2 = _session([_cmd("3", "c", 1), _cmd("4", "d", 0)], "s2")
        fixes = detect_fixes_all([s1, s2])
        assert fixes[0].fix_command.command == "b"
        assert fixes[1].fix_command.command == "d"
