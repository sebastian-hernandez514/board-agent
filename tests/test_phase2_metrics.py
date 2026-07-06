import subprocess

import pytest

from board_agent import phase2_metrics as f2


class _FakeProc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_success_first_try(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _FakeProc(0, stdout="metrics.yaml escrito")
    monkeypatch.setattr(subprocess, "run", fake_run)

    r = f2.run("2026-05")
    assert r.status == "PASS"
    assert len(calls) == 1
    assert "--month" in calls[0] and "2026-05" in calls[0]
    assert "--refresh" not in calls[0]


def test_run_passes_refresh_flag(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _FakeProc(0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    f2.run("2026-05", refresh=True)
    assert "--refresh" in calls[0]


def test_run_retries_on_too_many_connections_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    def fake_run(cmd, **kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return _FakeProc(1, stderr="FATAL: too many connections for role")
        return _FakeProc(0, stdout="ok")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(f2.time, "sleep", lambda s: None)

    r = f2.run("2026-05")
    assert r.status == "PASS"
    assert attempts["n"] == 3


def test_run_fails_after_exhausting_retries(monkeypatch):
    attempts = {"n": 0}

    def fake_run(cmd, **kwargs):
        attempts["n"] += 1
        return _FakeProc(1, stderr="too many connections")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(f2.time, "sleep", lambda s: None)

    r = f2.run("2026-05")
    assert r.status == "FAIL"
    assert attempts["n"] == 1 + len(f2._RETRY_BACKOFF_S)


def test_run_does_not_retry_non_connection_error(monkeypatch):
    attempts = {"n": 0}

    def fake_run(cmd, **kwargs):
        attempts["n"] += 1
        return _FakeProc(1, stderr="Traceback: KeyError 'app_version'")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(f2.time, "sleep", lambda s: None)

    r = f2.run("2026-05")
    assert r.status == "FAIL"
    assert attempts["n"] == 1
