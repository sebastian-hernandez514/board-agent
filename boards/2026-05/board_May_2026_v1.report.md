# Board 2026-05 — v1
Generado: 2026-07-10T22:08:15

## Fase 4 — Business Rules Validator
✅ [R1] ARR total incluye Alanube — arr_total=29,200,000 vs alegra+alanube=29,181,770 (diff=18,230)
✅ [R2] New MRR Core + Lite ≈ Total — core=24,000 + lite=47,000 = 71,000 vs total=71,000 (diff=0)
⏭️ [R3] ARR Walk balancea (buckets = Net New ARR = EoP-BoP) — error: celda vacía o no numérica: '—'
⏭️ [R4] Net Churn es negativo — error: celda vacía o no numérica: '—'
⏭️ [R6] FX residual < $3M — error: celda vacía o no numérica: '—'
⏭️ [R8] ARR EoP (Constant Currency) = ARR EoP en el mes de corte — error: celda vacía o no numérica: '—'
✅ [R5] cross_down restado en Net Expansion — recomputado=269,755 vs mostrado=300,000 (diff=-30,245); cross_down=91,959 (debe restarse, no sumarse)
✅ [R9] is_quarter_end consistente con el mes de corte — cutoff_month=2026-05 → esperado=False, metrics.yaml=False
✅ [R10] Logo Churn Global entre 0.0% y 20.0% — logo_churn_global=4.2%
✅ [R7] Logos EoP = COUNT DISTINCT dedup (verificación independiente) — metrics.yaml=58,974 vs Metabase independiente=58,974 (diff=+0)
⏭️ [R11] Budget CSV completo para el quarter (parcial) — mes de corte no es cierre de quarter
✅ [R17] P&L (Net Revenue/Gross Margin/EBITDA) presente — net_revenue=$2.4M gross_margin=80.9% ebitda_margin=7.7%
✅ [R12] ~47 slides en el standalone — encontrados=47
✅ [R13] Investment: delta neutro (sin verde/rojo) — 20 celdas verificadas, todas correctas
✅ [R14] Churn/CAC: delta invertido — 8 celdas verificadas, todas correctas
⏭️ [R15] Resto de métricas: signo estándar de color — no se encontraron filas de esta métrica en el HTML
✅ [R16] Ningún slide-shell fuerza dimensión px inline — 47 slides verificados, sin overrides de dimensión
✅ [R18] Ningún slide-shell recorta contenido en silencio (overflow) — 47 slides verificados, sin desbordes
✅ [R19] ARR EoP coincide entre Monthly Performance y YTD Performance — ambas slides muestran $29.2M

## Fase 5 — Diff Review
⏭️ [D1] ARR total variación — error: could not convert string to float: '>+999'
⏭️ [D2] Logos EoP variación — error: list index out of range
⏭️ [D3] Churn Rate variación — error: list index out of range
✅ [D4] New Logos YoY dentro de ±30.0% — new_logos_yoy=0.0%
⚠️ [D5] FX Impact absoluto ≤ $2M — fx_impact=27,800,000
✅ [D6] Sugerencia de versión — 0 versión(es) ya en 2026-05/ → sugerido v1
⏭️ [D7] Lista de slides que cambiaron vs board anterior — no hay ningún board guardado todavía para comparar
