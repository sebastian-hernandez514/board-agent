# Board 2026-08 — v38
Generado: 2026-09-29T17:11:18

## Fase 4 — Business Rules Validator
✅ [R1] ARR total incluye Alanube — arr_total=34,700,000 vs alegra+alanube=34,692,578 (diff=7,422)
⏭️ [R3] ARR Walk balancea (buckets = Net New ARR = EoP-BoP) — error: 'no se encontró la sección del ARR Walk GLO en arr_walk_table'
⏭️ [R4] Net Churn es negativo — error: 'no se encontró la sección del ARR Walk GLO en arr_walk_table'
⏭️ [R6] FX residual < $3M — error: 'no se encontró la sección del ARR Walk GLO en arr_walk_table'
⏭️ [R8] ARR EoP (Constant Currency) = ARR EoP en el mes de corte — error: 'no se encontró la sección del ARR Walk GLO en arr_walk_table'
✅ [R9] is_quarter_end consistente con el mes de corte — cutoff_month=2026-08 → esperado=False, metrics.yaml=False
✅ [R10] Logo Churn Global entre 0.0% y 20.0% — logo_churn_global=3.8%
✅ [R7] Logos EoP = COUNT DISTINCT dedup (verificación independiente) — metrics.yaml=60,190 vs Metabase independiente=60,190 (diff=+0)
⏭️ [R11] Budget CSV completo para el quarter (parcial) — mes de corte no es cierre de quarter
✅ [R17] P&L (Net Revenue/Gross Margin/EBITDA) presente — net_revenue=$2.9M gross_margin=81.4% ebitda_margin=12.3%
✅ [R12] ~47 slides en el standalone — encontrados=45
✅ [R13] Investment: delta neutro (sin verde/rojo) — 20 celdas verificadas, todas correctas
✅ [R14] Churn/CAC: delta invertido — 40 celdas verificadas, todas correctas
✅ [R15] Resto de métricas: signo estándar de color — 136 celdas verificadas, todas correctas
✅ [R16] Ningún slide-shell fuerza dimensión px inline — 44 slides verificados, sin overrides de dimensión
⏭️ [R18] Ningún slide-shell recorta contenido en silencio (overflow) — playwright no está instalado — correr con 'uv run --with playwright python run.py ...' para habilitar esta regla
✅ [R19] ARR EoP coincide entre Monthly Performance y YTD Performance — ambas slides muestran $34.7M
✅ [R20] Stock Core+Lite = GLO, mes a mes — 161 meses verificados, todos cuadran
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Core ARR EoP — reportado=$14,687,214 vs ARR Walk v2=$14,687,776 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Core Logos EoP — reportado=18,777 vs ARR Walk v2=18,777 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Lite ARR EoP — reportado=$8,158,929 vs ARR Walk v2=$8,159,241 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Lite Logos EoP — reportado=26,242 vs ARR Walk v2=26,242 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Core ARR EoP — reportado=$1,703,032 vs ARR Walk v2=$1,701,649 (diff=+0.08%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Core Logos EoP — reportado=2,124 vs ARR Walk v2=2,124 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Lite ARR EoP — reportado=$1,248,510 vs ARR Walk v2=$1,247,496 (diff=+0.08%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Lite Logos EoP — reportado=3,121 vs ARR Walk v2=3,121 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Core ARR EoP — reportado=$2,949,965 vs ARR Walk v2=$2,949,965 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Core Logos EoP — reportado=2,112 vs ARR Walk v2=2,112 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Lite ARR EoP — reportado=$1,918,410 vs ARR Walk v2=$1,918,410 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Lite Logos EoP — reportado=2,727 vs ARR Walk v2=2,727 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Core ARR EoP — reportado=$529,056 vs ARR Walk v2=$529,056 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Core Logos EoP — reportado=622 vs ARR Walk v2=622 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Lite ARR EoP — reportado=$424,521 vs ARR Walk v2=$424,521 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Lite Logos EoP — reportado=1,034 vs ARR Walk v2=1,034 (diff=+0.00%)
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos New — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos Recovered — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos Reactivated — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos Churn — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR New — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR Recovered — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR Reactivated — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR Churn — 1 meses verificados, todos cuadran

## Fase 5 — Diff Review
✅ [D1] ARR total variación ≤ 5.0% — arr_mom=4.1%
✅ [D2] Logos EoP variación ≤ 3.0% — 59.8k → 60.2k (+0.7%)
✅ [D3] Churn Rate variación ≤ 1.0pp — 3.9% → 3.8% (-0.1pp)
✅ [D4] New Logos YoY dentro de ±30.0% — new_logos_yoy=11.4%
✅ [D5] FX Impact absoluto ≤ $2M — fx_impact=1,000,000
✅ [D6] Sugerencia de versión — 37 versión(es) ya en 2026-08/ → sugerido v38 (última: v37)
✅ [D7] Lista de slides que cambiaron vs board anterior — vs board_Aug_2026_v37.html — 1/44 cambiaron: [1]
