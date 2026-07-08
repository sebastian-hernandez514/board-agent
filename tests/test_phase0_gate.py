import calendar
import csv

import pytest
import yaml

from board_agent import paths, phase0_gate

MONTH = "2026-05"


def _write_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True)


def _write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow(r)


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """Redirige todas las rutas que lee phase0_gate.py a un directorio temporal —
    ninguno de estos tests toca los archivos reales de Template Board."""
    monkeypatch.setattr(paths, "PNL_ACTUAL_CSV", tmp_path / "pnl_actual.csv")
    monkeypatch.setattr(paths, "CEO_YAML", tmp_path / "ceo.yaml")
    monkeypatch.setattr(paths, "DISCUSSION_TOPICS_YAML", tmp_path / "discussion_topics.yaml")
    monkeypatch.setattr(paths, "ARR_WALK_YAML", tmp_path / "arr_walk.yaml")
    monkeypatch.setattr(paths, "CONFIG_YAML", tmp_path / "config.yaml")
    monkeypatch.setattr(paths, "FINANCIAL_PERFORMANCE_TEMPLATE", tmp_path / "4_financial_performance.j2")
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)  # _check_pnl_actual busca pnl_override.yaml acá
    return tmp_path


def _seed_all_pass(tmp_path, month=MONTH):
    _write_csv(tmp_path / "pnl_actual.csv", ["Date", "Category", "Type", "Technical Team", "sum Amount USD"],
               [{"Date": "5/31/2026", "Category": "x", "Type": "y", "Technical Team": "z", "sum Amount USD": "100"}])
    _write_yaml(tmp_path / "ceo.yaml", {"ceo_title": "CEO Highlights", "highlights": ["a"], "lowlights": ["b"]})
    _write_yaml(tmp_path / "discussion_topics.yaml", {"topics": [{"title_plain": "Topic real"}]})
    _write_yaml(tmp_path / "arr_walk.yaml", {"products": [{"id": "core", "asks": ["x"]}], "alanube_insight": "algo"})
    y, m = month.split("-")
    month_name_en = calendar.month_name[int(m)]
    _write_yaml(tmp_path / "config.yaml", {"period": month, "month_label": f"{month_name_en} {y}"})
    (tmp_path / "4_financial_performance.j2").write_text(
        f"<title>Alegra Board — Financial Performance · {month_name_en} {y}</title>", encoding="utf-8"
    )


def _by_id(results):
    return {r.id: r for r in results}


def test_gate_all_pass(isolated_paths):
    _seed_all_pass(isolated_paths)
    results = _by_id(phase0_gate.run(MONTH))
    for rid in ("F0.4", "F0.5", "F0.6", "F0.7", "F0.8", "F0.9"):
        assert results[rid].status == "PASS", f"{rid}: {results[rid].detail}"


def test_pnl_override_fallback_passes(isolated_paths):
    """Reproduce el caso real: CSV viejo, pero pnl_override.yaml tiene el mes — debe dar PASS."""
    _seed_all_pass(isolated_paths)
    _write_csv(isolated_paths / "pnl_actual.csv", ["Date", "Category", "Type", "Technical Team", "sum Amount USD"],
               [{"Date": "3/31/2026", "Category": "x", "Type": "y", "Technical Team": "z", "sum Amount USD": "100"}])
    _write_yaml(isolated_paths / "pnl_override.yaml", {MONTH: {"net_revenue": "$2.4M"}})
    results = _by_id(phase0_gate.run(MONTH))
    assert results["F0.4"].status == "PASS"
    assert "override" in results["F0.4"].detail


def test_pnl_no_csv_no_override_warns_not_fails(isolated_paths):
    """Cambiado 2026-07-08: el P&L sin datos ya no bloquea todo el flujo (ver decisión en
    phase0_gate.py) — el freno real ahora es R17 del Validator, con el board ya armado."""
    _seed_all_pass(isolated_paths)
    _write_csv(isolated_paths / "pnl_actual.csv", ["Date", "Category", "Type", "Technical Team", "sum Amount USD"],
               [{"Date": "3/31/2026", "Category": "x", "Type": "y", "Technical Team": "z", "sum Amount USD": "100"}])
    results = _by_id(phase0_gate.run(MONTH))
    assert results["F0.4"].status == "WARN"


def test_ceo_yaml_empty_lowlights_warns(isolated_paths):
    _seed_all_pass(isolated_paths)
    _write_yaml(isolated_paths / "ceo.yaml", {"ceo_title": "CEO Highlights", "highlights": ["a"], "lowlights": []})
    results = _by_id(phase0_gate.run(MONTH))
    assert results["F0.5"].status == "WARN"


def test_ceo_yaml_warns_when_content_is_for_a_different_month(isolated_paths):
    """Reproduce el falso PASS encontrado 2026-07-08 simulando el flujo de junio-26: el YAML
    real tenía texto de mayo, no vacío, sin placeholders — y F0.5 pasaba igual. Con el campo
    'updated_for_month' presente y distinto del mes objetivo, ahora debe dar WARN."""
    _seed_all_pass(isolated_paths)
    _write_yaml(isolated_paths / "ceo.yaml", {
        "ceo_title": "CEO Highlights", "highlights": ["a"], "lowlights": ["b"],
        "updated_for_month": "2026-04",
    })
    results = _by_id(phase0_gate.run(MONTH))  # MONTH = "2026-05"
    r = results["F0.5"]
    assert r.status == "WARN"
    assert "2026-04" in r.detail and "2026-05" in r.detail


def test_ceo_yaml_passes_when_updated_for_month_matches(isolated_paths):
    _seed_all_pass(isolated_paths)
    _write_yaml(isolated_paths / "ceo.yaml", {
        "ceo_title": "CEO Highlights", "highlights": ["a"], "lowlights": ["b"],
        "updated_for_month": MONTH,
    })
    results = _by_id(phase0_gate.run(MONTH))
    assert results["F0.5"].status == "PASS"
    assert "sin campo" not in results["F0.5"].detail


def test_ceo_yaml_pass_notes_month_unverified_when_field_missing(isolated_paths):
    """Comportamiento hacia atrás: el ceo.yaml real de hoy no tiene 'updated_for_month' — debe
    seguir dando PASS (no romper nada existente), pero el detail debe decir honestamente que
    no se pudo verificar el mes, no fingir certeza como antes."""
    _seed_all_pass(isolated_paths)
    results = _by_id(phase0_gate.run(MONTH))
    r = results["F0.5"]
    assert r.status == "PASS"
    assert "sin campo 'updated_for_month'" in r.detail


def test_discussion_topics_placeholder_warns(isolated_paths):
    _seed_all_pass(isolated_paths)
    _write_yaml(isolated_paths / "discussion_topics.yaml",
                {"topics": [{"title_plain": "Discussion Topic (Por definir)"}]})
    results = _by_id(phase0_gate.run(MONTH))
    assert results["F0.6"].status == "WARN"


def test_arr_walk_empty_asks_warns(isolated_paths):
    _seed_all_pass(isolated_paths)
    _write_yaml(isolated_paths / "arr_walk.yaml",
                {"products": [{"id": "core", "asks": []}], "alanube_insight": "algo"})
    results = _by_id(phase0_gate.run(MONTH))
    assert results["F0.7"].status == "WARN"


def test_discussion_topics_pass_includes_dead_scaffold_caveat(isolated_paths):
    """F0.6 solo revisa el scaffold desconectado — el PASS debe dejarlo explícito, no fingir
    que valida el contenido real de 2_discussion_topic.j2."""
    _seed_all_pass(isolated_paths)
    results = _by_id(phase0_gate.run(MONTH))
    r = results["F0.6"]
    assert r.status == "PASS"
    assert "desconectado" in r.detail


def test_config_month_fails_when_config_still_has_previous_month(isolated_paths):
    """Reproduce el bug real reportado por el usuario: corrió run.py --month 2026-06 pero
    config.yaml seguía en period: '2026-05' — varias slides del board mostraron 'May' en vez
    de 'June'. F0.8 debe bloquear (FAIL), no solo avisar."""
    _seed_all_pass(isolated_paths, month="2026-05")
    results = _by_id(phase0_gate.run("2026-06"))
    r = results["F0.8"]
    assert r.status == "FAIL"
    assert "2026-05" in r.detail and "2026-06" in r.detail


def test_config_month_passes_when_period_matches(isolated_paths):
    _seed_all_pass(isolated_paths, month="2026-06")
    results = _by_id(phase0_gate.run("2026-06"))
    assert results["F0.8"].status == "PASS"


def test_financial_performance_month_warns_when_title_is_stale(isolated_paths):
    """Reproduce el otro síntoma real reportado: el HTML de Finance (Template 4) sigue con el
    <title> del mes anterior porque Sofía todavía no mandó el del mes nuevo."""
    _seed_all_pass(isolated_paths, month="2026-06")
    (isolated_paths / "4_financial_performance.j2").write_text(
        "<title>Alegra Board — Financial Performance · May 2026</title>", encoding="utf-8"
    )
    results = _by_id(phase0_gate.run("2026-06"))
    r = results["F0.9"]
    assert r.status == "WARN"
    assert "May 2026" in r.detail and "2026-06" in r.detail


def test_financial_performance_month_passes_when_title_matches(isolated_paths):
    _seed_all_pass(isolated_paths, month="2026-06")
    results = _by_id(phase0_gate.run("2026-06"))
    assert results["F0.9"].status == "PASS"


def test_financial_performance_month_skips_when_title_pattern_missing(isolated_paths):
    _seed_all_pass(isolated_paths)
    (isolated_paths / "4_financial_performance.j2").write_text(
        "<title>Alegra Board</title>", encoding="utf-8"
    )
    results = _by_id(phase0_gate.run(MONTH))
    assert results["F0.9"].status == "SKIP"


def test_financial_performance_month_skips_when_file_missing(isolated_paths):
    _seed_all_pass(isolated_paths)
    (isolated_paths / "4_financial_performance.j2").unlink()
    results = _by_id(phase0_gate.run(MONTH))
    assert results["F0.9"].status == "SKIP"
