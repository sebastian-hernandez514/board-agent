"""Fase 1 — Data Freshness Check.

Migración 2026-07-10: Board Agent ya no tiene acceso a Redshift ni credenciales AWS, así
que este chequeo ya no corre queries en vivo. En su lugar lee el bloque "freshness" que
Claude Code ya debió escribir en METABASE_CACHE_FILE — una query MBQL de
MAX(fecha)/COUNT(*) por tabla, para el mes objetivo, corrida vía el MCP de Metabase antes
de invocar el pipeline (ver board_agent/metabase_fetch_spec.py para el detalle de cada
query y memory/project_board_agent.md para el historial de la migración).
"""

import json

from . import paths
from .report import CheckResult

# Única fuente de verdad de las 13 queries de freshness — board_agent/metabase_fetch_spec.py
# (documentación de qué correr por el MCP de Metabase) importa esta misma lista en vez de
# mantener una copia a mano; hallazgo 2026-07-14: antes había dos listas de 13 elementos
# mantenidas por separado, sin nada que avisara si se desincronizaban.
# check_id -> (label, tabla en Metabase, severidad si la tabla no tiene filas del mes,
#              columna de fecha a usar en MAX()/COUNT() al construir la query MBQL)
_CHECKS = [
    ("F1.1",  "fact_customers_mrr tiene el mes objetivo",         "dm_strategic.fact_customers_mrr",           "FAIL", "date_month"),
    ("F1.2",  "bi_customer_monthly_status tiene el mes objetivo", "dm_retention.bi_customer_monthly_status",   "FAIL", "date_month"),
    ("F1.3",  "fact_cac_version_segments tiene el mes objetivo",  "dm_strategic.fact_cac_version_segments",    "WARN", "cohortmonth"),
    ("F1.4",  "accountant_master_table tiene el mes objetivo",    "dm_accountant.accountant_master_table",     "FAIL", "date_month"),
    ("F1.5",  "tb_trm_banrep (FX) tiene el mes objetivo",         "dm_strategic.tb_trm_banrep",                "FAIL", "month"),
    ("F1.6",  "fact_alanube_arr_walk tiene el mes objetivo",      "dm_alanube.fact_alanube_arr_walk",          "WARN", "month_date"),
    ("F1.7",  "payback_cohort_results tiene el mes objetivo",     "dm_strategic.payback_cohort_results",       "WARN", "cohort_month"),
    ("F1.8",  "fact_headcount_eop tiene el mes objetivo",         "dm_strategic.fact_headcount_eop",           "WARN", "fecha"),
    ("F1.9",  "fact_headcount_forecast tiene el mes objetivo",    "dm_strategic.fact_headcount_forecast",      "WARN", "fecha"),
    ("F1.10", "fact_headcount_movements tiene el mes objetivo",   "dm_strategic.fact_headcount_movements",     "WARN", "fecha"),
    ("F1.11", "bi_churn_retired tiene el mes objetivo",           "dm_retention.bi_churn_retired",             "WARN", "date_month"),
    ("F1.12", "fact_closed_deals tiene el mes objetivo",          "dm_sales.fact_closed_deals",                "WARN", "close_date (DATE_TRUNC month)"),
    ("F1.13", "sales_actions tiene el mes objetivo",              "dm_sales.sales_actions",                    "WARN", "fecha (DATE_TRUNC month)"),
]


def run(month: str) -> list[CheckResult]:
    """month en formato 'YYYY-MM'."""
    if not paths.METABASE_CACHE_FILE.exists():
        return [CheckResult(
            "F1.0", "Cache de Metabase disponible", "FAIL",
            f"no existe {paths.METABASE_CACHE_FILE} — antes de correr el pipeline, Claude Code debe "
            "ejecutar las queries de freshness vía el MCP de Metabase y escribirlas ahí "
            "(ver board_agent/metabase_fetch_spec.py)",
        )]

    cache = json.loads(paths.METABASE_CACHE_FILE.read_text(encoding="utf-8"))
    if cache.get("month") != month:
        return [CheckResult(
            "F1.0", "Cache de Metabase corresponde al mes objetivo", "FAIL",
            f"el cache es para '{cache.get('month')}', se pidió '{month}' — hay que refrescarlo antes de continuar",
        )]

    freshness = cache.get("freshness", {})
    results = []
    for check_id, label, table, fail_status, _date_column in _CHECKS:
        entry = freshness.get(check_id)
        if entry is None:
            results.append(CheckResult(check_id, label, fail_status,
                                        f"falta en el cache de freshness ({table}) — no se corrió esa query MBQL"))
            continue
        n = int(entry.get("n") or 0)
        status = "PASS" if n > 0 else fail_status
        results.append(CheckResult(check_id, label, status,
                                    f"filas del mes: {n} (max visto en la tabla: {entry.get('max_date')})"))
    results.append(_check_query_shapes(cache))
    return results


def _check_query_shapes(cache: dict) -> CheckResult:
    """F1.14 — versión ACOTADA de validación de forma (hallazgo #5, 2026-07-14). Por
    diseño NO conoce el schema de columnas de cada una de las ~20 queries (eso quedó
    documentado como pendiente real — ver board_agent/metabase_fetch_spec.py y
    memory/project_board_agent.md, "esquema completo de las 20 queries"). Lo que SÍ
    detecta, de forma genérica (sin necesitar saber qué columnas espera cada query):
    resultados vacíos, filas que no son dicts (JSON pegado mal / tipo equivocado), o
    filas donde TODOS los campos son None/vacíos (alguien pegó un placeholder en vez del
    resultado real). No reemplaza chequear que las columnas correctas existan con los
    tipos correctos — eso requiere el trabajo completo, todavía no hecho."""
    queries = cache.get("queries", {})
    if not queries:
        return CheckResult("F1.14", "Forma de los datos del cache (chequeo acotado)", "WARN",
                            "cache['queries'] está vacío — nada que validar todavía")

    empty, malformed, blank = [], [], []
    for label, rows in queries.items():
        if not isinstance(rows, list):
            malformed.append(label)
            continue
        if not rows:
            empty.append(label)
            continue
        if not all(isinstance(r, dict) for r in rows):
            malformed.append(label)
            continue
        if not any(v not in (None, "", []) for r in rows for v in r.values()):
            blank.append(label)

    if malformed:
        return CheckResult("F1.14", "Forma de los datos del cache (chequeo acotado)", "FAIL",
                            f"{len(malformed)} quer{'y' if len(malformed) == 1 else 'ies'} con filas mal "
                            f"formadas (no son una lista de objetos): {sorted(malformed)}")
    if blank:
        return CheckResult("F1.14", "Forma de los datos del cache (chequeo acotado)", "WARN",
                            f"{len(blank)} quer{'y' if len(blank) == 1 else 'ies'} con filas donde TODOS "
                            f"los campos están vacíos/None — revisar si es un placeholder pegado por "
                            f"error: {sorted(blank)}")
    if empty:
        return CheckResult("F1.14", "Forma de los datos del cache (chequeo acotado)", "WARN",
                            f"{len(empty)} quer{'y' if len(empty) == 1 else 'ies'} con 0 filas: {sorted(empty)}")
    return CheckResult("F1.14", "Forma de los datos del cache (chequeo acotado)", "PASS",
                        f"{len(queries)} quer{'y' if len(queries) == 1 else 'ies'} verificadas: sin filas "
                        "vacías, mal formadas, ni completamente en blanco")
