import subprocess
import sys
import types

import pytest

from board_agent import phase1_freshness as f1


class _FakeCompletedProcess:
    def __init__(self, returncode):
        self.returncode = returncode


@pytest.fixture
def fake_redshift_guard(monkeypatch):
    """Instala un módulo falso 'redshift_guard' en sys.modules — phase1_freshness lo importa
    de forma diferida (`from redshift_guard import ...` dentro de _run_sql), así que basta con
    reemplazar el módulo antes de llamar run()/_run_sql()."""
    fake = types.ModuleType("redshift_guard")
    calls = {"run_query": [], "fetch_results": []}

    def run_query(sql, database, cluster_identifier, db_user):
        calls["run_query"].append(sql)
        return {"status": "executed", "statement_id": "fake-id"}

    def fetch_results(statement_id):
        calls["fetch_results"].append(statement_id)
        return [{"n": 5, "max_seen": "2026-05-01"}]

    fake.run_query = run_query
    fake.fetch_results = fetch_results
    monkeypatch.setitem(sys.modules, "redshift_guard", fake)
    return fake, calls


def test_check_sso_pass(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0))
    r = f1._check_sso()
    assert r.status == "PASS"


def test_check_sso_fail_nonzero_exit(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(1))
    r = f1._check_sso()
    assert r.status == "FAIL"
    assert "sso login" in r.detail


def test_check_sso_fail_aws_cli_missing(monkeypatch):
    def _raise(*a, **k):
        raise FileNotFoundError()
    monkeypatch.setattr(subprocess, "run", _raise)
    r = f1._check_sso()
    assert r.status == "FAIL"
    assert "aws" in r.detail


def test_run_sql_success(fake_redshift_guard):
    row = f1._run_sql("db", "cluster", "user", "SELECT 1")
    assert row == {"n": 5, "max_seen": "2026-05-01"}


def test_run_sql_retries_on_too_many_connections(monkeypatch, fake_redshift_guard):
    fake, calls = fake_redshift_guard
    attempts = {"n": 0}

    def flaky_run_query(sql, database, cluster_identifier, db_user):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("FATAL: too many connections for role")
        return {"status": "executed", "statement_id": "fake-id"}

    fake.run_query = flaky_run_query
    monkeypatch.setattr(f1.time, "sleep", lambda s: None)  # no esperar de verdad en el test

    row = f1._run_sql("db", "cluster", "user", "SELECT 1")
    assert attempts["n"] == 3
    assert row == {"n": 5, "max_seen": "2026-05-01"}


def test_run_sql_does_not_retry_other_errors(monkeypatch, fake_redshift_guard):
    fake, calls = fake_redshift_guard
    attempts = {"n": 0}

    def bad_run_query(sql, database, cluster_identifier, db_user):
        attempts["n"] += 1
        raise RuntimeError("syntax error at or near SELEKT")

    fake.run_query = bad_run_query
    monkeypatch.setattr(f1.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="syntax error"):
        f1._run_sql("db", "cluster", "user", "SELECT 1")
    assert attempts["n"] == 1  # no reintentó — no es un error transitorio de conexión


def test_check_table_pass(fake_redshift_guard):
    r = f1._check_table("F1.1", "tabla tiene el mes", "db", "cluster", "user",
                         "date_month", "schema.tabla", "2026-05")
    assert r.status == "PASS"
    assert "filas de 2026-05-01: 5" in r.detail


def test_check_table_fail_zero_rows(monkeypatch, fake_redshift_guard):
    fake, calls = fake_redshift_guard
    fake.fetch_results = lambda sid: [{"n": 0, "max_seen": "2026-04-01"}]
    r = f1._check_table("F1.1", "tabla tiene el mes", "db", "cluster", "user",
                         "date_month", "schema.tabla", "2026-05")
    assert r.status == "FAIL"


def test_check_table_custom_fail_status_is_warn(monkeypatch, fake_redshift_guard):
    fake, calls = fake_redshift_guard
    fake.fetch_results = lambda sid: [{"n": 0, "max_seen": "2026-04-01"}]
    r = f1._check_table("F1.3", "Finance a veces tarda", "db", "cluster", "user",
                         "cohortmonth", "db_finance.fact_cac_version_segments", "2026-05",
                         fail_status="WARN")
    assert r.status == "WARN"


def test_check_table_connection_error_is_fail(monkeypatch, fake_redshift_guard):
    fake, calls = fake_redshift_guard

    def raise_query(sql, database, cluster_identifier, db_user):
        raise RuntimeError("connection refused")
    fake.run_query = raise_query
    monkeypatch.setattr(f1.time, "sleep", lambda s: None)

    r = f1._check_table("F1.1", "tabla tiene el mes", "db", "cluster", "user",
                         "date_month", "schema.tabla", "2026-05")
    assert r.status == "FAIL"
    assert "error de conexión" in r.detail


def test_run_skips_rs_checks_when_sso_fails(monkeypatch):
    monkeypatch.setattr(f1, "_check_sso", lambda: __import__("board_agent.report", fromlist=["CheckResult"]).CheckResult("F1.0", "SSO", "FAIL", "sin sesión"))
    results = f1.run("2026-05")
    assert len(results) == 2
    assert results[0].status == "FAIL"
    assert results[1].status == "SKIP"


def test_run_full_pass(fake_redshift_guard, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0))
    results = f1.run("2026-05")
    # SSO + 13 checks de tabla (F1.1-F1.13, ampliado 2026-07-08)
    assert len(results) == 14
    assert results[0].id == "F1.0"
    ids = [r.id for r in results]
    assert ids == ["F1.0", "F1.1", "F1.2", "F1.3", "F1.4", "F1.5", "F1.6", "F1.7",
                   "F1.8", "F1.9", "F1.10", "F1.11", "F1.12", "F1.13"]
    assert all(r.status == "PASS" for r in results)


def test_check_table_range_pass(fake_redshift_guard):
    r = f1._check_table_range("F1.12", "tabla a nivel evento tiene el mes", "db", "cluster", "user",
                               "close_date", "schema.tabla", "2026-05")
    assert r.status == "PASS"


def test_check_table_range_warn_when_no_rows_in_month(monkeypatch, fake_redshift_guard):
    fake, calls = fake_redshift_guard
    fake.fetch_results = lambda sid: [{"n": 0, "max_seen": "2026-04-15"}]
    r = f1._check_table_range("F1.12", "tabla a nivel evento tiene el mes", "db", "cluster", "user",
                               "close_date", "schema.tabla", "2026-05")
    assert r.status == "WARN"


def test_check_table_range_uses_date_trunc_not_exact_match(fake_redshift_guard):
    """Diferencia real con _check_table: una fila del 15 del mes debe contar — si usara
    igualdad exacta contra el día 1, nunca matchearía nada en una tabla a nivel de evento."""
    fake, calls = fake_redshift_guard
    f1._check_table_range("F1.12", "x", "db", "cluster", "user",
                           "close_date", "schema.tabla", "2026-05")
    assert "DATE_TRUNC" in calls["run_query"][-1]
