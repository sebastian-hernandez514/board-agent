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
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)  # _check_pnl_actual busca pnl_override.yaml acá
    return tmp_path


def _seed_all_pass(tmp_path, month=MONTH):
    _write_csv(tmp_path / "pnl_actual.csv", ["Date", "Category", "Type", "Technical Team", "sum Amount USD"],
               [{"Date": "5/31/2026", "Category": "x", "Type": "y", "Technical Team": "z", "sum Amount USD": "100"}])
    _write_yaml(tmp_path / "ceo.yaml", {"ceo_title": "CEO Highlights", "highlights": ["a"], "lowlights": ["b"]})
    _write_yaml(tmp_path / "discussion_topics.yaml", {"topics": [{"title_plain": "Topic real"}]})
    _write_yaml(tmp_path / "arr_walk.yaml", {"products": [{"id": "core", "asks": ["x"]}], "alanube_insight": "algo"})


def _by_id(results):
    return {r.id: r for r in results}


def test_gate_all_pass(isolated_paths):
    _seed_all_pass(isolated_paths)
    results = _by_id(phase0_gate.run(MONTH))
    for rid in ("F0.4", "F0.5", "F0.6", "F0.7"):
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


def test_pnl_no_csv_no_override_fails(isolated_paths):
    _seed_all_pass(isolated_paths)
    _write_csv(isolated_paths / "pnl_actual.csv", ["Date", "Category", "Type", "Technical Team", "sum Amount USD"],
               [{"Date": "3/31/2026", "Category": "x", "Type": "y", "Technical Team": "z", "sum Amount USD": "100"}])
    results = _by_id(phase0_gate.run(MONTH))
    assert results["F0.4"].status == "FAIL"


def test_ceo_yaml_empty_lowlights_warns(isolated_paths):
    _seed_all_pass(isolated_paths)
    _write_yaml(isolated_paths / "ceo.yaml", {"ceo_title": "CEO Highlights", "highlights": ["a"], "lowlights": []})
    results = _by_id(phase0_gate.run(MONTH))
    assert results["F0.5"].status == "WARN"


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
