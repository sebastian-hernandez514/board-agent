# Board 2026-06 — v11
Generado: 2026-07-24T15:40:51

## Fase 4 — Business Rules Validator
✅ [R1] ARR total incluye Alanube — arr_total=31,000,000 vs alegra+alanube=30,981,770 (diff=18,230)
✅ [R3] ARR Walk balancea (buckets = Net New ARR = EoP-BoP) — buckets=2,700,000 vs netNewARR=2,700,000 (diff=0); EoP-BoP=2,700,000 vs netNewARR=2,700,000 (diff=0)
✅ [R4] Net Churn es negativo — net_churn=-2,800,000
✅ [R6] FX residual < $3M — fx_impact=1,100,000
✅ [R8] ARR EoP (Constant Currency) = ARR EoP en el mes de corte — eop_cc=30,000,000 vs eop=30,000,000 (diff=0)
✅ [R9] is_quarter_end consistente con el mes de corte — cutoff_month=2026-06 → esperado=True, metrics.yaml=True
✅ [R10] Logo Churn Global entre 0.0% y 20.0% — logo_churn_global=3.9%
✅ [R7] Logos EoP = COUNT DISTINCT dedup (verificación independiente) — metrics.yaml=59,283 vs Metabase independiente=59,283 (diff=+0)
✅ [R11] Budget CSV completo para el quarter (parcial, solo ARR EoP) — completo: ['Apr - 26', 'May - 26', 'Jun - 26']
✅ [R17] P&L (Net Revenue/Gross Margin/EBITDA) presente — net_revenue=$7.4M gross_margin=81.1% ebitda_margin=9.7%
✅ [R12] ~47 slides en el standalone — encontrados=48
✅ [R13] Investment: delta neutro (sin verde/rojo) — 20 celdas verificadas, todas correctas
✅ [R14] Churn/CAC: delta invertido — 40 celdas verificadas, todas correctas
✅ [R15] Resto de métricas: signo estándar de color — 120 celdas verificadas, todas correctas
✅ [R16] Ningún slide-shell fuerza dimensión px inline — 47 slides verificados, sin overrides de dimensión
⏭️ [R18] Ningún slide-shell recorta contenido en silencio (overflow) — playwright no está instalado — correr con 'uv run --with playwright python run.py ...' para habilitar esta regla
✅ [R19] ARR EoP coincide entre Monthly Performance y YTD Performance — ambas slides muestran $31.0M

## Fase 5 — Diff Review
⚠️ [D1] ARR total variación ≤ 5.0% — arr_qoq=9.8%
✅ [D2] Logos EoP variación ≤ 3.0% — 57.6k → 59.3k (+3.0%)
✅ [D3] Churn Rate variación ≤ 1.0pp — 4.8% → 3.9% (-0.9pp)
✅ [D4] New Logos YoY dentro de ±30.0% — new_logos_yoy=23.1%
✅ [D5] FX Impact absoluto ≤ $2M — fx_impact=1,100,000
✅ [D6] Sugerencia de versión — 10 versión(es) ya en 2026-06/ → sugerido v11 (última: v10)
✅ [D7] Lista de slides que cambiaron vs board anterior — vs board_Jun_2026_v10.html — 10/47 cambiaron: [1, 5, 6, 7, 8, 9, 17, 18, 22, 31]
