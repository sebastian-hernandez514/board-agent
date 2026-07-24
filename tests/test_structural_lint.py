from board_agent import structural_lint as lint


def test_no_duplicate_ids_on_clean_html():
    html = '<div id="a"></div><div id="b"></div>'
    assert lint.check_duplicate_ids(html) == []


def test_detects_duplicate_id():
    html = '<div id="a"></div><div id="a"></div><div id="b"></div>'
    assert lint.check_duplicate_ids(html) == ["a"]


def test_detects_multiple_duplicate_ids_once_each():
    html = '<div id="a"></div><div id="a"></div><div id="b"></div><div id="b"></div><div id="b"></div>'
    assert lint.check_duplicate_ids(html) == ["a", "b"]


def test_balanced_tags_pass():
    html = "<div><script>1</script></div>"
    assert lint.check_balanced_tags(html) == {}


def test_unbalanced_script_tag_detected():
    html = "<div><script>1</script><script>2</div>"
    unbalanced = lint.check_balanced_tags(html)
    assert unbalanced["script"] == (2, 1)


def test_unbalanced_div_tag_detected():
    html = "<div><div></div>"
    unbalanced = lint.check_balanced_tags(html)
    assert unbalanced["div"] == (2, 1)


def test_orphaned_references_clean_when_canvas_has_matching_script():
    html = """
    <canvas id="arrEoPChart"></canvas>
    <script>const ctx = document.getElementById('arrEoPChart');</script>
    """
    result = lint.check_orphaned_references(html)
    assert result["canvases_sin_script"] == []
    assert result["scripts_a_id_inexistente"] == []


def test_orphaned_references_detects_canvas_without_script():
    """Caso real de 5_go_to_market.j2: un <canvas> queda sin ningún script que lo
    inicialice — típicamente porque el script que lo hacía se movió/borró a medias."""
    html = '<canvas id="acqCoreChart"></canvas>'
    result = lint.check_orphaned_references(html)
    assert result["canvases_sin_script"] == ["acqCoreChart"]
    assert result["scripts_a_id_inexistente"] == []


def test_orphaned_references_detects_script_pointing_to_missing_id():
    """El otro lado del mismo caso: el script sobrevive pero el canvas que buscaba
    se movió/renombró/borró."""
    html = "<script>document.getElementById('acqCoreChart').innerHTML;</script>"
    result = lint.check_orphaned_references(html)
    assert result["canvases_sin_script"] == []
    assert result["scripts_a_id_inexistente"] == ["acqCoreChart"]


def test_orphaned_references_ignores_non_canvas_ids_without_script():
    """No debe marcar como huérfano un id normal (div de estilo/ancla) que nunca
    necesitó un script — solo <canvas> sin script es inequívocamente un chart roto."""
    html = '<div id="section-header"></div><canvas id="myChart"></canvas><script>getElementById("myChart")</script>'
    result = lint.check_orphaned_references(html)
    assert result["canvases_sin_script"] == []
    assert result["scripts_a_id_inexistente"] == []


def test_orphaned_references_query_selector_variant():
    html = '<canvas id="fw2Chart"></canvas><script>document.querySelector("#fw2Chart")</script>'
    result = lint.check_orphaned_references(html)
    assert result["canvases_sin_script"] == []


def test_orphaned_references_canvas_used_via_helper_function_argument():
    """Caso real encontrado corriendo contra 5_go_to_market.j2/8_appendix.j2: el id se pasa
    como argumento a un helper propio (mkChart/buildChart), no vía getElementById directo —
    antes esto daba un falso positivo de 'canvas sin script'."""
    html = """
    <canvas id="cCore"></canvas>
    <script>function mkChart(id, data) { ... } mkChart('cCore', someData);</script>
    """
    result = lint.check_orphaned_references(html)
    assert result["canvases_sin_script"] == []
    assert result["scripts_a_id_inexistente"] == []  # 'cCore' vía helper no cuenta como lookup roto


def test_orphaned_references_defensive_guard_is_not_flagged_as_broken():
    """Caso real de 5_go_to_market.j2 (slides de Flywheel deshabilitadas con {% if false %}):
    if (document.getElementById('X')) ... es código que ya anticipa que el id puede no
    existir — no es una referencia rota, es manejo defensivo correcto."""
    html = """<script>
    if (document.getElementById('fw_entitiesLine')) new Chart(document.getElementById('fw_entitiesLine'), {});
    </script>"""
    result = lint.check_orphaned_references(html)
    assert result["scripts_a_id_inexistente"] == []


def test_orphaned_references_unguarded_getelementbyid_to_missing_id_is_still_flagged():
    """El caso real encontrado en 3_arr_walk.j2: getElementById SIN ningún if de protección
    y el id no existe en ningún lado — esto sí debe seguir marcado, es un bug real (el
    siguiente uso de esa variable revienta con 'Cannot read properties of null')."""
    html = """<script>
    const el = document.getElementById('awcoreQCards');
    el.innerHTML += '<div></div>';
    </script>"""
    result = lint.check_orphaned_references(html)
    assert result["scripts_a_id_inexistente"] == ["awcoreQCards"]
