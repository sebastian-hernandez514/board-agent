"""Registro declarativo de slides propensas a quedar desactualizadas (Fase 3).

Nace de una idea de Luis Caro en tts-bi-data (2026-07-09, propuesta `deck.md`/`::: meta`):
declarar los metadatos de cada slide en un solo lugar en vez de enterrarlos en código. No
adoptamos su formato completo (JSON de chart + renderer genérico) — nuestros charts ya jalan
solos desde Redshift, no hay nada que un PO edite ahí a mano; el problema real que sí
compartíamos era tener 4 funciones casi-idénticas (F3.4/F3.5/F3.6/F3.7), cada una con su
archivo/marcador/sentinel hardcodeado a mano y repetido.

Este módulo reemplaza esas 4 funciones por una sola (`check_stale_slide`) que recorre
`SLIDE_SPECS` — agregar una slide nueva (como Headcount, F3.8) es agregar una entrada a la
lista, no escribir 30 líneas nuevas.

Sigue el mismo principio de siempre: solo lee/escribe `Template Board/output/*.html` (el
artefacto ya generado por generate.py) o YAMLs editoriales (datos, no código fuente) — nunca
toca el .j2 fuente de Template Board.
"""

import re
from dataclasses import dataclass
from typing import Callable, Optional

import yaml

from . import paths
from .phase0_gate import extract_financial_performance_title_month, extract_updated_for_month_comment
from .report import CheckResult

_STALE_OVERLAY_STYLE = (
    "<style>.stale-slide{position:relative !important;}"
    ".stale-overlay{position:absolute;inset:0;z-index:999;background:#f8fafc;"
    "display:flex;flex-direction:column;align-items:center;justify-content:center;"
    "gap:10px;text-align:center;padding:40px;box-sizing:border-box;}"
    ".stale-overlay .stale-icon{font-size:32px;}"
    ".stale-overlay .stale-title{font-size:20px;font-weight:700;color:#475569;}"
    ".stale-overlay .stale-sub{font-size:14px;color:#94a3b8;max-width:520px;}</style>"
)

_STALE_OVERLAY_HTML = (
    '<div class="stale-overlay"><div class="stale-icon">⏳</div>'
    '<div class="stale-title">{section} — contenido pendiente</div>'
    '<div class="stale-sub">Esta sección mostraba {old_label} — se ocultó para no publicar '
    'el mes equivocado.</div></div>'
)

_MARKER_SEARCH_WINDOW = 2000


def _overlay_stale_slides(html: str, slide_classes, section: str, old_label: str) -> tuple[str, int]:
    """Cubre cada slide de `slide_classes` (un string o una lista de strings — ej. la portada
    de un topic Y sus slides de contenido) con un overlay "contenido pendiente", sin borrar ni
    reescribir el HTML anidado existente debajo (evita el riesgo de romper la estructura con
    regex de reemplazo) — le agrega la clase marcadora `stale-slide` (position:relative, ver
    _STALE_OVERLAY_STYLE) e inserta el overlay como hijo justo después del tag de apertura.
    Devuelve (html_modificado, cantidad_de_slides_tapadas). 0 slides → no modifica nada."""
    if isinstance(slide_classes, str):
        slide_classes = [slide_classes]

    overlay = _STALE_OVERLAY_HTML.format(section=section, old_label=old_label)
    total = 0
    for slide_class in slide_classes:
        open_re = re.compile(r'<div class="' + re.escape(slide_class) + r'"[^>]*>')
        n = len(open_re.findall(html))
        if n == 0:
            continue
        total += n

        def _inject(m, _cls=slide_class):
            tag = m.group(0).replace(f'class="{_cls}"', f'class="{_cls} stale-slide"', 1)
            return tag + overlay

        html = open_re.sub(_inject, html)

    if total == 0:
        return html, 0
    if "</head>" in html:
        html = html.replace("</head>", _STALE_OVERLAY_STYLE + "</head>", 1)
    else:
        html = _STALE_OVERLAY_STYLE + html
    return html, total


def _replace_stale_body_with_placeholder(html: str, section: str, old_label: str,
                                          n_placeholder_slides: int = 2) -> tuple[str, int]:
    """Para secciones cuyo CONTENIDO real varía en cantidad mes a mes (ej. Discussion Topics
    puede tener 1, 2 o 3 topics = 3, 6 o 9 slides distintas) — en vez de tapar cada slide
    existente (lo que llenaría el board con tantos "contenido pendiente" como topics tenía
    el mes anterior), reemplaza TODO el <body> por un esqueleto FIJO: una portada genérica de
    sección + `n_placeholder_slides` slides vacías tapadas — siempre el mismo tamaño, sin
    importar cuánto contenido había antes. Pedido explícito del usuario (2026-07-24): "así no
    estén debe salir la portada... y 2 slides vacías... porque si no llenamos el board de
    slides vacías" (F3.5, Discussion Topics). Devuelve (html_modificado,
    n_placeholder_slides) — o (html, 0) si no encuentra <body>."""
    body_match = re.search(r"<body>.*</body>", html, re.S)
    if not body_match:
        return html, 0

    overlay = _STALE_OVERLAY_HTML.format(section=section, old_label=old_label)
    cover = (
        '<div class="slide section-divider">'
        '<div class="eyebrow">Discussion Topic</div>'
        f'<div class="section-title">{section}</div>'
        '<div class="slide-num">1</div>'
        '</div>'
        '<div class="slide-divider">↓</div>'
    )
    placeholders = "".join(
        f'<div class="dt-slide stale-slide">{overlay}</div>'
        for _ in range(n_placeholder_slides)
    )
    new_body = f"<body>{cover}{placeholders}</body>"
    html = html[:body_match.start()] + new_body + html[body_match.end():]
    if "</head>" in html:
        html = html.replace("</head>", _STALE_OVERLAY_STYLE + "</head>", 1)
    else:
        html = _STALE_OVERLAY_STYLE + html
    return html, n_placeholder_slides


def _overlay_single_slide_by_marker(html: str, marker_text: str, slide_class: str,
                                     section: str, old_label: str) -> tuple[str, int]:
    """Para slides SIN clase propia (comparten `slide_class` con otras slides del mismo
    archivo, ej. CEO Highlights en 1_inicio.j2): ubica `marker_text` (un comentario HTML
    estable, ej. '<!-- SLIDE 2 — ... -->') y tapa solo el PRÓXIMO `<div class="slide_class">`
    que aparece después — no todas las ocurrencias del archivo. Devuelve
    (html_modificado, 1 o 0)."""
    idx = html.find(marker_text)
    if idx == -1:
        return html, 0

    open_re = re.compile(r'<div class="' + re.escape(slide_class) + r'"[^>]*>')
    m = open_re.search(html, idx, idx + _MARKER_SEARCH_WINDOW)
    if not m:
        return html, 0

    overlay = _STALE_OVERLAY_HTML.format(section=section, old_label=old_label)
    tag = m.group(0).replace(f'class="{slide_class}"', f'class="{slide_class} stale-slide"', 1)
    html = html[:m.start()] + tag + overlay + html[m.end():]
    if "</head>" in html:
        html = html.replace("</head>", _STALE_OVERLAY_STYLE + "</head>", 1)
    else:
        html = _STALE_OVERLAY_STYLE + html
    return html, 1


# ── Funciones de frescura — cada una sabe leer SU fuente de verdad y devuelve
# ("pass"|"stale"|"skip", info) donde `info` es la etiqueta de mes coincidente (pass),
# la etiqueta del mes viejo a mostrar en el overlay (stale), o el motivo (skip). ──────────

def _ceo_freshness(html: str, month: str):
    try:
        with open(paths.CEO_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        return "skip", f"error leyendo ceo.yaml: {e}"
    m = data.get("updated_for_month")
    if m is None:
        return "skip", "ceo.yaml no tiene 'updated_for_month' — no se puede verificar si el contenido es del mes correcto"
    return ("pass", m) if m == month else ("stale", m)


def _discussion_topics_freshness(html: str, month: str):
    m = extract_updated_for_month_comment(html)
    if m is None:
        return "skip", "no se encontró el comentario 'updated_for_month' en el HTML generado"
    return ("pass", m) if m == month else ("stale", m)


def _headcount_freshness(html: str, month: str):
    m = extract_updated_for_month_comment(html)
    if m is None:
        return "skip", "no se encontró el comentario 'updated_for_month' en el HTML generado"
    return ("pass", m) if m == month else ("stale", m)


def _financial_performance_freshness(html: str, month: str):
    label, m = extract_financial_performance_title_month(html)
    if m is None:
        return "skip", "no se encontró el patrón 'Financial Performance · Mes AAAA' en el <title>"
    return ("pass", label) if m == month else ("stale", label)


def _nps_freshness(html: str, month: str):
    try:
        with open(paths.NPS_SNAPSHOT_YAML, encoding="utf-8") as f:
            snap = yaml.safe_load(f) or {}
    except Exception as e:
        return "skip", f"error leyendo nps_snapshot.yaml: {e}"
    return ("pass", month) if month in snap else ("stale", "un mes anterior")


@dataclass
class StaleSlideSpec:
    check_id: str
    label: str
    output_filename: str
    check_freshness: Callable[[str, str], tuple]  # (html, month) -> ("pass"|"stale"|"skip", info)
    scope: str  # "file" (tapa varias clases de slide en todo el archivo), "marker" (una sola
                # slide) o "body_replace" (reemplaza todo <body> por portada + N slides vacías
                # fijas — para secciones cuyo conteo real de slides varía mes a mes)
    section_label: str
    slide_classes: Optional[list] = None  # requerido si scope == "file"
    marker: Optional[str] = None  # requerido si scope == "marker"
    notify: str = ""


SLIDE_SPECS = [
    StaleSlideSpec(
        check_id="F3.6", label="CEO Highlights — ocultar visualmente si están desactualizados",
        output_filename="1_inicio.html", check_freshness=_ceo_freshness,
        scope="marker", marker="SLIDE 2 — CEO Highlights", section_label="CEO Highlights",
        notify="Avisar a Mayra Gutiérrez.",
    ),
    StaleSlideSpec(
        check_id="F3.5", label="Discussion Topics — ocultar visualmente si están desactualizados",
        output_filename="2_discussion_topic.html", check_freshness=_discussion_topics_freshness,
        scope="body_replace", section_label="Discussion Topics",
    ),
    StaleSlideSpec(
        check_id="F3.4", label="Template 4 — ocultar visualmente si está desactualizado",
        output_filename="4_financial_performance.html", check_freshness=_financial_performance_freshness,
        scope="file", slide_classes=["board-slide"], section_label="Financial Performance",
        notify="Avisar a Sofía Maldonado.",
    ),
    StaleSlideSpec(
        check_id="F3.7", label="6_rd (NPS) — ocultar visualmente si está desactualizado",
        output_filename="6_rd.html", check_freshness=_nps_freshness,
        scope="marker", marker="SLIDE 3 — NPS Alegra", section_label="NPS",
    ),
    StaleSlideSpec(
        check_id="F3.8", label="Headcount — ocultar visualmente si está desactualizado",
        output_filename="7_headcount.html", check_freshness=_headcount_freshness,
        scope="file", slide_classes=["hc-slide"], section_label="Headcount",
        notify="Avisar a People & Talent.",
    ),
]


def check_stale_slide(spec: StaleSlideSpec, month: str) -> CheckResult:
    """Motor genérico: aplica `spec` contra `Template Board/output/{spec.output_filename}`.
    No escribe nada si no encuentra el archivo, no puede determinar el mes, o ya está al día."""
    html_path = paths.OUTPUT_DIR / spec.output_filename
    if not html_path.exists():
        return CheckResult(spec.check_id, spec.label, "SKIP", f"no existe {html_path}")

    html = html_path.read_text(encoding="utf-8")
    status, info = spec.check_freshness(html, month)

    if status == "skip":
        return CheckResult(spec.check_id, spec.label, "SKIP", info)
    if status == "pass":
        return CheckResult(spec.check_id, spec.label, "PASS", f"'{info}' coincide con {month}, no se oculta nada")

    old_label = info
    if spec.scope == "marker":
        new_html, n = _overlay_single_slide_by_marker(html, spec.marker, "slide", spec.section_label, old_label)
    elif spec.scope == "body_replace":
        new_html, n = _replace_stale_body_with_placeholder(html, spec.section_label, old_label)
    else:
        new_html, n = _overlay_stale_slides(html, spec.slide_classes, spec.section_label, old_label)

    if n == 0:
        if spec.scope == "marker":
            reason = f"no se encontró la slide de {spec.section_label} en el HTML"
        elif spec.scope == "body_replace":
            reason = "no se encontró <body> en el HTML"
        else:
            reason = "no se encontró ninguna slide en el HTML"
        return CheckResult(spec.check_id, spec.label, "SKIP", reason)

    html_path.write_text(new_html, encoding="utf-8")
    notify = f" {spec.notify}" if spec.notify else ""
    if spec.scope == "body_replace":
        detail = (f"reemplazado por portada + {n} slide(s) vacía(s) — mostraba '{old_label}' "
                   f"pero se está generando {month}.{notify}")
    else:
        detail = (f"{n} slide(s) de {spec.section_label} ocultas con overlay — mostraba '{old_label}' "
                   f"pero se está generando {month}.{notify}")
    return CheckResult(spec.check_id, spec.label, "WARN", detail)
