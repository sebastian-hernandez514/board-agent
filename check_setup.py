#!/usr/bin/env python3
"""Chequeo de arranque para Board Agent — correr esto PRIMERO, antes de intentar generar
un board, sobre todo si es tu primera vez.

No crea, corrige ni instala nada. Solo diagnostica y separa dos problemas que se confunden
fácil (encontrado simulando el flujo de junio-26 desde cero, ver memory/project_board_agent.md):

  1. Herramientas/accesos que TE faltan a ti (uv, AWS CLI, sesión SSO).
  2. Fuentes de datos que están desactualizadas — esto NO es un problema del agente ni tuyo,
     es que alguien (ver el RACI en el Playbook de la wiki) todavía no actualizó su fuente
     ese mes. Si ves un FAIL/WARN acá, avísale a esa persona en vez de asumir que algo se rompió.

Uso:
    uv run --with boto3 --with pyyaml python check_setup.py --month 2026-06
"""

import argparse
import shutil
import subprocess
import sys

from board_agent import phase0_gate, phase1_freshness
from board_agent.report import CheckResult, print_report


def _check_uv() -> CheckResult:
    path = shutil.which("uv")
    if path:
        return CheckResult("S.1", "uv instalado", "PASS", path)
    return CheckResult("S.1", "uv instalado", "FAIL",
                        "instalar desde https://docs.astral.sh/uv/getting-started/installation/")


def _check_aws_cli() -> CheckResult:
    try:
        proc = subprocess.run(["aws", "--version"], capture_output=True, text=True, timeout=10)
    except FileNotFoundError:
        return CheckResult("S.2", "AWS CLI instalado", "FAIL",
                            "comando 'aws' no encontrado — instalar AWS CLI v2 (pedir ayuda a Sebastián si es la primera vez)")
    detail = (proc.stdout or proc.stderr).strip()
    return CheckResult("S.2", "AWS CLI instalado", "PASS", detail)


def main() -> int:
    parser = argparse.ArgumentParser(description="Chequeo de arranque de Board Agent (solo lectura)")
    parser.add_argument("--month", required=True, help="Mes objetivo YYYY-MM del board que quieres generar")
    args = parser.parse_args()

    print(f"Board Agent — chequeo de arranque para {args.month}\n")

    setup_results = [_check_uv(), _check_aws_cli()]
    setup_ok = print_report("HERRAMIENTAS Y ACCESOS", setup_results)

    if not setup_ok:
        print("\n❌ Te falta algo básico (S.1/S.2) — resuelve esto antes de seguir. "
              "Si no sabes cómo, revisa el Playbook del Board en la wiki o pregúntale a Sebastián.")
        return 1

    gate_results = phase0_gate.run(args.month)
    print_report("CONTENIDO EDITORIAL (Fase 0)", gate_results)

    freshness_results = phase1_freshness.run(args.month)
    print_report("FUENTES DE DATOS EN REDSHIFT (Fase 1)", freshness_results)

    n_fail = sum(1 for r in gate_results + freshness_results if r.status == "FAIL")
    n_warn = sum(1 for r in gate_results + freshness_results if r.status == "WARN")

    print(f"\n{'='*60}")
    if n_fail:
        print(f"❌ Hay {n_fail} bloqueante(s). El flujo completo (run.py) NO va a avanzar hasta "
              f"que se resuelvan — revisa el detail de cada FAIL de arriba y avisa al dueño según "
              f"el RACI del Playbook. Esto no significa que el agente esté roto.")
    elif n_warn:
        print(f"⚠️  {n_warn} advertencia(s) — el flujo completo SÍ avanzaría, pero alguna sección "
              f"del board puede salir con datos viejos o contenido sin llenar. Revisar antes de publicar.")
    else:
        print("✅ Todo listo — puedes correr el flujo completo:")
        print(f"   uv run --with boto3 --with pyyaml python run.py --month {args.month}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
