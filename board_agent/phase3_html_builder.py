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
"""

import base64
import re
import subprocess

from . import paths
from .phase0_gate import extract_financial_performance_title_month
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


_BOARD_SLIDE_OPEN_RE = re.compile(r'<div class="board-slide">')

_STALE_OVERLAY_STYLE = (
    "<style>.stale-overlay{position:absolute;inset:0;z-index:999;background:#f8fafc;"
    "display:flex;flex-direction:column;align-items:center;justify-content:center;"
    "gap:10px;text-align:center;padding:40px;box-sizing:border-box;}"
    ".stale-overlay .stale-icon{font-size:32px;}"
    ".stale-overlay .stale-title{font-size:20px;font-weight:700;color:#475569;}"
    ".stale-overlay .stale-sub{font-size:14px;color:#94a3b8;max-width:520px;}</style>"
)

_STALE_OVERLAY_HTML = (
    '<div class="stale-overlay"><div class="stale-icon">⏳</div>'
    '<div class="stale-title">Financial Performance — contenido pendiente</div>'
    '<div class="stale-sub">Finance todavía no envía el reporte de este mes '
    '(esta sección mostraba {old_label}) — se ocultó para no publicar el mes equivocado.</div></div>'
)


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

    n_slides = len(_BOARD_SLIDE_OPEN_RE.findall(html))
    if n_slides == 0:
        return CheckResult("F3.4", label, "SKIP", "no se encontró ningún .board-slide en el HTML")

    overlay = _STALE_OVERLAY_HTML.format(old_label=found_label)
    html = _BOARD_SLIDE_OPEN_RE.sub(f'<div class="board-slide" style="position:relative">{overlay}', html)
    if "</head>" in html:
        html = html.replace("</head>", _STALE_OVERLAY_STYLE + "</head>", 1)
    else:
        html = _STALE_OVERLAY_STYLE + html
    html_path.write_text(html, encoding="utf-8")

    return CheckResult("F3.4", label, "WARN",
                        f"{n_slides} slides de Financial Performance ocultas con overlay — el título decía "
                        f"'{found_label}' pero se está generando {month}. Avisar a Sofía Maldonado.")


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
