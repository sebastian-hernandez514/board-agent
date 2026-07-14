"""Fase 0 — Human Inputs Gate (workaround temporal, ver AGENT_ARCHITECTURE.md).

Verifica que las fuentes manuales (CSVs, YAMLs editoriales) tengan datos del
mes objetivo ANTES de correr fetch_metrics.py. Esta fase debe desaparecer
cuando esas fuentes se muevan a Redshift — mientras tanto, decirle al usuario
exactamente qué falta y quién lo provee.

F0.8 y F0.9 (agregadas 2026-07-08): hallazgo real reportado por el usuario tras generar el
board de junio con el agente — varias slides seguían mostrando "May" pese a haber corrido
`run.py --month 2026-06`. Causa raíz: `config.yaml` (period/month_label, usado en TODOS los
templates para headers) y el HTML de Template 4 (Financial Performance, pegado a mano por
Finance) no tenían NINGÚN check que comparara su mes contra el `--month` pedido — F0.8 y F0.9
cierran ese gap. Alcance acordado con el usuario: solo detección (FAIL/WARN), sin modificar
ningún archivo de Template Board para "vaciar" slides desactualizadas — eso queda pendiente
como decisión de diseño aparte.
"""

import csv
import re
from datetime import datetime

import yaml

from . import output_integrity, paths
from .report import CheckResult

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

MESES_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

PLACEHOLDER_MARKERS = ("por definir", "tbd", "todo", "pendiente de", "n/a")


def _month_label_es(month: str) -> str:
    y, m = month.split("-")
    return f"{MESES_ES[int(m)]} {y}"


def _check_pnl_actual(month: str) -> CheckResult:
    """merge_pnl() en fetch_metrics.py cae a data/pnl_override.yaml si el CSV no
    tiene filas del mes (workaround ya en uso, con datos de Finance a mano) —
    el gate tiene que reconocer esa fuente también o reporta un falso bloqueante.

    WARN, no FAIL (cambiado 2026-07-08): el resto del board (ARR, MRR, Churn, Headcount)
    no depende del P&L — bloquear TODO el flujo por un dato que Finance manda aparte y
    tarde le impedía a cualquiera revisar el resto mientras se espera. merge_pnl() ya
    maneja la ausencia de datos sin romperse (no setea net_revenue/gross_margin/ebitda_margin,
    Jinja2 los renderiza en blanco sin error) — el freno real ahora vive en R17 del Validator
    (Fase 4), que sí bloquea la publicación si esos 3 campos faltan, con el board ya armado
    y visible para revisar en vez de tapar todo desde el inicio."""
    target_y, target_m = (int(x) for x in month.split("-"))
    max_date = None
    hit_csv = False
    with open(paths.PNL_ACTUAL_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        try:
            d = datetime.strptime(r["Date"], "%m/%d/%Y")
        except (ValueError, KeyError):
            continue
        if max_date is None or d > max_date:
            max_date = d
        if d.year == target_y and d.month == target_m:
            hit_csv = True

    hit_override = False
    override_path = paths.DATA_DIR / "pnl_override.yaml"
    if override_path.exists():
        with open(override_path, encoding="utf-8") as f:
            override = yaml.safe_load(f) or {}
        hit_override = month in override

    if hit_csv:
        return CheckResult("F0.4", f"P&L tiene filas de {month} (CSV o override)", "PASS", "fuente: CSV")
    if hit_override:
        return CheckResult("F0.4", f"P&L tiene filas de {month} (CSV o override)", "PASS",
                            "fuente: data/pnl_override.yaml (manual, no el CSV)")
    return CheckResult("F0.4", f"P&L tiene filas de {month} (CSV o override)", "WARN",
                        f"CSV parado en {max_date.date() if max_date else '?'} y sin entrada '{month}' en pnl_override.yaml "
                        f"— el flujo sigue igual, pero R17 del Validator va a FAIL si Net Revenue/Gross Margin/EBITDA salen vacíos")


def _check_ceo_yaml(month: str) -> CheckResult:
    """F0.5 daba un falso PASS hasta 2026-07-08: solo revisaba que highlights/lowlights no
    estuvieran vacíos, nunca que fueran del mes correcto — se descubrió simulando el flujo de
    junio-26 desde cero (el YAML tenía texto de mayo y el check igual pasaba en verde).
    Fix backward-compatible: si alguien agrega la clave opcional 'updated_for_month' al YAML
    (ej. 'updated_for_month: \"2026-06\"'), el check la compara contra el mes objetivo. Si el
    campo no existe todavía (el ceo.yaml real de hoy no lo tiene), el check sigue funcionando
    como antes pero deja explícito en el detail que no pudo verificar el mes — no finge certeza."""
    with open(paths.CEO_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    highlights = data.get("highlights") or []
    lowlights = data.get("lowlights") or []
    label = _month_label_es(month)
    title = (data.get("ceo_title") or "").lower()
    text_blob = " ".join(highlights + lowlights).lower()
    has_placeholder = any(m in text_blob for m in PLACEHOLDER_MARKERS)
    empty = not highlights or not lowlights
    updated_for_month = data.get("updated_for_month")

    if empty or has_placeholder:
        return CheckResult("F0.5", "editorial/ceo.yaml sin placeholders vacíos", "WARN",
                            f"highlights={len(highlights)} lowlights={len(lowlights)} placeholder_detectado={has_placeholder}")
    if updated_for_month is not None and updated_for_month != month:
        return CheckResult("F0.5", "editorial/ceo.yaml sin placeholders vacíos", "WARN",
                            f"contenido marcado como de '{updated_for_month}', pero se está generando '{month}' "
                            f"— revisar si ya se actualizó el CEO commentary de este mes")
    unverified_note = ("" if updated_for_month is not None else
                        " — sin campo 'updated_for_month': no se puede verificar que el contenido sea del mes correcto, solo que no está vacío")
    return CheckResult("F0.5", "editorial/ceo.yaml sin placeholders vacíos", "PASS",
                        f"highlights={len(highlights)} lowlights={len(lowlights)} (título: '{data.get('ceo_title')}', esperado mes: {label}){unverified_note}")


_UPDATED_FOR_MONTH_COMMENT_RE = re.compile(r"<!--\s*updated_for_month:\s*(\d{4}-\d{2})\s*-->")


def extract_updated_for_month_comment(html: str):
    """Busca el sentinel '<!-- updated_for_month: YYYY-MM -->' — mismo patrón que el campo
    `updated_for_month` de ceo.yaml, pero para archivos que son HTML puro (no YAML) y por lo
    tanto no pueden tener un campo estructurado. Devuelve 'YYYY-MM' o None si no existe.
    Compartido entre F0.6 (Fase 0, lee el .j2 fuente) y F3.5 (Fase 3, post-procesa el
    output/*.html ya generado — el comentario pasa intacto a través de Jinja2)."""
    m = _UPDATED_FOR_MONTH_COMMENT_RE.search(html)
    return m.group(1) if m else None


def _check_discussion_topics(month: str) -> CheckResult:
    """F0.6 — reescrita 2026-07-08 (antes revisaba `discussion_topics.yaml`, un scaffold
    DESCONECTADO del template real — ver commit anterior el mismo día para el hallazgo
    original). El contenido real de la slide vive escrito a mano en
    `templates/2_discussion_topic.j2`, que no es YAML y no podía tener un campo verificable.
    Se le agregó el mismo sentinel que ya usa `ceo.yaml` (`updated_for_month`), pero como
    comentario HTML (`<!-- updated_for_month: YYYY-MM -->`) ya que el archivo es HTML puro.
    Backward-compatible: si el sentinel no existe todavía, WARN honesto en vez de fingir
    certeza — mismo criterio que F0.5."""
    label = "2_discussion_topic.j2 marcado como actualizado para el mes objetivo"
    try:
        html = paths.DISCUSSION_TOPIC_TEMPLATE.read_text(encoding="utf-8")
    except Exception as e:
        return CheckResult("F0.6", label, "WARN", f"error leyendo el template: {e}")

    sentinel_month = extract_updated_for_month_comment(html)
    if sentinel_month is None:
        return CheckResult("F0.6", label, "WARN",
                            "no se encontró el comentario 'updated_for_month' en 2_discussion_topic.j2 — "
                            "no se puede verificar si el contenido es del mes correcto "
                            "(agregar '<!-- updated_for_month: YYYY-MM -->' al inicio del archivo)")
    if sentinel_month != month:
        return CheckResult("F0.6", label, "WARN",
                            f"el archivo está marcado como de '{sentinel_month}' pero se está generando '{month}' "
                            f"— revisar si ya se actualizaron los discussion topics de este mes")
    return CheckResult("F0.6", label, "PASS", f"marcado como '{sentinel_month}', coincide")


def _check_headcount(month: str) -> CheckResult:
    """F0.11 — agregada 2026-07-09 (mismo hueco que F0.6 pero en Headcount): los comentarios de
    Highlights/Lowlights de `7_headcount.j2` (slides "Headcount by Team" y "People & Talent")
    viven escritos a mano dentro del `.j2`, igual que Discussion Topics antes de su fix — sin
    ningún YAML propio ni campo verificable. Mismo sentinel, mismo criterio: comentario HTML
    `<!-- updated_for_month: YYYY-MM -->` al inicio del archivo."""
    label = "7_headcount.j2 marcado como actualizado para el mes objetivo"
    try:
        html = paths.HEADCOUNT_TEMPLATE.read_text(encoding="utf-8")
    except Exception as e:
        return CheckResult("F0.11", label, "WARN", f"error leyendo el template: {e}")

    sentinel_month = extract_updated_for_month_comment(html)
    if sentinel_month is None:
        return CheckResult("F0.11", label, "WARN",
                            "no se encontró el comentario 'updated_for_month' en 7_headcount.j2 — "
                            "no se puede verificar si los comentarios de Headcount son del mes correcto "
                            "(agregar '<!-- updated_for_month: YYYY-MM -->' al inicio del archivo)")
    if sentinel_month != month:
        return CheckResult("F0.11", label, "WARN",
                            f"el archivo está marcado como de '{sentinel_month}' pero se está generando '{month}' "
                            f"— revisar si ya se actualizaron los comentarios de Headcount de este mes")
    return CheckResult("F0.11", label, "PASS", f"marcado como '{sentinel_month}', coincide")


def _check_config_month(month: str) -> CheckResult:
    """F0.8 — ver nota de módulo. config.yaml es el ÚNICO paso manual del checklist mensual de
    Template Board que no tenía ningún check en Fase 0, pese a que `config.period`/`month_label`
    se usa en TODOS los templates para headers y títulos. FAIL, no WARN: es una comparación
    exacta de texto, sin ambigüedad ni riesgo de falso positivo — si no coincide, el board
    completo va a mostrar el mes viejo en los headers, sin excepción."""
    with open(paths.CONFIG_YAML, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    period = config.get("period")
    if period != month:
        return CheckResult("F0.8", "config.yaml (period/month_label) coincide con el mes objetivo", "FAIL",
                            f"config.yaml tiene period='{period}' pero se está generando '{month}' — "
                            f"actualizar data/config.yaml antes de publicar, si no TODOS los headers/títulos "
                            f"del board van a mostrar el mes viejo")
    return CheckResult("F0.8", "config.yaml (period/month_label) coincide con el mes objetivo", "PASS",
                        f"period='{period}', month_label='{config.get('month_label')}'")


_TEMPLATE4_TITLE_RE = re.compile(r"Financial Performance\s*·\s*(\w+)\s+(\d{4})", re.IGNORECASE)


def extract_financial_performance_title_month(html: str):
    """Extrae '{Mes} {Año}' y el mes en formato 'YYYY-MM' del <title> de Template 4 (convención
    ya existente: "Financial Performance · May 2026"). Devuelve (label, 'YYYY-MM') o (None, None)
    si no se pudo parsear. Compartida entre F0.9 (Fase 0, solo lectura del .j2 fuente) y F3.4
    (Fase 3, post-procesa el output/*.html ya generado) — mismo parseo, un solo lugar."""
    m = _TEMPLATE4_TITLE_RE.search(html)
    if not m:
        return None, None
    month_name, year = m.group(1), m.group(2)
    month_num = MESES_EN.get(month_name.lower())
    if month_num is None:
        return None, None
    return f"{month_name} {year}", f"{year}-{month_num:02d}"


def _check_financial_performance_month(month: str) -> CheckResult:
    """F0.9 — ver nota de módulo. Template 4 es HTML completo pegado a mano por Sofía Maldonado
    cada mes (ver RACI en docs/BOARD_PLAYBOOK_DRAFT.md) — no es YAML, no puede tener un campo
    tipo 'updated_for_month'. Se reusa una convención ya existente en el archivo real: el
    <title> siempre trae el mes (ej. "Financial Performance · May 2026"). WARN, no FAIL —
    mismo criterio que F0.4 (P&L): es un insumo externo que llega tarde, no debe bloquear todo
    el flujo, pero si el título no matchea es señal real de que el HTML sigue siendo del mes
    anterior."""
    label = "Template 4 (Financial Performance) — <title> coincide con el mes objetivo"
    try:
        html = paths.FINANCIAL_PERFORMANCE_TEMPLATE.read_text(encoding="utf-8")
    except Exception as e:
        return CheckResult("F0.9", label, "SKIP", f"error: {e}")

    found_label, found_month = extract_financial_performance_title_month(html)
    if found_month is None:
        return CheckResult("F0.9", label, "SKIP",
                            "no se encontró el patrón 'Financial Performance · Mes AAAA' en el <title>")

    if found_month != month:
        return CheckResult("F0.9", label, "WARN",
                            f"el <title> dice '{found_label}' pero se está generando '{month}' — "
                            f"avisar a Sofía Maldonado si todavía no mandó el HTML de Financial Performance de este mes")
    return CheckResult("F0.9", label, "PASS", f"<title> dice '{found_label}', coincide")


def _check_arr_walk_yaml() -> CheckResult:
    with open(paths.ARR_WALK_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    products = data.get("products") or []
    all_asks_empty = all(not p.get("asks") for p in products)
    insight_empty = not (data.get("alanube_insight") or "").strip()
    if all_asks_empty or insight_empty:
        return CheckResult("F0.7", "editorial/arr_walk.yaml comentarios llenos", "WARN",
                            f"asks vacíos en todos los productos={all_asks_empty} · alanube_insight vacío={insight_empty}")
    return CheckResult("F0.7", "editorial/arr_walk.yaml comentarios llenos", "PASS", "")


def _check_nps_snapshot(month: str) -> CheckResult:
    """F0.10 — agregada 2026-07-08 (segunda revisión, tercer hallazgo del día): descubierto
    generando junio real que `_build_nps()` en fetch_metrics.py devuelve `None` cuando
    `nps_snapshot.yaml` no tiene el mes objetivo (comportamiento correcto y documentado ahí
    mismo) — pero `6_rd.j2` no lo blinda (`metrics.nps.score`, `.costa_rica_trend`, etc. sin
    ningún `{% if %}`), así que `generate.py` truena con `'None' has no attribute
    'costa_rica_trend'`. Como Jinja2 renderiza el archivo entero de una sola pasada
    (`tmpl.render()` se ejecuta ANTES de escribir el archivo — ver generate.py), el crash deja
    TODO `output/6_rd.html` sin regenerar, no solo la parte de NPS — incluida "Product
    Performance", que de otro modo sí tomaría el mes correcto (usa `config.month_label`
    dinámico). No se tocó `6_rd.j2` (blindar esa plantilla es cambio de Template Board, fuera
    de alcance) — este check avisa ANTES de correr generate.py, y F3.7 (Fase 3) tapa TODO el
    archivo si ya quedó viejo. WARN, no FAIL — mismo criterio que F0.4/F0.9: insumo externo
    (sesión de Amplitude) que llega tarde, no debe bloquear el resto del flujo."""
    label = "nps_snapshot.yaml tiene el mes objetivo"
    try:
        with open(paths.NPS_SNAPSHOT_YAML, encoding="utf-8") as f:
            snap = yaml.safe_load(f) or {}
    except Exception as e:
        return CheckResult("F0.10", label, "WARN", f"error leyendo nps_snapshot.yaml: {e}")

    if month not in snap:
        return CheckResult("F0.10", label, "WARN",
                            f"nps_snapshot.yaml no tiene entrada '{month}' — generate.py va a fallar al armar "
                            f"la slide de NPS y va a dejar TODO output/6_rd.html (incluida Product Performance) "
                            f"con el mes anterior; hace falta una sesión de Claude + Amplitude para cargar el "
                            f"snapshot de este mes")
    return CheckResult("F0.10", label, "PASS", f"snapshot de '{month}' presente")


def run(month: str) -> list[CheckResult]:
    """month en formato 'YYYY-MM' (mes objetivo del próximo board).

    Fuentes que salieron de este gate porque ya se automatizaron (fetch_metrics.py las lee
    directo de RS, dejaron de ser un input manual — ver docs/AGENT_ARCHITECTURE.md):
    - paises_fx.csv → dwh_dimensions.tb_trm_banrep (Fase 1, check F1.5)
    - chart_alanube.yaml → bi_alanube.fact_alanube_arr_walk (load_alanube_arr(), 2026-07-03)
    - Payback.csv → bi_strategic.payback_cohort_results (load_payback(), 2026-07-06)
    """
    return [
        _check_pnl_actual(month),
        _check_ceo_yaml(month),
        _check_discussion_topics(month),
        _check_arr_walk_yaml(),
        _check_config_month(month),
        _check_financial_performance_month(month),
        _check_nps_snapshot(month),
        _check_headcount(month),
        output_integrity.check_for_manual_edits(),
    ]
