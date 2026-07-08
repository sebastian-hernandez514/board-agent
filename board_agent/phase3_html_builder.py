"""Fase 3 — HTML Builder. generate.py + re-embed de imágenes de discussion topics + merge_standalone.py.

El paso de re-embed existe porque generate.py sobrescribe 2_discussion_topic.html con una
ruta relativa a las imágenes de assets/YYYY-MM/ que queda rota en el standalone — es el paso
manual que "siempre se rompe" según memory/project_board_pipeline.md. Automatizarlo acá lo elimina.

Antes (hasta 2026-07-06) esto buscaba un único nombre de archivo hardcodeado
("cr-landing-icp.png") — bug real encontrado en la revisión de esa fecha: el template ya
había cambiado a "image-2.png" y el board v44 (guardado como entregable) salió con esa imagen
sin embeber (ruta relativa rota si se abre el HTML fuera de Template Board/output/). Ahora
busca cualquier <img src="...data/assets/{month}/..."> sin importar el nombre del archivo,
así que un topic nuevo con una imagen de otro nombre queda cubierto automáticamente.

F3.4 (agregada 2026-07-08): tapa visualmente las slides de Template 4 (Financial Performance)
si el <title> del HTML ya generado sigue en el mes anterior (mismo hallazgo real que F0.9,
ver phase0_gate.py) — en vez de publicar el board con los números de Finance del mes pasado
disfrazados como si fueran de este mes. Solo escribe en output/4_financial_performance.html
(el artefacto ya generado por generate.py), nunca en el .j2 fuente — mismo patrón que
_reembed_cr_image(). No elimina ni reescribe el contenido existente (evita el riesgo de
romper HTML anidado con regex) — inserta un overlay que lo cubre visualmente por completo.

F3.5 (agregada 2026-07-08, mismo día): mismo mecanismo para Discussion Topics, usando el
sentinel '<!-- updated_for_month: YYYY-MM -->' agregado a 2_discussion_topic.j2 (ver F0.6 en
phase0_gate.py) — el comentario pasa intacto a través de Jinja2, así que se puede leer del
output/2_discussion_topic.html ya generado sin tocar el .j2 fuente en esta fase. Cubre tanto
las slides de contenido (`.dt-slide`) como las portadas de cada topic (`.slide.section-divider`)
— hallazgo del usuario 2026-07-08 (segunda revisión): la portada revelaba el título del tema
viejo (ej. "ICP Split Costa Rica Update") aunque el contenido de abajo ya estuviera tapado.
"""

import base64
import re
import subprocess

from . import paths
from .phase0_gate import extract_financial_performance_title_month, extract_updated_for_month_comment
from .report import CheckResult


def _run_script(script_path, deps: tuple[str, ...], extra_args=None):
    cmd = ["uv", "run"]
    for d in deps:
        cmd += ["--with", d]
    cmd += ["python3", str(script_path)] + (extra_args or [])
    return subprocess.run(cmd, cwd=paths.TEMPLATE_BOARD, capture_output=True, text=True, timeout=300)


_EXT_TO_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def _reembed_cr_image(month: str) -> CheckResult:
    html_path = paths.OUTPUT_DIR / "2_discussion_topic.html"
    if not html_path.exists():
        return CheckResult("F3.2", "Re-embed imágenes de discussion topics", "FAIL",
                            f"no existe {html_path} — ¿corrió generate.py?")

    html = html_path.read_text(encoding="utf-8")
    pattern = re.compile(r'src="[^"]*assets/' + re.escape(month) + r'/([^"/]+)"')
    filenames = sorted(set(pattern.findall(html)))

    if not filenames:
        return CheckResult("F3.2", "Re-embed imágenes de discussion topics", "PASS",
                            "sin imágenes referenciadas en data/assets/ este mes")

    embedded, missing = [], []
    for fname in filenames:
        img_path = paths.DATA_DIR / "assets" / month / fname
        mime = _EXT_TO_MIME.get(img_path.suffix.lower(), "image/png")
        if not img_path.exists():
            missing.append(fname)
            continue
        b64 = base64.b64encode(img_path.read_bytes()).decode()
        html = re.sub(r'src="[^"]*assets/' + re.escape(month) + r'/' + re.escape(fname) + r'"',
                      f'src="data:{mime};base64,{b64}"', html)
        embedded.append(fname)

    html_path.write_text(html, encoding="utf-8")

    if missing:
        return CheckResult("F3.2", "Re-embed imágenes de discussion topics", "WARN",
                            f"embebidas: {embedded or 'ninguna'} · faltantes en disco (slide queda con imagen rota): {missing}")
    return CheckResult("F3.2", "Re-embed imágenes de discussion topics", "PASS",
                        f"embebidas: {embedded}")


_STALE_OVERLAY_STYLE = (
    "<style>.stale-slide{position:relative !important;}"
    ".stale-overlay{position:absolute;inset:0;z-index:999;background:#f8fafc;"
    "display:flex;flex-direction:column;align-items:center;justify-content:center;"
    "gap:10px;text-align:center;padding:40px;box-sizing:border-box;}"
    ".stale-overlay .stale-icon{font-size:32px;}"
    ".stale-overlay .stale-title{font-size:20px;font-weight:700;color:#475569;}"
    ".stale-overlay .stale-sub{font-size:14px;color:#94a3b8;max-width:520px;}</style>"
)

_STALE_OVERLAY_HTML = (
    '<div class="stale-overlay"><div class="stale-icon">⏳</div>'
    '<div class="stale-title">{section} — contenido pendiente</div>'
    '<div class="stale-sub">Esta sección mostraba {old_label} — se ocultó para no publicar '
    'el mes equivocado.</div></div>'
)


def _overlay_stale_slides(html: str, slide_classes, section: str, old_label: str) -> tuple[str, int]:
    """Cubre cada slide de `slide_classes` (un string o una lista de strings — ej. la portada
    de un topic Y sus slides de contenido) con un overlay "contenido pendiente", sin borrar ni
    reescribir el HTML anidado existente debajo (evita el riesgo de romper la estructura con
    regex de reemplazo) — le agrega la clase marcadora `stale-slide` (position:relative, ver
    _STALE_OVERLAY_STYLE) e inserta el overlay como hijo justo después del tag de apertura.
    Devuelve (html_modificado, cantidad_de_slides_tapadas). 0 slides → no modifica nada."""
    if isinstance(slide_classes, str):
        slide_classes = [slide_classes]

    overlay = _STALE_OVERLAY_HTML.format(section=section, old_label=old_label)
    total = 0
    for slide_class in slide_classes:
        open_re = re.compile(r'<div class="' + re.escape(slide_class) + r'"[^>]*>')
        n = len(open_re.findall(html))
        if n == 0:
            continue
        total += n

        def _inject(m, _cls=slide_class):
            tag = m.group(0).replace(f'class="{_cls}"', f'class="{_cls} stale-slide"', 1)
            return tag + overlay

        html = open_re.sub(_inject, html)

    if total == 0:
        return html, 0
    if "</head>" in html:
        html = html.replace("</head>", _STALE_OVERLAY_STYLE + "</head>", 1)
    else:
        html = _STALE_OVERLAY_STYLE + html
    return html, total


def _flag_stale_financial_performance(month: str) -> CheckResult:
    """F3.4 — ver nota de módulo. Post-procesa output/4_financial_performance.html (ya generado
    por generate.py), nunca el .j2 fuente. WARN, no FAIL — mismo criterio que F0.9: es un
    insumo externo que llega tarde, no debe bloquear la generación del resto del board."""
    label = "Template 4 — ocultar visualmente si está desactualizado"
    html_path = paths.OUTPUT_DIR / "4_financial_performance.html"
    if not html_path.exists():
        return CheckResult("F3.4", label, "SKIP", f"no existe {html_path}")

    html = html_path.read_text(encoding="utf-8")
    found_label, found_month = extract_financial_performance_title_month(html)
    if found_month is None:
        return CheckResult("F3.4", label, "SKIP",
                            "no se encontró el patrón 'Financial Performance · Mes AAAA' en el <title>")
    if found_month == month:
        return CheckResult("F3.4", label, "PASS", f"'{found_label}' coincide con {month}, no se oculta nada")

    new_html, n_slides = _overlay_stale_slides(html, "board-slide", "Financial Performance", found_label)
    if n_slides == 0:
        return CheckResult("F3.4", label, "SKIP", "no se encontró ningún .board-slide en el HTML")
    html_path.write_text(new_html, encoding="utf-8")

    return CheckResult("F3.4", label, "WARN",
                        f"{n_slides} slides de Financial Performance ocultas con overlay — el título decía "
                        f"'{found_label}' pero se está generando {month}. Avisar a Sofía Maldonado.")


def _flag_stale_discussion_topics(month: str) -> CheckResult:
    """F3.5 — ver nota de módulo. Post-procesa output/2_discussion_topic.html (ya generado por
    generate.py), nunca el .j2 fuente. WARN, no FAIL — mismo criterio que F3.4/F0.6."""
    label = "Discussion Topics — ocultar visualmente si están desactualizados"
    html_path = paths.OUTPUT_DIR / "2_discussion_topic.html"
    if not html_path.exists():
        return CheckResult("F3.5", label, "SKIP", f"no existe {html_path}")

    html = html_path.read_text(encoding="utf-8")
    sentinel_month = extract_updated_for_month_comment(html)
    if sentinel_month is None:
        return CheckResult("F3.5", label, "SKIP",
                            "no se encontró el comentario 'updated_for_month' en el HTML generado")
    if sentinel_month == month:
        return CheckResult("F3.5", label, "PASS", f"marcado como '{sentinel_month}', coincide con {month}")

    new_html, n_slides = _overlay_stale_slides(
        html, ["dt-slide", "slide section-divider"], "Discussion Topics", sentinel_month)
    if n_slides == 0:
        return CheckResult("F3.5", label, "SKIP", "no se encontró ningún .dt-slide/.section-divider en el HTML")
    html_path.write_text(new_html, encoding="utf-8")

    return CheckResult("F3.5", label, "WARN",
                        f"{n_slides} slides de Discussion Topics ocultas con overlay (incluida la portada del "
                        f"tema) — el archivo está marcado como '{sentinel_month}' pero se está generando {month}.")


def run(month: str) -> list[CheckResult]:
    results = []

    proc = _run_script(paths.GENERATE_SCRIPT, deps=("jinja2", "pyyaml"))
    if proc.stdout:
        print(proc.stdout)
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr)
        results.append(CheckResult("F3.1", "generate.py corrió sin errores", "FAIL", f"exit code {proc.returncode}"))
        return results
    results.append(CheckResult("F3.1", "generate.py corrió sin errores", "PASS", ""))

    results.append(_reembed_cr_image(month))
    results.append(_flag_stale_discussion_topics(month))
    results.append(_flag_stale_financial_performance(month))

    proc2 = _run_script(paths.MERGE_SCRIPT, deps=())
    if proc2.stdout:
        print(proc2.stdout)
    if proc2.returncode != 0:
        if proc2.stderr:
            print(proc2.stderr)
        results.append(CheckResult("F3.3", "merge_standalone.py corrió sin errores", "FAIL", f"exit code {proc2.returncode}"))
        return results
    results.append(CheckResult("F3.3", "merge_standalone.py corrió sin errores", "PASS", ""))

    return results
