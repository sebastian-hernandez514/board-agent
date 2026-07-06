"""Fase 5 — Diff Review.

No hace falta guardar snapshots históricos aparte: metrics.yaml ya trae series de 5 meses
(arr_walk_table) y los deltas MoM/YoY pre-calculados — Fase 5 solo les aplica los umbrales
de alerta documentados en docs/AGENT_ARCHITECTURE.md.

D7 ("lista de slides que cambiaron") sí requiere diff de HTML — implementado 2026-07-06
reusando el mismo criterio de detección de slides que R12 (paths.SLIDE_CLASS_TOKENS), en vez
de contarlas.
"""

import re

import yaml

from . import paths, versioning
from .parsing import find_row, last, parse_cell, parse_money_cell
from .report import CheckResult

_SLIDE_DIV_RE = re.compile(r'<div class="([^"]*)"')


def _slide_chunks(html: str) -> list[str]:
    """Divide el HTML en slides usando los mismos class tokens que R12 (phase4_validator.py) —
    una lista de substrings, uno por slide, en orden de aparición."""
    starts = [m.start() for m in _SLIDE_DIV_RE.finditer(html)
              if set(m.group(1).split()) & paths.SLIDE_CLASS_TOKENS]
    return [html[start:(starts[i + 1] if i + 1 < len(starts) else len(html))]
            for i, start in enumerate(starts)]


def _normalize_slide(chunk: str) -> str:
    """Elimina TODO espacio en blanco (no solo colapsa) para que diferencias de formato (ej.
    indentación distinta entre corridas de generate.py) no cuenten como 'la slide cambió' —
    colapsar a un solo espacio no alcanza cuando un lado no tiene ningún espacio ahí."""
    return re.sub(r"\s+", "", chunk)


def _latest_version_file(board_dir):
    if not board_dir.exists():
        return None
    files = [p for p in board_dir.glob("*_v*.html") if re.search(r"_v(\d+)\.html$", p.name)]
    if not files:
        return None
    return max(files, key=lambda p: int(re.search(r"_v(\d+)\.html$", p.name).group(1)))


def _find_previous_board(cutoff: str):
    """Última versión guardada para diffear contra el standalone actual — primero dentro
    del mismo mes (iteración en curso), si no existe intenta el mes anterior (board ya
    publicado). None si no hay ningún board guardado todavía en ninguno de los dos."""
    cur = _latest_version_file(paths.BOARDS_DIR / cutoff)
    if cur:
        return cur
    y, m = int(cutoff[:4]), int(cutoff[5:])
    m -= 1
    if m == 0:
        y, m = y - 1, 12
    return _latest_version_file(paths.BOARDS_DIR / f"{y:04d}-{m:02d}")


def _check_d7(cutoff: str) -> CheckResult:
    prev_path = _find_previous_board(cutoff)
    if prev_path is None:
        return CheckResult("D7", "Lista de slides que cambiaron vs board anterior", "SKIP",
                            "no hay ningún board guardado todavía para comparar")
    if not paths.BOARD_STANDALONE_HTML.exists():
        return CheckResult("D7", "Lista de slides que cambiaron vs board anterior", "SKIP",
                            f"no existe {paths.BOARD_STANDALONE_HTML} — ¿corrió Fase 3?")

    old_slides = _slide_chunks(prev_path.read_text(encoding="utf-8"))
    new_slides = _slide_chunks(paths.BOARD_STANDALONE_HTML.read_text(encoding="utf-8"))

    changed = []
    for i in range(max(len(old_slides), len(new_slides))):
        old_c = _normalize_slide(old_slides[i]) if i < len(old_slides) else None
        new_c = _normalize_slide(new_slides[i]) if i < len(new_slides) else None
        if old_c != new_c:
            changed.append(i + 1)

    count_note = "" if len(old_slides) == len(new_slides) else f" (¡{len(old_slides)}→{len(new_slides)} slides!)"
    detail = f"vs {prev_path.name}{count_note} — {len(changed)}/{len(new_slides)} cambiaron: {changed}"
    return CheckResult("D7", "Lista de slides que cambiaron vs board anterior", "PASS", detail)

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

    try:
        results.append(_check_d7(metrics["cutoff_month"]))
    except Exception as e:
        results.append(CheckResult("D7", "Lista de slides que cambiaron vs board anterior", "SKIP", f"error: {e}"))

    return results
