#!/usr/bin/env python3
"""Board Agent — CLI de entrada.

Regla general: no modifica nada dentro de ../Template Board/, solo lee sus archivos
o lo invoca como subproceso (fetch_metrics.py, generate.py, merge_standalone.py,
generate_pdf.py). Única excepción autorizada: el flujo default guarda cada corrida
como versión nueva en boards/YYYY-MM/ (ver board_agent/versioning.py) y actualiza
HTML_FILE/PDF_OUT en generate_pdf.py para que apunten ahí — aprobado explícitamente
por el usuario 2026-07-03.

Uso:
    # Flujo completo: Fase 0→1→2→3→4→5 encadenado (para en el primer FAIL bloqueante),
    # guarda automáticamente como versión nueva en boards/YYYY-MM/ al final
    uv run --with pyyaml --with boto3 python run.py --month 2026-05 [--refresh]

    # Solo Fase 4 (Validator) sobre el metrics.yaml/board ya generados
    uv run --with pyyaml --with boto3 python run.py --validate-only --month 2026-05

    # Solo Fase 5 (Diff Review) sobre el metrics.yaml actual
    uv run --with pyyaml python run.py --diff-only --month 2026-05

    # Fase 6 (PDF) — primero sin --yes para ver a qué versión apunta generate_pdf.py hoy,
    # después con --yes para ejecutarlo de verdad (requiere aprobación humana explícita)
    uv run --with pyyaml python run.py --pdf
    uv run --with pyyaml python run.py --pdf --yes
"""

import argparse
import sys
from datetime import date

from board_agent import (
    paths, phase0_gate, phase1_freshness, phase2_metrics, phase3_html_builder,
    phase4_validator, phase5_diff, phase6_pdf, versioning,
)
from board_agent.report import print_report


def _default_month() -> str:
    """Mes objetivo por defecto: el mes actual (el próximo board a preparar)."""
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Board Agent — orquestador del pipeline de Template Board")
    parser.add_argument("--month", default=_default_month(), help="Mes objetivo YYYY-MM (default: mes actual)")
    parser.add_argument("--validate-only", action="store_true",
                         help="Corre solo Fase 4 (Validator) sobre el metrics.yaml/board ya generados")
    parser.add_argument("--diff-only", action="store_true",
                         help="Corre solo Fase 5 (Diff Review) sobre el metrics.yaml actual")
    parser.add_argument("--refresh", action="store_true",
                         help="Pasa --refresh a fetch_metrics.py (bypass cache de Redshift)")
    parser.add_argument("--pdf", action="store_true",
                         help="Corre Fase 6 (PDF) — muestra HTML_FILE/PDF_OUT actuales de generate_pdf.py")
    parser.add_argument("--yes", action="store_true",
                         help="Confirma la ejecución de --pdf (si no, solo muestra los targets)")
    args = parser.parse_args()

    ok = True

    if args.pdf:
        print("Board Agent — Fase 6 (PDF Generation)")
        result = phase6_pdf.run(confirmed=args.yes)
        ok = print_report("FASE 6 — PDF Generation", [result]) and ok
        return 0 if ok else 1

    if args.diff_only:
        print("Board Agent — Fase 5 (Diff Review) sobre metrics.yaml actual")
        results = phase5_diff.run()
        ok = print_report("FASE 5 — Diff Review", results) and ok
        return 0 if ok else 1

    if args.validate_only:
        print("Board Agent — Fase 4 (Validator) sobre metrics.yaml actual (cutoff configurado en Template Board)")
        results = phase4_validator.run()
        ok = print_report("FASE 4 — Business Rules Validator", results) and ok
        return 0 if ok else 1

    print(f"Board Agent — mes objetivo: {args.month}")
    print(f"(Template Board apunta hoy a: leer {paths.CONFIG_YAML} para ver el período configurado)")

    gate_results = phase0_gate.run(args.month)
    ok = print_report("FASE 0 — Human Inputs Gate", gate_results) and ok

    freshness_results = phase1_freshness.run(args.month)
    ok = print_report("FASE 1 — Data Freshness Check", freshness_results) and ok

    if not ok:
        print("\n❌ Hay checks bloqueantes (FAIL) en Fase 0 o Fase 1 — no se puede avanzar a generar el board.")
        return 1

    metrics_result = phase2_metrics.run(args.month, refresh=args.refresh)
    ok = print_report("FASE 2 — Metrics Computation", [metrics_result]) and ok
    if not ok:
        print("\n❌ fetch_metrics.py falló — no se puede avanzar a generar el HTML.")
        return 1

    html_results = phase3_html_builder.run(args.month)
    ok = print_report("FASE 3 — HTML Builder", html_results) and ok
    if not ok:
        print("\n❌ La generación de HTML falló — no se puede validar un board a medio generar.")
        return 1

    validator_results = phase4_validator.run()
    ok = print_report("FASE 4 — Business Rules Validator", validator_results) and ok

    diff_results = phase5_diff.run()
    # Fase 5 es informativa (WARN, no bloquea) — no participa del `ok` final.
    print_report("FASE 5 — Diff Review", diff_results)

    # Versionado automático — se guarda pase o no pase el Validator (ver
    # memory/project_board_agent.md, decisión 2026-07-03): un board que falló la
    # validación sigue siendo un checkpoint útil del historial.
    saved = versioning.save_version(args.month, validator_results, diff_results)
    print(f"\n📦 Guardado como v{saved['version']} en {saved['html'].parent}:")
    print(f"   {saved['html'].name}")
    print(f"   {saved['metrics'].name}")
    print(f"   {saved['report'].name}")
    print(f"   generate_pdf.py actualizado → apunta a esta versión (correr --pdf --yes cuando esté aprobado)")

    print("\nFase 6 (PDF) — correr aparte con --pdf (y --yes para ejecutar) cuando el board esté aprobado.")
    if not ok:
        print("\n⚠️  El board se generó pero el Validator encontró FAILs — revisar el reporte antes de publicar.")
    else:
        print("\n✅ Board generado, validado y versionado.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
