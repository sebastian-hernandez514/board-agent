"""update_appendix.py — Agrega el mes nuevo a los arrays de churn por tenure en 8_appendix.j2

Migración 2026-07-10: este script ya no habla con Redshift ni con AWS CLI (tenía su propio
acceso directo, hardcodeado a un usuario personal — encontrado y cerrado en la migración a
Metabase, ver memory/project_board_agent.md). Ahora lee filas ya obtenidas por Claude Code
vía el MCP de Metabase desde data/.metabase_cache.json → cache["appendix"][month] — poblalo
antes de correr este script (ver board_agent/metabase_fetch_spec.py, misma query que
_SQL_CHURN_TENURE de fetch_metrics.py, sin el bucket "bop" que esa usa).

Uso:
    uv run --with pyyaml python3 scripts/update_appendix.py --month 2026-06
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
TEMPLATE = ROOT / "templates" / "8_appendix.j2"
METABASE_CACHE_FILE = ROOT / "data" / ".metabase_cache.json"

M13_PLUS = {"M13-M15","M16-M18","M19-M24","M25-M30","M31-M36","M37-M42","M43-M48","M49+"}
HTML_BRACKETS = ["M1-M3","M4-M6","M7-M9","M10-M12","M13+"]
MONTH_SHORT = {
    "01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May","06":"Jun",
    "07":"Jul","08":"Aug","09":"Sep","10":"Oct","11":"Nov","12":"Dec",
}


def get_results(month: str) -> list[dict]:
    """Filas de {segmento, bracket, logos_churn} para `month` — puebladas por Claude Code vía
    el MCP de Metabase (misma lógica que _SQL_CHURN_TENURE en scripts/fetch_metrics.py,
    aplicada a un solo mes). No corre ninguna query en vivo."""
    if not METABASE_CACHE_FILE.exists():
        raise SystemExit(
            f"No existe {METABASE_CACHE_FILE} — Claude Code debe correr la query MBQL de churn por "
            f"tenure para {month} vía el MCP de Metabase y escribirla en cache['appendix']['{month}'] "
            "(ver board_agent/metabase_fetch_spec.py)."
        )
    cache = json.loads(METABASE_CACHE_FILE.read_text(encoding="utf-8"))
    rows = cache.get("appendix", {}).get(month)
    if rows is None:
        raise SystemExit(
            f"Falta cache['appendix']['{month}'] en {METABASE_CACHE_FILE.name} — corré la query MBQL "
            "correspondiente vía el MCP de Metabase y agregala al cache antes de continuar."
        )
    return rows


def aggregate(rows: list[dict]) -> dict[str, dict[str, int]]:
    agg: dict = defaultdict(int)
    for r in rows:
        b = "M13+" if r["bracket"] in M13_PLUS else r["bracket"]
        agg[(r["segmento"], b)] += int(r["logos_churn"] or 0)

    out: dict = {"Global": {}, "Core": {}, "Lite": {}}
    for b in HTML_BRACKETS:
        out["Core"][b]   = agg.get(("Core", b), 0)
        out["Lite"][b]   = agg.get(("Lite", b), 0)
        out["Global"][b] = (agg.get(("Core", b), 0)
                           + agg.get(("Lite", b), 0)
                           + agg.get(("Otro", b), 0))
    return out


def patch_section(section_text: str, bracket_vals: dict[str, int]) -> str:
    """Agrega un valor al final de cada array de bracket dentro de un bloque de segmento."""
    for b in HTML_BRACKETS:
        v = bracket_vals[b]
        pattern = re.compile(
            r'("' + re.escape(b) + r'":\s*\[[^\]]*?)(\])',
            re.MULTILINE,
        )
        section_text, n = pattern.subn(
            lambda m, _v=v: f"{m.group(1)},{_v}{m.group(2)}",
            section_text, count=1,
        )
        if n == 0:
            sys.exit(f"No encontré bracket {b!r}")
    return section_text


def patch_template(month: str, vals: dict[str, dict[str, int]]) -> None:
    yyyy, mm = month.split("-")
    label = MONTH_SHORT[mm] if yyyy == "2026" else f"{MONTH_SHORT[mm]} {yyyy[-2:]}"

    text = TEMPLATE.read_text()

    # 1) MONTHS array
    text = re.sub(
        r"(const MONTHS = \[[^\]]*?)(\];)",
        lambda m: f"{m.group(1)},'{label}'{m.group(2)}",
        text, count=1,
    )

    # 2) DATA arrays — partir el bloque DATA por segmento para evitar
    #    que el regex de un segmento modifique el bloque del siguiente
    seg_order = ["Global", "Core", "Lite"]
    # Encontrar inicio de cada bloque de segmento dentro del objeto DATA
    positions = []
    for seg in seg_order:
        pat = re.compile(r'\b' + re.escape(seg) + r'\s*:\s*\{')
        m = pat.search(text)
        if not m:
            sys.exit(f"No encontré sección {seg!r} en el template")
        positions.append(m.start())

    # Procesar cada sección por separado (de atrás hacia adelante para no desplazar índices)
    for i in reversed(range(len(seg_order))):
        seg = seg_order[i]
        start = positions[i]
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        section = text[start:end]
        section = patch_section(section, vals[seg])
        text = text[:start] + section + text[end:]

    TEMPLATE.write_text(text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="YYYY-MM (ej: 2026-06)")
    args = ap.parse_args()

    if not re.match(r"^\d{4}-\d{2}$", args.month):
        sys.exit("Formato esperado: YYYY-MM")

    print(f"→ Leyendo churn por tenure para {args.month} del cache de Metabase")
    rows = get_results(args.month)
    print(f"  {len(rows)} filas")
    vals = aggregate(rows)

    print(f"\nValores {args.month}:")
    for seg in ["Global", "Core", "Lite"]:
        print(f"  {seg:6s}: " + "  ".join(f"{b}={vals[seg][b]}" for b in HTML_BRACKETS))

    patch_template(args.month, vals)
    print(f"\n✓ {TEMPLATE.name} actualizado")
    print("  Correr: uv run --with jinja2 --with pyyaml python3 scripts/generate.py --template 8_appendix")


if __name__ == "__main__":
    main()
