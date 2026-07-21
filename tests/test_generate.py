import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import generate  # noqa: E402


@pytest.fixture
def isolated_generate(tmp_path, monkeypatch):
    templates_dir = tmp_path / "templates"
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    templates_dir.mkdir()
    data_dir.mkdir()
    (data_dir / "editorial").mkdir()
    monkeypatch.setattr(generate, "ROOT", tmp_path)
    monkeypatch.setattr(generate, "TMPL_DIR", templates_dir)
    monkeypatch.setattr(generate, "DATA_DIR", data_dir)
    monkeypatch.setattr(generate, "OUTPUT_DIR", output_dir)
    return templates_dir, data_dir, output_dir


def _write(path, content):
    path.write_text(content, encoding="utf-8")


def test_none_two_levels_deep_does_not_crash_and_gets_tracked(isolated_generate, monkeypatch, capsys):
    """Reproduce el incidente real de NPS: metrics.nps es None, el template encadena 2
    niveles más (.costa_rica_trend.name) — antes del fix esto lanzaba UndefinedError y
    tumbaba TODO el render() del archivo. Con ChainableUndefined debe renderizar en
    blanco y quedar registrado, no explotar."""
    templates_dir, data_dir, _ = isolated_generate
    _write(templates_dir / "test.j2", "<html><body>[{{ metrics.nps.costa_rica_trend.name }}]</body></html>")
    _write(data_dir / "metrics.yaml", "nps: null\n")
    monkeypatch.setattr(sys, "argv", ["generate.py", "--template", "test"])

    exit_code = generate.main()

    assert exit_code == 0
    out_html = (isolated_generate[2] / "test.html").read_text(encoding="utf-8")
    assert "[]" in out_html  # el valor faltante se imprimió en blanco, no reventó
    captured = capsys.readouterr()
    assert "MISSING_FIELDS test: costa_rica_trend" in captured.out


def test_real_syntax_error_does_not_block_other_templates(isolated_generate, monkeypatch, capsys):
    """Un error real (no de datos faltantes) en un template no debe impedir que los
    demás templates, sin relación, se regeneren igual — mismo criterio que
    phase3_html_builder.py no abortando el resto de Fase 3 ante returncode 2."""
    templates_dir, _, output_dir = isolated_generate
    _write(templates_dir / "bad.j2", "{% if true %}<html><body>sin endif</body>")
    _write(templates_dir / "good.j2", "<html><body>OK</body></html>")
    monkeypatch.setattr(sys, "argv", ["generate.py"])

    exit_code = generate.main()

    assert exit_code == 2
    assert (output_dir / "good.html").exists()
    assert not (output_dir / "bad.html").exists()
    captured = capsys.readouterr()
    assert "FALLARON: bad" in captured.out


def test_requested_template_not_found_returns_1(isolated_generate, monkeypatch, capsys):
    templates_dir, _, _ = isolated_generate
    _write(templates_dir / "real.j2", "<html></html>")
    monkeypatch.setattr(sys, "argv", ["generate.py", "--template", "no_existe"])

    exit_code = generate.main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "no_existe" in captured.out


def test_comma_separated_template_list_renders_only_those(isolated_generate, monkeypatch):
    templates_dir, _, output_dir = isolated_generate
    _write(templates_dir / "a.j2", "<html>A</html>")
    _write(templates_dir / "b.j2", "<html>B</html>")
    _write(templates_dir / "c.j2", "<html>C</html>")
    monkeypatch.setattr(sys, "argv", ["generate.py", "--template", "a,b"])

    exit_code = generate.main()

    assert exit_code == 0
    assert (output_dir / "a.html").exists()
    assert (output_dir / "b.html").exists()
    assert not (output_dir / "c.html").exists()


def test_tojson_filter_guards_against_undefined():
    assert generate._tojson(generate.Undefined()) == "null"


def test_hl_split_filter_guards_against_undefined():
    assert generate._hl_split(generate.Undefined(), "cls") == ""
