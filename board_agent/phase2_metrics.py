"""Fase 2 — Metrics Computation. Llama fetch_metrics.py como subprocess (regla del
proyecto: Board Agent nunca reimplementa lógica de Template Board, solo lo invoca).

Migración 2026-07-10: fetch_metrics.py ya no habla con Redshift, así que el retry-con-
backoff que existía acá para "too many connections" (un problema del pool de conexiones
de RS) dejó de aplicar tal cual. fetch_metrics.py ahora falla con un RuntimeError propio
y determinista si el cache de Metabase falta o es de otro mes — eso NO hay que reintentar,
va a fallar igual (test_run_fails_without_retry_when_cache_missing).

Bug corregido 2026-07-14: se había quitado el retry ENTERO, no solo el de RS — cualquier
falla transitoria del propio subproceso (ej. `uv run --with pyyaml` resolviendo el paquete
con una red inestable, sin cache de uv caliente) tumbaba la Fase 2 al primer intento, sin
ninguna chance de recuperarse. Se reintroduce el mismo patrón de antes (backoff corto),
pero el detector de "¿vale la pena reintentar?" ahora es genérico: si fetch_metrics.py
llegó a correr y falló con SU PROPIO RuntimeError (mensaje determinista, no tiene sentido
reintentar — va a fallar igual), no reintenta; cualquier otra falla (el subproceso ni
llegó a correr Python, timeout, error del toolchain de uv, etc.) sí se reintenta."""

import subprocess
import time

from . import paths
from .report import CheckResult

_RETRY_BACKOFF_S = [5, 15]


def run(month: str, refresh: bool = False) -> CheckResult:
    cmd = ["uv", "run", "--with", "pyyaml", "python3", str(paths.FETCH_SCRIPT), "--month", month]
    if refresh:
        cmd.append("--refresh")

    last_proc = None
    for wait_s in [0] + _RETRY_BACKOFF_S:
        if wait_s:
            print(f"  ⏳ fetch_metrics.py falló sin un error propio y determinista — "
                  f"reintentando en {wait_s}s (posible falla transitoria del subproceso)…")
            time.sleep(wait_s)
        proc = subprocess.run(cmd, cwd=paths.BOARD_AGENT_ROOT, capture_output=True, text=True, timeout=600)
        if proc.stdout:
            print(proc.stdout)
        if proc.returncode == 0:
            return CheckResult("F2", "fetch_metrics.py corrió sin errores", "PASS",
                                f"metrics.yaml actualizado para {month}")
        last_proc = proc
        if "RuntimeError:" in (proc.stderr or ""):
            break  # error propio y determinista (cache faltante/mes equivocado) — no reintentar

    if last_proc.stderr:
        print(last_proc.stderr)
    return CheckResult("F2", "fetch_metrics.py corrió sin errores", "FAIL", f"exit code {last_proc.returncode}")
