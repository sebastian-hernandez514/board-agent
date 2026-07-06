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


def _raw_buckets_matching_net_expansion(net_expansion=300_000, cross_down=200_000):
    """12 buckets crudos consistentes con un Net Expansion dado (upsell+down+pricing+
    cross_new+cross_readop-cross_down = net_expansion) — el resto de valores no importan
    para R5, se rellenan con placeholders. 300_000 = el Net Expansion real (último valor,
    '0.3') de la sección GLO del fixture (tests/fixtures/metrics_sample.yaml)."""
    upsell, down, pricing, cross_new, cross_readop = 300_000, -50_000, 20_000, 10_000, 5_000
    # ajusta 'down' para que la suma dé exacto el net_expansion pedido
    down = net_expansion - (upsell + pricing + cross_new + cross_readop - cross_down)
    return {
        "a_new_base_t0": 700_000, "a_new_cross_t0": 70_000, "a_recov": 190_000, "a_react": 470_000,
        "a_churn": 1_400_000, "a_upsell": upsell, "a_down": down, "a_pricing": pricing,
        "a_cross_new": cross_new, "a_cross_readop": cross_readop, "a_cross_down": cross_down,
        "a_fx": -450_000,
    }


def test_r5_passes_when_raw_buckets_reconcile_with_net_expansion(tmp_path):
    metrics = _load_fixture()
    metrics["arr_walk_raw_buckets"] = _raw_buckets_matching_net_expansion()
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R5"].status == "PASS"


def test_r5_fails_when_cross_down_is_added_instead_of_subtracted(tmp_path):
    """Reproduce la 'trampa de signos' documentada en CLAUDE.md de Template Board: si
    cross_down se sumara en vez de restarse, el recomputado se aleja del Net Expansion
    mostrado por 2×cross_down — con cross_down=200_000 eso son $400K de diferencia,
    muy por encima de TOL_ARR_WALK ($150K)."""
    metrics = _load_fixture()
    buckets = _raw_buckets_matching_net_expansion(net_expansion=300_000, cross_down=200_000)
    buckets["a_cross_down"] = -200_000  # bug hipotético: quedó con el signo volteado en el SQL
    metrics["arr_walk_raw_buckets"] = buckets
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R5"].status == "FAIL"


def test_r5_skip_when_raw_buckets_missing(tmp_path):
    """El fixture real (extracto de v37) no tiene arr_walk_raw_buckets — campo agregado
    2026-07-06, boards anteriores a esa fecha no lo tienen."""
    metrics = _load_fixture()
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R5"].status == "SKIP"


# ── R13/R14/R15 — reglas de color (parsean el HTML renderizado, no metrics.yaml) ──────────

def _delta_td(css_class, text):
    return f'<td class="delta {css_class} right">{text}</td>'


def _butterfly_row(metric_name, core_yoy, core_mom, lite_mom, lite_yoy, primary=False):
    name_class = "metric-name primary" if primary else "metric-name"
    return (
        f"<tr>{_delta_td(*core_yoy)}{_delta_td(*core_mom)}"
        f'<td class="val right">100</td>'
        f'<td class="metric-col"><span class="status-dot sd-green"></span>'
        f'<span class="{name_class}">{metric_name}</span></td>'
        f'<td class="val left">100</td>'
        f"{_delta_td(*lite_mom)}{_delta_td(*lite_yoy)}</tr>"
    )


def _write_html(tmp_path, rows_html):
    p = tmp_path / "board_standalone.html"
    p.write_text("<html><body><table><tbody>" + "".join(rows_html) + "</tbody></table></body></html>",
                  encoding="utf-8")
    return p


def _run_with_html(tmp_path, html_path):
    return phase4_validator.run(metrics_path=FIXTURE, html_path=html_path)


def test_r13_pass_when_investment_is_always_neutral(tmp_path):
    rows = [_butterfly_row("Investment", ("neutral", "-14.0%"), ("neutral", "+2.6%"),
                            ("neutral", "+1.3%"), ("neutral", "-19.6%"))]
    html_path = _write_html(tmp_path, rows)
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R13"]
    assert r.status == "PASS"
    assert "4 celdas" in r.detail


def test_r13_fails_when_investment_delta_is_colored(tmp_path):
    """Reproduce el bug hipotético que motivó la regla: Investment con verde/rojo en vez de
    neutro (ej. si alguien quita el 'neutral_delta' del template sin querer)."""
    rows = [_butterfly_row("Investment", ("pos", "-14.0%"), ("neutral", "+2.6%"),
                            ("neutral", "+1.3%"), ("neutral", "-19.6%"))]
    html_path = _write_html(tmp_path, rows)
    results = _run_with_html(tmp_path, html_path)
    assert _results_by_id(results)["R13"].status == "FAIL"


def test_r14_pass_when_churn_and_cac_are_inverted(tmp_path):
    rows = [
        _butterfly_row("CAC", ("neg", "+2.6%"), ("neg", "+20.6%"), ("pos", "-7.5%"), ("pos", "-46.5%")),
        _butterfly_row("Churn Rate", ("pos", "-6.7%"), ("pos", "-5.1%"), ("neg", "+5.1%"), ("neg", "+12.2%"), primary=True),
    ]
    html_path = _write_html(tmp_path, rows)
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R14"]
    assert r.status == "PASS"
    assert "8 celdas" in r.detail


def test_r14_fails_when_cac_uses_standard_sign_instead_of_inverted(tmp_path):
    """CAC bajando (bueno) pintado en rojo por error — debería ser verde (invertido)."""
    rows = [_butterfly_row("CAC", ("neg", "-7.5%"), ("neg", "+20.6%"), ("pos", "-7.5%"), ("pos", "-46.5%"))]
    html_path = _write_html(tmp_path, rows)
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R14"]
    assert r.status == "FAIL"
    assert "CAC" in r.detail


def test_r15_pass_when_standard_metrics_use_normal_sign(tmp_path):
    rows = [_butterfly_row("New Logos", ("pos", "+10.0%"), ("neg", "-5.0%"),
                            ("pos", "+3.0%"), ("neg", "-1.0%"))]
    html_path = _write_html(tmp_path, rows)
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R15"]
    assert r.status == "PASS"


def test_r15_fails_when_positive_value_is_colored_red(tmp_path):
    rows = [_butterfly_row("New Logos", ("neg", "+10.0%"), ("neg", "-5.0%"),
                            ("pos", "+3.0%"), ("neg", "-1.0%"))]
    html_path = _write_html(tmp_path, rows)
    results = _run_with_html(tmp_path, html_path)
    assert _results_by_id(results)["R15"].status == "FAIL"


def test_r15_ignores_zero_percent_deltas(tmp_path):
    """0% no tiene un color 'correcto' obvio (ni pos ni neg son objetivamente un error) —
    no debe contarse como violación en ningún sentido."""
    rows = [_butterfly_row("New Logos", ("pos", "0%"), ("neg", "0.0%"),
                            ("pos", "+3.0%"), ("neg", "-1.0%"))]
    html_path = _write_html(tmp_path, rows)
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R15"]
    assert r.status == "PASS"
    assert "2 celdas" in r.detail  # las 2 celdas en 0% no se cuentan


def test_r13_14_15_skip_when_html_missing(tmp_path):
    results = phase4_validator.run(metrics_path=FIXTURE, html_path=MISSING_HTML)
    by_id = _results_by_id(results)
    for rid in ("R13", "R14", "R15"):
        assert by_id[rid].status == "SKIP"


def test_r13_14_15_skip_when_no_matching_rows_found(tmp_path):
    """HTML válido pero sin ninguna fila 'butterfly' — no debe fallar, debe marcar SKIP para
    cada regla que no encontró filas que verificar (no confundir 'sin datos' con 'PASS')."""
    html_path = _write_html(tmp_path, ["<tr><td>contenido sin metric-name</td></tr>"])
    results = _run_with_html(tmp_path, html_path)
    by_id = _results_by_id(results)
    for rid in ("R13", "R14", "R15"):
        assert by_id[rid].status == "SKIP"
