#!/usr/bin/env python3
"""
merge_standalone.py — Combina todos los HTML del board en un solo archivo auto-contenido.

Uso:
    uv run python3 scripts/merge_standalone.py

Genera: output/board_standalone.html
"""

import re
from datetime import datetime
from pathlib import Path

ROOT       = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
STYLES_DIR = ROOT / "styles"

# Orden de slides
SLIDE_FILES = [
    "1_inicio.html",
    "2_discussion_topic.html",
    "3_arr_walk.html",
    "4_financial_performance.html",
    "5_go_to_market.html",
    "6_rd.html",
    "7_headcount.html",
    "8_appendix.html",
]


def extract_styles(html: str) -> list[str]:
    """Extrae el contenido de todos los bloques <style>...</style>."""
    return re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL)


def extract_body(html: str) -> str:
    """Extrae el contenido entre <body> y </body>."""
    m = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL)
    return m.group(1).strip() if m else ""


def main():
    # ── Leer base.css
    base_css = (STYLES_DIR / "base.css").read_text(encoding="utf-8")

    all_styles: list[str] = []
    all_bodies: list[str] = []

    # Section covers permanentes — se inyectan antes del template correspondiente
    # independiente de si Finance reemplaza el HTML de ese template.
    SECTION_COVERS = {
        "4_financial_performance.html": """
<style>
  .s04-cover { background:#0F172A; display:flex; flex-direction:column; justify-content:center; padding:0 72px; }
  .s04-cover .eyebrow { font-size:13px; font-weight:600; letter-spacing:0.12em; text-transform:uppercase; color:#30BBB7; margin-bottom:12px; }
  .s04-cover .section-title { font-size:42px; font-weight:700; color:#FFFFFF; line-height:1.15; margin-bottom:14px; }
  .s04-cover .section-sub { font-size:16px; color:#94A3B8; font-weight:400; }
  .s04-cover .slide-num { position:absolute; bottom:24px; right:32px; font-size:11px; color:#475569; font-weight:500; }
</style>
<div class="slide s04-cover">
  <div class="eyebrow">Section 04</div>
  <div class="section-title">Financial Performance</div>
  <div class="section-sub">P&amp;L · OpEx · Revenue Bridge · Cash Flow</div>
  <div class="slide-num">1</div>
</div>
<div class="slide-divider">↓</div>""",
    }

    for fname in SLIDE_FILES:
        fpath = OUTPUT_DIR / fname
        if not fpath.exists():
            print(f"  ⚠️  No encontrado, se omite: {fname}")
            continue
        html = fpath.read_text(encoding="utf-8")
        styles = extract_styles(html)
        body   = extract_body(html)
        all_styles.extend(styles)
        # Inyectar section cover si aplica
        cover = SECTION_COVERS.get(fname, "")
        all_bodies.append(f"\n<!-- ═══ {fname} ═══ -->\n{cover}\n{body}")
        print(f"  ✅ {fname}")

    combined_styles = "\n\n".join(all_styles)
    combined_body   = "\n".join(all_bodies)

    # Inyectar timestamp en la primera slide (cover)
    now = datetime.now().strftime("%d %b %Y, %H:%M")
    timestamp_html = f'<div class="cover-updated">Last updated: {now}</div>'
    combined_body = combined_body.replace(
        '<div class="cover-logo">Alegra</div>',
        f'<div class="cover-logo">Alegra</div>\n    {timestamp_html}',
        1,
    )

    standalone = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Alegra Board</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>

  <style>
/* ── base.css ─────────────────────────────────── */
{base_css}
/* ── timestamp ───────────────────────────────── */
.cover-updated {{
  position: absolute;
  bottom: 28px;
  right: 48px;
  font-size: 10px;
  color: rgba(255,255,255,0.45);
  font-family: 'DM Mono', monospace;
  letter-spacing: 0.04em;
}}
  </style>
  <style>
/* ── estilos por slide ────────────────────────── */
{combined_styles}
  </style>
</head>
<body>
{combined_body}
</body>
</html>
"""

    out = OUTPUT_DIR / "board_standalone.html"
    out.write_text(standalone, encoding="utf-8")
    print(f"\n🎉 Standalone generado: {out.relative_to(ROOT)}")
    print(f"   Tamaño: {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
