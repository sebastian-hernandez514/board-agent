#!/usr/bin/env python3
"""CI — screenshot de página completa de cada output/<template>.html ya generado, para
publicarlo como artifact del PR (antes/después) — así quien aprueba ve el resultado real
sin tener que correr nada localmente. Requiere `playwright install chromium` ya corrido.

Uso: uv run --with playwright python3 scripts/ci_screenshot.py --templates 3_arr_walk,6_rd --out-dir screenshots/after
"""
import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--templates", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        for stem in [t.strip() for t in args.templates.split(",") if t.strip()]:
            html_path = ROOT / "output" / f"{stem}.html"
            if not html_path.exists():
                print(f"⚠️  no existe {html_path}, se omite screenshot")
                continue
            page.goto(f"file://{html_path}")
            out_path = out_dir / f"{stem}.png"
            page.screenshot(path=str(out_path), full_page=True)
            print(f"📸 {out_path}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
