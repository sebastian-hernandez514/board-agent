# Board 2026-06 — v36
Generado: 2026-07-27T20:01:06

## Fase 4 — Business Rules Validator
✅ [R1] ARR total incluye Alanube — arr_total=31,000,000 vs alegra+alanube=30,998,602 (diff=1,398)
✅ [R3] ARR Walk balancea (buckets = Net New ARR = EoP-BoP) — buckets=2,700,000 vs netNewARR=2,700,000 (diff=0); EoP-BoP=2,700,000 vs netNewARR=2,700,000 (diff=0)
✅ [R4] Net Churn es negativo — net_churn=-2,800,000
✅ [R6] FX residual < $3M — fx_impact=1,100,000
✅ [R8] ARR EoP (Constant Currency) = ARR EoP en el mes de corte — eop_cc=30,000,000 vs eop=30,000,000 (diff=0)
✅ [R9] is_quarter_end consistente con el mes de corte — cutoff_month=2026-06 → esperado=True, metrics.yaml=True
✅ [R10] Logo Churn Global entre 0.0% y 20.0% — logo_churn_global=4.1%
✅ [R7] Logos EoP = COUNT DISTINCT dedup (verificación independiente) — metrics.yaml=59,283 vs Metabase independiente=59,283 (diff=+0)
✅ [R11] Budget CSV completo para el quarter (parcial, solo ARR EoP) — completo: ['Apr - 26', 'May - 26', 'Jun - 26']
✅ [R17] P&L (Net Revenue/Gross Margin/EBITDA) presente — net_revenue=$7.4M gross_margin=81.1% ebitda_margin=9.7%
✅ [R12] ~47 slides en el standalone — encontrados=54
✅ [R13] Investment: delta neutro (sin verde/rojo) — 20 celdas verificadas, todas correctas
✅ [R14] Churn/CAC: delta invertido — 40 celdas verificadas, todas correctas
✅ [R15] Resto de métricas: signo estándar de color — 120 celdas verificadas, todas correctas
✅ [R16] Ningún slide-shell fuerza dimensión px inline — 53 slides verificados, sin overrides de dimensión
⚠️ [R18] Ningún slide-shell recorta contenido en silencio (overflow) — 2/53 slides con contenido desbordado: "slide" (+6px vert, +0px horiz) "2Q26 PERFORMANCE
GROWTH
ARR
$31.0M
QoQ
+9.8%
·
Bud
+7.1%
YoY"; "slide" (+6px vert, +0px horiz) "YTD PERFORMANCE · 2026
GROWTH
ARR
$31.0M
Bud
+7.1%
YoY
+32.5"
✅ [R19] ARR EoP coincide entre Monthly Performance y YTD Performance — ambas slides muestran $31.0M
✅ [R20] Stock Core+Lite = GLO, mes a mes — 159 meses verificados, todos cuadran
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Core ARR EoP — reportado=$11,872,176 vs ARR Walk v2=$11,876,390 (diff=+0.04%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Core Logos EoP — reportado=17,516 vs ARR Walk v2=17,519 (diff=+0.02%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Lite ARR EoP — reportado=$7,742,353 vs ARR Walk v2=$7,748,018 (diff=+0.07%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Colombia Lite Logos EoP — reportado=26,949 vs ARR Walk v2=26,959 (diff=+0.04%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Core ARR EoP — reportado=$1,607,792 vs ARR Walk v2=$1,610,403 (diff=+0.16%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Core Logos EoP — reportado=1,996 vs ARR Walk v2=1,996 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Lite ARR EoP — reportado=$1,201,268 vs ARR Walk v2=$1,204,227 (diff=+0.25%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — México Lite Logos EoP — reportado=2,982 vs ARR Walk v2=2,983 (diff=+0.03%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Core ARR EoP — reportado=$2,644,854 vs ARR Walk v2=$2,646,541 (diff=+0.06%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Core Logos EoP — reportado=1,850 vs ARR Walk v2=1,851 (diff=+0.05%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Lite ARR EoP — reportado=$2,236,621 vs ARR Walk v2=$2,236,180 (diff=+0.02%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Rep. Dominicana Lite Logos EoP — reportado=3,020 vs ARR Walk v2=3,020 (diff=+0.00%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Core ARR EoP — reportado=$496,498 vs ARR Walk v2=$497,559 (diff=+0.21%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Core Logos EoP — reportado=594 vs ARR Walk v2=596 (diff=+0.34%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Lite ARR EoP — reportado=$403,855 vs ARR Walk v2=$403,402 (diff=+0.11%)
✅ [R21] Country Performance: stock vs ARR Walk v2 (verificación cruzada) — Costa Rica Lite Logos EoP — reportado=956 vs ARR Walk v2=955 (diff=+0.10%)

## Fase 5 — Diff Review
⚠️ [D1] ARR total variación ≤ 5.0% — arr_qoq=9.8%
✅ [D2] Logos EoP variación ≤ 3.0% — 57.6k → 59.3k (+3.0%)
✅ [D3] Churn Rate variación ≤ 1.0pp — 4.8% → 4.1% (-0.7pp)
✅ [D4] New Logos YoY dentro de ±30.0% — new_logos_yoy=23.1%
✅ [D5] FX Impact absoluto ≤ $2M — fx_impact=1,100,000
✅ [D6] Sugerencia de versión — 35 versión(es) ya en 2026-06/ → sugerido v36 (última: v35)
✅ [D7] Lista de slides que cambiaron vs board anterior — vs board_Jun_2026_v35.html — 2/53 cambiaron: [1, 9]
