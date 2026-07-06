# Arquitectura del Agente — Board Ejecutivo Mensual

> **Versión:** 0.1 — baseline (estado actual + visión)
> **Fecha:** 2026-06-19
> **Propósito:** Punto de partida para diseñar el sistema multi-agente que automatice la generación del board. Este doc captura lo que tenemos hoy y la dirección a donde queremos llegar. Contrastar contra versiones futuras.

---

## 1. Estado Actual del Pipeline

### Stack técnico
- **Lenguaje:** Python (`uv run --with boto3 --with pyyaml --with jinja2`)
- **Datos principales:** Redshift (cluster-2: `redshift-cluster-2` / cluster-1: `data-redshift-cluster`)
- **Seguridad:** `redshift_guard.py` para todas las queries
- **Renderizado:** Jinja2 templates → HTML → PDF (Playwright)
- **Autenticación RS:** AWS SSO perfil `alegra`

### Flujo de generación hoy

```
fetch_metrics.py  →  data/metrics.yaml  →  generate.py  →  output/*.html
                                                         →  merge_standalone.py
                                                         →  board_standalone.html
                                                         →  generate_pdf.py → .pdf
```

### Fuentes de datos — inventario completo

| Fuente | Tipo | Cluster | Actualización | Estado hoy |
|---|---|---|---|---|
| `dwh_facts.fact_customers_mrr` | Redshift | cluster-2 | Automático | ✅ |
| `db_finance.fact_cac_version_segments` | Redshift | cluster-2 | Automático | ✅ |
| `bi_sales.sales_actions` | Redshift | cluster-2 | Automático | ✅ |
| `bi_sales.fact_closed_deals` | Redshift | cluster-2 | Automático | ✅ |
| `db_amplitude_events.amplitude_ac_events` | Redshift | cluster-2 | Automático | ✅ |
| `bi_accountant.accountant_master_table` | Redshift | cluster-2 | Automático | ✅ |
| `dm_retention.bi_customer_monthly_status` | Redshift | cluster-1 | Automático | ✅ |
| `dwh_dimensions.tb_trm_banrep` | Redshift | cluster-2 | Automático | ✅ (2026-07-03, reemplazó `csv/paises_fx.csv`) |
| `bi_alanube.fact_alanube_arr_walk` | Redshift | cluster-2 | Automático | ✅ parcial (2026-07-03, reemplazó `data/chart_alanube.yaml` — solo ARR EoP de Chart 1 y `arr_total`; el ARR Walk completo de Alanube en `3_arr_walk.j2` sigue editorial manual) |
| `bi_strategic.payback_cohort_results` | Redshift | cluster-2 | Mensual (`CALL refresh_payback()`, ya programado por el usuario) | ✅ (2026-07-04, reemplazó `csv/Payback.csv`, `load_payback()`) |
| `bi_strategic_relationships.fact_headcount_*` (4 tablas) | Redshift | cluster-2 | Automático | ✅ (2026-07-03/04, reemplazó los 2 Sheets de Headcount, `load_headcount_*()` + template `7_headcount.j2` convertido a Jinja2) |
| `bi_sales.sales_actions` / `fact_closed_deals` (funnel), `flywheel`, `bi_accountant.accountant_master_table` (supercontadores/value events) | Redshift | cluster-2 | Automático | ✅ ya conectado a `metrics.gtm.*` — la doc anterior (2026-06-19) decía "hardcodeado", quedó desactualizada; verificado 2026-07-04 leyendo `5_go_to_market.j2` directamente |
| `csv/P&L Histórico- ACtual.csv` | CSV manual | — | Mensual humano | ⚠️ Manual — **descartado automatizar** por decisión del usuario (Finance maneja su reporte aparte) |
| `csv/P&L Histórico - Budget.csv` | CSV manual | — | Estático anual | ⚠️ Manual |
| `csv/Metricas_budget.csv` | CSV manual | — | Estático anual | ⚠️ Manual (prioridad baja — estático) |
| Template 4 HTML (Finance) | HTML externo | — | Mensual — equipo externo | ⚠️ Dependencia — **descartado automatizar**, decisión del usuario |
| NPS scores (`6_rd.j2`) | `data/nps_snapshot.yaml` (snapshot asistido) | — | Mensual, vía MCP de Amplitude en sesión de Claude (ya no requiere screenshots) | ✅ Parcial (2026-07-06) — datos ya no hardcodeados en el template, pero la fuente sigue siendo un paso asistido mensual (no una API que `fetch_metrics.py` llame solo) — ver `Template Board/CLAUDE.md` sección "Template 6 — NPS" |
| `data/editorial/ceo.yaml` | YAML editorial | — | Mensual humano | ⚠️ Manual — correcto que sea manual (narrativa) |
| `data/editorial/discussion_topics.yaml` | YAML editorial | — | Mensual humano | ⚠️ Manual — correcto que sea manual (narrativa) |
| `data/editorial/arr_walk.yaml` | YAML editorial | — | Mensual humano | ⚠️ Manual — correcto que sea manual (narrativa) |
| `8_appendix.j2` "Churned by tenure" (GLO/Core/Lite) | `db_retention.bi_churn_retired` + `dwh_facts.fact_customers_mrr` | cluster-2 | Automático | ✅ Hecho 2026-07-06 (`_build_churn_tenure()`, reemplazó el script externo `~/Downloads/board/update_board.py` que usaba perfil SSO/db_user distintos al resto del proyecto) |
| Footnote "May-26 ratio (47%/53%)" en `5_go_to_market.j2` (Flywheel Quarterly) | Texto literal en HTML | — | Mensual humano | ⚠️ Manual — trivial (una línea de texto) |

### Bugs conocidos que llegaron a producción

| Bug | Qué pasó | Versión donde se detectó | Regla que debería haberlo bloqueado |
|---|---|---|---|
| ARR no incluía Alanube | `arr_total` solo tenía Alegra | v36 Mayo-26 | `arr_total = alegra + alanube` — ✅ implementada como R1 en `phase4_validator.py` |
| New MRR usaba ARR en vez de MRR | No se dividía por /12 | v37 Mayo-26 | `new_mrr_core + new_mrr_lite ≈ total_new_mrr` — ✅ implementada como R2 en `phase4_validator.py` |
| ARR EoP (Constant Currency) nunca fue constant currency de verdad | `mrr_usd_eop_cc` tomaba `amount_usd_mrr` del warehouse sin ajuste al mes de corte — afectaba TODOS los boards, no un mes puntual | Encontrado 2026-07-03 al construir R8, corregido el mismo día en `fetch_metrics.py` (`CACHE_VERSION v27`) | `ARR EoP (CC) = ARR EoP en el mes de corte` — ✅ implementada como R8, y la causa raíz ya está corregida (no solo bloqueada) |

### Slides con datos NO en metrics.yaml (hardcodeados hoy)

**Verificado línea por línea 2026-07-04** — la versión anterior de esta tabla estaba desactualizada (`5_go_to_market.j2` y `7_headcount.j2` ya no son ciertos como se describían). Estado real:

| Template | Slide | Contenido hardcodeado | Estado |
|---|---|---|---|
| `5_go_to_market.j2` | Acquisition Funnel, Flywheel, Value Events, Supercontadores | — | ✅ Ya conectado a `metrics.gtm.*` (funnel_countries, flywheel, supercontadores, value_events) — `funnelBands` que queda hardcodeado es solo config de estilo del chart (colores/labels), no data |
| `5_go_to_market.j2` | Flywheel Growth Play (header) | — | ✅ Ya dinámico (`config.month_label`) |
| `5_go_to_market.j2` | Flywheel Quarterly (footnote) | Texto "May-26 ratio (47%/53%)" | ⚠️ Manual — trivial |
| `8_appendix.j2` | Churned by tenure GLO/Core/Lite | — | ✅ Ya conectado a `metrics.churn_tenure.*` (2026-07-06) |
| `7_headcount.j2` | Todas las slides | — | ✅ Convertido a Jinja2 2026-07-04 (Fase 1+2 completas, ver `memory/project_board_agent.md`) — solo quedan manuales los bloques de "Comments" (editorial, por diseño) |
| `6_rd.j2` | NPS (slide 3) | — | ✅ Ya conectado a `metrics.nps.*` (2026-07-06) — la fuente (`data/nps_snapshot.yaml`) sigue siendo un snapshot asistido mensual, no una tabla RS ni una API que fetch_metrics.py llame sola

### Paso post-generación que se rompe siempre

Después de cada `generate.py`, la imagen de Costa Rica (`cr-landing-icp.png` en `2_discussion_topic.j2`) pierde su base64 y hay que re-embeberla manualmente. Si se olvida, el standalone queda con imagen rota silenciosamente.

✅ **Automatizado 2026-07-03** por Board Agent Fase 3 (`board_agent/phase3_html_builder.py::_reembed_cr_image`) — corre solo entre `generate.py` y `merge_standalone.py`, ya no requiere intervención manual.

---

## 2. Arquitectura Propuesta — Sistema Multi-Agente

### Principio de diseño fundamental

> **Todo debe salir de una base de datos. La Fase 0 (Human Inputs) no debe existir en el estado final.**

Hoy existe una Fase 0 implícita porque varias fuentes son CSVs, YAMLs y HTMLs que un humano actualiza mensualmente. Eso es un problema de arquitectura, no del agente. El agente bien diseñado expone ese problema claramente: si la data no está en la base, el board no sale. El camino es mover cada fuente manual a una tabla de Redshift o a un ETL automatizado.

La Fase 0 existe hoy como workaround. La arquitectura objetivo la hace desaparecer.

### Las 6 fases

```
FASE 0 — Human Inputs Gate            ← DEBE DESAPARECER      ✅ implementada (phase0_gate.py)
FASE 1 — Data Freshness Check         ← fuentes automáticas   ✅ implementada (phase1_freshness.py)
FASE 2 — Metrics Computation          ← fetch_metrics.py      ✅ implementada (phase2_metrics.py)
FASE 3 — HTML Builder                 ← generate.py + merge + fixes  ✅ implementada (phase3_html_builder.py)
FASE 4 — Business Rules Validator     ← las reglas duras      ✅ implementada, 14/15 reglas activas (phase4_validator.py)
FASE 5 — Diff Review                  ← vs board anterior     ✅ implementada, 7/7 reglas activas incl. D7 (phase5_diff.py)
FASE 6 — PDF Generation (opcional)    ← trigger manual del usuario  ✅ implementada, gate manual a propósito (phase6_pdf.py)
```

**Estado real a 2026-07-03:** las 6 fases tienen código funcional en `board_agent/*.py`, corridas de punta a punta contra un mes real (mayo-26) via `run.py`. Ver `memory/project_board_agent.md` (memoria de Claude) para el detalle sesión por sesión — esta sección de abajo describe el diseño original y sigue siendo la referencia de qué hace cada fase, pero ya no es aspiracional.

---

### FASE 0 — Human Inputs Gate *(workaround temporal)*

**Propósito:** Verificar que las fuentes manuales estén listas antes de correr el pipeline.
**Por qué existe:** Porque varias fuentes no están en ninguna base de datos todavía.
**Estado objetivo:** Esta fase desaparece cuando todas las fuentes sean automatizadas.

**Checks actuales (mientras dure):**

| Check | Tipo | Blocker |
|---|---|---|
| `paises_fx.csv` tiene fila del mes actual | Automático | ✅ Sí |
| `chart_alanube.yaml` tiene el mes actual | Automático | ✅ Sí |
| `Payback.csv` tiene el mes actual | Automático | ✅ Sí |
| `P&L Histórico- ACtual.csv` tiene el mes actual | Automático | ✅ Sí |
| `editorial/ceo.yaml` no tiene placeholders vacíos | Automático | ⚠️ Warning |
| `editorial/discussion_topics.yaml` no vacío | Automático | ⚠️ Warning |
| Template 4 (Finance HTML) fue recibido | Manual | ✅ Sí |
| NPS screenshots existen en `data/assets/YYYY-MM/` | Automático | ⚠️ Warning |

**Output:** Lista ✅/⚠️/❌. Si hay ❌ blocker: para y lista exactamente qué falta y quién lo provee.

**Camino para eliminarla (fuente por fuente):**

| Fuente manual hoy | Automatización objetivo |
|---|---|
| `paises_fx.csv` | ETL a RS o Sheets con Google Finance |
| `chart_alanube.yaml` | `dm_alanube.fact_alanube_arr_walk` ya existe — conectar |
| `Payback.csv` | `fetch_payback_from_sheets()` en `fetch_metrics.py` (aprobado, pendiente) |
| `P&L Histórico- ACtual.csv` | Finance tiene los datos en Sheets — Drive API |
| `Metricas_budget.csv` | Estático anual — cargar a RS una vez |
| Template 4 (Finance HTML) | Finance genera su propia sección via API o Sheets compartido |
| NPS screenshots | Amplitude API o tabla RS con los scores |
| `editorial/ceo.yaml` | Solo la narrativa CEO es irreemplazable — el resto puede generarse |
| Arrays JS hardcodeados | Migrar a `metrics.yaml` (ver sección de deuda técnica) |

---

### FASE 1 — Data Freshness Check

**Propósito:** Verificar que las fuentes automáticas (Redshift) están accesibles y tienen datos del mes actual.

**Checks:**

| Check | Cómo | Blocker |
|---|---|---|
| SSO activo (`aws sts get-caller-identity`) | Shell | ✅ |
| cluster-2 responde | Query trivial `SELECT 1` | ✅ |
| cluster-1 responde | Query trivial `SELECT 1` | ✅ |
| `fact_customers_mrr` tiene el mes actual | `MAX(date_month)` | ✅ |
| `dm_retention.bi_customer_monthly_status` tiene el mes actual | `MAX(date_month)` | ✅ |
| `fact_cac_version_segments` tiene el mes actual | `MAX(cohortmonth)` | ⚠️ Warning (Finance a veces tarda) |
| `bi_accountant.accountant_master_table` tiene el mes actual | `MAX(date_month)` | ✅ |

**Output:** Reporte de disponibilidad. Si `fact_customers_mrr` no tiene el mes → blocker total.

---

### FASE 2 — Metrics Computation

**Propósito:** Correr `fetch_metrics.py` y producir `data/metrics.yaml`.

**Qué hace hoy:**

| Query | Tabla fuente | Para qué slide |
|---|---|---|
| `_SQL_FACT_SUMMARY` | `dwh_facts.fact_customers_mrr` | ARR Walk Core/Lite, países |
| `_SQL_LOGOS_ALL` | `dwh_facts.fact_customers_mrr` | Logos deduplicados |
| `_SQL_INVESTMENT` | `db_finance.fact_cac_version_segments` | CAC, Payback |
| `_SQL_FUNNEL_SIGNUPS` | `bi_sales.sales_actions` | Funnel adquisición |
| `_SQL_FUNNEL_LOGOS` | `bi_sales.fact_closed_deals` | Funnel conversión |
| `_SQL_PRODUCT_PERF` | `dwh_facts.fact_customers_mrr` | Product performance |
| `_SQL_FLYWHEEL` | `fact_customers_mrr + db_hubspot` | Flywheel entes/logos |
| `_SQL_SC_HIST` | `bi_accountant.accountant_master_table` | Supercontadores stock |
| `_SQL_VALUE_EVENTS` | `db_amplitude_events.amplitude_ac_events` | Value events |
| `_SQL_SOW_TOP20` | `bi_accountant.accountant_master_table` | Share of Wallet top 20 |
| `_SQL_RETENTION_CHURN` | `dm_retention.bi_customer_monthly_status` | Churn rate (cluster-1) |

**Las 11 queries corren en paralelo** (se lanzan simultáneamente, se esperan en _pages).

**Merges de CSV (después de RS):**

| Función | CSV | Para qué |
|---|---|---|
| `merge_budget()` | `Metricas_budget.csv` | vs Budget (ARR, New MRR, Logos, Churn) |
| `merge_pnl()` | `P&L Histórico- ACtual.csv` + Budget | Net Revenue, Gross Margin, EBITDA |
| `merge_payback()` | `Payback.csv` | Payback por segmento |

**Output:** `data/metrics.yaml` — única fuente que lee `generate.py`.

**Nota CACHE_VERSION:** Si se modifica cualquier SQL o lógica de cálculo, incrementar `CACHE_VERSION` en `fetch_metrics.py`. La caché persiste entre corridas del mismo mes.

---

### FASE 3 — HTML Builder

**Propósito:** Transformar `metrics.yaml` + `editorial/*.yaml` + `templates/*.j2` en el board HTML.

**Pasos en orden:**

1. `generate.py` → `output/1_inicio.html`, ..., `output/8_appendix.html`
2. `merge_standalone.py` → `output/board_standalone.html`
3. Re-embed imagen CRI (`cr-landing-icp.png` → base64) en `output/2_discussion_topic.html` y en el standalone ← **paso que hoy se hace manualmente y siempre se olvida**

**Templates y su fuente de datos:**

| Template | Fuente principal | Tiene datos hardcodeados |
|---|---|---|
| `1_inicio.j2` | `metrics.yaml` | Sí — Chart 2 Net New ARR (arrays JS) |
| `2_discussion_topic.j2` | `editorial/discussion_topics.yaml` | Sí — imagen CRI |
| `3_arr_walk.j2` | `metrics.yaml` | Sí — Slide Alanube |
| `4_financial_performance.j2` | HTML externo de Finance | Todo hardcodeado (reemplazo mensual) |
| `5_go_to_market.j2` | `metrics.yaml` (parcial) | Sí — 5 slides (ver tabla deuda técnica) |
| `6_rd.j2` | `metrics.yaml` (parcial) | Sí — NPS scores |
| `7_headcount.j2` | Hardcodeado | Todo hardcodeado |
| `8_appendix.j2` | `metrics.yaml` (parcial) | Sí — Net ARR Expansion arrays |

**Output:** `output/board_standalone.html`

---

### FASE 4 — Business Rules Validator

**Propósito:** Verificar que el board es matemáticamente correcto antes de publicarlo. Aquí se hubieran bloqueado los bugs de v36 y v37.

**Reglas duras — si falla, el board no puede publicarse:**

| # | Regla | Fórmula | Origen del bug conocido |
|---|---|---|---|
| R1 | ARR total incluye Alanube | `arr_total ≈ alegra_arr + alanube_arr` | Bug v36 Mayo-26 |
| R2 | New MRR usa /12 | `new_mrr_core + new_mrr_lite ≈ total_new_mrr` (en M, no M×12) | Bug v37 Mayo-26 |
| R3 | ARR Walk balancea | `Additions + Recovered + Net Churn + Net Expansion + FX = Net New ARR = ARR EoP − ARR BoP` | — |
| R4 | Net Churn es negativo | `Net Churn < 0` | Trampa de signos `a_churn` |
| R5 | cross_down restado | `Net Expansion = upsell + down + pricing + cross_new + cross_readop − cross_down` | Trampa de signos `a_cross_down` |
| R6 | FX residual pequeño | `abs(FX Impact) < $3M` | Si es mayor, hay error en lógica FX |
| R7 | Logos usa deduplicación | `logos_eop` viene de `logos_all` (COUNT DISTINCT), no de `l_eop` del summary | Diferencia de ~38 logos |
| R8 | CC del mes base = EoP regular | `arr_cc[mes_actual] ≈ arr_eop[mes_actual]` (ratio FX = 1) | — |

**Reglas de consistencia — si falla, revisar antes de publicar:**

| # | Regla |
|---|---|
| R9 | Mes de cierre de Q (mar/jun/sep/dic) → comparación QoQ; resto → MoM; debe ser consistente en todas las slides |
| R10 | Churn rate entre 0% y 20% (si es mayor, probable doble conteo) |
| R11 | Budget en cierre de Q = suma de los 3 meses del Q, no solo el mes puntual |
| R12 | Número de slides en el standalone ≈ 47 (si < 40, algo no se generó) |

**Reglas de estilo:**

| # | Regla |
|---|---|
| R13 | Investment: delta en negro/neutro (sin verde/rojo) — ✅ implementada 2026-07-06, parsea HTML (`_check_color_rules`), validado 20/20 celdas en mayo-26 |
| R14 | Churn Rate y CAC: delta invertido (negativo = verde, positivo = rojo) — ✅ implementada, 40/40 celdas correctas |
| R15 | Resto de métricas: positivo = verde, negativo = rojo — ✅ implementada, 119/119 celdas correctas |

**Output:** Reporte PASS/FAIL por regla con los valores que fallan. Si alguna regla dura falla → no avanzar a versión final sin revisión humana explícita.

---

### FASE 5 — Diff Review

**Propósito:** ¿Qué cambió respecto al board anterior? Evitar publicar errores detectables por comparación.

**Checks:**

| Métrica | Threshold de alerta |
|---|---|
| ARR total | Cambio > 5% MoM inesperado |
| Logos EoP | Cambio > 3% MoM inesperado |
| Churn Rate | Cambio > 1pp MoM inesperado |
| New Logos | Cambio > 30% vs mismo mes año anterior |
| FX Impact | Absoluto > $2M (señal de error FX) |

**Output:**
- Lista de slides que cambiaron vs board anterior — ✅ D7, implementado 2026-07-06: parte el HTML en slides (mismo criterio que R12) y compara chunk a chunk contra la última versión guardada (mismo mes, o mes anterior si es la primera corrida del mes). Validado contra datos reales: 19/47 slides detectadas correctamente tras los cambios de Payback/Headcount/Alanube/NPS del mismo día.
- Comparativa de KPIs clave (valor anterior → valor nuevo → delta)
- Sugerencia de versión (vN)
- Flag si algún cambio supera los thresholds

---

### FASE 6 — PDF Generation *(trigger manual)*

**Propósito:** Generar el PDF final para distribución.
**Por qué es manual:** El usuario debe confirmar que el HTML está aprobado antes de generar el PDF.

**Comando:**
```bash
uv run --with playwright --with pillow python scripts/generate_pdf.py
```

**Características:** screenshot por slide a 3x, ~47 slides, ~17MB, formato 4K.

---

## 3. Deuda Técnica — Lo que bloquea la automatización completa

### Prioridad alta (bloquea la Fase 0) — ✅ TODAS hechas a 2026-07-04

| Item | Esfuerzo | Impacto | Estado |
|---|---|---|---|
| `load_payback()` en `fetch_metrics.py` desde `bi_strategic.payback_cohort_results` | Medio | Elimina update manual de `Payback.csv` | ✅ Hecho 2026-07-04 |
| Conectar `chart_alanube.yaml` a `bi_alanube.fact_alanube_arr_walk` | Bajo | Elimina update manual de ARR Alanube (Chart 1) | ✅ Hecho 2026-07-03 (`load_alanube_arr()`) |
| FX rates desde RS en lugar de `paises_fx.csv` | Medio | Elimina update manual de FX | ✅ Hecho 2026-07-03 (`dwh_dimensions.tb_trm_banrep`, `load_fx()`) |
| P&L real desde Sheets (Drive API) | Alto | Elimina update manual de P&L CSVs | ❌ Descartado — Finance maneja su reporte por separado, fuera de alcance por decisión del usuario |
| Automatizar re-embed imagen CRI post-generación | Muy bajo | Elimina paso manual que siempre se olvida | ✅ Hecho 2026-07-03 (`phase3_html_builder.py`) |
| Migrar `7_headcount.j2` a datos dinámicos desde RS | Alto | Slide Headcount completamente automatizada | ✅ Hecho 2026-07-03/04 (`load_headcount_*()` + template convertido a Jinja2, Fase 1+2) |

**Con esto, de la Fase 0 original ya no queda ningún blocker automatizable pendiente** — lo que resta (P&L, Template 4 Finance, editorial YAMLs) son exclusiones deliberadas, no deuda.

### Prioridad media — lo que queda genuinamente sin automatizar (verificado 2026-07-04)

| Item | Esfuerzo | Impacto | Estado |
|---|---|---|---|
| NPS (`6_rd.j2`) — snapshot asistido | Medio | Elimina screenshots, datos bajo control del template (no del Validator todavía) | ✅ Hecho 2026-07-06 (`_build_nps()` + `data/nps_snapshot.yaml`) — se investigó calcular 100% desde RS (`amplitude_events_gold` tiene los eventos reales) pero la fórmula reconstruida dio 2-8% de diferencia vs Amplitude; el usuario prefirió exactitud sobre automatización completa por ahora |
| ~~Sacar "Churned by tenure" del script externo~~ | — | — | ✅ Hecho 2026-07-06 (`_build_churn_tenure()` en `fetch_metrics.py`, ver `memory/project_board_agent.md`) |
| ~~Automatizar el ARR Walk completo de Alanube~~ | — | — | ✅ Hecho 2026-07-06 (`_build_alanube_walk_table()`, slide 9 de `1_inicio.j2` — 17 filas, 4 bloques, validado contra el Excel oficial de Alanube). "ARR Growth Rate MoM/QoQ" y "Avg. ARR per Logo" no reconcilian ni con la fuente oficial — fórmula estándar documentada como pendiente de confirmar con Finance/Alanube |
| ~~Footnote "May-26 ratio" en `5_go_to_market.j2`~~ | — | — | ✅ Hecho 2026-07-06 (`out["gtm"]["own_pct"]/"client_pct"/"own_ratio_label"`) |
| ~~Migrar arrays JS de `5_go_to_market.j2`~~ | — | — | ✅ Ya estaba hecho — la doc anterior estaba desactualizada, verificado 2026-07-04 |

### Prioridad baja (calidad de vida)

| Item |
|---|
| Template 4 (Finance): definir API o formato de intercambio con el equipo de Finance |
| Sistema de versiones: guardar solo 3-4 versiones por mes (hoy llegó a v42) |
| `Metricas_budget.csv` → cargar a RS como tabla estática anual |

---

## 4. Visión Final — Estado Objetivo

```
                    ┌─────────────────────────────────────────┐
                    │              REDSHIFT                   │
                    │  fact_customers_mrr                     │
                    │  fact_cac_version_segments              │
                    │  dm_retention                           │
                    │  bi_accountant                          │
                    │  bi_sales                               │
                    │  dm_alanube (ARR Alanube)               │
                    │  fact_fx_rates (FX — nuevo)             │
                    │  fact_budget (Budget — nuevo)           │
                    │  fact_pnl (P&L — nuevo)                 │
                    │  fact_payback (Payback — nuevo)         │
                    │  fact_headcount (HC — nuevo)            │
                    └──────────────────┬──────────────────────┘
                                       │ todo automático
                    ┌──────────────────▼──────────────────────┐
                    │         FASE 1: Data Check              │
                    │  ¿Están todos los datos del mes?        │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────┐
                    │         FASE 2: Metrics                 │
                    │  fetch_metrics.py → metrics.yaml        │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────┐
                    │         FASE 3: HTML Builder            │
                    │  generate.py → board_standalone.html    │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────┐
                    │         FASE 4: Validator               │
                    │  15 reglas duras + consistencia         │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────┐
                    │         FASE 5: Diff Review             │
                    │  vs board anterior → versión vN         │
                    └──────────────────┬──────────────────────┘
                                       │ aprobación humana (CEO commentary)
                    ┌──────────────────▼──────────────────────┐
                    │         FASE 6: PDF                     │
                    └─────────────────────────────────────────┘
```

**Lo único que debe seguir siendo humano en el estado final:**
- El texto de CEO commentary (Highlights, Lowlights, Financial Update) — criterio editorial, no datos
- La aprobación final antes de publicar — decisión humana, no técnica

Todo lo demás es automatizable.

---

## 5. Métricas de éxito

| Métrica | Estado actual (2026-07-04) | Objetivo |
|---|---|---|
| Versiones por board mensual | ~v42 (Mayo-26) | ≤ v5 |
| Fuentes manuales | 5 (NPS, Churn-by-tenure externo, ARR Walk Alanube, footnote GTM, P&L/Template4/editorial — estos 3 últimos deliberadamente excluidos) | 0 automatizable (salvo CEO commentary + P&L/Template4 Finance) |
| Bugs detectados post-publicación | 5 (ARR Alanube, New MRR /12, Constant Currency, Headcount Attrition/columnas, — todos ya corregidos) | 0 |
| Tiempo total de generación | ~4-6 horas con iteraciones | < 30 min |
| Slides con datos no validables | 2 (NPS, Churn-by-tenure) — antes 8 | 0 |
