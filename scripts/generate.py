#!/usr/bin/env python3
"""
generate.py — Render Jinja2 templates into HTML

Usage:
    uv run --with jinja2 --with pyyaml python3 scripts/generate.py
    uv run --with jinja2 --with pyyaml python3 scripts/generate.py --template 3_arr_walk

Reads:
    data/metrics.yaml          (from fetch_metrics.py)
    data/editorial/*.yaml      (editorial content — human-filled)
    data/config.yaml           (board configuration: month, quarter labels)

Writes:
    output/<template_name>.html
"""

import argparse, base64, json, re, sys
from pathlib import Path
from datetime import datetime

import yaml
from jinja2 import ChainableUndefined, Environment, FileSystemLoader, Undefined

ROOT       = Path(__file__).parent.parent
TMPL_DIR   = ROOT / "templates"
DATA_DIR   = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

# Un dato en None a 2+ niveles de profundidad (ej. metrics.nps.costa_rica_trend.name
# cuando metrics.nps es None — pasó de verdad con NPS) no debe poder tumbar el render()
# de TODO el archivo — Jinja2 con Undefined por defecto lanza UndefinedError en el segundo
# nivel de encadenamiento, y como generate.py renderiza cada .j2 en una sola llamada, eso
# se lleva puestas las demás slides del mismo archivo. ChainableUndefined (Jinja2 built-in,
# hecho para esto) permite encadenar sin explotar; _TrackingUndefined además registra cada
# ocurrencia para que no desaparezca en silencio — ver board_agent/phase3_html_builder.py (F3.9).
_missing_fields: list[str] = []


class _TrackingUndefined(ChainableUndefined):
    def __str__(self) -> str:
        name = self._undefined_name or "?"
        if name not in _missing_fields:
            _missing_fields.append(name)
        return super().__str__()


def _load_nps_images(period: str) -> list[str]:
    """Lee nps_1.png, nps_2.png, nps_3.png de data/assets/{period}/ y devuelve data URIs base64."""
    assets_dir = DATA_DIR / "assets" / period
    images = []
    for i in range(1, 10):
        p = assets_dir / f"nps_{i}.png"
        if not p.exists():
            break
        b64 = base64.b64encode(p.read_bytes()).decode()
        images.append(f"data:image/png;base64,{b64}")
    return images

# ── Load YAML helper ───────────────────────────────────────────────────────────
def _load(path):
    if not path.exists():
        print(f"  ⚠️  No existe: {path}")
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

# ── Merge editorial asks into metrics.arr_walk_products ───────────────────────
def _merge_arr_walk_editorial(metrics, arr_walk_ed):
    prod_by_id = {p["id"]: p for p in metrics.get("arr_walk_products", [])}
    for ep in arr_walk_ed.get("products", []):
        pid = ep.get("id")
        if pid in prod_by_id:
            prod_by_id[pid]["asks"]         = ep.get("asks", [])
            prod_by_id[pid]["action_title"] = ep.get("action_title", prod_by_id[pid]["action_title"])
    # Global ARR walk title
    if "global_title" in arr_walk_ed:
        metrics["arr_walk_headline"] = arr_walk_ed["global_title"]
    # Alanube editorial
    if "alanube_title"   in arr_walk_ed:
        metrics.setdefault("alanube_title",   arr_walk_ed["alanube_title"])
    if "alanube_insight" in arr_walk_ed:
        metrics.setdefault("alanube_insight", arr_walk_ed["alanube_insight"])

# ── tojson Jinja2 filter ───────────────────────────────────────────────────────
def _tojson(value, indent=None):
    # Undefined llega hasta acá como objeto Python plano, fuera del encadenamiento
    # de Jinja2 (json.dumps no lo sabe serializar) — mismo motivo que el guard de abajo.
    if isinstance(value, Undefined):
        return "null"
    return json.dumps(value, ensure_ascii=False, indent=indent)

# ── hl_split Jinja2 filter ─────────────────────────────────────────────────────
def _hl_split(text, cls):
    """Bold the lead up to the first '.', ',', or ' —'."""
    if isinstance(text, Undefined):
        return ""
    m = re.search(r'\.| —', text)
    if m:
        end = m.end()
        return f'<span class="{cls}">{text[:end]}</span>{text[end:]}'
    return text

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", default=None,
                        help="Render solo estos templates, separados por coma (sin extensión). Default: todos.")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load data sources
    metrics  = _load(DATA_DIR / "metrics.yaml")
    config   = _load(DATA_DIR / "config.yaml")
    editorial = {
        "highlights":       [],
        "lowlights":        [],
        "rule_of_40":       "",
        "monthly_headline": "",
        "ceo_title":        "CEO Highlights & Lowlights",
        "pp_focus":         [],
        "pp_risks":         [],
        "pt_bullets":       [],
        "alanube_title":    "Alanube ARR Walk",
        "alanube_insight":  "",
        **_load(DATA_DIR / "editorial" / "ceo.yaml"),
    }
    editorial["topics"] = _load(DATA_DIR / "editorial" / "discussion_topics.yaml").get("topics", [])

    # Merge ARR Walk editorial
    arr_walk_ed = _load(DATA_DIR / "editorial" / "arr_walk.yaml")
    _merge_arr_walk_editorial(metrics, arr_walk_ed)
    editorial["alanube_title"]   = arr_walk_ed.get("alanube_title",   editorial["alanube_title"])
    editorial["alanube_insight"] = arr_walk_ed.get("alanube_insight", editorial["alanube_insight"])

    # NPS images — data/assets/{period}/nps_1.png, nps_2.png, nps_3.png
    period = config.get("period") or metrics.get("cutoff_month", "")
    editorial["nps_images"] = _load_nps_images(period)
    if editorial["nps_images"]:
        print(f"  🖼️  NPS images: {len(editorial['nps_images'])} imágenes cargadas desde data/assets/{period}/")
    else:
        print(f"  ⚠️  NPS images: no se encontraron en data/assets/{period}/")

    # ── Default config if not present
    if not config:
        cutoff = metrics.get("cutoff_month", "2026-02")
        mo  = int(cutoff[5:])
        yr  = cutoff[:4]
        _MONTHS = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]
        config = {
            "month_label":   f"{_MONTHS[mo-1]} {yr}",
            "quarter_label": f"{(mo-1)//3 + 1}Q{yr[2:]}",
            "prev_year":     str(int(yr) - 1),
        }

    # ── Jinja2 environment
    env = Environment(loader=FileSystemLoader(str(TMPL_DIR)), autoescape=False,
                       undefined=_TrackingUndefined)
    env.filters["tojson"]   = _tojson
    env.filters["hl_split"] = _hl_split
    env.filters["safe"]     = lambda v: v  # already safe (no autoescaping)

    ctx = {"metrics": metrics, "config": config, "editorial": editorial}

    # ── Render templates
    templates = sorted(TMPL_DIR.glob("*.j2"))
    if args.template:
        wanted = {t.strip() for t in args.template.split(",") if t.strip()}
        matched = [t for t in templates if t.stem in wanted]
        not_found = wanted - {t.stem for t in matched}
        if not_found:
            print(f"❌ Template(s) no encontrado(s) en {TMPL_DIR}: {', '.join(sorted(not_found))}")
            return 1
        templates = matched

    failed_templates: list[str] = []
    missing_by_template: dict[str, list[str]] = {}

    for tmpl_path in templates:
        tmpl_name = tmpl_path.stem
        _missing_fields.clear()
        try:
            tmpl  = env.get_template(tmpl_path.name)
            html  = tmpl.render(**ctx)
            out_f = OUTPUT_DIR / f"{tmpl_name}.html"
            out_f.write_text(html, encoding="utf-8")
            print(f"  ✅ {out_f.relative_to(ROOT)}")
            if _missing_fields:
                missing_by_template[tmpl_name] = list(_missing_fields)
        except Exception as e:
            print(f"  ❌ {tmpl_name}: {e}")
            failed_templates.append(tmpl_name)

    for tmpl_name, fields in missing_by_template.items():
        print(f"MISSING_FIELDS {tmpl_name}: {', '.join(fields)}")

    print(f"\n🎉 HTML generado en {OUTPUT_DIR}/")

    if failed_templates:
        print(f"FALLARON: {', '.join(failed_templates)}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
