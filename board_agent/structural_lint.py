"""Linter estructural sobre HTML ya generado — no depende de que Jinja2/generate.py
falle, son chequeos puramente mecánicos sobre el output/*.html final, mismo estilo
regex-sobre-HTML que ya usa phase4_validator.py (R16/R18). Ninguno de los 2 (ni R12,
que solo cuenta slides) chequea esto — terreno libre.

Nace de la pregunta "si alguien mueve HTML a mano, ¿puede desconectar algo sin que se
note?" — ids duplicados y tags desbalanceados son daño estructural directo; el caso real
que motiva check_orphaned_references() es el que encontramos en 5_go_to_market.j2: un
<canvas> vive en una slide y el <script> que lo inicializa (getElementById) vive 400
líneas después, en otra slide — si alguien mueve el canvas sin mover el script (o
viceversa), el chart queda roto sin que Jinja2 ni generate.py se enteren.

Restringido a <canvas> (no "cualquier id sin uso") a propósito: la mayoría de los ids en
estos templates son anclas de estilo/CSS que nunca necesitan un script — solo un canvas
sin ningún script que lo inicialice es inequívocamente un chart huérfano.
"""

import re

_ID_RE = re.compile(r'\bid="([^"]+)"')
_CANVAS_ID_RE = re.compile(r'<canvas\b[^>]*\bid="([^"]+)"', re.IGNORECASE)
_SCRIPT_BLOCK_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
_SCRIPT_OPEN_RE = re.compile(r"<script\b", re.IGNORECASE)
_SCRIPT_CLOSE_RE = re.compile(r"</script>", re.IGNORECASE)
_DIV_OPEN_RE = re.compile(r"<div\b", re.IGNORECASE)
_DIV_CLOSE_RE = re.compile(r"</div>", re.IGNORECASE)
_ID_REF_RE = re.compile(r"""getElementById\(\s*['"]([^'"]+)['"]\s*\)|querySelector\(\s*['"]#([^'"]+)['"]\s*\)""")

# Patrón real encontrado corriendo esto por primera vez contra los 8 templates (2026-07-21,
# board de junio): varios templates pasan el id como argumento a un helper propio
# (`mkChart('cCore', ...)`, `cvMakeChart('cvCol', ...)`, `buildChart('chart-global', ...)`)
# en vez de resolverlo inline con getElementById — sin esto, canvases_sin_script daba falsos
# positivos. Se usa SOLO para "¿este canvas se usa en algún lado?" (más laxo a propósito),
# nunca para decidir si una referencia está rota (eso sigue siendo estricto, ver abajo).
_ANY_CALL_STRING_ARG_RE = re.compile(r"""[A-Za-z_$][\w$]*\(\s*['"]([^'"]+)['"]""")

# Guard defensivo real ya usado en el repo (5_go_to_market.j2, slides de Flywheel
# deshabilitadas con {% if false %}): `if (document.getElementById('X')) ...` — si el id no
# existe, el bloque simplemente no corre, cero riesgo de romper nada. No es una referencia
# huérfana real, es código que ya anticipa que el elemento puede no existir.
_GUARDED_ID_RE = re.compile(r"""if\s*\(\s*document\.getElementById\(\s*['"]([^'"]+)['"]\s*\)\s*\)""")


def check_duplicate_ids(html: str) -> list[str]:
    """Ids que aparecen 2+ veces en el HTML — orden de primera aparición del duplicado."""
    seen: set[str] = set()
    dupes: list[str] = []
    for i in _ID_RE.findall(html):
        if i in seen and i not in dupes:
            dupes.append(i)
        seen.add(i)
    return dupes


def check_balanced_tags(html: str) -> dict[str, tuple[int, int]]:
    """{tag: (abiertos, cerrados)} solo para los tags que NO coinciden. Vacío = todo bien."""
    pairs = {
        "script": (_SCRIPT_OPEN_RE, _SCRIPT_CLOSE_RE),
        "div": (_DIV_OPEN_RE, _DIV_CLOSE_RE),
    }
    unbalanced = {}
    for tag, (open_re, close_re) in pairs.items():
        n_open, n_close = len(open_re.findall(html)), len(close_re.findall(html))
        if n_open != n_close:
            unbalanced[tag] = (n_open, n_close)
    return unbalanced


def check_orphaned_references(html: str) -> dict[str, list[str]]:
    """canvases_sin_script: <canvas id="X"> que ningún <script> del archivo parece usar
    (ni por getElementById directo, ni pasándolo como argumento a un helper propio).
    scripts_a_id_inexistente: un `getElementById`/`querySelector` busca un id que no existe
    en ningún elemento, y no está protegido por un `if (document.getElementById(...))`."""
    all_ids = set(_ID_RE.findall(html))
    canvas_ids = set(_CANVAS_ID_RE.findall(html))

    dom_lookups: set[str] = set()      # getElementById/querySelector reales — deben existir
    guarded: set[str] = set()          # protegidos por if (getElementById(...)) — no rompen nada
    any_call_args: set[str] = set()    # cualquier string pasado a una función — señal de "se usa"

    for script_body in _SCRIPT_BLOCK_RE.findall(html):
        for m in _ID_REF_RE.finditer(script_body):
            dom_lookups.add(m.group(1) or m.group(2))
        guarded.update(_GUARDED_ID_RE.findall(script_body))
        any_call_args.update(_ANY_CALL_STRING_ARG_RE.findall(script_body))

    broken = (dom_lookups - all_ids) - guarded
    referenced_for_canvas_check = dom_lookups | any_call_args

    return {
        "canvases_sin_script": sorted(canvas_ids - referenced_for_canvas_check),
        "scripts_a_id_inexistente": sorted(broken),
    }
