import json

from board_agent import paths
from board_agent import phase1_freshness as f1

_ALL_CHECK_IDS = [c[0] for c in f1._CHECKS]


def _write_cache(tmp_path, monkeypatch, month="2026-05", freshness=None, queries=None):
    cache_file = tmp_path / ".metabase_cache.json"
    monkeypatch.setattr(paths, "METABASE_CACHE_FILE", cache_file)
    cache_file.write_text(json.dumps({"month": month, "freshness": freshness or {}, "queries": queries or {}}),
                           encoding="utf-8")
    return cache_file


def _full_freshness(n=5, max_date="2026-05-01"):
    return {check_id: {"n": n, "max_date": max_date} for check_id in _ALL_CHECK_IDS}


def _well_formed_queries():
    """Cache['queries'] con forma correcta — para tests que esperan F1.14 en PASS."""
    return {"algo (una query)": [{"col_a": 1, "col_b": "x"}]}


def test_run_fails_when_cache_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "METABASE_CACHE_FILE", tmp_path / "no-existe.json")
    results = f1.run("2026-05")
    assert len(results) == 1
    assert results[0].status == "FAIL"
    assert results[0].id == "F1.0"


def test_run_fails_when_cache_is_for_a_different_month(tmp_path, monkeypatch):
    _write_cache(tmp_path, monkeypatch, month="2026-04", freshness=_full_freshness())
    results = f1.run("2026-05")
    assert len(results) == 1
    assert results[0].status == "FAIL"
    assert "2026-04" in results[0].detail and "2026-05" in results[0].detail


def test_run_full_pass(tmp_path, monkeypatch):
    _write_cache(tmp_path, monkeypatch, month="2026-05", freshness=_full_freshness(),
                 queries=_well_formed_queries())
    results = f1.run("2026-05")
    assert len(results) == 14
    ids = [r.id for r in results]
    assert ids == ["F1.1", "F1.2", "F1.3", "F1.4", "F1.5", "F1.6", "F1.7",
                   "F1.8", "F1.9", "F1.10", "F1.11", "F1.12", "F1.13", "F1.14"]
    assert all(r.status == "PASS" for r in results)


def test_missing_check_uses_its_fail_status(tmp_path, monkeypatch):
    freshness = _full_freshness()
    del freshness["F1.1"]  # FAIL-severity check
    del freshness["F1.6"]  # WARN-severity check
    _write_cache(tmp_path, monkeypatch, freshness=freshness)
    results = {r.id: r for r in f1.run("2026-05")}
    assert results["F1.1"].status == "FAIL"
    assert results["F1.6"].status == "WARN"


def test_zero_rows_uses_its_fail_status(tmp_path, monkeypatch):
    freshness = _full_freshness()
    freshness["F1.4"] = {"n": 0, "max_date": "2026-04-01"}   # FAIL-severity check
    freshness["F1.7"] = {"n": 0, "max_date": "2026-04-01"}   # WARN-severity check
    _write_cache(tmp_path, monkeypatch, freshness=freshness)
    results = {r.id: r for r in f1.run("2026-05")}
    assert results["F1.4"].status == "FAIL"
    assert results["F1.7"].status == "WARN"


def test_detail_reports_row_count_and_max_date(tmp_path, monkeypatch):
    _write_cache(tmp_path, monkeypatch, freshness=_full_freshness(n=42, max_date="2026-05-30"))
    results = {r.id: r for r in f1.run("2026-05")}
    assert "42" in results["F1.1"].detail
    assert "2026-05-30" in results["F1.1"].detail


# ── F1.14 — chequeo acotado de forma de los datos (hallazgo #5, 2026-07-14) ──────────────
# NO valida columnas/tipos por query (eso es el trabajo completo, todavía pendiente — ver
# board_agent/metabase_fetch_spec.py). Solo detecta: vacío, filas que no son dicts, y filas
# donde TODOS los campos son None/vacíos.

def test_f1_14_passes_with_no_queries_block_at_all(tmp_path, monkeypatch):
    """Cache sin 'queries' (ej. solo se pobló freshness todavía) — no hay nada que
    validar, no debe bloquear con FAIL."""
    _write_cache(tmp_path, monkeypatch, freshness=_full_freshness())
    results = {r.id: r for r in f1.run("2026-05")}
    assert results["F1.14"].status == "WARN"
    assert "vacío" in results["F1.14"].detail


def test_f1_14_warns_on_empty_query_result(tmp_path, monkeypatch):
    _write_cache(tmp_path, monkeypatch, freshness=_full_freshness(),
                 queries={**_well_formed_queries(), "SC value events mensuales (amplitude)": []})
    results = {r.id: r for r in f1.run("2026-05")}
    assert results["F1.14"].status == "WARN"
    assert "SC value events mensuales (amplitude)" in results["F1.14"].detail


def test_f1_14_warns_on_all_blank_rows(tmp_path, monkeypatch):
    """Simula un placeholder pegado por error — filas presentes pero todo en None."""
    _write_cache(tmp_path, monkeypatch, freshness=_full_freshness(),
                 queries={**_well_formed_queries(), "Payback (bi_strategic.payback_cohort_results)":
                          [{"dimension": None, "cohort_month": None, "pb_base": None}]})
    results = {r.id: r for r in f1.run("2026-05")}
    assert results["F1.14"].status == "WARN"
    assert "Payback (bi_strategic.payback_cohort_results)" in results["F1.14"].detail


def test_f1_14_fails_on_malformed_rows(tmp_path, monkeypatch):
    """Filas que no son objetos (ej. alguien pegó el JSON mal, quedó una lista de strings)."""
    _write_cache(tmp_path, monkeypatch, freshness=_full_freshness(),
                 queries={**_well_formed_queries(), "logos consolidados": ["esto no es un dict"]})
    results = {r.id: r for r in f1.run("2026-05")}
    assert results["F1.14"].status == "FAIL"
    assert "logos consolidados" in results["F1.14"].detail
