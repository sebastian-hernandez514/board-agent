import yaml
import pytest

from board_agent import paths, phase5_diff as f5


def _base_metrics(**overrides):
    m = {
        "cutoff_month": "2026-05",
        "is_quarter_end": False,
        "arr_mom": "-0.1%",
        "arr_qoq": "2.0%",
        "new_logos_yoy": "10.0%",
        "arr_walk_table": {
            "sections": [
                {"rows": [
                    {"label": "Total EoP", "cells": ["55.0", "58.0", "59.0"]},
                    {"label": "Logo Monthly Churn %", "cells": ["3.5", "3.8", "4.2"]},
                ]},
                {"rows": [
                    {"label": "ARR BoP", "cells": ["27.0", "27.5", "28.2"]},
                    {"label": "(+/−) FX Impact", "cells": ["0.1", "0.2", "-0.5"]},
                ]},
            ]
        },
    }
    m.update(overrides)
    return m


@pytest.fixture
def metrics_file(tmp_path):
    def _write(metrics):
        p = tmp_path / "metrics.yaml"
        p.write_text(yaml.safe_dump(metrics), encoding="utf-8")
        return p
    return _write


@pytest.fixture
def isolated_boards_dir(tmp_path, monkeypatch):
    boards_dir = tmp_path / "boards"
    monkeypatch.setattr(paths, "BOARDS_DIR", boards_dir)
    return boards_dir


def _find(results, rid):
    return next(r for r in results if r.id == rid)


def test_d1_arr_mom_pass_within_threshold(metrics_file, isolated_boards_dir):
    p = metrics_file(_base_metrics(arr_mom="-0.1%"))
    results = f5.run(metrics_path=p)
    assert _find(results, "D1").status == "PASS"


def test_d1_arr_mom_warn_beyond_threshold(metrics_file, isolated_boards_dir):
    p = metrics_file(_base_metrics(arr_mom="7.5%"))
    results = f5.run(metrics_path=p)
    assert _find(results, "D1").status == "WARN"


def test_d1_uses_qoq_field_on_quarter_end(metrics_file, isolated_boards_dir):
    p = metrics_file(_base_metrics(is_quarter_end=True, arr_qoq="9.0%", arr_mom="0.0%"))
    results = f5.run(metrics_path=p)
    r = _find(results, "D1")
    assert r.status == "WARN"
    assert "arr_qoq" in r.detail


def test_d2_logos_eop_variation(metrics_file, isolated_boards_dir):
    p = metrics_file(_base_metrics())
    results = f5.run(metrics_path=p)
    r = _find(results, "D2")
    # 58 -> 59 = +1.72%, dentro del umbral de 3%
    assert r.status == "PASS"


def test_d2_logos_eop_warn(metrics_file, isolated_boards_dir):
    m = _base_metrics()
    m["arr_walk_table"]["sections"][0]["rows"][0]["cells"] = ["55.0", "58.0", "65.0"]
    p = metrics_file(m)
    results = f5.run(metrics_path=p)
    assert _find(results, "D2").status == "WARN"


def test_d3_churn_rate_pp_delta(metrics_file, isolated_boards_dir):
    p = metrics_file(_base_metrics())
    results = f5.run(metrics_path=p)
    # 3.8 -> 4.2 = +0.4pp, dentro de 1pp
    assert _find(results, "D3").status == "PASS"


def test_d4_new_logos_yoy_warn(metrics_file, isolated_boards_dir):
    p = metrics_file(_base_metrics(new_logos_yoy="45.0%"))
    results = f5.run(metrics_path=p)
    assert _find(results, "D4").status == "WARN"


def test_d5_fx_impact_within_threshold(metrics_file, isolated_boards_dir):
    p = metrics_file(_base_metrics())
    results = f5.run(metrics_path=p)
    # -0.5 sin sufijo -> parse_money_cell interpreta como $ -500,000 (millones) -> abs < 2M
    assert _find(results, "D5").status == "PASS"


def test_d5_fx_impact_warn_when_large(metrics_file, isolated_boards_dir):
    m = _base_metrics()
    m["arr_walk_table"]["sections"][1]["rows"][1]["cells"] = ["0.1", "0.2", "-3.5"]
    p = metrics_file(m)
    results = f5.run(metrics_path=p)
    assert _find(results, "D5").status == "WARN"


def test_d6_version_suggestion_empty_dir(metrics_file, isolated_boards_dir):
    p = metrics_file(_base_metrics())
    results = f5.run(metrics_path=p)
    r = _find(results, "D6")
    assert r.status == "PASS"
    assert "v1" in r.detail


def test_d6_version_suggestion_numeric_not_alpha_sort(metrics_file, isolated_boards_dir):
    board_dir = isolated_boards_dir / "2026-05"
    board_dir.mkdir(parents=True)
    for n in (1, 2, 9, 41):
        (board_dir / f"board_May_2026_v{n}.html").write_text("x")
    p = metrics_file(_base_metrics())
    results = f5.run(metrics_path=p)
    assert "v42" in _find(results, "D6").detail


def test_d7_skip_when_no_previous_board(metrics_file, isolated_boards_dir):
    p = metrics_file(_base_metrics())
    results = f5.run(metrics_path=p)
    r = _find(results, "D7")
    assert r.status == "SKIP"


def _slide(page_num, body="contenido"):
    return f'<div class="slide"><p>{body}</p><span class="footer-page">{page_num}</span></div>'


def test_d7_detects_changed_slides(metrics_file, isolated_boards_dir, monkeypatch, tmp_path):
    prev_dir = isolated_boards_dir / "2026-05"
    prev_dir.mkdir(parents=True)
    prev_html = _slide(1, "Slide uno viejo") + _slide(2, "Slide dos — no cambia") + _slide(3, "Slide tres viejo")
    (prev_dir / "board_May_2026_v1.html").write_text(prev_html, encoding="utf-8")

    standalone = tmp_path / "board_standalone.html"
    new_html = _slide(1, "Slide uno NUEVO") + _slide(2, "Slide dos — no cambia") + _slide(3, "Slide tres NUEVO")
    standalone.write_text(new_html, encoding="utf-8")
    monkeypatch.setattr(paths, "BOARD_STANDALONE_HTML", standalone)

    p = metrics_file(_base_metrics())
    results = f5.run(metrics_path=p)
    r = _find(results, "D7")
    assert r.status == "PASS"
    assert "2/3 cambiaron: [1, 3]" in r.detail
    assert "board_May_2026_v1.html" in r.detail


def test_d7_falls_back_to_previous_month_if_current_month_has_no_versions(monkeypatch, tmp_path, metrics_file, isolated_boards_dir):
    prev_month_dir = isolated_boards_dir / "2026-04"
    prev_month_dir.mkdir(parents=True)
    (prev_month_dir / "board_Apr_2026_v3.html").write_text(_slide(1, "abril"), encoding="utf-8")

    standalone = tmp_path / "board_standalone.html"
    standalone.write_text(_slide(1, "mayo"), encoding="utf-8")
    monkeypatch.setattr(paths, "BOARD_STANDALONE_HTML", standalone)

    p = metrics_file(_base_metrics())
    results = f5.run(metrics_path=p)
    r = _find(results, "D7")
    assert r.status == "PASS"
    assert "board_Apr_2026_v3.html" in r.detail


def test_d7_ignores_whitespace_only_differences(monkeypatch, tmp_path, metrics_file, isolated_boards_dir):
    prev_dir = isolated_boards_dir / "2026-05"
    prev_dir.mkdir(parents=True)
    (prev_dir / "board_May_2026_v1.html").write_text(_slide(1, "mismo contenido"), encoding="utf-8")

    standalone = tmp_path / "board_standalone.html"
    standalone.write_text('<div class="slide">\n\n  <p>mismo   contenido</p>\n  <span class="footer-page">1</span></div>', encoding="utf-8")
    monkeypatch.setattr(paths, "BOARD_STANDALONE_HTML", standalone)

    p = metrics_file(_base_metrics())
    results = f5.run(metrics_path=p)
    r = _find(results, "D7")
    assert "0/1 cambiaron" in r.detail


def test_missing_field_produces_skip_not_crash(metrics_file, isolated_boards_dir):
    m = _base_metrics()
    del m["new_logos_yoy"]
    p = metrics_file(m)
    results = f5.run(metrics_path=p)
    assert _find(results, "D4").status == "SKIP"
    # el resto de las reglas no deberían verse afectadas por este campo faltante
    assert _find(results, "D1").status == "PASS"


def test_run_returns_all_seven_checks(metrics_file, isolated_boards_dir):
    p = metrics_file(_base_metrics())
    results = f5.run(metrics_path=p)
    ids = [r.id for r in results]
    assert ids == ["D1", "D2", "D3", "D4", "D5", "D6", "D7"]
