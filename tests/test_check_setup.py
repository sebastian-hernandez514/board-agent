"""Tests del script de arranque check_setup.py — mockea todo, nunca toca Metabase real."""

import shutil

import check_setup
from board_agent import paths
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


def test_check_metabase_cache_pass_when_present(tmp_path, monkeypatch):
    cache_file = tmp_path / ".metabase_cache.json"
    cache_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paths, "METABASE_CACHE_FILE", cache_file)
    r = check_setup._check_metabase_cache_exists()
    assert r.status == "PASS"


def test_check_metabase_cache_fail_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "METABASE_CACHE_FILE", tmp_path / "no-existe.json")
    r = check_setup._check_metabase_cache_exists()
    assert r.status == "FAIL"
    assert "metabase_fetch_spec" in r.detail


def test_main_stops_early_if_tooling_missing(monkeypatch):
    monkeypatch.setattr(check_setup, "_check_uv", lambda: _r("S.1", "FAIL"))
    monkeypatch.setattr(check_setup, "_check_metabase_cache_exists", lambda: _r("S.2", "PASS"))
    called = {"gate": False}
    monkeypatch.setattr(check_setup.phase0_gate, "run", lambda month: called.update(gate=True) or [])
    monkeypatch.setattr("sys.argv", ["check_setup.py", "--month", "2026-06"])

    assert check_setup.main() == 1
    assert called["gate"] is False  # nunca llegó a revisar contenido/datos


def test_main_reports_fail_exit_code_when_source_blocks(monkeypatch):
    monkeypatch.setattr(check_setup, "_check_uv", lambda: _r("S.1", "PASS"))
    monkeypatch.setattr(check_setup, "_check_metabase_cache_exists", lambda: _r("S.2", "PASS"))
    monkeypatch.setattr(check_setup.phase0_gate, "run", lambda month: [_r("F0.4", "FAIL")])
    monkeypatch.setattr(check_setup.phase1_freshness, "run", lambda month: [_r("F1.1", "PASS")])
    monkeypatch.setattr("sys.argv", ["check_setup.py", "--month", "2026-06"])

    assert check_setup.main() == 1


def test_main_exit_0_when_everything_ready(monkeypatch):
    monkeypatch.setattr(check_setup, "_check_uv", lambda: _r("S.1", "PASS"))
    monkeypatch.setattr(check_setup, "_check_metabase_cache_exists", lambda: _r("S.2", "PASS"))
    monkeypatch.setattr(check_setup.phase0_gate, "run", lambda month: [_r("F0.4", "PASS")])
    monkeypatch.setattr(check_setup.phase1_freshness, "run", lambda month: [_r("F1.1", "PASS")])
    monkeypatch.setattr("sys.argv", ["check_setup.py", "--month", "2026-06"])

    assert check_setup.main() == 0


def test_main_exit_0_on_warn_only(monkeypatch):
    """WARN no debe bloquear el exit code — solo FAIL."""
    monkeypatch.setattr(check_setup, "_check_uv", lambda: _r("S.1", "PASS"))
    monkeypatch.setattr(check_setup, "_check_metabase_cache_exists", lambda: _r("S.2", "PASS"))
    monkeypatch.setattr(check_setup.phase0_gate, "run", lambda month: [_r("F0.6", "WARN")])
    monkeypatch.setattr(check_setup.phase1_freshness, "run", lambda month: [_r("F1.3", "WARN")])
    monkeypatch.setattr("sys.argv", ["check_setup.py", "--month", "2026-06"])

    assert check_setup.main() == 0
