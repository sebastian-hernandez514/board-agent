"""Tests del orquestador CLI (run.py) — hasta 2026-07-06 no tenía ninguna cobertura.

Cada fase se mockea devolviendo CheckResult controlados; lo que se prueba es el
ENCADENADO (qué fase llama a cuál, dónde corta en FAIL, qué exit code devuelve),
no la lógica interna de cada fase (eso ya lo cubre su propio test_phaseN_*.py).
"""

from pathlib import Path

import run
from board_agent.report import CheckResult


def _r(id_, status, desc="check"):
    return CheckResult(id_, desc, status)


def _fake_versioning(monkeypatch, calls):
    def fake_save_version(month, validator_results, diff_results):
        calls.append((month, validator_results, diff_results))
        return {
            "version": 1,
            "html": Path("/tmp/board_x_v1.html"),
            "metrics": Path("/tmp/board_x_v1.metrics.yaml"),
            "report": Path("/tmp/board_x_v1.report.md"),
            "pdf_target": Path("/tmp/board_x_v1.pdf"),
        }
    monkeypatch.setattr(run.versioning, "save_version", fake_save_version)


def test_default_month_is_current_month_yyyy_mm():
    from datetime import date
    today = date.today()
    assert run._default_month() == f"{today.year:04d}-{today.month:02d}"


def test_pdf_flag_calls_phase6_with_confirmed_flag(monkeypatch):
    captured = {}

    def fake_run(confirmed=False):
        captured["confirmed"] = confirmed
        return _r("F6.1", "PASS")
    monkeypatch.setattr(run.phase6_pdf, "run", fake_run)
    monkeypatch.setattr("sys.argv", ["run.py", "--pdf", "--yes"])

    assert run.main() == 0
    assert captured["confirmed"] is True


def test_pdf_flag_without_yes_still_exits_0_on_skip(monkeypatch):
    monkeypatch.setattr(run.phase6_pdf, "run", lambda confirmed=False: _r("F6.1", "SKIP"))
    monkeypatch.setattr("sys.argv", ["run.py", "--pdf"])
    assert run.main() == 0


def test_diff_only_flag_runs_phase5_and_reflects_fail_in_exit_code(monkeypatch):
    monkeypatch.setattr(run.phase5_diff, "run", lambda: [_r("D1", "FAIL")])
    monkeypatch.setattr("sys.argv", ["run.py", "--diff-only", "--month", "2026-05"])
    assert run.main() == 1


def test_validate_only_flag_runs_phase4_without_month_argument(monkeypatch):
    """Documenta el comportamiento real (encontrado en revisión de código 2026-07-06):
    --validate-only ignora --month por completo — solo re-valida lo que ya esté en
    metrics.yaml/board_standalone.html, sin verificar que corresponda al mes pedido."""
    captured = {"called_with_args": None}

    def fake_run(*args, **kwargs):
        captured["called_with_args"] = (args, kwargs)
        return [_r("R1", "PASS")]
    monkeypatch.setattr(run.phase4_validator, "run", fake_run)
    monkeypatch.setattr("sys.argv", ["run.py", "--validate-only", "--month", "2026-04"])

    assert run.main() == 0
    assert captured["called_with_args"] == ((), {})  # no se le pasó "2026-04" en absoluto


def test_validate_only_reflects_fail_in_exit_code(monkeypatch):
    monkeypatch.setattr(run.phase4_validator, "run", lambda: [_r("R1", "FAIL")])
    monkeypatch.setattr("sys.argv", ["run.py", "--validate-only"])
    assert run.main() == 1


def test_full_flow_happy_path_saves_version_and_exits_0(monkeypatch):
    monkeypatch.setattr(run.phase0_gate, "run", lambda month: [_r("F0.4", "PASS")])
    monkeypatch.setattr(run.phase1_freshness, "run", lambda month: [_r("F1.1", "PASS")])
    monkeypatch.setattr(run.phase2_metrics, "run", lambda month, refresh=False: _r("F2.1", "PASS"))
    monkeypatch.setattr(run.phase3_html_builder, "run", lambda month: [_r("F3.1", "PASS")])
    monkeypatch.setattr(run.phase4_validator, "run", lambda: [_r("R1", "PASS")])
    monkeypatch.setattr(run.phase5_diff, "run", lambda: [_r("D1", "PASS")])
    calls = []
    _fake_versioning(monkeypatch, calls)
    monkeypatch.setattr("sys.argv", ["run.py", "--month", "2026-05"])

    assert run.main() == 0
    assert len(calls) == 1
    assert calls[0][0] == "2026-05"


def test_full_flow_stops_before_metrics_if_gate_fails(monkeypatch):
    monkeypatch.setattr(run.phase0_gate, "run", lambda month: [_r("F0.4", "FAIL")])
    monkeypatch.setattr(run.phase1_freshness, "run", lambda month: [_r("F1.1", "PASS")])
    called = {"metrics": False}
    monkeypatch.setattr(run.phase2_metrics, "run", lambda month, refresh=False: called.update(metrics=True) or _r("F2.1", "PASS"))
    monkeypatch.setattr("sys.argv", ["run.py", "--month", "2026-05"])

    assert run.main() == 1
    assert called["metrics"] is False


def test_full_flow_stops_before_html_if_metrics_fails(monkeypatch):
    monkeypatch.setattr(run.phase0_gate, "run", lambda month: [_r("F0.4", "PASS")])
    monkeypatch.setattr(run.phase1_freshness, "run", lambda month: [_r("F1.1", "PASS")])
    monkeypatch.setattr(run.phase2_metrics, "run", lambda month, refresh=False: _r("F2.1", "FAIL"))
    called = {"html": False}
    monkeypatch.setattr(run.phase3_html_builder, "run", lambda month: called.update(html=True) or [_r("F3.1", "PASS")])
    monkeypatch.setattr("sys.argv", ["run.py", "--month", "2026-05"])

    assert run.main() == 1
    assert called["html"] is False


def test_full_flow_stops_before_validator_if_html_builder_fails(monkeypatch):
    monkeypatch.setattr(run.phase0_gate, "run", lambda month: [_r("F0.4", "PASS")])
    monkeypatch.setattr(run.phase1_freshness, "run", lambda month: [_r("F1.1", "PASS")])
    monkeypatch.setattr(run.phase2_metrics, "run", lambda month, refresh=False: _r("F2.1", "PASS"))
    monkeypatch.setattr(run.phase3_html_builder, "run", lambda month: [_r("F3.1", "FAIL")])
    called = {"validator": False}
    monkeypatch.setattr(run.phase4_validator, "run", lambda: called.update(validator=True) or [_r("R1", "PASS")])
    monkeypatch.setattr("sys.argv", ["run.py", "--month", "2026-05"])

    assert run.main() == 1
    assert called["validator"] is False


def test_full_flow_validator_fail_still_saves_version(monkeypatch):
    """Decisión de diseño documentada en versioning.py: se versiona pase o no pase el
    Validator — un board fallido sigue siendo un checkpoint útil."""
    monkeypatch.setattr(run.phase0_gate, "run", lambda month: [_r("F0.4", "PASS")])
    monkeypatch.setattr(run.phase1_freshness, "run", lambda month: [_r("F1.1", "PASS")])
    monkeypatch.setattr(run.phase2_metrics, "run", lambda month, refresh=False: _r("F2.1", "PASS"))
    monkeypatch.setattr(run.phase3_html_builder, "run", lambda month: [_r("F3.1", "PASS")])
    monkeypatch.setattr(run.phase4_validator, "run", lambda: [_r("R1", "FAIL")])
    monkeypatch.setattr(run.phase5_diff, "run", lambda: [_r("D1", "PASS")])
    calls = []
    _fake_versioning(monkeypatch, calls)
    monkeypatch.setattr("sys.argv", ["run.py", "--month", "2026-05"])

    assert run.main() == 1
    assert len(calls) == 1  # se guardó igual


def test_full_flow_passes_refresh_flag_to_phase2(monkeypatch):
    captured = {}
    monkeypatch.setattr(run.phase0_gate, "run", lambda month: [_r("F0.4", "PASS")])
    monkeypatch.setattr(run.phase1_freshness, "run", lambda month: [_r("F1.1", "PASS")])

    def fake_metrics(month, refresh=False):
        captured["refresh"] = refresh
        return _r("F2.1", "PASS")
    monkeypatch.setattr(run.phase2_metrics, "run", fake_metrics)
    monkeypatch.setattr(run.phase3_html_builder, "run", lambda month: [_r("F3.1", "FAIL")])
    monkeypatch.setattr("sys.argv", ["run.py", "--month", "2026-05", "--refresh"])

    run.main()
    assert captured["refresh"] is True
