"""metabase_fetch_spec.py — Spec de referencia de todo lo que debe vivir en
data/.metabase_cache.json antes de correr el pipeline (run.py, check_setup.py,
fetch_metrics.py, update_appendix.py).

Este módulo NO ejecuta nada — no tiene acceso a Metabase ni a Redshift. Es documentación
importable: para cada entrada de cache dice qué tabla(s) de Metabase la respaldan, qué
lógica de negocio implementa y si su traducción a MBQL (el único modo que soporta el
conector `claude.ai Metabase MCP`, sin SQL nativo — verificado 2026-07-10) ya quedó
validada contra Redshift real. El detalle línea por línea del JSON MBQL de cada query
(joins, self-joins, gotchas de sintaxis) NO se guardó como artefacto reusable — se
construyó interactivamente vía mcp__metabase__construct_query durante la sesión de
migración y quedó documentado como PATRÓN (no como payload) en
memory/project_board_agent.md, sección "CIERRE DEFINITIVO" (2026-07-10). Quien puebla el
cache debe reconstruir cada query con ese mismo patrón, apoyándose en el SQL canónico
(todavía presente como comentario/constante en scripts/fetch_metrics.py) como
especificación exacta de columnas y lógica.

Migración completa: Board Agent no se conecta a Redshift ni tiene credenciales AWS (ver
board_agent/paths.py). Todo dato viene de Metabase, corrido por Claude Code vía el MCP
(OAuth, sin API keys embebidas — mandato de Arquitectura, ver memory/project_board_agent.md).

── Forma de data/.metabase_cache.json ──────────────────────────────────────────────────

{
  "month": "2026-06",                          # cutoff que corresponde a "queries"/"freshness"
  "fetched_at": "2026-07-10T14:30:00",          # informativo, no lo valida ningún check
  "freshness": {"F1.1": {"n": 21343, "max_date": "2026-06-01"}, ...},   # ver FRESHNESS_CHECKS
  "queries":   {"fact_customers_mrr (summary)": [{...fila...}, ...], ...},  # ver QUERIES
  "validator": {"R7": {"logos_eop": 58974}},                             # ver VALIDATOR_CHECKS
  "appendix":  {"2026-06": [{"segmento": "Core", "bracket": "M1-M3", "logos_churn": 42}, ...]},
}

freshness/validator/appendix son independientes del "month" de arriba salvo freshness
(phase1_freshness.py exige que coincida exacto) — queries también exige el mismo "month"
(fetch_metrics.py._check_metabase_cache_month). "appendix" se puebla por mes específico,
puede tener varias entradas simultáneas (un mes por corrida de update_appendix.py).
"""

from .phase1_freshness import _CHECKS as _FRESHNESS_CHECKS_SOURCE

# ── QUERIES — cache["queries"][label], consumidas por scripts/fetch_metrics.py ──────────
# status: "exact" (0 diff contra RS) | "exact_with_data_lag" (traducción correcta, pero
#   Metabase tenía datos desactualizados el 2026-07-10 — revalidar freshness antes de confiar)
#   | "assembled_exact" (ensamblada completa después, también 0 diff) | "blocked" (no migrable
#   todavía, falta tabla en Metabase)
QUERIES = [
    {
        "label": "fact_customers_mrr (summary)",
        "sql_const": "_SQL_FACT_SUMMARY",
        "metabase_tables": ["dm_strategic.fact_customers_mrr"],
        "status": "exact",
        "notes": "La más compleja del pipeline — 19 columnas, self-joins de mes a mes, split "
                 "New Base T0/Cross T0 vía sort_key + join anidado de 2 stages (sin ROW_NUMBER "
                 "real). Re-verificada COMPLETA 2026-07-10, columna por columna, para mayo-2026 — "
                 "las 18 métricas reconstruidas desde cero en MBQL y comparadas contra Redshift, "
                 "0 diferencias en todas: logos_eop/new/recov/react (58974/2337/744/1406) y "
                 "mrr_usd_eop (22 filas país×segmento, match hasta el 6to decimal); logos_churn "
                 "(20 filas); mrr_usd_recov/react (44 valores); mrr_usd_churn (self-join simple "
                 "mes-1, 20 valores); mrr_usd_upsell/downsell/pricing_others (self-join completo "
                 "mes-1 con clasificación por plan_name+delta, 66 valores); mrr_usd_new_base_t0/"
                 "new_cross_t0 (el sort_key trick con 3 niveles de anidamiento — flm → t0_products "
                 "→ bpl → clasificación — 17 filas × 2 métricas); mrr_usd_cross_new_t1plus/"
                 "cross_readop (products_added, misma lógica de fpm + anti-join, 11 filas × 2 "
                 "métricas); mrr_usd_cross_down (products_removed, anti-join simétrico, 14 filas). "
                 "**18/18 métricas validadas, 0 diferencias — la query más importante y compleja "
                 "del pipeline queda 100% probada.** Gotchas de sintaxis nuevos encontrados en "
                 "esta prueba: (1) una expresión definida en el stage 1 de un join de 2 stages "
                 "debe referenciarse en el stage 2 como ['field',{},'nombre'], NO como "
                 "['expression',{},'nombre'] — las expresiones no son visibles entre stages, solo "
                 "sus columnas de salida; (2) esos field-refs cross-stage necesitan 'base-type' "
                 "explícito en breakout/aggregation del stage 2, igual que ya se documentó para "
                 "joins simples; (3) un anti-join (LEFT JOIN + is-null) sobre un join NO agregado "
                 "(raw rows) funciona directo, sin necesidad de agregar el lado derecho primero — "
                 "solo el lado usado como 'existencia' (ej. active_may/active_april) necesita "
                 "agregarse a pares distintos antes del INNER JOIN, para no multiplicar filas.",
    },
    {
        "label": "company mrr mensual (ARR Walk v2)",
        "sql_const": "_SQL_COMPANY_MRR_MONTHLY",
        "metabase_tables": ["dm_strategic.fact_customers_mrr"],
        "status": "exact",
        "notes": "Agregado 2026-07-22 — reemplaza el ARR Walk de 'fact_customers_mrr (summary)' "
                 "(New/Churn/Reactivated/Recovered/Upsell/Downsell por producto+plan) por la "
                 "metodología validada contra el Excel real de Finance (New=primer MRR>0, "
                 "Churn=pasa a 0, Reactivated=vuelve el mes siguiente, Recovered=vuelve más "
                 "tarde, Upsell/Downsell=compañía continua sube/baja, todo a nivel COMPAÑÍA "
                 "completa, no por producto). Validado en vivo con 15 quarters reales contra "
                 "RS (4Q22→2Q26) — match a la décima con el Excel en los 5 quarters completos "
                 "de referencia (1Q25-1Q26). A diferencia de 'fact_customers_mrr (summary)', "
                 "esta query NO tiene self-joins — es una agregación simple sin historial: "
                 "`SUM(amount_conv) GROUP BY id_company, segment_type_def, app_version` **solo "
                 "del mes de corte**. Toda la secuenciación (comparar contra el mes anterior, "
                 "detectar gaps para Reactivated/Recovered) se hace en Python en "
                 "fetch_metrics.py, leyendo/actualizando el estado local "
                 "data/.company_mrr_history.json (NO vive en Metabase ni se recalcula cada "
                 "mes vía MBQL — se sembró una sola vez con un pull directo a RS, ver "
                 "memory/project_board_agent.md). Grano ~60K filas (una por compañía×segmento "
                 "activa) — más grande que cualquier query de negocio existente salvo 'Alanube "
                 "ARR Walk completo' (~3.5K filas), pero sin self-join hace que la traducción "
                 "MBQL sea mecánicamente simple (mismo patrón que 'logos consolidados').",
    },
    {
        "label": "logos consolidados",
        "sql_const": "_SQL_LOGOS_ALL",
        "metabase_tables": ["dm_strategic.fact_customers_mrr"],
        "status": "exact",
        "notes": "Agregación simple, sin self-join. Re-verificado 2026-07-10 (prueba real "
                 "post-migración): abr/may/jun-2026, 4 métricas (logos_eop/new/recov/react) — "
                 "12/12 números idénticos contra Redshift, sin ningún desfase (a diferencia de "
                 "accountant_master_table y fact_cac_version_segments). Confirma que "
                 "fact_customers_mrr no tiene el problema de sync que sí tienen otras tablas.",
    },
    {
        "label": "investment por país",
        "sql_const": "_SQL_INVESTMENT",
        "metabase_tables": ["dm_strategic.fact_cac_version_segments"],
        "status": "exact_with_data_lag",
        "notes": "Re-verificado 2026-07-10 (abr-jun 2026, prueba real post-migración): abril "
                 "match exacto (18/18 filas). Mayo presente pero con diferencias pequeñas de "
                 "centavos/decenas de dólar en casi todas las filas (ej. colombia/Core "
                 "$208,156.73 en Metabase vs $208,168.46 en RS, diff -$11.73) — mismo patrón de "
                 "sync incompleto que accountant_master_table. **Junio 2026 falta por completo "
                 "en Metabase (0 de 20 filas)** — esta tabla no se ha sincronizado para el mes "
                 "en curso. Antes de usar este número para un board de un mes reciente, correr "
                 "el freshness check (F1.3) y no asumir que 'la tabla existe' = 'tiene el mes'.",
    },
    {
        "label": "tasas FX (tb_trm_banrep)",
        "sql_const": "_SQL_FX_BANREP",
        "metabase_tables": ["dm_strategic.tb_trm_banrep"],
        "status": "exact",
        "notes": "Re-verificado 2026-07-10 (misma sesión, después del sync manual que disparó el "
                 "usuario): 0 diff exacto para 2026-01 a 2026-06 contra Redshift, incluido el mes "
                 "que antes faltaba (2026-06). El desfase anterior fue puntual, no estructural — "
                 "esta tabla no tiene el problema de refresh diario que sí tiene "
                 "accountant_master_table (ver abajo). Igual, verificar MAX(month) en freshness "
                 "antes de confiar ciegamente en el mes más reciente.",
    },
    {
        "label": "ARR Alanube (fact_alanube_arr_walk)",
        "sql_const": "_SQL_ALANUBE_ARR",
        "metabase_tables": ["dm_alanube.fact_alanube_arr_walk"],
        "status": "exact",
        "notes": "SUM(arr_local) excepto event_type='C', agregado por mes. Re-verificado "
                 "2026-07-10: serie histórica COMPLETA (31 meses, nov-2023 a may-2026), 31/31 "
                 "valores exactos contra Redshift, sin ningún desfase.",
    },
    {
        "label": "Alanube ARR Walk completo (fact_alanube_arr_walk)",
        "sql_const": "load_alanube_walk_raw (SQL inline)",
        "metabase_tables": ["dm_alanube.fact_alanube_arr_walk"],
        "status": "exact",
        "notes": "Grano cliente×mes completo (~3.5K filas), 0 diff (spot-check CLOUDYA SRL). "
                 "Re-verificado 2026-07-10 (mayo-2026, agregado por event_type): 297 filas "
                 "totales, 6 categorías (C/D/N/R/U/vacío), count+sum exactos en las 6 — 0 "
                 "diferencias. Nota: Metabase representa el event_type vacío como NULL, "
                 "Redshift como string vacío '' — mismo dato, solo distinta representación del "
                 "vacío entre motores, no afecta la agregación.",
    },
    {
        "label": "Payback (bi_strategic.payback_cohort_results)",
        "sql_const": "load_payback (SQL inline)",
        "metabase_tables": ["dm_strategic.payback_cohort_results"],
        "status": "exact",
        "notes": "15 dimensiones, filtro model='nc', 0 diff. Re-verificado 2026-07-10: las 15 "
                 "dimensiones, COUNT(*)=54 y SUM(pb_base) cada una, 0 diferencias en todas.",
    },
    {
        "label": "Headcount EoP (fact_headcount_eop)",
        "sql_const": "load_headcount_eop (SQL inline)",
        "metabase_tables": ["dm_strategic.fact_headcount_eop"],
        "status": "exact",
        "notes": "21 equipos, conteo total 1659, 0 diff. Re-verificado 2026-07-10 (SUM(headcount) "
                 "+ COUNT DISTINCT team por mes, abr/may-2026): 508/21 y 509/21, 0 diferencias.",
    },
    {
        "label": "Headcount Forecast (fact_headcount_forecast)",
        "sql_const": "load_headcount_forecast (SQL inline)",
        "metabase_tables": ["dm_strategic.fact_headcount_forecast"],
        "status": "exact",
        "notes": "156 filas, conteo exacto. Re-verificado 2026-07-10 (SUM(headcount_fcst) + "
                 "COUNT DISTINCT team, abr/may-2026): 572/13 y 573/13, 0 diferencias.",
    },
    {
        "label": "Headcount Movements (fact_headcount_movements)",
        "sql_const": "load_headcount_movements (SQL inline)",
        "metabase_tables": ["dm_strategic.fact_headcount_movements"],
        "status": "exact",
        "notes": "2268 filas, conteo exacto. Re-verificado 2026-07-10 (SUM(new_hires)/SUM(attrition)"
                 "/COUNT DISTINCT team, abr/may-2026): (10,14,18) y (11,11,18), 0 diferencias.",
    },
    {
        "label": "Headcount categorías (dim_headcount_team_category)",
        "sql_const": "load_headcount_categories (SQL inline)",
        "metabase_tables": ["dm_strategic.dim_headcount_team_category"],
        "status": "exact",
        "notes": "21 filas, dimensión estática sin fecha, conteo exacto. Re-verificado 2026-07-10 "
                 "(COUNT DISTINCT team=21, category=6), 0 diferencias.",
    },
    {
        "label": "retention churn (dm_retention, cluster-1)",
        "sql_const": "_SQL_RETENTION_CHURN",
        "metabase_tables": ["dm_retention.bi_customer_monthly_status"],
        "status": "exact",
        "notes": "22/23 filas exactas — 1 fila con NULL-vs-0 en un caso borde (segment=null), "
                 "no es bug de traducción. Ya no aplica la distinción de 'cluster-1' (era solo "
                 "para enrutar la conexión RS, que ya no existe) — mismo schema en Metabase. "
                 "Re-verificado 2026-07-10 (prueba real post-migración, un mes fijo en vez del "
                 "self-join histórico completo): mayo-2026, 23/23 filas, 3 métricas cada una "
                 "(logos_churned/reactivated/bop) — 69/69 números exactos contra Redshift "
                 "(cluster-1, bi_data_source/data-redshift-cluster). Nota de sintaxis: al "
                 "referenciar el resultado de un join en una expresión (bop_join = field con "
                 "join-alias), agregarlo con MAX()/otra agregación en el stage principal — "
                 "listarlo en 'fields' junto con 'aggregation'/'breakout' hace que el motor lo "
                 "descarte silenciosamente del SELECT final (columna ausente sin error).",
    },
    {
        "label": "product performance (6_rd)",
        "sql_const": "_SQL_PRODUCT_PERF",
        "metabase_tables": ["dm_strategic.fact_customers_mrr"],
        "status": "exact",
        "notes": "8/8 filas, incluye la base del LAG de bop_subs (mismo patrón self-join de "
                 "fact_summary). Re-verificado 2026-07-10 (prueba real post-migración) para "
                 "mayo-2026: 4 productos × 7 métricas (eop_subs, bop_subs, churn_logos, "
                 "react_logos, new_logos, new_mrr, core_subs) — 28/28 valores exactos. "
                 "`LAG() OVER (PARTITION BY product_name ORDER BY date_month)` con gap fijo de 1 "
                 "mes se resuelve con el mismo patrón ya usado en retention_churn: self-join "
                 "simple a un mes fijo (no hace falta el truco de desigualdad+MAX, que es solo "
                 "para gaps arbitrarios).",
    },
    {
        "label": "funnel signups (bi_sales)",
        "sql_const": "_SQL_FUNNEL_SIGNUPS",
        "metabase_tables": ["dm_sales.sales_actions"],
        "status": "exact",
        "notes": "0 diff. Re-verificado 2026-07-10 para mayo-2026: 4 países, 0 diferencias "
                 "(colombia=5480, costaRica=512, mexico=2599, republicaDominicana=2066).",
    },
    {
        "label": "funnel new logos (bi_sales)",
        "sql_const": "_SQL_FUNNEL_LOGOS",
        "metabase_tables": ["dm_sales.fact_closed_deals"],
        "status": "exact",
        "notes": "0 diff. Re-verificado 2026-07-10 para mayo-2026: 4 países, 0 diferencias "
                 "(colombia=1441, costaRica=105, mexico=281, republicaDominicana=368). Nota: el "
                 "fingerprint de Metabase para close_date muestra 'latest: 2026-02-10' (metadata "
                 "de perfilado, no se actualiza en vivo) pero la query sí devuelve filas reales "
                 "de mayo-2026 — no tomar el fingerprint como indicador de freshness real, usar "
                 "siempre una query MAX(fecha) explícita (como hace phase1_freshness.py).",
    },
    {
        "label": "Churned by tenure (db_retention.bi_churn_retired)",
        "sql_const": "_SQL_CHURN_TENURE",
        "metabase_tables": ["dm_retention.bi_churn_retired", "dm_strategic.fact_customers_mrr"],
        "status": "assembled_exact",
        "notes": "churn_agg 24/24 filas exactas, bop 25/25 filas exactas (incluye Otro/M49+=1), "
                 "FULL OUTER JOIN final ya probado como primitivo aislado. Cuidado con el filtro "
                 "event_product NOT IN (...) del CTE fp — debe ser '!=' (not-null-safe si hace "
                 "falta), un '=' invertido colapsa fp_month a NULL y todo cae en M49+ (bug real "
                 "encontrado y corregido en esta sesión). Alimenta 8_appendix.j2 vía "
                 "_build_churn_tenure() Y scripts/update_appendix.py (ver cache['appendix']).",
    },
    {
        "label": "flywheel entities+logos",
        "sql_const": "_SQL_FLYWHEEL",
        "metabase_tables": [
            "dm_strategic.fact_customers_mrr",
            "dm_sales.companies_relation_ids",
            "dm_sales.associations_accounting_entities_to_companies",
        ],
        "status": "exact",
        "notes": "La más compleja del pipeline completo (empatada con fact_summary). LAG/"
                 "ROW_NUMBER con gaps arbitrarios reemplazado por self-join con desigualdad "
                 "(date_month < cutoff) + MAX(date_month) — funciona solo fijando el cutoff a un "
                 "mes a la vez (no como query histórica única), que es exactamente cómo corre "
                 "fetch_metrics.py. churned_logos resuelto con anti-join (LEFT JOIN + is-null), "
                 "no NOT EXISTS. Validada dos veces, en dos sesiones distintas, ambas 5/5 exacto a "
                 "nivel logo: abril-2026 (stock=14804, new=546, reactivated=344, recovered=191, "
                 "churned=902) y mayo-2026, re-verificada 2026-07-10 (stock=15010, new=621, "
                 "reactivated=313, recovered=161, churned=889) — el join a "
                 "companies_relation_ids/associations_accounting_entities_to_companies (con un "
                 "cruce de tipos varchar↔bigint sin cast explícito, que compiló sin problema) "
                 "también confirmado estable. Nivel entidad (ent_*) NO se probó por separado — "
                 "mismo patrón, agrupando por entity_id en vez de logo_id.",
    },
    {
        "label": "SC histórico stock (accountant_master)",
        "sql_const": "_SQL_SC_HIST",
        "metabase_tables": ["dm_accountant.accountant_master_table"],
        "status": "exact_with_data_lag",
        "notes": "Diferencia real, RECURRENTE — confirmada dos veces en días distintos, con "
                 "signo y magnitud distintos cada vez (no es un desfase fijo que se pueda "
                 "descontar): 2026-07-10 (primera prueba) 7794 vs 7779 (Metabase por ENCIMA de "
                 "RS). Re-verificado la misma tarde para abr/may/jun-2026: Metabase "
                 "(7794,7929,7993) vs RS (7779,7933,7988) — abril Metabase por encima, mayo y "
                 "junio por DEBAJO. Confirma que es el refresh diario TRUNCATE+INSERT de la "
                 "tabla (ambas fuentes son un moving target, no un desfase estático) — no es un "
                 "bug de traducción MBQL. Para cualquier corrida real, correr freshness (MAX/"
                 "COUNT del mes) inmediatamente antes de fetch_metrics.py y aceptar que puede "
                 "haber una diferencia de bajo % vs. lo que alguien vea consultando RS en otro "
                 "momento del mismo día.",
    },
    {
        "label": "SC top-20 SoW",
        "sql_const": "_SQL_SOW_TOP20",
        "metabase_tables": ["dm_accountant.accountant_master_table"],
        "status": "exact_with_data_lag",
        "notes": "18/20 exacto (mismo rank/nombre/MRR/logos) — las 2 que difieren (Yenny, "
                 "FTAVAREZ) son la misma causa que SC histórico (desfase de sync de "
                 "accountant_master_table). order-by de un ranking con >1 agregación debe "
                 "referenciarse por índice (['aggregation', {}, 1]), no por nombre bare-string "
                 "('sum') — bug real del compilador de este conector si hay ambigüedad. "
                 "**Re-confirmado 2026-07-10** (ranking core: real_logos+mrr vía ORDER BY "
                 "DESC+LIMIT 20, abril-2026): 18/20 filas exactas — las 2 discrepancias son, "
                 "otra vez, exactamente Yenny y FTAVAREZ (mismo id_entity, mismo nombre, valores "
                 "distintos de pipeline_stage/real_logos/mrr) — confirma que NO es una "
                 "coincidencia de una sola sesión, es un desfase recurrente y predecible de esta "
                 "tabla específica.",
    },
    {
        "label": "SC value events mensuales (amplitude)",
        "sql_const": "_SQL_VALUE_EVENTS (simplificada — ver nota)",
        "metabase_tables": ["dm_accountant.accountant_master_table", "dm_accountant.value_events_monthly"],
        "status": "exact_with_data_lag",
        "notes": "RESUELTA 2026-07-14 sin esperar al equipo de contadores: en vez de la tabla "
                 "cruda db_amplitude_events.amplitude_ac_events (nunca copiada a Metabase), el "
                 "usuario creó bi_accountant.value_events_monthly (grano id_company×event_name×"
                 "mes, is_attr ya resuelto) — apareció en Metabase el 2026-07-11 como "
                 "dm_accountant.value_events_monthly. El CTE `active` sigue leyendo "
                 "accountant_master_table sin cambios; `ev_monthly` pasó de agregar la cruda a "
                 "un SELECT directo de la tabla nueva (ya no hace falta agregación, el grano ya "
                 "es el correcto). Validada para mayo-2026 (single-month, ventana marzo-mayo "
                 "para el join de -2 meses): nl=280, no_=132, nx=54, nge3=204 exactos; "
                 "total=7940 vs 7948, nf/nj/nw/nk/nge1/nge2 con diff de -1 (~0.1%) — MISMA causa "
                 "raíz ya documentada del desfase de sync de accountant_master_table (refresh "
                 "diario TRUNCATE+INSERT), no un bug de traducción MBQL. Con esto, "
                 "20/20 queries del inventario quedan migradas.",
    },
]

# ── FRESHNESS — cache["freshness"][check_id], consumidas por phase1_freshness.py ─────────
# Cada entrada: {"n": <COUNT(*) del mes objetivo>, "max_date": <MAX(fecha) visto en la tabla>}
#
# Derivada de phase1_freshness._CHECKS (única fuente de verdad, hallazgo 2026-07-14) — antes
# esto era una lista de 13 tuplas mantenida a mano por separado, sin nada que avisara si se
# desincronizaba de lo que el pipeline realmente valida. (check_id, tabla, columna de fecha).
FRESHNESS_CHECKS = [
    (check_id, table, date_column)
    for check_id, _label, table, _fail_status, date_column in _FRESHNESS_CHECKS_SOURCE
]

# ── F1.14 — validación de forma del cache["queries"] (hallazgo #5, 2026-07-14) ───────────
# NO requiere correr ninguna query nueva vía el MCP — se calcula solo, en Fase 1, a partir
# de las ~20 queries de negocio que ya se pusieron en cache["queries"]. Versión ACOTADA a
# propósito (decisión del usuario 2026-07-14): detecta resultados vacíos, filas que no son
# objetos, y filas donde TODOS los campos son None/vacíos — sin conocer el schema real de
# columnas/tipos de cada query.
#
# PENDIENTE REAL (explícitamente NO descartado, el usuario pidió que quede documentado):
# la versión completa necesita, para cada una de las ~20 entradas de QUERIES arriba, el
# schema esperado — qué columnas debe tener cada fila y de qué tipo (numérico, fecha,
# string) — y validarlo en Fase 1 contra cada fila real del cache. Eso permitiría detectar
# cosas que la versión acotada NO detecta: un nombre de columna mal escrito (ej. "pb" en
# vez de "pb_base" — la fila igual pasa el chequeo de "no está en blanco" si tiene OTRAS
# columnas con datos), o que una query puntual tenga datos de un mes distinto al resto
# (hoy solo se valida cache["month"], un campo global, no por query). Ver
# board_agent/phase1_freshness.py::_check_query_shapes() para la implementación actual.

# ── VALIDATOR — cache["validator"][check_id], consumidas por phase4_validator.py ─────────
VALIDATOR_CHECKS = [
    {
        "check_id": "R7",
        "keys": ["logos_eop"],
        "metabase_tables": ["dm_strategic.fact_customers_mrr"],
        "notes": "COUNT(DISTINCT id_company) con los mismos filtros que 'logos consolidados' "
                 "arriba, pero corrida como verificación independiente (no reusa el resultado de "
                 "esa query). Validado 2026-07-03 contra mayo-26 real: 58,974 = 58,974.",
    },
]

# ── APPENDIX — cache["appendix"][month], consumida por scripts/update_appendix.py ───────
# Mismo patrón que "Churned by tenure" de QUERIES (churn_agg solamente, sin el bop) pero
# corrida para UN mes específico cada vez que alguien actualiza 8_appendix.j2 manualmente.
APPENDIX_SPEC = {
    "metabase_tables": ["dm_retention.bi_churn_retired", "dm_strategic.fact_customers_mrr"],
    "row_shape": {"segmento": "Core | Lite | Otro", "bracket": "M1-M3 | M4-M6 | ... | M49+",
                  "logos_churn": "int"},
    "notes": "scripts/update_appendix.py --month YYYY-MM espera cache['appendix']['YYYY-MM'] "
             "poblado antes de correr — puede tener varias entradas de distintos meses a la vez.",
}
