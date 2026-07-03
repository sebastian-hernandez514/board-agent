import copy
from pathlib import Path

import yaml

from board_agent import phase4_validator

FIXTURE = Path(__file__).parent / "fixtures" / "metrics_sample.yaml"
MISSING_HTML = Path("/nonexistent/board_standalone.html")


def _load_fixture() -> dict:
    with open(FIXTURE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _results_by_id(results):
    return {r.id: r for r in results}


def _write_and_run(tmp_path, metrics: dict):
    p = tmp_path / "metrics.yaml"
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(metrics, f, allow_unicode=True)
    return phase4_validator.run(metrics_path=p, html_path=MISSING_HTML)


def test_smoke_against_real_may_2026_data():
    """Corre el validator contra el extracto real del board v37 ya publicado.

    Confirma el hallazgo de la sesión: R8 (ARR EoP CC = ARR EoP en el mes de
    corte) FALLA en el board de mayo-26 ya publicado — esa es precisamente la
    inconsistencia real de ~$1.7M documentada en el plan de esta sesión.
    """
    results = phase4_validator.run(metrics_path=FIXTURE, html_path=MISSING_HTML)
    by_id = _results_by_id(results)

    assert by_id["R1"].status == "PASS"  # ARR total ya incluye Alanube
    assert by_id["R2"].status == "PASS"  # New MRR core+lite = total
    assert by_id["R3"].status == "PASS"  # ARR walk balancea (dentro de tolerancia de redondeo)
    assert by_id["R4"].status == "PASS"  # Net Churn negativo
    assert by_id["R6"].status == "PASS"  # FX residual < $3M
    assert by_id["R8"].status == "FAIL"  # <-- hallazgo real: CC=$26.5M vs EoP=$28.2M
    assert by_id["R9"].status == "PASS"  # mayo no es cierre de quarter
    assert by_id["R10"].status == "PASS"  # churn 4.1% dentro de 0-20%
    assert by_id["R12"].status == "SKIP"  # sin HTML disponible en el test

    for rid in ("R5", "R7", "R11", "R13", "R14", "R15"):
        assert by_id[rid].status == "SKIP"


def test_r1_fails_when_arr_total_excludes_alanube(tmp_path):
    """Reproduce el bug real de v36: arr_total sin sumar Alanube."""
    metrics = _load_fixture()
    metrics["arr_total"] = "$28.2M"  # solo Alegra, sin los ~$1.0M de Alanube
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R1"].status == "FAIL"


def test_r2_fails_when_new_mrr_not_divided_by_12(tmp_path):
    """Reproduce el bug real de v37: total en ARR anualizado en vez de MRR mensual."""
    metrics = _load_fixture()
    metrics["new_mrr"] = "$852K"  # $71K * 12 — el bug real (faltaba /12)
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R2"].status == "FAIL"


def test_r4_fails_when_net_churn_sign_is_flipped(tmp_path):
    metrics = _load_fixture()
    for row in metrics["arr_walk_table"]["sections"][1]["rows"]:
        if row["label"] == "Net Churn":
            row["cells"][-1] = "0.9"  # positivo en vez de "(0.9)"
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R4"].status == "FAIL"


def test_r9_fails_when_quarter_end_flag_is_wrong(tmp_path):
    metrics = _load_fixture()
    metrics["is_quarter_end"] = True  # mayo no es cierre de quarter
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R9"].status == "FAIL"


def test_r10_fails_on_implausible_churn(tmp_path):
    metrics = _load_fixture()
    metrics["logo_churn_global"] = 35.0  # doble conteo sospechoso
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R10"].status == "FAIL"
