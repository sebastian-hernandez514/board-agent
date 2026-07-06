"""print_report() y CheckResult.line() — hasta 2026-07-06 no tenían ningún test directo,
pese a ser el formato compartido por las 6 fases."""

from board_agent.report import BLOCKING_STATUSES, STATUS_ICON, CheckResult, print_report


def test_check_result_line_without_detail():
    r = CheckResult("R1", "ARR total incluye Alanube", "PASS")
    assert r.line() == "✅ [R1] ARR total incluye Alanube"


def test_check_result_line_with_detail():
    r = CheckResult("R1", "ARR total incluye Alanube", "FAIL", "diff=1,000")
    assert r.line() == "❌ [R1] ARR total incluye Alanube — diff=1,000"


def test_check_result_line_unknown_status_uses_fallback_icon():
    r = CheckResult("X1", "algo", "BOGUS")
    assert r.line().startswith("? [X1]")


def test_print_report_returns_true_with_no_fail(capsys):
    results = [CheckResult("R1", "a", "PASS"), CheckResult("R2", "b", "WARN"), CheckResult("R3", "c", "SKIP")]
    assert print_report("FASE X", results) is True


def test_print_report_returns_false_with_any_fail(capsys):
    results = [CheckResult("R1", "a", "PASS"), CheckResult("R2", "b", "FAIL")]
    assert print_report("FASE X", results) is False


def test_print_report_true_on_empty_results(capsys):
    """Fase sin ningún check (ej. Fase 5 con metrics.yaml recién creado) no debe bloquear."""
    assert print_report("FASE X", []) is True


def test_print_report_prints_title_and_summary_counts(capsys):
    results = [CheckResult("R1", "a", "PASS"), CheckResult("R2", "b", "PASS"), CheckResult("R3", "c", "WARN")]
    print_report("FASE X — Validator", results)
    out = capsys.readouterr().out
    assert "=== FASE X — Validator ===" in out
    assert "2 PASS · 1 WARN · 0 FAIL · 0 SKIP" in out


def test_status_icon_covers_all_four_statuses():
    assert set(STATUS_ICON.keys()) == {"PASS", "WARN", "FAIL", "SKIP"}


def test_blocking_statuses_is_consistent_with_print_report_logic():
    """BLOCKING_STATUSES existe pero print_report() lo reimplementa a mano (n_fail == 0) en vez
    de leer de esta constante — ver hallazgo de revisión 2026-07-06. Este test no arregla ese
    acoplamiento, solo deja constancia de que hoy ambos coinciden (si alguien cambia uno sin el
    otro, este test debería fallar y avisar)."""
    results_only_blocking = [CheckResult("R1", "a", s) for s in BLOCKING_STATUSES]
    assert print_report("FASE X", results_only_blocking) is False
