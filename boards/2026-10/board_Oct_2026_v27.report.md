# Board 2026-10 — v27
Generado: 2026-11-18T07:20:16

## Fase 4 — Business Rules Validator
✅ [R1] ARR total incluye Alanube — arr_total=34,700,000 vs alegra+alanube=34,684,137 (diff=15,863)
✅ [R3] ARR Walk balancea (buckets = Net New ARR = EoP-BoP) — buckets=200,000 vs netNewARR=100,000 (diff=100,000); EoP-BoP=100,000 vs netNewARR=100,000 (diff=0)
✅ [R4] Net Churn es negativo — net_churn=-1,000,000
✅ [R6] FX residual < $3M — fx_impact=-300,000
✅ [R8] ARR EoP (Constant Currency) = ARR EoP en el mes de corte — eop_cc=33,500,000 vs eop=33,500,000 (diff=0)
✅ [R9] is_quarter_end consistente con el mes de corte — cutoff_month=2026-10 → esperado=False, metrics.yaml=False
✅ [R10] Logo Churn Global entre 0.0% y 20.0% — logo_churn_global=3.8%
✅ [R7] Logos EoP = COUNT DISTINCT dedup (verificación independiente) — metrics.yaml=61,747 vs Metabase independiente=61,747 (diff=+0)
⏭️ [R11] Budget CSV completo para el quarter (parcial) — mes de corte no es cierre de quarter
✅ [R17] P&L (Net Revenue/Gross Margin/EBITDA) presente — net_revenue=$2.9M gross_margin=80.3% ebitda_margin=2.0%
⚠️ [R12] ~47 slides en el standalone — encontrados=41
✅ [R13] Investment: delta neutro (sin verde/rojo) — 16 celdas verificadas, todas correctas
✅ [R14] Churn/CAC: delta invertido — 32 celdas verificadas, todas correctas
✅ [R15] Resto de métricas: signo estándar de color — 112 celdas verificadas, todas correctas
✅ [R16] Ningún slide-shell fuerza dimensión px inline — 31 slides verificados, sin overrides de dimensión
⏭️ [R18] Ningún slide-shell recorta contenido en silencio (overflow) — playwright no está instalado — correr con 'uv run --with playwright python run.py ...' para habilitar esta regla
✅ [R19] ARR EoP coincide entre Monthly Performance y YTD Performance — ambas slides muestran $34.7M
✅ [R20] Stock Core+Lite = GLO, mes a mes — 163 meses verificados, todos cuadran
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Core ARR EoP — reportado=$14,620,464 vs ARR Walk v2=$14,620,886 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Core Logos EoP — reportado=19,391 vs ARR Walk v2=19,391 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Lite ARR EoP — reportado=$7,860,248 vs ARR Walk v2=$7,860,475 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Lite Logos EoP — reportado=26,468 vs ARR Walk v2=26,468 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Core ARR EoP — reportado=$1,632,685 vs ARR Walk v2=$1,636,975 (diff=+0.26%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Core Logos EoP — reportado=2,208 vs ARR Walk v2=2,208 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Lite ARR EoP — reportado=$1,190,460 vs ARR Walk v2=$1,193,588 (diff=+0.26%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Lite Logos EoP — reportado=3,252 vs ARR Walk v2=3,252 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Core ARR EoP — reportado=$3,141,648 vs ARR Walk v2=$3,141,648 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Core Logos EoP — reportado=2,281 vs ARR Walk v2=2,281 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Lite ARR EoP — reportado=$2,170,070 vs ARR Walk v2=$2,170,070 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Lite Logos EoP — reportado=3,013 vs ARR Walk v2=3,013 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Core ARR EoP — reportado=$551,251 vs ARR Walk v2=$551,251 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Core Logos EoP — reportado=663 vs ARR Walk v2=663 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Lite ARR EoP — reportado=$432,491 vs ARR Walk v2=$432,491 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Lite Logos EoP — reportado=1,088 vs ARR Walk v2=1,088 (diff=+0.00%)
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos New — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos Recovered — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos Reactivated — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — Logos Churn — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR New — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR Recovered — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR Reactivated — 1 meses verificados, todos cuadran
✅ [R22] Flujo Core+Lite = GLO, mes a mes (aditivo) — MRR Churn — 1 meses verificados, todos cuadran

## Fase 5 — Diff Review
✅ [D1] ARR total variación ≤ 5.0% — arr_mom=0.5%
✅ [D2] Logos EoP variación ≤ 3.0% — 60.7k → 61.7k (+1.6%)
✅ [D3] Churn Rate variación ≤ 1.0pp — 4.3% → 3.8% (-0.5pp)
✅ [D4] New Logos YoY dentro de ±30.0% — new_logos_yoy=28.4%
✅ [D5] FX Impact absoluto ≤ $2M — fx_impact=-300,000
✅ [D6] Sugerencia de versión — 26 versión(es) ya en 2026-10/ → sugerido v27 (última: v26)
✅ [D7] Lista de slides que cambiaron vs board anterior — vs board_Oct_2026_v26.html — 3/41 cambiaron: [1, 5, 6]
