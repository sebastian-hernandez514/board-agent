#!/usr/bin/env python3
"""CI — smoke test de render + linter estructural para los templates que cambiaron en un PR.

No corre contra Metabase/RS — usa un fixture congelado (tests/fixtures/metrics_sample.yaml)
solo para poder invocar generate.py sin depender de credenciales en CI. Esto NO valida
corrección de datos (eso lo sigue haciendo Fase 4 local, con datos reales) — valida que el
render no truene por un error real (returncode 1/2 de generate.py) y que el HTML resultante
no tenga daño estructural (ids duplicados, tags desbalanceados, referencias huérfanas
canvas<->script — ver board_agent/structural_lint.py).

Uso: uv run --with jinja2 --with pyyaml python3 scripts/ci_render_check.py --templates 3_arr_walk,6_rd
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from board_agent import structural_lint  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--templates", required=True, help="lista separada por coma, ej. '3_arr_walk,6_rd'")
    parser.add_argument("--fixture", default=str(ROOT / "tests" / "fixtures" / "metrics_sample.yaml"))
    args = parser.parse_args()

    metrics_yaml = ROOT / "data" / "metrics.yaml"
    metrics_yaml.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.fixture, metrics_yaml)

    templates = [t.strip() for t in args.templates.split(",") if t.strip()]
    proc = subprocess.run(
        ["uv", "run", "--with", "jinja2", "--with", "pyyaml", "python3",
         str(ROOT / "scripts" / "generate.py"), "--template", ",".join(templates)],
        cwd=ROOT, capture_output=True, text=True,
    )
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr)
        print(f"❌ generate.py salió con código {proc.returncode}")
        return 1

    problems = []
    for stem in templates:
        html_path = ROOT / "output" / f"{stem}.html"
        if not html_path.exists():
            continue
        html = html_path.read_text(encoding="utf-8")

        dupes = structural_lint.check_duplicate_ids(html)
        if dupes:
            problems.append(f"{stem}: ids duplicados {dupes}")

        unbalanced = structural_lint.check_balanced_tags(html)
        if unbalanced:
            problems.append(f"{stem}: tags desbalanceados {unbalanced}")

        orphans = structural_lint.check_orphaned_references(html)
        if orphans["canvases_sin_script"]:
            problems.append(f"{stem}: canvases sin script {orphans['canvases_sin_script']}")
        if orphans["scripts_a_id_inexistente"]:
            problems.append(f"{stem}: scripts a id inexistente {orphans['scripts_a_id_inexistente']}")

    if problems:
        print("❌ Linter estructural encontró problemas:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("✅ Render limpio, sin problemas estructurales.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
