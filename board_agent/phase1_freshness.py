"""Fase 1 — Data Freshness Check.

Verifica que las fuentes automáticas (Redshift) estén accesibles y tengan
datos del mes objetivo. Reusa redshift_guard.py (regla del proyecto: nunca
consultar RS por fuera de ese módulo).
"""

import subprocess
import sys
import time

from . import paths
from .report import CheckResult

sys.path.insert(0, str(paths.REDSHIFT_GUARD_MODULE_DIR))

# Backoff ante "too many connections" (nos pasó en vivo el 2026-07-03, ver
# memory/project_board_agent.md) — otros errores (SQL inválido, tabla inexistente, etc.)
# no se reintentan, fallan de una.
_RETRY_BACKOFF_S = [5, 15, 30]


def _check_sso() -> CheckResult:
    try:
        proc = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--profile", paths.AWS_PROFILE],
            capture_output=True, text=True, timeout=15,
        )
    except FileNotFoundError:
        return CheckResult("F1.0", "AWS CLI disponible", "FAIL", "comando 'aws' no encontrado en PATH")
    if proc.returncode == 0:
        return CheckResult("F1.0", "Sesión SSO activa (perfil alegra)", "PASS", "")
    return CheckResult("F1.0", "Sesión SSO activa (perfil alegra)", "FAIL",
                        "correr: aws sso login --profile alegra")


def _run_sql(database: str, cluster: str, db_user: str, sql: str):
    from redshift_guard import fetch_results, run_query

    def _attempt():
        result = run_query(sql=sql, database=database, cluster_identifier=cluster, db_user=db_user)
        if result["status"] != "executed":
            raise RuntimeError(f"query no se ejecutó: {result}")
        rows = fetch_results(result["statement_id"])
        if not rows:
            raise RuntimeError("query devolvió 0 filas")
        return rows[0]

    last_error = None
    for wait_s in [0] + _RETRY_BACKOFF_S:
        if wait_s:
            print(f"  ⏳ reintentando en {wait_s}s ({last_error})…")
            time.sleep(wait_s)
        try:
            return _attempt()
        except Exception as e:
            last_error = e
            if "too many connections" not in str(e).lower():
                raise  # no es un error transitorio de conexión — no tiene sentido reintentar
    raise last_error


def _check_table(check_id: str, label: str, database: str, cluster: str, db_user: str,
                  date_col: str, table: str, month: str, fail_status: str = "FAIL") -> CheckResult:
    """Verifica presencia EXACTA del mes objetivo (no solo que MAX >= mes) — la tabla puede
    ya tener filas de meses posteriores (snapshot corriente) sin que el mes objetivo esté completo.
    """
    target = f"{month}-01"
    sql = (
        f"SELECT COUNT(*) AS n, MAX({date_col}) AS max_seen "
        f"FROM {table} WHERE {date_col} = DATE '{target}'"
    )
    try:
        row = _run_sql(database, cluster, db_user, sql)
    except Exception as e:
        return CheckResult(check_id, label, "FAIL", f"error de conexión/query: {e}")
    n = int(row.get("n") or 0)
    status = "PASS" if n > 0 else fail_status
    return CheckResult(check_id, label, status, f"filas de {target}: {n} (max_seen en la tabla: {row.get('max_seen')})")


def run(month: str) -> list[CheckResult]:
    """month en formato 'YYYY-MM'."""
    results = [_check_sso()]
    if results[0].status == "FAIL":
        # Sin SSO ninguna query de RS va a funcionar — no tiene sentido intentarlas.
        results.append(CheckResult("F1.x", "Checks de Redshift", "SKIP", "SSO inactivo, ver F1.0"))
        return results

    results.append(_check_table(
        "F1.1", "fact_customers_mrr tiene el mes objetivo",
        paths.RS_DATABASE, paths.RS_CLUSTER, paths.RS_DB_USER,
        "date_month", "dwh_facts.fact_customers_mrr", month,
    ))
    results.append(_check_table(
        "F1.2", "bi_customer_monthly_status tiene el mes objetivo (cluster-1)",
        paths.RS_DATABASE_1, paths.RS_CLUSTER_1, paths.RS_DB_USER_1,
        "date_month", "dm_retention.bi_customer_monthly_status", month,
    ))
    results.append(_check_table(
        "F1.3", "fact_cac_version_segments tiene el mes objetivo",
        paths.RS_DATABASE, paths.RS_CLUSTER, paths.RS_DB_USER,
        "cohortmonth", "db_finance.fact_cac_version_segments", month,
        fail_status="WARN",  # Finance a veces tarda — no es blocker duro (AGENT_ARCHITECTURE.md)
    ))
    results.append(_check_table(
        "F1.4", "accountant_master_table tiene el mes objetivo",
        paths.RS_DATABASE, paths.RS_CLUSTER, paths.RS_DB_USER,
        "date_month", "bi_accountant.accountant_master_table", month,
    ))
    results.append(_check_table(
        "F1.5", "tb_trm_banrep (FX) tiene el mes objetivo",
        paths.RS_DATABASE, paths.RS_CLUSTER, paths.RS_DB_USER,
        "month", "dwh_dimensions.tb_trm_banrep", month,
    ))
    return results
