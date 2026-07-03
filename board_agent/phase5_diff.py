"""Fase 5 — Diff Review.

No hace falta guardar snapshots históricos aparte: metrics.yaml ya trae series de 5 meses
(arr_walk_table) y los deltas MoM/YoY pre-calculados — Fase 5 solo les aplica los umbrales
de alerta documentados en docs/AGENT_ARCHITECTURE.md.

"Lista de slides que cambiaron" (comparar HTML renderizado contra el board anterior) queda
como gap explícito — requiere diff de HTML, no de metrics.yaml, no implementado hoy.
"""

import yaml

from . import paths, versioning
from .parsing import find_row, last, parse_cell, parse_money_cell
from .report import CheckResult

THRESH_ARR_MOM_PCT = 5.0
THRESH_LOGOS_MOM_PCT = 3.0
THRESH_CHURN_MOM_PP = 1.0
THRESH_NEW_LOGOS_YOY_PCT = 30.0
THRESH_FX_IMPACT_ABS = 2_000_000


def _load_metrics(metrics_path):
    with open(metrics_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _section_with_label(metrics: dict, label: str) -> list:
    for section in metrics["arr_walk_table"]["sections"]:
        if label in {r["label"] for r in section["rows"]}:
            return section["rows"]
    raise KeyError(f"ninguna sección de arr_walk_table tiene la fila '{label}'")


def _version_suggestion(metrics: dict) -> CheckResult:
    cutoff = metrics["cutoff_month"]
    board_dir = paths.BOARDS_DIR / cutoff
    files = sorted(board_dir.glob("*_v*.html")) if board_dir.exists() else []
    next_v = versioning.next_version_number(cutoff)
    detail = f"{len(files)} versión(es) ya en {board_dir.name}/ → sugerido v{next_v}"
    if next_v > 1:
        detail += f" (última: v{next_v - 1})"
    return CheckResult("D6", "Sugerencia de versión", "PASS", detail)


def run(metrics_path=paths.METRICS_YAML) -> list[CheckResult]:
    results = []
    metrics = _load_metrics(metrics_path)

    try:
        field = "arr_qoq" if metrics.get("is_quarter_end") else "arr_mom"
        pct = parse_cell(metrics[field])
        status = "WARN" if abs(pct) > THRESH_ARR_MOM_PCT else "PASS"
        results.append(CheckResult("D1", f"ARR total variación ≤ {THRESH_ARR_MOM_PCT}%", status, f"{field}={pct}%"))
    except Exception as e:
        results.append(CheckResult("D1", "ARR total variación", "SKIP", f"error: {e}"))

    try:
        logos_rows = _section_with_label(metrics, "Total EoP")
        cells = find_row(logos_rows, "Total EoP")
        cur, prev = parse_cell(cells[-1]), parse_cell(cells[-2])
        pct = (cur - prev) / prev * 100 if prev else 0
        status = "WARN" if abs(pct) > THRESH_LOGOS_MOM_PCT else "PASS"
        results.append(CheckResult("D2", f"Logos EoP variación ≤ {THRESH_LOGOS_MOM_PCT}%", status,
                                    f"{prev:.1f}k → {cur:.1f}k ({pct:+.1f}%)"))
    except Exception as e:
        results.append(CheckResult("D2", "Logos EoP variación", "SKIP", f"error: {e}"))

    try:
        logos_rows = _section_with_label(metrics, "Logo Monthly Churn %")
        cells = find_row(logos_rows, "Logo Monthly Churn %")
        cur, prev = parse_cell(cells[-1]), parse_cell(cells[-2])
        delta_pp = cur - prev
        status = "WARN" if abs(delta_pp) > THRESH_CHURN_MOM_PP else "PASS"
        results.append(CheckResult("D3", f"Churn Rate variación ≤ {THRESH_CHURN_MOM_PP}pp", status,
                                    f"{prev}% → {cur}% ({delta_pp:+.1f}pp)"))
    except Exception as e:
        results.append(CheckResult("D3", "Churn Rate variación", "SKIP", f"error: {e}"))

    try:
        pct = parse_cell(metrics["new_logos_yoy"])
        status = "WARN" if abs(pct) > THRESH_NEW_LOGOS_YOY_PCT else "PASS"
        results.append(CheckResult("D4", f"New Logos YoY dentro de ±{THRESH_NEW_LOGOS_YOY_PCT}%", status,
                                    f"new_logos_yoy={pct}%"))
    except Exception as e:
        results.append(CheckResult("D4", "New Logos YoY", "SKIP", f"error: {e}"))

    try:
        glo_rows = _section_with_label(metrics, "ARR BoP")
        fx = parse_money_cell(last(find_row(glo_rows, "(+/−) FX Impact")))
        status = "WARN" if abs(fx) > THRESH_FX_IMPACT_ABS else "PASS"
        results.append(CheckResult("D5", f"FX Impact absoluto ≤ ${THRESH_FX_IMPACT_ABS / 1e6:.0f}M", status,
                                    f"fx_impact={fx:,.0f}"))
    except Exception as e:
        results.append(CheckResult("D5", "FX Impact absoluto", "SKIP", f"error: {e}"))

    try:
        results.append(_version_suggestion(metrics))
    except Exception as e:
        results.append(CheckResult("D6", "Sugerencia de versión", "SKIP", f"error: {e}"))

    results.append(CheckResult(
        "D7", "Lista de slides que cambiaron vs board anterior", "SKIP",
        "no implementado — requiere diff de HTML renderizado, no solo de metrics.yaml",
    ))

    return results
