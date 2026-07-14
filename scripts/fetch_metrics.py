#!/usr/bin/env python3
"""
fetch_metrics.py — Ensambla data/metrics.yaml a partir de data/.metabase_cache.json

Migración 2026-07-10: este script ya NO se conecta a Redshift. Lee filas ya obtenidas
por Claude Code vía el MCP de Metabase (ver board_agent/metabase_fetch_spec.py) desde
METABASE_CACHE_FILE — populalo antes de correr este script.

Usage:
    uv run --with pyyaml python3 scripts/fetch_metrics.py
    uv run --with pyyaml python3 scripts/fetch_metrics.py --refresh
    uv run --with pyyaml python3 scripts/fetch_metrics.py --month 2026-02

Outputs:
    data/metrics.yaml   (consumed by generate.py → Jinja2 templates)

Sources:
    - dm_strategic.fact_cac_version_segments  (Investment)
    - dm_strategic.fact_customers_mrr         (logos consolidados + country-level)

Data NOT covered here (needs fetch_sheets.py):
    - Budget / Plan  (arr_vs_budget, new_mrr_vs_budget, etc.)
    - Gross Margin / EBITDA  (financial P&L)
    - Payback period
    Placeholders are written as "N/A" so templates render without crashing.
"""

import sys, json, argparse, time, math, csv, calendar
from datetime import datetime
from collections import defaultdict
from pathlib import Path

import yaml  # pip install pyyaml (or uv run --with pyyaml)

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent
CACHE_FILE     = ROOT / "data" / ".cache_metrics.json"
RAW_CACHE_FILE = ROOT / "data" / ".raw_cache.yaml"
OUTPUT_FILE    = ROOT / "data" / "metrics.yaml"
# Resultados de las queries MBQL ya ejecutadas por Claude Code vía el MCP de Metabase
# (mcp__metabase__*) — este script YA NO habla con Redshift ni con boto3 (migración
# 2026-07-10, ver memory/project_board_agent.md y board_agent/metabase_fetch_spec.py
# para el detalle de qué query MBQL llena cada clave). No hay ningún script que lo
# puebla automáticamente — Claude Code escribe cada resultado a mano en este JSON,
# vía el MCP de Metabase, antes de correr este script (proceso manual, no un job).
METABASE_CACHE_FILE = ROOT / "data" / ".metabase_cache.json"
BUDGET_FILE  = ROOT / "csv" / "Metricas_budget.csv"
PNL_ACTUAL   = ROOT / "csv" / "P&L Histórico- ACtual.csv"
PNL_BUDGET   = ROOT / "csv" / "P&L Histórico - Budget.csv"

# ── FX Conversion ───────────────────────────────────────────────────────────────
# Los 5 países con conversión propia — el resto usa amount_mrr tal cual (ya en USD)
_FX_PAISES = {"argentina", "colombia", "mexico", "peru", "spain"}

# dwh_dimensions.tb_trm_banrep (RS, cluster-2) — reemplaza csv/paises_fx.csv desde 2026-07-03
# (ver memory/project_board_agent.md). Mismas tasas Banco de la República que se venían
# copiando a mano al CSV — confirmado idéntico para mayo-26 (COP=3714.02, MEX=17.32, PEN=3.44).
_SQL_FX_BANREP = """
SELECT month, cop_usd, ars_usd, eur_usd, mex_usd, pen_usd
FROM dwh_dimensions.tb_trm_banrep
ORDER BY month
"""
_FX_COL_TO_PAIS = {
    "cop_usd": "colombia",
    "ars_usd": "argentina",
    "eur_usd": "spain",
    "mex_usd": "mexico",
    "pen_usd": "peru",
}

# Decimales a usar por país al redondear la tasa FX
# CO/AR → entero; MX/PE → 1 decimal; ES → 3 decimales
_FX_DECIMALS = {
    "colombia":  0,
    "argentina": 0,
    "mexico":    1,
    "peru":      1,
    "spain":     3,
}

# Mapeo de app_version (Redshift) → nombre en paises_fx.csv
_APP_TO_FX_PAIS = {
    "colombia":  "colombia",
    "mexico":    "mexico",
    "argentina": "argentina",
    "peru":      "peru",
    "spain":     "spain",
    "españa":    "spain",
    "espana":    "spain",
}

_fx_cache = None

def load_fx():
    """Carga tasas FX desde dwh_dimensions.tb_trm_banrep (RS) → {(pais, 'YYYY-MM'): fx_rate}.
    Memoizado en proceso — se llama más de una vez por corrida (load_data + arr_walk_table)
    y antes era gratis porque leía un CSV local; ahora cada llamada es una query a RS."""
    global _fx_cache
    if _fx_cache is not None:
        return _fx_cache
    fx = {}
    rows = _pages_or_missing("tasas FX (tb_trm_banrep)", [],
                              "tb_trm_banrep no disponible — usando amount_usd_mrr sin conversión FX")
    for row in rows:
        mes = str(row.get("month") or "")[:7]  # "YYYY-MM"
        if not mes:
            continue
        for col, pais in _FX_COL_TO_PAIS.items():
            val = row.get(col)
            if val is None:
                continue
            decimals = _FX_DECIMALS.get(pais, 0)
            fx[(pais, mes)] = round(float(val), decimals)
    _fx_cache = fx
    return fx

_SQL_ALANUBE_ARR = """
SELECT month_date,
       SUM(CASE WHEN event_type <> 'C' THEN arr_local ELSE 0 END) AS arr_eop
FROM bi_alanube.fact_alanube_arr_walk
GROUP BY 1
ORDER BY 1
"""

_alanube_arr_cache = None

def load_alanube_arr():
    """ARR EoP mensual de Alanube desde bi_alanube.fact_alanube_arr_walk (RS) → {'YYYY-MM': USD}.
    Reemplaza data/chart_alanube.yaml (manual) desde 2026-07-03 — ver memory/project_board_agent.md.
    Fórmula validada contra los valores conocidos de mar/abr/may-26 (diff < 0.5%): SUM(arr_local)
    de TODOS los event_type excepto 'C' (Churn) — arr_local, pese al nombre, ya viene en USD
    (columna sin renombrar tras el fix, confirmado por el equipo de Alanube). Requiere
    db_user="sebastian-hernandez" (permisos de bi_alanube.*, ya el default de _run())."""
    global _alanube_arr_cache
    if _alanube_arr_cache is not None:
        return _alanube_arr_cache
    out = {}
    rows = _pages_or_missing("ARR Alanube (fact_alanube_arr_walk)", [],
                              "bi_alanube.fact_alanube_arr_walk no disponible — ARR Alanube en $0")
    for row in rows:
        mes = str(row.get("month_date") or "")[:7]  # "YYYY-MM"
        val = row.get("arr_eop")
        if mes and val is not None:
            out[mes] = float(val)
    _alanube_arr_cache = out
    return out

_alanube_walk_raw_cache = None

def load_alanube_walk_raw():
    """Grano cliente×mes completo de bi_alanube.fact_alanube_arr_walk (~3.5K filas, se trae
    entero) → lista de dicts. Base para _build_alanube_walk() (Logo Walk + ARR Walk + Finance/
    Operation Metrics de la slide 9 de 1_inicio.j2, 'ARR Walk — Alanube'). event_type: ''=sin
    cambio, N=new, R=recovered, U=upgrade, D=downgrade, C=churn. arr_local es el valor
    ABSOLUTO del mes (no delta) — confirmado 2026-07-06 comparando el mismo cliente mes a mes
    (ej. CLOUDYA SRL: abr=1434.72 'U' → may=1984.80 'U', delta real=550.08, no 1984.80)."""
    global _alanube_walk_raw_cache
    if _alanube_walk_raw_cache is not None:
        return _alanube_walk_raw_cache
    out = []
    rows = _pages_or_missing("Alanube ARR Walk completo (fact_alanube_arr_walk)", [],
                              "fact_alanube_arr_walk (completo) no disponible")
    for r in rows:
        mes = str(r.get("month_date") or "")[:7]
        if not mes or r.get("name") is None:
            continue
        out.append({
            "name": r["name"], "month": mes,
            "arr": float(r.get("arr_local") or 0),
            "event_type": (r.get("event_type") or "").strip(),
            "docs": float(r.get("documentos") or 0),
            "otr": float(r.get("otr") or 0),
        })
    _alanube_walk_raw_cache = out
    return out


_alanube_monthly_cache = None

def _build_alanube_monthly():
    """Arma la serie mensual completa de Logo Walk + ARR Walk + docs/OTR de Alanube, un dict
    por mes con todos los buckets ya calculados (BoP, New, Recovered, Expansion, Contraction,
    Churned, FX residual, EoP). Expansion/Contraction/Churned requieren comparar el arr_local
    del cliente contra su propio valor del mes anterior (self-join por 'name', ver docstring
    de load_alanube_walk_raw) — no se puede calcular con un simple SUM por event_type."""
    global _alanube_monthly_cache
    if _alanube_monthly_cache is not None:
        return _alanube_monthly_cache

    rows = load_alanube_walk_raw()
    by_month, by_month_name = {}, {}
    for r in rows:
        by_month.setdefault(r["month"], []).append(r)
        by_month_name[(r["month"], r["name"])] = r

    months_all = sorted(by_month.keys())
    monthly = {}
    for m in months_all:
        mrows = by_month[m]
        pm = _prev_m(m)
        names_eop = {r["name"] for r in mrows if r["event_type"] != "C"}
        d = {
            "logos_eop": len(names_eop),
            "logos_new": len({r["name"] for r in mrows if r["event_type"] == "N"}),
            "logos_rec": len({r["name"] for r in mrows if r["event_type"] == "R"}),
            "logos_chu": len({r["name"] for r in mrows if r["event_type"] == "C"}),
            "arr_eop": sum(r["arr"] for r in mrows if r["event_type"] != "C"),
            "arr_new": sum(r["arr"] for r in mrows if r["event_type"] == "N"),
            "arr_rec": sum(r["arr"] for r in mrows if r["event_type"] == "R"),
            "docs": sum(r["docs"] for r in mrows),
            "otr": sum(r["otr"] for r in mrows),
        }
        arr_exp = arr_con = arr_chu = 0.0
        for r in mrows:
            if r["event_type"] in ("U", "D"):
                prev = by_month_name.get((pm, r["name"]))
                delta = r["arr"] - (prev["arr"] if prev else 0.0)
                if r["event_type"] == "U":
                    arr_exp += delta
                else:
                    arr_con += delta
            elif r["event_type"] == "C":
                prev = by_month_name.get((pm, r["name"]))
                if prev:
                    arr_chu -= prev["arr"]
        d["arr_exp"], d["arr_con"], d["arr_chu"] = arr_exp, arr_con, arr_chu
        monthly[m] = d

    for m in months_all:
        pm = _prev_m(m)
        d = monthly[m]
        d["logos_bop"] = monthly.get(pm, {}).get("logos_eop", 0)
        d["arr_bop"] = monthly.get(pm, {}).get("arr_eop", 0.0)
        # FX = residual — mismo criterio que el ARR Walk GLO/Core/Lite de Alegra (ver CLAUDE.md):
        # garantiza que el walk balancee exacto (BoP + buckets + FX = EoP) por construcción.
        d["arr_fx"] = d["arr_eop"] - (d["arr_bop"] + d["arr_new"] + d["arr_rec"] + d["arr_exp"] + d["arr_con"] + d["arr_chu"])

    _alanube_monthly_cache = monthly
    return monthly


_ALANUBE_QUARTERS_2025 = [
    ("1Q25", ["2025-01", "2025-02", "2025-03"]),
    ("2Q25", ["2025-04", "2025-05", "2025-06"]),
    ("3Q25", ["2025-07", "2025-08", "2025-09"]),
    ("4Q25", ["2025-10", "2025-11", "2025-12"]),
]


def _alanube_period_agg(monthly, months):
    """Agrega una lista de meses consecutivos a un período (trimestre, YTD, etc). BoP/EoP
    (stock) toman el primer/último mes; el resto (flujos) se suman."""
    months = [m for m in months if m in monthly]
    if not months:
        return None
    first, last = months[0], months[-1]
    return {
        "logos_bop": monthly[first]["logos_bop"], "logos_eop": monthly[last]["logos_eop"],
        "logos_new": sum(monthly[m]["logos_new"] for m in months),
        "logos_rec": sum(monthly[m]["logos_rec"] for m in months),
        "logos_chu": sum(monthly[m]["logos_chu"] for m in months),
        "arr_bop": monthly[first]["arr_bop"], "arr_eop": monthly[last]["arr_eop"],
        "arr_new": sum(monthly[m]["arr_new"] for m in months),
        "arr_rec": sum(monthly[m]["arr_rec"] for m in months),
        "arr_exp": sum(monthly[m]["arr_exp"] for m in months),
        "arr_con": sum(monthly[m]["arr_con"] for m in months),
        "arr_chu": sum(monthly[m]["arr_chu"] for m in months),
        "arr_fx":  sum(monthly[m]["arr_fx"] for m in months),
        "docs": sum(monthly[m]["docs"] for m in months),
        "otr":  sum(monthly[m]["otr"]  for m in months),
        "n_months": len(months),
    }


def _al_mm(v):
    """Formato 'MM USD' estilo del template: coma decimal, paréntesis si es negativo (ej. '0,94' / '(0,06)')."""
    v_mm = v / 1e6
    return f"({abs(v_mm):.2f})".replace(".", ",") if v_mm < 0 else f"{v_mm:.2f}".replace(".", ",")


def _al_k(v):
    """Formato 'K USD' (OTR): coma decimal, 1 decimal."""
    return f"{v / 1e3:.1f}".replace(".", ",")


def _al_pct(cur, prev):
    """% con coma decimal y paréntesis si es negativo — '—' si no hay base."""
    if not prev:
        return "—"
    pct = (cur - prev) / abs(prev) * 100
    return f"({abs(pct):.0f}%)" if pct < 0 else f"{pct:.0f}%"


def _al_money(v):
    return f"${v:,.0f}"


def _al_docs_mm(v):
    return f"{v / 1e6:.1f}".replace(".", ",")


def _al_docs_k(v):
    """v ya viene en docs/logo (no dividido por 1000 todavía)."""
    return f"{v / 1e3:.1f}".replace(".", ",")


def _al_price_per_doc_raw(arr_eop, avg_monthly_docs, logos_eop):
    """Precio por documento = (ARR EoP/12) / (docs promedio mensual / Logos EoP), es decir
    ARR mensual total ÷ documentos-por-logo mensual. Fórmula NO obvia (mezcla un total con un
    promedio per-logo) pero reproduce EXACTO el 'Summary' oficial de Alanube (hoja de cálculo
    fuente, `Super Skills/ARR Walk Alanube - May-26_final.xlsx`) — validado 2026-07-06 en
    1Q25 (0,327), 2Q25 (0,605), 3Q25 (0,683), todos exactos. Devuelve el número crudo (sin
    formatear) para que _finalize() pueda calcular el delta% antes de convertirlo a texto."""
    if not logos_eop or not avg_monthly_docs:
        return None
    docs_per_logo = avg_monthly_docs / logos_eop
    return (arr_eop / 12) / docs_per_logo


def _shift_months(months, offset):
    """Desplaza una lista de meses 'YYYY-MM' por offset meses (negativo = hacia atrás)."""
    out = []
    for mo_iso in months:
        yy, mm = int(mo_iso[:4]), int(mo_iso[5:])
        idx = yy * 12 + (mm - 1) + offset
        out.append(f"{idx // 12:04d}-{idx % 12 + 1:02d}")
    return out


def _build_alanube_walk_table(cutoff):
    """Slide 9 de 1_inicio.j2 ('ARR Walk — Alanube') — Logo Walk + ARR Walk + Finance/Operation
    Metrics, histórico trimestral (1Q25-4Q25 fijo) + período actual (mes o trimestre según
    is_quarter_end) + YTD. Fuente: bi_alanube.fact_alanube_arr_walk vía _build_alanube_monthly().
    Reemplaza el hardcode manual que existía desde antes — ver memory/project_board_agent.md
    2026-07-06 para la validación completa (EoP exacto, Logos con desfase de 2-4 unidades sin
    explicar, 'Price per Document' no reproducido exacto)."""
    monthly = _build_alanube_monthly()
    y, m = int(cutoff[:4]), int(cutoff[5:])
    is_q_end = m in (3, 6, 9, 12)

    period_months = [ms for _, ms in _ALANUBE_QUARTERS_2025]

    if is_q_end:
        cur_months_list = [[f"{y:04d}-{mm:02d}" for mm in range(m - 2, m + 1)]]
        cur_labels = [f"{(m // 3)}Q{y % 100:02d}"]
    else:
        m1 = _prev_m(cutoff)
        cur_months_list = [[m1], [cutoff]]
        cur_labels = [_month_label(m1), _month_label(cutoff)]

    ytd_py_months = [f"{y - 1:04d}-{mm:02d}" for mm in range(1, m + 1)]  # misma ventana que ytd_cy (Ene→cutoff), no el año completo
    ytd_cy_months = [f"{y:04d}-{mm:02d}" for mm in range(1, m + 1)]

    all_months_lists = period_months + cur_months_list + [ytd_py_months, ytd_cy_months]
    all_periods = [_alanube_period_agg(monthly, ms) for ms in all_months_lists]
    # YoY: mismo período, 12 meses atrás (ej. 1Q25 → 1Q24; mayo-26 → mayo-25; YTD-26 → YTD-25)
    yoy_periods = [_alanube_period_agg(monthly, _shift_months(ms, -12)) for ms in all_months_lists]

    # En cierre de Q solo hay 1 columna "actual" (el trimestre), así que el delta "QoQ%" no
    # se puede sacar comparando 2 columnas actuales entre sí (como sí se hace en meses
    # normales) — hace falta el trimestre ANTERIOR como referencia. Relevante ya para el
    # próximo mes real (jun-2026 = 2Q26, cierre de Q).
    prev_q_period = prev_q_yoy_period = None
    if is_q_end:
        prev_q_last = _shift_months([cutoff], -3)[0]
        py, pm = int(prev_q_last[:4]), int(prev_q_last[5:])
        prev_q_months = [f"{py:04d}-{mm:02d}" for mm in range(pm - 2, pm + 1)]
        prev_q_period = _alanube_period_agg(monthly, prev_q_months)
        prev_q_yoy_period = _alanube_period_agg(monthly, _shift_months(prev_q_months, -12))

    n_cur = len(cur_months_list)  # 1 si cierre de Q, 2 si mes normal

    def _finalize(get_value_or_raw, formatter, prev_q_value=None):
        """Reparte en {quarters, current, ytd_py, ytd_cy} + calcula 'current_delta'/'ytd_delta'
        como el %-cambio entre los propios valores de la fila (mismo patrón en las ~17 filas
        de la tabla — confirmado contra el hardcode: ej. Logos BoP delta=(May-Apr)/Apr, no una
        fórmula distinta por fila). prev_q_value: valor de la fila para el trimestre ANTERIOR
        — solo se usa en cierre de Q, donde 'current' tiene 1 sola columna y no hay con qué
        comparar sin él. get_value_or_raw acepta un callable (se mapea sobre all_periods) o
        una lista cruda ya construida (ej. growth_yoy_pct, que combina 2 series distintas)."""
        if callable(get_value_or_raw):
            raw = [None if p is None else get_value_or_raw(p) for p in all_periods]
        else:
            raw = get_value_or_raw
        cur_raw = raw[4:4 + n_cur]
        ytd_py_raw, ytd_cy_raw = raw[-2], raw[-1]
        if len(cur_raw) > 1:
            cur_delta = _al_pct(cur_raw[-1], cur_raw[0])
        elif cur_raw and cur_raw[0] is not None and prev_q_value is not None:
            cur_delta = _al_pct(cur_raw[0], prev_q_value)
        else:
            cur_delta = "—"
        ytd_delta = _al_pct(ytd_cy_raw, ytd_py_raw)
        fmt = lambda v: "—" if v is None else formatter(v)
        return {
            "quarters": [fmt(v) for v in raw[:4]],
            "current": [fmt(v) for v in cur_raw],
            "ytd_py": fmt(ytd_py_raw), "ytd_cy": fmt(ytd_cy_raw),
            "current_delta": cur_delta, "ytd_delta": ytd_delta,
        }

    def _pq(get_value):
        """Valor de prev_q_period para esta fila (None si no es cierre de Q o no hay dato)."""
        return None if prev_q_period is None else get_value(prev_q_period)

    _fmt_neg = lambda v: f"({v})"
    _fmt_pct1 = lambda v: (f"({abs(v):.1f}%)" if v < 0 else f"{v:.1f}%")

    return {
        "current_labels": cur_labels,
        "is_quarter_end": is_q_end,
        "current_header_label": ("QoQ%" if is_q_end else "MoM A%"),
        "logos": {
            "bop": _finalize(lambda p: p["logos_bop"], str, _pq(lambda p: p["logos_bop"])),
            "new": _finalize(lambda p: p["logos_new"], str, _pq(lambda p: p["logos_new"])),
            "recovered": _finalize(lambda p: p["logos_rec"], str, _pq(lambda p: p["logos_rec"])),
            "churned": _finalize(lambda p: p["logos_chu"], _fmt_neg, _pq(lambda p: p["logos_chu"])),
            "eop": _finalize(lambda p: p["logos_eop"], str, _pq(lambda p: p["logos_eop"])),
        },
        "arr": {
            "bop": _finalize(lambda p: p["arr_bop"], _al_mm, _pq(lambda p: p["arr_bop"])),
            "new": _finalize(lambda p: p["arr_new"], _al_mm, _pq(lambda p: p["arr_new"])),
            "recovered": _finalize(lambda p: p["arr_rec"], _al_mm, _pq(lambda p: p["arr_rec"])),
            "expansion": _finalize(lambda p: p["arr_exp"], _al_mm, _pq(lambda p: p["arr_exp"])),
            "contraction": _finalize(lambda p: p["arr_con"], _al_mm, _pq(lambda p: p["arr_con"])),
            "churned": _finalize(lambda p: p["arr_chu"], _al_mm, _pq(lambda p: p["arr_chu"])),
            "fx": _finalize(lambda p: p["arr_fx"], _al_mm, _pq(lambda p: p["arr_fx"])),
            "eop": _finalize(lambda p: p["arr_eop"], _al_mm, _pq(lambda p: p["arr_eop"])),
            "otr": _finalize(lambda p: p["otr"], _al_k, _pq(lambda p: p["otr"])),
        },
        "finance": {
            # Growth Rate MoM/QoQ: NO reconcilia con (EoP-BoP)/BoP ni siquiera en el Excel
            # fuente oficial (Super Skills/ARR Walk Alanube - May-26_final.xlsx, hoja Summary) —
            # se probó con sus propios BoP/EoP y tampoco da los números que ellos muestran.
            # Se usa la fórmula estándar (documentada, difiere del histórico) — ver
            # memory/project_board_agent.md 2026-07-06.
            "growth_pct": _finalize(
                lambda p: (p["arr_eop"] - p["arr_bop"]) / p["arr_bop"] * 100 if p["arr_bop"] else None,
                _fmt_pct1,
                _pq(lambda p: (p["arr_eop"] - p["arr_bop"]) / p["arr_bop"] * 100 if p["arr_bop"] else None)),
            "growth_yoy_pct": _finalize(
                [None if (c is None or y is None or not y.get("arr_eop")) else (c["arr_eop"] - y["arr_eop"]) / y["arr_eop"] * 100
                 for c, y in zip(all_periods, yoy_periods)],
                _fmt_pct1,
                (None if not (is_q_end and prev_q_period and prev_q_yoy_period and prev_q_yoy_period.get("arr_eop"))
                 else (prev_q_period["arr_eop"] - prev_q_yoy_period["arr_eop"]) / prev_q_yoy_period["arr_eop"] * 100)),
            # Avg. ARR per Logo: misma salvedad que Growth Rate — no reconcilia ni contra el Excel fuente.
            "arr_per_logo": _finalize(
                lambda p: p["arr_eop"] / p["logos_eop"] / 12 if p["logos_eop"] else None,
                _al_money,
                _pq(lambda p: p["arr_eop"] / p["logos_eop"] / 12 if p["logos_eop"] else None)),
            "churn_rate_pct": _finalize(
                lambda p: abs(p["arr_chu"]) / p["arr_bop"] * 100 if p["arr_bop"] else None,
                lambda v: f"({v:.1f}%)",
                _pq(lambda p: abs(p["arr_chu"]) / p["arr_bop"] * 100 if p["arr_bop"] else None)),
        },
        "operation": {
            # "Avg. Monthly" — promedio mensual DENTRO del período (docs/n_months), no la suma.
            # Confirmado 2026-07-06 contra las 4 columnas trimestrales ya hardcodeadas (suma÷3 =
            # valor publicado, exacto). Para el mes de corte n_months=1 (no-op).
            "docs_mm": _finalize(
                lambda p: p["docs"] / p["n_months"], _al_docs_mm,
                _pq(lambda p: p["docs"] / p["n_months"])),
            "docs_per_logo_k": _finalize(
                lambda p: (p["docs"] / p["n_months"]) / p["logos_eop"] if p["logos_eop"] else None, _al_docs_k,
                _pq(lambda p: (p["docs"] / p["n_months"]) / p["logos_eop"] if p["logos_eop"] else None)),
            "price_per_doc": _finalize(
                lambda p: _al_price_per_doc_raw(p["arr_eop"], p["docs"] / p["n_months"], p["logos_eop"]),
                lambda v: f"{v:.1f}".replace(".", ","),
                _pq(lambda p: _al_price_per_doc_raw(p["arr_eop"], p["docs"] / p["n_months"], p["logos_eop"]))),
        },
    }

_HC_SCHEMA = "bi_strategic_relationships"
_headcount_eop_cache = None
_headcount_forecast_cache = None
_headcount_movements_cache = None
_headcount_categories_cache = None

def load_headcount_eop():
    """Headcount EoP real, por mes y equipo, desde bi_strategic_relationships.fact_headcount_eop (RS)
    → {(team, 'YYYY-MM'): headcount}. Reemplaza el copy/paste manual del Sheet EoP para 7_headcount.j2
    desde 2026-07-03 — ver memory/project_board_agent.md. Volumen trivial (~1.6K filas), se trae
    completo y se filtra en Python."""
    global _headcount_eop_cache
    if _headcount_eop_cache is not None:
        return _headcount_eop_cache
    out = {}
    rows = _pages_or_missing("Headcount EoP (fact_headcount_eop)", [],
                              "fact_headcount_eop no disponible — Headcount en blanco")
    for row in rows:
        mes = str(row.get("fecha") or "")[:7]
        if mes and row.get("team") is not None and row.get("headcount") is not None:
            out[(row["team"], mes)] = int(row["headcount"])
    _headcount_eop_cache = out
    return out

def load_headcount_forecast():
    """Forecast de headcount por mes proyectado y equipo → {(team, 'YYYY-MM'): headcount_fcst}.
    Solo equipos CON presupuesto (13 de 21) — la ausencia de una fila se trata como Fcst=0."""
    global _headcount_forecast_cache
    if _headcount_forecast_cache is not None:
        return _headcount_forecast_cache
    out = {}
    rows = _pages_or_missing("Headcount Forecast (fact_headcount_forecast)", [],
                              "fact_headcount_forecast no disponible — Forecast en 0")
    for row in rows:
        mes = str(row.get("fecha") or "")[:7]
        if mes and row.get("team") is not None and row.get("headcount_fcst") is not None:
            out[(row["team"], mes)] = int(row["headcount_fcst"])
    _headcount_forecast_cache = out
    return out

def load_headcount_movements():
    """Movimientos (contrataciones/salidas) por mes y equipo → {(team, 'YYYY-MM'): (new_hires, attrition)}.
    Ya vienen agregados por equipo en el Sheet fuente, no a nivel de persona."""
    global _headcount_movements_cache
    if _headcount_movements_cache is not None:
        return _headcount_movements_cache
    out = {}
    rows = _pages_or_missing("Headcount Movements (fact_headcount_movements)", [],
                              "fact_headcount_movements no disponible — Movimientos en 0")
    for row in rows:
        mes = str(row.get("fecha") or "")[:7]
        if mes and row.get("team") is not None:
            out[(row["team"], mes)] = (int(row.get("new_hires") or 0), int(row.get("attrition") or 0))
    _headcount_movements_cache = out
    return out

def load_headcount_categories():
    """Mapeo equipo → categoría P&L → {team: category}. 21 equipos en 6 categorías."""
    global _headcount_categories_cache
    if _headcount_categories_cache is not None:
        return _headcount_categories_cache
    out = {}
    rows = _pages_or_missing("Headcount categorías (dim_headcount_team_category)", [],
                              "dim_headcount_team_category no disponible — sin categorías")
    for row in rows:
        if row.get("team") is not None:
            out[row["team"]] = row.get("category") or "Other"
    _headcount_categories_cache = out
    return out

_PAYBACK_DIM_TO_KEY = {
    "global": ("Todos", "Total"), "global_core": ("Todos", "Core"), "global_lite": ("Todos", "Lite"),
    "colombia": ("colombia", "Total"), "colombia_core": ("colombia", "Core"), "colombia_lite": ("colombia", "Lite"),
    "mexico": ("mexico", "Total"), "mexico_core": ("mexico", "Core"), "mexico_lite": ("mexico", "Lite"),
    "rd": ("republicaDominicana", "Total"), "rd_core": ("republicaDominicana", "Core"), "rd_lite": ("republicaDominicana", "Lite"),
    "cr": ("costaRica", "Total"), "cr_core": ("costaRica", "Core"), "cr_lite": ("costaRica", "Lite"),
}
_payback_cache = None

def load_payback():
    """PB Proy. Base (pb_base) por país/segmento/mes desde bi_strategic.payback_cohort_results (RS)
    → {(Type, Segment): {'YYYY-MM': meses}} — mismas claves que usaba el CSV manual (Type="Todos"
    para global, Segment="Total"/"Core"/"Lite") para no tener que tocar los consumidores.
    Reemplaza csv/Payback.csv desde 2026-07-04 — ver memory/project_board_agent.md.

    model='nc' (New CAC) es el que corresponde a "PB Proy. Base" — confirmado porque su columna
    investment coincide exacto con el New CAC ya validado independientemente (Colombia Core
    mayo-26: $298,924). RS sale sistemáticamente 5-12% más alto que el Sheet manual para CO/MX
    (RD casi exacto, CR mixto) — confirmado con el usuario 2026-07-04 que es esperado (diferencia
    de metodología del motor nuevo vs. el proceso manual viejo), no es un bug."""
    global _payback_cache
    if _payback_cache is not None:
        return _payback_cache
    out = {}
    rows = _pages_or_missing("Payback (bi_strategic.payback_cohort_results)", [],
                              "bi_strategic.payback_cohort_results no disponible — Payback en blanco")
    for row in rows:
        key = _PAYBACK_DIM_TO_KEY.get(row.get("dimension"))
        mes = str(row.get("cohort_month") or "")[:7]
        val = row.get("pb_base")
        if key and mes and val is not None:
            out.setdefault(key, {})[mes] = float(val)
    _payback_cache = out
    return out

_M13_PLUS_BRACKETS = {
    "M13-M15", "M16-M18", "M19-M24", "M25-M30",
    "M31-M36", "M37-M42", "M43-M48", "M49+",
}
_CHURN_TENURE_BRACKETS = ["M1-M3", "M4-M6", "M7-M9", "M10-M12", "M13+"]

_SQL_CHURN_TENURE = """
WITH
fp AS (
  SELECT id_company, app_version, MIN(DATE_TRUNC('month', date_month)) AS fp_month
  FROM dwh_facts.fact_customers_mrr
  WHERE event_logo = 'NEW' AND event_product NOT IN ('AWAITING PAYMENT','CHURN')
    AND amount_usd_mrr > 0 AND date_month <= '{cutoff}-01'
  GROUP BY 1, 2
),
churners AS (
  SELECT r.id_company, r.app_version, r.date_month, r.team_manage,
         CASE WHEN r.segment IN ('Core','Lite') THEN r.segment ELSE 'Otro' END AS segmento,
         DATEDIFF('month', COALESCE(fp.fp_month, DATEADD('month', -60, r.date_month)), r.date_month) AS months_tenure
  FROM db_retention.bi_churn_retired r
  LEFT JOIN fp ON fp.id_company = r.id_company AND fp.app_version = r.app_version
  WHERE r.date_month >= '2025-01-01' AND r.date_month <= '{cutoff}-01'
    AND r.team_manage IN ('Voluntary', 'Delinquent')
),
churners_bracketed AS (
  SELECT date_month, segmento, team_manage, months_tenure,
    CASE
      WHEN months_tenure BETWEEN  0 AND  2 THEN 'M1-M3'
      WHEN months_tenure BETWEEN  3 AND  5 THEN 'M4-M6'
      WHEN months_tenure BETWEEN  6 AND  8 THEN 'M7-M9'
      WHEN months_tenure BETWEEN  9 AND 11 THEN 'M10-M12'
      WHEN months_tenure BETWEEN 12 AND 14 THEN 'M13-M15'
      WHEN months_tenure BETWEEN 15 AND 17 THEN 'M16-M18'
      WHEN months_tenure BETWEEN 18 AND 23 THEN 'M19-M24'
      WHEN months_tenure BETWEEN 24 AND 29 THEN 'M25-M30'
      WHEN months_tenure BETWEEN 30 AND 35 THEN 'M31-M36'
      WHEN months_tenure BETWEEN 36 AND 41 THEN 'M37-M42'
      WHEN months_tenure BETWEEN 42 AND 47 THEN 'M43-M48'
      ELSE                                       'M49+'
    END AS bracket,
    id_company
  FROM churners
),
churn_agg AS (
  SELECT TO_CHAR(date_month, 'YYYY-MM') AS mes, segmento, bracket,
    COUNT(DISTINCT id_company) AS logos_churn
  FROM churners_bracketed
  GROUP BY 1, 2, 3
),
active_with_tenure AS (
  SELECT m.id_company, m.app_version, m.date_month,
         CASE WHEN m.segment_type_def IN ('Core','Lite') THEN m.segment_type_def ELSE 'Otro' END AS segmento,
         DATEDIFF('month', COALESCE(fp.fp_month, DATEADD('month', -60, m.date_month)), m.date_month) AS months_tenure
  FROM dwh_facts.fact_customers_mrr m
  LEFT JOIN fp ON fp.id_company = m.id_company AND fp.app_version = m.app_version
  WHERE m.date_month >= '2024-12-01' AND m.date_month <= '{prev_cutoff}-01'
    AND m.event_logo NOT IN ('CHURN','AWAITING PAYMENT')
),
bop AS (
  SELECT TO_CHAR(DATEADD('month', 1, date_month), 'YYYY-MM') AS mes, segmento,
    CASE
      WHEN months_tenure BETWEEN  0 AND  2 THEN 'M1-M3'
      WHEN months_tenure BETWEEN  3 AND  5 THEN 'M4-M6'
      WHEN months_tenure BETWEEN  6 AND  8 THEN 'M7-M9'
      WHEN months_tenure BETWEEN  9 AND 11 THEN 'M10-M12'
      WHEN months_tenure BETWEEN 12 AND 14 THEN 'M13-M15'
      WHEN months_tenure BETWEEN 15 AND 17 THEN 'M16-M18'
      WHEN months_tenure BETWEEN 18 AND 23 THEN 'M19-M24'
      WHEN months_tenure BETWEEN 24 AND 29 THEN 'M25-M30'
      WHEN months_tenure BETWEEN 30 AND 35 THEN 'M31-M36'
      WHEN months_tenure BETWEEN 36 AND 41 THEN 'M37-M42'
      WHEN months_tenure BETWEEN 42 AND 47 THEN 'M43-M48'
      ELSE                                       'M49+'
    END AS bracket,
    COUNT(DISTINCT id_company) AS bop_logos
  FROM active_with_tenure
  GROUP BY 1, 2, 3
)
SELECT
  COALESCE(c.mes, b.mes) AS mes,
  COALESCE(c.segmento, b.segmento) AS segmento,
  COALESCE(c.bracket, b.bracket) AS bracket,
  COALESCE(c.logos_churn, 0) AS logos_churn
FROM churn_agg c
FULL OUTER JOIN bop b
  ON b.mes = c.mes AND b.segmento = c.segmento AND b.bracket = c.bracket
WHERE COALESCE(c.mes, b.mes) >= '2025-01'
  AND COALESCE(c.mes, b.mes) <= '{cutoff}'
  AND COALESCE(c.segmento, b.segmento) IN ('Core','Lite','Otro')
ORDER BY mes, segmento, bracket
"""

_churn_tenure_cache = {}

def _build_churn_tenure(cutoff):
    """'Churned by tenure' (8_appendix.j2, slides GLO/Core/Lite) desde RS — reemplaza el
    script externo ~/Downloads/board/update_board.py (perfil SSO alegra-data, db_user
    jhon-gallego) que vivía fuera de este proyecto, sin versionar en ningún repo. Migrado a
    _run() estándar (sebastian-hernandez) 2026-07-06 — confirmado que tiene permiso de
    lectura sobre db_retention.bi_churn_retired (174K filas). Misma lógica de
    Q41_churn_tenure_subbrackets.sql, parametrizada por cutoff en vez de fechas fijas."""
    if cutoff in _churn_tenure_cache:
        return _churn_tenure_cache[cutoff]
    prev_cutoff = _prev_m(cutoff)
    sql = _SQL_CHURN_TENURE.format(cutoff=cutoff, prev_cutoff=prev_cutoff)
    rows = _pages_or_missing("Churned by tenure (db_retention.bi_churn_retired)", [],
                              "Churned by tenure no disponible — appendix en blanco")

    agg = {}
    for r in rows:
        mes, seg, bracket = r.get("mes"), r.get("segmento"), r.get("bracket")
        if not (mes and seg and bracket):
            continue
        b = "M13+" if bracket in _M13_PLUS_BRACKETS else bracket
        agg[(mes, seg, b)] = agg.get((mes, seg, b), 0) + int(r.get("logos_churn") or 0)

    months_out = []
    data = {seg: {b: [] for b in _CHURN_TENURE_BRACKETS} for seg in ("Global", "Core", "Lite")}
    y, m = 2025, 1
    while f"{y:04d}-{m:02d}" <= cutoff:
        mes_iso = f"{y:04d}-{m:02d}"
        months_out.append(f"Jan {y % 100:02d}" if m == 1 else _MONTH_NAMES[m - 1])
        for b in _CHURN_TENURE_BRACKETS:
            core_v = agg.get((mes_iso, "Core", b), 0)
            lite_v = agg.get((mes_iso, "Lite", b), 0)
            otro_v = agg.get((mes_iso, "Otro", b), 0)
            data["Core"][b].append(core_v)
            data["Lite"][b].append(lite_v)
            data["Global"][b].append(core_v + lite_v + otro_v)
        m += 1
        if m == 13:
            m = 1; y += 1

    out = {"months": months_out, "data": data}
    _churn_tenure_cache[cutoff] = out
    return out

_NPS_SNAPSHOT_FILE = ROOT / "data" / "nps_snapshot.yaml"
_NPS_COUNTRIES = [("colombia", "Colombia"), ("mexico", "Mexico"),
                  ("dom_rep", "Dom. Rep."), ("costa_rica", "Costa Rica")]
_NPS_BAR_MAX = 75  # referencia visual para el ancho de barra "By Country" — no es un límite
                   # real de NPS (va de -100 a 100), es la escala elegida en el diseño
                   # original del template (63/47.4 ≈ 72/54.3 ≈ 70/52.4 ≈ 40/30.2 ≈ 1/75).


def _nps_delta(cur, prev):
    """Formatea un delta de NPS al estilo del template ('▲ +4.9 MoM' / '▼ -2.3 vs Mar')."""
    if cur is None or prev is None:
        return None, "neu"
    d = round(cur - prev, 1)
    if d > 0:
        return f"▲ +{d}", "pos"
    if d < 0:
        return f"▼ {d}", "neg"
    return "▬ 0.0", "neu"


def _build_nps(cutoff):
    """NPS (6_rd.j2 slide 3) desde snapshot asistido (data/nps_snapshot.yaml) — la fuente real
    es el dashboard de Amplitude (https://app.amplitude.com/analytics/alegra/dashboard/jvmfiss8),
    pero fetch_metrics.py no puede llamar al MCP de Amplitude (solo existe dentro de una sesión
    de Claude Code, no es una API que un script standalone pueda usar). Decisión del usuario
    2026-07-06: actualizar este YAML una vez al mes vía sesión de Claude en vez de screenshots.
    Se evaluó calcular esto 100% desde RS (db_amplitude_events.amplitude_events_gold ya tiene
    los eventos de encuesta) pero la fórmula reconstruida dio ~2-8% de diferencia vs Amplitude
    (no exacta) — el usuario prefirió el snapshot exacto por ahora. Ver memory/project_board_agent.md."""
    if not _NPS_SNAPSHOT_FILE.exists():
        return None
    snap = yaml.safe_load(_NPS_SNAPSHOT_FILE.read_text()) or {}
    m1, m2 = _prev_m(cutoff), _prev_m(_prev_m(cutoff))
    cur, d1, d2 = snap.get(cutoff), snap.get(m1) or {}, snap.get(m2) or {}
    if not cur:
        return None

    dist = cur.get("distribution") or {}
    by_country_cur = cur.get("by_country") or {}

    def _dist_pct(key):
        """Amplitude reporta cada % del chart de distribución redondeado de forma independiente
        (ej. mayo-26: 64.7+14.9+19.4 = 99.0%, no 100%) — mismo bug que Mayra detectó antes.
        Los 'n' de cada bucket sí suman exacto a 'responses', así que recalcular desde ahí
        garantiza que el total siempre dé 100%."""
        n, total = dist.get(f"{key}_n"), cur.get("responses")
        if n is not None and total:
            return round(n / total * 100, 1)
        return dist.get(f"{key}_pct")

    by_country_out = []
    for key, label in _NPS_COUNTRIES:
        score = by_country_cur.get(key)
        if score is None:
            continue
        by_country_out.append({
            "name": label, "score": f"{score:.1f}",
            "bar_pct": round(score / _NPS_BAR_MAX * 100),
        })

    def _trend_card(label, key=None):
        cur_v = cur.get("score") if key is None else (cur.get("by_country") or {}).get(key)
        v1 = d1.get("score") if key is None else (d1.get("by_country") or {}).get(key)
        v2 = d2.get("score") if key is None else (d2.get("by_country") or {}).get(key)
        mom_s, mom_c = _nps_delta(cur_v, v1)
        vs2_s, vs2_c = _nps_delta(cur_v, v2)
        return {
            "name": label,
            "v2": f"{v2:.1f}" if v2 is not None else "—",
            "v1": f"{v1:.1f}" if v1 is not None else "—",
            "cur": f"{cur_v:.1f}" if cur_v is not None else "—",
            "mom": mom_s or "—", "mom_class": mom_c,
            "vs2": vs2_s or "—", "vs2_class": vs2_c,
            "vs2_note": None if v2 is not None else f"{_MONTH_NAMES[int(m2[5:]) - 1]}: no data",
        }

    return {
        "score": f"{cur['score']:.1f}" if cur.get("score") is not None else "—",
        "responses": f"{cur['responses']:,}" if cur.get("responses") is not None else "—",
        "promoters_pct": _dist_pct("promoters"), "promoters_n": dist.get("promoters_n"),
        "passives_pct": _dist_pct("passives"), "passives_n": dist.get("passives_n"),
        "detractors_pct": _dist_pct("detractors"), "detractors_n": dist.get("detractors_n"),
        "by_country": by_country_out,
        "trend": [_trend_card("NPS Global"), _trend_card("Colombia", "colombia"),
                  _trend_card("Mexico", "mexico"), _trend_card("Dom. Rep.", "dom_rep")],
        "costa_rica_trend": _trend_card("Costa Rica", "costa_rica"),
        "trend_period_label": (f"{_MONTH_NAMES[int(m2[5:]) - 1]} → {_MONTH_NAMES[int(m1[5:]) - 1]} "
                                f"→ {_MONTH_NAMES[int(cutoff[5:]) - 1]} {cutoff[:4]}"),
    }

def _apply_fx_to_row(row, fx, cutoff):
    """Convierte mrr_usd_* de moneda local a USD para países FX.
    Para CO/MX/AR/PE/ES: amount_conv en SQL ya es amount_mrr (local) — dividir por tasa.
    El resto usa amount_usd_mrr directamente — no-op.

    mrr_usd_eop se divide por la tasa del PROPIO mes (spot histórico, como siempre).
    mrr_usd_eop_cc se divide por la tasa del mes de CORTE (constant currency real):
    mismo numerador en moneda local, revaluado siempre al FX vigente en el mes que
    se está reportando — así en el mes de corte CC == EoP regular (ratio FX=1).
    Antes mrr_usd_eop_cc tomaba amount_usd_mrr del warehouse sin ningún ajuste al
    mes de corte, por lo que nunca era realmente "constant currency" (bug real
    encontrado 2026-07-02/03, ver memory/project_board_agent.md)."""
    av = row.get("app_version", "")
    if av not in _FX_PAISES:
        return

    def _tasa(mes):
        t = fx.get((av, mes))
        if t:
            return t
        # fallback: tasa más reciente disponible para ese país (evita quedar sin conversión si el CSV no tiene el mes)
        meses_disp = sorted(k[1] for k in fx if k[0] == av)
        return fx.get((av, meses_disp[-1])) if meses_disp else None

    m = (row.get("date_month") or "")[:7]  # "YYYY-MM"
    tasa = _tasa(m)
    if not tasa:
        return
    mrr_fields = [
        "mrr_usd_eop", "mrr_usd_new_base_t0", "mrr_usd_new_cross_t0",
        "mrr_usd_recov", "mrr_usd_react", "mrr_usd_churn",
        "mrr_usd_upsell", "mrr_usd_downsell", "mrr_usd_pricing_others",
        "mrr_usd_cross_new_t1plus", "mrr_usd_cross_readop", "mrr_usd_cross_down",
    ]
    for f in mrr_fields:
        if row.get(f) is not None:
            row[f] = row[f] / tasa

    tasa_cutoff = _tasa(cutoff)
    if tasa_cutoff and row.get("mrr_usd_eop_cc") is not None:
        row["mrr_usd_eop_cc"] = row["mrr_usd_eop_cc"] / tasa_cutoff

CACHE_VERSION = "v38-nps-pct-from-n"

# ── SQL ────────────────────────────────────────────────────────────────────────
# Fuente única: dwh_facts.fact_customers_mrr — lógica canónica (walk-mrr-canonico.md)
# Buckets: new_base_t0, new_cross_t0, recov, react, churn (nivel producto),
#          upsell, downsell, pricing_others (comparación plan_name),
#          cross_new_t1plus, cross_readop, cross_down (logos activos que agregan/quitan productos)
# FX: CO/MX/AR/PE/ES → amount_conv = amount_mrr (local); resto → amount_conv = amount_usd_mrr
# _apply_fx_to_row() divide por tasa del mes para los 5 países FX
_SQL_FACT_SUMMARY = """
WITH mrr_base AS (
  SELECT id_company, app_version, segment_type_def, date_month,
         id_product, plan_name, amount_usd_mrr, event_product, event_logo,
         CASE app_version
           WHEN 'colombia'  THEN amount_mrr
           WHEN 'mexico'    THEN amount_mrr
           WHEN 'argentina' THEN amount_mrr
           WHEN 'peru'      THEN amount_mrr
           WHEN 'spain'     THEN amount_mrr
           ELSE COALESCE(amount_usd_real_mrr, amount_usd_mrr)
         END AS amount_conv
  FROM dwh_facts.fact_customers_mrr
  WHERE date_month <= '{cutoff}-01'
    AND segment_type_def IN ('Core', 'Lite')
    AND event_product NOT IN ('AWAITING PAYMENT', 'CHURN')
    AND amount_usd_mrr > 0
    AND plan_name IS NOT NULL
    AND plan_name <> ''
),
flm AS (
  SELECT id_company, app_version, MIN(date_month) AS logo_first_month
  FROM mrr_base GROUP BY 1,2
),
fpm AS (
  SELECT id_company, app_version, id_product, MIN(date_month) AS prod_first_month
  FROM mrr_base GROUP BY 1,2,3
),
t0_products AS (
  SELECT DISTINCT m.id_company, m.app_version, m.id_product,
    CASE m.id_product WHEN 1 THEN 1 WHEN 4 THEN 2 WHEN 2 THEN 3
                      WHEN 3 THEN 4 WHEN 11 THEN 5 ELSE 99 END AS rk
  FROM mrr_base m
  JOIN flm ON m.id_company=flm.id_company AND m.app_version=flm.app_version
          AND m.date_month=flm.logo_first_month
),
base_product_per_logo AS (
  SELECT id_company, app_version, id_product AS base_id_product
  FROM (
    SELECT id_company, app_version, id_product,
           ROW_NUMBER() OVER (PARTITION BY id_company, app_version ORDER BY rk, id_product) AS rn
    FROM t0_products
  ) WHERE rn=1
),
mrr_eop AS (
  SELECT date_month, app_version, segment_type_def,
         SUM(amount_conv)      AS mrr_usd_eop,
         SUM(amount_conv)      AS mrr_usd_eop_cc
  FROM mrr_base GROUP BY 1,2,3
),
logo_metrics AS (
  SELECT date_month, app_version, segment_type_def,
         COUNT(DISTINCT id_company)                                             AS logos_eop,
         COUNT(DISTINCT CASE WHEN event_logo='NEW'         THEN id_company END) AS logos_new,
         COUNT(DISTINCT CASE WHEN event_logo='RECOVERED'   THEN id_company END) AS logos_recov,
         COUNT(DISTINCT CASE WHEN event_logo='REACTIVATED' THEN id_company END) AS logos_react
  FROM mrr_base GROUP BY 1,2,3
),
logo_churn AS (
  SELECT date_month, app_version, segment_type_def,
         COUNT(DISTINCT id_company) AS logos_churn
  FROM dwh_facts.fact_customers_mrr
  WHERE date_month <= '{cutoff}-01'
    AND segment_type_def IN ('Core', 'Lite')
    AND event_logo = 'CHURN'
  GROUP BY 1,2,3
),
logo_inflows AS (
  SELECT m.date_month, m.app_version, m.segment_type_def,
    SUM(CASE WHEN m.event_logo='NEW'
              AND (bpl.base_id_product IS NULL OR m.id_product <> bpl.base_id_product)
             THEN m.amount_conv ELSE 0 END)                       AS mrr_usd_new_cross_t0,
    SUM(CASE WHEN m.event_logo='NEW'
              AND bpl.base_id_product IS NOT NULL
              AND m.id_product = bpl.base_id_product
             THEN m.amount_conv ELSE 0 END)                       AS mrr_usd_new_base_t0,
    SUM(CASE WHEN m.event_logo='RECOVERED'   THEN m.amount_conv ELSE 0 END) AS mrr_usd_recov,
    SUM(CASE WHEN m.event_logo='REACTIVATED' THEN m.amount_conv ELSE 0 END) AS mrr_usd_react
  FROM mrr_base m
  LEFT JOIN base_product_per_logo bpl
    ON m.id_company=bpl.id_company AND m.app_version=bpl.app_version
  WHERE m.event_logo IN ('NEW','RECOVERED','REACTIVATED')
  GROUP BY 1,2,3
),
churn_outflows AS (
  SELECT cur.date_month, cur.app_version, cur.segment_type_def,
         SUM(prev.amount_conv) AS mrr_usd_churn
  FROM dwh_facts.fact_customers_mrr cur
  JOIN mrr_base prev
    ON cur.id_company=prev.id_company AND cur.app_version=prev.app_version
   AND cur.id_product=prev.id_product
   AND prev.date_month=DATEADD('month',-1,cur.date_month)
  WHERE cur.date_month <= '{cutoff}-01'
    AND cur.segment_type_def IN ('Core','Lite')
    AND cur.event_logo = 'CHURN'
  GROUP BY 1,2,3
),
companies_in_both AS (
  SELECT DISTINCT cur.id_company, cur.app_version, cur.date_month
  FROM mrr_base cur
  JOIN mrr_base prev
    ON cur.id_company=prev.id_company AND cur.app_version=prev.app_version
   AND prev.date_month=DATEADD('month',-1,cur.date_month)
),
products_added AS (
  SELECT cpe.date_month, cpe.app_version, cpe.segment_type_def, cpe.amount_conv,
         CASE WHEN fpm.prod_first_month=cpe.date_month THEN 1 ELSE 0 END AS is_first_adoption
  FROM mrr_base cpe
  JOIN companies_in_both cib
    ON cib.id_company=cpe.id_company AND cib.app_version=cpe.app_version
   AND cib.date_month=cpe.date_month
  LEFT JOIN mrr_base cpb
    ON cpb.id_company=cpe.id_company AND cpb.app_version=cpe.app_version
   AND cpb.id_product=cpe.id_product
   AND cpb.date_month=DATEADD('month',-1,cpe.date_month)
  JOIN fpm
    ON fpm.id_company=cpe.id_company AND fpm.app_version=cpe.app_version
   AND fpm.id_product=cpe.id_product
  WHERE cpb.id_company IS NULL
),
products_removed AS (
  SELECT DATEADD('month',1,cpb.date_month) AS date_month,
         cpb.app_version, cpb.segment_type_def, cpb.amount_conv
  FROM mrr_base cpb
  JOIN companies_in_both cib
    ON cib.id_company=cpb.id_company AND cib.app_version=cpb.app_version
   AND cib.date_month=DATEADD('month',1,cpb.date_month)
  LEFT JOIN mrr_base cpe
    ON cpe.id_company=cpb.id_company AND cpe.app_version=cpb.app_version
   AND cpe.id_product=cpb.id_product
   AND cpe.date_month=DATEADD('month',1,cpb.date_month)
  WHERE cpe.id_company IS NULL
),
cross_agg AS (
  SELECT date_month, app_version, segment_type_def,
    SUM(CASE WHEN is_first_adoption=1 THEN amount_conv ELSE 0 END) AS mrr_usd_cross_new_t1plus,
    SUM(CASE WHEN is_first_adoption=0 THEN amount_conv ELSE 0 END) AS mrr_usd_cross_readop,
    0::numeric AS mrr_usd_cross_down
  FROM products_added GROUP BY 1,2,3
  UNION ALL
  SELECT date_month, app_version, segment_type_def, 0, 0, SUM(amount_conv)
  FROM products_removed GROUP BY 1,2,3
),
cross_final AS (
  SELECT date_month, app_version, segment_type_def,
         SUM(mrr_usd_cross_new_t1plus) AS mrr_usd_cross_new_t1plus,
         SUM(mrr_usd_cross_readop)     AS mrr_usd_cross_readop,
         SUM(mrr_usd_cross_down)       AS mrr_usd_cross_down
  FROM cross_agg GROUP BY 1,2,3
),
plan_agg AS (
  SELECT cur.date_month, cur.app_version, cur.segment_type_def,
    SUM(CASE WHEN prev.plan_name <> cur.plan_name AND (cur.amount_conv-prev.amount_conv) > 0
             THEN cur.amount_conv-prev.amount_conv ELSE 0 END) AS mrr_usd_upsell,
    SUM(CASE WHEN prev.plan_name <> cur.plan_name AND (cur.amount_conv-prev.amount_conv) < 0
             THEN cur.amount_conv-prev.amount_conv ELSE 0 END) AS mrr_usd_downsell,
    SUM(CASE WHEN prev.plan_name  = cur.plan_name AND (cur.amount_conv-prev.amount_conv) <> 0
             THEN cur.amount_conv-prev.amount_conv ELSE 0 END) AS mrr_usd_pricing_others
  FROM mrr_base cur
  JOIN mrr_base prev
    ON prev.id_company=cur.id_company AND prev.app_version=cur.app_version
   AND prev.id_product=cur.id_product
   AND prev.date_month=DATEADD('month',-1,cur.date_month)
  GROUP BY 1,2,3
)
SELECT
  e.date_month,
  e.segment_type_def                            AS segment,
  e.app_version,
  COALESCE(lm.logos_eop,0)                      AS logos_eop,
  COALESCE(lm.logos_new,0)                      AS logos_new,
  COALESCE(lm.logos_recov,0)                    AS logos_recov,
  COALESCE(lm.logos_react,0)                    AS logos_react,
  COALESCE(lc.logos_churn,0)                    AS logos_churn,
  e.mrr_usd_eop                                 AS mrr_usd_eop,
  e.mrr_usd_eop_cc                              AS mrr_usd_eop_cc,
  COALESCE(li.mrr_usd_new_base_t0,0)            AS mrr_usd_new_base_t0,
  COALESCE(li.mrr_usd_new_cross_t0,0)           AS mrr_usd_new_cross_t0,
  COALESCE(li.mrr_usd_recov,0)                  AS mrr_usd_recov,
  COALESCE(li.mrr_usd_react,0)                  AS mrr_usd_react,
  COALESCE(co.mrr_usd_churn,0)                  AS mrr_usd_churn,
  COALESCE(pa.mrr_usd_upsell,0)                 AS mrr_usd_upsell,
  COALESCE(pa.mrr_usd_downsell,0)               AS mrr_usd_downsell,
  COALESCE(pa.mrr_usd_pricing_others,0)         AS mrr_usd_pricing_others,
  COALESCE(cf.mrr_usd_cross_new_t1plus,0)       AS mrr_usd_cross_new_t1plus,
  COALESCE(cf.mrr_usd_cross_readop,0)           AS mrr_usd_cross_readop,
  COALESCE(cf.mrr_usd_cross_down,0)             AS mrr_usd_cross_down
FROM mrr_eop e
LEFT JOIN logo_metrics   lm USING (date_month, app_version, segment_type_def)
LEFT JOIN logo_churn     lc USING (date_month, app_version, segment_type_def)
LEFT JOIN logo_inflows   li USING (date_month, app_version, segment_type_def)
LEFT JOIN churn_outflows co USING (date_month, app_version, segment_type_def)
LEFT JOIN plan_agg       pa USING (date_month, app_version, segment_type_def)
LEFT JOIN cross_final    cf USING (date_month, app_version, segment_type_def)
ORDER BY date_month, segment_type_def, app_version
"""

# Logos consolidados (COUNT DISTINCT cross-segmento — evita doble conteo)
_SQL_LOGOS_ALL = """
SELECT date_month,
       COUNT(DISTINCT CASE WHEN event_logo NOT IN ('CHURN','AWAITING PAYMENT') THEN id_company END) AS logos_eop,
       COUNT(DISTINCT CASE WHEN event_logo = 'NEW'         THEN id_company END)                     AS logos_new,
       COUNT(DISTINCT CASE WHEN event_logo = 'RECOVERED'   THEN id_company END)                     AS logos_recov,
       COUNT(DISTINCT CASE WHEN event_logo = 'REACTIVATED' THEN id_company END)                     AS logos_react
FROM dwh_facts.fact_customers_mrr
WHERE date_month <= '{cutoff}-01'
  AND segment_type_def IN ('Core', 'Lite')
  AND amount_usd_mrr > 0
  AND plan_name IS NOT NULL AND plan_name <> ''
GROUP BY date_month
ORDER BY date_month
"""


_SQL_FUNNEL_SIGNUPS = """
SELECT
    DATE_TRUNC('month', sign_up_cohort)::DATE AS mes,
    app_version,
    COUNT(DISTINCT id_company) AS signups
FROM bi_sales.sales_actions
WHERE gestion = 'Leads contactables'
  AND sign_up_cohort >= DATEADD(month, -13, DATE_TRUNC('month', '{cutoff}-01'::DATE))
  AND sign_up_cohort <  DATEADD(month,   1, DATE_TRUNC('month', '{cutoff}-01'::DATE))
  AND app_version IN ('colombia','mexico','republicaDominicana','costaRica')
GROUP BY 1, 2
ORDER BY 1, 2
"""

_SQL_FUNNEL_LOGOS = """
SELECT
    DATE_TRUNC('month', close_date)::DATE AS mes,
    app_version,
    COUNT(DISTINCT id_company) AS new_logos
FROM bi_sales.fact_closed_deals
WHERE cross_selling = 'New Logo'
  AND close_date >= DATEADD(month, -13, DATE_TRUNC('month', '{cutoff}-01'::DATE))
  AND close_date <  DATEADD(month,   1, DATE_TRUNC('month', '{cutoff}-01'::DATE))
  AND app_version IN ('colombia','mexico','republicaDominicana','costaRica')
GROUP BY 1, 2
ORDER BY 1, 2
"""

_SQL_PRODUCT_PERF = """
WITH base AS (
    SELECT date_month, product_name, id_company, event_logo, amount_usd_mrr, segment_type_def AS segment
    FROM dwh_facts.fact_customers_mrr
    WHERE date_month >= DATEADD(month, -7, DATE_TRUNC('month', '{cutoff}-01'::DATE))
      AND date_month <= DATE_TRUNC('month', '{cutoff}-01'::DATE)
      AND product_name IN ('Alegra Contabilidad','Alegra POS','Alegra Nómina','Alegra Facturación')
      AND segment_type_def IN ('Core','Lite')
),
monthly AS (
    SELECT
        date_month, product_name,
        COUNT(DISTINCT CASE WHEN event_logo NOT IN ('CHURN','AWAITING PAYMENT') THEN id_company END) AS eop_subs,
        COUNT(DISTINCT CASE WHEN event_logo = 'CHURN'       THEN id_company END) AS churn_logos,
        COUNT(DISTINCT CASE WHEN event_logo = 'REACTIVATED' THEN id_company END) AS react_logos,
        COUNT(DISTINCT CASE WHEN event_logo = 'NEW'         THEN id_company END) AS new_logos,
        SUM(CASE WHEN event_logo = 'NEW' THEN amount_usd_mrr ELSE 0 END)         AS new_mrr,
        COUNT(DISTINCT CASE WHEN event_logo NOT IN ('CHURN','AWAITING PAYMENT')
                             AND segment = 'Core' THEN id_company END)           AS core_subs
    FROM base
    GROUP BY 1, 2
),
with_lag AS (
    SELECT *, LAG(eop_subs) OVER (PARTITION BY product_name ORDER BY date_month) AS bop_subs
    FROM monthly
)
SELECT date_month, product_name, eop_subs, bop_subs, churn_logos, react_logos, new_logos, new_mrr, core_subs
FROM with_lag
WHERE date_month >= DATEADD(month, -6, DATE_TRUNC('month', '{cutoff}-01'::DATE))
ORDER BY product_name, date_month
"""

_SQL_INVESTMENT = """
SELECT cohortmonth, app_version, segment_type,
       SUM(general_expenses_usd + paid_media_expenses_usd + publicidad_no_web_expenses_usd
           + software_and_tools_expenses_usd + team_expenses_usd + freelance_expenses_usd
           + payroll_expenses_usd + travel_expenses_usd) AS total_investment_usd,
       SUM(paid_media_expenses_usd + publicidad_no_web_expenses_usd) AS paid_media_usd,
       SUM(payroll_expenses_usd + team_expenses_usd + freelance_expenses_usd) AS people_usd,
       SUM(general_expenses_usd + software_and_tools_expenses_usd + travel_expenses_usd) AS other_usd
FROM db_finance.fact_cac_version_segments
WHERE cohortmonth <= '{cutoff}-01'
  AND cohortmonth >= DATEADD(month, -12, '{cutoff}-01')
  AND segment_type IN ('Core', 'Lite')
GROUP BY cohortmonth, app_version, segment_type
ORDER BY cohortmonth
"""

_SQL_FLYWHEEL = """
WITH base_monthly_data AS (
    SELECT mrr.date_month,
           e.hs_accounting_entity_id AS entity_id,
           mrr.id_company AS logo_id,
           SUM(mrr.amount_usd_mrr) AS amount_usd_mrr
    FROM dwh_facts.fact_customers_mrr mrr
    INNER JOIN data_table_bi.db_hubspot.companies_relation_ids r
        ON mrr.id_company = r.company_id
    INNER JOIN db_hubspot.associations_accounting_entities_to_companies e
        ON r.hubspot_company_id = e.hs_company_id
    WHERE mrr.amount_usd_mrr > 0
      AND mrr.date_month < DATE_TRUNC('month', CURRENT_DATE)
      AND e.hs_accounting_entity_id IS NOT NULL
    GROUP BY mrr.date_month, e.hs_accounting_entity_id, mrr.id_company
),
logos_history AS (
    SELECT date_month, logo_id,
           DATEDIFF(month, LAG(date_month) OVER (PARTITION BY logo_id ORDER BY date_month), date_month) AS months_gap,
           ROW_NUMBER() OVER (PARTITION BY logo_id ORDER BY date_month) AS appearance_num
    FROM base_monthly_data
    GROUP BY date_month, logo_id
),
logos_events AS (
    SELECT date_month, logo_id,
           CASE WHEN appearance_num = 1 THEN 'NEW'
                WHEN months_gap = 2 THEN 'REACTIVATED'
                WHEN months_gap > 2 THEN 'RECOVERED'
                WHEN months_gap = 1 THEN 'RETAINED' END AS event_type
    FROM logos_history
),
logos_churned AS (
    SELECT DATEADD(month, 1, lh.date_month) AS churn_month, lh.logo_id
    FROM logos_history lh
    WHERE NOT EXISTS (
        SELECT 1 FROM logos_history lh2
        WHERE lh2.logo_id = lh.logo_id
          AND lh2.date_month = DATEADD(month, 1, lh.date_month)
    )
    AND DATEADD(month, 1, lh.date_month) < DATE_TRUNC('month', CURRENT_DATE)
),
logos_metrics AS (
    SELECT date_month,
           COUNT(DISTINCT logo_id) AS stock_logos,
           COUNT(DISTINCT CASE WHEN event_type='NEW' THEN logo_id END) AS new_logos,
           COUNT(DISTINCT CASE WHEN event_type='REACTIVATED' THEN logo_id END) AS reactivated_logos,
           COUNT(DISTINCT CASE WHEN event_type='RECOVERED' THEN logo_id END) AS recovered_logos
    FROM logos_events GROUP BY date_month
),
logos_churn_metrics AS (
    SELECT churn_month AS date_month, COUNT(DISTINCT logo_id) AS churned_logos
    FROM logos_churned GROUP BY churn_month
),
entity_monthly_mrr AS (
    SELECT date_month, entity_id, SUM(amount_usd_mrr) AS total_mrr
    FROM base_monthly_data GROUP BY date_month, entity_id
),
entity_history AS (
    SELECT date_month, entity_id,
           DATEDIFF(month, LAG(date_month) OVER (PARTITION BY entity_id ORDER BY date_month), date_month) AS months_gap,
           ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY date_month) AS appearance_num
    FROM entity_monthly_mrr
    WHERE total_mrr > 0
),
entity_events AS (
    SELECT date_month, entity_id,
           CASE WHEN appearance_num = 1 THEN 'NEW'
                WHEN months_gap = 2 THEN 'REACTIVATED'
                WHEN months_gap > 2 THEN 'RECOVERED'
                WHEN months_gap = 1 THEN 'RETAINED' END AS event_type
    FROM entity_history
),
entity_churned AS (
    SELECT DATEADD(month, 1, eh.date_month) AS churn_month, eh.entity_id
    FROM entity_history eh
    WHERE NOT EXISTS (
        SELECT 1 FROM entity_history eh2
        WHERE eh2.entity_id = eh.entity_id
          AND eh2.date_month = DATEADD(month, 1, eh.date_month)
    )
    AND DATEADD(month, 1, eh.date_month) < DATE_TRUNC('month', CURRENT_DATE)
),
entity_metrics AS (
    SELECT date_month,
           COUNT(DISTINCT entity_id) AS stock_entities,
           COUNT(DISTINCT CASE WHEN event_type='NEW' THEN entity_id END) AS new_entities,
           COUNT(DISTINCT CASE WHEN event_type='REACTIVATED' THEN entity_id END) AS reactivated_entities,
           COUNT(DISTINCT CASE WHEN event_type='RECOVERED' THEN entity_id END) AS recovered_entities
    FROM entity_events GROUP BY date_month
),
entity_churn_metrics AS (
    SELECT churn_month AS date_month, COUNT(DISTINCT entity_id) AS churned_entities
    FROM entity_churned GROUP BY churn_month
)
SELECT TO_CHAR(COALESCE(lm.date_month, em.date_month), 'YYYY-MM-DD') AS month,
       COALESCE(em.new_entities,0) + COALESCE(em.recovered_entities,0)        AS ent_new_adds,
       COALESCE(ecm.churned_entities,0) - COALESCE(em.reactivated_entities,0) AS ent_net_churn,
       COALESCE(em.stock_entities,0)                                           AS ent_stock,
       COALESCE(lm.new_logos,0) + COALESCE(lm.recovered_logos,0)              AS lg_new_adds,
       COALESCE(lcm.churned_logos,0) - COALESCE(lm.reactivated_logos,0)       AS lg_net_churn,
       COALESCE(lm.stock_logos,0)                                              AS lg_stock
FROM logos_metrics lm
FULL OUTER JOIN logos_churn_metrics  lcm ON lm.date_month = lcm.date_month
FULL OUTER JOIN entity_metrics       em  ON COALESCE(lm.date_month, lcm.date_month) = em.date_month
FULL OUTER JOIN entity_churn_metrics ecm ON COALESCE(lm.date_month, lcm.date_month, em.date_month) = ecm.date_month
WHERE COALESCE(lm.date_month, lcm.date_month, em.date_month) >= '2024-01-01'
  AND COALESCE(lm.date_month, lcm.date_month, em.date_month) <  DATE_TRUNC('month', CURRENT_DATE)
ORDER BY month
"""


_SQL_SC_HIST = """
SELECT TO_CHAR(date_month, 'YYYY-MM') AS m,
       COUNT(DISTINCT CASE WHEN user_profile='client_of_accountant' AND logo_flywheel_event!='CHURNED' THEN id_company END) AS clientes,
       COUNT(DISTINCT CASE WHEN user_profile='accountant'           AND logo_flywheel_event!='CHURNED' THEN id_company END) AS propia
FROM bi_accountant.accountant_master_table
WHERE date_month < DATE_TRUNC('month', CURRENT_DATE)
GROUP BY date_month
ORDER BY date_month
"""

# Resuelta 2026-07-14: ev_monthly ya NO agrega la cruda db_amplitude_events.amplitude_ac_events
# (nunca copiada a Metabase, por eso esta query estuvo bloqueada) — en su lugar lee directo
# de bi_accountant.value_events_monthly, una tabla derivada más simple (grano
# id_company×event_name×mes, con is_attr ya resuelto) que el usuario creó y puebla el
# usuario mismo en Redshift (ver memory/project_board_agent.md, sección "_SQL_VALUE_EVENTS").
# `active` no cambió. Validada contra Redshift real para mayo-2026 (ventana single-month
# marzo-mayo): nl/no_/nx/nge3 exactos; total/nf/nj/nw/nk/nge1/nge2 con diff de ~0.1%, misma
# causa raíz ya documentada del desfase de sync de accountant_master_table — no un bug.
_SQL_VALUE_EVENTS = """
WITH
active AS (
    SELECT date_month, id_company
    FROM bi_accountant.accountant_master_table
    WHERE date_month >= DATEADD(month, -13, DATE_TRUNC('month', CURRENT_DATE))
      AND date_month < DATE_TRUNC('month', CURRENT_DATE)
      AND user_profile = 'client_of_accountant'
      AND logo_flywheel_event != 'CHURNED'
),
ev_monthly AS (
    SELECT id_company, event_name, is_attr,
           date_month AS event_month
    FROM bi_accountant.value_events_monthly
    WHERE date_month >= DATEADD(month, -16, DATE_TRUNC('month', CURRENT_DATE))
      AND date_month <  DATE_TRUNC('month', CURRENT_DATE)
),
ev_in_window AS (
    SELECT a.date_month, a.id_company, em.event_name, em.is_attr
    FROM active a
    JOIN ev_monthly em ON a.id_company = em.id_company
    WHERE em.event_month <= a.date_month
      AND em.event_month >= DATEADD(month, -2, a.date_month)
),
per_company AS (
    SELECT a.date_month, a.id_company,
           MAX(CASE WHEN e.event_name='ac-invoice-submitted'              THEN 1 ELSE 0 END) AS f_,
           MAX(CASE WHEN e.event_name='ac-journal-created'                THEN 1 ELSE 0 END) AS j_,
           MAX(CASE WHEN e.event_name='ac-ledger-category-import-started' THEN 1 ELSE 0 END) AS l_,
           MAX(CASE WHEN e.event_name='ac-opening-balance-created'        THEN 1 ELSE 0 END) AS o_,
           MAX(CASE WHEN e.event_name='ac-administrator-xml-imported-solicited' THEN 1 ELSE 0 END) AS x_,
           MAX(CASE WHEN e.is_attr = 1                                    THEN 1 ELSE 0 END) AS w_,
           MAX(CASE WHEN e.event_name='ac-journal-created' AND e.is_attr=1 THEN 1 ELSE 0 END) AS k_
    FROM active a
    LEFT JOIN ev_in_window e ON a.date_month = e.date_month AND a.id_company = e.id_company
    GROUP BY a.date_month, a.id_company
),
summary AS (
    SELECT date_month, COUNT(*) AS total,
           SUM(f_) AS nf, SUM(j_) AS nj, SUM(l_) AS nl,
           SUM(o_) AS no_, SUM(x_) AS nx,
           SUM(w_) AS nw, SUM(k_) AS nk,
           SUM(LEAST(f_+j_+l_+o_+x_, 1))                         AS nge1,
           SUM(CASE WHEN f_+j_+l_+o_+x_ >= 2 THEN 1 ELSE 0 END)  AS nge2,
           SUM(CASE WHEN f_+j_+l_+o_+x_ >= 3 THEN 1 ELSE 0 END)  AS nge3
    FROM per_company
    GROUP BY date_month
)
SELECT TO_CHAR(date_month, 'YYYY-MM') AS m, total,
       nf, nj, nl, no_, nx, nw, nk, nge1, nge2, nge3,
       ROUND(100.0*nf/NULLIF(total,0),    1) AS pct_factura,
       ROUND(100.0*nj/NULLIF(total,0),    1) AS pct_asiento,
       ROUND(100.0*nl/NULLIF(total,0),    1) AS pct_catalogo,
       ROUND(100.0*no_/NULLIF(total,0),   1) AS pct_saldos,
       ROUND(100.0*nx/NULLIF(total,0),    1) AS pct_adminxml,
       ROUND(100.0*nw/NULLIF(total,0),    1) AS pct_trabaja,
       ROUND(100.0*nk/NULLIF(total,0),    1) AS pct_contabiliza,
       ROUND(100.0*nge1/NULLIF(total,0),  1) AS pct_ge1,
       ROUND(100.0*nge2/NULLIF(total,0),  1) AS pct_ge2,
       ROUND(100.0*nge3/NULLIF(total,0),  1) AS pct_ge3
FROM summary
ORDER BY date_month
"""

_SQL_SOW_TOP20 = """
WITH latest_month AS (
    SELECT MAX(date_month) AS m
    FROM bi_accountant.accountant_master_table
    WHERE date_month < DATE_TRUNC('month', CURRENT_DATE)
),
cur_ranked AS (
    SELECT a.hs_accounting_entity_id, a.entity_name, a.entity_country_version,
           a.entity_hs_pipeline_stage,
           COUNT(DISTINCT CASE WHEN a.user_profile='client_of_accountant' AND a.logo_flywheel_event!='CHURNED' THEN a.id_company END) AS real_logos,
           SUM(CASE WHEN a.user_profile='client_of_accountant' AND a.logo_flywheel_event!='CHURNED' THEN a.amount_usd_mrr ELSE 0 END) AS mrr
    FROM bi_accountant.accountant_master_table a
    CROSS JOIN latest_month lm WHERE a.date_month = lm.m
    GROUP BY a.hs_accounting_entity_id, a.entity_name, a.entity_country_version, a.entity_hs_pipeline_stage
),
top20 AS (
    SELECT *, ROW_NUMBER() OVER (ORDER BY mrr DESC NULLS LAST) AS rn FROM cur_ranked
),
asoc AS (
    SELECT hs.hs_accounting_entity_id::varchar AS hs_id,
           COUNT(DISTINCT hs.hs_company_id) AS asoc_logos
    FROM db_hubspot.associations_accounting_entities_to_companies hs
    WHERE hs.hs_accounting_entity_id::varchar IN (SELECT hs_accounting_entity_id FROM top20 WHERE rn <= 20)
    GROUP BY hs.hs_accounting_entity_id
),
hist AS (
    SELECT a.hs_accounting_entity_id, a.date_month,
           COUNT(DISTINCT CASE WHEN a.user_profile='client_of_accountant' AND a.logo_flywheel_event!='CHURNED' THEN a.id_company END) AS real_logos
    FROM bi_accountant.accountant_master_table a
    CROSS JOIN latest_month lm
    WHERE a.hs_accounting_entity_id IN (SELECT hs_accounting_entity_id FROM top20 WHERE rn <= 20)
      AND (a.date_month = DATEADD(month, -1, lm.m) OR a.date_month = DATEADD(month, -12, lm.m))
    GROUP BY a.hs_accounting_entity_id, a.date_month
)
SELECT t.rn AS rank, t.entity_name AS contador, t.entity_country_version AS pais,
       ROUND(t.mrr, 2) AS mrr,
       t.real_logos AS real,
       COALESCE(a.asoc_logos, t.real_logos) AS asoc,
       t.entity_hs_pipeline_stage AS nivel,
       MAX(CASE WHEN h.date_month = DATEADD(month, -1, lm.m)  THEN h.real_logos END) AS real_mom,
       MAX(CASE WHEN h.date_month = DATEADD(month, -12, lm.m) THEN h.real_logos END) AS real_yoy
FROM top20 t
CROSS JOIN latest_month lm
LEFT JOIN asoc a ON t.hs_accounting_entity_id = a.hs_id
LEFT JOIN hist h ON t.hs_accounting_entity_id = h.hs_accounting_entity_id
WHERE t.rn <= 20
GROUP BY t.rn, t.entity_name, t.entity_country_version, t.mrr, t.real_logos, a.asoc_logos, t.entity_hs_pipeline_stage, lm.m
ORDER BY t.rn
"""

_SQL_RETENTION_CHURN = """
WITH events AS (
    SELECT
        date_month,
        version       AS app_version,
        segment,
        COUNT(DISTINCT CASE WHEN logo_event = 'CHURNED'     THEN id_company END) AS logos_churned,
        COUNT(DISTINCT CASE WHEN logo_event = 'REACTIVATED' THEN id_company END) AS logos_reactivated
    FROM dm_retention.bi_customer_monthly_status
    WHERE date_month >= DATEADD(month, -14, DATE_TRUNC('month', CURRENT_DATE))
    GROUP BY 1, 2, 3
),
bop AS (
    SELECT
        DATEADD(month, 1, date_month) AS date_month,
        version       AS app_version,
        segment,
        COUNT(DISTINCT CASE WHEN is_paying = true THEN id_company END) AS logos_bop
    FROM dm_retention.bi_customer_monthly_status
    WHERE date_month >= DATEADD(month, -15, DATE_TRUNC('month', CURRENT_DATE))
    GROUP BY 1, 2, 3
)
SELECT e.date_month, e.app_version, e.segment,
       COALESCE(b.logos_bop, 0) AS logos_bop,
       e.logos_churned, e.logos_reactivated
FROM events e
LEFT JOIN bop b ON e.date_month = b.date_month
               AND e.app_version = b.app_version
               AND e.segment = b.segment
ORDER BY e.date_month, e.app_version, e.segment
"""


# ── Fetch helpers ────────────────────────────────────────────────────────────────
# Migración 2026-07-10: este script ya no habla con Redshift. _run/_run1 no ejecutan
# nada — el `sql` que reciben es sólo documentación de qué query MBQL corre en su
# lugar (ver board_agent/metabase_fetch_spec.py). El `label` es la clave con la que
# Claude Code (único cliente autorizado del MCP de Metabase — RS quedó reservado
# para uso interno del equipo de datos, no para agentes/skills compartidos) ya
# debió haber escrito las filas resultantes en METABASE_CACHE_FILE antes de correr
# este script. _pages() simplemente busca esa clave en el cache.
def _run(sql, label):
    return label

def _run1(sql, label):
    return label

def _load_metabase_cache():
    if not METABASE_CACHE_FILE.exists():
        raise RuntimeError(
            f"No existe {METABASE_CACHE_FILE}. Antes de correr fetch_metrics.py, Claude Code debe "
            "ejecutar las queries MBQL vía el MCP de Metabase (mcp__metabase__*) y escribir sus "
            "resultados ahí — ver board_agent/metabase_fetch_spec.py."
        )
    return json.loads(METABASE_CACHE_FILE.read_text(encoding="utf-8"))

def _pages(label):
    cache = _load_metabase_cache()
    queries = cache.get("queries", {})
    if label not in queries:
        raise RuntimeError(
            f"Falta '{label}' en el bloque 'queries' de {METABASE_CACHE_FILE.name} — corré la query "
            "MBQL correspondiente vía el MCP de Metabase y agregala al cache antes de continuar."
        )
    return queries[label]

# Criterio unificado 2026-07-14: toda query faltante debe terminar en un FAIL visible del
# pipeline, nunca en un warning silencioso (el board sigue con datos en $0/blanco sin que
# nadie se entere) ni en un crash crudo del primer _pages() que falle (antes 11 de ~20
# queries directas de load_data() no tenían try/except y tumbaban todo con un traceback en
# vez de listar qué faltaba). _pages_or_missing() reemplaza el patrón "try/except: print
# warning, degradar en silencio" que estaba duplicado ~9 veces: sigue degradando al
# `fallback` para que el resto del script pueda seguir corriendo y juntar TODAS las
# queries faltantes en una sola pasada, pero las registra en _MISSING_QUERIES — load_data()
# revisa esa lista al final y tira UN solo RuntimeError con todo lo que falta, en vez de
# que cada función decida por su cuenta si avisa o no.
_MISSING_QUERIES = []

def _pages_or_missing(label, fallback, warning):
    try:
        return _pages(label)
    except Exception as e:
        print(f"  ⚠️  {warning} ({e})")
        _MISSING_QUERIES.append(label)
        return fallback

def _parse_retention_churn(rows):
    """Parsea filas de _SQL_RETENTION_CHURN (dm_retention.bi_customer_monthly_status, cluster-1).
    Retorna tres dicts:
      by_seg        → {month: {segment: {bop, churned, reactivated}}}  ('all' = suma global)
      by_country    → {month: {app_version: {bop, churned, reactivated}}}  (suma todos segmentos)
      by_seg_country → {month: {app_version: {segment: {bop, churned, reactivated}}}}
    """
    by_seg         = {}
    by_country     = {}
    by_seg_country = {}

    for r in rows:
        m   = str(r["date_month"])[:7]
        seg = str(r.get("segment")     or "").strip() or "Unknown"
        app = str(r.get("app_version") or "").strip() or "other"
        d   = {
            "bop":         int(r.get("logos_bop")         or 0),
            "churned":     int(r.get("logos_churned")     or 0),
            "reactivated": int(r.get("logos_reactivated") or 0),
        }
        # Por segmento global
        by_seg.setdefault(m, {}).setdefault(seg, {"bop": 0, "churned": 0, "reactivated": 0})
        for k in d: by_seg[m][seg][k] += d[k]
        # Por país (suma de segmentos)
        by_country.setdefault(m, {}).setdefault(app, {"bop": 0, "churned": 0, "reactivated": 0})
        for k in d: by_country[m][app][k] += d[k]
        # Por país + segmento
        by_seg_country.setdefault(m, {}).setdefault(app, {}).setdefault(seg, {"bop": 0, "churned": 0, "reactivated": 0})
        for k in d: by_seg_country[m][app][seg][k] += d[k]

    # "all" global = suma de todos los segmentos del mes
    for m, segs in by_seg.items():
        by_seg[m]["all"] = {
            "bop":         sum(s["bop"]         for s in segs.values()),
            "churned":     sum(s["churned"]     for s in segs.values()),
            "reactivated": sum(s["reactivated"] for s in segs.values()),
        }

    return {"by_seg": by_seg, "by_country": by_country, "by_seg_country": by_seg_country}

def _check_metabase_cache_month(cutoff):
    cache = _load_metabase_cache()
    if cache.get("month") != cutoff:
        raise RuntimeError(
            f"{METABASE_CACHE_FILE.name} es para el mes '{cache.get('month')}', se pidió '{cutoff}' — "
            "Claude Code debe refrescar el cache (queries + freshness) para este mes antes de continuar."
        )

def load_data(cutoff, refresh=False):
    # Bug real corregido 2026-07-14: CACHE_FILE (.cache_metrics.json) era un atajo de
    # rendimiento de la era Redshift (evitar re-consultar RS). Ahora que la fuente es un
    # JSON local ya barato de releer, este atajo solo servía para servir en silencio un
    # resultado VIEJO cuando alguien corregía data/.metabase_cache.json para el mismo mes
    # sin pasar --refresh — el bug no era detectable porque (version, cutoff) seguían
    # matcheando aunque el CONTENIDO del cache de Metabase hubiera cambiado. Se eliminó el
    # atajo de lectura: siempre se recalcula desde data/.metabase_cache.json (rápido, es
    # solo un JSON local), y solo se valida que sea del mes pedido.
    _check_metabase_cache_month(cutoff)

    sids = {
        "fact_summary":    _run(_SQL_FACT_SUMMARY.format(cutoff=cutoff),    "fact_customers_mrr (summary)"),
        "logos_all":       _run(_SQL_LOGOS_ALL.format(cutoff=cutoff),       "logos consolidados"),
        "investment":      _run(_SQL_INVESTMENT.format(cutoff=cutoff),      "investment por país"),
        "funnel_signups":  _run(_SQL_FUNNEL_SIGNUPS.format(cutoff=cutoff),  "funnel signups (bi_sales)"),
        "funnel_logos":    _run(_SQL_FUNNEL_LOGOS.format(cutoff=cutoff),    "funnel new logos (bi_sales)"),
        "product_perf":    _run(_SQL_PRODUCT_PERF.format(cutoff=cutoff),    "product performance (6_rd)"),
        "flywheel":        _run(_SQL_FLYWHEEL,                              "flywheel entities+logos"),
        "sc_hist":         _run(_SQL_SC_HIST,                               "SC histórico stock (accountant_master)"),
        "sc_events":       _run(_SQL_VALUE_EVENTS,                          "SC value events mensuales (amplitude)"),
        "sc_sow":          _run(_SQL_SOW_TOP20,                             "SC top-20 SoW"),
        "retention_churn": _run1(_SQL_RETENTION_CHURN,                      "retention churn (dm_retention, cluster-1)"),
    }
    # Criterio unificado 2026-07-14: antes estas 11 llamadas no tenían try/except — la
    # primera query faltante tumbaba fetch_metrics.py entero con un traceback crudo, sin
    # decir cuáles de las otras 10 también faltaban. Ahora cada una degrada a lista vacía
    # (como ya hacían load_fx/load_payback/etc.) y _pages_or_missing() las va acumulando en
    # _MISSING_QUERIES — el chequeo de abajo, después de intentarlas TODAS, es el que
    # decide si falla la corrida completa (con la lista completa de lo que falta), en vez
    # de que cada llamada decida por su cuenta si avisa o no.
    fact_summary_rows  = _pages_or_missing(sids["fact_summary"],    [], "fact_customers_mrr (summary) no disponible")
    logos_rows         = _pages_or_missing(sids["logos_all"],       [], "logos consolidados no disponible")
    investment_rows    = _pages_or_missing(sids["investment"],      [], "investment por país no disponible")
    funnel_signup_rows = _pages_or_missing(sids["funnel_signups"],  [], "funnel signups no disponible")
    funnel_logos_rows  = _pages_or_missing(sids["funnel_logos"],    [], "funnel new logos no disponible")
    product_perf_rows  = _pages_or_missing(sids["product_perf"],    [], "product performance no disponible")
    flywheel_rows      = _pages_or_missing(sids["flywheel"],        [], "flywheel entities+logos no disponible")
    sc_hist_rows        = _pages_or_missing(sids["sc_hist"],        [], "SC histórico stock no disponible")
    sc_events_rows      = _pages_or_missing(sids["sc_events"],      [], "SC value events mensuales no disponible")
    sc_sow_rows         = _pages_or_missing(sids["sc_sow"],         [], "SC top-20 SoW no disponible")
    retention_rows      = _pages_or_missing(sids["retention_churn"],[], "retention churn no disponible")
    # OJO: NO se chequea _MISSING_QUERIES acá — load_fx(), load_payback(), load_headcount_*()
    # y _build_churn_tenure() se llaman más adelante en el pipeline (algunos incluso fuera de
    # load_data(), en build_yaml()/merge_payback() dentro de main()), así que una query que
    # ellos necesiten todavía no tuvo chance de fallar en este punto. El chequeo agregado real
    # está al final de main(), después de que TODO haya tenido su oportunidad de correr.

    # ── Aplicar conversión FX (amount_mrr → USD)
    # Países en paises_fx.csv: mrr_usd_* = mrr_local_* / tasa CSV
    # Resto: mrr_usd_* ya viene de amount_usd_mrr (fallback correcto)
    fx = load_fx()
    for row in fact_summary_rows:
        _apply_fx_to_row(row, fx, cutoff)
    print(f"  💱 FX aplicado — CO/MX/AR/PE/ES: amount_mrr/tasa · resto: amount_usd_mrr directo")

    # ── Aggregate summary by (month, segment) — collapse app_version
    _NUM = ["logos_eop","logos_new","logos_recov","logos_react","logos_churn",
            "mrr_eop","mrr_eop_cc","mrr_new_base_t0","mrr_new_cross_t0","mrr_recov","mrr_react",
            "mrr_churn","mrr_upsell","mrr_downsell","mrr_pricing_others",
            "mrr_cross_new_t1plus","mrr_cross_readop","mrr_cross_down"]
    _COL_MAP = {
        "mrr_usd_eop":              "mrr_eop",
        "mrr_usd_eop_cc":           "mrr_eop_cc",
        "mrr_usd_new_base_t0":      "mrr_new_base_t0",
        "mrr_usd_new_cross_t0":     "mrr_new_cross_t0",
        "mrr_usd_recov":            "mrr_recov",
        "mrr_usd_react":            "mrr_react",
        "mrr_usd_churn":            "mrr_churn",
        "mrr_usd_upsell":           "mrr_upsell",
        "mrr_usd_downsell":         "mrr_downsell",
        "mrr_usd_pricing_others":   "mrr_pricing_others",
        "mrr_usd_cross_new_t1plus": "mrr_cross_new_t1plus",
        "mrr_usd_cross_readop":     "mrr_cross_readop",
        "mrr_usd_cross_down":       "mrr_cross_down",
    }
    grouped = {}
    for r in fact_summary_rows:
        m   = str(r["date_month"])[:7]
        seg = r.get("segment") or "Other"
        key = (m, seg)
        if key not in grouped:
            grouped[key] = {"m": m, "seg": seg, **{k: 0.0 for k in _NUM}}
        for rs_col, py_col in _COL_MAP.items():
            grouped[key][py_col] += float(r.get(rs_col) or 0)
        for col in ["logos_eop","logos_new","logos_recov","logos_react","logos_churn"]:
            grouped[key][col] += float(r.get(col) or 0)

    summary = list(grouped.values())

    # ── Logos consolidated (COUNT DISTINCT cross-segmento — sin doble conteo)
    logos_all = {}
    for r in logos_rows:
        m = str(r["date_month"])[:7]
        logos_all[m] = {
            "logos_eop":   float(r.get("logos_eop")   or 0),
            "logos_new":   float(r.get("logos_new")   or 0),
            "logos_recov": float(r.get("logos_recov") or 0),
            "logos_react": float(r.get("logos_react") or 0),
        }

    # ── Country (month → app_version → segment → metrics) — directo desde fact
    _COUNTRIES = {"colombia", "mexico", "costaRica", "republicaDominicana"}
    country = {}
    for r in fact_summary_rows:
        m   = str(r["date_month"])[:7]
        app = r.get("app_version") or ""
        seg = r.get("segment") or "Other"
        if app not in _COUNTRIES:
            continue
        eop = float(r.get("logos_eop") or 0)
        country.setdefault(m, {}).setdefault(app, {})[seg] = {
            "logos_eop":              eop,
            "logos_new":              float(r.get("logos_new")                  or 0),
            "logos_recov":            float(r.get("logos_recov")                or 0),
            "logos_react":            float(r.get("logos_react")                or 0),
            "logos_churn":            float(r.get("logos_churn")                or 0),
            "mrr_eop":                float(r.get("mrr_usd_eop")                or 0),
            "mrr_new_base_t0":        float(r.get("mrr_usd_new_base_t0")        or 0),
            "mrr_new_cross_t0":       float(r.get("mrr_usd_new_cross_t0")       or 0),
            "mrr_new":                float(r.get("mrr_usd_new_base_t0") or 0) + float(r.get("mrr_usd_new_cross_t0") or 0),
            "mrr_recov":              float(r.get("mrr_usd_recov")              or 0),
            "mrr_react":              float(r.get("mrr_usd_react")              or 0),
            "mrr_churn":              float(r.get("mrr_usd_churn")              or 0),
            "mrr_upsell":             float(r.get("mrr_usd_upsell")             or 0),
            "mrr_downsell":           float(r.get("mrr_usd_downsell")           or 0),
            "mrr_pricing_others":     float(r.get("mrr_usd_pricing_others")     or 0),
            "mrr_cross_new_t1plus":   float(r.get("mrr_usd_cross_new_t1plus")   or 0),
            "mrr_cross_readop":       float(r.get("mrr_usd_cross_readop")       or 0),
            "mrr_cross_down":         float(r.get("mrr_usd_cross_down")         or 0),
        }

    # ── Investment: {country_key: {segment: {month: {total, paid, people, other}}}}
    investment = {}
    for r in investment_rows:
        app = (r.get("app_version") or "").strip()
        seg = (r.get("segment_type") or "").strip()
        m   = str(r.get("cohortmonth") or "")[:7]  # "2026-02"
        investment.setdefault(app, {}).setdefault(seg, {})[m] = {
            "total":  float(r.get("total_investment_usd") or 0),
            "paid":   float(r.get("paid_media_usd") or 0),
            "people": float(r.get("people_usd") or 0),
            "other":  float(r.get("other_usd") or 0),
        }

    # ── Funnel: signups + new logos por mes y país (bi_sales)
    funnel = {}
    for r in funnel_signup_rows:
        m  = str(r.get("mes") or "")[:7]
        ck = (r.get("app_version") or "").strip()
        if m and ck:
            funnel.setdefault(m, {}).setdefault(ck, {})["signups"] = int(r.get("signups") or 0)
    for r in funnel_logos_rows:
        m  = str(r.get("mes") or "")[:7]
        ck = (r.get("app_version") or "").strip()
        if m and ck:
            funnel.setdefault(m, {}).setdefault(ck, {})["logos"] = int(r.get("new_logos") or 0)

    # ── Product Performance (6_rd) ── {product_name → {date_month → {metrics}}}
    product_perf = {}
    for r in product_perf_rows:
        pn = r.get("product_name") or ""
        dm = str(r.get("date_month") or "")[:10]
        if not pn or not dm:
            continue
        product_perf.setdefault(pn, {})[dm] = {
            "eop_subs":   int(r.get("eop_subs")   or 0),
            "bop_subs":   int(r.get("bop_subs")   or 0),
            "churn_logos": int(r.get("churn_logos") or 0),
            "react_logos": int(r.get("react_logos") or 0),
            "new_logos":   int(r.get("new_logos")   or 0),
            "new_mrr":     float(r.get("new_mrr")   or 0),
            "core_subs":   int(r.get("core_subs")   or 0),
        }

    # ── Flywheel: {month_iso: {ent_new_adds, ent_net_churn, ent_stock, lg_new_adds, lg_net_churn, lg_stock}}
    flywheel = {}
    for r in flywheel_rows:
        m = str(r.get("month") or "")[:7]
        if not m:
            continue
        flywheel[m] = {
            "ent_new_adds": int(r.get("ent_new_adds") or 0),
            "ent_net_churn": int(r.get("ent_net_churn") or 0),
            "ent_stock":    int(r.get("ent_stock")    or 0),
            "lg_new_adds":  int(r.get("lg_new_adds")  or 0),
            "lg_net_churn": int(r.get("lg_net_churn") or 0),
            "lg_stock":     int(r.get("lg_stock")     or 0),
        }

    sc = {
        "hist":             sc_hist_rows,
        "events":           sc_events_rows,
        "sow":              sc_sow_rows,
        "retention_churn":  _parse_retention_churn(retention_rows),
    }

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({
        "version":      CACHE_VERSION,
        "cutoff":       cutoff,
        "fetched_at":   datetime.now().isoformat(),
        "summary":      summary,
        "logos_all":    logos_all,
        "country":      country,
        "investment":   investment,
        "funnel":       funnel,
        "product_perf": product_perf,
        "flywheel":     flywheel,
        "sc":           sc,
    }))
    n_country = sum(len(segs) for ms in country.values() for segs in ms.values())
    print(f"  ✅ {len(fact_summary_rows)} filas fact · {len(summary)} summary · {len(logos_all)} meses logos · {n_country} registros país · {len(investment)} países investment · {len(funnel)} meses funnel · {len(product_perf)} productos · {len(sc_hist_rows)} meses SC hist · {len(sc_events_rows)} meses SC events · {len(sc_sow_rows)} SC sow")
    return summary, logos_all, country, investment, funnel, product_perf, flywheel, sc

# ── Metric computation (adapted from dashboard.py) ────────────────────────────
_MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def _month_label(m):   # "2026-02" → "Feb-26"
    return f"{_MONTH_NAMES[int(m[5:])-1]}-{m[2:4]}"

def _prev_m(m):
    y, mo = int(m[:4]), int(m[5:])
    mo -= 1
    if mo == 0: mo, y = 12, y - 1
    return f"{y:04d}-{mo:02d}"

def _prev_q(q_months):
    """Given a list of months for a quarter, return the 3 preceding months."""
    first = q_months[0]
    prev = []
    m = first
    for _ in range(3):
        m = _prev_m(m)
        prev.insert(0, m)
    return prev

def _calc(ms, bym):
    """Compute ARR Walk metrics — lógica canónica (walk-mrr-canonico.md).
    Buckets: new_base_t0, new_cross_t0, recov, react, churn (producto-nivel),
             upsell, downsell, pricing_others (comparación plan_name),
             cross_new_t1plus, cross_readop, cross_down.
    FX Impact = residual (debería ser mínimo con SQL canónico).
    """
    ms = [m for m in ms if m in bym]
    if not ms: return None
    le = lambda m: bym.get(m, {}).get("logos_eop", 0)
    me = lambda m: bym.get(m, {}).get("mrr_eop",   0)

    bop_l = le(_prev_m(ms[0])); eop_l = le(ms[-1])
    new_l   = sum(bym[m].get("logos_new",   0) for m in ms)
    recov_l = sum(bym[m].get("logos_recov", 0) for m in ms)
    react_l = sum(bym[m].get("logos_react", 0) for m in ms)
    disc_l  = bop_l + new_l + recov_l - eop_l + react_l
    nc_l    = disc_l - react_l
    n       = len(ms)
    avg_l   = (bop_l + eop_l) / 2 or 1

    bop_m       = me(_prev_m(ms[0])); eop_m = me(ms[-1])
    new_base_m  = sum(bym[m].get("mrr_new_base_t0",      0) for m in ms)
    new_cross_m = sum(bym[m].get("mrr_new_cross_t0",     0) for m in ms)
    new_m       = new_base_m + new_cross_m
    recov_m     = sum(bym[m].get("mrr_recov",            0) for m in ms)
    react_m     = sum(bym[m].get("mrr_react",            0) for m in ms)
    churn_m     = sum(bym[m].get("mrr_churn",            0) for m in ms)
    up_m        = sum(bym[m].get("mrr_upsell",           0) for m in ms)
    down_m      = sum(bym[m].get("mrr_downsell",         0) for m in ms)
    pricing_m   = sum(bym[m].get("mrr_pricing_others",   0) for m in ms)
    cross_new_m = sum(bym[m].get("mrr_cross_new_t1plus", 0) for m in ms)
    cross_ro_m  = sum(bym[m].get("mrr_cross_readop",     0) for m in ms)
    cross_dn_m  = sum(bym[m].get("mrr_cross_down",       0) for m in ms)

    nc_m  = react_m - churn_m
    fx_m  = eop_m - (bop_m + new_base_m + new_cross_m + recov_m + react_m
                     - churn_m + up_m + down_m + pricing_m
                     + cross_new_m + cross_ro_m - cross_dn_m)

    # Churn rate: promedio de tasas mensuales (CHURN - REACTIVATED) / BoP
    # Usa bi_retention.bi_customer_monthly_status cuando disponible (precalculado en logos_churn_rate_retention)
    _monthly_churn_rates = []
    for mi in ms:
        if "logos_churn_rate_retention" in bym.get(mi, {}):
            _monthly_churn_rates.append(bym[mi]["logos_churn_rate_retention"])
        else:
            _bop_mi   = le(_prev_m(mi))
            _churn_mi = bym.get(mi, {}).get("logos_churn", 0)
            _react_mi = bym.get(mi, {}).get("logos_react", 0)
            if _bop_mi > 0:
                _monthly_churn_rates.append(max(_churn_mi - _react_mi, 0) / _bop_mi)
    l_churn_pct = sum(_monthly_churn_rates) / len(_monthly_churn_rates) if _monthly_churn_rates else 0

    last    = ms[-1]
    yoy_key = f"{int(last[:4])-1:04d}{last[4:]}"
    l_py    = le(yoy_key)
    a_py    = me(yoy_key) * 12

    return {
        "l_bop": bop_l, "l_new": new_l, "l_recov": recov_l,
        "l_react": react_l, "l_disc": disc_l, "l_net_churn": nc_l, "l_eop": eop_l,
        "l_eop_py": l_py,
        "l_churn_pct": l_churn_pct,
        "l_new_pct": (new_l + recov_l) / avg_l / n,
        "l_disc_pct": disc_l / avg_l / n,
        "l_nc_pct":   nc_l   / avg_l / n,
        # ARR buckets canónicos (×12 para anualizar)
        "a_bop":            bop_m*12,
        "a_new":            new_m*12,            # combinado (base + cross T0)
        "a_new_base_t0":    new_base_m*12,
        "a_new_cross_t0":   new_cross_m*12,
        "a_recov":          recov_m*12,
        "a_react":          react_m*12,
        "a_churn":          churn_m*12,
        "a_net_churn":      nc_m*12,
        "a_upsell":         up_m*12,
        "a_down":           down_m*12,
        "a_pricing":        pricing_m*12,
        "a_cross_new":      cross_new_m*12,
        "a_cross_readop":   cross_ro_m*12,
        "a_cross_down":     cross_dn_m*12,
        "a_net_exp":        (up_m + down_m)*12,  # solo cambios de plan
        "a_fx":             fx_m*12,
        "a_eop":            eop_m*12,
        "a_net_new":        (eop_m - bop_m)*12,
        "a_cc_eop":         bym.get(ms[-1], {}).get("mrr_eop_cc", eop_m) * 12,
        "a_eop_py":         a_py,
    }

QUARTERS = [
    ("1Q24", ["2024-01","2024-02","2024-03"]),
    ("2Q24", ["2024-04","2024-05","2024-06"]),
    ("3Q24", ["2024-07","2024-08","2024-09"]),
    ("4Q24", ["2024-10","2024-11","2024-12"]),
    ("1Q25", ["2025-01","2025-02","2025-03"]),
    ("2Q25", ["2025-04","2025-05","2025-06"]),
    ("3Q25", ["2025-07","2025-08","2025-09"]),
    ("4Q25", ["2025-10","2025-11","2025-12"]),
    ("1Q26", ["2026-01","2026-02","2026-03"]),
    ("2Q26", ["2026-04","2026-05","2026-06"]),
    ("3Q26", ["2026-07","2026-08","2026-09"]),
    ("4Q26", ["2026-10","2026-11","2026-12"]),
]

def _seg_metrics(bym, all_months, latest_mm):
    q, mo, ytd = {}, {}, {}
    for lbl, ms in QUARTERS:
        r = _calc(ms, bym)
        if r: q[lbl] = r
    for m in all_months:
        r = _calc([m], bym)
        if r: mo[_month_label(m)] = r
    for yr in ["2024", "2025", "2026"]:
        ms = [m for m in all_months if m.startswith(yr) and m[5:] <= latest_mm]
        r  = _calc(ms, bym)
        if r: ytd[yr] = r
    return {"quarters": q, "months": mo, "ytd": ytd}

def build_seg_metrics(summary, logos_all, sc=None):
    _NUM = ["logos_eop","logos_new","logos_recov","logos_react","logos_churn",
            "mrr_eop","mrr_eop_cc","mrr_new","mrr_new_base_t0","mrr_new_cross_t0",
            "mrr_recov","mrr_react","mrr_churn",
            "mrr_upsell","mrr_downsell","mrr_pricing_others",
            "mrr_cross_new_t1plus","mrr_cross_readop","mrr_cross_down"]
    segs_raw = defaultdict(dict)
    for r in summary:
        segs_raw[r["seg"]][r["m"]] = r

    all_months = sorted({m for sd in segs_raw.values() for m in sd})
    segs_raw["all"] = {}
    for m in all_months:
        row = {"m": m, "seg": "all"}
        for k in _NUM:
            row[k] = sum(segs_raw[seg].get(m, {}).get(k, 0.0)
                         for seg in segs_raw if seg != "all")
        if m in logos_all:
            for lk in ["logos_eop","logos_new","logos_recov","logos_react"]:
                row[lk] = logos_all[m][lk]
        segs_raw["all"][m] = row

    # Inyectar tasa de churn desde dm_retention.bi_customer_monthly_status (cluster-1)
    # Aplica a "all", "Core" y "Lite" — la tabla tiene columna segment
    _rc_seg = ((sc or {}).get("retention_churn") or {}).get("by_seg", {})
    for m, seg_data in _rc_seg.items():
        for target_seg in ("all", "Core", "Lite"):
            rd = seg_data.get(target_seg)
            if rd and rd["bop"] > 0 and m in segs_raw.get(target_seg, {}):
                net = rd["churned"] - rd["reactivated"]
                segs_raw[target_seg][m]["logos_churn_rate_retention"] = max(net, 0) / rd["bop"]

    latest_mm = max(all_months)[5:] if all_months else "12"

    result = {}
    for seg in ["all", "Core", "Lite"]:
        if segs_raw.get(seg):
            result[seg] = _seg_metrics(segs_raw[seg], all_months, latest_mm)
    return result, segs_raw, all_months, latest_mm

# ── Number formatters ──────────────────────────────────────────────────────────
def _fm(v):
    """USD amount → "$X.XM" for ≥1M, "$XK" for <1M"""
    if v is None: return "N/A"
    if abs(v) >= 1e6:
        return f"${v/1e6:.1f}M"
    return f"${v/1e3:.0f}K"

def _fl(v):
    """Logos → "X.Xk" """
    if v is None: return "N/A"
    return f"{v/1e3:.1f}k"

def _fp(v):
    """Ratio → "+X.X%"  (or "(X.X%)" for negative) """
    if v is None: return "N/A"
    pct = v * 100
    return f"{pct:+.1f}%"

def _pct_delta(curr, prev):
    """Compute % change and return (label, is_positive)."""
    if not prev: return "0%", True
    delta = (curr - prev) / abs(prev)
    if delta > 9.99: return ">+999%", True
    if delta < -9.99: return "<-999%", False
    return _fp(delta), delta >= 0

def _arr_pct_delta(curr_dict, prev_dict, key):
    c = curr_dict.get(key, 0)
    p = prev_dict.get(key, 0)
    return _pct_delta(c, p)

# ── SVG Sparkline ──────────────────────────────────────────────────────────────
def _sparkline(values, color="#534AB7", width=44, height=14, stroke=1.5):
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return f'<svg class="bf-spark" viewBox="0 0 {width} {height}"></svg>'
    lo, hi = min(vals), max(vals)
    rng = hi - lo or 1
    n   = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = i / (n - 1) * (width - 2) + 1
        y = height - 2 - (v - lo) / rng * (height - 4)
        pts.append(f"{x:.1f},{y:.1f}")
    return (f'<svg class="bf-spark" viewBox="0 0 {width} {height}">'
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round"/></svg>')

# ── Build metrics.yaml structure ───────────────────────────────────────────────
_PRODUCT_MAP = [
    {"rs": "Alegra Contabilidad", "name": "Accounting"},
    {"rs": "Alegra POS",          "name": "POS"},
    {"rs": "Alegra Nómina",       "name": "Payroll"},
    {"rs": "Alegra Facturación",  "name": "Invoicing"},
]

def _build_product_perf(months6, product_perf, logos_all):
    """Construye la tabla de product performance para 6_rd: 4 productos × 6 meses."""
    products = []
    total_subs_by_month = [0.0] * len(months6)

    for pc in _PRODUCT_MAP:
        rs_key = pc["rs"]
        pdata  = product_perf.get(rs_key, {})

        eop_k, pct_logos, churn_rate, avg_ticket, pct_core = [], [], [], [], []
        for i, m in enumerate(months6):
            md  = pdata.get(m + "-01", {}) or pdata.get(m, {})
            eop = md.get("eop_subs", 0)
            bop = md.get("bop_subs", 0)
            ch  = md.get("churn_logos", 0)
            rx  = md.get("react_logos", 0)
            nl  = md.get("new_logos", 0)
            nm  = md.get("new_mrr", 0.0)
            co  = md.get("core_subs", 0)

            total_logos_eop = logos_all.get(m, {}).get("logos_eop", 0)

            eop_k.append(f"{eop/1000:.2f}")
            pct_logos.append(f"{eop/total_logos_eop*100:.1f}%" if total_logos_eop else "—")
            net_churn = max(ch - rx, 0)
            churn_rate.append(f"{net_churn/bop*100:.2f}%" if bop else "—")
            avg_ticket.append(f"${nm/nl:.2f}" if nl else "—")
            pct_core.append(f"{co/eop*100:.1f}%" if eop else "—")

            total_subs_by_month[i] += eop

        products.append({
            "name":       pc["name"],
            "eop_subs":   eop_k,
            "pct_logos":  pct_logos,
            "churn_rate": churn_rate,
            "avg_ticket": avg_ticket,
            "pct_core":   pct_core,
        })

    total_logos_k = [
        f"{logos_all.get(m, {}).get('logos_eop', 0)/1000:.2f}"
        for m in months6
    ]
    total_subs_k = [f"{v/1000:.2f}" for v in total_subs_by_month]

    return {
        "months":        [_month_label(m) for m in months6],
        "products":      products,
        "total_subs":    total_subs_k,
        "total_logos_k": total_logos_k,
    }

def _build_funnel_countries(months13, funnel):
    """Construye {country: {signups, logos, cvr}} para los 13 meses del funnel."""
    _COUNTRIES_FUNNEL = ["colombia", "mexico", "republicaDominicana", "costaRica"]

    def _country_data(ck):
        signups = [funnel.get(m, {}).get(ck, {}).get("signups", 0) for m in months13]
        logos   = [funnel.get(m, {}).get(ck, {}).get("logos",   0) for m in months13]
        cvr     = [round(logos[i] / signups[i] * 100, 1) if signups[i] else 0
                   for i in range(len(months13))]
        return {"signups": signups, "logos": logos, "cvr": cvr}

    result = {"months": [_month_label(m) for m in months13]}
    for ck in _COUNTRIES_FUNNEL:
        result[ck] = _country_data(ck)
    return result


def _build_flywheel(flywheel):
    """Convierte {month_iso: {ent_new_adds,...}} → arrays para los charts de slides 5-6."""
    months_iso = sorted(flywheel.keys())
    _names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    def _fw_label(m):
        return f"{_names[int(m[5:])-1]}\n{m[:4]}"
    def _fw_q_label(m):
        return f"{_names[int(m[5:])-1]}-{m[2:4]}"

    # Quarterly indices: quarter-end months (Mar/Jun/Sep/Dec) + trailing non-quarter months
    q_end    = [m for m in months_iso if int(m[5:7]) in (3, 6, 9, 12)]
    last_q   = q_end[-1] if q_end else (months_iso[-1] if months_iso else "")
    trailing = [m for m in months_iso if m > last_q]
    q_all    = q_end + trailing
    q_idx    = [months_iso.index(m) for m in q_all]
    q_labels = [_fw_q_label(m) for m in q_all]

    return {
        "months":       [_fw_label(m) for m in months_iso],
        "ent_new_adds": [flywheel[m]["ent_new_adds"] for m in months_iso],
        "ent_churn":    [flywheel[m]["ent_net_churn"] for m in months_iso],
        "ent_stock":    [flywheel[m]["ent_stock"]     for m in months_iso],
        "lg_new_adds":  [flywheel[m]["lg_new_adds"]   for m in months_iso],
        "lg_churn":     [flywheel[m]["lg_net_churn"]  for m in months_iso],
        "lg_stock":     [flywheel[m]["lg_stock"]      for m in months_iso],
        "q_idx":        q_idx,
        "q_labels":     q_labels,
    }


def _build_supercontadores(sc_hist, sc_events, sc_sow, cutoff):
    """
    Builds supercontadores data from Redshift results.
    Returns (supercontadores_dict, funnel_hist_list).
    """
    _MES_LONG = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                 "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    _MES_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    def _short_label(m):  # "2026-05" → "May'26"
        mo = int(m[5:7])
        return f"{_MES_SHORT[mo-1]}'{m[2:4]}"

    # ── hist: full monthly stock ──────────────────────────────────────────────
    hist = [{"m": r["m"],
             "clientes": int(r.get("clientes") or 0),
             "propia":   int(r.get("propia")   or 0),
             "total":    int(r.get("clientes") or 0) + int(r.get("propia") or 0)}
            for r in sc_hist]

    latest_h  = hist[-1] if hist else {"clientes": 0, "propia": 0, "total": 0}
    eop       = latest_h["total"]
    clientes  = latest_h["clientes"]
    propia    = latest_h["propia"]

    # ── corte label ──────────────────────────────────────────────────────────
    co_mo  = int(cutoff[5:7])
    co_yr  = cutoff[:4]
    corte  = f"{_MES_LONG[co_mo-1]} {co_yr}"

    # ── fc: current snapshot ─────────────────────────────────────────────────
    latest_ev = sc_events[-1] if sc_events else {}
    fc = {
        "denom":           int(latest_ev.get("total")    or 0),
        "trabaja":         int(latest_ev.get("nw")       or 0),
        "trabaja_pct":   float(latest_ev.get("pct_trabaja")     or 0),
        "contabiliza":     int(latest_ev.get("nk")       or 0),
        "contabiliza_pct":float(latest_ev.get("pct_contabiliza") or 0),
        "acct_ge1":        int(latest_ev.get("nge1")     or 0),
        "acct_ge1_pct":  float(latest_ev.get("pct_ge1") or 0),
        "acct_ge2":        int(latest_ev.get("nge2")     or 0),
        "acct_ge2_pct":  float(latest_ev.get("pct_ge2") or 0),
        "acct_ge3":        int(latest_ev.get("nge3")     or 0),
        "acct_ge3_pct":  float(latest_ev.get("pct_ge3") or 0),
        "eventos": [
            {"k": "Factura (ac-invoice-submitted)",        "n": int(latest_ev.get("nf")  or 0), "pct": float(latest_ev.get("pct_factura")    or 0), "attr": False},
            {"k": "Asiento contable (ac-journal-created)", "n": int(latest_ev.get("nj")  or 0), "pct": float(latest_ev.get("pct_asiento")    or 0), "attr": True},
            {"k": "Catálogo de cuentas",                   "n": int(latest_ev.get("nl")  or 0), "pct": float(latest_ev.get("pct_catalogo")   or 0), "attr": False},
            {"k": "Saldos contables",                      "n": int(latest_ev.get("no_") or 0), "pct": float(latest_ev.get("pct_saldos")     or 0), "attr": False},
            {"k": "Admin XML",                             "n": int(latest_ev.get("nx")  or 0), "pct": float(latest_ev.get("pct_adminxml")   or 0), "attr": True},
        ],
    }

    # ── fc_hist: monthly bookkeeping rate ─────────────────────────────────────
    fc_hist = [{"m":       r["m"],
                "clientes": int(r.get("total")  or 0),
                "contabiliza": int(r.get("nk")  or 0),
                "pct":    float(r.get("pct_contabiliza") or 0),
                "tracked": float(r.get("pct_contabiliza") or 0) > 0}
               for r in sc_events]

    # ── funnelHist: last 7 months for area chart ──────────────────────────────
    funnel_hist = [{"m":       _short_label(r["m"]),
                    "factura": float(r.get("pct_factura")  or 0),
                    "asiento": float(r.get("pct_asiento")  or 0),
                    "catalogo":float(r.get("pct_catalogo") or 0),
                    "saldos":  float(r.get("pct_saldos")   or 0),
                    "adminxml":float(r.get("pct_adminxml") or 0)}
                   for r in sc_events[-7:]]

    # ── sow: top-20 table ─────────────────────────────────────────────────────
    sow = []
    for r in sc_sow:
        real = int(r.get("real") or 0)
        asoc_n = int(r.get("asoc") or 0)
        mrr  = float(r.get("mrr") or 0)
        sow_asoc = round(100.0 * real / asoc_n, 1) if asoc_n > 0 else None
        pais_raw = str(r.get("pais") or "")
        pais_map = {
            "Colombia":             "COL",
            "Mexico":               "MEX",
            "Costa Rica":           "CRI",
            "Republica Dominicana": "DOM",
            "Spain":                "ESP",
            "Peru":                 "PER",
            "Argentina":            "ARG",
            "Chile":                "CHL",
            "Panama":               "PAN",
            "USA":                  "USA",
        }
        pais = pais_map.get(pais_raw, pais_raw[:3].upper() if pais_raw else "—")
        real_mom = r.get("real_mom")
        real_yoy = r.get("real_yoy")
        def _delta(hist_val):
            if hist_val is None or asoc_n == 0:
                return None
            return round(100.0 * (real - int(hist_val)) / asoc_n, 1)
        sow.append({
            "rank":      int(r.get("rank") or 0),
            "contador":  str(r.get("contador") or ""),
            "pais":      pais,
            "mrr":       mrr,
            "real":      real,
            "asoc":      asoc_n,
            "pot":       None,
            "sow_asoc":  sow_asoc,
            "sow_pot":   None,
            "nivel":     str(r.get("nivel") or ""),
            "delta_mom": _delta(real_mom),
            "delta_yoy": _delta(real_yoy),
        })

    # ── sow_tot: aggregated totals ────────────────────────────────────────────
    tot_mrr  = round(sum(r["mrr"]  for r in sow))
    tot_real = sum(r["real"] for r in sow)
    tot_asoc = sum(r["asoc"] for r in sow)
    gap = tot_asoc - tot_real
    sow_asoc_tot = round(100.0 * tot_real / tot_asoc, 1) if tot_asoc > 0 else None
    # aggregate historical for total delta
    _mom_vals = [int(r.get("real_mom") or 0) for r in sc_sow if r.get("real_mom") is not None]
    _yoy_vals = [int(r.get("real_yoy") or 0) for r in sc_sow if r.get("real_yoy") is not None]
    tot_real_mom = sum(_mom_vals) if _mom_vals else None
    tot_real_yoy = sum(_yoy_vals) if _yoy_vals else None
    delta_mom_tot = round(100.0 * (tot_real - tot_real_mom) / tot_asoc, 1) if tot_real_mom is not None and tot_asoc > 0 else None
    delta_yoy_tot = round(100.0 * (tot_real - tot_real_yoy) / tot_asoc, 1) if tot_real_yoy is not None and tot_asoc > 0 else None
    sow_tot = {"mrr": tot_mrr, "real": tot_real, "asoc": tot_asoc,
               "pot": None, "sow_asoc": sow_asoc_tot, "sow_pot": None, "gap": gap,
               "delta_mom": delta_mom_tot, "delta_yoy": delta_yoy_tot}

    supercontadores = {
        "corte":   corte,
        "eop":     eop,
        "clientes":clientes,
        "propia":  propia,
        "hist":    hist,
        "fc":      fc,
        "fc_hist": fc_hist,
        "sow":     sow,
        "sow_tot": sow_tot,
    }
    return supercontadores, funnel_hist


# Orden de equipos por categoría — coincide con el orden ya usado en 7_headcount.j2.
# dim_headcount_team_category solo da equipo→categoría, no el orden de presentación
# dentro de cada categoría, así que se fija acá (son 21 equipos, no cambia seguido).
_HC_CATEGORY_ORDER = [
    ("Cost of Revenue", ["Customer Experience", "Customer Success", "Collection"]),
    ("Customer Acquisition Costs", ["Growth", "Sales", "Accountants", "Strategic Relationships", "RevOps"]),
    ("Product & Development", ["Development", "Product"]),
    ("General & Administration", ["Data", "Finance", "People", "Strategic Direction", "Talent Acquisition"]),
    ("Alanube", ["Alanube"]),
    ("Other", ["CEO", "CTO", "Design", "Product Manager", "Talent"]),
]


def _hc_pct(curr, prev):
    """(curr-prev)/prev — '—' si prev es 0 (no hay base de comparación), no '0%'."""
    if not prev:
        return "—"
    pct = (curr - prev) / prev * 100
    return f"{'+' if pct > 0 else ''}{pct:.1f}%"


def _hc_diff(curr, prev):
    """curr-prev con signo — '—' si prev es 0 (mismo criterio que _hc_pct)."""
    if not prev:
        return "—"
    d = curr - prev
    return f"+{d}" if d > 0 else (str(d) if d < 0 else "0")


def _hc_signed(n):
    """Para 'Actual vs Fcst' cuando Fcst=0 — se muestra el Closing directo con signo."""
    return f"+{n}" if n > 0 else (str(n) if n < 0 else "0")


def _hc_pct_of(closing, fcst):
    if not fcst:
        return "—"
    return f"{closing / fcst * 100:.1f}%"


def _hc_share(closing, total):
    if not total:
        return "0%"
    return f"{round(closing / total * 100)}%"


def _hc_class(s):
    """Clase CSS por signo — regla estándar (positivo=verde, negativo=rojo), sin
    inversión (headcount no es como Churn/CAC)."""
    if s in ("—", "0", "0%", "0.0%"):
        return "hcs-neu"
    return "hcs-neg" if s.startswith("-") else "hcs-pos"


def _hc_team_row(team, cutoff, m1, m12, dec_prior, eop, fcst):
    dec25 = eop.get((team, dec_prior), 0)
    v_m1 = eop.get((team, m1), 0)
    v_m12 = eop.get((team, m12), 0)
    closing = eop.get((team, cutoff), 0)
    fcst_v = fcst.get((team, cutoff), 0)
    mom = _hc_pct(closing, v_m1)
    yoy = _hc_pct(closing, v_m12)
    var_ly = _hc_diff(closing, v_m12)
    avf = _hc_diff(closing, fcst_v) if fcst_v else _hc_signed(closing)
    pct_pred = _hc_pct_of(closing, fcst_v)
    return {
        "name": team,
        "dec25": dec25, "m1": v_m1, "m12": v_m12, "closing": closing,
        "mom_pct": mom, "mom_class": _hc_class(mom),
        "yoy_pct": yoy, "yoy_class": _hc_class(yoy),
        "var_ly": var_ly, "var_ly_class": _hc_class(var_ly),
        "fcst": fcst_v, "actual_vs_fcst": avf, "actual_vs_fcst_class": _hc_class(avf),
        "pct_pred": pct_pred,
    }


def _build_headcount(cutoff: str) -> tuple[dict, dict]:
    """Arma metrics.hc (tabla + KPIs, slide 2) y metrics.pt (series 13 meses, slide 3)
    desde las 4 tablas de bi_strategic_relationships (ver memory/project_board_agent.md,
    2026-07-03). Reemplaza el copy/paste manual de los 2 Google Sheets de Headcount.

    OJO — bug real encontrado en el template ya publicado al diseñar esto: las columnas
    "MoM%"/"YoY%"/"Var HC vs LY" del board venían calculadas con el mes de referencia
    cambiado (MoM% usaba M-12, YoY%/Var HC vs LY usaban M-1). Acá se calcula CORRECTO
    (MoM% vs M-1, YoY%/Var HC vs LY vs M-12) — los números de esas columnas van a diferir
    de lo ya publicado a propósito."""
    eop = load_headcount_eop()
    fcst = load_headcount_forecast()
    moves = load_headcount_movements()
    cats = load_headcount_categories()

    y, m = int(cutoff[:4]), int(cutoff[5:])
    m1 = _prev_m(cutoff)
    m12 = f"{y - 1:04d}-{m:02d}"
    dec_prior = f"{y - 1:04d}-12"

    all_teams = sorted({team for _, teams in _HC_CATEGORY_ORDER for team in teams})
    # Por si dim_headcount_team_category tiene equipos que no están en el orden fijo de arriba
    # (no debería pasar con los 21 conocidos, pero no hay que caerse si aparece uno nuevo).
    known = {t for _, teams in _HC_CATEGORY_ORDER for t in teams}
    extra = sorted(set(cats.keys()) - known)

    categories_out = []
    total_dec25 = total_m1 = total_m12 = total_closing = total_fcst = 0
    for cat_name, teams in _HC_CATEGORY_ORDER + ([("Other (sin mapear)", extra)] if extra else []):
        team_rows = [_hc_team_row(t, cutoff, m1, m12, dec_prior, eop, fcst) for t in teams]
        c_dec25 = sum(r["dec25"] for r in team_rows)
        c_m1 = sum(r["m1"] for r in team_rows)
        c_m12 = sum(r["m12"] for r in team_rows)
        c_closing = sum(r["closing"] for r in team_rows)
        c_fcst = sum(r["fcst"] for r in team_rows)
        total_dec25 += c_dec25; total_m1 += c_m1; total_m12 += c_m12
        total_closing += c_closing; total_fcst += c_fcst
        cat_mom = _hc_pct(c_closing, c_m1)
        cat_yoy = _hc_pct(c_closing, c_m12)
        cat_var = _hc_diff(c_closing, c_m12)
        cat_avf = _hc_diff(c_closing, c_fcst) if c_fcst else _hc_signed(c_closing)
        categories_out.append({
            "name": cat_name,
            "row": {
                "dec25": c_dec25, "m1": c_m1, "m12": c_m12, "closing": c_closing,
                "mom_pct": cat_mom, "mom_class": _hc_class(cat_mom),
                "yoy_pct": cat_yoy, "yoy_class": _hc_class(cat_yoy),
                "var_ly": cat_var, "var_ly_class": _hc_class(cat_var),
                "fcst": c_fcst, "actual_vs_fcst": cat_avf, "actual_vs_fcst_class": _hc_class(cat_avf),
                "pct_pred": _hc_pct_of(c_closing, c_fcst),
            },
            "teams": team_rows,
        })

    # Share necesita el total final — se calcula una vez que se conoce total_closing
    for cat in categories_out:
        cat["row"]["share"] = _hc_share(cat["row"]["closing"], total_closing)
        for r in cat["teams"]:
            r["share"] = _hc_share(r["closing"], total_closing)

    active_mom = _hc_pct(total_closing, total_m1)
    active_yoy = _hc_pct(total_closing, total_m12)
    active_var = _hc_diff(total_closing, total_m12)
    active_avf = _hc_diff(total_closing, total_fcst) if total_fcst else _hc_signed(total_closing)
    active_team_row = {
        "dec25": total_dec25, "m1": total_m1, "m12": total_m12, "closing": total_closing,
        "share": "100%",
        "mom_pct": active_mom, "mom_class": _hc_class(active_mom),
        "yoy_pct": active_yoy, "yoy_class": _hc_class(active_yoy),
        "var_ly": active_var, "var_ly_class": _hc_class(active_var),
        "fcst": total_fcst, "actual_vs_fcst": active_avf, "actual_vs_fcst_class": _hc_class(active_avf),
        "pct_pred": _hc_pct_of(total_closing, total_fcst),
    }

    # ── KPIs sidebar ──
    new_hires_mes = sum(moves.get((t, cutoff), (0, 0))[0] for t in all_teams)
    attrition_mes = sum(moves.get((t, cutoff), (0, 0))[1] for t in all_teams)
    new_hires_ytd = 0
    for mm in range(1, m + 1):
        mes_iso = f"{y:04d}-{mm:02d}"
        new_hires_ytd += sum(moves.get((t, mes_iso), (0, 0))[0] for t in all_teams)
    turnover_rate = (attrition_mes / total_closing * 100) if total_closing else 0.0

    # Promedio de turnover mensual del año calendario anterior completo
    prev_year_rates = []
    for mm in range(1, 13):
        mes_iso = f"{y - 1:04d}-{mm:02d}"
        hc_mes = sum(eop.get((t, mes_iso), 0) for t in all_teams)
        attr_mes = sum(moves.get((t, mes_iso), (0, 0))[1] for t in all_teams)
        if hc_mes:
            prev_year_rates.append(attr_mes / hc_mes * 100)
    turnover_fy_prev_avg = sum(prev_year_rates) / len(prev_year_rates) if prev_year_rates else 0.0

    hc_out = {
        "slide2_title": "Headcount",
        "total": total_closing,
        "new_hires": new_hires_mes, "new_hires_sub": f"in {_month_label(cutoff).split('-')[0]} · {new_hires_ytd} YTD",
        "attrition": attrition_mes,
        "turnover_rate": f"{turnover_rate:.2f}%",
        "turnover_rate_sub": f"FY {y - 1} average: {turnover_fy_prev_avg:.2f}",
        # Etiquetas de columna dinámicas para la tabla (antes texto literal en el template,
        # causa del bug de columnas Apr-26/May-25 cruzadas — ver memory/project_board_agent.md).
        "dec_label": _month_label(dec_prior), "m1_label": _month_label(m1),
        "m12_label": _month_label(m12), "closing_label": _month_label(cutoff),
        "categories": categories_out,
        "active_team_row": active_team_row,
    }

    # ── Slide 3 — serie de 13 meses (m12 → cutoff inclusive) ──
    pt_months, pt_hc, pt_hires, pt_attr, pt_turnover = [], [], [], [], []
    yy, mm = y - 1, m
    for _ in range(13):
        mes_iso = f"{yy:04d}-{mm:02d}"
        hc_mes = sum(eop.get((t, mes_iso), 0) for t in all_teams)
        hires_mes = sum(moves.get((t, mes_iso), (0, 0))[0] for t in all_teams)
        attr_mes = sum(moves.get((t, mes_iso), (0, 0))[1] for t in all_teams)
        pt_months.append(_MONTH_NAMES[mm - 1])
        pt_hc.append(hc_mes)
        pt_hires.append(hires_mes)
        pt_attr.append(attr_mes)
        pt_turnover.append(round(attr_mes / hc_mes * 100, 2) if hc_mes else 0.0)
        mm += 1
        if mm == 13:
            mm = 1
            yy += 1

    pt_out = {
        "months": pt_months, "hc_eop": pt_hc, "hires": pt_hires,
        "attrition": pt_attr, "attrition_pct": pt_turnover, "turnover_pct": pt_turnover,
        "ya_max": max(pt_hires + pt_attr, default=1),
        "yhead_max": max(pt_hc, default=1), "yhead_min": 0,
        "ylines_max": max(pt_turnover, default=1),
        "yt_max": max(pt_turnover, default=1),
    }
    return hc_out, pt_out


def _build_chart_history(seg_metrics, segs_raw, cutoff, n_months=16):
    """Genera arrays mensuales para los charts del slide 4 (últimos n_months meses)."""
    all_m_data = seg_metrics.get("all", {}).get("months", {})
    all_iso    = sorted(m for m in segs_raw.get("all", {}).keys() if m <= cutoff)
    chart_iso  = all_iso[-n_months:]

    # ARR de Alanube desde RS (ver load_alanube_arr) — spot y cc usan la misma serie: no hay
    # ajuste de constant currency separado para Alanube todavía (igual que en chart_alanube.yaml
    # antes, donde ambos dicts tenían los mismos valores).
    alanube_spot_map = alanube_cc_map = load_alanube_arr()

    def _alanube_val(mapping, iso_m):
        if iso_m in mapping:
            return mapping[iso_m]
        # Usar el último valor conocido anterior al mes pedido
        candidates = [v for k, v in mapping.items() if k <= iso_m]
        return candidates[-1] if candidates else 0

    months_out      = []
    alegra_spot_out = []
    alegra_cc_out   = []
    alanube_spot_out= []
    alanube_cc_out  = []
    new_adds_out    = []
    net_churn_out   = []
    net_exp_out     = []
    fx_impact_out   = []
    net_new_out     = []

    for iso_m in chart_iso:
        lbl = _month_label(iso_m)
        d   = all_m_data.get(lbl, {})

        a_eop    = d.get("a_eop",    0)
        a_cc_eop = d.get("a_cc_eop", a_eop)
        a_new    = d.get("a_new",    0)
        a_recov  = d.get("a_recov",  0)
        a_react  = d.get("a_react",  0)
        a_churn  = d.get("a_churn",  0)
        a_upsell = d.get("a_upsell", 0)
        a_down   = d.get("a_down",   0)
        a_pricing   = d.get("a_pricing",    0)
        a_cross_new = d.get("a_cross_new",  0)
        a_cross_ro  = d.get("a_cross_readop", 0)
        a_cross_dn  = d.get("a_cross_down", 0)
        a_net_new   = d.get("a_net_new", 0)
        a_fx        = d.get("a_fx",      0)

        months_out.append(lbl)
        alegra_spot_out.append(round(a_eop    / 1e6, 2))
        alegra_cc_out.append(  round(a_cc_eop / 1e6, 2))
        alanube_spot_out.append(_alanube_val(alanube_spot_map, iso_m))
        alanube_cc_out.append(  _alanube_val(alanube_cc_map,   iso_m))
        new_adds_out.append(   round((a_new + a_recov) / 1000))
        net_churn_out.append(  round((-a_churn + a_react) / 1000))
        net_exp_out.append(    round((a_upsell + a_down + a_pricing + a_cross_new + a_cross_ro - a_cross_dn) / 1000))
        fx_impact_out.append(  round(a_fx    / 1000))
        net_new_out.append(    round(a_net_new / 1000))

    return {
        "months":        months_out,
        "alegra_spot":   alegra_spot_out,
        "alegra_cc":     alegra_cc_out,
        "alanube_spot":  alanube_spot_out,
        "alanube_cc":    alanube_cc_out,
        "new_adds":      new_adds_out,
        "net_churn":     net_churn_out,
        "net_expansion": net_exp_out,
        "fx_impact":     fx_impact_out,
        "net_new":       net_new_out,
    }


def build_yaml(seg_metrics, segs_raw, all_months, latest_mm, country_raw, cutoff, investment=None, funnel=None, product_perf=None, logos_all=None, flywheel=None, sc=None):
    # Latest month label (e.g. "Feb-26") and last quarter label
    latest_m = cutoff  # "2026-02"
    latest_m_lbl = _month_label(latest_m)  # "Feb-26"

    # Determine which quarter cutoff falls in
    def _quarter_of(m):
        for lbl, ms in QUARTERS:
            if m in ms: return lbl
        return QUARTERS[-1][0]
    latest_q_lbl = _quarter_of(latest_m)

    # ── Prior month & prior year month
    prev_m  = _prev_m(latest_m)
    prev_m_lbl = _month_label(prev_m)
    prev_yr = f"{int(latest_m[:4])-1}{latest_m[4:]}"

    def _mo(seg, m=latest_m_lbl):
        return seg_metrics.get(seg, {}).get("months", {}).get(m, {})

    def _mo_prev(seg):
        return seg_metrics.get(seg, {}).get("months", {}).get(prev_m_lbl, {})

    def _mo_py(seg):
        py_lbl = _month_label(prev_yr)
        return seg_metrics.get(seg, {}).get("months", {}).get(py_lbl, {})

    def _q(seg, q=latest_q_lbl):
        return seg_metrics.get(seg, {}).get("quarters", {}).get(q, {})

    def _q_prev(seg):
        # Previous quarter label
        idx = next((i for i, (l, _) in enumerate(QUARTERS) if l == latest_q_lbl), -1)
        if idx <= 0: return {}
        prev_q_lbl = QUARTERS[idx-1][0]
        return seg_metrics.get(seg, {}).get("quarters", {}).get(prev_q_lbl, {})

    # ── Global KPIs (slide 1 — Key Summary)
    all_m    = _mo("all")
    all_m_pv = _mo_prev("all")
    all_m_py = _mo_py("all")

    def _delta_m(key):  return _pct_delta(all_m.get(key,0), all_m_pv.get(key,0))
    def _delta_y(key):  return _pct_delta(all_m.get(key,0), all_m_py.get(key,0))

    arr_mom_str, arr_mom_pos      = _delta_m("a_eop")
    arr_yoy_str, arr_yoy_pos      = _delta_y("a_eop")
    new_mrr_mom_str, new_mrr_mom_pos = _delta_m("a_new")
    new_mrr_yoy_str, new_mrr_yoy_pos = _delta_y("a_new")
    new_logos_mom_str, new_logos_mom_pos = _delta_m("l_new")
    new_logos_yoy_str, new_logos_yoy_pos = _delta_y("l_new")

    # ── Quarter-end detection y QoQ deltas ───────────────────────────────────
    is_quarter_end = int(latest_m[5:]) in (3, 6, 9, 12)
    all_q     = _q("all")
    all_q_pv  = _q_prev("all")
    arr_qoq_str,       arr_qoq_pos       = _pct_delta(all_q.get("a_eop",0), all_q_pv.get("a_eop",0))
    new_mrr_qoq_str,   new_mrr_qoq_pos   = _pct_delta(all_q.get("a_new",0), all_q_pv.get("a_new",0))
    new_logos_qoq_str, new_logos_qoq_pos = _pct_delta(all_q.get("l_new",0), all_q_pv.get("l_new",0))
    # Label del quarter previo, e.g. "Q4 2025"
    idx_q = next((i for i,(l,_) in enumerate(QUARTERS) if l==latest_q_lbl), -1)
    prev_q_label = QUARTERS[idx_q-1][0] if idx_q > 0 else "—"

    # ── ARR Walk products (Core + Lite)  ─────────────────────────────────────
    _PRODUCT_CFG = [
        {"seg": "Core", "id": "core", "name": "Core", "color": "#534AB7"},
        {"seg": "Lite", "id": "lite", "name": "Lite", "color": "#1D9E75"},
    ]

    # Build quarterly chart arrays for each product
    available_qs = [lbl for lbl, ms in QUARTERS
                    if _calc(ms, segs_raw.get("Core", {}))]

    products = []
    for cfg in _PRODUCT_CFG:
        seg      = cfg["seg"]
        q_data   = seg_metrics.get(seg, {}).get("quarters", {})
        q_prev_d = _q_prev(seg)
        q_cur_d  = _q(seg)
        q_py_key = _month_label(prev_yr)
        q_py_d   = seg_metrics.get(seg, {}).get("months", {}).get(q_py_key, {})

        if not q_cur_d:
            continue  # segment not present

        # Chart arrays — all available quarters
        chart_qs = [lbl for lbl, _ in QUARTERS if lbl in q_data]
        arr_new_rec    = [q_data[q].get("a_new",   0)/1e6 + q_data[q].get("a_recov", 0)/1e6 for q in chart_qs]
        arr_expansion  = [max(q_data[q].get("a_upsell",  0)/1e6, 0) for q in chart_qs]
        arr_churn      = [max(q_data[q].get("a_churn",   0)/1e6, 0) for q in chart_qs]
        arr_contraction= [max(q_data[q].get("a_down",    0)/1e6, 0) for q in chart_qs]
        arr_net_new    = [q_data[q].get("a_net_new", 0)/1e6 for q in chart_qs]
        logos_new_ch   = [q_data[q].get("l_new",   0) + q_data[q].get("l_recov", 0) for q in chart_qs]
        logos_exp_ch   = [0] * len(chart_qs)
        logos_churn_ch = [q_data[q].get("l_disc",  0) for q in chart_qs]
        logos_down_ch  = [0] * len(chart_qs)
        y_max          = max((max(arr_new_rec + arr_expansion) if arr_new_rec else 0),
                             (max(arr_churn + arr_contraction) if arr_churn else 0)) * 1.25 or 1

        # q_cards (BoP/EoP per quarter for last 5 quarters)
        q_cards = []
        bym_seg = segs_raw.get(seg, {})
        for q_lbl, ms in QUARTERS[-5:]:
            if not any(m in bym_seg for m in ms): continue
            bop_m_key = _prev_m(ms[0])
            bop_mrr   = bym_seg.get(bop_m_key, {}).get("mrr_eop", 0)
            bop_logos = bym_seg.get(bop_m_key, {}).get("logos_eop", 0)
            eop_m_key = ms[-1]
            eop_mrr   = bym_seg.get(eop_m_key, {}).get("mrr_eop", 0)
            eop_logos = bym_seg.get(eop_m_key, {}).get("logos_eop", 0)
            q_cards.append({
                "label":    q_lbl,
                "bopArr":   _fm(bop_mrr * 12),
                "bopLogos": round(bop_logos / 1e3, 2),
                "eopArr":   _fm(eop_mrr * 12),
                "eopLogos": round(eop_logos / 1e3, 2),
            })

        # Key headline metrics
        logos_yoy_str, logos_yoy_pos = _pct_delta(q_cur_d.get("l_eop",0), q_cur_d.get("l_eop_py",0))
        logos_qoq_str, logos_qoq_pos = _pct_delta(q_cur_d.get("l_eop",0), q_prev_d.get("l_eop",0))
        arr_yoy_s,  arr_yoy_p   = _pct_delta(q_cur_d.get("a_eop",0), q_cur_d.get("a_eop_py",0))
        arr_qoq_s,  arr_qoq_p   = _pct_delta(q_cur_d.get("a_eop",0), q_prev_d.get("a_eop",0))
        churn_qoq_s, churn_qoq_p = _pct_delta(q_cur_d.get("a_churn",0), q_prev_d.get("a_churn",0))
        churn_yoy_s, churn_yoy_p = _pct_delta(q_cur_d.get("a_churn",0), q_cur_d.get("a_eop_py",0))
        nn_qoq_s,   nn_qoq_p    = _pct_delta(q_cur_d.get("a_net_new",0), q_prev_d.get("a_net_new",0))

        prev_q_nn = q_prev_d.get("a_net_new", 0)
        prev_q_lbl_str = QUARTERS[max(0, next((i for i,(l,_) in enumerate(QUARTERS) if l==latest_q_lbl), 0)-1)][0]

        products.append({
            "id":           cfg["id"],
            "name":         cfg["name"],
            "color":        cfg["color"],
            "action_title": f"ARR Walk {cfg['name']} — {latest_q_lbl}",
            # KPI cards
            "arr_eop":      _fm(q_cur_d.get("a_eop", 0)),
            "arr_yoy":      arr_yoy_s,
            "arr_qoq":      arr_qoq_s,
            "logos_eop":    _fl(q_cur_d.get("l_eop", 0)),
            "logos_yoy":    logos_yoy_str,
            "logos_qoq":    logos_qoq_str,
            "churn_arr":    _fm(q_cur_d.get("a_churn", 0)),
            "churn_qoq":    churn_qoq_s,
            "churn_yoy":    churn_yoy_s,
            "net_new_arr":  _fm(q_cur_d.get("a_net_new", 0)),
            "net_new_vs":   f"vs {_fm(prev_q_nn)} en {prev_q_lbl_str}",
            "net_new_qoq":  nn_qoq_s,
            # Chart data
            "quarters":        chart_qs,
            "arr_new_rec":     arr_new_rec,
            "arr_expansion":   arr_expansion,
            "arr_churn":       arr_churn,
            "arr_contraction": arr_contraction,
            "arr_net_new":     arr_net_new,
            "logos_new":       logos_new_ch,
            "logos_expansion": logos_exp_ch,
            "logos_churn":     logos_churn_ch,
            "logos_contraction": logos_down_ch,
            "q_cards":         q_cards,
            "y_max":           round(y_max, 2),
            # Asks — editorial content; merged by generate.py from editorial/arr_walk.yaml
            "asks": [],
        })

    # ── Country butterfly ─────────────────────────────────────────────────────
    COUNTRY_CFG = [
        {"key": "colombia",            "team": "CO", "name": "Colombia",         "flag": "🇨🇴"},
        {"key": "mexico",              "team": "MX", "name": "México",           "flag": "🇲🇽"},
        {"key": "republicaDominicana", "team": "DR", "name": "Rep. Dominicana",  "flag": "🇩🇴"},
        {"key": "costaRica",           "team": "CR", "name": "Costa Rica",       "flag": "🇨🇷"},
    ]

    # Build per-country time series from country_raw: month → team → seg → metrics
    def _country_ts(team, seg, key, months=12):
        """Return list of values for the last `months` months (chronological)."""
        recent = sorted(country_raw.keys())[-months:]
        return [country_raw.get(m, {}).get(team, {}).get(seg, {}).get(key, 0) for m in recent]

    def _country_m(team, seg, m=latest_m):
        return country_raw.get(m, {}).get(team, {}).get(seg, {})

    def _country_pm(team, seg):
        return country_raw.get(prev_m, {}).get(team, {}).get(seg, {})

    def _country_pym(team, seg):
        return country_raw.get(prev_yr, {}).get(team, {}).get(seg, {})

    CORE_COLOR = "#534AB7"
    LITE_COLOR = "#1D9E75"

    # ── Payback por país desde RS (bi_strategic.payback_cohort_results) — serie completa ──
    # payback_by_country: {country_key: {seg: {month: val}}}
    payback_by_country = {}
    for (_typ, _seg), _months in load_payback().items():
        if _typ != "Todos":
            payback_by_country.setdefault(_typ, {})[_seg] = _months

    # Q months para lógica de cierre de Q en países
    _cur_q_ms  = next((ms for _, ms in QUARTERS if latest_m in ms), [latest_m])
    _prev_q_ms = next((QUARTERS[i-1][1] for i, (_, ms) in enumerate(QUARTERS)
                       if latest_m in ms and i > 0), [latest_m])
    # Mismo Q del año anterior (YoY para Q)
    _cur_q_ms_py = [f"{int(m[:4])-1}{m[4:]}" for m in _cur_q_ms]

    countries = []
    for cfg in COUNTRY_CFG:
        tm  = cfg["team"]   # display code: CO/MX/DR/CR
        key = cfg["key"]    # lookup key in country_raw: colombia/mexico/...

        # Skip countries with no data
        if not country_raw.get(latest_m, {}).get(key):
            continue

        def _val_cm(seg, k=key):  return _country_m(k, seg)
        def _val_pm(seg, k=key):  return _country_pm(k, seg)
        def _val_pym(seg, k=key): return _country_pym(k, seg)

        def _seg_kpi(seg, color):
            cur  = _val_cm(seg)
            prev = _val_pm(seg)
            py   = _val_pym(seg)
            arr_cur  = cur.get("mrr_eop", 0) * 12
            arr_prev = prev.get("mrr_eop", 0) * 12
            arr_py   = py.get("mrr_eop", 0) * 12
            mom_s, mom_p = _pct_delta(arr_cur, arr_prev)
            yoy_s, yoy_p = _pct_delta(arr_cur, arr_py)
            return {
                "arr":           _fm(arr_cur),
                "arr_mom":       mom_s,
                "arr_mom_positive": mom_p,
                "arr_yoy":       yoy_s,
                "arr_yoy_positive": yoy_p,
            }

        def _butterfly_row(metric_name, key_fn, fmt_fn, color_c, color_l, neg_is_bad=True):
            def _side(seg, color, neg_is_bad=neg_is_bad):
                cur_v  = key_fn(_val_cm(seg))
                prev_v = key_fn(_val_pm(seg))
                py_v   = key_fn(_val_pym(seg))
                mom_s, mom_p = _pct_delta(cur_v, prev_v)
                yoy_s, yoy_p = _pct_delta(cur_v, py_v)
                ts    = _country_ts(tm, seg, key_fn.__name__ if hasattr(key_fn,'__name__') else "mrr_eop", 12)
                return {
                    "val":          fmt_fn(cur_v),
                    "val_negative": (cur_v < 0) if neg_is_bad else False,
                    "mom":          mom_s,
                    "mom_positive": mom_p,
                    "yoy":          yoy_s,
                    "yoy_positive": yoy_p,
                    "sparkline_svg": _sparkline(ts, color),
                }
            return {
                "metric_name": metric_name,
                "core":        _side("Core", color_c),
                "lite":        _side("Lite", color_l),
            }

        _recent12 = sorted(country_raw.keys())[-12:]

        def _cd(seg, m):
            return country_raw.get(m, {}).get(key, {}).get(seg, {})

        def _row(name, fn, fmt):
            """Row where fn(month_dict) gives the value."""
            def _side(seg, color):
                v     = fn(_val_cm(seg))
                v_pm  = fn(_val_pm(seg))
                v_py  = fn(_val_pym(seg))
                mom_s, mom_p = _pct_delta(v, v_pm)
                yoy_s, yoy_p = _pct_delta(v, v_py)
                return {
                    "val": fmt(v), "val_negative": v < 0,
                    "mom": mom_s, "mom_positive": mom_p,
                    "yoy": yoy_s, "yoy_positive": yoy_p,
                    "sparkline_svg": _sparkline([fn(_cd(seg, m)) for m in _recent12], color),
                }
            return {"metric_name": name, "core": _side("Core", CORE_COLOR), "lite": _side("Lite", LITE_COLOR)}

        def _row2(name, fn, fmt):
            """Row where fn(seg, m) gives the value — for metrics needing two months."""
            def _side(seg, color):
                v     = fn(seg, latest_m)
                v_pm  = fn(seg, prev_m)
                v_py  = fn(seg, prev_yr)
                mom_s, mom_p = _pct_delta(v, v_pm)
                yoy_s, yoy_p = _pct_delta(v, v_py)
                return {
                    "val": fmt(v), "val_negative": v < 0,
                    "mom": mom_s, "mom_positive": mom_p,
                    "yoy": yoy_s, "yoy_positive": yoy_p,
                    "sparkline_svg": _sparkline([fn(seg, m) for m in _recent12], color),
                }
            return {"metric_name": name, "core": _side("Core", CORE_COLOR), "lite": _side("Lite", LITE_COLOR)}

        def _na_row(name):
            _ns = {"val": "N/A", "val_negative": False, "mom": "—", "mom_positive": True,
                   "yoy": "—", "yoy_positive": True, "sparkline_svg": ""}
            return {"metric_name": name, "core": dict(_ns), "lite": dict(_ns)}

        # Net New ARR: mes = EoP - BoP del mes; Q = EoP último mes Q - BoP primer mes Q
        def _net_new_arr(seg, m):
            m_prev = _prev_m(m)
            return (_cd(seg, m).get("mrr_eop", 0) - _cd(seg, m_prev).get("mrr_eop", 0)) * 12

        def _net_new_arr_q(seg, q_ms):
            eop = _cd(seg, q_ms[-1]).get("mrr_eop", 0)
            bop = _cd(seg, _prev_m(q_ms[0])).get("mrr_eop", 0)
            return (eop - bop) * 12

        # Logos Growth: mes = EoP - BoP del mes; Q = EoP último mes Q - BoP primer mes Q
        def _logos_growth(seg, m):
            return _cd(seg, m).get("logos_eop", 0) - _cd(seg, _prev_m(m)).get("logos_eop", 0)

        def _logos_growth_q(seg, q_ms):
            return _cd(seg, q_ms[-1]).get("logos_eop", 0) - _cd(seg, _prev_m(q_ms[0])).get("logos_eop", 0)

        # ARPA = ARR EoP / Logos EoP
        def _arpa(seg, m):
            l = _cd(seg, m).get("logos_eop", 0)
            return _cd(seg, m).get("mrr_eop", 0) / l if l else 0

        # Churn Rate % mensual = (CHURN - REACTIVATED) / BoP * 100
        _sc_local = sc or {}
        def _churn_rate(seg, m, _k=key):
            _rc_sc = (_sc_local.get("retention_churn") or {}).get("by_seg_country", {})
            _rd = _rc_sc.get(m, {}).get(_k, {}).get(seg)
            if _rd and _rd["bop"] > 0:
                return max(_rd["churned"] - _rd["reactivated"], 0) / _rd["bop"] * 100
            bop   = _cd(seg, _prev_m(m)).get("logos_eop", 0)
            churn = _cd(seg, m).get("logos_churn", 0)
            react = _cd(seg, m).get("logos_react", 0)
            return (max(churn - react, 0) / bop * 100) if bop else 0

        # ── Helpers Q-aware (solo activos cuando is_quarter_end) ──────────────
        def _q_sum_field(seg, field, q_ms):
            return sum(_cd(seg, m).get(field, 0) for m in q_ms)

        def _q_churn_avg(seg, q_ms):
            rates = [_churn_rate(seg, m) for m in q_ms]
            valid = [r for r in rates if r > 0]
            return sum(valid) / len(valid) if valid else 0

        def _row_q(name, month_fn, q_field, fmt):
            """Row Q-aware: suma del Q cuando is_quarter_end, mes actual si no."""
            def _side(seg, color):
                if is_quarter_end:
                    v     = _q_sum_field(seg, q_field, _cur_q_ms)
                    v_pm  = _q_sum_field(seg, q_field, _prev_q_ms)
                    v_py  = _q_sum_field(seg, q_field, _cur_q_ms_py)
                else:
                    v     = month_fn(_val_cm(seg))
                    v_pm  = month_fn(_val_pm(seg))
                    v_py  = month_fn(_val_pym(seg))
                mom_s, mom_p = _pct_delta(v, v_pm)
                yoy_s, yoy_p = _pct_delta(v, v_py)
                return {
                    "val": fmt(v), "val_negative": v < 0,
                    "mom": mom_s, "mom_positive": mom_p,
                    "yoy": yoy_s, "yoy_positive": yoy_p,
                    "sparkline_svg": _sparkline([month_fn(_cd(seg, m)) for m in _recent12], color),
                }
            return {"metric_name": name, "core": _side("Core", CORE_COLOR), "lite": _side("Lite", LITE_COLOR)}

        def _churn_row_q(name, fmt):
            """Churn Rate Q-aware: promedio de tasas del Q."""
            def _side(seg, color):
                if is_quarter_end:
                    v    = _q_churn_avg(seg, _cur_q_ms)
                    v_pm = _q_churn_avg(seg, _prev_q_ms)
                    v_py = _q_churn_avg(seg, _cur_q_ms_py)
                else:
                    v    = _churn_rate(seg, latest_m)
                    v_pm = _churn_rate(seg, prev_m)
                    v_py = _churn_rate(seg, prev_yr)
                mom_s, mom_p = _pct_delta(v, v_pm)
                yoy_s, yoy_p = _pct_delta(v, v_py)
                return {
                    "val": fmt(v), "val_negative": v < 0,
                    "mom": mom_s, "mom_positive": mom_p,
                    "yoy": yoy_s, "yoy_positive": yoy_p,
                    "sparkline_svg": _sparkline([_churn_rate(seg, m) for m in _recent12], color),
                }
            return {"metric_name": name, "core": _side("Core", CORE_COLOR), "lite": _side("Lite", LITE_COLOR)}

        def _inv_row_q(name):
            """Investment Q-aware: suma del Q."""
            def _side(seg, color):
                if is_quarter_end:
                    v    = sum((_inv_v(seg, m) or 0) for m in _cur_q_ms)
                    v_pm = sum((_inv_v(seg, m) or 0) for m in _prev_q_ms)
                    v_py = sum((_inv_v(seg, m) or 0) for m in _cur_q_ms_py)
                else:
                    v    = _inv_v(seg, latest_m)
                    v_pm = _inv_v(seg, prev_m)
                    v_py = _inv_v(seg, prev_yr)
                if v is None:
                    return _na_side()
                mom_s, mom_p = _pct_delta(v, v_pm) if v_pm is not None else ("—", True)
                yoy_s, yoy_p = _pct_delta(v, v_py) if v_py is not None else ("—", True)
                ts = [_inv_v(seg, m) or 0 for m in _recent12]
                return {"val": _fm(v), "val_negative": False,
                        "mom": mom_s, "mom_positive": mom_p,
                        "yoy": yoy_s, "yoy_positive": yoy_p,
                        "sparkline_svg": _sparkline(ts, color)}
            return {"metric_name": name, "core": _side("Core", CORE_COLOR), "lite": _side("Lite", LITE_COLOR)}

        def _cac_row_q(name):
            """CAC Q-aware: Investment_Q / New Logos_Q."""
            def _side(seg, color):
                if is_quarter_end:
                    inv  = sum((_inv_v(seg, m) or 0) for m in _cur_q_ms)
                    nl   = _q_sum_field(seg, "logos_new", _cur_q_ms)
                    v    = inv / nl if nl > 0 else None
                    inv_p = sum((_inv_v(seg, m) or 0) for m in _prev_q_ms)
                    nl_p  = _q_sum_field(seg, "logos_new", _prev_q_ms)
                    v_pm  = inv_p / nl_p if nl_p > 0 else None
                    inv_py = sum((_inv_v(seg, m) or 0) for m in _cur_q_ms_py)
                    nl_py  = _q_sum_field(seg, "logos_new", _cur_q_ms_py)
                    v_py   = inv_py / nl_py if nl_py > 0 else None
                else:
                    v    = _cac_v(seg, latest_m)
                    v_pm = _cac_v(seg, prev_m)
                    v_py = _cac_v(seg, prev_yr)
                if v is None:
                    return _na_side()
                mom_s, mom_p = _pct_delta(v, v_pm) if v_pm is not None else ("—", True)
                yoy_s, yoy_p = _pct_delta(v, v_py) if v_py is not None else ("—", True)
                ts = [(_cac_v(seg, m) or 0) for m in _recent12]
                return {"val": f"${v:,.0f}", "val_negative": False,
                        "mom": mom_s, "mom_positive": mom_p,
                        "yoy": yoy_s, "yoy_positive": yoy_p,
                        "sparkline_svg": _sparkline(ts, color)}
            return {"metric_name": name, "core": _side("Core", CORE_COLOR), "lite": _side("Lite", LITE_COLOR)}

        # Payback por país desde CSV — serie de tiempo
        def _pb_v(seg, m):
            return payback_by_country.get(key, {}).get(seg, {}).get(m)

        def _payback_row(name):
            def _pb_avg(seg, q_ms):
                vals = [_pb_v(seg, m) for m in q_ms if _pb_v(seg, m) is not None]
                return sum(vals) / len(vals) if vals else None
            def _side(seg, color):
                if is_quarter_end:
                    v    = _pb_avg(seg, _cur_q_ms)
                    v_pm = _pb_avg(seg, _prev_q_ms)
                    v_py = _pb_avg(seg, _cur_q_ms_py)
                else:
                    v    = _pb_v(seg, latest_m)
                    v_pm = _pb_v(seg, prev_m)
                    v_py = _pb_v(seg, prev_yr)
                if v is None:
                    return _na_side()
                mom_s, mom_p = _pct_delta(v, v_pm) if v_pm is not None else ("—", True)
                yoy_s, yoy_p = _pct_delta(v, v_py) if v_py is not None else ("—", True)
                ts = [_pb_v(seg, m) or 0 for m in _recent12]
                return {"val": f"{v:.1f} mo", "val_negative": False,
                        "mom": mom_s, "mom_positive": mom_p,
                        "yoy": yoy_s, "yoy_positive": yoy_p,
                        "sparkline_svg": _sparkline(ts, color)}
            return {"metric_name": name, "core": _side("Core", CORE_COLOR), "lite": _side("Lite", LITE_COLOR)}

        # Investment y CAC — series de tiempo {seg: {month: usd}}
        inv_ts = (investment or {}).get(key, {})

        def _inv_v(seg, m):
            rec = inv_ts.get(seg, {}).get(m)
            return rec["total"] if rec else None

        def _cac_v(seg, m):
            inv = _inv_v(seg, m)
            nl  = _cd(seg, m).get("logos_new", 0)
            return inv / nl if (inv is not None and nl > 0) else None

        def _na_side():
            return {"val": "N/A", "val_negative": False, "mom": "—",
                    "mom_positive": True, "yoy": "—", "yoy_positive": True,
                    "sparkline_svg": ""}

        def _ts_side(seg, color, val_fn, fmt_fn, neg_is_bad=False):
            v    = val_fn(seg, latest_m)
            v_pm = val_fn(seg, prev_m)
            v_py = val_fn(seg, prev_yr)
            if v is None:
                return _na_side()
            mom_s, mom_p = _pct_delta(v, v_pm) if v_pm is not None else ("—", True)
            yoy_s, yoy_p = _pct_delta(v, v_py) if v_py is not None else ("—", True)
            ts = [val_fn(seg, m) or 0 for m in _recent12]
            return {"val": fmt_fn(v), "val_negative": (v < 0) if neg_is_bad else False,
                    "mom": mom_s, "mom_positive": mom_p,
                    "yoy": yoy_s, "yoy_positive": yoy_p,
                    "sparkline_svg": _sparkline(ts, color)}

        def _inv_row(name):
            return {"metric_name": name,
                    "core": _ts_side("Core", CORE_COLOR, _inv_v, _fm),
                    "lite": _ts_side("Lite", LITE_COLOR, _inv_v, _fm)}

        def _cac_row(name):
            return {"metric_name": name,
                    "core": _ts_side("Core", CORE_COLOR, _cac_v, lambda v: f"${v:,.0f}"),
                    "lite": _ts_side("Lite", LITE_COLOR, _cac_v, lambda v: f"${v:,.0f}")}

        # Net New ARR Q-aware
        def _net_new_arr_row(name):
            def _side(seg, color):
                if is_quarter_end:
                    v    = _net_new_arr_q(seg, _cur_q_ms)
                    v_pm = _net_new_arr_q(seg, _prev_q_ms)
                    v_py = _net_new_arr_q(seg, _cur_q_ms_py)
                else:
                    v    = _net_new_arr(seg, latest_m)
                    v_pm = _net_new_arr(seg, prev_m)
                    v_py = _net_new_arr(seg, prev_yr)
                mom_s, mom_p = _pct_delta(v, v_pm)
                yoy_s, yoy_p = _pct_delta(v, v_py)
                return {"val": _fm(v), "val_negative": v < 0,
                        "mom": mom_s, "mom_positive": mom_p,
                        "yoy": yoy_s, "yoy_positive": yoy_p,
                        "sparkline_svg": _sparkline([_net_new_arr(seg, m) for m in _recent12], color)}
            return {"metric_name": name, "core": _side("Core", CORE_COLOR), "lite": _side("Lite", LITE_COLOR)}

        # Logos Growth Q-aware
        def _logos_growth_row(name):
            fmt = lambda v: f"+{int(v):,}" if v >= 0 else f"({int(abs(v)):,})"
            def _side(seg, color):
                if is_quarter_end:
                    v    = _logos_growth_q(seg, _cur_q_ms)
                    v_pm = _logos_growth_q(seg, _prev_q_ms)
                    v_py = _logos_growth_q(seg, _cur_q_ms_py)
                else:
                    v    = _logos_growth(seg, latest_m)
                    v_pm = _logos_growth(seg, prev_m)
                    v_py = _logos_growth(seg, prev_yr)
                mom_s, mom_p = _pct_delta(v, v_pm)
                yoy_s, yoy_p = _pct_delta(v, v_py)
                return {"val": fmt(v), "val_negative": v < 0,
                        "mom": mom_s, "mom_positive": mom_p,
                        "yoy": yoy_s, "yoy_positive": yoy_p,
                        "sparkline_svg": _sparkline([_logos_growth(seg, m) for m in _recent12], color)}
            return {"metric_name": name, "core": _side("Core", CORE_COLOR), "lite": _side("Lite", LITE_COLOR)}

        butterfly_rows = [
            _inv_row_q("Investment"),
            _net_new_arr_row("Net New ARR"),
            _logos_growth_row("Logos Growth"),
            _row_q("New Logos",       lambda d: d.get("logos_new", 0), "logos_new", lambda v: f"{int(v):,}"),
            _row_q("New ARR",         lambda d: d.get("mrr_new", 0), "mrr_new", lambda v: f"${v*12/1e3:.0f}K"),
            _row2("ARPA",             _arpa,          lambda v: f"${v:,.0f}"),
            _cac_row_q("CAC"),
            _churn_row_q("Churn Rate",                lambda v: f"{v:.1f}%"),
            _payback_row("Payback"),
        ]

        countries.append({
            "team":         tm,
            "name":         cfg["name"],
            "flag":         cfg["flag"],
            "action_title": f"{cfg['flag']} {cfg['name']} — Core vs Lite Performance",
            "core":         _seg_kpi("Core", CORE_COLOR),
            "lite":         _seg_kpi("Lite", LITE_COLOR),
            "butterfly_rows": butterfly_rows,
        })

    # ── Global Country Performance (TODOS los países — usa segs_raw global) ──
    # segs_raw["Core"/"Lite"][m] = datos globales de fact_customers_mrr sin filtro de país

    def _graw(seg, m):
        return segs_raw.get(seg, {}).get(m, {})

    def _gm(seg):   return _graw(seg, latest_m)
    def _gpm(seg):  return _graw(seg, prev_m)
    def _gpym(seg): return _graw(seg, prev_yr)

    def _g_net_new_arr(seg, m):
        return (_graw(seg, m).get("mrr_eop", 0) - _graw(seg, _prev_m(m)).get("mrr_eop", 0)) * 12

    def _g_net_new_arr_q(seg, q_ms):
        return (_graw(seg, q_ms[-1]).get("mrr_eop", 0) - _graw(seg, _prev_m(q_ms[0])).get("mrr_eop", 0)) * 12

    def _g_logos_growth(seg, m):
        return _graw(seg, m).get("logos_eop", 0) - _graw(seg, _prev_m(m)).get("logos_eop", 0)

    def _g_logos_growth_q(seg, q_ms):
        return _graw(seg, q_ms[-1]).get("logos_eop", 0) - _graw(seg, _prev_m(q_ms[0])).get("logos_eop", 0)

    def _g_arpa(seg, m):
        d = _graw(seg, m)
        l = d.get("logos_eop", 0)
        return d.get("mrr_eop", 0) / l if l else 0

    def _g_new_arpa(seg, m):
        d  = _graw(seg, m)
        nl = d.get("logos_new", 0)
        new_mrr = d.get("mrr_new_base_t0", 0) + d.get("mrr_new_cross_t0", 0)
        return new_mrr / nl if nl > 0 else 0

    def _g_churn(seg, m):
        bop   = _graw(seg, _prev_m(m)).get("logos_eop", 0)
        churn = _graw(seg, m).get("logos_churn", 0)
        react = _graw(seg, m).get("logos_react", 0)
        return (max(churn - react, 0) / bop * 100) if bop else 0

    def _g_churn_avg_q(seg, q_ms):
        rates = [_g_churn(seg, m) for m in q_ms]
        valid = [r for r in rates if r > 0]
        return sum(valid) / len(valid) if valid else 0

    def _g_q_sum(seg, field, q_ms):
        return sum(_graw(seg, m).get(field, 0) for m in q_ms)

    def _g_inv(seg, m, field="total"):
        vals = [country_inv.get(seg, {}).get(m, {}).get(field) for country_inv in investment.values()]
        valid = [v for v in vals if v is not None]
        return sum(valid) if valid else None

    def _g_inv_paid(seg, m):   return _g_inv(seg, m, "paid")
    def _g_inv_people(seg, m): return _g_inv(seg, m, "people")
    def _g_inv_other(seg, m):  return _g_inv(seg, m, "other")

    def _g_cac(seg, m):
        inv = _g_inv(seg, m)
        nl  = _graw(seg, m).get("logos_new", 0)
        return inv / nl if (inv is not None and nl > 0) else None

    _g_na = {"val": "N/A", "val_negative": False, "mom": "—", "mom_positive": True,
             "yoy": "—", "yoy_positive": True, "sparkline_svg": ""}

    def _g_side(seg, v, v_pm, v_py, fmt_fn, neg_is_bad=True):
        if v is None:
            return dict(_g_na)
        mom_s, mom_p = _pct_delta(v, v_pm) if v_pm is not None else ("—", True)
        yoy_s, yoy_p = _pct_delta(v, v_py) if v_py is not None else ("—", True)
        return {"val": fmt_fn(v), "val_negative": (v < 0) if neg_is_bad else False,
                "mom": mom_s, "mom_positive": mom_p,
                "yoy": yoy_s, "yoy_positive": yoy_p, "sparkline_svg": ""}

    def _g_make(name, core_side, lite_side):
        return {"metric_name": name, "core": core_side, "lite": lite_side}

    def _g_inv_row_q():
        def _s(seg):
            if is_quarter_end:
                v, vp, vy = (sum((_g_inv(seg,m) or 0) for m in ms) for ms in [_cur_q_ms, _prev_q_ms, _cur_q_ms_py])
            else:
                v, vp, vy = _g_inv(seg,latest_m), _g_inv(seg,prev_m), _g_inv(seg,prev_yr)
            return _g_side(seg, v, vp, vy, _fm, neg_is_bad=False)
        return _g_make("Investment", _s("Core"), _s("Lite"))

    def _g_nna_row():
        def _s(seg):
            if is_quarter_end:
                v, vp, vy = _g_net_new_arr_q(seg,_cur_q_ms), _g_net_new_arr_q(seg,_prev_q_ms), _g_net_new_arr_q(seg,_cur_q_ms_py)
            else:
                v, vp, vy = _g_net_new_arr(seg,latest_m), _g_net_new_arr(seg,prev_m), _g_net_new_arr(seg,prev_yr)
            return _g_side(seg, v, vp, vy, _fm, neg_is_bad=True)
        return _g_make("Net New ARR", _s("Core"), _s("Lite"))

    def _g_logos_growth_row():
        fmt = lambda v: f"+{int(v):,}" if v >= 0 else f"({int(abs(v)):,})"
        def _s(seg):
            if is_quarter_end:
                v, vp, vy = _g_logos_growth_q(seg,_cur_q_ms), _g_logos_growth_q(seg,_prev_q_ms), _g_logos_growth_q(seg,_cur_q_ms_py)
            else:
                v, vp, vy = _g_logos_growth(seg,latest_m), _g_logos_growth(seg,prev_m), _g_logos_growth(seg,prev_yr)
            return _g_side(seg, v, vp, vy, fmt, neg_is_bad=True)
        return _g_make("Logos Growth", _s("Core"), _s("Lite"))

    def _g_row_q(name, m_fn, q_field, fmt_fn):
        def _s(seg):
            if is_quarter_end:
                v, vp, vy = (_g_q_sum(seg, q_field, ms) for ms in [_cur_q_ms, _prev_q_ms, _cur_q_ms_py])
            else:
                v, vp, vy = m_fn(_gm(seg)), m_fn(_gpm(seg)), m_fn(_gpym(seg))
            return _g_side(seg, v, vp, vy, fmt_fn, neg_is_bad=True)
        return _g_make(name, _s("Core"), _s("Lite"))

    def _g_arpa_row():
        def _s(seg):
            v, vp, vy = _g_arpa(seg,latest_m), _g_arpa(seg,prev_m), _g_arpa(seg,prev_yr)
            return _g_side(seg, v, vp, vy, lambda v: f"${v:,.0f}", neg_is_bad=False)
        row = _g_make("ARPA", _s("Core"), _s("Lite"))
        _na_core = _g_new_arpa("Core", latest_m)
        _na_lite = _g_new_arpa("Lite", latest_m)
        row["arpa_new_core"] = f"${_na_core:,.0f}" if _na_core else "N/A"
        row["arpa_new_lite"] = f"${_na_lite:,.0f}" if _na_lite else "N/A"
        # MoM / YoY para ARPA New Logos
        for side, curr in [("core", _na_core), ("lite", _na_lite)]:
            pm = _g_new_arpa("Core" if side == "core" else "Lite", prev_m)
            py = _g_new_arpa("Core" if side == "core" else "Lite", prev_yr)
            ms, mp = _pct_delta(curr, pm) if (curr and pm) else ("—", True)
            ys, yp = _pct_delta(curr, py) if (curr and py) else ("—", True)
            row[f"arpa_new_{side}_mom"] = ms
            row[f"arpa_new_{side}_mom_positive"] = mp
            row[f"arpa_new_{side}_yoy"] = ys
            row[f"arpa_new_{side}_yoy_positive"] = yp
        return row

    def _g_cac_row_q():
        def _s(seg):
            if is_quarter_end:
                def _cac_q(ms):
                    inv = sum((_g_inv(seg,m) or 0) for m in ms)
                    nl  = _g_q_sum(seg, "logos_new", ms)
                    return inv / nl if nl > 0 else None
                v, vp, vy = _cac_q(_cur_q_ms), _cac_q(_prev_q_ms), _cac_q(_cur_q_ms_py)
            else:
                v, vp, vy = _g_cac(seg,latest_m), _g_cac(seg,prev_m), _g_cac(seg,prev_yr)
            return _g_side(seg, v, vp, vy, lambda v: f"${v:,.0f}", neg_is_bad=False)
        return _g_make("CAC", _s("Core"), _s("Lite"))

    def _g_churn_row_q():
        def _s(seg):
            if is_quarter_end:
                v, vp, vy = _g_churn_avg_q(seg,_cur_q_ms), _g_churn_avg_q(seg,_prev_q_ms), _g_churn_avg_q(seg,_cur_q_ms_py)
            else:
                v, vp, vy = _g_churn(seg,latest_m), _g_churn(seg,prev_m), _g_churn(seg,prev_yr)
            return _g_side(seg, v, vp, vy, lambda v: f"{v:.1f}%", neg_is_bad=False)
        return _g_make("Churn Rate", _s("Core"), _s("Lite"))

    def _g_payback_row():
        _gpb = {seg: load_payback().get(("Todos", seg), {}) for seg in ("Core", "Lite")}
        def _g_pb(seg, m): return _gpb.get(seg, {}).get(m)
        def _g_pb_avg(seg, q_ms):
            vals = [_g_pb(seg, m) for m in q_ms if _g_pb(seg, m) is not None]
            return sum(vals)/len(vals) if vals else None
        def _s(seg):
            if is_quarter_end:
                v, vp, vy = _g_pb_avg(seg,_cur_q_ms), _g_pb_avg(seg,_prev_q_ms), _g_pb_avg(seg,_cur_q_ms_py)
            else:
                v, vp, vy = _g_pb(seg,latest_m), _g_pb(seg,prev_m), _g_pb(seg,prev_yr)
            return _g_side(seg, v, vp, vy, lambda v: f"{v:.1f} mo", neg_is_bad=False)
        return _g_make("Payback", _s("Core"), _s("Lite"))

    def _g_seg_kpi(seg):
        cur, prv, py = _gm(seg), _gpm(seg), _gpym(seg)
        ac, ap, ayp = cur.get("mrr_eop",0)*12, prv.get("mrr_eop",0)*12, py.get("mrr_eop",0)*12
        ms, mp = _pct_delta(ac, ap)
        ys, yp = _pct_delta(ac, ayp)
        return {"arr": _fm(ac), "arr_mom": ms, "arr_mom_positive": mp,
                "arr_yoy": ys, "arr_yoy_positive": yp}

    # ── Core vs Lite split percentages for summary slide ────────────────────────
    _core_arr_raw  = _gm("Core").get("mrr_eop", 0) * 12
    _lite_arr_raw  = _gm("Lite").get("mrr_eop", 0) * 12
    _total_arr_spl = _core_arr_raw + _lite_arr_raw
    _core_arr_pct  = round(_core_arr_raw / _total_arr_spl * 100) if _total_arr_spl else 0

    if is_quarter_end:
        _core_new_mrr_raw = sum(_graw("Core", m).get("mrr_new_base_t0", 0) + _graw("Core", m).get("mrr_new_cross_t0", 0) for m in _cur_q_ms)
        _lite_new_mrr_raw = sum(_graw("Lite", m).get("mrr_new_base_t0", 0) + _graw("Lite", m).get("mrr_new_cross_t0", 0) for m in _cur_q_ms)
    else:
        _core_new_mrr_raw = _gm("Core").get("mrr_new_base_t0", 0) + _gm("Core").get("mrr_new_cross_t0", 0)
        _lite_new_mrr_raw = _gm("Lite").get("mrr_new_base_t0", 0) + _gm("Lite").get("mrr_new_cross_t0", 0)
    _total_new_mrr_spl  = _core_new_mrr_raw + _lite_new_mrr_raw
    _core_new_mrr_pct   = round(_core_new_mrr_raw / _total_new_mrr_spl * 100) if _total_new_mrr_spl else 0

    global_country = {
        "action_title": "🌎 Global — Core vs Lite Performance",
        "core": _g_seg_kpi("Core"),
        "lite": _g_seg_kpi("Lite"),
        "butterfly_rows": [
            _g_inv_row_q(),
            _g_nna_row(),
            _g_logos_growth_row(),
            _g_row_q("New Logos", lambda d: d.get("logos_new",0), "logos_new", lambda v: f"{int(v):,}"),
            _g_row_q("New ARR", lambda d: d.get("mrr_new_base_t0",0)+d.get("mrr_new_cross_t0",0), "mrr_new_base_t0", lambda v: f"${v*12/1e3:.0f}K"),
            _g_arpa_row(),
            _g_cac_row_q(),
            _g_churn_row_q(),
            _g_payback_row(),
        ],
    }

    # ── Alanube placeholder (manual data until RS source is defined) ──────────
    alanube = {
        "arr_bop":         "N/A",
        "arr_eop":         "N/A",
        "arr_delta_display": "N/A",
        "new_accounts":    "N/A",
        "issuing":         "N/A",
        "onboarding":      "N/A",
        "wf_bop_accounts": "N/A",
        "wf_new_arr":      "N/A",
        "wf_new_accounts": "N/A",
        "wf_new_note":     "Pendiente de fuente RS",
        "wf_churn_arr":    "N/A",
        "wf_churn_accounts": "N/A",
        "wf_churn_note":   "Pendiente de fuente RS",
        "wf_upside_arr":   "N/A",
        "wf_upside_note":  "Cuentas en onboarding",
        "wf_eop_accounts": "N/A",
    }

    # ── Chart period label
    first_q = next((lbl for lbl, _ in QUARTERS if lbl in
                    (seg_metrics.get("Core",{}).get("quarters",{}) or
                     seg_metrics.get("all",{}).get("quarters",{}))), "?")
    arr_chart_period_label = f"{first_q} – {latest_q_lbl}"

    # ── Alanube ARR — sumar automáticamente desde bi_alanube.fact_alanube_arr_walk (RS)
    # Carga los valores de Alanube para el mes actual, mes anterior y año anterior.
    # Esto evita tener que editar metrics.yaml manualmente después de cada fetch.
    _alanube_spot: dict = load_alanube_arr()

    def _alanube(month_iso: str) -> float:
        """Retorna ARR de Alanube en USD para el mes dado (usa el último conocido si no existe)."""
        if month_iso in _alanube_spot:
            return float(_alanube_spot[month_iso])
        # fallback: último mes disponible (para meses futuros sin dato aún)
        if _alanube_spot:
            return float(_alanube_spot[max(_alanube_spot.keys())])
        return 0.0

    def _prev_month(m: str) -> str:
        y, mo = int(m[:4]), int(m[5:])
        mo -= 1
        if mo == 0: y -= 1; mo = 12
        return f"{y:04d}-{mo:02d}"

    def _year_ago(m: str) -> str:
        return f"{int(m[:4])-1:04d}-{m[5:]}"

    _al_cur  = _alanube(latest_m)
    _al_prev = _alanube(_prev_month(latest_m))
    _al_py   = _alanube(_year_ago(latest_m))

    _alegra_cur  = all_m.get("a_eop", 0)
    _alegra_prev = all_m_pv.get("a_eop", 0)
    _alegra_py   = all_m_py.get("a_eop", 0)

    _total_cur  = _alegra_cur  + _al_cur
    _total_prev = _alegra_prev + _al_prev
    _total_py   = _alegra_py   + _al_py

    arr_mom_str, arr_mom_pos = _pct_delta(_total_cur, _total_prev)
    arr_yoy_str, arr_yoy_pos = _pct_delta(_total_cur, _total_py)

    # ── Assemble final structure
    out = {
        # --- Config (also needed by templates)
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "cutoff_month":  cutoff,

        # --- Slide 1 / Key Summary global KPIs (Alegra + Alanube)
        "arr_total":           _fm(_total_cur),
        "is_quarter_end":      is_quarter_end,
        "prev_quarter_label":  prev_q_label,

        "arr_mom":             arr_mom_str,
        "arr_mom_positive":    arr_mom_pos,
        "arr_qoq":             arr_qoq_str,
        "arr_qoq_positive":    arr_qoq_pos,
        "arr_vs_budget":       "N/A",
        "arr_vs_budget_positive": True,
        "arr_yoy":             arr_yoy_str,
        "arr_yoy_positive":    arr_yoy_pos,
        "arr_core_lite_split":     f"Core {_core_arr_pct}% · Lite {100 - _core_arr_pct}%",
        "new_mrr_core_lite_split": f"Core {_core_new_mrr_pct}% · Lite {100 - _core_new_mrr_pct}%",
        "new_mrr_core_fmt":        _fm(_core_new_mrr_raw),
        "new_mrr_lite_fmt":        _fm(_lite_new_mrr_raw),

        "new_mrr":                    _fm(all_q.get("a_new", 0) / 12) if is_quarter_end else _fm(all_m.get("a_new", 0) / 12),  # Q=suma 3 meses, MoM=mes actual
        "new_mrr_mom":                new_mrr_mom_str,
        "new_mrr_mom_positive":       new_mrr_mom_pos,
        "new_mrr_qoq":                new_mrr_qoq_str,
        "new_mrr_qoq_positive":       new_mrr_qoq_pos,
        "new_mrr_vs_budget":          "N/A",
        "new_mrr_vs_budget_positive": True,
        "new_mrr_yoy":                new_mrr_yoy_str,
        "new_mrr_yoy_positive":       new_mrr_yoy_pos,

        "new_logos":                    _fl(all_q.get("l_new", 0)) if is_quarter_end else _fl(all_m.get("l_new", 0)),  # Q=suma 3 meses
        "new_logos_mom":                new_logos_mom_str,
        "new_logos_mom_positive":       new_logos_mom_pos,
        "new_logos_qoq":                new_logos_qoq_str,
        "new_logos_qoq_positive":       new_logos_qoq_pos,
        "new_logos_vs_budget":          "N/A",
        "new_logos_yoy":                new_logos_yoy_str,
        "new_logos_yoy_positive":       new_logos_yoy_pos,

        # --- Financial KPIs (from Sheets — placeholders)
        "net_revenue":                  "N/A",
        "net_revenue_mom":              "N/A",
        "net_revenue_mom_positive":     True,
        "net_revenue_vs_budget":        "N/A",
        "net_revenue_vs_budget_positive": True,
        "net_revenue_yoy":              "N/A",
        "net_revenue_yoy_positive":     True,

        "gross_margin":                  "N/A",
        "gross_margin_mom":              "N/A",
        "gross_margin_vs_budget":        "N/A",
        "gross_margin_vs_budget_positive": True,
        "gross_margin_yoy":              "N/A",
        "gross_margin_yoy_positive":     True,

        "ebitda_margin":                  "N/A",
        "ebitda_margin_mom":              "N/A",
        "ebitda_margin_mom_positive":     True,
        "ebitda_margin_vs_budget":        "N/A",
        "ebitda_margin_vs_budget_positive": True,
        "ebitda_margin_yoy":              "N/A",
        "ebitda_margin_yoy_positive":     True,

        # --- Risk KPIs (Sheets for payback, RS for churn)
        "logo_churn_core":    round((_q("Core") if is_quarter_end else _mo("Core")).get("l_churn_pct", 0) * 100, 1),
        "logo_churn_lite":    round((_q("Lite") if is_quarter_end else _mo("Lite")).get("l_churn_pct", 0) * 100, 1),
        "logo_churn_global":  round((_q("all")  if is_quarter_end else all_m).get("l_churn_pct", 0) * 100, 1),
        "logo_churn_vs_budget_pp": "N/A",
        "payback_core":       "N/A",
        "payback_lite":       "N/A",
        "payback_hist":       "N/A",

        # Raw values for budget merge (removed before writing yaml)
        "_raw": {
            "arr_eop":         all_m.get("a_eop", 0),
            "new_mrr":         (all_q.get("a_new", 0) if is_quarter_end else all_m.get("a_new", 0)) / 12,
            "new_logos":       all_q.get("l_new", 0) if is_quarter_end else all_m.get("l_new", 0),
            "logo_churn_pct":  round((_q("all") if is_quarter_end else all_m).get("l_churn_pct", 0) * 100, 2),
        },

        # --- ARR Walk products (Section 03)
        "arr_chart_period_label": arr_chart_period_label,
        "arr_walk_products":      products,

        # --- Alanube (Section 03)
        "alanube": alanube,

        # --- Countries (Section 03)
        "countries": countries,
        "global_country": global_country,
    }

    # ── YTD acumulado (slide 5) ───────────────────────────────────────────────
    _cur_yr  = latest_m[:4]
    _prev_yr_int = str(int(_cur_yr) - 1)
    _ytd_cur = seg_metrics.get("all", {}).get("ytd", {}).get(_cur_yr, {})
    _ytd_py  = seg_metrics.get("all", {}).get("ytd", {}).get(_prev_yr_int, {})

    _new_mrr_ytd    = _ytd_cur.get("a_new", 0) / 12
    _new_mrr_ytd_py = _ytd_py.get("a_new",  0) / 12
    _new_l_ytd      = _ytd_cur.get("l_new", 0)
    _new_l_ytd_py   = _ytd_py.get("l_new",  0)

    out["new_mrr_ytd"]              = _fm(_new_mrr_ytd)
    out["new_mrr_ytd_yoy"], out["new_mrr_ytd_yoy_positive"] = _pct_delta(_new_mrr_ytd, _new_mrr_ytd_py)
    out["new_logos_ytd"]            = _fl(_new_l_ytd)
    out["new_logos_ytd_yoy"], out["new_logos_ytd_yoy_positive"] = _pct_delta(_new_l_ytd, _new_l_ytd_py)

    # ── Global chart arrays + QTD metrics (1_inicio) ──────────────────────────
    _all_q_data = seg_metrics.get("all", {}).get("quarters", {})
    _cqs        = [lbl for lbl, _ in QUARTERS if lbl in _all_q_data]
    _aq_cur     = _all_q_data.get(latest_q_lbl, {})
    _aq_prv_idx = max(0, next((i for i,(l,_) in enumerate(QUARTERS) if l==latest_q_lbl), 0)-1)
    _aq_prv_lbl = QUARTERS[_aq_prv_idx][0]
    _aq_prv     = _all_q_data.get(_aq_prv_lbl, {})
    _all_bym    = segs_raw.get("all", {})

    _g_new_rec  = [_all_q_data[q].get("a_new",0)/1e6 + _all_q_data[q].get("a_recov",0)/1e6 for q in _cqs]
    _g_exp      = [max(_all_q_data[q].get("a_upsell",0)/1e6, 0) for q in _cqs]
    _g_churn    = [max(_all_q_data[q].get("a_churn",0)/1e6, 0) for q in _cqs]
    _g_cont     = [max(_all_q_data[q].get("a_down",0)/1e6, 0) for q in _cqs]
    _g_nn       = [_all_q_data[q].get("a_net_new",0)/1e6 for q in _cqs]
    _g_ln       = [_all_q_data[q].get("l_new",0)+_all_q_data[q].get("l_recov",0) for q in _cqs]
    _g_lc       = [_all_q_data[q].get("l_disc",0) for q in _cqs]
    _g_ymax     = max((max(_g_new_rec+_g_exp) if _g_new_rec else 0),
                      (max(_g_churn+_g_cont)   if _g_churn   else 0)) * 1.25 or 1

    _gqc = []
    for _ql, _ms in QUARTERS[-5:]:
        if not any(m in _all_bym for m in _ms): continue
        _bop_k = _prev_m(_ms[0]); _eop_k = _ms[-1]
        _gqc.append({
            "label":    _ql,
            "bopArr":   _fm(_all_bym.get(_bop_k,{}).get("mrr_eop",0)*12),
            "bopLogos": round(_all_bym.get(_bop_k,{}).get("logos_eop",0)/1e3,2),
            "eopArr":   _fm(_all_bym.get(_eop_k,{}).get("mrr_eop",0)*12),
            "eopLogos": round(_all_bym.get(_eop_k,{}).get("logos_eop",0)/1e3,2),
        })

    out.update({
        "arr_quarters":            _cqs,
        "arr_new_rec":             _g_new_rec,
        "arr_expansion":           _g_exp,
        "arr_churn":               _g_churn,
        "arr_contraction":         _g_cont,
        "arr_net_new":             _g_nn,
        "arr_chart_y_max":         round(_g_ymax, 2),
        "logos_new":               _g_ln,
        "logos_expansion":         [0]*len(_cqs),
        "logos_churn":             _g_lc,
        "logos_contraction":       [0]*len(_cqs),
        "arr_q_cards":             _gqc,
        # QTD
        "arr_eop_qtd":             _fm(_aq_cur.get("a_eop",0)),
        "arr_qoq":                 _pct_delta(_aq_cur.get("a_eop",0), _aq_prv.get("a_eop",0))[0],
        "net_new_arr_qtd":         _fm(_aq_cur.get("a_net_new",0)),
        "net_new_arr_prev_qtd":    _fm(_aq_prv.get("a_net_new",0)),
        "net_new_arr_qoq":         _pct_delta(_aq_cur.get("a_net_new",0), _aq_prv.get("a_net_new",0))[0],
        "logos_eop_qtd":           _fl(_aq_cur.get("l_eop",0)),
        "logos_qoq":               _pct_delta(_aq_cur.get("l_eop",0), _aq_prv.get("l_eop",0))[0],
        "logos_yoy":               _pct_delta(_aq_cur.get("l_eop",0), _aq_cur.get("l_eop_py",0))[0],
        "prev_quarter_label":      _aq_prv_lbl,
        # SMB logos (global) / Accountant — desde flywheel lg_stock
        "smb_logos_eop":           round(_aq_cur.get("l_eop",0)),
        "smb_logos_yoy":           _pct_delta(_aq_cur.get("l_eop",0), _aq_cur.get("l_eop_py",0))[0],
        "smb_logos_yoy_positive":  _pct_delta(_aq_cur.get("l_eop",0), _aq_cur.get("l_eop_py",0))[1],
        "smb_logos_net_adds":      round(all_m.get("l_new",0)+all_m.get("l_recov",0)-all_m.get("l_disc",0)),
        "accountant_logos_eop":          "N/A",
        "accountant_logos_mom":          "N/A",
        "accountant_logos_mom_positive": True,
        "accountant_logos_yoy":          "N/A",
        "accountant_logos_yoy_positive": True,
        "accountant_logos_net_adds":     "N/A",
        # Churn extras
        "logo_churn_qoq":          _pct_delta(_aq_cur.get("a_churn",0), _aq_prv.get("a_churn",0))[0],
        "logo_churn_yoy":          _pct_delta(_aq_cur.get("a_churn",0), _aq_cur.get("a_eop_py",0))[0],
        "logo_churn_qtd_avg":      "N/A",
    })

    # ── ARR Walk Table (nuevo slide en 1_inicio) ──────────────────────────────
    _last5q = [lbl for lbl, _ in QUARTERS if lbl in _all_q_data][-5:]

    def _fa_abs(v):
        return _fm(v) if v != 0 else "—"

    def _fa_delta(v):
        if v == 0: return "—"
        s = f"{abs(v)/1e6:.1f}"
        return s if v > 0 else f"({s})"

    def _fl_abs(v):
        return f"{int(round(v)):,}" if v else "—"

    def _fl_delta(v):
        if v == 0: return "—"
        return f"+{int(round(v)):,}" if v > 0 else f"({int(round(abs(v))):,})"

    def _pill_pct(cur, prv, invert=False):
        """(text, is_good) para cambio porcentual entre dos valores."""
        if not prv or cur is None: return ("—", None)
        chg = (cur - prv) / abs(prv)
        pos = chg >= 0
        sign = "+" if pos else "−"
        good = pos if not invert else not pos
        return (f"{sign}{abs(chg)*100:.0f}%", good)

    def _pill_pp(cur, prv, invert=False):
        """(text, is_good) para cambio en puntos porcentuales (valores ya en fracción)."""
        if cur is None or prv is None: return ("—", None)
        diff = cur - prv
        pos = diff >= 0
        sign = "+" if pos else "−"
        good = pos if not invert else not pos
        return (f"{sign}{abs(diff)*100:.1f}pp", good)

    # Valores del año anterior para cada quarter en _last5q
    def _py_lbl(q):
        """1Q26 → 1Q25, 4Q25 → 4Q24, etc."""
        prefix, yr = q[:-2], int(q[-2:])
        return f"{prefix}{yr-1:02d}"

    def _qraw_py(key):
        return [_all_q_data.get(_py_lbl(q), {}).get(key) or 0 for q in _last5q]

    def _aw_row(label, row_type, dot, raws, fmtfn, raws_py=None, pp=False, invert=False, nv=False):
        """Construye un dict de fila para arr_walk_table. raws = lista de 5 valores numéricos."""
        cells = [fmtfn(r) for r in raws]
        pill_fn = _pill_pp if pp else _pill_pct
        # QoQ por cada quarter: cambio vs quarter anterior (primero = —)
        qoq_cells = []
        for i, r in enumerate(raws):
            if i == 0:
                qoq_cells.append(("—", None))
            else:
                qoq_cells.append(pill_fn(r, raws[i-1], invert=invert))
        # YoY por cada quarter: cambio vs mismo quarter año anterior
        yoy_cells = []
        for i, r in enumerate(raws):
            py = raws_py[i] if raws_py else None
            if py:
                yoy_cells.append(pill_fn(r, py, invert=invert))
            else:
                yoy_cells.append(("—", None))
        qoq, qoq_good = qoq_cells[-1]
        yoy, yoy_good = yoy_cells[-1]
        if raws[0] and raws[-1] is not None:
            _ytd_vs, _ytd_vs_good = pill_fn(raws[-1], raws[0], invert=invert)
        else:
            _ytd_vs, _ytd_vs_good = "—", None
        return {
            "label": label, "type": row_type, "dot": dot,
            "cells": cells,
            "qoq": qoq, "qoq_good": qoq_good,
            "yoy": yoy, "yoy_good": yoy_good,
            "qoq_cells": [{"v": v, "good": g} for v, g in qoq_cells],
            "yoy_cells": [{"v": v, "good": g} for v, g in yoy_cells],
            "ytd_prev": cells[0],
            "ytd_cur": cells[-1],
            "ytd_vs": _ytd_vs,
            "ytd_vs_good": _ytd_vs_good,
            "nv": nv,
        }

    # ── SaaS Metrics helpers (compartidos Q y M) ─────────────────────────────
    _q_months_map = {lbl: ms for lbl, ms in QUARTERS}

    def _sm_for_q(q):
        ms = _q_months_map.get(q, [])
        total = 0.0
        for country_inv in (investment or {}).values():
            for seg_inv in country_inv.values():
                for m in ms:
                    total += seg_inv.get(m, {}).get("total", 0)
        return total

    def _sm_for_m_g(m_iso):
        total = 0.0
        for _ci in (investment or {}).values():
            for _si in _ci.values():
                total += _si.get(m_iso, {}).get("total", 0)
        return total

    # Payback global (Type="Todos") — desde RS (bi_strategic.payback_cohort_results)
    _pb_global = {seg: load_payback().get(("Todos", seg), {}) for seg in ("Total", "Core", "Lite")}

    def _payback_for_q(q):
        ms = _q_months_map.get(q, [])
        vals = [_pb_global.get("Total", {}).get(m) for m in ms
                if _pb_global.get("Total", {}).get(m)]
        return sum(vals) / len(vals) if vals else 0

    def _payback_for_m_g(m_iso):
        v = _pb_global.get("Total", {}).get(m_iso)
        return v if v is not None else 0

    _fx_rates = load_fx()

    def _fx_avg_q(pais, q):
        ms = _q_months_map.get(q, [])
        rates = [_fx_rates[(pais, m)] for m in ms if (pais, m) in _fx_rates]
        return sum(rates) / len(rates) if rates else 0

    # ── Rama mensual / trimestral para global arr_walk_table ─────────────────
    if not is_quarter_end:
        _all_m_data_g = seg_metrics.get("all", {}).get("months", {})
        _all_iso_g    = sorted(segs_raw.get("all", {}).keys())
        _last5m_iso_g = _all_iso_g[-5:]
        _g5           = [_month_label(m) for m in _last5m_iso_g]

        def _graw(key):
            return [_all_m_data_g.get(lbl, {}).get(key) or 0 for lbl in _g5]

        def _m_py_lbl_g(lbl):
            mon, yr = lbl[:3], int(lbl[-2:])
            return f"{mon}-{yr-1:02d}"

        _a_eop_py  = [_all_m_data_g.get(_m_py_lbl_g(lbl), {}).get("a_eop") or 0 for lbl in _g5]
        _a_sm      = [_sm_for_m_g(m) for m in _last5m_iso_g]
        _a_payback = [_payback_for_m_g(m) for m in _last5m_iso_g]
        _a_cop     = [_fx_rates.get(("colombia", m), 0) for m in _last5m_iso_g]
        _a_mxn     = [_fx_rates.get(("mexico",   m), 0) for m in _last5m_iso_g]
        _g_ytd_labels = [f"YTD'{int(cutoff[:4]) % 100 - 1:02d}", f"YTD'{int(cutoff[:4]) % 100:02d}"]
    else:
        _g5 = _last5q

        def _graw(key):
            return [_all_q_data[q].get(key) or 0 for q in _g5]

        _a_eop_py  = _qraw_py("a_eop")
        _a_sm      = [_sm_for_q(q) for q in _g5]
        _a_payback = [_payback_for_q(q) for q in _g5]
        _a_cop     = [_fx_avg_q("colombia", q) for q in _g5]
        _a_mxn     = [_fx_avg_q("mexico",   q) for q in _g5]
        _g_ytd_labels = [f"YTD'{int(cutoff[:4]) % 100 - 1:02d}", f"YTD'{int(cutoff[:4]) % 100:02d}"]

    _l_bop    = _graw("l_bop")
    _l_new    = _graw("l_new")
    # Opción A: usar logos_all (COUNT DISTINCT sin doble conteo) para que cuadre con SMB Logos EoP
    if not is_quarter_end:
        _l_eop = [(logos_all or {}).get(m, {}).get("logos_eop") or _graw("l_eop")[i]
                  for i, m in enumerate(_last5m_iso_g)]
    else:
        _l_eop = [(logos_all or {}).get(_q_months_map.get(q, [""])[-1], {}).get("logos_eop") or _graw("l_eop")[i]
                  for i, q in enumerate(_g5)]
    _l_churn  = _graw("l_churn_pct")
    _a_bop    = _graw("a_bop")
    _a_new    = _graw("a_new")
    _a_recov  = _graw("a_recov")
    _a_churn  = _graw("a_churn")       # gross churn (positivo)
    _a_upsell = _graw("a_upsell")
    _a_down   = _graw("a_down")
    _a_fx     = _graw("a_fx")
    _a_net_new = _graw("a_net_new")
    _a_eop    = _graw("a_eop")
    _a_eop_cc = _graw("a_cc_eop")

    _l_new_pct    = _graw("l_new_pct")
    _a_net_exp    = [_a_upsell[i] + _a_down[i] for i in range(len(_g5))]
    _a_net_ce_pct = [(_a_churn[i] + _a_net_exp[i]) / _a_bop[i] if _a_bop[i] else 0 for i in range(len(_g5))]

    # 5 simplified buckets for global ARR Walk slide
    _a_additions  = [_graw("a_new_base_t0")[i] + _graw("a_new_cross_t0")[i] for i in range(len(_g5))]
    _a_net_churn  = [-_graw("a_churn")[i] + _graw("a_react")[i] for i in range(len(_g5))]  # churn almacenado positivo, react positivo → net negativo
    _a_net_exp_full = [_a_upsell[i] + _a_down[i] + _graw("a_pricing")[i] + _graw("a_cross_new")[i] + _graw("a_cross_readop")[i] - _graw("a_cross_down")[i] for i in range(len(_g5))]

    # 12 buckets crudos (mes de corte, último elemento de _g5) — antes solo vivían como
    # variables Python internas de esta función, sin exponerse en metrics.yaml. Board Agent
    # (R5) los necesita para verificar de forma independiente que Net Expansion resta
    # cross_down (y no lo suma) — ver memory/project_board_agent.md 2026-07-06.
    out["arr_walk_raw_buckets"] = {
        "a_new_base_t0": _graw("a_new_base_t0")[-1], "a_new_cross_t0": _graw("a_new_cross_t0")[-1],
        "a_recov": _graw("a_recov")[-1], "a_react": _graw("a_react")[-1],
        "a_churn": _graw("a_churn")[-1], "a_upsell": _a_upsell[-1], "a_down": _a_down[-1],
        "a_pricing": _graw("a_pricing")[-1], "a_cross_new": _graw("a_cross_new")[-1],
        "a_cross_readop": _graw("a_cross_readop")[-1], "a_cross_down": _graw("a_cross_down")[-1],
        "a_fx": _a_fx[-1],
    }

    out["arr_walk_table"] = {
        "quarters": _g5,
        "ytd_labels": _g_ytd_labels,
        "sections": [
            {
                "label": "Logo EoP (000's)",
                "rows": [
                    _aw_row("Total EoP", "rb", "g",
                        _l_eop, lambda v: f"{v/1e3:.1f}" if v != 0 else "—"),
                    _aw_row("Logo Monthly New Adds %", "rt", None,
                        _l_new_pct, lambda v: f"{v*100:.1f}%" if v != 0 else "—",
                        pp=True),
                    _aw_row("Logo Monthly Churn %", "rt", None,
                        _l_churn, lambda v: f"{v*100:.1f}%" if v != 0 else "—",
                        pp=True, invert=True),
                ],
            },
            {
                "label": "ARR Walk — Spot ($M)",
                "rows": [
                    _aw_row("ARR BoP",            "rb", "g", _a_bop,                    lambda v: f"{v/1e6:.1f}" if v != 0 else "—"),
                    _aw_row("Additions",           "in", "g", _a_additions,            _fa_delta),
                    _aw_row("Recovered",           "in", "g", _a_recov,                 _fa_delta),
                    _aw_row("Net Churn",           "in", "r", _a_net_churn,             _fa_delta, nv=True),
                    _aw_row("Net Expansion",       "in", "a", _a_net_exp_full,          _fa_delta),
                    _aw_row("(+/−) FX Impact",     "in", "s", _a_fx,                   _fa_delta),
                    _aw_row("ARR EoP",             "rb", "g", _a_eop,                   lambda v: f"{v/1e6:.1f}" if v != 0 else "—", raws_py=_a_eop_py),
                    _aw_row("Net New ARR",         "rb", "a", _a_net_new,               _fa_delta),
                    _aw_row("ARR EoP (Constant Currency)",        "in", "s", _a_eop_cc,                lambda v: f"{v/1e6:.1f}" if v != 0 else "—"),
                ],
            },
            {
                "label": "SaaS Metrics",
                "rows": [
                    _aw_row("S&M Total Spend ($K)", "in", "s", _a_sm,
                        lambda v: f"${v/1e3:.0f}K" if v else "—", invert=True),
                    _aw_row("CAC Payback (meses)", "in", "g", _a_payback,
                        lambda v: f"{v:.1f}" if v else "—", invert=True),
                    _aw_row("FX — COP/USD", "rt", "s", _a_cop,
                        lambda v: f"{v:,.0f}" if v else "—", invert=True),
                    _aw_row("FX — MXN/USD", "rt", "s", _a_mxn,
                        lambda v: f"{v:.1f}" if v else "—", invert=True),
                ],
            },
        ],
    }

    # ── OVERRIDE TEMPORAL ARR Walk Global (valores del SS Apr-2026) ──────────
    # Solo aplica en modo trimestral — en mensual los datos vienen directo de RS.
    # Remover este bloque cuando RS entregue datos correctos en modo Q.
    if is_quarter_end:
        _aw_overrides = {
            "Total EoP":          {"cells": ["54.5","54.2","55.1","56.8","57.6"]},
            "Logo Monthly New Adds %": {"cells": ["5.1%","4.7%","4.9%","5.3%","5.3%"]},
            "Logo Monthly Churn %":    {"cells": ["5.2%","4.9%","4.3%","4.3%","4.8%"]},
            "ARR BoP":            {"cells": ["$19.2","$22.4","$22.9","$24.2","$26.6"]},
            "Recovered":          {"cells": ["+$400K","+$500K","+$500K","+$700K","+$500K"]},
            "Net Churn":          {"cells": ["($2.6M)","($2.6M)","($2.5M)","($2.4M)","($3.3M)"]},
            "Net Expansion":      {"cells": ["+$2.7M","+$700K","+$700K","+$1.5M","+$400K"]},
            "(+/−) FX Impact":    {"cells": ["+$800K","+$200K","+$700K","+$600K","+$400K"]},
            "ARR EoP":            {
                "cells": ["$22.4","$22.9","$24.2","$26.6","$27.3"],
                "qoq_cells": [{"v":"—","good":None},{"v":"+3%","good":True},{"v":"+6%","good":True},{"v":"+10%","good":True},{"v":"+3%","good":True}],
                "yoy_cells": [{"v":"+39%","good":True},{"v":"+41%","good":True},{"v":"+31%","good":True},{"v":"+39%","good":True},{"v":"+22%","good":True}],
                "qoq": "+3%", "qoq_good": True, "yoy": "+22%", "yoy_good": True,
                "ytd_prev": "$22.4", "ytd_cur": "$27.3",
            },
            "Net New ARR":        {"cells": ["+$3.2M","+$600K","+$1.3M","+$2.3M","+$700K"], "ytd_prev":"+$3.2M","ytd_cur":"+$700K"},
            "ARR EoP (Constant Currency)":       {
                "cells": ["$24.2","$24.6","$25.2","$27.0","$27.3"],
                "qoq_cells": [{"v":"—","good":None},{"v":"+2%","good":True},{"v":"+2%","good":True},{"v":"+7%","good":True},{"v":"+1%","good":True}],
                "ytd_prev": "$24.2", "ytd_cur": "$27.3",
            },
        }
        for _sec in out["arr_walk_table"]["sections"]:
            for _row in _sec["rows"]:
                if _row["label"] in _aw_overrides:
                    _row.update(_aw_overrides[_row["label"]])
    # ── FIN OVERRIDE ─────────────────────────────────────────────────────────

    # ── Per-segment ARR Walk Table (slides 2-3 de 3_arr_walk) ────────────────
    for _prod in out["arr_walk_products"]:
        _seg_name = _prod["name"]   # "Core" o "Lite"

        if is_quarter_end:
            # ── Modo trimestral: últimos 5 quarters ──
            _sq_data  = seg_metrics.get(_seg_name, {}).get("quarters", {})
            _s5       = [lbl for lbl, _ in QUARTERS if lbl in _sq_data][-5:]
            if not _s5:
                _prod["arr_walk_table"] = None
                continue

            def _sraw(key, _sd=_sq_data, _ss=_s5):
                return [_sd[q].get(key) or 0 for q in _ss]

            _sl_bop_raw = _sraw("l_bop")
            _sl_new_pct = [_sraw("l_new")[i] / (3 * _sl_bop_raw[i]) if _sl_bop_raw[i] else 0
                           for i in range(len(_s5))]
            _sa_sm      = [_sm_for_q(q) for q in _s5]
            _sa_pb      = [_payback_for_q(q) for q in _s5]
            _sa_cop     = [_fx_avg_q("colombia", q) for q in _s5]
            _sa_mxn     = [_fx_avg_q("mexico",   q) for q in _s5]
            _sa_eop_py  = [_sq_data.get(_py_lbl(q), {}).get("a_eop") or 0 for q in _s5]
            _ytd_labels = [f"YTD'{_s5[0][-2:]}", f"YTD'{_s5[-1][-2:]}"]

        else:
            # ── Modo mensual: últimos 5 meses ──
            _sm_data  = seg_metrics.get(_seg_name, {}).get("months", {})
            _seg_iso  = sorted(segs_raw.get(_seg_name, {}).keys())
            _s5m_iso  = _seg_iso[-5:]
            _s5       = [_month_label(m) for m in _s5m_iso]
            if not _s5:
                _prod["arr_walk_table"] = None
                continue

            def _sraw(key, _sd=_sm_data, _ss=_s5):
                return [_sd.get(lbl, {}).get(key) or 0 for lbl in _ss]

            _sl_bop_raw = _sraw("l_bop")
            _sl_new_pct = [_sraw("l_new")[i] / _sl_bop_raw[i] if _sl_bop_raw[i] else 0
                           for i in range(len(_s5))]

            def _sm_for_m(m_iso):
                total = 0.0
                for _ci in (investment or {}).values():
                    total += _ci.get(_seg_name, {}).get(m_iso, {}).get("total", 0)
                return total

            def _payback_for_m(m_iso):
                v = _pb_global.get(_seg_name, {}).get(m_iso)
                return v if v is not None else 0

            def _m_py_lbl(lbl):
                mon, yr = lbl[:3], int(lbl[-2:])
                return f"{mon}-{yr-1:02d}"

            _sa_sm      = [_sm_for_m(m) for m in _s5m_iso]
            _sa_pb      = [_payback_for_m(m) for m in _s5m_iso]
            _sa_cop     = [_fx_rates.get(("colombia", m), 0) for m in _s5m_iso]
            _sa_mxn     = [_fx_rates.get(("mexico",   m), 0) for m in _s5m_iso]
            _sa_eop_py  = [_sm_data.get(_m_py_lbl(lbl), {}).get("a_eop") or 0 for lbl in _s5]
            _ytd_labels = [f"YTD'{_s5[0][-2:]}", f"YTD'{_s5[-1][-2:]}"]

        _sl_bop      = _sraw("l_bop")
        _sl_new      = _sraw("l_new")
        _sl_eop      = _sraw("l_eop")
        _sl_churn    = _sraw("l_churn_pct")
        _sa_bop      = _sraw("a_bop")
        _sa_new_base = _sraw("a_new_base_t0")
        _sa_new_cross= _sraw("a_new_cross_t0")
        _sa_new      = _sraw("a_new")
        _sa_recov    = _sraw("a_recov")
        _sa_react    = _sraw("a_react")
        _sa_churn    = _sraw("a_churn")
        _sa_upsell   = _sraw("a_upsell")
        _sa_down     = _sraw("a_down")
        _sa_pricing  = _sraw("a_pricing")
        _sa_cross_new= _sraw("a_cross_new")
        _sa_cross_ro = _sraw("a_cross_readop")
        _sa_cross_dn = _sraw("a_cross_down")
        _sa_fx       = _sraw("a_fx")
        _sa_net_new  = _sraw("a_net_new")
        _sa_eop      = _sraw("a_eop")
        _sa_eop_cc   = _sraw("a_cc_eop")

        _sa_net_exp = [_sa_upsell[i] + _sa_down[i] for i in range(len(_s5))]
        _sa_net_ce  = [(_sa_churn[i] + _sa_net_exp[i]) / _sa_bop[i] if _sa_bop[i] else 0
                       for i in range(len(_s5))]

        # 5 simplified buckets for Core/Lite ARR Walk (misma lógica que global)
        _sa_additions   = [_sa_new_base[i] + _sa_new_cross[i]                                                    for i in range(len(_s5))]
        _sa_net_churn   = [-_sa_churn[i] + _sa_react[i]                                                          for i in range(len(_s5))]
        _sa_net_exp_full= [_sa_upsell[i] + _sa_down[i] + _sa_pricing[i] + _sa_cross_new[i] + _sa_cross_ro[i] - _sa_cross_dn[i]
                                                                                                                  for i in range(len(_s5))]

        _prod["arr_walk_table"] = {
            "quarters":   _s5,
            "ytd_labels": _ytd_labels,
            "sections": [
                {
                    "label": "Logo EoP (000's)",
                    "rows": [
                        _aw_row("Total EoP", "rb", "g", _sl_eop, lambda v: f"{v/1e3:.1f}" if v != 0 else "—"),
                        _aw_row("Logo Monthly New Adds %", "rt", None, _sl_new_pct, lambda v: f"{v*100:.1f}%" if v != 0 else "—", pp=True),
                        _aw_row("Logo Monthly Churn %", "rt", None, _sl_churn, lambda v: f"{v*100:.1f}%" if v != 0 else "—", pp=True, invert=True),
                    ],
                },
                {
                    "label": "ARR Walk — Spot ($M)",
                    "rows": [
                        _aw_row("ARR BoP",           "rb", "g", _sa_bop,      lambda v: f"{v/1e6:.1f}" if v != 0 else "—"),
                        _aw_row("Additions",        "in", "g", _sa_additions,    _fa_delta),
                        _aw_row("Recovered",        "in", "g", _sa_recov,        _fa_delta),
                        _aw_row("Net Churn",        "in", "r", _sa_net_churn,    _fa_delta, nv=True),
                        _aw_row("Net Expansion",    "in", "a", _sa_net_exp_full, _fa_delta),
                        _aw_row("(+/−) FX Impact",  "in", "s", _sa_fx,          _fa_delta),
                        _aw_row("ARR EoP",                   "rb", "g", _sa_eop,    lambda v: f"{v/1e6:.1f}" if v != 0 else "—", raws_py=_sa_eop_py),
                        _aw_row("Net New ARR",               "rb", "a", _sa_net_new, _fa_delta),
                        _aw_row("ARR EoP (Constant Currency)", "in", "s", _sa_eop_cc, lambda v: f"{v/1e6:.1f}" if v != 0 else "—"),
                    ],
                },
                {
                    "label": "SaaS Metrics",
                    "rows": [
                        _aw_row("S&M Total Spend ($K)", "in", "s", _sa_sm,
                            lambda v: f"${v/1e3:.0f}K" if v else "—", invert=True),
                        _aw_row("CAC Payback (meses)", "in", "g", _sa_pb,
                            lambda v: f"{v:.1f}" if v else "—", invert=True),
                        _aw_row("FX — COP/USD", "rt", "s", _sa_cop,
                            lambda v: f"{v:,.0f}" if v else "—", invert=True),
                        _aw_row("FX — MXN/USD", "rt", "s", _sa_mxn,
                            lambda v: f"{v:.1f}" if v else "—", invert=True),
                    ],
                },
            ],
        }

        # ── OVERRIDE TEMPORAL por segmento (solo modo trimestral) ───────────
        if not is_quarter_end:
            continue
        _seg_overrides = {
            "Core": {
                "Total EoP":           {"cells": ["18.8","19.4","20.4","22.0","23.0"]},
                "Logo Monthly New Adds %": {"cells": ["4.6%","4.5%","4.6%","4.5%","4.5%"]},
                "Logo Monthly Churn %":    {"cells": ["3.4%","3.2%","3.0%","2.8%","3.6%"]},
                "ARR BoP":             {"cells": ["$10.6","$12.2","$12.8","$13.8","$15.6"]},
                "New — Base T0":       {"cells": ["+$1.0M","+$1.0M","+$1.0M","+$1.1M","+$1.2M"]},
                "Recovered":           {"cells": ["+$100K","+$200K","+$100K","+$200K","+$100K"]},
                "Churn":               {"cells": ["($1.0M)","($1.0M)","($1.0M)","($1.0M)","($1.5M)"]},
                "Upsell":              {"cells": ["+$1.2M","+$400K","+$400K","+$900K","+$200K"]},
                "(+/−) FX Impact":     {"cells": ["+$500K","+$100K","+$400K","+$300K","+$300K"]},
                "ARR EoP":             {
                    "cells": ["$12.2","$12.8","$13.8","$15.6","$16.2"],
                    "qoq_cells": [{"v":"—","good":None},{"v":"+5%","good":True},{"v":"+8%","good":True},{"v":"+13%","good":True},{"v":"+4%","good":True}],
                    "yoy_cells": [{"v":"+36%","good":True},{"v":"+41%","good":True},{"v":"+36%","good":True},{"v":"+48%","good":True},{"v":"+33%","good":True}],
                    "qoq": "+4%", "qoq_good": True, "yoy": "+33%", "yoy_good": True,
                    "ytd_prev": "$12.2", "ytd_cur": "$16.2",
                },
                "Net New ARR":         {"cells": ["+$1.6M","+$600K","+$1.0M","+$1.8M","+$600K"], "ytd_prev":"+$1.6M","ytd_cur":"+$600K"},
                "ARR EoP (Constant Currency)":        {
                    "cells": ["$13.2","$13.8","$14.4","$15.9","$16.2"],
                    "qoq_cells": [{"v":"—","good":None},{"v":"+4%","good":True},{"v":"+4%","good":True},{"v":"+11%","good":True},{"v":"+2%","good":True}],
                    "ytd_prev": "$13.2", "ytd_cur": "$16.2",
                },
            },
            "Lite": {
                "Total EoP":           {"cells": ["35.7","34.8","34.7","34.8","34.6"]},
                "Logo Monthly New Adds %": {"cells": ["5.4%","4.8%","5.0%","5.8%","5.7%"]},
                "Logo Monthly Churn %":    {"cells": ["6.1%","5.7%","5.1%","5.1%","5.5%"]},
                "ARR BoP":             {"cells": ["$8.6","$10.1","$10.1","$10.4","$10.9"]},
                "New — Base T0":       {"cells": ["+$700K","+$800K","+$800K","+$900K","+$1.3M"]},
                "Recovered":           {"cells": ["+$300K","+$400K","+$400K","+$500K","+$400K"]},
                "Churn":               {"cells": ["($1.5M)","($1.6M)","($1.5M)","($1.5M)","($1.8M)"]},
                "Upsell":              {"cells": ["+$1.5M","+$300K","+$300K","+$600K","+$200K"]},
                "(+/−) FX Impact":     {"cells": ["+$400K","+$100K","+$300K","+$200K","+$200K"]},
                "ARR EoP":             {
                    "cells": ["$10.1","$10.1","$10.4","$10.9","$11.1"],
                    "qoq_cells": [{"v":"—","good":None},{"v":"−0%","good":False},{"v":"+3%","good":True},{"v":"+5%","good":True},{"v":"+1%","good":True}],
                    "yoy_cells": [{"v":"+43%","good":True},{"v":"+41%","good":True},{"v":"+26%","good":True},{"v":"+27%","good":True},{"v":"+9%","good":True}],
                    "qoq": "+1%", "qoq_good": True, "yoy": "+9%", "yoy_good": True,
                    "ytd_prev": "$10.1", "ytd_cur": "$11.1",
                },
                "Net New ARR":         {"cells": ["+$1.6M","($0K)","+$300K","+$500K","+$100K"], "ytd_prev":"+$1.6M","ytd_cur":"+$100K"},
                "ARR EoP (Constant Currency)":        {
                    "cells": ["$11.0","$10.9","$10.8","$11.1","$11.1"],
                    "qoq_cells": [{"v":"—","good":None},{"v":"−1%","good":False},{"v":"−0%","good":False},{"v":"+3%","good":True},{"v":"−0%","good":False}],
                    "ytd_prev": "$11.0", "ytd_cur": "$11.1",
                },
            },
        }
        if _seg_name in _seg_overrides:
            for _sec in _prod["arr_walk_table"]["sections"]:
                for _row in _sec["rows"]:
                    if _row["label"] in _seg_overrides[_seg_name]:
                        _row.update(_seg_overrides[_seg_name][_row["label"]])
        # ── FIN OVERRIDE ─────────────────────────────────────────────────────

    # ── pp namespace (4_financial_performance) ────────────────────────────────
    _pp_months = [_month_label(m) for m in all_months[-12:]]
    _pp_prods  = []
    for _pc in [{"seg":"Core","id":"core","name":"Core","color":"#534AB7"},
                {"seg":"Lite","id":"lite","name":"Lite","color":"#1D9E75"}]:
        _bs = segs_raw.get(_pc["seg"], {})
        _mc = _bs.get(latest_m, {}); _mp = _bs.get(prev_m, {}); _my = _bs.get(prev_yr, {})
        _ac = _mc.get("mrr_eop",0)*12; _ap = _mp.get("mrr_eop",0)*12; _ay = _my.get("mrr_eop",0)*12
        _lc = _mc.get("logos_eop",0);  _lp = _mp.get("logos_eop",0);  _ly = _my.get("logos_eop",0)
        _pp_prods.append({
            "id": _pc["id"], "name": _pc["name"], "color": _pc["color"],
            "arr": _fm(_ac),
            "arr_mom": _pct_delta(_ac,_ap)[0], "arr_mom_positive": _pct_delta(_ac,_ap)[1],
            "arr_yoy": _pct_delta(_ac,_ay)[0], "arr_yoy_positive": _pct_delta(_ac,_ay)[1],
            "logos": _fl(_lc),
            "logos_mom": _pct_delta(_lc,_lp)[0], "logos_mom_positive": _pct_delta(_lc,_lp)[1],
            "logos_yoy": _pct_delta(_lc,_ly)[0], "logos_yoy_positive": _pct_delta(_lc,_ly)[1],
            "spark_arr":   [_bs.get(m,{}).get("mrr_eop",0)*12/1e6 for m in all_months[-12:]],
            "spark_data":  [_bs.get(m,{}).get("mrr_eop",0)*12/1e6 for m in all_months[-12:]],
            "spark_color": _pc["color"],
            "spark_fill":  _pc["color"] + "33",
        })
    out["pp"] = {
        "total_subs":        _fl(all_m.get("l_eop",0)),
        "total_subs_delta":  arr_mom_str,
        "total_logos":       _fl(all_m.get("l_eop",0)),
        "total_logos_delta": arr_mom_str,
        "period_label":      f"{latest_m_lbl} · ARR in USD",
        "spark_months":      _pp_months,
        "products":          _pp_prods,
    }

    # ── gtm namespace (5_go_to_market) ────────────────────────────────────────
    _nl_c     = round(_mo("Core").get("l_new",0))
    _nl_c_prv = round(_mo_prev("Core").get("l_new",0))
    _nl_c_py  = round(_mo_py("Core").get("l_new",0))
    _nl_l     = round(_mo("Lite").get("l_new",0))
    _nl_l_prv = round(_mo_prev("Lite").get("l_new",0))
    _nl_l_py  = round(_mo_py("Lite").get("l_new",0))

    # Country new logos — arrays of last 13 months for stacked bar chart
    _gtm_months13 = sorted(country_raw.keys())[-13:]
    def _cnl_ts(seg, ck):
        return [round(country_raw.get(m,{}).get(ck,{}).get(seg,{}).get("logos_new",0))
                for m in _gtm_months13]

    _na = "N/A"

    # ── Investment helpers for GTM (global = sum across countries)
    _inv_months13 = sorted({
        m for ci in investment.values() for seg in ci.values() for m in seg
    })[-13:]

    def _fmt_inv(v):
        if v is None: return _na
        if v >= 1_000_000: return f"${v/1_000_000:.1f}M"
        return f"${round(v/1_000)}K"

    def _pct_str(num, den):
        if not den: return _na
        return f"{round(num/den*100)}%"

    def _inv_series(seg, field):
        return [round(_g_inv(seg, m, field) or 0) for m in _inv_months13]

    def _pct_series(seg, num_fn, den_fn):
        result = []
        for m in _inv_months13:
            n, d = num_fn(seg, m), den_fn(seg, m)
            result.append(round(n/d*100, 1) if (n and d) else None)
        return result

    # Current, prev month, prev year values per segment
    _g_inv_m  = {s: _g_inv(s, latest_m)  for s in ("Core","Lite")}
    _g_inv_pm = {s: _g_inv(s, prev_m)    for s in ("Core","Lite")}
    _g_inv_py = {s: _g_inv(s, prev_yr)   for s in ("Core","Lite")}

    def _inv_delta(seg, cur_fn, prv_fn):
        c, p = cur_fn(seg, latest_m), prv_fn(seg, latest_m)
        if not c or not p: return _na, True
        return _pct_delta(c, p)

    _paid_pct_lite_series  = _pct_series("Lite", _g_inv_paid, _g_inv)
    _paid_pct_core_series  = _pct_series("Core", _g_inv_paid, _g_inv)
    _team_pct_core_series  = _pct_series("Core", _g_inv_people, _g_inv)

    def _pct_cur(seg, comp_fn):
        t, c = _g_inv(seg, latest_m), comp_fn(seg, latest_m)
        return _pct_str(c, t) if (t and c is not None) else _na

    # top2_concentration: % of Core new logos from top-2 countries in latest month
    _top2_vals = sorted([
        country_raw.get(latest_m, {}).get(ck, {}).get("Core", {}).get("logos_new", 0)
        for ck in ("colombia","mexico","republicaDominicana","costaRica")
    ], reverse=True)
    _top2_total = sum(_top2_vals[:2])
    _top2_all   = sum(_top2_vals) or 1
    _top2_pct   = f"{round(_top2_total/_top2_all*100)}%"

    out["gtm"] = {
        "new_logos_core":              _nl_c,
        "new_logos_core_mom":          _pct_delta(_nl_c, _nl_c_prv)[0],
        "new_logos_core_mom_positive": _pct_delta(_nl_c, _nl_c_prv)[1],
        "new_logos_core_yoy":          _pct_delta(_nl_c, _nl_c_py)[0],
        "new_logos_core_yoy_positive": _pct_delta(_nl_c, _nl_c_py)[1],
        "new_logos_lite":              _nl_l,
        "new_logos_lite_mom":          _pct_delta(_nl_l, _nl_l_prv)[0],
        "new_logos_lite_mom_positive": _pct_delta(_nl_l, _nl_l_prv)[1],
        "new_logos_lite_yoy":          _pct_delta(_nl_l, _nl_l_py)[0],
        "new_logos_lite_yoy_positive": _pct_delta(_nl_l, _nl_l_py)[1],
        "new_logos_core_co": _cnl_ts("Core","colombia"),
        "new_logos_core_mx": _cnl_ts("Core","mexico"),
        "new_logos_core_dr": _cnl_ts("Core","republicaDominicana"),
        "new_logos_core_cr": _cnl_ts("Core","costaRica"),
        "new_logos_lite_co": _cnl_ts("Lite","colombia"),
        "new_logos_lite_mx": _cnl_ts("Lite","mexico"),
        "new_logos_lite_dr": _cnl_ts("Lite","republicaDominicana"),
        "new_logos_lite_cr": _cnl_ts("Lite","costaRica"),
        "chart_months":     [_month_label(m) for m in all_months[-13:]],
        "inv_chart_months": [_month_label(m) for m in _inv_months13],
        # S&M investment — from RS (db_finance.fact_cac_version_segments)
        "sm_core_total":           _fmt_inv(_g_inv_m["Core"]),
        "sm_core_total_cur":       _fmt_inv(_g_inv_m["Core"]),
        "sm_core_total_prev":      _fmt_inv(_g_inv_pm["Core"]),
        "sm_core_total_prev_year": _fmt_inv(_g_inv_py["Core"]),
        "sm_core_people":          _pct_cur("Core", _g_inv_people),
        "sm_core_people_prev":     _pct_str(_g_inv_people("Core", prev_m) or 0, _g_inv("Core", prev_m) or 1),
        "sm_core_people_prev_year":_pct_str(_g_inv_people("Core", prev_yr) or 0, _g_inv("Core", prev_yr) or 1),
        "sm_core_paid":            _pct_cur("Core", _g_inv_paid),
        "sm_core_paid_prev":       _pct_str(_g_inv_paid("Core", prev_m) or 0, _g_inv("Core", prev_m) or 1),
        "sm_core_paid_prev_year":  _pct_str(_g_inv_paid("Core", prev_yr) or 0, _g_inv("Core", prev_yr) or 1),
        "sm_core_other":           _pct_cur("Core", _g_inv_other),
        "sm_core_other_prev":      _pct_str(_g_inv_other("Core", prev_m) or 0, _g_inv("Core", prev_m) or 1),
        "sm_core_other_prev_year": _pct_str(_g_inv_other("Core", prev_yr) or 0, _g_inv("Core", prev_yr) or 1),
        "sm_core_var":             _pct_delta(_g_inv_m["Core"], _g_inv_pm["Core"])[0] if _g_inv_m["Core"] else _na,
        "sm_core_var_positive":    _pct_delta(_g_inv_m["Core"], _g_inv_pm["Core"])[1] if _g_inv_m["Core"] else True,
        "sm_lite_total":           _fmt_inv(_g_inv_m["Lite"]),
        "sm_lite_total_cur":       _fmt_inv(_g_inv_m["Lite"]),
        "sm_lite_total_prev":      _fmt_inv(_g_inv_pm["Lite"]),
        "sm_lite_total_prev_year": _fmt_inv(_g_inv_py["Lite"]),
        "sm_lite_people":          _pct_cur("Lite", _g_inv_people),
        "sm_lite_people_prev":     _pct_str(_g_inv_people("Lite", prev_m) or 0, _g_inv("Lite", prev_m) or 1),
        "sm_lite_people_prev_year":_pct_str(_g_inv_people("Lite", prev_yr) or 0, _g_inv("Lite", prev_yr) or 1),
        "sm_lite_paid":            _pct_cur("Lite", _g_inv_paid),
        "sm_lite_paid_prev":       _pct_str(_g_inv_paid("Lite", prev_m) or 0, _g_inv("Lite", prev_m) or 1),
        "sm_lite_paid_prev_year":  _pct_str(_g_inv_paid("Lite", prev_yr) or 0, _g_inv("Lite", prev_yr) or 1),
        "sm_lite_other":           _pct_cur("Lite", _g_inv_other),
        "sm_lite_other_prev":      _pct_str(_g_inv_other("Lite", prev_m) or 0, _g_inv("Lite", prev_m) or 1),
        "sm_lite_other_prev_year": _pct_str(_g_inv_other("Lite", prev_yr) or 0, _g_inv("Lite", prev_yr) or 1),
        "sm_lite_var":             _pct_delta(_g_inv_m["Lite"], _g_inv_pm["Lite"])[0] if _g_inv_m["Lite"] else _na,
        "sm_lite_var_positive":    _pct_delta(_g_inv_m["Lite"], _g_inv_pm["Lite"])[1] if _g_inv_m["Lite"] else True,
        # Paid media / team % series
        "paid_media_pct_core_series": _paid_pct_core_series,
        "paid_media_pct_lite":        _pct_cur("Lite", _g_inv_paid),
        "paid_media_pct_lite_series": _paid_pct_lite_series,
        "team_pct_core":              _pct_cur("Core", _g_inv_people),
        "team_pct_core_series":       _team_pct_core_series,
        # Absolute investment series by component (for stacked bar charts)
        "sm_core_paid_series":   [round(_g_inv_paid("Core",   m) or 0) for m in _inv_months13],
        "sm_core_people_series": [round(_g_inv_people("Core", m) or 0) for m in _inv_months13],
        "sm_core_other_series":  [round(_g_inv_other("Core",  m) or 0) for m in _inv_months13],
        "sm_lite_paid_series":   [round(_g_inv_paid("Lite",   m) or 0) for m in _inv_months13],
        "sm_lite_people_series": [round(_g_inv_people("Lite", m) or 0) for m in _inv_months13],
        "sm_lite_other_series":  [round(_g_inv_other("Lite",  m) or 0) for m in _inv_months13],
        "top2_concentration":          _top2_pct,
        # Funnel — desde bi_sales.sales_actions + bi_sales.fact_closed_deals
        "funnel_countries": _build_funnel_countries(_gtm_months13, funnel or {}),
        # Flywheel Entities + Logos (slides 5-6 de 5_go_to_market)
        "flywheel": _build_flywheel(flywheel or {}),
        # Supercontadores (slides 4, 4b, 4c, 4d de 5_go_to_market) — poblado abajo
        "supercontadores": {},
        "value_events":    [],
    }

    # ── Supercontadores (slides 4-4d de 5_go_to_market) ─────────────────────
    _sc = sc or {}
    _sc_data, _funnel_hist = _build_supercontadores(
        _sc.get("hist", []), _sc.get("events", []), _sc.get("sow", []), cutoff
    )
    out["gtm"]["supercontadores"] = _sc_data
    out["gtm"]["value_events"]    = _funnel_hist

    # Own vs Client ratio para el footnote de la slide "Flywheel Quarterly" (5_go_to_market.j2)
    # — mismo cálculo que ya usa el chart fw2_entBar/fw2_lgBar (metrics.gtm.supercontadores.propia/eop),
    # antes el footnote de texto tenía el mes y el % literales ("May-26 ratio (47%/53%)") sin actualizar.
    _sc_eop, _sc_propia = _sc_data.get("eop") or 0, _sc_data.get("propia") or 0
    out["gtm"]["own_pct"]         = round(_sc_propia / _sc_eop * 100) if _sc_eop else 0
    out["gtm"]["client_pct"]      = 100 - out["gtm"]["own_pct"] if _sc_eop else 0
    out["gtm"]["own_ratio_label"] = _month_label(cutoff)

    # ── Accountant Logos EoP — desde flywheel lg_stock ───────────────────────
    _fw_iso = sorted((flywheel or {}).keys())
    if len(_fw_iso) >= 2:
        _lg_eop  = (flywheel or {})[_fw_iso[-1]]["lg_stock"]
        _lg_prev = (flywheel or {})[_fw_iso[-2]]["lg_stock"]
        _lg_mom, _lg_mom_pos = _pct_delta(_lg_eop, _lg_prev)
        _lg_net  = (flywheel or {})[_fw_iso[-1]]["lg_new_adds"] - abs((flywheel or {})[_fw_iso[-1]].get("lg_net_churn", 0))
        _lg_yoy, _lg_yoy_pos = ("N/A", True)
        if len(_fw_iso) >= 13:
            _lg_py = (flywheel or {})[_fw_iso[-13]]["lg_stock"]
            _lg_yoy, _lg_yoy_pos = _pct_delta(_lg_eop, _lg_py)
        out["accountant_logos_eop"]          = f"{_lg_eop:,}".replace(",", ".")
        out["accountant_logos_mom"]          = _lg_mom
        out["accountant_logos_mom_positive"] = _lg_mom_pos
        out["accountant_logos_yoy"]          = _lg_yoy
        out["accountant_logos_yoy_positive"] = _lg_yoy_pos
        out["accountant_logos_net_adds"]     = f"+{_lg_net}" if _lg_net > 0 else str(_lg_net)

    # ── rd namespace (6_rd — Product Performance) ────────────────────────────
    _rd_months6 = all_months[-6:]
    out["rd"] = _build_product_perf(_rd_months6, product_perf or {}, logos_all)

    # ── nps (6_rd — NPS slide) — snapshot asistido desde Amplitude, ver _build_nps() ──
    out["nps"] = _build_nps(cutoff)

    # ── hc / pt namespaces (7_headcount) — desde bi_strategic_relationships (RS) ──
    out["hc"], out["pt"] = _build_headcount(cutoff)

    # ── churn_tenure (8_appendix — Churned by tenure GLO/Core/Lite) — desde RS ──
    out["churn_tenure"] = _build_churn_tenure(cutoff)

    # ── Chart history (slide 4: ARR EoP + Net New ARR) ────────────────────────
    out["chart_arr_history"] = _build_chart_history(seg_metrics, segs_raw, cutoff)

    # ── Alanube ARR Walk completo (slide 9 de 1_inicio.j2) — desde RS ──────────
    out["alanube_walk"] = _build_alanube_walk_table(cutoff)

    return out

def merge_accountant_logos(out: dict) -> None:
    """Calcula accountant_logos_* desde metrics.gtm.flywheel.lg_stock ya cargado en out."""
    try:
        lg = out.get("gtm", {}).get("flywheel", {}).get("lg_stock", [])
        if len(lg) < 2:
            return
        eop  = lg[-1]
        prev = lg[-2]
        mom_val, mom_pos = _pct_delta(eop, prev)
        net  = out.get("gtm", {}).get("flywheel", {}).get("lg_new_adds", [])
        churn = out.get("gtm", {}).get("flywheel", {}).get("lg_churn", [])
        net_adds = (net[-1] if net else 0) - abs(churn[-1] if churn else 0)
        yoy_val, yoy_pos = ("N/A", True)
        if len(lg) >= 13:
            yoy_val, yoy_pos = _pct_delta(eop, lg[-13])
        out["accountant_logos_eop"]          = f"{eop:,}".replace(",", ".")
        out["accountant_logos_mom"]          = mom_val
        out["accountant_logos_mom_positive"] = mom_pos
        out["accountant_logos_yoy"]          = yoy_val
        out["accountant_logos_yoy_positive"] = yoy_pos
        out["accountant_logos_net_adds"]     = f"+{net_adds}" if net_adds > 0 else str(net_adds)
        # Eliminar claves viejas si existen
        out.pop("accountant_logos_qoq", None)
        out.pop("accountant_logos_qoq_positive", None)
        print(f"✅ Accountant Logos: EoP {eop:,} · MoM {mom_val} · YoY {yoy_val} · net adds {net_adds}")
    except Exception as e:
        print(f"⚠️  merge_accountant_logos: {e}")


# ── MAIN ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Fetch board metrics from Redshift")
    parser.add_argument("--refresh",  action="store_true", help="Ignorar caché")
    parser.add_argument("--month",    default=None,        help="Mes de corte YYYY-MM (default: mes anterior)")
    parser.add_argument("--csv-only", action="store_true", help="Solo re-mergea CSVs (Budget, P&L, Payback) sin tocar Redshift")
    args = parser.parse_args()

    # Default cutoff = previous month
    if args.month:
        cutoff = args.month
    else:
        now = datetime.now()
        m = now.month - 1 or 12
        y = now.year if now.month > 1 else now.year - 1
        cutoff = f"{y:04d}-{m:02d}"

    print(f"📊 fetch_metrics.py · cutoff: {cutoff}")

    if args.csv_only:
        # Solo actualizar los merges de CSV sobre el metrics.yaml existente
        if not OUTPUT_FILE.exists():
            print("❌ No existe metrics.yaml — corre primero sin --csv-only para generar el YAML base.")
            sys.exit(1)
        print("📂 --csv-only: cargando metrics.yaml existente…")
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            out = yaml.safe_load(f)
        # Restaurar _raw desde cache para que merge_budget pueda comparar vs real
        if RAW_CACHE_FILE.exists():
            with open(RAW_CACHE_FILE, "r", encoding="utf-8") as _f:
                _cached = yaml.safe_load(_f) or {}
                out["_raw"] = _cached.get("_raw", {})
        print("💰 Mergeando budget desde CSV…")
        merge_budget(out, cutoff)
        out.pop("_raw", None)
        print("📊 Mergeando P&L (Net Revenue, Gross Margin, EBITDA)…")
        merge_pnl(out, cutoff)
        print("⏱️  Mergeando Payback…")
        merge_payback(out, cutoff)
        merge_accountant_logos(out)
    else:
        print("📡 Cargando datos del cache de Metabase…")
        summary, logos_all, country_raw, investment, funnel, product_perf, flywheel, sc = load_data(cutoff, refresh=args.refresh)

        print("⚙️  Calculando métricas por segmento…")
        seg_metrics, segs_raw, all_months, latest_mm = build_seg_metrics(summary, logos_all, sc=sc)

        print("🗺️  Construyendo estructura YAML…")
        out = build_yaml(seg_metrics, segs_raw, all_months, latest_mm, country_raw, cutoff, investment, funnel=funnel, product_perf=product_perf, logos_all=logos_all, flywheel=flywheel, sc=sc)

        print("💰 Mergeando budget desde CSV…")
        merge_budget(out, cutoff)
        # Guardar _raw en cache para que --csv-only pueda usarlo después
        if "_raw" in out:
            with open(RAW_CACHE_FILE, "w", encoding="utf-8") as _f:
                yaml.dump({"_raw": out["_raw"]}, _f)
        out.pop("_raw", None)  # solo para cálculo interno, no va al yaml

        print("📊 Mergeando P&L (Net Revenue, Gross Margin, EBITDA)…")
        merge_pnl(out, cutoff)

        print("⏱️  Mergeando Payback…")
        merge_payback(out, cutoff)
        merge_accountant_logos(out)

    # Criterio unificado 2026-07-14: toda query faltante del cache de Metabase debe ser un
    # FAIL visible, nunca un warning silencioso que deja el board con datos en $0/blanco.
    # Este es el único punto de chequeo real — corre DESPUÉS de que todo el pipeline (las 11
    # queries de load_data(), más load_fx/load_payback/load_headcount_*/load_alanube_*/
    # _build_churn_tenure, se llamen desde donde se llamen) tuvo su oportunidad de intentar
    # cada query, así que la lista es completa en un solo intento — no hace falta corregir
    # una query, volver a correr, descubrir la siguiente, y repetir.
    if _MISSING_QUERIES:
        faltantes = sorted(set(_MISSING_QUERIES))
        raise RuntimeError(
            f"Faltan {len(faltantes)} quer{'y' if len(faltantes) == 1 else 'ies'} en el cache de "
            f"Metabase para {cutoff}: {faltantes} — no se puede confiar en el board con datos "
            "parciales. Corré cada query MBQL faltante (ver board_agent/metabase_fetch_spec.py) y "
            "agregala al cache antes de continuar."
        )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        yaml.dump(out, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"✅ metrics.yaml escrito → {OUTPUT_FILE}")
    print(f"   ARR total: {out['arr_total']} · MoM: {out['arr_mom']} · YoY: {out['arr_yoy']}")
    print(f"   Productos: {[p['name'] for p in out['arr_walk_products']]}")
    print(f"   Países:    {[c['team'] for c in out['countries']]}")


# ── Budget merge ───────────────────────────────────────────────────────────────
def _parse_num(s):
    """Remove $, commas and % from a CSV value and return float."""
    return float(str(s).replace("$", "").replace(",", "").replace("%", "").strip())

def merge_budget(out, cutoff):
    """Read Metricas_budget.csv, find the active month and inject vs_budget fields into out."""
    if not BUDGET_FILE.exists():
        print(f"⚠️  Budget CSV no encontrado: {BUDGET_FILE} — vs_budget queda N/A")
        return

    _MONTHS_EN = ["Jan","Feb","Mar","Apr","May","Jun",
                  "Jul","Aug","Sep","Oct","Nov","Dec"]

    def _cutoff_to_key(c):
        y, m = c.split("-")
        return f"{_MONTHS_EN[int(m)-1]} - {y[2:]}"  # "2026-03" → "Mar - 26"

    def _q_months_for(c):
        """Devuelve los 3 meses del quarter al que pertenece c."""
        for _, ms in QUARTERS:
            if c in ms:
                return ms
        return [c]

    is_quarter_end = out.get("is_quarter_end", False)
    month_key = _cutoff_to_key(cutoff)

    # Leer TODO el CSV indexado por (Metric, month_key)
    budget_by_month = defaultdict(dict)   # {month_key: {metric: value}}
    with open(BUDGET_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        first_data_col = None
        for row in reader:
            if first_data_col is None:
                cols = [c for c in row.keys() if c not in ("Metric", "Fecha")]
                first_data_col = cols[0] if cols else None
            fk = row.get("Fecha", "").strip()
            metric = row.get("Metric", "").strip()
            val_str = (row.get(first_data_col, "") or "").strip()
            if fk and metric and val_str:
                try:
                    budget_by_month[fk][metric] = _parse_num(val_str)
                except ValueError:
                    pass

    # Budget del mes actual (para ARR EoP y Churn — siempre punto del mes)
    budget = budget_by_month.get(month_key, {})
    if not budget:
        print(f"⚠️  No se encontraron filas de budget para '{month_key}' en el CSV")
        return

    # Budget acumulado del Q para New MRR y New Logos (cuando es cierre de Q)
    if is_quarter_end:
        q_keys = [_cutoff_to_key(m) for m in _q_months_for(cutoff)]
        budget_q_new_mrr   = sum(budget_by_month.get(k, {}).get("New MRR",   0) for k in q_keys)
        budget_q_new_logos = sum(budget_by_month.get(k, {}).get("New Logos", 0) for k in q_keys)
    else:
        budget_q_new_mrr   = budget.get("New MRR",   0)
        budget_q_new_logos = budget.get("New Logos", 0)

    raw = out.get("_raw", {})

    def _pct(real, bud):
        if bud == 0:
            return "N/A", True
        delta = (real - bud) / bud * 100
        sign = "+" if delta >= 0 else ""
        return f"{sign}{delta:.1f}%", delta >= 0

    def _pp(real, bud):
        delta = real - bud
        sign = "+" if delta >= 0 else ""
        return f"{sign}{delta:.2f}"

    # ARR EoP
    if "ARR EoP" in budget:
        s, pos = _pct(raw.get("arr_eop", 0), budget["ARR EoP"])
        out["arr_vs_budget"] = s
        out["arr_vs_budget_positive"] = pos

    # New MRR (vs Q budget cuando es cierre de Q)
    if budget_q_new_mrr:
        s, pos = _pct(raw.get("new_mrr", 0), budget_q_new_mrr)
        out["new_mrr_vs_budget"] = s
        out["new_mrr_vs_budget_positive"] = pos

    # New Logos (vs Q budget cuando es cierre de Q)
    if budget_q_new_logos:
        s, pos = _pct(raw.get("new_logos", 0), budget_q_new_logos)
        out["new_logos_vs_budget"] = s

    # Churn Rate (pp delta: real - budget)
    if "Churn Rate" in budget:
        out["logo_churn_vs_budget_pp"] = _pp(raw.get("logo_churn_pct", 0), budget["Churn Rate"])

    print(f"✅ Budget mergeado para {month_key}: ARR {out['arr_vs_budget']} · "
          f"New MRR {out['new_mrr_vs_budget']} · New Logos {out['new_logos_vs_budget']} · "
          f"Churn {out['logo_churn_vs_budget_pp']}pp")


# ── P&L merge ──────────────────────────────────────────────────────────────────
def _pnl_date_str(cutoff):
    """'2026-02' → '2/28/2026' (último día del mes)."""
    y, m = int(cutoff[:4]), int(cutoff[5:])
    last = calendar.monthrange(y, m)[1]
    return f"{m}/{last}/{y}"

def _prev_cutoff(cutoff):
    """'2026-02' → '2026-01'."""
    y, m = int(cutoff[:4]), int(cutoff[5:])
    m -= 1
    if m == 0:
        m, y = 12, y - 1
    return f"{y}-{m:02d}"

def _yoy_cutoff(cutoff):
    """'2026-02' → '2025-02'."""
    return f"{int(cutoff[:4])-1}{cutoff[4:]}"

def _norm_cat(c):
    """Normaliza nombres de categoría con variaciones de mayúsculas."""
    return c.strip().lower()

# Mapeo de categorías normalizadas → clave interna
_CAT_MAP = {
    "income":                                        "income",
    "cost of revenue":                               "cor",
    "customer acquisition costs":                    "cac",
    "product (expensed)":                            "product",
    "general and administrative":                    "ga",
    "depreciation/amortization":                     "da",
    "taxes":                                         "taxes",
    "non - operating income/ expenses (net)":        "non_op",
    "non-operating income":                          "non_op",
    "interest expenses":                             "non_op",
    "financial yield":                               "fin_yield",
    "provisions":                                    "provisions",
    "interco":                                       "interco",
}

def _load_pnl_rows(filepath, date_str, amount_col):
    """Carga filas de un CSV de P&L para una fecha específica."""
    rows = []
    if not Path(filepath).exists():
        return rows
    with open(filepath, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("Date", "").strip() == date_str:
                try:
                    val = float(str(row.get(amount_col, "0")).replace(",", "").strip() or 0)
                except ValueError:
                    val = 0.0
                norm = _norm_cat(row.get("Category", ""))
                rows.append({
                    "cat":  _CAT_MAP.get(norm, norm),
                    "type": row.get("Type", "").strip(),
                    "val":  val,
                })
    return rows

def _calc_pnl(rows):
    """Aplica la lógica de signos y calcula las líneas del P&L."""
    by_cat   = defaultdict(float)
    by_ctype = defaultdict(float)
    for r in rows:
        by_cat[r["cat"]]                  += r["val"]
        by_ctype[(r["cat"], r["type"])]   += r["val"]

    # ── Income ─────────────────────────────────────────────────────────────────
    op_inc  = by_ctype.get(("income", "Operating Income"), 0)
    refunds = by_ctype.get(("income", "Refunds"), 0)
    total_revenue = abs(op_inc) - abs(refunds)

    # ── CoR ────────────────────────────────────────────────────────────────────
    cor = abs(by_cat.get("cor", 0))

    # ── Gross ──────────────────────────────────────────────────────────────────
    gross_income   = total_revenue - cor
    gross_margin   = gross_income / total_revenue * 100 if total_revenue else 0

    # ── OpEx (sin CoR) ─────────────────────────────────────────────────────────
    cac     = abs(by_cat.get("cac", 0))
    product = abs(by_cat.get("product", 0))
    ga      = abs(by_cat.get("ga", 0))
    opex    = cac + product + ga

    # ── EBITDA ─────────────────────────────────────────────────────────────────
    ebitda        = gross_income - opex
    ebitda_margin = ebitda / total_revenue * 100 if total_revenue else 0

    # ── Below-EBITDA ───────────────────────────────────────────────────────────
    non_op    = by_cat.get("non_op", 0)     # viene negativo → restar = sumar
    fin_yield = by_cat.get("fin_yield", 0)  # viene negativo → restar = sumar
    da        = abs(by_cat.get("da", 0))
    taxes     = abs(by_cat.get("taxes", 0))

    net_income     = ebitda - non_op - da - fin_yield - taxes
    net_income_pct = net_income / total_revenue * 100 if total_revenue else 0

    # ── Provisions (invertir signo) ────────────────────────────────────────────
    provisions = by_cat.get("provisions", 0) * -1

    # ── Interco ────────────────────────────────────────────────────────────────
    ico_op_inc     = by_ctype.get(("interco", "Operating Income"), 0) * -1
    ico_non_op_inc = by_ctype.get(("interco", "Non-Operating Income"), 0) * -1
    ico_expenses   = by_ctype.get(("interco", "Interco Expenses"), 0)
    ico_cod        = by_ctype.get(("interco", "Cost of Debt"), 0)
    ico_taxes      = by_ctype.get(("interco", "Interco Taxes"), 0)
    total_interco  = (ico_op_inc + ico_non_op_inc) - (ico_expenses + ico_cod + ico_taxes)

    # ── Financial Outcome ──────────────────────────────────────────────────────
    fo     = net_income + provisions + total_interco
    fo_pct = fo / total_revenue * 100 if total_revenue else 0

    return {
        "total_revenue":   total_revenue,
        "gross_income":    gross_income,
        "gross_margin":    gross_margin,
        "cac":             cac,
        "product":         product,
        "ga":              ga,
        "opex":            opex,
        "ebitda":          ebitda,
        "ebitda_margin":   ebitda_margin,
        "net_income":      net_income,
        "net_income_pct":  net_income_pct,
        "provisions":      provisions,
        "total_interco":   total_interco,
        "fo":              fo,
        "fo_pct":          fo_pct,
    }

def merge_pnl(out, cutoff):
    """Lee los CSVs de P&L actual y budget, calcula métricas e inyecta en out."""
    if not PNL_ACTUAL.exists():
        print(f"⚠️  P&L Actual no encontrado: {PNL_ACTUAL}")
        return

    date_cur  = _pnl_date_str(cutoff)
    date_prev = _pnl_date_str(_prev_cutoff(cutoff))
    date_yoy  = _pnl_date_str(_yoy_cutoff(cutoff))

    rows_cur  = _load_pnl_rows(PNL_ACTUAL, date_cur,  "sum Amount USD")
    rows_prev = _load_pnl_rows(PNL_ACTUAL, date_prev, "sum Amount USD")
    rows_yoy  = _load_pnl_rows(PNL_ACTUAL, date_yoy,  "sum Amount USD")
    rows_bud  = _load_pnl_rows(PNL_BUDGET, date_cur,  "Amount") if PNL_BUDGET.exists() else []

    if not rows_cur:
        # Intentar override manual (data/pnl_override.yaml)
        _override_path = ROOT / "data" / "pnl_override.yaml"
        if _override_path.exists():
            import yaml as _yaml
            _ov = _yaml.safe_load(_override_path.read_text()).get(cutoff, {})
            if _ov:
                out.update(_ov)
                print(f"✅ P&L override aplicado para {cutoff} (data/pnl_override.yaml)")
                return
        print(f"⚠️  P&L: sin filas para {date_cur}")
        return

    cur  = _calc_pnl(rows_cur)
    prev = _calc_pnl(rows_prev) if rows_prev else {}
    yoy  = _calc_pnl(rows_yoy)  if rows_yoy  else {}
    bud  = _calc_pnl(rows_bud)  if rows_bud  else {}

    def _pct_delta(a, b):
        if not b: return "N/A", True
        d = (a - b) / abs(b) * 100
        return f"{'+'if d>=0 else ''}{d:.1f}%", d >= 0

    def _pp_delta(a, b):
        if not b: return "N/A", True
        d = a - b
        return f"{'+'if d>=0 else ''}{d:.1f}pp", d >= 0

    def _fm_rev(v):
        if abs(v) >= 1e6: return f"${v/1e6:.1f}M"
        if abs(v) >= 1e3: return f"${v/1e3:.0f}K"
        return f"${v:.0f}"

    rev  = cur["total_revenue"]
    gm   = cur["gross_margin"]
    ebm  = cur["ebitda_margin"]

    # Net Revenue
    out["net_revenue"]                   = _fm_rev(rev)
    out["net_revenue_mom"], out["net_revenue_mom_positive"] = (
        _pct_delta(rev, prev.get("total_revenue", 0)) if prev else ("N/A", True))
    out["net_revenue_vs_budget"], out["net_revenue_vs_budget_positive"] = (
        _pct_delta(rev, bud.get("total_revenue", 0)) if bud else ("N/A", True))
    out["net_revenue_yoy"], out["net_revenue_yoy_positive"] = (
        _pct_delta(rev, yoy.get("total_revenue", 0)) if yoy else ("N/A", True))

    # Gross Margin %
    out["gross_margin"]                  = f"{gm:.1f}%"
    out["gross_margin_mom"], _           = (
        _pp_delta(gm, prev.get("gross_margin", 0)) if prev else ("N/A", True))
    out["gross_margin_vs_budget"], out["gross_margin_vs_budget_positive"] = (
        _pp_delta(gm, bud.get("gross_margin", 0)) if bud else ("N/A", True))
    out["gross_margin_yoy"], out["gross_margin_yoy_positive"] = (
        _pp_delta(gm, yoy.get("gross_margin", 0)) if yoy else ("N/A", True))

    # EBITDA Margin %
    out["ebitda_margin"]                 = f"{ebm:.1f}%"
    out["ebitda_margin_mom"], out["ebitda_margin_mom_positive"] = (
        _pp_delta(ebm, prev.get("ebitda_margin", 0)) if prev else ("N/A", True))
    out["ebitda_margin_vs_budget"], out["ebitda_margin_vs_budget_positive"] = (
        _pp_delta(ebm, bud.get("ebitda_margin", 0)) if bud else ("N/A", True))
    out["ebitda_margin_yoy"], out["ebitda_margin_yoy_positive"] = (
        _pp_delta(ebm, yoy.get("ebitda_margin", 0)) if yoy else ("N/A", True))

    print(f"✅ P&L mergeado para {date_cur}: "
          f"Revenue {out['net_revenue']} · GM {out['gross_margin']} · EBITDA {out['ebitda_margin']}")


# ── Payback merge ───────────────────────────────────────────────────────────────
def merge_payback(out, cutoff, payback_hist=16):
    """Inyecta payback_core, payback_lite y payback_hist en out desde load_payback() (RS).
    En cierre de quarter (mes 3/6/9/12) usa promedio de los 3 meses del Q.
    En meses normales usa el valor puntual del mes.
    """
    year, month = int(cutoff[:4]), int(cutoff[5:7])
    is_quarter_end = month in (3, 6, 9, 12)

    # Meses a promediar: si es Q-end, los 3 del quarter; si no, solo el mes actual
    if is_quarter_end:
        q_start = month - 2
        date_strs = [f"{year}-{m:02d}" for m in range(q_start, month + 1)]
    else:
        date_strs = [cutoff]

    # Acumular valores por segmento
    pb = load_payback()
    buckets = {"Core": [], "Lite": [], "Total": []}
    for seg in buckets:
        months = pb.get(("Todos", seg), {})
        for d in date_strs:
            if d in months:
                buckets[seg].append(months[d])

    def _avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else None

    core_val   = _avg(buckets["Core"])
    lite_val   = _avg(buckets["Lite"])
    global_val = _avg(buckets["Total"])

    if core_val is None or lite_val is None:
        print(f"⚠️  Payback: sin datos para {date_strs}")
        return

    out["payback_global"] = global_val if global_val is not None else "N/A"
    out["payback_core"]   = core_val
    out["payback_lite"]   = lite_val
    out["payback_hist"]   = payback_hist

    period = f"Q avg {date_strs[0]}→{date_strs[-1]}" if is_quarter_end else cutoff
    print(f"✅ Payback mergeado ({period}): Global {out['payback_global']} mo · Core {out['payback_core']} mo · Lite {out['payback_lite']} mo · Hist {payback_hist} mo")


if __name__ == "__main__":
    main()
