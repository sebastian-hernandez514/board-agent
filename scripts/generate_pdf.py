#!/usr/bin/env python3
"""
generate_pdf.py — Genera el PDF del board con alta calidad (3x resolución).

Requisitos:
    uv run --with playwright --with pillow python scripts/generate_pdf.py

IMPORTANTE — Por qué este enfoque:
  El HTML del board es un scroll vertical de slides con padding/gaps entre ellos.
  El método nativo de Playwright (page.pdf()) corta los slides porque el contenido
  no está alineado a múltiplos exactos del alto de página.

  Solución: capturar cada elemento de slide individualmente con element.screenshot()
  a 3x de resolución (2880x1620px), luego combinar las imágenes en un PDF con Pillow.
  Esto garantiza:
    - Cada página = exactamente un slide (960x540px lógicos)
    - Sin cortes ni desbordamientos
    - Calidad alta (~288 DPI efectivos en impresión)

CRÍTICO — Selector de slides:
  No todos los templates usan la clase `.slide`. Mapa actual:
    .slide      → 1_inicio, 2_discussion_topic, 3_arr_walk, 4_financial_performance, 6_rd, 8_appendix
    .gtm-slide  → 5_go_to_market
    .hc-slide   → 7_headcount
  Si se agrega un nuevo template, verificar su clase y añadirla al selector de abajo.
"""

import asyncio, io, os
from pathlib import Path
from playwright.async_api import async_playwright
from PIL import Image

ROOT       = Path(__file__).resolve().parent.parent
HTML_FILE = ROOT / "boards" / "2026-06" / "board_Jun_2026_v19.html"
PDF_OUT = ROOT / "boards" / "2026-06" / "board_Jun_2026_v19.pdf"
SCALE      = 4   # 4x → 3840x2160px por slide (4K/UHD, ~384 DPI — sobre el estándar de impresión 300 DPI)
WAIT_MS    = 4000  # tiempo para que Chart.js termine de renderizar

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": 960, "height": 540},
            device_scale_factor=SCALE,
        )
        url = "file://" + str(HTML_FILE).replace(" ", "%20")
        await page.goto(url)
        await page.wait_for_timeout(WAIT_MS)

        # Incluye todos los tipos de slide: .slide, .gtm-slide (go_to_market), .hc-slide (headcount), .board-slide (financial_performance), .dt-slide (discussion_topic)
        slides = await page.query_selector_all(".slide, .gtm-slide, .hc-slide, .board-slide, .dt-slide")
        print(f"Capturando {len(slides)} slides a {SCALE}x resolución...")

        images = []
        for i, slide in enumerate(slides):
            png = await slide.screenshot(type="png")
            img = Image.open(io.BytesIO(png)).convert("RGB")
            images.append(img)
            print(f"  [{i+1}/{len(slides)}] {img.size[0]}x{img.size[1]}px")

        await browser.close()

        # resolution=384 → 960px * 4x / 384dpi = 10 pulgadas de ancho (4K, correcto)
        images[0].save(
            str(PDF_OUT),
            save_all=True,
            append_images=images[1:],
            resolution=384,
        )

        size_mb = os.path.getsize(PDF_OUT) / 1e6
        print(f"\nPDF generado: {PDF_OUT}")
        print(f"Tamaño: {size_mb:.1f} MB | Slides: {len(images)} | Resolución: {images[0].size[0]}x{images[0].size[1]}px")

if __name__ == "__main__":
    asyncio.run(main())
