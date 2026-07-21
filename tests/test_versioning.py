import pytest

from board_agent import paths, versioning
from board_agent.report import CheckResult

MONTH = "2026-06"


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    boards_dir = tmp_path / "boards"
    historico_dir = boards_dir / "historico"
    output_html = tmp_path / "output" / "board_standalone.html"
    metrics_yaml = tmp_path / "data" / "metrics.yaml"
    pdf_script = tmp_path / "scripts" / "generate_pdf.py"

    output_html.parent.mkdir(parents=True, exist_ok=True)
    metrics_yaml.parent.mkdir(parents=True, exist_ok=True)
    pdf_script.parent.mkdir(parents=True, exist_ok=True)

    output_html.write_text("<html>board de prueba</html>", encoding="utf-8")
    metrics_yaml.write_text("cutoff_month: '2026-06'\n", encoding="utf-8")
    pdf_script.write_text(
        'HTML_FILE  = ROOT / "boards" / "2026-05" / "board_May_2026_v41.html"\n'
        'PDF_OUT    = ROOT / "boards" / "2026-05" / "board_May_2026_v41.pdf"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(paths, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(paths, "HISTORICO_DIR", historico_dir)
    monkeypatch.setattr(paths, "BOARD_STANDALONE_HTML", output_html)
    monkeypatch.setattr(paths, "METRICS_YAML", metrics_yaml)
    monkeypatch.setattr(paths, "PDF_SCRIPT", pdf_script)
    return tmp_path


def test_next_version_number_empty_dir(isolated_paths):
    assert versioning.next_version_number(MONTH) == 1


def test_next_version_number_sorts_numerically_not_alphabetically(isolated_paths):
    board_dir = paths.BOARDS_DIR / MONTH
    board_dir.mkdir(parents=True)
    for n in (1, 2, 9, 41):
        (board_dir / f"board_Jun_2026_v{n}.html").write_text("x", encoding="utf-8")
    # "v9" ordenaría después de "v41" si se comparara como texto — el caso real que
    # se encontró y corrigió el 2026-07-03 en phase5_diff.py.
    assert versioning.next_version_number(MONTH) == 42


def test_save_version_creates_expected_files(isolated_paths):
    validator_results = [CheckResult("R1", "ARR total incluye Alanube", "PASS", "ok")]
    diff_results = [CheckResult("D1", "ARR total variación", "PASS", "ok")]

    saved = versioning.save_version(MONTH, validator_results, diff_results)

    assert saved["version"] == 1
    assert saved["html"].name == "board_Jun_2026_v1.html"
    assert saved["metrics"].name == "board_Jun_2026_v1.metrics.yaml"
    assert saved["report"].name == "board_Jun_2026_v1.report.md"
    assert saved["html"].exists()
    assert saved["metrics"].exists()
    assert saved["report"].exists()

    assert saved["html"].read_text(encoding="utf-8") == "<html>board de prueba</html>"

    report_text = saved["report"].read_text(encoding="utf-8")
    assert "Board 2026-06 — v1" in report_text
    assert "R1" in report_text
    assert "D1" in report_text


def test_save_version_increments_on_second_call(isolated_paths):
    versioning.save_version(MONTH, [], [])
    second = versioning.save_version(MONTH, [], [])
    assert second["version"] == 2
    assert second["html"].name == "board_Jun_2026_v2.html"
    # La v1 no se pisa
    assert (paths.BOARDS_DIR / MONTH / "board_Jun_2026_v1.html").exists()


def test_save_version_updates_generate_pdf_targets(isolated_paths):
    versioning.save_version(MONTH, [], [])
    content = paths.PDF_SCRIPT.read_text(encoding="utf-8")
    assert 'HTML_FILE = ROOT / "boards" / "2026-06" / "board_Jun_2026_v1.html"' in content
    assert 'PDF_OUT = ROOT / "boards" / "2026-06" / "board_Jun_2026_v1.pdf"' in content
    # Los valores viejos (mayo, v41) ya no deben quedar
    assert "2026-05" not in content
    assert "v41" not in content


def test_mark_final_raises_if_no_version_exists(isolated_paths):
    with pytest.raises(RuntimeError, match="No hay ninguna versión"):
        versioning.mark_final(MONTH)


def test_mark_final_copies_latest_version_with_clean_name(isolated_paths):
    versioning.save_version(MONTH, [], [])  # v1
    versioning.save_version(MONTH, [], [])  # v2

    result = versioning.mark_final(MONTH)

    assert result["version"] == 2
    assert result["html"] == paths.HISTORICO_DIR / "board_Jun_2026.html"
    assert result["html"].exists()
    assert result["metrics"].exists()
    assert result["report"].exists()
    assert result["html"].read_text(encoding="utf-8") == "<html>board de prueba</html>"
    # las versiones de trabajo en boards/YYYY-MM/ siguen intactas, no se tocan
    assert (paths.BOARDS_DIR / MONTH / "board_Jun_2026_v1.html").exists()
    assert (paths.BOARDS_DIR / MONTH / "board_Jun_2026_v2.html").exists()


def test_mark_final_can_target_specific_version(isolated_paths):
    versioning.save_version(MONTH, [], [])  # v1
    versioning.save_version(MONTH, [], [])  # v2

    result = versioning.mark_final(MONTH, version=1)

    assert result["version"] == 1


def test_mark_final_raises_if_requested_version_missing(isolated_paths):
    versioning.save_version(MONTH, [], [])  # v1
    with pytest.raises(RuntimeError, match="No existe"):
        versioning.mark_final(MONTH, version=5)


def test_mark_final_overwrites_previous_final_for_same_month(isolated_paths):
    """Un mes tiene una sola entrada en el histórico — re-marcar lo pisa, no duplica."""
    versioning.save_version(MONTH, [], [])  # v1
    versioning.mark_final(MONTH, version=1)
    versioning.save_version(MONTH, [], [])  # v2
    versioning.mark_final(MONTH, version=2)

    files = list(paths.HISTORICO_DIR.glob("board_Jun_2026*.html"))
    assert len(files) == 1


def test_update_pdf_script_targets_raises_if_pattern_does_not_match(isolated_paths):
    """Bug real encontrado en revisión de código 2026-07-06: si generate_pdf.py cambia de
    formato (ej. otro estilo de comillas) y _TARGET_RE deja de matchear, re.sub() no fallaba
    — escribía el archivo sin cambios y save_version() reportaba éxito, dejando el PDF
    apuntando en silencio a la versión vieja. Ahora debe explotar en vez de fallar en silencio."""
    paths.PDF_SCRIPT.write_text("HTML_FILE = 'algo que no matchea el regex'\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="se esperaban 2 reemplazos"):
        versioning.save_version(MONTH, [], [])
