# Board 2026-09 — v77
Generado: 2026-10-27T12:40:14

## Fase 4 — Business Rules Validator
✅ [R1] ARR total incluye Alanube — arr_total=34,500,000 vs alegra+alanube=34,501,978 (diff=-1,978)
✅ [R3] ARR Walk balancea (buckets = Net New ARR = EoP-BoP) — buckets=3,400,000 vs netNewARR=3,400,000 (diff=0); EoP-BoP=3,400,000 vs netNewARR=3,400,000 (diff=0)
✅ [R4] Net Churn es negativo — net_churn=-3,300,000
✅ [R6] FX residual < $3M — fx_impact=2,100,000
✅ [R8] ARR EoP (Constant Currency) = ARR EoP en el mes de corte — eop_cc=33,400,000 vs eop=33,400,000 (diff=0)
✅ [R9] is_quarter_end consistente con el mes de corte — cutoff_month=2026-09 → esperado=True, metrics.yaml=True
✅ [R10] Logo Churn Global entre 0.0% y 20.0% — logo_churn_global=4.1%
✅ [R7] Logos EoP = COUNT DISTINCT dedup (verificación independiente) — metrics.yaml=60,722 vs Metabase independiente=60,722 (diff=+0)
✅ [R11] Budget CSV completo para el quarter (parcial, solo ARR EoP) — completo: ['Jul - 26', 'Aug - 26', 'Sep - 26']
✅ [R17] P&L (Net Revenue/Gross Margin/EBITDA) presente — net_revenue=$8.5M gross_margin=82.4% ebitda_margin=12.5%
⚠️ [R12] ~47 slides en el standalone — encontrados=44
✅ [R13] Investment: delta neutro (sin verde/rojo) — 16 celdas verificadas, todas correctas
✅ [R14] Churn/CAC: delta invertido — 32 celdas verificadas, todas correctas
✅ [R15] Resto de métricas: signo estándar de color — 112 celdas verificadas, todas correctas
✅ [R16] Ningún slide-shell fuerza dimensión px inline — 30 slides verificados, sin overrides de dimensión
⏭️ [R18] Ningún slide-shell recorta contenido en silencio (overflow) — playwright no está instalado — correr con 'uv run --with playwright python run.py ...' para habilitar esta regla
✅ [R19] ARR EoP coincide entre Monthly Performance y YTD Performance — ambas slides muestran $34.5M
✅ [R20] Stock Core+Lite = GLO, mes a mes — 162 meses verificados, todos cuadran
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Core ARR EoP — reportado=$14,410,460 vs ARR Walk v2=$14,411,474 (diff=+0.01%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Core Logos EoP — reportado=19,010 vs ARR Walk v2=19,010 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Lite ARR EoP — reportado=$7,911,287 vs ARR Walk v2=$7,911,843 (diff=+0.01%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Lite Logos EoP — reportado=26,286 vs ARR Walk v2=26,286 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Core ARR EoP — reportado=$1,717,394 vs ARR Walk v2=$1,719,613 (diff=+0.13%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Core Logos EoP — reportado=2,155 vs ARR Walk v2=2,155 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Lite ARR EoP — reportado=$1,261,697 vs ARR Walk v2=$1,263,327 (diff=+0.13%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Lite Logos EoP — reportado=3,206 vs ARR Walk v2=3,206 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Core ARR EoP — reportado=$3,096,164 vs ARR Walk v2=$3,096,164 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Core Logos EoP — reportado=2,175 vs ARR Walk v2=2,175 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Lite ARR EoP — reportado=$2,071,975 vs ARR Walk v2=$2,071,975 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Lite Logos EoP — reportado=2,779 vs ARR Walk v2=2,779 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Core ARR EoP — reportado=$547,222 vs ARR Walk v2=$547,222 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Core Logos EoP — reportado=641 vs ARR Walk v2=641 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Lite ARR EoP — reportado=$423,586 vs ARR Walk v2=$423,586 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Lite Logos EoP — reportado=1,056 vs ARR Walk v2=1,056 (diff=+0.00%)
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos New — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos Recovered — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos Reactivated — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos Churn — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR New — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR Recovered — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR Reactivated — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR Churn — 1 meses verificados, todos cuadran

## Fase 5 — Diff Review
⚠️ [D1] ARR total variación ≤ 5.0% — arr_qoq=11.2%
✅ [D2] Logos EoP variación ≤ 3.0% — 59.3k → 60.7k (+2.4%)
✅ [D3] Churn Rate variación ≤ 1.0pp — 4.1% → 4.1% (+0.0pp)
✅ [D4] New Logos YoY dentro de ±30.0% — new_logos_yoy=18.7%
⚠️ [D5] FX Impact absoluto ≤ $2M — fx_impact=2,100,000
✅ [D6] Sugerencia de versión — 71 versión(es) ya en 2026-09/ → sugerido v77 (última: v76)
✅ [D7] Lista de slides que cambiaron vs board anterior — vs board_Sep_2026_v76.html — 3/44 cambiaron: [1, 14, 15]
