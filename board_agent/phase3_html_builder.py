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

F3.4/F3.5/F3.6/F3.7/F3.8: tapan visualmente el contenido desactualizado de Template 4
(Financial Performance), Discussion Topics, CEO Highlights, 6_rd (Product Performance + NPS)
y Headcount respectivamente — cada uno con su propia fuente de frescura (título del HTML,
sentinel en comentario, campo YAML, presencia de clave en snapshot). Solo escriben en
output/*.html (el artefacto ya generado por generate.py), nunca en el .j2 fuente.

Refactor 2026-07-09: las 4 funciones originales (F3.4-F3.7, agregadas 2026-07-08) eran casi
idénticas — cada una con su archivo/marcador/sentinel hardcodeado a mano y repetido. A raíz de
una propuesta de Luis Caro en tts-bi-data (formato `deck.md` con metadatos declarados por
slide en vez de enterrados en código), se extrajo el patrón compartido a
`slide_registry.py`: un registro declarativo (`SLIDE_SPECS`) + un motor genérico
(`check_stale_slide`). Agregar Headcount (F3.8) fue agregar una entrada a la lista, no
escribir 30 líneas nuevas — ver slide_registry.py para el detalle completo y la nota de
crédito a la propuesta que lo motivó.
"""

import base64
import re
import subprocess

from . import paths
from .report import CheckResult
from .slide_registry import SLIDE_SPECS, check_stale_slide


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


_SPEC_BY_ID = {spec.check_id: spec for spec in SLIDE_SPECS}


def _flag_stale_ceo_highlights(month: str) -> CheckResult:
    """F3.6 — ver slide_registry.py para la lógica completa (registro + motor genérico)."""
    return check_stale_slide(_SPEC_BY_ID["F3.6"], month)


def _flag_stale_discussion_topics(month: str) -> CheckResult:
    """F3.5 — ver slide_registry.py."""
    return check_stale_slide(_SPEC_BY_ID["F3.5"], month)


def _flag_stale_financial_performance(month: str) -> CheckResult:
    """F3.4 — ver slide_registry.py."""
    return check_stale_slide(_SPEC_BY_ID["F3.4"], month)


def _flag_stale_nps(month: str) -> CheckResult:
    """F3.7 — ver slide_registry.py."""
    return check_stale_slide(_SPEC_BY_ID["F3.7"], month)


def _flag_stale_headcount(month: str) -> CheckResult:
    """F3.8 (agregada 2026-07-09) — Headcount tenía el mismo hueco que Discussion Topics antes
    de su fix: comentarios de Highlights/Lowlights escritos a mano en 7_headcount.j2, sin
    ningún YAML ni sentinel. Ver slide_registry.py para la lógica completa."""
    return check_stale_slide(_SPEC_BY_ID["F3.8"], month)


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
    results.append(_flag_stale_ceo_highlights(month))
    results.append(_flag_stale_discussion_topics(month))
    results.append(_flag_stale_financial_performance(month))
    results.append(_flag_stale_nps(month))
    results.append(_flag_stale_headcount(month))

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
