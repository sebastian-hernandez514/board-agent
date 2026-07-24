"""Fase 4 — Business Rules Validator.

Verifica que el board sea matemáticamente correcto ANTES de publicarlo.
La regla R1 es la que hubiera bloqueado un bug real de v36/v37
(ver Board Agent/docs/AGENT_ARCHITECTURE.md; R2 cubría el otro bug de esa época pero se
retiró 2026-07-24, ver nota sobre R5/R2 más abajo). R8 se agregó porque al construir
este validador se encontró una inconsistencia real en el board de mayo-26 ya
publicado (ver docs/AGENT_ARCHITECTURE.md — hallazgo 2026-07-02).

R7 corre una query RS INDEPENDIENTE (no reusa lógica de fetch_metrics.py) — valida
metrics.yaml sin depender de que Template Board exponga el dato crudo. R11 es una
versión reducida y honesta de la regla original: solo verifica completitud del CSV
de budget en cierre de Q, no reproduce la aritmética completa de vs_budget (no se
pudo validar contra un mes de cierre de Q real en esta sesión — mayo-26 no lo es).

R13-15 están implementadas y activas desde 2026-07-06 (commit "Completar Validator R5,
R13-15") — parsean el HTML generado para verificar colores de delta. Caen a SKIP solo
cuando el HTML no está disponible, no por diseño. (R5 vivió acá desde esa misma fecha
hasta 2026-07-22, cuando se retiró — su premisa, la trampa de signos de "cross_down" en
Net Expansion, dejó de aplicar con ARR Walk v2, ver scripts/fetch_metrics.py. R2 se retiró
2026-07-24 por la misma razón: asumía que New MRR de Core+Lite siempre suma exacto al
total GLO, pero ARR Walk v2 clasifica GLO de forma independiente a nivel de compañía
completa — una compañía nueva en un segmento pero ya cliente en el otro correctamente NO
cuenta como "New" a nivel de compañía, aunque sí cuente como "New" en ese segmento.)

R16 (cumplimiento de diseño, agregada 2026-07-06) también cae a SKIP si no encuentra ningún
elemento con clase de slide-shell en el HTML — ver docstring de _check_r16_slide_dimensions.

R18 (overflow de texto, agregada 2026-07-08 — Bloque 4 del roadmap de colaboración, ver
memory/project_board_collaboration_roadmap.md) requiere Playwright + Chromium instalados;
si no están disponibles, SKIP — no es una dependencia dura del pipeline. Arranca en WARN por
decisión explícita del usuario (regla nueva, sin historial de falsos positivos todavía).

R19 (agregada 2026-07-08 — "Agente 3" de la reunión original del 19-jun, consistencia entre
slides): verifica que el ARR EoP mostrado en "Monthly Performance" coincida literalmente con
el de "YTD Performance" en el HTML ya renderizado. FAIL, no WARN — es el mismo tipo de bug
real que ya pasó una vez (v36, ARR sin Alanube en una vista) y no un heurístico nuevo sin
historial.

R20 (agregada 2026-07-24, pedido explícito del usuario "por si acaso"): el STOCK de MRR
(mrr_eop) de Core+Lite debe sumar exacto al de GLO ("all") en TODOS los meses — a diferencia
del FLUJO (New/Churn/Upsell/Downsell), que NO cuadra por diseño (migraciones Lite↔Core, ver
R2 retirada). Es un guardrail de regresión: nunca debería fallar en la práctica, porque "all"
se construye literalmente como suma de segmentos en build_seg_metrics().
"""

import csv
import json
import re
from pathlib import Path

import yaml

from . import paths
from .parsing import find_row, last, parse_cell, parse_money_cell
from .report import CheckResult

TOL_ARR_WALK = 150_000  # celdas de arr_walk_table vienen redondeadas a 1 decimal en $M (±$50K por celda)
TOL_ARR_TOTAL = 50_000
TOL_CC = 100_000
FX_RESIDUAL_LIMIT = 3_000_000
CHURN_MIN_PCT = 0.0
CHURN_MAX_PCT = 20.0


def _load_metrics(metrics_path: Path) -> dict:
    with open(metrics_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _arr_walk_glo_rows(metrics: dict) -> list:
    """Sección 'ARR BoP ... ARR EoP (Constant Currency)' de arr_walk_table (GLO)."""
    for section in metrics["arr_walk_table"]["sections"]:
        labels = {r["label"] for r in section["rows"]}
        if "ARR BoP" in labels and "Net New ARR" in labels:
            return section["rows"]
    raise KeyError("no se encontró la sección del ARR Walk GLO en arr_walk_table")


_TR_RE = re.compile(r'<tr[^>]*>(.*?)</tr>', re.S)
_METRIC_NAME_RE = re.compile(r'<span class="metric-name[^"]*">([^<]+)</span>')
_DELTA_TD_RE = re.compile(r'<td class="delta ([a-z]+)[^"]*">\s*([^<]*?)\s*</td>')

_R13_NEUTRAL_METRICS = {"Investment"}
_R14_INVERTED_METRICS = {"Churn Rate", "CAC"}


def _delta_sign(text: str):
    """+1/-1 según el signo del texto ya formateado (ej. '+2.6%', '-7.5%') — None si está
    vacío o es 0% (ahí cualquier clase es defendible, no hay violación posible)."""
    t = text.strip()
    if not t or t in ("—", "-", "0%", "0.0%", "+0%", "+0.0%"):
        return None
    return -1 if t.startswith("-") or t.startswith("(") else 1


def _check_color_rules(html_path: Path) -> list[CheckResult]:
    """R13/R14/R15 — reglas de color de las filas 'butterfly' (Country Performance en
    3_arr_walk.j2 y Global Country Performance en 1_inicio.j2, misma estructura en ambas).
    Cada <tr> trae <span class="metric-name"> como ancla confiable (no hay data-attribute) —
    ver memory/project_board_agent.md 2026-07-06. Clases reales: 'pos'/'neg'/'neutral',
    siempre junto a la clase base 'delta' (ej. class="delta pos right")."""
    definitions = [
        ("R13", "Investment: delta neutro (sin verde/rojo)"),
        ("R14", "Churn/CAC: delta invertido"),
        ("R15", "Resto de métricas: signo estándar de color"),
    ]
    try:
        html = html_path.read_text(encoding="utf-8")
    except Exception as e:
        return [CheckResult(rid, desc, "SKIP", f"error: {e}") for rid, desc in definitions]

    checked = {"R13": 0, "R14": 0, "R15": 0}
    violations = {"R13": [], "R14": [], "R15": []}

    for tr_match in _TR_RE.finditer(html):
        tr_html = tr_match.group(1)
        name_m = _METRIC_NAME_RE.search(tr_html)
        deltas = _DELTA_TD_RE.findall(tr_html)
        if not name_m or not deltas:
            continue
        metric = name_m.group(1).strip()
        rid = ("R13" if metric in _R13_NEUTRAL_METRICS
                else "R14" if metric in _R14_INVERTED_METRICS
                else "R15")

        for css_class, text in deltas:
            if rid == "R13":
                checked[rid] += 1
                if css_class != "neutral":
                    violations[rid].append(f"{metric}={text} → clase={css_class} (esperado 'neutral')")
                continue
            sign = _delta_sign(text)
            if sign is None:
                continue
            checked[rid] += 1
            want_pos = (sign < 0) if rid == "R14" else (sign > 0)
            expected = "pos" if want_pos else "neg"
            if css_class != expected:
                violations[rid].append(f"{metric}={text} → clase={css_class} (esperado '{expected}')")

    results = []
    for rid, desc in definitions:
        if checked[rid] == 0:
            results.append(CheckResult(rid, desc, "SKIP", "no se encontraron filas de esta métrica en el HTML"))
        elif violations[rid]:
            sample = "; ".join(violations[rid][:3])
            results.append(CheckResult(rid, desc, "FAIL",
                                        f"{len(violations[rid])}/{checked[rid]} celdas mal coloreadas: {sample}"))
        else:
            results.append(CheckResult(rid, desc, "PASS", f"{checked[rid]} celdas verificadas, todas correctas"))
    return results


_DIV_TAG_RE = re.compile(r'<div\s+([^>]*)>')
_CLASS_ATTR_RE = re.compile(r'class="([^"]*)"')
_STYLE_ATTR_RE = re.compile(r'style="([^"]*)"')
_PX_OVERRIDE_RE = re.compile(r'(width|height)\s*:\s*[\d.]+px')


def _check_r16_slide_dimensions(html_path: Path) -> CheckResult:
    """R16 — primera regla de cumplimiento de diseño (ver docs/AGENT_ARCHITECTURE.md, gap
    identificado en la reunión de colaboración del 19-jun-2026). Sin renderizar en navegador:
    verifica que ningún elemento con una clase de slide-shell (SLIDE_CLASS_TOKENS, las que
    heredan 960×540 de --slide-width/--slide-height en base.css) tenga un inline style que
    fije width/height en px — eso pisaría el tamaño fijo del slide sin que nadie lo note.

    v2 (2026-07-06, corregido tras revisión de código): la v1 buscaba el literal
    `class="..." style="..."` con ese orden exacto y sin nada en medio — un `id="x"` intercalado
    o `style` antes que `class` en cualquier .j2 futuro desactivaba la regla en silencio (falso
    negativo). Ahora se extraen `class`/`style` de forma independiente del atributo completo del
    tag, sin importar orden. También se agrega un contador `checked`: la v1 devolvía PASS incluso
    si el regex no encontraba ningún slide-shell (0 revisados = 0 violaciones = "PASS" engañoso,
    indistinguible de "revisé todo y está bien") — ahora eso es SKIP explícito, mismo criterio
    que usan R13-R15 con su propio contador `checked`.
    Alcance conocido: solo detecta overrides en unidades px (no %, vw, calc()) — cubre el caso
    real que motivó la regla, no es un parser de CSS completo."""
    try:
        html = html_path.read_text(encoding="utf-8")
    except Exception as e:
        return CheckResult("R16", "Ningún slide-shell fuerza dimensión px inline", "SKIP", f"error: {e}")

    checked = 0
    violations = []
    for m in _DIV_TAG_RE.finditer(html):
        attrs = m.group(1)
        class_m = _CLASS_ATTR_RE.search(attrs)
        if not class_m or not (set(class_m.group(1).split()) & paths.SLIDE_CLASS_TOKENS):
            continue
        checked += 1
        style_m = _STYLE_ATTR_RE.search(attrs)
        if style_m and _PX_OVERRIDE_RE.search(style_m.group(1)):
            violations.append(f'class="{class_m.group(1)}" style="{style_m.group(1)}"')

    if checked == 0:
        return CheckResult("R16", "Ningún slide-shell fuerza dimensión px inline", "SKIP",
                            "no se encontró ningún elemento con clase de slide-shell en el HTML")
    if violations:
        sample = "; ".join(violations[:3])
        return CheckResult("R16", "Ningún slide-shell fuerza dimensión px inline", "FAIL",
                            f"{len(violations)}/{checked} slides con width/height px inline: {sample}")
    return CheckResult("R16", "Ningún slide-shell fuerza dimensión px inline", "PASS",
                        f"{checked} slides verificados, sin overrides de dimensión")


_R18_TOLERANCE_PX = 2


def _check_r18_slide_overflow(html_path: Path) -> CheckResult:
    """R18 — primera regla de "overflow de texto" del Bloque 4 (ver docs/AGENT_ARCHITECTURE.md
    sección 6 y memory/project_board_collaboration_roadmap.md). Los slide-shells con altura fija
    (`.slide`, `.hc-slide`, `.dt-slide`, `.gtm-slide` — confirmado en Template Board/styles/base.css
    y cada template) usan `overflow: hidden`: si el contenido real excede 960×540, el navegador lo
    recorta EN SILENCIO, sin ningún aviso visual ni error — exactamente el riesgo ya documentado en
    skills/ceo-highlights/SKILL.md (Regla de oro #1: "el contenido que se desborda se corta en
    silencio — no hay scroll ni aviso"). Esta regla lo detecta comparando scrollHeight/scrollWidth
    (contenido real) contra clientHeight/clientWidth (espacio visible) con Playwright.

    `.board-slide` (Template 4) usa `min-height`, no `height` — crece en vez de recortar, así que
    nunca dispara esta regla; es un comportamiento distinto, fuera de alcance aquí.

    Requiere Playwright + Chromium instalados (`uv run --with playwright python -m playwright
    install chromium`, una vez por entorno) — si no están disponibles, SKIP explícito. No es una
    dependencia dura del pipeline: el flujo normal (`run.py` sin ese extra) sigue funcionando igual,
    solo sin esta regla activa.

    Arranca en WARN, no FAIL (decisión explícita del usuario, 2026-07-08) — es una regla nueva sin
    historial de falsos positivos todavía, mismo criterio que se usó para F0.4→R17."""
    label = "Ningún slide-shell recorta contenido en silencio (overflow)"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return CheckResult("R18", label, "SKIP",
                            "playwright no está instalado — correr con "
                            "'uv run --with playwright python run.py ...' para habilitar esta regla")

    if not html_path.exists():
        return CheckResult("R18", label, "SKIP", f"no existe {html_path}")

    tokens_json = json.dumps(sorted(paths.SLIDE_CLASS_TOKENS))
    js = """() => {
        const tokens = __TOKENS__;
        const out = [];
        document.querySelectorAll('div').forEach(el => {
            const classes = el.className.split(/\\s+/);
            if (!classes.some(c => tokens.includes(c))) return;
            out.push({
                classes: el.className,
                overflowY: el.scrollHeight - el.clientHeight,
                overflowX: el.scrollWidth - el.clientWidth,
                text: (el.innerText || '').trim().slice(0, 60),
            });
        });
        return out;
    }""".replace("__TOKENS__", tokens_json)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1000, "height": 600})
            page.goto(html_path.resolve().as_uri())
            raw = page.evaluate(js)
            browser.close()
    except Exception as e:
        return CheckResult("R18", label, "SKIP", f"error corriendo Playwright: {e}")

    checked = len(raw)
    if checked == 0:
        return CheckResult("R18", label, "SKIP",
                            "no se encontró ningún elemento con clase de slide-shell en el HTML")

    violations = [r for r in raw if r["overflowY"] > _R18_TOLERANCE_PX or r["overflowX"] > _R18_TOLERANCE_PX]
    if violations:
        sample = "; ".join(
            f'"{v["classes"]}" (+{max(v["overflowY"], 0)}px vert, +{max(v["overflowX"], 0)}px horiz) '
            f'"{v["text"]}"'
            for v in violations[:3]
        )
        return CheckResult("R18", label, "WARN",
                            f"{len(violations)}/{checked} slides con contenido desbordado: {sample}")
    return CheckResult("R18", label, "PASS", f"{checked} slides verificados, sin desbordes")


_R19_ARR_SLIDE_LABELS = ("Monthly Performance", "YTD Performance")
_R19_ARR_VALUE_RE = re.compile(r'ks-p-name">ARR</div>\s*<div class="ks-p-val[^"]*">([^<]+)</div>')
_R19_SEARCH_WINDOW = 4000


def _check_r19_arr_slide_consistency(html_path: Path) -> CheckResult:
    """R19 — "Agente 3" de la reunión original del 19-jun (ver
    memory/project_board_collaboration_roadmap.md): Sebastián pidió explícito un check que
    compare que la misma cifra coincida entre distintas slides, no solo que la aritmética
    interna cuadre (eso ya lo hacen R1-R3 contra metrics.yaml). Caso real y documentado en
    Template Board/CLAUDE.md: 1_inicio.j2 renderiza `{{ metrics.arr_total }}` dos veces —
    en "Monthly Performance" y en "YTD Performance" — y ambas DEBEN mostrar el mismo ARR
    (Alegra + Alanube). No es un check tautológico: ya hubo un bug real de esta forma (v36,
    ARR sin Alanube en una de las dos vistas), y este codebase permite ediciones manuales
    puntuales del HTML ya generado (Template 4, re-embed de imágenes) que podrían romper esta
    igualdad sin que Jinja2 se entere. FAIL, no WARN — mismo criterio que R1."""
    label = "ARR EoP coincide entre Monthly Performance y YTD Performance"
    try:
        html = html_path.read_text(encoding="utf-8")
    except Exception as e:
        return CheckResult("R19", label, "SKIP", f"error: {e}")

    monthly_label, ytd_label = _R19_ARR_SLIDE_LABELS
    idx_monthly = html.find(monthly_label)
    idx_ytd = html.find(ytd_label)
    if idx_monthly == -1 or idx_ytd == -1:
        missing = monthly_label if idx_monthly == -1 else ytd_label
        return CheckResult("R19", label, "SKIP", f"no se encontró la slide '{missing}' en el HTML")

    # Acotar la búsqueda de "Monthly" a ANTES de que empiece "YTD" — si no, una regex sin match
    # en la slide de Monthly puede colarse y encontrar el bloque de ARR de la slide siguiente.
    monthly_end = idx_ytd if idx_ytd > idx_monthly else min(len(html), idx_monthly + _R19_SEARCH_WINDOW)
    bounds = [
        (monthly_label, idx_monthly, monthly_end),
        (ytd_label, idx_ytd, min(len(html), idx_ytd + _R19_SEARCH_WINDOW)),
    ]

    values = []
    for slide_label, start, end in bounds:
        m = _R19_ARR_VALUE_RE.search(html, start, end)
        if not m:
            return CheckResult("R19", label, "SKIP",
                                f"no se encontró el valor de ARR dentro de la slide '{slide_label}'")
        values.append(m.group(1).strip())

    if values[0] != values[1]:
        return CheckResult("R19", label, "FAIL",
                            f"Monthly Performance muestra {values[0]!r} pero YTD Performance muestra {values[1]!r}")
    return CheckResult("R19", label, "PASS", f"ambas slides muestran {values[0]}")


TOL_SEG_STOCK = 5_000  # margen de redondeo del pull mensual, no de la lógica en sí


def _check_r20_seg_stock_sums(metrics: dict) -> CheckResult:
    """R20 (2026-07-24) — guardrail de regresión: el STOCK de MRR ("mrr_eop", lo que
    alimenta ARR EoP/BoP) de Core + Lite debe sumar exacto al de "all" (GLO) en TODOS los
    meses, no solo en el de corte. A diferencia del FLUJO (New/Churn/Upsell/Downsell, que
    NO cuadra por diseño — las migraciones de compañías entre Lite y Core mueven plata
    entre esos buckets sin que sea plata nueva real, ver memory/project_board_agent.md
    sección 2026-07-24 y R2 retirada por la misma razón), el stock SIEMPRE debe cuadrar
    porque "all" se construye literalmente como la suma de los segmentos
    (build_seg_metrics() en fetch_metrics.py) — este check no debería fallar nunca en la
    práctica; si falla, es una regresión real en esa construcción, no un caso esperado."""
    label = "Stock Core+Lite = GLO, mes a mes"
    rows = metrics.get("seg_stock_by_month")
    if not rows:
        return CheckResult("R20", label, "SKIP", "seg_stock_by_month no está en metrics.yaml")

    peores = []
    for row in rows:
        expected = row.get("core_eop", 0.0) + row.get("lite_eop", 0.0)
        actual = row.get("all_eop", 0.0)
        diff = actual - expected
        if abs(diff) > TOL_SEG_STOCK:
            peores.append((row.get("m"), diff))

    if peores:
        detalle = ", ".join(f"{m}: diff={diff:,.0f}" for m, diff in peores[:5])
        return CheckResult("R20", label, "FAIL",
                            f"{len(peores)}/{len(rows)} meses no cuadran — {detalle}")
    return CheckResult("R20", label, "PASS", f"{len(rows)} meses verificados, todos cuadran")


def _count_slides(html_path: Path) -> int:
    html = html_path.read_text(encoding="utf-8")
    count = 0
    for m in re.finditer(r'class="([^"]*)"', html):
        classes = set(m.group(1).split())
        if classes & paths.SLIDE_CLASS_TOKENS:
            count += 1
    return count


_R7_LABEL = "Logos EoP = COUNT DISTINCT dedup (verificación independiente)"


def _check_r7_logos_dedup(metrics: dict) -> CheckResult:
    """Verifica smb_logos_eop contra un segundo conteo (COUNT DISTINCT id_company) que
    Claude Code escribe a mano en cache["validator"]["R7"] junto con el resto del cache del
    mes. Validado 2026-07-03 contra mayo-26 real: match exacto 58,974 = 58,974.

    OJO — desde la migración a Metabase (2026-07-10) esto ya NO es una verificación
    verdaderamente independiente: antes corría una query en vivo contra Redshift en el
    momento de validar; ahora lee un número que la MISMA persona escribió en la MISMA
    sesión manual que los datos primarios (ver board_agent/metabase_fetch_spec.py). No
    protege contra un error de transcripción que se repita en ambos lados — sigue siendo
    útil como chequeo de consistencia de doble entrada, pero no hay que confiar en el
    nombre "independiente" al pie de la letra.

    Bug corregido 2026-07-14: antes CUALQUIER excepción (cache no existe, falta
    smb_logos_eop, mes no coincide, falta cache["validator"]["R7"]) caía en el mismo except
    y devolvía SKIP — que en este validador se lee como "no aplica", no como "este freno
    falló". Ahora solo se SKIPea cuando falta un prerequisito genuino para intentar el
    check (metrics.yaml sin el campo, o el cache todavía no existe); si el cache SÍ existe
    pero está desactualizado o nunca se pobló cache["validator"]["R7"], es FAIL — es un
    error real, no un "no aplica"."""
    try:
        reported = int(metrics["smb_logos_eop"])
        cutoff = metrics["cutoff_month"]
    except (KeyError, TypeError, ValueError) as e:
        return CheckResult("R7", _R7_LABEL, "SKIP", f"metrics.yaml no tiene el campo necesario: {e}")

    if not paths.METABASE_CACHE_FILE.exists():
        return CheckResult("R7", _R7_LABEL, "SKIP", f"no existe {paths.METABASE_CACHE_FILE.name} todavía")

    try:
        cache = json.loads(paths.METABASE_CACHE_FILE.read_text(encoding="utf-8"))
        if cache.get("month") != cutoff:
            return CheckResult("R7", _R7_LABEL, "FAIL",
                                f"cache de Metabase es de '{cache.get('month')}', se esperaba '{cutoff}' "
                                "— refrescar el cache antes de validar")
        independent = int(cache["validator"]["R7"]["logos_eop"])
    except Exception as e:
        return CheckResult("R7", _R7_LABEL, "FAIL",
                            f"cache['validator']['R7'] mal formado o ausente ({e}) — correr la query "
                            "independiente vía Metabase y agregarla al cache antes de validar")

    diff = reported - independent
    status = "PASS" if diff == 0 else "FAIL"
    return CheckResult("R7", _R7_LABEL, status,
                        f"metrics.yaml={reported:,} vs Metabase independiente={independent:,} (diff={diff:+,})")


_R17_PLACEHOLDER_VALUES = (None, "", "N/A", "n/a")


def _check_r17_pnl_present(metrics: dict) -> CheckResult:
    """R17 — agregada 2026-07-08 junto con bajar F0.4 de FAIL a WARN en phase0_gate.py.
    merge_pnl() en fetch_metrics.py no truena si el CSV del P&L no tiene el mes — simplemente
    no setea net_revenue/gross_margin/ebitda_margin, y Jinja2 los renderiza en blanco sin
    error (confirmado: Environment(...) sin StrictUndefined). Eso significa que el board se
    puede generar completo con esa sección vacía sin que nada lo grite — este check es el
    freno real: si Finance no ha mandado el P&L, el Validator debe FAIL antes de publicar.

    Bug corregido 2026-07-08 (segunda revisión, generando junio real): fetch_metrics.py no deja
    estos campos vacíos/None cuando no hay datos — les pone el string literal "N/A" (valor por
    defecto seteado antes de llamar a merge_pnl(), nunca sobreescrito si el CSV no tiene el mes).
    `not "N/A"` es False, así que la versión anterior de este check nunca disparaba en la
    práctica. Confirmado en vivo: junio-26 sin P&L dio PASS con net_revenue=N/A."""
    missing = [k for k in ("net_revenue", "gross_margin", "ebitda_margin")
               if metrics.get(k) in _R17_PLACEHOLDER_VALUES]
    if missing:
        return CheckResult("R17", "P&L (Net Revenue/Gross Margin/EBITDA) presente", "FAIL",
                            f"campos faltantes o vacíos: {missing} — Finance no ha mandado el P&L de este mes, no publicar todavía")
    return CheckResult("R17", "P&L (Net Revenue/Gross Margin/EBITDA) presente", "PASS",
                        f"net_revenue={metrics.get('net_revenue')} gross_margin={metrics.get('gross_margin')} ebitda_margin={metrics.get('ebitda_margin')}")


def _check_r11_budget_quarter(metrics: dict) -> CheckResult:
    """Versión reducida de R11: en cierre de Q, verifica que Metricas_budget.csv tenga los 3
    meses del quarter completos (no vacíos) para 'ARR EoP'. NO reproduce la aritmética completa
    de *_vs_budget (requeriría un mes de cierre de Q real para validar la lógica — mayo-26 no
    lo es, no se implementó a ciegas).

    Bug corregido 2026-07-08 (segunda revisión, generando junio real — primer cierre de Q real
    contra el que se pudo probar esto): esta regla buscaba el valor en la columna con el MISMO
    nombre que 'Fecha' (ej. columna "Apr - 26" para la fila de abril) — pero el CSV en realidad
    guarda el valor de cada fila en la PRIMERA columna de datos, sin importar de qué mes sea esa
    fila (confirmado leyendo merge_budget() en fetch_metrics.py, que ya lo lee así y sí encuentra
    los datos). Con la lógica vieja, R11 reportaba "faltan" los 3 meses de un Q real que en
    verdad tenía los 3 con datos completos — falso positivo, no un hueco real de datos."""
    if not metrics.get("is_quarter_end"):
        return CheckResult("R11", "Budget CSV completo para el quarter (parcial)", "SKIP",
                            "mes de corte no es cierre de quarter")
    try:
        cutoff = metrics["cutoff_month"]  # 'YYYY-MM'
        y, m = cutoff.split("-")
        m = int(m)
        yy = y[2:]
        quarter_labels = [f"{paths.MES_ABBR_EN[mm]} - {yy}" for mm in (m - 2, m - 1, m)]

        with open(paths.METRICAS_BUDGET_CSV, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            data_cols = [c for c in fieldnames if c not in ("Metric", "Fecha")]
            first_data_col = data_cols[0] if data_cols else None
            rows = list(reader)

        missing = []
        for lbl in quarter_labels:
            match = next((r for r in rows if r.get("Metric") == "ARR EoP" and r.get("Fecha", "").strip() == lbl), None)
            if not match or not first_data_col or not (match.get(first_data_col) or "").strip():
                missing.append(lbl)
        status = "FAIL" if missing else "PASS"
        return CheckResult(
            "R11", "Budget CSV completo para el quarter (parcial, solo ARR EoP)", status,
            f"faltan: {missing}" if missing else f"completo: {quarter_labels}",
        )
    except Exception as e:
        return CheckResult("R11", "Budget CSV completo para el quarter (parcial)", "SKIP", f"error: {e}")


def run(metrics_path: Path = paths.METRICS_YAML, html_path: Path = paths.BOARD_STANDALONE_HTML) -> list[CheckResult]:
    results: list[CheckResult] = []
    metrics = _load_metrics(metrics_path)

    # R1 — ARR total incluye Alanube
    try:
        arr_total = parse_cell(metrics["arr_total"])
        chart = metrics["chart_arr_history"]
        expected = chart["alegra_spot"][-1] * 1_000_000 + chart["alanube_spot"][-1]
        diff = arr_total - expected
        status = "PASS" if abs(diff) <= TOL_ARR_TOTAL else "FAIL"
        results.append(CheckResult(
            "R1", "ARR total incluye Alanube", status,
            f"arr_total={arr_total:,.0f} vs alegra+alanube={expected:,.0f} (diff={diff:,.0f})",
        ))
    except Exception as e:
        results.append(CheckResult("R1", "ARR total incluye Alanube", "SKIP", f"error: {e}"))

    # R3 — ARR Walk balancea: Additions+Recovered+NetChurn+NetExpansion+FX ≈ NetNewARR ≈ EoP-BoP
    try:
        rows = _arr_walk_glo_rows(metrics)
        bop = parse_money_cell(last(find_row(rows, "ARR BoP")))
        additions = parse_money_cell(last(find_row(rows, "Additions")))
        recovered = parse_money_cell(last(find_row(rows, "Recovered")))
        net_churn = parse_money_cell(last(find_row(rows, "Net Churn")))
        net_expansion = parse_money_cell(last(find_row(rows, "Net Expansion")))
        fx_impact = parse_money_cell(last(find_row(rows, "(+/−) FX Impact")))
        eop = parse_money_cell(last(find_row(rows, "ARR EoP")))
        net_new_arr = parse_money_cell(last(find_row(rows, "Net New ARR")))

        sum_buckets = additions + recovered + net_churn + net_expansion + fx_impact
        diff_buckets = sum_buckets - net_new_arr
        diff_eop = net_new_arr - (eop - bop)
        status = "PASS" if abs(diff_buckets) <= TOL_ARR_WALK and abs(diff_eop) <= TOL_ARR_WALK else "FAIL"
        results.append(CheckResult(
            "R3", "ARR Walk balancea (buckets = Net New ARR = EoP-BoP)", status,
            f"buckets={sum_buckets:,.0f} vs netNewARR={net_new_arr:,.0f} (diff={diff_buckets:,.0f}); "
            f"EoP-BoP={eop - bop:,.0f} vs netNewARR={net_new_arr:,.0f} (diff={diff_eop:,.0f})",
        ))

        # R4 — Net Churn es negativo
        status4 = "PASS" if net_churn < 0 else "FAIL"
        results.append(CheckResult("R4", "Net Churn es negativo", status4, f"net_churn={net_churn:,.0f}"))

        # R6 — FX residual pequeño
        status6 = "PASS" if abs(fx_impact) < FX_RESIDUAL_LIMIT else "FAIL"
        results.append(CheckResult(
            "R6", f"FX residual < ${FX_RESIDUAL_LIMIT / 1e6:.0f}M", status6, f"fx_impact={fx_impact:,.0f}",
        ))

        # R8 — ARR EoP (Constant Currency) del mes de corte == ARR EoP regular (ratio FX = 1)
        eop_cc = parse_money_cell(last(find_row(rows, "ARR EoP (Constant Currency)")))
        diff_cc = eop_cc - eop
        status8 = "PASS" if abs(diff_cc) <= TOL_CC else "FAIL"
        results.append(CheckResult(
            "R8", "ARR EoP (Constant Currency) = ARR EoP en el mes de corte", status8,
            f"eop_cc={eop_cc:,.0f} vs eop={eop:,.0f} (diff={diff_cc:,.0f})",
        ))
    except Exception as e:
        for rid, desc in [
            ("R3", "ARR Walk balancea (buckets = Net New ARR = EoP-BoP)"),
            ("R4", "Net Churn es negativo"),
            ("R6", f"FX residual < ${FX_RESIDUAL_LIMIT / 1e6:.0f}M"),
            ("R8", "ARR EoP (Constant Currency) = ARR EoP en el mes de corte"),
        ]:
            results.append(CheckResult(rid, desc, "SKIP", f"error: {e}"))

    # R5 — RETIRADA 2026-07-22 (ver memory/project_board_agent.md): verificaba que
    # "cross_down" se restara en vez de sumarse dentro de Net Expansion (trampa de signos
    # de la metodología por producto+plan). ARR Walk v2 (New/Churn/Reactivated/Recovered/
    # Upsell/Downsell a nivel compañía, ver scripts/fetch_metrics.py::_apply_arr_walk_v2)
    # ya no separa cross-sell/pricing de Upsell/Downsell — Net Expansion pasa a ser
    # simplemente Upsell + Downsell, sin ningún signo que verificar acá. R3 sigue
    # validando que el walk balancee en conjunto.

    # R9 — Consistencia MoM vs QoQ según mes de cierre de quarter
    try:
        cutoff_month = metrics["cutoff_month"]  # 'YYYY-MM'
        month_num = int(cutoff_month.split("-")[1])
        expected_quarter_end = month_num in (3, 6, 9, 12)
        actual = bool(metrics["is_quarter_end"])
        status = "PASS" if actual == expected_quarter_end else "FAIL"
        results.append(CheckResult(
            "R9", "is_quarter_end consistente con el mes de corte", status,
            f"cutoff_month={cutoff_month} → esperado={expected_quarter_end}, metrics.yaml={actual}",
        ))
    except Exception as e:
        results.append(CheckResult("R9", "is_quarter_end consistente con el mes de corte", "SKIP", f"error: {e}"))

    # R10 — Churn Rate global entre 0% y 20%
    try:
        churn_pct = parse_cell(metrics["logo_churn_global"])
        status = "PASS" if CHURN_MIN_PCT <= churn_pct <= CHURN_MAX_PCT else "FAIL"
        results.append(CheckResult(
            "R10", f"Logo Churn Global entre {CHURN_MIN_PCT}% y {CHURN_MAX_PCT}%", status,
            f"logo_churn_global={churn_pct}%",
        ))
    except Exception as e:
        results.append(CheckResult("R10", "Logo Churn Global entre 0% y 20%", "SKIP", f"error: {e}"))

    results.append(_check_r7_logos_dedup(metrics))
    results.append(_check_r11_budget_quarter(metrics))
    results.append(_check_r17_pnl_present(metrics))

    # R12 — Número de slides en el standalone ≈ 47 (selector real de generate_pdf.py)
    try:
        n_slides = _count_slides(html_path)
        if n_slides >= paths.EXPECTED_SLIDE_COUNT - 2:
            status = "PASS"
        elif n_slides >= paths.MIN_SLIDE_COUNT_WARNING:
            status = "WARN"
        else:
            status = "FAIL"
        results.append(CheckResult(
            "R12", f"~{paths.EXPECTED_SLIDE_COUNT} slides en el standalone", status,
            f"encontrados={n_slides}",
        ))
    except Exception as e:
        results.append(CheckResult("R12", f"~{paths.EXPECTED_SLIDE_COUNT} slides en el standalone", "SKIP", f"error: {e}"))

    results.extend(_check_color_rules(html_path))
    results.append(_check_r16_slide_dimensions(html_path))
    results.append(_check_r18_slide_overflow(html_path))
    results.append(_check_r19_arr_slide_consistency(html_path))
    results.append(_check_r20_seg_stock_sums(metrics))

    return results
