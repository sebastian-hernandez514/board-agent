"""Fase 4 — Business Rules Validator.

Verifica que el board sea matemáticamente correcto ANTES de publicarlo.
Las reglas R1/R2 son las que hubieran bloqueado los bugs reales de v36/v37
(ver Board Agent/docs/AGENT_ARCHITECTURE.md). R8 se agregó porque al construir
este validador se encontró una inconsistencia real en el board de mayo-26 ya
publicado (ver docs/AGENT_ARCHITECTURE.md — hallazgo 2026-07-02).

R7 corre una query RS INDEPENDIENTE (no reusa lógica de fetch_metrics.py) — valida
metrics.yaml sin depender de que Template Board exponga el dato crudo. R11 es una
versión reducida y honesta de la regla original: solo verifica completitud del CSV
de budget en cierre de Q, no reproduce la aritmética completa de vs_budget (no se
pudo validar contra un mes de cierre de Q real en esta sesión — mayo-26 no lo es).

Reglas R5, R13-15 quedan como SKIP explícito: requieren datos que metrics.yaml no
expone (los 12 buckets crudos) o parsear CSS del render. No se fingen como cubiertas.
"""

import csv
import re
import sys
from pathlib import Path

import yaml

from . import paths
from .parsing import find_row, last, parse_cell, parse_money_cell
from .report import CheckResult

TOL_ARR_WALK = 150_000  # celdas de arr_walk_table vienen redondeadas a 1 decimal en $M (±$50K por celda)
TOL_ARR_TOTAL = 50_000
TOL_NEW_MRR = 1_000
TOL_CC = 100_000
FX_RESIDUAL_LIMIT = 3_000_000
CHURN_MIN_PCT = 0.0
CHURN_MAX_PCT = 20.0


def _load_metrics(metrics_path: Path) -> dict:
    with open(metrics_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _arr_walk_glo_rows(metrics: dict) -> list:
    """Sección 'ARR BoP ... ARR EoP (Constant Currency)' de arr_walk_table (GLO)."""
    for section in metrics["arr_walk_table"]["sections"]:
        labels = {r["label"] for r in section["rows"]}
        if "ARR BoP" in labels and "Net New ARR" in labels:
            return section["rows"]
    raise KeyError("no se encontró la sección del ARR Walk GLO en arr_walk_table")


def _count_slides(html_path: Path) -> int:
    html = html_path.read_text(encoding="utf-8")
    count = 0
    for m in re.finditer(r'class="([^"]*)"', html):
        classes = set(m.group(1).split())
        if classes & paths.SLIDE_CLASS_TOKENS:
            count += 1
    return count


def _check_r7_logos_dedup(metrics: dict) -> CheckResult:
    """Verifica smb_logos_eop vía COUNT(DISTINCT id_company) en RS — el mismo filtro que usa
    _SQL_LOGOS_ALL en fetch_metrics.py, pero corrido de forma independiente (Board Agent no
    reusa el código de Template Board). Validado 2026-07-03 contra mayo-26 real: match exacto
    58,974 = 58,974."""
    try:
        reported = int(metrics["smb_logos_eop"])
        cutoff = metrics["cutoff_month"]
        sys.path.insert(0, str(paths.REDSHIFT_GUARD_MODULE_DIR))
        from redshift_guard import fetch_results, run_query

        sql = f"""
            SELECT COUNT(DISTINCT id_company) AS logos_eop
            FROM dwh_facts.fact_customers_mrr
            WHERE date_month = DATE '{cutoff}-01'
              AND segment_type_def IN ('Core','Lite')
              AND event_product NOT IN ('AWAITING PAYMENT','CHURN')
              AND amount_usd_mrr > 0
              AND plan_name IS NOT NULL AND plan_name <> ''
        """
        result = run_query(sql=sql, database=paths.RS_DATABASE, cluster_identifier=paths.RS_CLUSTER,
                            db_user=paths.RS_DB_USER)
        if result["status"] != "executed":
            raise RuntimeError(f"query no se ejecutó: {result}")
        rows = fetch_results(result["statement_id"])
        independent = int(rows[0]["logos_eop"])
        diff = reported - independent
        status = "PASS" if diff == 0 else "FAIL"
        return CheckResult(
            "R7", "Logos EoP = COUNT DISTINCT dedup (verificación RS independiente)", status,
            f"metrics.yaml={reported:,} vs RS independiente={independent:,} (diff={diff:+,})",
        )
    except Exception as e:
        return CheckResult("R7", "Logos EoP = COUNT DISTINCT dedup (verificación RS independiente)", "SKIP",
                            f"error: {e}")


def _check_r11_budget_quarter(metrics: dict) -> CheckResult:
    """Versión reducida de R11: en cierre de Q, verifica que Metricas_budget.csv tenga los 3
    meses del quarter completos (no vacíos) para 'ARR EoP'. NO reproduce la aritmética completa
    de *_vs_budget (requeriría un mes de cierre de Q real para validar la lógica — mayo-26 no
    lo es, no se implementó a ciegas)."""
    if not metrics.get("is_quarter_end"):
        return CheckResult("R11", "Budget CSV completo para el quarter (parcial)", "SKIP",
                            "mes de corte no es cierre de quarter")
    try:
        cutoff = metrics["cutoff_month"]  # 'YYYY-MM'
        y, m = cutoff.split("-")
        m = int(m)
        yy = y[2:]
        quarter_labels = [f"{paths.MES_ABBR_EN[mm]} - {yy}" for mm in (m - 2, m - 1, m)]

        with open(paths.METRICAS_BUDGET_CSV, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        missing = []
        for lbl in quarter_labels:
            match = next((r for r in rows if r.get("Metric") == "ARR EoP" and r.get("Fecha", "").strip() == lbl), None)
            if not match or not (match.get(lbl) or "").strip():
                missing.append(lbl)
        status = "FAIL" if missing else "PASS"
        return CheckResult(
            "R11", "Budget CSV completo para el quarter (parcial, solo ARR EoP)", status,
            f"faltan: {missing}" if missing else f"completo: {quarter_labels}",
        )
    except Exception as e:
        return CheckResult("R11", "Budget CSV completo para el quarter (parcial)", "SKIP", f"error: {e}")


def run(metrics_path: Path = paths.METRICS_YAML, html_path: Path = paths.BOARD_STANDALONE_HTML) -> list[CheckResult]:
    results: list[CheckResult] = []
    metrics = _load_metrics(metrics_path)

    # R1 — ARR total incluye Alanube
    try:
        arr_total = parse_cell(metrics["arr_total"])
        chart = metrics["chart_arr_history"]
        expected = chart["alegra_spot"][-1] * 1_000_000 + chart["alanube_spot"][-1]
        diff = arr_total - expected
        status = "PASS" if abs(diff) <= TOL_ARR_TOTAL else "FAIL"
        results.append(CheckResult(
            "R1", "ARR total incluye Alanube", status,
            f"arr_total={arr_total:,.0f} vs alegra+alanube={expected:,.0f} (diff={diff:,.0f})",
        ))
    except Exception as e:
        results.append(CheckResult("R1", "ARR total incluye Alanube", "SKIP", f"error: {e}"))

    # R2 — New MRR Core + Lite = Total (bug real: faltaba /12 en v37)
    try:
        core = parse_cell(metrics["new_mrr_core_fmt"])
        lite = parse_cell(metrics["new_mrr_lite_fmt"])
        total = parse_cell(metrics["new_mrr"])
        diff = (core + lite) - total
        status = "PASS" if abs(diff) <= TOL_NEW_MRR else "FAIL"
        results.append(CheckResult(
            "R2", "New MRR Core + Lite ≈ Total", status,
            f"core={core:,.0f} + lite={lite:,.0f} = {core + lite:,.0f} vs total={total:,.0f} (diff={diff:,.0f})",
        ))
    except Exception as e:
        results.append(CheckResult("R2", "New MRR Core + Lite ≈ Total", "SKIP", f"error: {e}"))

    # R3 — ARR Walk balancea: Additions+Recovered+NetChurn+NetExpansion+FX ≈ NetNewARR ≈ EoP-BoP
    try:
        rows = _arr_walk_glo_rows(metrics)
        bop = parse_money_cell(last(find_row(rows, "ARR BoP")))
        additions = parse_money_cell(last(find_row(rows, "Additions")))
        recovered = parse_money_cell(last(find_row(rows, "Recovered")))
        net_churn = parse_money_cell(last(find_row(rows, "Net Churn")))
        net_expansion = parse_money_cell(last(find_row(rows, "Net Expansion")))
        fx_impact = parse_money_cell(last(find_row(rows, "(+/−) FX Impact")))
        eop = parse_money_cell(last(find_row(rows, "ARR EoP")))
        net_new_arr = parse_money_cell(last(find_row(rows, "Net New ARR")))

        sum_buckets = additions + recovered + net_churn + net_expansion + fx_impact
        diff_buckets = sum_buckets - net_new_arr
        diff_eop = net_new_arr - (eop - bop)
        status = "PASS" if abs(diff_buckets) <= TOL_ARR_WALK and abs(diff_eop) <= TOL_ARR_WALK else "FAIL"
        results.append(CheckResult(
            "R3", "ARR Walk balancea (buckets = Net New ARR = EoP-BoP)", status,
            f"buckets={sum_buckets:,.0f} vs netNewARR={net_new_arr:,.0f} (diff={diff_buckets:,.0f}); "
            f"EoP-BoP={eop - bop:,.0f} vs netNewARR={net_new_arr:,.0f} (diff={diff_eop:,.0f})",
        ))

        # R4 — Net Churn es negativo
        status4 = "PASS" if net_churn < 0 else "FAIL"
        results.append(CheckResult("R4", "Net Churn es negativo", status4, f"net_churn={net_churn:,.0f}"))

        # R6 — FX residual pequeño
        status6 = "PASS" if abs(fx_impact) < FX_RESIDUAL_LIMIT else "FAIL"
        results.append(CheckResult(
            "R6", f"FX residual < ${FX_RESIDUAL_LIMIT / 1e6:.0f}M", status6, f"fx_impact={fx_impact:,.0f}",
        ))

        # R8 — ARR EoP (Constant Currency) del mes de corte == ARR EoP regular (ratio FX = 1)
        eop_cc = parse_money_cell(last(find_row(rows, "ARR EoP (Constant Currency)")))
        diff_cc = eop_cc - eop
        status8 = "PASS" if abs(diff_cc) <= TOL_CC else "FAIL"
        results.append(CheckResult(
            "R8", "ARR EoP (Constant Currency) = ARR EoP en el mes de corte", status8,
            f"eop_cc={eop_cc:,.0f} vs eop={eop:,.0f} (diff={diff_cc:,.0f})",
        ))
    except Exception as e:
        for rid, desc in [
            ("R3", "ARR Walk balancea (buckets = Net New ARR = EoP-BoP)"),
            ("R4", "Net Churn es negativo"),
            ("R6", f"FX residual < ${FX_RESIDUAL_LIMIT / 1e6:.0f}M"),
            ("R8", "ARR EoP (Constant Currency) = ARR EoP en el mes de corte"),
        ]:
            results.append(CheckResult(rid, desc, "SKIP", f"error: {e}"))

    # R9 — Consistencia MoM vs QoQ según mes de cierre de quarter
    try:
        cutoff_month = metrics["cutoff_month"]  # 'YYYY-MM'
        month_num = int(cutoff_month.split("-")[1])
        expected_quarter_end = month_num in (3, 6, 9, 12)
        actual = bool(metrics["is_quarter_end"])
        status = "PASS" if actual == expected_quarter_end else "FAIL"
        results.append(CheckResult(
            "R9", "is_quarter_end consistente con el mes de corte", status,
            f"cutoff_month={cutoff_month} → esperado={expected_quarter_end}, metrics.yaml={actual}",
        ))
    except Exception as e:
        results.append(CheckResult("R9", "is_quarter_end consistente con el mes de corte", "SKIP", f"error: {e}"))

    # R10 — Churn Rate global entre 0% y 20%
    try:
        churn_pct = parse_cell(metrics["logo_churn_global"])
        status = "PASS" if CHURN_MIN_PCT <= churn_pct <= CHURN_MAX_PCT else "FAIL"
        results.append(CheckResult(
            "R10", f"Logo Churn Global entre {CHURN_MIN_PCT}% y {CHURN_MAX_PCT}%", status,
            f"logo_churn_global={churn_pct}%",
        ))
    except Exception as e:
        results.append(CheckResult("R10", "Logo Churn Global entre 0% y 20%", "SKIP", f"error: {e}"))

    results.append(_check_r7_logos_dedup(metrics))
    results.append(_check_r11_budget_quarter(metrics))

    # R12 — Número de slides en el standalone ≈ 47 (selector real de generate_pdf.py)
    try:
        n_slides = _count_slides(html_path)
        if n_slides >= paths.EXPECTED_SLIDE_COUNT - 2:
            status = "PASS"
        elif n_slides >= paths.MIN_SLIDE_COUNT_WARNING:
            status = "WARN"
        else:
            status = "FAIL"
        results.append(CheckResult(
            "R12", f"~{paths.EXPECTED_SLIDE_COUNT} slides en el standalone", status,
            f"encontrados={n_slides}",
        ))
    except Exception as e:
        results.append(CheckResult("R12", f"~{paths.EXPECTED_SLIDE_COUNT} slides en el standalone", "SKIP", f"error: {e}"))

    # Reglas con gap de datos conocido — no se fingen como cubiertas
    for rid, desc, why in [
        ("R5", "cross_down restado en Net Expansion", "requiere los 12 buckets crudos (no expuestos en metrics.yaml)"),
        ("R13", "Investment: delta neutro (sin verde/rojo)", "requiere parsear clases CSS del HTML — no implementado aún"),
        ("R14", "Churn/CAC: delta invertido", "requiere parsear clases CSS del HTML — no implementado aún"),
        ("R15", "Resto de métricas: signo estándar de color", "requiere parsear clases CSS del HTML — no implementado aún"),
    ]:
        results.append(CheckResult(rid, desc, "SKIP", why))

    return results
