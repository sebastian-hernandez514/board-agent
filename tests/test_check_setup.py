"""Tests del script de arranque check_setup.py — mockea todo, nunca toca AWS/Redshift reales."""

import shutil
import subprocess

import check_setup
from board_agent.report import CheckResult


def _r(id_, status, desc="check"):
    return CheckResult(id_, desc, status)


def test_check_uv_pass_when_found(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/uv")
    r = check_setup._check_uv()
    assert r.status == "PASS"


def test_check_uv_fail_when_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    r = check_setup._check_uv()
    assert r.status == "FAIL"
    assert "instalar" in r.detail


def test_check_aws_cli_pass(monkeypatch):
    class _Proc:
        returncode = 0
        stdout = "aws-cli/2.15.0"
        stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc())
    r = check_setup._check_aws_cli()
    assert r.status == "PASS"


def test_check_aws_cli_fail_when_not_installed(monkeypatch):
    def _raise(*a, **k):
        raise FileNotFoundError()
    monkeypatch.setattr(subprocess, "run", _raise)
    r = check_setup._check_aws_cli()
    assert r.status == "FAIL"


def test_main_stops_early_if_tooling_missing(monkeypatch, capsys):
    monkeypatch.setattr(check_setup, "_check_uv", lambda: _r("S.1", "FAIL"))
    monkeypatch.setattr(check_setup, "_check_aws_cli", lambda: _r("S.2", "PASS"))
    called = {"gate": False}
    monkeypatch.setattr(check_setup.phase0_gate, "run", lambda month: called.update(gate=True) or [])
    monkeypatch.setattr("sys.argv", ["check_setup.py", "--month", "2026-06"])

    assert check_setup.main() == 1
    assert called["gate"] is False  # nunca llegó a revisar contenido/datos


def test_main_reports_fail_exit_code_when_source_blocks(monkeypatch):
    monkeypatch.setattr(check_setup, "_check_uv", lambda: _r("S.1", "PASS"))
    monkeypatch.setattr(check_setup, "_check_aws_cli", lambda: _r("S.2", "PASS"))
    monkeypatch.setattr(check_setup.phase0_gate, "run", lambda month: [_r("F0.4", "FAIL")])
    monkeypatch.setattr(check_setup.phase1_freshness, "run", lambda month: [_r("F1.1", "PASS")])
    monkeypatch.setattr("sys.argv", ["check_setup.py", "--month", "2026-06"])

    assert check_setup.main() == 1


def test_main_exit_0_when_everything_ready(monkeypatch):
    monkeypatch.setattr(check_setup, "_check_uv", lambda: _r("S.1", "PASS"))
    monkeypatch.setattr(check_setup, "_check_aws_cli", lambda: _r("S.2", "PASS"))
    monkeypatch.setattr(check_setup.phase0_gate, "run", lambda month: [_r("F0.4", "PASS")])
    monkeypatch.setattr(check_setup.phase1_freshness, "run", lambda month: [_r("F1.1", "PASS")])
    monkeypatch.setattr("sys.argv", ["check_setup.py", "--month", "2026-06"])

    assert check_setup.main() == 0


def test_main_exit_0_on_warn_only(monkeypatch):
    """WARN no debe bloquear el exit code — solo FAIL."""
    monkeypatch.setattr(check_setup, "_check_uv", lambda: _r("S.1", "PASS"))
    monkeypatch.setattr(check_setup, "_check_aws_cli", lambda: _r("S.2", "PASS"))
    monkeypatch.setattr(check_setup.phase0_gate, "run", lambda month: [_r("F0.6", "WARN")])
    monkeypatch.setattr(check_setup.phase1_freshness, "run", lambda month: [_r("F1.3", "WARN")])
    monkeypatch.setattr("sys.argv", ["check_setup.py", "--month", "2026-06"])

    assert check_setup.main() == 0
