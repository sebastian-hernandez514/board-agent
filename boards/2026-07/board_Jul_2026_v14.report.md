# Board 2026-07 — v14
Generado: 2026-08-18T18:53:20

## Fase 4 — Business Rules Validator
✅ [R1] ARR total incluye Alanube — arr_total=33,300,000 vs alegra+alanube=33,256,326 (diff=43,674)
✅ [R3] ARR Walk balancea (buckets = Net New ARR = EoP-BoP) — buckets=2,200,000 vs netNewARR=2,100,000 (diff=100,000); EoP-BoP=2,100,000 vs netNewARR=2,100,000 (diff=0)
✅ [R4] Net Churn es negativo — net_churn=-1,000,000
✅ [R6] FX residual < $3M — fx_impact=1,400,000
✅ [R8] ARR EoP (Constant Currency) = ARR EoP en el mes de corte — eop_cc=32,100,000 vs eop=32,100,000 (diff=0)
✅ [R9] is_quarter_end consistente con el mes de corte — cutoff_month=2026-07 → esperado=False, metrics.yaml=False
✅ [R10] Logo Churn Global entre 0.0% y 20.0% — logo_churn_global=3.9%
✅ [R7] Logos EoP = COUNT DISTINCT dedup (verificación independiente) — metrics.yaml=59,777 vs Metabase independiente=59,777 (diff=+0)
⏭️ [R11] Budget CSV completo para el quarter (parcial) — mes de corte no es cierre de quarter
✅ [R17] P&L (Net Revenue/Gross Margin/EBITDA) presente — net_revenue=$2.8M gross_margin=83.5% ebitda_margin=17.4%
⚠️ [R12] ~47 slides en el standalone — encontrados=41
✅ [R13] Investment: delta neutro (sin verde/rojo) — 20 celdas verificadas, todas correctas
✅ [R14] Churn/CAC: delta invertido — 40 celdas verificadas, todas correctas
✅ [R15] Resto de métricas: signo estándar de color — 118 celdas verificadas, todas correctas
✅ [R16] Ningún slide-shell fuerza dimensión px inline — 40 slides verificados, sin overrides de dimensión
⏭️ [R18] Ningún slide-shell recorta contenido en silencio (overflow) — playwright no está instalado — correr con 'uv run --with playwright python run.py ...' para habilitar esta regla
✅ [R19] ARR EoP coincide entre Monthly Performance y YTD Performance — ambas slides muestran $33.3M
✅ [R20] Stock Core+Lite = GLO, mes a mes — 160 meses verificados, todos cuadran
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Core ARR EoP — reportado=$13,882,590 vs ARR Walk v2=$13,882,790 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Core Logos EoP — reportado=18,495 vs ARR Walk v2=18,495 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Lite ARR EoP — reportado=$7,937,802 vs ARR Walk v2=$7,937,917 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Lite Logos EoP — reportado=26,381 vs ARR Walk v2=26,381 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Core ARR EoP — reportado=$1,621,947 vs ARR Walk v2=$1,624,214 (diff=+0.14%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Core Logos EoP — reportado=2,064 vs ARR Walk v2=2,064 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Lite ARR EoP — reportado=$1,206,110 vs ARR Walk v2=$1,207,796 (diff=+0.14%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Lite Logos EoP — reportado=3,058 vs ARR Walk v2=3,058 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Core ARR EoP — reportado=$2,892,689 vs ARR Walk v2=$2,892,689 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Core Logos EoP — reportado=2,071 vs ARR Walk v2=2,071 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Lite ARR EoP — reportado=$1,882,713 vs ARR Walk v2=$1,882,713 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Lite Logos EoP — reportado=2,677 vs ARR Walk v2=2,677 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Core ARR EoP — reportado=$518,144 vs ARR Walk v2=$518,144 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Core Logos EoP — reportado=621 vs ARR Walk v2=621 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Lite ARR EoP — reportado=$405,661 vs ARR Walk v2=$405,661 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Lite Logos EoP — reportado=999 vs ARR Walk v2=999 (diff=+0.00%)
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos New — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos Recovered — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos Reactivated — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos Churn — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR New — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR Recovered — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR Reactivated — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR Churn — 1 meses verificados, todos cuadran

## Fase 5 — Diff Review
⚠️ [D1] ARR total variación ≤ 5.0% — arr_mom=7.2%
✅ [D2] Logos EoP variación ≤ 3.0% — 59.3k → 59.8k (+0.8%)
✅ [D3] Churn Rate variación ≤ 1.0pp — 4.1% → 3.9% (-0.2pp)
✅ [D4] New Logos YoY dentro de ±30.0% — new_logos_yoy=2.8%
✅ [D5] FX Impact absoluto ≤ $2M — fx_impact=1,400,000
✅ [D6] Sugerencia de versión — 13 versión(es) ya en 2026-07/ → sugerido v14 (última: v13)
✅ [D7] Lista de slides que cambiaron vs board anterior — vs board_Jul_2026_v13.html — 2/40 cambiaron: [1, 33]
