"""Fase 2 — Metrics Computation. Llama fetch_metrics.py como subprocess (regla del
proyecto: Board Agent nunca reimplementa lógica de Template Board, solo lo invoca)."""

import subprocess
import time

from . import paths
from .report import CheckResult

# Backoff ante "too many connections" en RS (nos pasó en vivo el 2026-07-03) — otros
# fallos de fetch_metrics.py (SQL roto, CSV faltante, etc.) no se reintentan.
_RETRY_BACKOFF_S = [10, 30, 60]


def run(month: str, refresh: bool = False) -> CheckResult:
    cmd = [
        "uv", "run", "--with", "boto3", "--with", "pyyaml", "python3",
        str(paths.FETCH_SCRIPT), "--month", month,
    ]
    if refresh:
        cmd.append("--refresh")

    last_proc = None
    for wait_s in [0] + _RETRY_BACKOFF_S:
        if wait_s:
            print(f"  ⏳ fetch_metrics.py falló por conexión RS — reintentando en {wait_s}s…")
            time.sleep(wait_s)
        proc = subprocess.run(cmd, cwd=paths.TEMPLATE_BOARD, capture_output=True, text=True, timeout=600)
        if proc.stdout:
            print(proc.stdout)
        if proc.returncode == 0:
            return CheckResult("F2", "fetch_metrics.py corrió sin errores", "PASS",
                                f"metrics.yaml actualizado para {month}")
        last_proc = proc
        combined = (proc.stdout or "") + (proc.stderr or "")
        if "too many connections" not in combined.lower():
            break  # no es un error transitorio de conexión — no tiene sentido reintentar

    if last_proc.stderr:
        print(last_proc.stderr)
    return CheckResult("F2", "fetch_metrics.py corrió sin errores", "FAIL", f"exit code {last_proc.returncode}")
