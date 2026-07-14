import copy
import csv
import sys
import types
from pathlib import Path

import pytest
import yaml

from board_agent import paths, phase4_validator

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
    # El fixture está recortado a los campos que R1-R12 necesitaban cuando se armó (2026-06-18,
    # antes de que existiera R17) — nunca incluyó net_revenue/gross_margin/ebitda_margin, así
    # que R17 da FAIL acá por un hueco del fixture, no porque el board real de mayo no tuviera P&L.
    assert by_id["R17"].status == "FAIL"

    for rid in ("R5", "R7", "R11", "R13", "R14", "R15", "R18", "R19"):
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


def test_r5_skip_not_fail_on_quarter_end_due_to_known_override(tmp_path):
    """Hallazgo real 2026-07-08 generando junio (primer cierre de Q real probado):
    fetch_metrics.py tiene un override temporal documentado ("valores del SS Apr-2026") que
    sobreescribe arr_walk_table con números fijos de abril en CUALQUIER cierre de Q — hace que
    el recomputado (real) y el mostrado (hardcodeado) diverjan siempre, sin ser un bug real.
    Debe dar SKIP explicando la causa, no FAIL (que sugeriría un bug de esta regla/Board Agent)."""
    metrics = _load_fixture()
    metrics["is_quarter_end"] = True
    buckets = _raw_buckets_matching_net_expansion(net_expansion=300_000, cross_down=200_000)
    buckets["a_cross_down"] = -200_000  # misma divergencia que el test de FAIL, pero en cierre de Q
    metrics["arr_walk_raw_buckets"] = buckets
    results = _write_and_run(tmp_path, metrics)
    r = _results_by_id(results)["R5"]
    assert r.status == "SKIP"
    assert "override" in r.detail.lower()


# ── R3, R6 — aisladas del smoke test (que solo verifica el caso PASS/FAIL del fixture real) ──

def _set_glo_row(metrics, label, value):
    """Reemplaza la última celda de una fila de la sección ARR Walk GLO (identificada por
    tener 'ARR BoP' y 'Net New ARR', igual que _arr_walk_glo_rows en producción)."""
    for section in metrics["arr_walk_table"]["sections"]:
        labels = {r["label"] for r in section["rows"]}
        if "ARR BoP" in labels and "Net New ARR" in labels:
            for row in section["rows"]:
                if row["label"] == label:
                    row["cells"][-1] = value
                    return
    raise KeyError(label)


def test_r3_fails_when_buckets_dont_sum_to_net_new_arr(tmp_path):
    """Reproduce el caso que R3 existe para atrapar: alguien rompe la aritmética del ARR
    Walk (ej. un bucket con signo volteado en fetch_metrics.py) y Net New ARR deja de
    cuadrar con la suma de los 5 buckets."""
    metrics = _load_fixture()
    _set_glo_row(metrics, "Net New ARR", "5.0")  # el real de mayo-26 es "(0.1)" — ver fixture
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R3"].status == "FAIL"


def test_r6_fails_when_fx_impact_exceeds_3m(tmp_path):
    """FX residual grande es señal de error de lógica FX, no una variación normal del mes."""
    metrics = _load_fixture()
    _set_glo_row(metrics, "(+/−) FX Impact", "5.0")  # $5M > límite de $3M
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R6"].status == "FAIL"


def test_r6_passes_when_fx_impact_is_within_limit(tmp_path):
    metrics = _load_fixture()
    _set_glo_row(metrics, "(+/−) FX Impact", "1.0")  # $1M, dentro del límite de $3M
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R6"].status == "PASS"


# ── R7 — dedup de logos vía query MBQL independiente (leída del cache de Metabase) ───────────

@pytest.fixture
def fake_metabase_cache(tmp_path, monkeypatch):
    """Migración 2026-07-10: _check_r7_logos_dedup ya no corre nada en vivo — lee
    cache["validator"]["R7"]["logos_eop"] de METABASE_CACHE_FILE (poblado por Claude Code
    vía el MCP de Metabase antes de correr el pipeline)."""
    import json
    cache_file = tmp_path / ".metabase_cache.json"
    monkeypatch.setattr(paths, "METABASE_CACHE_FILE", cache_file)

    def _write(logos_eop=58974, month="2026-05"):
        cache_file.write_text(json.dumps({"month": month, "validator": {"R7": {"logos_eop": logos_eop}}}),
                               encoding="utf-8")
    return _write


def test_r7_passes_when_independent_query_matches_reported(tmp_path, fake_metabase_cache):
    fake_metabase_cache(logos_eop=58974)
    metrics = _load_fixture()
    metrics["smb_logos_eop"] = 58974  # coincide con el cache de arriba
    results = _write_and_run(tmp_path, metrics)
    r = _results_by_id(results)["R7"]
    assert r.status == "PASS"
    assert "58,974" in r.detail


def test_r7_fails_when_independent_query_diverges(tmp_path, fake_metabase_cache):
    """Reproduce el caso real validado 2026-07-03 (match exacto 58,974) pero forzando un
    divergencia — ej. metrics.yaml quedó con un valor viejo de una corrida anterior."""
    fake_metabase_cache(logos_eop=58974)
    metrics = _load_fixture()
    metrics["smb_logos_eop"] = 59000  # diverge del cache (58974)
    results = _write_and_run(tmp_path, metrics)
    r = _results_by_id(results)["R7"]
    assert r.status == "FAIL"
    assert "diff=" in r.detail


def test_r7_skip_when_smb_logos_eop_field_missing(tmp_path, fake_metabase_cache):
    """El fixture real no tiene smb_logos_eop, así que ni siquiera llega a leer el cache —
    cae directo a SKIP por KeyError."""
    fake_metabase_cache(logos_eop=58974)
    metrics = _load_fixture()
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R7"].status == "SKIP"


def test_r7_skip_when_cache_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "METABASE_CACHE_FILE", tmp_path / "no-existe.json")
    metrics = _load_fixture()
    metrics["smb_logos_eop"] = 58974
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R7"].status == "SKIP"


def test_r7_fails_when_cache_is_stale_month(tmp_path, fake_metabase_cache):
    """Bug corregido 2026-07-14: el cache SÍ existe (no es un 'no aplica'), pero es de otro
    mes — antes esto caía en el except genérico y daba SKIP; ahora es FAIL, porque es un
    error real (alguien no refrescó el cache), no una condición de 'no corrió el check'."""
    fake_metabase_cache(logos_eop=58974, month="2026-04")  # cache viejo, cutoff real es 2026-05
    metrics = _load_fixture()
    metrics["smb_logos_eop"] = 58974
    results = _write_and_run(tmp_path, metrics)
    r = _results_by_id(results)["R7"]
    assert r.status == "FAIL"
    assert "2026-04" in r.detail and "2026-05" in r.detail


def test_r7_fails_when_validator_block_missing_from_cache(tmp_path, monkeypatch):
    """Bug corregido 2026-07-14: cache existe y es del mes correcto, pero nadie corrió la
    query independiente y pobló cache['validator']['R7'] — antes esto también caía en SKIP
    (KeyError silencioso); ahora es FAIL, porque el freno de seguridad no se puede saltar."""
    import json
    cache_file = tmp_path / ".metabase_cache.json"
    cache_file.write_text(json.dumps({"month": "2026-05", "queries": {}}), encoding="utf-8")
    monkeypatch.setattr(paths, "METABASE_CACHE_FILE", cache_file)
    metrics = _load_fixture()
    metrics["smb_logos_eop"] = 58974
    results = _write_and_run(tmp_path, metrics)
    r = _results_by_id(results)["R7"]
    assert r.status == "FAIL"
    assert "validator" in r.detail


# ── R11 — completitud del budget CSV en cierre de quarter ────────────────────────────────

def _write_budget_csv(tmp_path, rows):
    """rows: [{"Metric":..., "Fecha":..., "value":...}]. El valor SIEMPRE se escribe en la
    primera columna de datos ("Apr - 26"), sin importar de qué mes sea la fila — reproduce la
    estructura real de Metricas_budget.csv (confirmado leyendo merge_budget() en
    fetch_metrics.py: lee de ahí, no de la columna con el nombre del mes de la fila). Bug real
    encontrado 2026-07-08: la versión anterior de este helper (y de R11) asumía que el valor
    vivía en la columna con el mismo nombre que 'Fecha' — falso, causaba que R11 reportara
    "faltan" 3 meses que en realidad estaban completos en el CSV real de junio-26."""
    p = tmp_path / "Metricas_budget.csv"
    header = ["Metric", "Fecha", "Apr - 26", "May - 26", "Jun - 26"]
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({"Metric": r["Metric"], "Fecha": r["Fecha"], "Apr - 26": r.get("value", "")})
    return p


def test_r11_skip_when_not_quarter_end(tmp_path):
    metrics = _load_fixture()  # is_quarter_end: false, mayo no es cierre de Q
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R11"].status == "SKIP"


def test_r11_passes_when_all_three_quarter_months_present(tmp_path, monkeypatch):
    """Reproduce el CSV real de junio-26: las 3 filas (Abr/May/Jun) existen con su valor en la
    primera columna de datos — debe dar PASS, no el falso 'faltan' que daba la versión con bug."""
    metrics = _load_fixture()
    metrics["cutoff_month"] = "2026-06"
    metrics["is_quarter_end"] = True
    budget_csv = _write_budget_csv(tmp_path, [
        {"Metric": "ARR EoP", "Fecha": "Apr - 26", "value": "27000000"},
        {"Metric": "ARR EoP", "Fecha": "May - 26", "value": "27500000"},
        {"Metric": "ARR EoP", "Fecha": "Jun - 26", "value": "28000000"},
    ])
    monkeypatch.setattr(paths, "METRICAS_BUDGET_CSV", budget_csv)
    results = _write_and_run(tmp_path, metrics)
    r = _results_by_id(results)["R11"]
    assert r.status == "PASS", r.detail


def test_r11_fails_when_a_quarter_month_is_missing_from_budget_csv(tmp_path, monkeypatch):
    metrics = _load_fixture()
    metrics["cutoff_month"] = "2026-06"
    metrics["is_quarter_end"] = True
    budget_csv = _write_budget_csv(tmp_path, [
        {"Metric": "ARR EoP", "Fecha": "Apr - 26", "value": "27000000"},
        {"Metric": "ARR EoP", "Fecha": "May - 26", "value": "27500000"},
        # Jun - 26 falta por completo
    ])
    monkeypatch.setattr(paths, "METRICAS_BUDGET_CSV", budget_csv)
    results = _write_and_run(tmp_path, metrics)
    r = _results_by_id(results)["R11"]
    assert r.status == "FAIL"
    assert "Jun - 26" in r.detail


# ── R12 — conteo de slides en el standalone (~47) ────────────────────────────────────────

def _html_with_n_slides(tmp_path, n):
    body = "".join(f'<div class="dt-slide"></div>' for _ in range(n))
    return _write_raw_html(tmp_path, body)


def test_r12_passes_with_expected_slide_count(tmp_path):
    html_path = _html_with_n_slides(tmp_path, paths.EXPECTED_SLIDE_COUNT)
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R12"]
    assert r.status == "PASS"
    assert str(paths.EXPECTED_SLIDE_COUNT) in r.detail


def test_r12_warns_when_slightly_below_expected(tmp_path):
    n = paths.MIN_SLIDE_COUNT_WARNING + 1  # entre el mínimo de warning y el esperado-2
    html_path = _html_with_n_slides(tmp_path, n)
    results = _run_with_html(tmp_path, html_path)
    assert _results_by_id(results)["R12"].status == "WARN"


def test_r12_fails_when_far_below_minimum(tmp_path):
    html_path = _html_with_n_slides(tmp_path, paths.MIN_SLIDE_COUNT_WARNING - 5)
    results = _run_with_html(tmp_path, html_path)
    assert _results_by_id(results)["R12"].status == "FAIL"


# ── R17 — P&L presente (agregada 2026-07-08 al bajar F0.4 de FAIL a WARN) ────────────────

def test_r17_passes_when_pnl_fields_present(tmp_path):
    metrics = _load_fixture()
    metrics["net_revenue"] = "$2.4M"
    metrics["gross_margin"] = "68.0%"
    metrics["ebitda_margin"] = "7.7%"
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R17"].status == "PASS"


def test_r17_fails_when_pnl_fields_missing(tmp_path):
    """Reproduce el escenario real que motivó esta regla: Finance no mandó el P&L del mes,
    merge_pnl() no truena pero tampoco setea estos campos — el Validator debe atraparlo acá,
    con el board ya armado, en vez de que F0.4 bloquee todo desde el inicio (WARN ahora)."""
    metrics = _load_fixture()  # el fixture nunca tuvo estos 3 campos
    results = _write_and_run(tmp_path, metrics)
    r = _results_by_id(results)["R17"]
    assert r.status == "FAIL"
    assert "net_revenue" in r.detail


def test_r17_fails_when_pnl_field_is_empty_string(tmp_path):
    """No solo 'falta la clave' — un valor vacío/None también debe contar como faltante."""
    metrics = _load_fixture()
    metrics["net_revenue"] = ""
    metrics["gross_margin"] = "68.0%"
    metrics["ebitda_margin"] = "7.7%"
    results = _write_and_run(tmp_path, metrics)
    assert _results_by_id(results)["R17"].status == "FAIL"


def test_r17_fails_when_pnl_field_is_literal_na_placeholder(tmp_path):
    """Bug real encontrado 2026-07-08 generando junio: fetch_metrics.py no deja estos campos
    en None/vacío cuando no hay datos — les pone el string literal "N/A" (default seteado antes
    de merge_pnl(), nunca sobreescrito). `not "N/A"` es False, así que la versión anterior de
    R17 daba PASS con el P&L completamente ausente. Confirmado en vivo contra junio-26 real."""
    metrics = _load_fixture()
    metrics["net_revenue"] = "N/A"
    metrics["gross_margin"] = "N/A"
    metrics["ebitda_margin"] = "N/A"
    results = _write_and_run(tmp_path, metrics)
    r = _results_by_id(results)["R17"]
    assert r.status == "FAIL"
    assert "net_revenue" in r.detail


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


def _write_raw_html(tmp_path, body: str):
    p = tmp_path / "board_standalone.html"
    p.write_text(f"<html><body>{body}</body></html>", encoding="utf-8")
    return p


def test_r16_pass_when_no_slide_has_inline_px_override(tmp_path):
    """Reproduce el patrón real de los 8 templates (verificado 2026-07-06): slides sin
    inline style de dimensión, o con style que no toca width/height en px (ej. padding:0
    del full-bleed image en 2_discussion_topic.j2)."""
    html_path = _write_raw_html(tmp_path, '''
        <div class="dt-slide" style="padding:0;"><img src="x.png"></div>
        <div class="slide section-divider">cover</div>
    ''')
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R16"]
    assert r.status == "PASS"


def test_r16_fails_when_slide_shell_has_px_dimension_override(tmp_path):
    """Alguien agrega un slide nuevo con width/height fijo inline, pisando el 960x540 que
    debería venir de --slide-width/--slide-height en base.css — exactamente el tipo de error
    que este check existe para atrapar."""
    html_path = _write_raw_html(tmp_path, '''
        <div class="dt-slide" style="width:800px;height:400px;">roto</div>
    ''')
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R16"]
    assert r.status == "FAIL"
    assert "dt-slide" in r.detail


def test_r16_ignores_non_shell_elements_with_px_styles(tmp_path):
    """Un <div> interno cualquiera (no un slide-shell) puede tener width/height en px sin
    problema — R16 solo le importa a los contenedores de slide completo."""
    html_path = _write_raw_html(tmp_path, '''
        <div class="dt-slide"><div class="icon" style="width:24px;height:24px;">x</div></div>
    ''')
    results = _run_with_html(tmp_path, html_path)
    assert _results_by_id(results)["R16"].status == "PASS"


def test_r16_skip_when_html_missing():
    results = phase4_validator.run(metrics_path=FIXTURE, html_path=MISSING_HTML)
    assert _results_by_id(results)["R16"].status == "SKIP"


def test_r16_skip_when_no_slide_shell_found_at_all(tmp_path):
    """v1 de esta regla devolvía PASS aunque no hubiera ningún slide-shell en el HTML —
    indistinguible de 'revisé todo y está bien'. Debe ser SKIP explícito, mismo criterio que
    R13-R15 cuando no encuentran filas que verificar."""
    html_path = _write_raw_html(tmp_path, '<div class="not-a-slide">contenido irrelevante</div>')
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R16"]
    assert r.status == "SKIP"


def test_r16_fails_when_style_attribute_comes_before_class(tmp_path):
    """Bug real encontrado en revisión de código 2026-07-06: la v1 exigía literalmente
    class="..." seguido de style="..." en ese orden — este caso (orden invertido) pasaba
    desapercibido como falso negativo. Debe detectarse igual."""
    html_path = _write_raw_html(tmp_path, '<div style="width:800px;" class="dt-slide">roto</div>')
    results = _run_with_html(tmp_path, html_path)
    assert _results_by_id(results)["R16"].status == "FAIL"


def test_r16_fails_when_attribute_is_interleaved_between_class_and_style(tmp_path):
    """Mismo bug: un atributo intermedio (ej. id) entre class y style también desactivaba
    la v1 en silencio."""
    html_path = _write_raw_html(tmp_path, '<div class="dt-slide" id="foo" style="height:400px;">roto</div>')
    results = _run_with_html(tmp_path, html_path)
    assert _results_by_id(results)["R16"].status == "FAIL"


class _FakePageR18:
    def __init__(self, evaluate_result):
        self._result = evaluate_result
        self.goto_calls = []

    def goto(self, uri):
        self.goto_calls.append(uri)

    def evaluate(self, js):
        return self._result


class _FakeBrowserR18:
    def __init__(self, page):
        self._page = page
        self.closed = False

    def new_page(self, viewport=None):
        return self._page

    def close(self):
        self.closed = True


class _FakeChromiumR18:
    def __init__(self, browser):
        self._browser = browser

    def launch(self):
        return self._browser


class _FakePlaywrightContextR18:
    def __init__(self, browser):
        self.chromium = _FakeChromiumR18(browser)


class _FakeSyncPlaywrightR18:
    def __init__(self, browser):
        self._browser = browser

    def __enter__(self):
        return _FakePlaywrightContextR18(self._browser)

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_playwright_r18(monkeypatch):
    """Inyecta un módulo playwright.sync_api falso en sys.modules — playwright no es
    dependencia del proyecto (ver pyproject.toml), así que el import local dentro de
    _check_r18_slide_overflow debe resolverse contra este doble, no contra el paquete real."""

    def _install(evaluate_result):
        page = _FakePageR18(evaluate_result)
        browser = _FakeBrowserR18(page)
        fake_module = types.ModuleType("playwright.sync_api")
        fake_module.sync_playwright = lambda: _FakeSyncPlaywrightR18(browser)
        monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
        monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_module)
        return page

    return _install


def test_r18_skip_when_playwright_not_installed(tmp_path):
    """El entorno de test no declara playwright como dependencia (ver pyproject.toml) — R18
    debe degradar a SKIP en vez de tumbar el resto del Validator."""
    html_path = _write_raw_html(tmp_path, '<div class="dt-slide">contenido normal</div>')
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R18"]
    assert r.status == "SKIP"
    assert "playwright" in r.detail.lower()


def test_r18_skip_when_html_missing(fake_playwright_r18):
    fake_playwright_r18([])
    results = phase4_validator.run(metrics_path=FIXTURE, html_path=MISSING_HTML)
    r = _results_by_id(results)["R18"]
    assert r.status == "SKIP"
    assert "no existe" in r.detail


def test_r18_skip_when_no_slide_shell_found(tmp_path, fake_playwright_r18):
    fake_playwright_r18([])
    html_path = _write_raw_html(tmp_path, '<div class="not-a-slide">x</div>')
    results = _run_with_html(tmp_path, html_path)
    assert _results_by_id(results)["R18"].status == "SKIP"


def test_r18_pass_when_no_overflow(tmp_path, fake_playwright_r18):
    fake_playwright_r18([{"classes": "dt-slide", "overflowY": 0, "overflowX": 0, "text": "todo bien"}])
    html_path = _write_raw_html(tmp_path, '<div class="dt-slide">todo bien</div>')
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R18"]
    assert r.status == "PASS"
    assert "1 slides verificados" in r.detail


def test_r18_warns_when_slide_content_overflows(tmp_path, fake_playwright_r18):
    """Reproduce el riesgo real documentado en skills/ceo-highlights/SKILL.md: contenido que
    excede el slide fijo de 960x540 y se recorta en silencio por overflow:hidden."""
    fake_playwright_r18([
        {"classes": "slide", "overflowY": 45, "overflowX": 0, "text": "CEO Highlights & Lowlights..."},
    ])
    html_path = _write_raw_html(tmp_path, '<div class="slide">mucho contenido</div>')
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R18"]
    assert r.status == "WARN"
    assert "1/1 slides" in r.detail


def test_r18_ignores_overflow_within_tolerance(tmp_path, fake_playwright_r18):
    """1px de diferencia es ruido de redondeo del navegador, no un desborde real."""
    fake_playwright_r18([{"classes": "slide", "overflowY": 1, "overflowX": 0, "text": "x"}])
    html_path = _write_raw_html(tmp_path, '<div class="slide">x</div>')
    results = _run_with_html(tmp_path, html_path)
    assert _results_by_id(results)["R18"].status == "PASS"


def test_r18_skip_on_playwright_runtime_error(tmp_path, monkeypatch):
    """Si Chromium no está instalado (browser.launch() revienta), R18 no debe tumbar el resto
    del Validator — debe degradar a SKIP con el error, mismo criterio que R7 con Redshift."""

    class _BoomChromium:
        @staticmethod
        def launch():
            raise RuntimeError("Executable doesn't exist")

    class _BoomContext:
        def __enter__(self):
            return types.SimpleNamespace(chromium=_BoomChromium())

        def __exit__(self, *exc):
            return False

    fake_module = types.ModuleType("playwright.sync_api")
    fake_module.sync_playwright = lambda: _BoomContext()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_module)

    html_path = _write_raw_html(tmp_path, '<div class="slide">x</div>')
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R18"]
    assert r.status == "SKIP"
    assert "Executable" in r.detail


def _write_r19_html(tmp_path, monthly_arr, ytd_arr):
    body = f'''
        <!-- SLIDE 5 — Monthly Performance -->
        <div class="slide">
          <div class="ks-p-name">ARR</div>
          <div class="ks-p-val">{monthly_arr}</div>
        </div>
        <!-- SLIDE 5 — YTD Performance -->
        <div class="slide">
          <div class="ks-p-name">ARR</div>
          <div class="ks-p-val ks-p-val-green">{ytd_arr}</div>
        </div>
    '''
    return _write_raw_html(tmp_path, body)


def test_r19_pass_when_arr_matches_across_slides(tmp_path):
    html_path = _write_r19_html(tmp_path, "$29.8M", "$29.8M")
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R19"]
    assert r.status == "PASS"
    assert "$29.8M" in r.detail


def test_r19_fails_when_arr_diverges_across_slides(tmp_path):
    """Reproduce el bug real v36: ARR sin Alanube en una de las dos vistas."""
    html_path = _write_r19_html(tmp_path, "$29.8M", "$28.8M")
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R19"]
    assert r.status == "FAIL"
    assert "$29.8M" in r.detail
    assert "$28.8M" in r.detail


def test_r19_skip_when_html_missing():
    results = phase4_validator.run(metrics_path=FIXTURE, html_path=MISSING_HTML)
    assert _results_by_id(results)["R19"].status == "SKIP"


def test_r19_skip_when_slide_not_found(tmp_path):
    html_path = _write_raw_html(tmp_path, '<div class="slide">contenido sin las slides esperadas</div>')
    results = _run_with_html(tmp_path, html_path)
    r = _results_by_id(results)["R19"]
    assert r.status == "SKIP"
    assert "Monthly Performance" in r.detail


def test_r19_skip_when_arr_value_not_found_in_slide(tmp_path):
    """La slide existe pero no tiene el bloque ks-p-name/ks-p-val esperado — no debe
    confundirse con un FAIL, es un formato distinto al esperado."""
    html_path = _write_raw_html(tmp_path, '''
        <!-- SLIDE 5 — Monthly Performance -->
        <div class="slide">sin el bloque de ARR</div>
        <!-- SLIDE 5 — YTD Performance -->
        <div class="slide">
          <div class="ks-p-name">ARR</div>
          <div class="ks-p-val">$29.8M</div>
        </div>
    ''')
    results = _run_with_html(tmp_path, html_path)
    assert _results_by_id(results)["R19"].status == "SKIP"
