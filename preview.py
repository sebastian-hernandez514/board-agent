#!/usr/bin/env python3
"""Vista previa (screenshot) de una slide ya generada — sin tocar Template Board.

Pedido del equipo en el workshop del 2026-07-08: que después de un cambio (un highlight, un
comentario, un discussion topic) se pueda "ver" el resultado sin abrir un HTML ni entender qué
es un DOM. Esto lee un archivo que Template Board ya generó en su propia carpeta output/ (nunca
lo escribe, solo lo lee) y guarda un PNG de la slide que coincida con el texto buscado.

Requiere que ya se haya corrido `generate.py --template X` en Template Board — este script no
lo corre por su cuenta.

Uso:
    uv run --with playwright python preview.py --template 3_arr_walk --slide "ARR Core"
    uv run --with playwright python preview.py --template 1_inicio --slide "New Logos"
"""

import argparse
import sys
from pathlib import Path

from board_agent import paths


def _find_matching_slides(page, needle: str):
    needle_lower = needle.lower()
    matches = []
    for s in page.query_selector_all(".slide"):
        text = s.inner_text() or ""
        if needle_lower in text.lower():
            matches.append(s)
    return matches


def screenshot_slide(template: str, needle: str, out_path: Path) -> Path:
    html_path = paths.OUTPUT_DIR / f"{template}.html"
    if not html_path.exists():
        raise FileNotFoundError(
            f"no existe {html_path} — corré 'generate.py --template {template}' en Template Board primero"
        )

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 600})
        page.goto(html_path.resolve().as_uri())
        matches = _find_matching_slides(page, needle)
        if not matches:
            browser.close()
            raise ValueError(f"no se encontró ninguna slide con el texto '{needle}' en {html_path.name}")
        if len(matches) > 1:
            browser.close()
            raise ValueError(
                f"se encontraron {len(matches)} slides que contienen '{needle}' en {html_path.name} — "
                f"sé más específico (ej. el título completo de la slide)"
            )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        matches[0].screenshot(path=str(out_path))
        browser.close()
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Vista previa de una slide ya generada (solo lectura)")
    parser.add_argument("--template", required=True, help="nombre del template sin .html, ej. 3_arr_walk")
    parser.add_argument("--slide", required=True, help="texto que identifica la slide, ej. 'ARR Core'")
    parser.add_argument("--out", default=None, help="dónde guardar el PNG (default: previews/<auto>.png)")
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else (
        Path(__file__).parent / "previews" / f"{args.template}__{args.slide.replace(' ', '_')}.png"
    )
    try:
        result = screenshot_slide(args.template, args.slide, out_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ {e}")
        return 1

    print(f"✅ Vista previa guardada en: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
