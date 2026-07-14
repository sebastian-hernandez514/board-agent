import pytest

from board_agent import output_integrity, paths


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    hash_state_file = tmp_path / ".state" / "output_hashes.json"
    backup_dir = output_dir / ".manual-edits-backup"

    monkeypatch.setattr(paths, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(paths, "HASH_STATE_FILE", hash_state_file)
    monkeypatch.setattr(paths, "MANUAL_EDITS_BACKUP_DIR", backup_dir)
    return output_dir


def _write_html(output_dir, name, content):
    (output_dir / name).write_text(content, encoding="utf-8")


def test_first_run_ever_passes_with_no_baseline(isolated_paths):
    """Sin baseline todavía (repo recién clonado, o primera corrida) — no hay nada contra qué
    comparar, no debe bloquear."""
    _write_html(isolated_paths, "1_inicio.html", "<html>v1</html>")
    result = output_integrity.check_for_manual_edits()
    assert result.status == "PASS"
    assert "sin baseline" in result.detail


def test_passes_when_nothing_changed_since_last_generation(isolated_paths):
    _write_html(isolated_paths, "1_inicio.html", "<html>v1</html>")
    _write_html(isolated_paths, "3_arr_walk.html", "<html>arr walk</html>")
    output_integrity.record_generated_state()

    result = output_integrity.check_for_manual_edits()
    assert result.status == "PASS"
    assert "2 archivo(s) verificados" in result.detail


def test_fails_and_backs_up_when_a_file_was_hand_edited(isolated_paths):
    """El caso real reportado por el usuario: alguien le cambia el título / agrega un
    comentario directo al HTML ya generado. Debe FAIL duro y dejar un backup recuperable."""
    _write_html(isolated_paths, "3_arr_walk.html", "<html>original generado por generate.py</html>")
    output_integrity.record_generated_state()

    _write_html(isolated_paths, "3_arr_walk.html", "<html>original generado por generate.py + comentario a mano</html>")

    result = output_integrity.check_for_manual_edits()
    assert result.status == "FAIL"
    assert "3_arr_walk.html" in result.detail

    backups = list(paths.MANUAL_EDITS_BACKUP_DIR.glob("3_arr_walk.*.html"))
    assert len(backups) == 1
    assert "comentario a mano" in backups[0].read_text(encoding="utf-8")


def test_only_flags_the_file_that_actually_changed(isolated_paths):
    _write_html(isolated_paths, "1_inicio.html", "<html>v1</html>")
    _write_html(isolated_paths, "3_arr_walk.html", "<html>arr walk</html>")
    output_integrity.record_generated_state()

    _write_html(isolated_paths, "3_arr_walk.html", "<html>arr walk EDITADO</html>")

    result = output_integrity.check_for_manual_edits()
    assert result.status == "FAIL"
    assert "3_arr_walk.html" in result.detail
    assert "1_inicio.html" not in result.detail


def test_passes_again_after_a_fresh_regeneration_records_new_baseline(isolated_paths):
    """Simula el flujo real: se detecta drift, alguien corre generate.py de nuevo (o mueve el
    contenido a la capa correcta y regenera) — record_generated_state() debe dejar todo en
    verde otra vez, sin arrastrar el FAIL viejo."""
    _write_html(isolated_paths, "3_arr_walk.html", "<html>v1</html>")
    output_integrity.record_generated_state()
    _write_html(isolated_paths, "3_arr_walk.html", "<html>editado a mano</html>")
    assert output_integrity.check_for_manual_edits().status == "FAIL"

    # Regenera (ej. generate.py corrió de nuevo) y vuelve a registrar el estado
    _write_html(isolated_paths, "3_arr_walk.html", "<html>v2 regenerado</html>")
    output_integrity.record_generated_state()

    result = output_integrity.check_for_manual_edits()
    assert result.status == "PASS"


def test_new_file_appearing_is_not_treated_as_drift(isolated_paths):
    """Un archivo nuevo (ej. una slide nueva agregada al template) no tiene hash previo —
    no debe contarse como 'editado a mano', solo los archivos que YA estaban en la baseline
    y cambiaron de contenido."""
    _write_html(isolated_paths, "1_inicio.html", "<html>v1</html>")
    output_integrity.record_generated_state()

    _write_html(isolated_paths, "9_nueva_slide.html", "<html>slide nueva</html>")

    result = output_integrity.check_for_manual_edits()
    assert result.status == "PASS"


def test_output_dir_missing_passes_with_no_baseline(isolated_paths, monkeypatch):
    monkeypatch.setattr(paths, "OUTPUT_DIR", isolated_paths.parent / "no-existe")
    result = output_integrity.check_for_manual_edits()
    assert result.status == "PASS"


def test_fails_when_a_baselined_file_disappears(isolated_paths):
    """Bug real corregido 2026-07-14: si alguien edita un archivo a mano y LUEGO lo borra
    (o se borra por accidente) antes de la siguiente corrida, el chequeo antes hacía
    `continue` sobre el archivo faltante y daba PASS en silencio — justo el caso de pérdida
    de edición manual que este módulo existe para atrapar. Ahora debe FAIL (no hay nada que
    respaldar, pero es una discrepancia real)."""
    _write_html(isolated_paths, "1_inicio.html", "<html>v1</html>")
    _write_html(isolated_paths, "3_arr_walk.html", "<html>arr walk</html>")
    output_integrity.record_generated_state()

    (isolated_paths / "3_arr_walk.html").unlink()

    result = output_integrity.check_for_manual_edits()
    assert result.status == "FAIL"
    assert "3_arr_walk.html" in result.detail
    assert "desaparecieron" in result.detail
