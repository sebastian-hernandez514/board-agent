"""Fase 6 — PDF Generation (trigger manual, por diseño).

generate_pdf.py tiene HTML_FILE/PDF_OUT hardcodeados adentro del script (no acepta
argumentos). Desde 2026-07-03, `versioning.save_version()` las actualiza automáticamente
para apuntar a la última versión guardada (ver board_agent/versioning.py) — pero la
generación del PDF en sí sigue siendo manual a propósito: el usuario debe confirmar que
esa versión está aprobada antes de generar el PDF. Este módulo solo LEE esas líneas para
mostrarlas (nunca las escribe) y exige --yes explícito para ejecutar el subprocess.
"""

import re
import subprocess

from . import paths
from .report import CheckResult

_TARGET_RE = re.compile(r'(HTML_FILE|PDF_OUT)\s*=\s*ROOT\s*/\s*"boards"\s*/\s*"([^"]+)"\s*/\s*"([^"]+)"')


def _read_current_targets() -> dict:
    content = paths.PDF_SCRIPT.read_text(encoding="utf-8")
    targets = {}
    for m in _TARGET_RE.finditer(content):
        targets[m.group(1)] = f"boards/{m.group(2)}/{m.group(3)}"
    return targets


def run(confirmed: bool = False) -> CheckResult:
    targets = _read_current_targets()
    html_target = targets.get("HTML_FILE", "<no se pudo leer>")
    pdf_target = targets.get("PDF_OUT", "<no se pudo leer>")
    print(f"generate_pdf.py apunta hoy a:\n  HTML_FILE = {html_target}\n  PDF_OUT   = {pdf_target}")

    if not confirmed:
        return CheckResult(
            "F6", "PDF Generation", "SKIP",
            "no confirmado — si HTML_FILE/PDF_OUT de arriba son la versión correcta a publicar, "
            "correr de nuevo con --pdf --yes. Si no, editarlos a mano en scripts/generate_pdf.py primero.",
        )

    cmd = ["uv", "run", "--with", "playwright", "--with", "pillow", "python3", str(paths.PDF_SCRIPT)]
    proc = subprocess.run(cmd, cwd=paths.BOARD_AGENT_ROOT, capture_output=True, text=True, timeout=900)
    if proc.stdout:
        print(proc.stdout)
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr)
        return CheckResult("F6", "PDF Generation", "FAIL", f"exit code {proc.returncode}")
    return CheckResult("F6", "PDF Generation", "PASS", f"generado: {pdf_target}")
