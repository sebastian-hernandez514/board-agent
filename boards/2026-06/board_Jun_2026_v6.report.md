# Board 2026-06 — v6
Generado: 2026-07-21T09:17:28

## Fase 4 — Business Rules Validator
✅ [R1] ARR total incluye Alanube — arr_total=31,000,000 vs alegra+alanube=30,981,770 (diff=18,230)
✅ [R2] New MRR Core + Lite ≈ Total — core=81,000 + lite=140,000 = 221,000 vs total=222,000 (diff=-1,000)
✅ [R3] ARR Walk balancea (buckets = Net New ARR = EoP-BoP) — buckets=700,000 vs netNewARR=700,000 (diff=0); EoP-BoP=700,000 vs netNewARR=700,000 (diff=0)
✅ [R4] Net Churn es negativo — net_churn=-3,300,000
✅ [R6] FX residual < $3M — fx_impact=400,000
✅ [R8] ARR EoP (Constant Currency) = ARR EoP en el mes de corte — eop_cc=27,300,000 vs eop=27,300,000 (diff=0)
⏭️ [R5] cross_down restado en Net Expansion — recomputado=1,124,629 vs mostrado=400,000 (diff=724,629); cross_down=347,119 (debe restarse, no sumarse) — no confiable en cierre de Q: fetch_metrics.py sobreescribe arr_walk_table con el override temporal 'valores del SS Apr-2026' (ver comentario en el código), no es un bug de esta regla
✅ [R9] is_quarter_end consistente con el mes de corte — cutoff_month=2026-06 → esperado=True, metrics.yaml=True
✅ [R10] Logo Churn Global entre 0.0% y 20.0% — logo_churn_global=3.9%
✅ [R7] Logos EoP = COUNT DISTINCT dedup (verificación independiente) — metrics.yaml=59,283 vs Metabase independiente=59,283 (diff=+0)
✅ [R11] Budget CSV completo para el quarter (parcial, solo ARR EoP) — completo: ['Apr - 26', 'May - 26', 'Jun - 26']
❌ [R17] P&L (Net Revenue/Gross Margin/EBITDA) presente — campos faltantes o vacíos: ['net_revenue', 'gross_margin', 'ebitda_margin'] — Finance no ha mandado el P&L de este mes, no publicar todavía
✅ [R12] ~47 slides en el standalone — encontrados=48
✅ [R13] Investment: delta neutro (sin verde/rojo) — 20 celdas verificadas, todas correctas
✅ [R14] Churn/CAC: delta invertido — 40 celdas verificadas, todas correctas
✅ [R15] Resto de métricas: signo estándar de color — 120 celdas verificadas, todas correctas
✅ [R16] Ningún slide-shell fuerza dimensión px inline — 47 slides verificados, sin overrides de dimensión
⏭️ [R18] Ningún slide-shell recorta contenido en silencio (overflow) — playwright no está instalado — correr con 'uv run --with playwright python run.py ...' para habilitar esta regla
✅ [R19] ARR EoP coincide entre Monthly Performance y YTD Performance — ambas slides muestran $31.0M

## Fase 5 — Diff Review
⚠️ [D1] ARR total variación ≤ 5.0% — arr_qoq=9.8%
✅ [D2] Logos EoP variación ≤ 3.0% — 56.8k → 57.6k (+1.4%)
✅ [D3] Churn Rate variación ≤ 1.0pp — 4.3% → 4.8% (+0.5pp)
✅ [D4] New Logos YoY dentro de ±30.0% — new_logos_yoy=23.2%
✅ [D5] FX Impact absoluto ≤ $2M — fx_impact=400,000
✅ [D6] Sugerencia de versión — 5 versión(es) ya en 2026-06/ → sugerido v6 (última: v5)
✅ [D7] Lista de slides que cambiaron vs board anterior — vs board_Jun_2026_v5.html — 1/47 cambiaron: [1]
