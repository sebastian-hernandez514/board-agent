"""Fase 3 — HTML Builder. generate.py + re-embed imagen Costa Rica + merge_standalone.py.

El paso de re-embed existe porque generate.py sobrescribe 2_discussion_topic.html con una
ruta relativa a la imagen CRI que queda rota en el standalone — es el paso manual que
"siempre se rompe" según memory/project_board_pipeline.md. Automatizarlo acá lo elimina.
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


def _reembed_cr_image(month: str) -> CheckResult:
    img_path = paths.DATA_DIR / "assets" / month / "cr-landing-icp.png"
    html_path = paths.OUTPUT_DIR / "2_discussion_topic.html"
    if not img_path.exists():
        return CheckResult("F3.2", "Re-embed imagen Costa Rica", "WARN", f"no existe {img_path} — slide queda con imagen rota")
    if not html_path.exists():
        return CheckResult("F3.2", "Re-embed imagen Costa Rica", "FAIL", f"no existe {html_path} — ¿corrió generate.py?")
    b64 = base64.b64encode(img_path.read_bytes()).decode()
    html = html_path.read_text(encoding="utf-8")
    new_html = re.sub(r'src="[^"]*cr-landing-icp\.png"', f'src="data:image/png;base64,{b64}"', html)
    html_path.write_text(new_html, encoding="utf-8")
    return CheckResult("F3.2", "Re-embed imagen Costa Rica", "PASS", "")


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
