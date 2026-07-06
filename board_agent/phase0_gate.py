"""Fase 0 — Human Inputs Gate (workaround temporal, ver AGENT_ARCHITECTURE.md).

Verifica que las fuentes manuales (CSVs, YAMLs editoriales) tengan datos del
mes objetivo ANTES de correr fetch_metrics.py. Esta fase debe desaparecer
cuando esas fuentes se muevan a Redshift — mientras tanto, decirle al usuario
exactamente qué falta y quién lo provee.
"""

import csv
from datetime import datetime

import yaml

from . import paths
from .report import CheckResult

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

PLACEHOLDER_MARKERS = ("por definir", "tbd", "todo", "pendiente de", "n/a")


def _month_label_es(month: str) -> str:
    y, m = month.split("-")
    return f"{MESES_ES[int(m)]} {y}"


def _check_pnl_actual(month: str) -> CheckResult:
    """merge_pnl() en fetch_metrics.py cae a data/pnl_override.yaml si el CSV no
    tiene filas del mes (workaround ya en uso, con datos de Finance a mano) —
    el gate tiene que reconocer esa fuente también o reporta un falso bloqueante.
    """
    target_y, target_m = (int(x) for x in month.split("-"))
    max_date = None
    hit_csv = False
    with open(paths.PNL_ACTUAL_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        try:
            d = datetime.strptime(r["Date"], "%m/%d/%Y")
        except (ValueError, KeyError):
            continue
        if max_date is None or d > max_date:
            max_date = d
        if d.year == target_y and d.month == target_m:
            hit_csv = True

    hit_override = False
    override_path = paths.DATA_DIR / "pnl_override.yaml"
    if override_path.exists():
        with open(override_path, encoding="utf-8") as f:
            override = yaml.safe_load(f) or {}
        hit_override = month in override

    if hit_csv:
        return CheckResult("F0.4", f"P&L tiene filas de {month} (CSV o override)", "PASS", "fuente: CSV")
    if hit_override:
        return CheckResult("F0.4", f"P&L tiene filas de {month} (CSV o override)", "PASS",
                            "fuente: data/pnl_override.yaml (manual, no el CSV)")
    return CheckResult("F0.4", f"P&L tiene filas de {month} (CSV o override)", "FAIL",
                        f"CSV parado en {max_date.date() if max_date else '?'} y sin entrada '{month}' en pnl_override.yaml")


def _check_ceo_yaml(month: str) -> CheckResult:
    with open(paths.CEO_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    highlights = data.get("highlights") or []
    lowlights = data.get("lowlights") or []
    label = _month_label_es(month)
    title = (data.get("ceo_title") or "").lower()
    text_blob = " ".join(highlights + lowlights).lower()
    has_placeholder = any(m in text_blob for m in PLACEHOLDER_MARKERS)
    empty = not highlights or not lowlights
    if empty or has_placeholder:
        return CheckResult("F0.5", "editorial/ceo.yaml sin placeholders vacíos", "WARN",
                            f"highlights={len(highlights)} lowlights={len(lowlights)} placeholder_detectado={has_placeholder}")
    return CheckResult("F0.5", "editorial/ceo.yaml sin placeholders vacíos", "PASS",
                        f"highlights={len(highlights)} lowlights={len(lowlights)} (título: '{data.get('ceo_title')}', esperado mes: {label})")


def _check_discussion_topics() -> CheckResult:
    with open(paths.DISCUSSION_TOPICS_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    topics = data.get("topics") or []
    placeholders = [t for t in topics if "por definir" in (t.get("title_plain") or "").lower()]
    if not topics or placeholders:
        return CheckResult("F0.6", "editorial/discussion_topics.yaml no vacío", "WARN",
                            f"{len(placeholders)}/{len(topics)} topics aún placeholder")
    return CheckResult("F0.6", "editorial/discussion_topics.yaml no vacío", "PASS", f"{len(topics)} topics")


def _check_arr_walk_yaml() -> CheckResult:
    with open(paths.ARR_WALK_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    products = data.get("products") or []
    all_asks_empty = all(not p.get("asks") for p in products)
    insight_empty = not (data.get("alanube_insight") or "").strip()
    if all_asks_empty or insight_empty:
        return CheckResult("F0.7", "editorial/arr_walk.yaml comentarios llenos", "WARN",
                            f"asks vacíos en todos los productos={all_asks_empty} · alanube_insight vacío={insight_empty}")
    return CheckResult("F0.7", "editorial/arr_walk.yaml comentarios llenos", "PASS", "")


def run(month: str) -> list[CheckResult]:
    """month en formato 'YYYY-MM' (mes objetivo del próximo board).

    Fuentes que salieron de este gate porque ya se automatizaron (fetch_metrics.py las lee
    directo de RS, dejaron de ser un input manual — ver docs/AGENT_ARCHITECTURE.md):
    - paises_fx.csv → dwh_dimensions.tb_trm_banrep (Fase 1, check F1.5)
    - chart_alanube.yaml → bi_alanube.fact_alanube_arr_walk (load_alanube_arr(), 2026-07-03)
    - Payback.csv → bi_strategic.payback_cohort_results (load_payback(), 2026-07-06)
    """
    return [
        _check_pnl_actual(month),
        _check_ceo_yaml(month),
        _check_discussion_topics(),
        _check_arr_walk_yaml(),
    ]
