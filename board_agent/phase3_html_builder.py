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
"""

import base64
import re
import subprocess

from . import paths
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
