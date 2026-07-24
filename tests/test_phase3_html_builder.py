import base64
import subprocess

import pytest
import yaml

from board_agent import paths, phase3_html_builder as f3


class _FakeProc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    data_dir.mkdir()
    output_dir.mkdir()
    monkeypatch.setattr(paths, "DATA_DIR", data_dir)
    monkeypatch.setattr(paths, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(paths, "CEO_YAML", tmp_path / "ceo.yaml")
    monkeypatch.setattr(paths, "NPS_SNAPSHOT_YAML", tmp_path / "nps_snapshot.yaml")
    return data_dir, output_dir


def test_reembed_cr_image_pass_when_no_image_referenced(isolated_dirs):
    """Un mes sin ninguna slide con imagen (topic solo de texto) no debe ser un WARN — no hay
    nada roto, simplemente no aplica."""
    data_dir, output_dir = isolated_dirs
    (output_dir / "2_discussion_topic.html").write_text("<html></html>")
    r = f3._reembed_cr_image("2026-05")
    assert r.status == "PASS"
    assert "sin imágenes" in r.detail


def test_reembed_cr_image_warn_when_referenced_image_missing_on_disk(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    html_path = output_dir / "2_discussion_topic.html"
    html_path.write_text('<img src="../data/assets/2026-05/image-2.png">', encoding="utf-8")
    r = f3._reembed_cr_image("2026-05")
    assert r.status == "WARN"
    assert "image-2.png" in r.detail


def test_reembed_cr_image_fail_when_html_missing(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    img_dir = data_dir / "assets" / "2026-05"
    img_dir.mkdir(parents=True)
    (img_dir / "image-2.png").write_bytes(b"\x89PNG fake")
    r = f3._reembed_cr_image("2026-05")
    assert r.status == "FAIL"


def test_reembed_cr_image_pass_embeds_base64_regardless_of_filename(isolated_dirs):
    """Reproduce el bug real encontrado 2026-07-06: el template usaba 'image-2.png', no
    'cr-landing-icp.png' — la función debe embeber cualquier nombre de archivo, no uno fijo."""
    data_dir, output_dir = isolated_dirs
    img_dir = data_dir / "assets" / "2026-05"
    img_dir.mkdir(parents=True)
    img_bytes = b"\x89PNG fake bytes"
    (img_dir / "image-2.png").write_bytes(img_bytes)
    html_path = output_dir / "2_discussion_topic.html"
    html_path.write_text('<img src="../data/assets/2026-05/image-2.png">', encoding="utf-8")

    r = f3._reembed_cr_image("2026-05")
    assert r.status == "PASS"
    new_html = html_path.read_text(encoding="utf-8")
    expected_b64 = base64.b64encode(img_bytes).decode()
    assert f'src="data:image/png;base64,{expected_b64}"' in new_html
    assert "image-2.png" not in new_html


def test_reembed_cr_image_embeds_multiple_images_in_same_month(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    img_dir = data_dir / "assets" / "2026-05"
    img_dir.mkdir(parents=True)
    (img_dir / "image-2.png").write_bytes(b"one")
    (img_dir / "image-3.jpg").write_bytes(b"two")
    html_path = output_dir / "2_discussion_topic.html"
    html_path.write_text(
        '<img src="../data/assets/2026-05/image-2.png">'
        '<img src="../data/assets/2026-05/image-3.jpg">', encoding="utf-8")

    r = f3._reembed_cr_image("2026-05")
    assert r.status == "PASS"
    new_html = html_path.read_text(encoding="utf-8")
    assert "data:image/png;base64," in new_html
    assert "data:image/jpeg;base64," in new_html


def test_flag_stale_financial_performance_skips_when_html_missing(isolated_dirs):
    r = f3._flag_stale_financial_performance("2026-06")
    assert r.status == "SKIP"


def test_flag_stale_financial_performance_skips_when_title_pattern_missing(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    (output_dir / "4_financial_performance.html").write_text("<title>Alegra Board</title>", encoding="utf-8")
    r = f3._flag_stale_financial_performance("2026-06")
    assert r.status == "SKIP"


def test_flag_stale_financial_performance_pass_when_title_matches(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    html_path = output_dir / "4_financial_performance.html"
    html_path.write_text(
        '<html><head><title>Alegra Board — Financial Performance · June 2026</title></head>'
        '<body><div class="board-slide">contenido real</div></body></html>', encoding="utf-8")
    r = f3._flag_stale_financial_performance("2026-06")
    assert r.status == "PASS"
    assert html_path.read_text(encoding="utf-8").count("contenido real") == 1
    assert "stale-overlay" not in html_path.read_text(encoding="utf-8")


def test_flag_stale_financial_performance_warns_and_overlays_when_title_is_old(isolated_dirs):
    """Reproduce el bug real reportado por el usuario: generó el board de junio y Template 4
    seguía diciendo 'May 2026'. Debe taparse visualmente, no reescribir/borrar el contenido."""
    data_dir, output_dir = isolated_dirs
    html_path = output_dir / "4_financial_performance.html"
    html_path.write_text(
        '<html><head><title>Alegra Board — Financial Performance · May 2026</title></head>'
        '<body>'
        '<div class="board-slide">slide 1 vieja</div>'
        '<div class="board-slide">slide 2 vieja</div>'
        '</body></html>', encoding="utf-8")

    r = f3._flag_stale_financial_performance("2026-06")
    assert r.status == "WARN"
    assert "May 2026" in r.detail and "2026-06" in r.detail

    new_html = html_path.read_text(encoding="utf-8")
    assert new_html.count("stale-overlay") >= 2  # una por cada .board-slide (CSS + 2 overlays = 3, pero al menos 2)
    assert "slide 1 vieja" in new_html  # el contenido original NO se borra, solo se tapa
    assert "slide 2 vieja" in new_html
    assert new_html.count('class="board-slide stale-slide"') == 2


def test_flag_stale_financial_performance_skip_when_no_board_slide_found(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    html_path = output_dir / "4_financial_performance.html"
    html_path.write_text(
        '<title>Alegra Board — Financial Performance · May 2026</title><body>sin slides</body>',
        encoding="utf-8")
    r = f3._flag_stale_financial_performance("2026-06")
    assert r.status == "SKIP"


def test_flag_stale_discussion_topics_skips_when_html_missing(isolated_dirs):
    r = f3._flag_stale_discussion_topics("2026-06")
    assert r.status == "SKIP"


def test_flag_stale_discussion_topics_skips_when_sentinel_missing(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    (output_dir / "2_discussion_topic.html").write_text("<html>sin sentinel</html>", encoding="utf-8")
    r = f3._flag_stale_discussion_topics("2026-06")
    assert r.status == "SKIP"


def test_flag_stale_discussion_topics_pass_when_sentinel_matches(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    html_path = output_dir / "2_discussion_topic.html"
    html_path.write_text(
        '<!-- updated_for_month: 2026-06 --><body><div class="dt-slide">contenido real</div></body>',
        encoding="utf-8")
    r = f3._flag_stale_discussion_topics("2026-06")
    assert r.status == "PASS"
    assert html_path.read_text(encoding="utf-8").count("contenido real") == 1
    assert "stale-overlay" not in html_path.read_text(encoding="utf-8")


def test_flag_stale_discussion_topics_replaces_body_with_fixed_placeholder(isolated_dirs):
    """Fix 2026-07-24 (pedido explícito del usuario): el número real de topics/slides varía
    mes a mes (1, 2 o 3 topics = 3, 6 o 9 slides) — taparlas todas in-place llenaría el board
    con tantos "contenido pendiente" como topics hubiera el mes anterior. En vez de eso, todo
    el <body> se reemplaza por un esqueleto FIJO: portada genérica "Discussion Topics" + 2
    slides vacías tapadas, sin importar cuánto contenido (ni qué títulos) había antes."""
    data_dir, output_dir = isolated_dirs
    html_path = output_dir / "2_discussion_topic.html"
    html_path.write_text(
        '<!-- updated_for_month: 2026-05 --><html><head></head><body>'
        '<div class="slide section-divider"><div class="section-title">Mexico Strategy</div></div>'
        '<div class="dt-slide">topic 1 viejo</div>'
        '<div class="slide section-divider"><div class="section-title">ICP Split Costa Rica Update</div></div>'
        '<div class="dt-slide">topic 2 viejo</div>'
        '</body></html>', encoding="utf-8")

    r = f3._flag_stale_discussion_topics("2026-06")
    assert r.status == "WARN"
    assert "2026-05" in r.detail and "2026-06" in r.detail
    assert "portada + 2 slide(s)" in r.detail

    new_html = html_path.read_text(encoding="utf-8")
    # contenido viejo (de cualquier cantidad de topics que hubiera) ya no aparece
    assert "Mexico Strategy" not in new_html
    assert "ICP Split Costa Rica Update" not in new_html
    assert "topic 1 viejo" not in new_html
    assert "topic 2 viejo" not in new_html
    # esqueleto fijo: 1 portada genérica + exactamente 2 slides vacías tapadas
    assert new_html.count('class="slide section-divider"') == 1
    assert "Discussion Topic" in new_html
    assert new_html.count('class="dt-slide stale-slide"') == 2
    assert new_html.count('class="stale-overlay"') == 2


def test_flag_stale_discussion_topics_skip_when_no_body_found(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    html_path = output_dir / "2_discussion_topic.html"
    html_path.write_text('<!-- updated_for_month: 2026-05 -->sin body', encoding="utf-8")
    r = f3._flag_stale_discussion_topics("2026-06")
    assert r.status == "SKIP"


def _write_ceo_yaml(tmp_path, updated_for_month=None):
    data = {"ceo_title": "CEO Highlights & Lowlights", "highlights": ["a"], "lowlights": ["b"]}
    if updated_for_month is not None:
        data["updated_for_month"] = updated_for_month
    with open(tmp_path / "ceo.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)


_INICIO_WITH_CEO_SLIDE = '''<html><head></head><body>
  <!-- SLIDE 1 — Cover -->
  <div class="slide">portada</div>
  <!-- SLIDE 2 — CEO Highlights / Lowlights -->
  <div class="slide">
    <div class="slide-header"><span class="title">CEO Highlights &amp; Lowlights</span></div>
    <div class="hl-outer-grid">contenido real de highlights</div>
  </div>
  <!-- SLIDE 3 — Monthly Performance -->
  <div class="slide">monthly performance fresco, no debe tocarse</div>
</body></html>'''


def test_flag_stale_ceo_highlights_skip_when_html_missing(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    r = f3._flag_stale_ceo_highlights("2026-06")
    assert r.status == "SKIP"


def test_flag_stale_ceo_highlights_skip_when_ceo_yaml_missing(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    (output_dir / "1_inicio.html").write_text(_INICIO_WITH_CEO_SLIDE, encoding="utf-8")
    r = f3._flag_stale_ceo_highlights("2026-06")
    assert r.status == "SKIP"


def test_flag_stale_ceo_highlights_skip_when_sentinel_absent(tmp_path, isolated_dirs):
    """Backward-compatible: si ceo.yaml no tiene 'updated_for_month' todavía, SKIP honesto —
    no se puede verificar, y no se tapa contenido que podría estar perfectamente al día."""
    data_dir, output_dir = isolated_dirs
    (output_dir / "1_inicio.html").write_text(_INICIO_WITH_CEO_SLIDE, encoding="utf-8")
    _write_ceo_yaml(tmp_path)
    r = f3._flag_stale_ceo_highlights("2026-06")
    assert r.status == "SKIP"
    assert "updated_for_month" in r.detail


def test_flag_stale_ceo_highlights_pass_when_sentinel_matches(tmp_path, isolated_dirs):
    data_dir, output_dir = isolated_dirs
    html_path = output_dir / "1_inicio.html"
    html_path.write_text(_INICIO_WITH_CEO_SLIDE, encoding="utf-8")
    _write_ceo_yaml(tmp_path, updated_for_month="2026-06")
    r = f3._flag_stale_ceo_highlights("2026-06")
    assert r.status == "PASS"
    assert "stale-overlay" not in html_path.read_text(encoding="utf-8")


def test_flag_stale_ceo_highlights_warns_and_overlays_only_that_slide(tmp_path, isolated_dirs):
    """Reproduce el hallazgo del usuario: CEO Highlights seguía mostrando contenido de mayo en
    junio. Debe taparse SOLO esa slide — Monthly Performance (misma clase .slide) debe quedar
    intacta, sin overlay."""
    data_dir, output_dir = isolated_dirs
    html_path = output_dir / "1_inicio.html"
    html_path.write_text(_INICIO_WITH_CEO_SLIDE, encoding="utf-8")
    _write_ceo_yaml(tmp_path, updated_for_month="2026-05")

    r = f3._flag_stale_ceo_highlights("2026-06")
    assert r.status == "WARN"
    assert "2026-05" in r.detail and "2026-06" in r.detail

    new_html = html_path.read_text(encoding="utf-8")
    assert new_html.count('class="stale-overlay"') == 1  # (el selector CSS también contiene la palabra)
    assert "contenido real de highlights" in new_html  # conservado, solo tapado
    assert "monthly performance fresco, no debe tocarse" in new_html
    # solo UNA slide .slide ganó la clase stale-slide — no todas las del archivo
    assert new_html.count('class="slide stale-slide"') == 1


def test_flag_stale_ceo_highlights_skip_when_marker_not_found(tmp_path, isolated_dirs):
    data_dir, output_dir = isolated_dirs
    (output_dir / "1_inicio.html").write_text("<html><body>sin el marcador esperado</body></html>",
                                                encoding="utf-8")
    _write_ceo_yaml(tmp_path, updated_for_month="2026-05")
    r = f3._flag_stale_ceo_highlights("2026-06")
    assert r.status == "SKIP"


def _write_nps_snapshot(tmp_path, months):
    data = {m: {"score": 46.5} for m in months}
    with open(tmp_path / "nps_snapshot.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)


_RD_WITH_NPS_SLIDE = '''<html><head></head><body>
  <!-- SLIDE 1 — Section Cover -->
  <div class="slide section-cover">portada, clase distinta a "slide", no se toca</div>
  <!-- SLIDE 2 — Product Performance -->
  <div class="slide">product performance de mayo</div>
  <!-- SLIDE 3 — NPS Alegra -->
  <div class="slide">
    <div class="slide-header"><span class="title">NPS Alegra Accounting</span></div>
    contenido real de NPS de mayo
  </div>
</body></html>'''


def test_flag_stale_nps_skip_when_html_missing(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    r = f3._flag_stale_nps("2026-06")
    assert r.status == "SKIP"


def test_flag_stale_nps_pass_when_month_present(tmp_path, isolated_dirs):
    data_dir, output_dir = isolated_dirs
    html_path = output_dir / "6_rd.html"
    html_path.write_text(_RD_WITH_NPS_SLIDE, encoding="utf-8")
    _write_nps_snapshot(tmp_path, ["2026-05", "2026-06"])
    r = f3._flag_stale_nps("2026-06")
    assert r.status == "PASS"
    assert "stale-overlay" not in html_path.read_text(encoding="utf-8")


def test_flag_stale_nps_warns_and_overlays_only_nps(tmp_path, isolated_dirs):
    """Fix 2026-07-24 (bug real reportado por el usuario): NPS sin snapshot para el mes de
    corte NO debe tapar Product Performance — desde que generate.py usa
    ChainableUndefined/_TrackingUndefined, un campo de NPS faltante ya no truena el render
    del archivo entero (queda en blanco, ver F3.9); Product Performance sí se regenera bien
    para el mes correcto en la misma corrida. Antes (scope="file" con slide_classes=["slide"])
    tapaba las DOS slides porque comparten la misma clase genérica — ahora usa el mismo
    patrón de marcador que F3.6 (CEO Highlights) para tapar solo la slide de NPS."""
    data_dir, output_dir = isolated_dirs
    html_path = output_dir / "6_rd.html"
    html_path.write_text(_RD_WITH_NPS_SLIDE, encoding="utf-8")
    _write_nps_snapshot(tmp_path, ["2026-05"])  # sin junio

    r = f3._flag_stale_nps("2026-06")
    assert r.status == "WARN"
    assert "2026-06" in r.detail
    assert "Product Performance" not in r.detail

    new_html = html_path.read_text(encoding="utf-8")
    assert new_html.count('class="stale-overlay"') == 1
    assert new_html.count('class="slide stale-slide"') == 1  # solo NPS
    assert "contenido real de NPS de mayo" in new_html  # conservado, solo tapado
    assert 'class="slide">product performance de mayo</div>' in new_html  # NO tapado
    assert 'class="slide section-cover"' in new_html  # portada tampoco tocada


def test_flag_stale_nps_skip_when_no_slide_found(tmp_path, isolated_dirs):
    data_dir, output_dir = isolated_dirs
    (output_dir / "6_rd.html").write_text("<html><body>sin ninguna slide</body></html>",
                                            encoding="utf-8")
    _write_nps_snapshot(tmp_path, ["2026-05"])
    r = f3._flag_stale_nps("2026-06")
    assert r.status == "SKIP"


_HEADCOUNT_HTML = '''<html><head></head><body>
  <div class="slide section-cover">portada, clase distinta a "hc-slide", no se toca</div>
  <div class="hc-slide">Headcount by Team de mayo</div>
  <div class="hc-slide">People &amp; Talent de mayo</div>
</body></html>'''


def test_flag_stale_headcount_skip_when_html_missing(isolated_dirs):
    r = f3._flag_stale_headcount("2026-06")
    assert r.status == "SKIP"


def test_flag_stale_headcount_skip_when_sentinel_missing(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    (output_dir / "7_headcount.html").write_text("<html>sin sentinel</html>", encoding="utf-8")
    r = f3._flag_stale_headcount("2026-06")
    assert r.status == "SKIP"


def test_flag_stale_headcount_pass_when_sentinel_matches(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    html_path = output_dir / "7_headcount.html"
    html_path.write_text(f"<!-- updated_for_month: 2026-06 -->\n{_HEADCOUNT_HTML}", encoding="utf-8")
    r = f3._flag_stale_headcount("2026-06")
    assert r.status == "PASS"
    assert "stale-overlay" not in html_path.read_text(encoding="utf-8")


def test_flag_stale_headcount_warns_and_overlays_both_slides(isolated_dirs):
    """Mismo hueco que tenía Discussion Topics: comentarios de Headcount desactualizados deben
    taparse — ambas slides (.hc-slide), no la portada (clase distinta)."""
    data_dir, output_dir = isolated_dirs
    html_path = output_dir / "7_headcount.html"
    html_path.write_text(f"<!-- updated_for_month: 2026-05 -->\n{_HEADCOUNT_HTML}", encoding="utf-8")

    r = f3._flag_stale_headcount("2026-06")
    assert r.status == "WARN"
    assert "2026-05" in r.detail and "2026-06" in r.detail

    new_html = html_path.read_text(encoding="utf-8")
    assert new_html.count('class="hc-slide stale-slide"') == 2
    assert 'class="slide section-cover"' in new_html  # portada no tocada
    assert "Headcount by Team de mayo" in new_html  # conservado, solo tapado
    assert "People &amp; Talent de mayo" in new_html


def test_flag_stale_headcount_skip_when_no_slide_found(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    (output_dir / "7_headcount.html").write_text(
        "<!-- updated_for_month: 2026-05 --><html><body>sin hc-slide</body></html>", encoding="utf-8")
    r = f3._flag_stale_headcount("2026-06")
    assert r.status == "SKIP"


def test_run_stops_early_if_generate_fails(monkeypatch, isolated_dirs):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _FakeProc(1, stderr="boom"))
    results = f3.run("2026-05")
    assert len(results) == 1
    assert results[0].id == "F3.1"
    assert results[0].status == "FAIL"


def test_run_returncode_2_does_not_abort_rest_of_fase_3(monkeypatch, isolated_dirs):
    """returncode 1 (catastrófico) aborta todo — returncode 2 (uno o más templates con
    un error real, no de datos) NO debería: los templates que sí se generaron bien no
    deberían quedar bloqueados por un bug ajeno en otro archivo."""
    calls = {"n": 0}

    def fake_run(cmd, **kw):
        calls["n"] += 1
        if "generate.py" in str(cmd):
            return _FakeProc(2, stdout="FALLARON: 6_rd")
        return _FakeProc(0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    results = f3.run("2026-05")

    assert calls["n"] == 2  # generate.py Y merge_standalone.py — no se abortó
    f31 = next(r for r in results if r.id == "F3.1")
    assert f31.status == "FAIL"
    assert "6_rd" in f31.detail
    assert results[-1].id == "F3.3"
    assert results[-1].status == "PASS"


def test_run_parses_missing_fields_as_warn_for_non_critical_template(monkeypatch, isolated_dirs):
    monkeypatch.setattr(subprocess, "run",
                         lambda cmd, **kw: _FakeProc(0, stdout="MISSING_FIELDS 6_rd: nps, costa_rica_trend"))
    results = f3.run("2026-05")
    f39 = next(r for r in results if r.id == "F3.9")
    assert f39.status == "WARN"
    assert "nps" in f39.detail and "costa_rica_trend" in f39.detail


def test_run_parses_missing_fields_as_fail_for_board_critical_template(monkeypatch, isolated_dirs):
    monkeypatch.setattr(subprocess, "run",
                         lambda cmd, **kw: _FakeProc(0, stdout="MISSING_FIELDS 1_inicio: arr_total"))
    results = f3.run("2026-05")
    f39 = next(r for r in results if r.id == "F3.9")
    assert f39.status == "FAIL"


def test_run_with_templates_param_passes_comma_list_to_generate(monkeypatch, isolated_dirs):
    captured_cmds = []

    def fake_run(cmd, **kw):
        captured_cmds.append(cmd)
        return _FakeProc(0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    f3.run("2026-05", templates=["3_arr_walk", "6_rd"])

    generate_cmd = captured_cmds[0]
    assert "--template" in generate_cmd
    assert "3_arr_walk,6_rd" in generate_cmd


def test_structural_lint_flags_duplicate_id_as_fail(monkeypatch, isolated_dirs):
    data_dir, output_dir = isolated_dirs
    (output_dir / "6_rd.html").write_text('<div id="dup"></div><div id="dup"></div>', encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _FakeProc(0))

    results = f3.run("2026-05", templates=["6_rd"])

    f310 = next(r for r in results if r.id == "F3.10")
    assert f310.status == "FAIL"
    assert "dup" in f310.detail


def test_run_stops_before_merge_reembed_still_runs(monkeypatch, isolated_dirs):
    data_dir, output_dir = isolated_dirs
    (output_dir / "2_discussion_topic.html").write_text(
        '<img src="../data/assets/2026-05/image-2.png">')  # referenciada pero no existe en disco -> WARN

    calls = {"n": 0}

    def fake_run(cmd, **kw):
        calls["n"] += 1
        return _FakeProc(0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    results = f3.run("2026-05")
    ids = [r.id for r in results]
    # F3.10 aparece una sola vez porque, en este test, 2_discussion_topic.html es el único
    # output/*.html que existe en disco (de los 8 stems posibles) — el linter estructural
    # solo corre sobre lo que sí existe.
    assert ids == ["F3.1", "F3.10", "F3.2", "F3.6", "F3.5", "F3.4", "F3.7", "F3.8", "F3.3"]
    assert results[0].status == "PASS"
    assert results[1].status == "PASS"  # F3.10 — <img> sin ids/scripts, nada que reportar
    assert results[2].status == "WARN"  # F3.2 — imagen no existe en este test
    assert results[3].status == "SKIP"  # no existe ceo.yaml en este test
    assert results[4].status == "SKIP"  # sin sentinel 'updated_for_month' en este test
    assert results[5].status == "SKIP"  # no hay 4_financial_performance.html en este test
    assert results[6].status == "SKIP"  # no hay 6_rd.html en este test
    assert results[7].status == "SKIP"  # no hay 7_headcount.html en este test
    assert results[8].status == "PASS"
    assert calls["n"] == 2  # generate.py + merge_standalone.py


def test_run_fails_on_merge_error(monkeypatch, isolated_dirs):
    data_dir, output_dir = isolated_dirs
    (output_dir / "2_discussion_topic.html").write_text("<html></html>")

    call_order = []

    def fake_run(cmd, **kw):
        script = str(cmd[cmd.index("python3") + 1])
        call_order.append(script)
        if "merge_standalone" in script:
            return _FakeProc(1, stderr="merge broke")
        return _FakeProc(0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    results = f3.run("2026-05")
    assert results[-1].id == "F3.3"
    assert results[-1].status == "FAIL"
