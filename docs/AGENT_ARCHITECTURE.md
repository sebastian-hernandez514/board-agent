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
FASE 4 — Business Rules Validator     ← las reglas duras      ✅ implementada, 19/19 reglas activas (phase4_validator.py)
FASE 5 — Diff Review                  ← vs board anterior     ✅ implementada, 7/7 reglas activas incl. D7 (phase5_diff.py)
FASE 6 — PDF Generation (opcional)    ← trigger manual del usuario  ✅ implementada, gate manual a propósito (phase6_pdf.py)
```

**Estado real a 2026-07-03:** las 6 fases tienen código funcional en `board_agent/*.py`, corridas de punta a punta contra un mes real (mayo-26) via `run.py`. Ver `memory/project_board_agent.md` (memoria de Claude) para el detalle sesión por sesión — esta sección de abajo describe el diseño original y sigue siendo la referencia de qué hace cada fase, pero ya no es aspiracional.

---

### FASE 0 — Human Inputs Gate *(workaround temporal)*

**Propósito:** Verificar que las fuentes manuales estén listas antes de correr el pipeline.
**Por qué existe:** Porque varias fuentes no están en ninguna base de datos todavía.
**Estado objetivo:** Esta fase desaparece cuando todas las fuentes sean automatizadas.

**Checks actuales — 8 en total (`board_agent/phase0_gate.py::run()`, ampliado 2026-07-09):**

| ID | Check | Blocker |
|---|---|---|
| F0.4 | `P&L Histórico- ACtual.csv` tiene el mes actual (o `data/pnl_override.yaml`) | ⚠️ Warning (bajado de FAIL 2026-07-08 — ver nota abajo) |
| F0.5 | `editorial/ceo.yaml` no tiene placeholders vacíos, y si trae `updated_for_month` que coincida con el mes objetivo | ⚠️ Warning |
| F0.6 | `2_discussion_topic.j2` — sentinel `<!-- updated_for_month: YYYY-MM -->` coincide con el mes objetivo | ⚠️ Warning |
| F0.7 | `editorial/arr_walk.yaml` con comentarios llenos | ⚠️ Warning |
| F0.8 | `data/config.yaml` (`period`) coincide con el `--month` pedido | ❌ **FAIL** |
| F0.9 | Template 4 (`4_financial_performance.j2`) — `<title>` coincide con el mes objetivo | ⚠️ Warning |
| F0.10 | `data/nps_snapshot.yaml` tiene una entrada para el mes objetivo | ⚠️ Warning |
| F0.11 | `7_headcount.j2` — sentinel `<!-- updated_for_month: YYYY-MM -->` coincide con el mes objetivo | ⚠️ Warning |

**F0.4 bajó de FAIL a WARN el 2026-07-08** (encontrado corriendo el flujo real para junio-26 y viendo que un solo dato de Finance tapaba la revisión de todo lo demás): `merge_pnl()` en `fetch_metrics.py` ya maneja la ausencia de datos sin romperse — no setea `net_revenue`/`gross_margin`/`ebitda_margin`, y Jinja2 (`Environment(...)` sin `StrictUndefined`) los renderiza en blanco sin error. El freno real se movió a **R17 del Validator** (Fase 4): si esos 3 campos faltan o vienen vacíos, el Validator da FAIL ahí, con el board ya armado y visible para revisar, en vez de bloquear todo desde el minuto uno.

**F0.8 y F0.9 agregadas 2026-07-08** — hallazgo real reportado por el usuario después de generar el board de junio con el agente: varias slides seguían mostrando "May" pese a haber corrido `run.py --month 2026-06`. Investigado y confirmado en código: `config.yaml` (usado por TODOS los templates para headers/títulos) y el HTML de Template 4 (pegado a mano por Finance) no tenían **ningún** check que comparara su mes contra el `--month` pedido — el gap de "Template 4 fue recibido" que quedaba como aspiracional en versiones anteriores de esta tabla (nunca tuvo función real) ahora sí existe como F0.9, reusando la convención ya existente del `<title>` del archivo (ej. "Financial Performance · May 2026"), sin pedirle a Finance ningún campo nuevo. F0.8 es FAIL (comparación exacta, cero ambigüedad); F0.9 es WARN (mismo criterio que F0.4: insumo externo que llega tarde). **Alcance acordado con el usuario:** solo detección — no se modificó ningún template de Template Board para "vaciar" slides desactualizadas, eso quedó fuera de esta pasada por decisión explícita.

**F0.6 reescrita 2026-07-08 (mismo día, corrección de una limitación detectada en el propio hallazgo de F0.8/F0.9):** antes revisaba `editorial/discussion_topics.yaml`, un scaffold **desconectado** del template real. Se agregó a `templates/2_discussion_topic.j2` el mismo sentinel que ya usa `ceo.yaml` (`updated_for_month`), pero como comentario HTML (`<!-- updated_for_month: YYYY-MM -->`, primera línea del archivo) ya que es HTML puro, no YAML — única línea del `.j2` fuente que Board Agent toca, no afecta el render. F0.6 ahora lee ese comentario y compara contra el mes objetivo, igual que F0.5/F0.9. Backward-compatible: si el sentinel no existe, WARN honesto en vez de fingir certeza.

**F0.10 agregada 2026-07-08 (mismo día, tercer hallazgo de la revisión del preview de junio):** `_build_nps()` en `fetch_metrics.py` devuelve `None` cuando `nps_snapshot.yaml` no tiene el mes objetivo (comportamiento correcto, documentado ahí mismo) — pero `6_rd.j2` no blinda `metrics.nps.score`/`.costa_rica_trend`/etc. con ningún `{% if %}`, así que `generate.py` truena armando esa slide específica (`'None' has no attribute 'costa_rica_trend'`) y deja `output/6_rd.html` con el mes anterior **sin avisar**. No se tocó `6_rd.j2` (blindar la plantilla es cambio de Template Board, fuera de alcance) — F0.10 avisa ANTES de correr `generate.py`, y **F3.7** (Fase 3) tapa la slide de NPS en el output si ya quedó vieja. WARN, no FAIL — mismo criterio que F0.4/F0.9.

**F0.11 agregada 2026-07-09** — mismo hueco que tenía F0.6 (Discussion Topics) antes de su fix: los comentarios de Highlights/Lowlights de `7_headcount.j2` (slides "Headcount by Team" y "People & Talent") viven escritos a mano dentro del `.j2`, sin ningún YAML propio ni campo verificable. Se le agregó el mismo sentinel (`<!-- updated_for_month: YYYY-MM -->`). Encontrado al construir el registro declarativo de slides (ver Fase 3 abajo) a partir de una propuesta de Luis Caro en tts-bi-data — al catalogar todas las slides propensas a quedar desactualizadas, Headcount fue el único caso real sin cubrir.

**1 check que existía en versiones anteriores de esta tabla y ya NO corre en este gate** (tabla desactualizada hasta 2026-07-06, corregida tras revisión de código):
- `paises_fx.csv`, `chart_alanube.yaml`, `Payback.csv` — se automatizaron y se movieron a Fase 1/2 (ver sección "Camino para eliminarla" abajo, fechas 2026-07-03/06).

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

**Checks — 14 en total (`board_agent/phase1_freshness.py::run()`, ampliado 2026-07-08 tras simular
el flujo de junio-26 desde cero y encontrar que solo se cubrían 5 de las ~15 tablas reales que
usa `fetch_metrics.py`):**

| ID | Check | Columna | Blocker |
|---|---|---|---|
| F1.0 | Sesión SSO activa (perfil `alegra`) | — | ✅ FAIL |
| F1.1 | `dwh_facts.fact_customers_mrr` tiene el mes | `date_month` | ✅ FAIL |
| F1.2 | `dm_retention.bi_customer_monthly_status` tiene el mes (cluster-1) | `date_month` | ✅ FAIL |
| F1.3 | `db_finance.fact_cac_version_segments` tiene el mes | `cohortmonth` | ⚠️ WARN (Finance a veces tarda) |
| F1.4 | `bi_accountant.accountant_master_table` tiene el mes | `date_month` | ✅ FAIL |
| F1.5 | `dwh_dimensions.tb_trm_banrep` (FX) tiene el mes | `month` | ✅ FAIL |
| F1.6 | `bi_alanube.fact_alanube_arr_walk` tiene el mes | `month_date` | ⚠️ WARN |
| F1.7 | `bi_strategic.payback_cohort_results` tiene el mes | `cohort_month` | ⚠️ WARN |
| F1.8 | `bi_strategic_relationships.fact_headcount_eop` tiene el mes | `fecha` | ⚠️ WARN |
| F1.9 | `bi_strategic_relationships.fact_headcount_forecast` tiene el mes | `fecha` | ⚠️ WARN |
| F1.10 | `bi_strategic_relationships.fact_headcount_movements` tiene el mes | `fecha` | ⚠️ WARN |
| F1.11 | `db_retention.bi_churn_retired` tiene el mes | `date_month` | ⚠️ WARN |
| F1.12 | `bi_sales.fact_closed_deals` tiene el mes (rango, no día exacto) | `close_date` | ⚠️ WARN |
| F1.13 | `bi_sales.sales_actions` tiene el mes (rango, no día exacto) | `fecha` | ⚠️ WARN |

**Por qué F1.1/F1.2/F1.4/F1.5 son FAIL duro y el resto WARN:** esas 4 alimentan directamente el ARR/MRR total del slide 1 (incluida la conversión FX). Las demás alimentan slides específicas (Alanube, Payback, Headcount, Churned by tenure, funnel GTM) — importantes, pero no tumban el número principal del board si faltan.

**Validado en vivo contra junio-26 (2026-07-08):** F1.1/F1.2/F1.4/F1.7-F1.13 en PASS; **F1.3, F1.5 y F1.6 en FAIL/WARN reales — `fact_cac_version_segments`, `tb_trm_banrep` y `fact_alanube_arr_walk` no tenían junio todavía** (max_seen = mayo-26 en las 3). No es un bug del check — son fuentes que de verdad no se habían actualizado. RACI: `tb_trm_banrep` → Luis Caro (avisa/escala), `fact_cac_version_segments` → Santiago González. `fact_alanube_arr_walk` sin dueño identificado todavía — pendiente.

**No cubiertas todavía, a propósito** (ver comentario en el código): `amplitude_ac_events` (tabla de eventos crudos, potencialmente costosa de chequear), `associations_accounting_entities_to_companies` de HubSpot (tabla de mapeo sin grano mensual), `dim_headcount_team_category` (dimensión estática, no aplica).

**Output:** Reporte de disponibilidad. Si alguno de los 4 FAIL duros no tiene el mes → blocker total, no se avanza a Fase 2.

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
2. Re-embed imagen CRI (`cr-landing-icp.png` → base64) en `output/2_discussion_topic.html` ← paso que antes se hacía manualmente y siempre se olvidaba
3. **F3.4 (agregada 2026-07-08):** si el `<title>` de `output/4_financial_performance.html` sigue en el mes anterior (mismo hallazgo real que F0.9), tapa visualmente cada `.board-slide` con un overlay "contenido pendiente" — en vez de publicar los números de Finance del mes pasado disfrazados de mes actual. Solo escribe en el `output/*.html` ya generado, nunca en el `.j2` fuente (mismo límite que el re-embed de imágenes). No borra ni reescribe el contenido existente (regex sobre HTML anidado es frágil) — inserta un `<div>` hermano con `position:absolute;inset:0` que lo cubre por completo. WARN, no FAIL. Validado en vivo con Playwright contra el `output/4_financial_performance.html` real de junio: las 6 slides quedaron en blanco con el mensaje, contenido original intacto debajo.
4. **F3.5 (agregada 2026-07-08, mismo día):** mismo mecanismo para Discussion Topics — lee el sentinel `<!-- updated_for_month: YYYY-MM -->` (ver F0.6) del `output/2_discussion_topic.html` ya generado (el comentario pasa intacto a través de Jinja2) y tapa cada `.dt-slide` si no coincide con el mes objetivo. Comparte la función `_overlay_stale_slides()` con F3.4 — mismo mecanismo genérico, distinta clase de slide-shell. Validado en vivo: el `.j2` real se marcó con `updated_for_month: 2026-05` (fecha real de la última actualización) y, al regenerar pidiendo junio, las 4 slides de discussion topics (incluida la que tiene la imagen de Costa Rica embebida) quedaron correctamente en blanco.
5. **F3.6 (agregada 2026-07-08, mismo día — tercera revisión con el usuario):** mismo problema pero para CEO Highlights, con una complicación distinta a F3.4/F3.5 — es UNA sola slide dentro de `output/1_inicio.html`, que comparte la clase genérica `.slide` con Monthly Performance, YTD Performance, ARR Walk GLO, etc. Tapar "toda la clase .slide del archivo" hubiera ocultado también slides frescas. Nueva función `_overlay_single_slide_by_marker()`: ubica la slide por el comentario `<!-- SLIDE 2 — CEO Highlights / Lowlights -->` (mismo criterio que R19 para anclar en HTML) y tapa solo la que aparece justo después. Lee `editorial/ceo.yaml` directo (dato, no código) para el sentinel `updated_for_month` — se agregó ese campo al archivo real (`"2026-05"`, fecha honesta de la última actualización), mismo campo que F0.5 ya usaba desde el 2026-07-06 pero nunca antes conectado a una acción real de Fase 3. Validado en vivo con Playwright: la slide de CEO Highlights quedó tapada, la slide siguiente (Table of Contents / Monthly Performance) quedó intacta sin overlay.
6. **F3.7 (agregada 2026-07-08, mismo día — corregida en una segunda pasada el mismo día):** cierra el hallazgo #5 (crash silencioso de NPS, ver F0.10 arriba) — y de paso el hallazgo #4 (Product Performance con "May 2026"), que resultó ser el MISMO problema, no uno aparte. Causa raíz confirmada leyendo `generate.py`: `html = tmpl.render(...)` se ejecuta ANTES de `out_f.write_text(html)` — si `render()` lanza una excepción (que lanza, al llegar a `metrics.nps.costa_rica_trend` sobre `None`), ese `write_text` nunca se llama. Jinja2 renderiza el archivo COMPLETO de una sola pasada, así que el crash deja TODO `output/6_rd.html` sin regenerar, no solo la parte de NPS — Product Performance (que si se regenerara sí tomaría el mes correcto, usa `config.month_label` dinámico) queda vieja como efecto colateral, no por un bug propio. Primera versión de F3.7 tapaba solo la slide de NPS (mismo mecanismo de marcador que F3.6) asumiendo que Product Performance seguía fresca — falso, corregido para tapar TODO el archivo (mismo mecanismo whole-file que F3.4/F3.5, reusando `_overlay_stale_slides()`). La portada (`class="slide section-cover"`, distinta a `class="slide"` exacto) queda fuera de alcance a propósito — solo muestra un título de sección + `quarter_label`, sin datos que puedan estar mal. Lee `data/nps_snapshot.yaml` directo. Validado en vivo con Playwright: las 2 slides de contenido (Product Performance y NPS) quedaron tapadas, la portada intacta.
7. **F3.8 (agregada 2026-07-09):** mismo mecanismo whole-file para Headcount — `7_headcount.j2` tenía el mismo hueco que Discussion Topics antes de su fix (comentarios de Highlights/Lowlights escritos a mano, sin YAML ni sentinel). Se le agregó el sentinel y F3.8 tapa `.hc-slide` (Headcount by Team + People & Talent) si no coincide, dejando la portada (`class="slide section-cover"`) intacta. Validado en vivo con Playwright.
8. **Refactor 2026-07-09 — `slide_registry.py`:** las 4 funciones F3.4-F3.7 (agregadas 2026-07-08) eran casi idénticas — cada una con su archivo/marcador/sentinel hardcodeado a mano. A raíz de una propuesta de **Luis Caro** en el canal `tts-bi-data` (formato `deck.md`: metadatos de cada slide declarados en un bloque `::: meta`, en vez de enterrados en código — pensado originalmente para decks tipo MBR, no para el board ejecutivo), se evaluó si adoptar ese formato completo (JSON de chart + renderer genérico) valía la pena. **Decisión: no** — nuestros charts ya jalan solos desde Redshift, no hay ningún `::: chart` que un PO necesite editar a mano, así que esa mitad del problema de Luis no aplica acá; migrar los 8 templates/47 slides a un renderer genérico sería reescribir Template Board desde cero, contra un sistema ya construido con 198+ tests. Lo que **sí se adoptó**, en espíritu: un registro declarativo (`SLIDE_SPECS` en `slide_registry.py`) que documenta, por slide, su archivo de salida, su fuente de frescura y su alcance de overlay — reemplaza las 4 funciones repetidas por un motor genérico (`check_stale_slide`). Agregar Headcount (F3.8) fue agregar una entrada a la lista, no escribir 30 líneas nuevas. Las funciones `_flag_stale_*` originales se conservan como wrappers delgados (compatibilidad con los tests existentes).
9. `merge_standalone.py` → `output/board_standalone.html` (ya incluye los overlays de F3.4/F3.5/F3.6/F3.7/F3.8 si aplicaron)

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
| R5 | cross_down restado | `Net Expansion = upsell + down + pricing + cross_new + cross_readop − cross_down` | Trampa de signos `a_cross_down`. **SKIP (no FAIL) en cierre de Q** — hallazgo 2026-07-08 generando junio real: `fetch_metrics.py` tiene un override temporal documentado ("valores del SS Apr-2026") que sobreescribe `arr_walk_table` con números fijos de abril en TODO cierre de Q, deuda técnica ya conocida de Template Board — comparar contra eso siempre diverge, no es un bug de esta regla. |
| R6 | FX residual pequeño | `abs(FX Impact) < $3M` | Si es mayor, hay error en lógica FX |
| R7 | Logos usa deduplicación | `logos_eop` viene de `logos_all` (COUNT DISTINCT), no de `l_eop` del summary | Diferencia de ~38 logos |
| R8 | CC del mes base = EoP regular | `arr_cc[mes_actual] ≈ arr_eop[mes_actual]` (ratio FX = 1) | — |
| R19 | ARR EoP coincide entre "Monthly Performance" y "YTD Performance" (mismo `{{ metrics.arr_total }}` renderizado 2 veces en `1_inicio.j2`) — ✅ implementada 2026-07-08, "Agente 3" de la reunión original del 19-jun (consistencia entre slides, ver `memory/project_board_collaboration_roadmap.md`). Validado en vivo: PASS contra `board_standalone.html` real, ambas slides con $29.8M | Bug v36 (mismo patrón: ARR sin Alanube en una vista) |

**Reglas de consistencia — si falla, revisar antes de publicar:**

| # | Regla |
|---|---|
| R9 | Mes de cierre de Q (mar/jun/sep/dic) → comparación QoQ; resto → MoM; debe ser consistente en todas las slides |
| R10 | Churn rate entre 0% y 20% (si es mayor, probable doble conteo) |
| R11 | Budget en cierre de Q = suma de los 3 meses del Q, no solo el mes puntual. **Bug corregido 2026-07-08** (primer cierre de Q real probado, junio): buscaba el valor en la columna con el mismo nombre que `Fecha`, pero el CSV real lo guarda siempre en la primera columna de datos (igual que lee `merge_budget()`) — daba falso "faltan" con los 3 meses completos. |
| R12 | Número de slides en el standalone ≈ 47 (si < 40, algo no se generó) |

**Reglas de estilo:**

| # | Regla |
|---|---|
| R13 | Investment: delta en negro/neutro (sin verde/rojo) — ✅ implementada 2026-07-06, parsea HTML (`_check_color_rules`), validado 20/20 celdas en mayo-26 |
| R14 | Churn Rate y CAC: delta invertido (negativo = verde, positivo = rojo) — ✅ implementada, 40/40 celdas correctas |
| R15 | Resto de métricas: positivo = verde, negativo = rojo — ✅ implementada, 119/119 celdas correctas |

**Reglas de cumplimiento de diseño (gap identificado en la reunión de colaboración 19-jun-2026 —
ver `memory/project_board_collaboration_roadmap.md`):**

| # | Regla |
|---|---|
| R16 | Ningún slide-shell (`SLIDE_CLASS_TOKENS`) fuerza width/height en px vía inline style — protege el 960×540 que viene de `--slide-width`/`--slide-height` en `base.css` — ✅ implementada 2026-07-06, verificado 0 falsos positivos contra los 8 templates reales |
| R18 | Ningún slide-shell recorta contenido en silencio por overflow — compara `scrollHeight`/`scrollWidth` (contenido real) contra `clientHeight`/`clientWidth` (espacio visible) con Playwright, sobre el HTML ya generado — ✅ implementada 2026-07-08 (Bloque 4 del roadmap de colaboración). Empieza en **WARN**, no FAIL (regla nueva, decisión del usuario). Requiere Playwright + Chromium instalados; si no están, SKIP explícito — no es una dependencia dura de `run.py`. Validado en vivo contra `board_standalone.html` real: encontró un hallazgo genuino de +3px en la slide "Acquisition Funnel" (probable redondeo de un canvas de Chart.js, no un bug visual perceptible) — evidencia de que la regla funciona, no solo teoría. `.board-slide` (Template 4) usa `min-height`, no `height` — nunca dispara esta regla, es un comportamiento distinto fuera de alcance. |

**Regla de completitud de datos externos:**

| # | Regla |
|---|---|
| R17 | Net Revenue / Gross Margin / EBITDA Margin (P&L) presentes y no vacíos — ✅ implementada 2026-07-08, junto con bajar F0.4 de FAIL a WARN (ver sección Fase 0). Es el freno real si Finance no ha mandado el P&L del mes: antes bloqueaba todo desde el inicio, ahora el board se arma completo y este check lo detiene acá, antes de aprobar. **Bug corregido 2026-07-08** (mismo día, generando junio real): `fetch_metrics.py` no deja estos campos vacíos/`None` cuando faltan, les pone el string literal `"N/A"` — `not "N/A"` es `False`, así que la regla nunca disparaba en la práctica desde que se escribió. Ahora trata `"N/A"` igual que vacío. |

Candidatos evaluados y **descartados** (riesgo real de falsos positivos, no solo teórico):
- "Todo `.slide-header` debe traer `.title` y `.period`" — **falso**: `8_appendix.j2` tiene 3 slides de "Churned companies breakdown" con header solo-título, legítimo. Verificado con grep contra los 8 templates antes de escribir la regla.
- ~~Detección real de overflow de texto~~ — ✅ implementada 2026-07-08 como **R18** (ver tabla de arriba).
- **Paleta de colores permitida** — evaluado a fondo 2026-07-08, no solo en teoría: se comparó la paleta oficial de Alegra (Design MCP, `color.*`) contra los colores reales de `styles/base.css` — solo 6/14 coinciden exactamente, el resto (`#0f172b`, `#14b8a6`, `#9ca3af`, `#c2410c`, `#e5e7eb`, `#ffedd5`) son elegidos a mano para este board, no vienen del design system de producto. Además cada template mete sus propios acentos (`#534AB7`/`#1D9E75` Core/Lite en `3_arr_walk.j2`) — el universo real es **169 colores hex distintos** entre `base.css` + los 8 `.j2`, sin curaduría central. Una regla "avisa si el color no está en la paleta X" dispararía con cualquier acento nuevo legítimo. Se le propuso al usuario una versión angosta de bajo ruido (detector de casi-duplicados/typos, ej. `#534ab6` vs `#534ab7`) — decidió explícitamente no construirla. Descartado, no solo pospuesto.

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
                    │  19 reglas duras + consistencia         │
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

---

## 6. Self-Service — Skills de colaboración (2026-07-08)

Salidas del workshop de colaboración del 2026-07-08 (Luis Caro, Mayra Gutiérrez, Santiago González,
Sofía Maldonado): el equipo pidió poder editar contenido del board sin depender de Sebastián. Se
construyeron 2 skills de Claude Code (formato estándar: `SKILL.md` con frontmatter, Propósito,
Contexto, Auto-pilot, Reglas de oro, Ejecución) más un prototipo de vista previa:

| Skill/herramienta | Qué hace | Alcance |
|---|---|---|
| `skills/ceo-highlights/` | Edita `Template Board/data/editorial/ceo.yaml` (Highlights, Lowlights, Financial Update, `updated_for_month`) | Slide "CEO Highlights & Lowlights" (`1_inicio.j2`) |
| `skills/slide-comments/` | Agrega/edita un comentario (`asks`) en `arr_walk.yaml` | Solo slides ARR Core y ARR Lite (`3_arr_walk.j2`) — **no** es un mecanismo genérico para cualquier slide todavía, ver limitantes en la skill |
| `preview.py` | CLI que screenshotea una slide ya generada (Playwright, lectura de `Template Board/output/*.html`) para que alguien no técnico vea el resultado sin abrir un HTML | Cualquier template ya generado — busca por texto visible de la slide |

**Bug real encontrado y corregido en el camino:** `arr_walk.yaml` tenía los campos `asks`/`alanube_insight`
con CSS ya definido en `3_arr_walk.j2`, pero el template nunca los renderizaba — un panel fantasma
desde antes de esta sesión. Se conectó `asks` (ver `skills/slide-comments/SKILL.md` para el detalle
del fix y la validación visual con Playwright). `alanube_insight` sigue sin conectar — deuda técnica
documentada, no arreglada en esta pasada.

**Restricción de arquitectura respetada en todo esto:** ninguna de estas 3 piezas escribe dentro de
`Template Board/` desde Board Agent — las skills editan YAMLs que Template Board ya leía, y
`preview.py` solo lee `output/*.html` ya generado por `generate.py`. El único cambio de template
(`3_arr_walk.j2`, para des-fantasmizar el panel) se hizo una vez, directo en Template Board, fuera
del código de Board Agent — no se repite este patrón hacia adelante.

**Pendiente:** tests para `preview.py` (hecho, `tests/test_preview.py`), documentar ambas skills +
`preview.py` en el Playbook de la wiki (pendiente — ver `memory/project_board_collaboration_roadmap.md`).

---

## 7. De "una skill por slide" a un self-service general (2026-07-09)

**El problema que hizo repensar el enfoque:** al construir la sección 6, cada skill nueva
(CEO Highlights, ARR Walk comments) requería enganchar a mano un campo YAML + un bloque
Jinja2 para ESA slide específica. Revisando el board completo se confirmó que **NPS y
Country Performance no tienen ningún mecanismo de comentario** — ni siquiera "fantasma" como
tenía `arr_walk.yaml` antes de conectarse. Con 47 slides y solo 3 cubiertas, seguir
construyendo "una skill por slide a medida que alguien la pide" no escala, y no cumple lo que
el equipo pidió explícitamente: poder tocar **cualquier slide**, de forma muy fácil, en
lenguaje natural, sin importar qué tan técnica sea la persona.

**Reflexión (usuario, 2026-07-09):** las 3 skills construidas no fueron desperdicio — pero
son el nivel de abstracción equivocado para lo que el equipo realmente pidió. En vez de
recetas puntuales por campo/slide, hace falta una **capacidad general**: hablar con la IA
sobre cualquier parte del board, con una experiencia guiada (comparada explícitamente con un
"menú de videojuego") porque el público va desde muy técnico hasta cero técnico.

**3 skills nuevas, construidas a partir de esa reflexión:**

| Skill | Qué resuelve |
|---|---|
| `skills/board-assistant/` | Punto de entrada guiado — si el pedido es vago o es la primera vez de la persona, ofrece un menú de 4 opciones (construir board nuevo / actualizar / agregar-corregir contenido / verificar un dato) y deriva a la skill correcta. Referenciado también desde `CLAUDE.md` para que aparezca proactivamente. |
| `skills/edit-slide-content/` | Generaliza `ceo-highlights`/`slide-comments`/`discussion-topic` — para CUALQUIER slide: detecta si el mecanismo de datos ya existe (y en ese caso usa la skill correspondiente) o construye el enganche nuevo (YAML + bloque Jinja2, reusando el patrón visual de `.aw-comments-panel` como referencia de diseño, conectado a `slide_registry.py` si el contenido es sensible al mes). Incluye guía para agregar una slide nueva (ej. al Appendix) con el checklist de Validator correspondiente (R12, R16, R18). |
| `skills/verify-data-point/` | Formaliza el procedimiento real usado el 2026-07-09 para verificar el ARR de junio contra un dashboard externo (que resultó ser mock) — reconstruir el dato independiente desde Redshift (mismo criterio que R5/R7 del Validator) en vez de solo repetir lo que dice `metrics.yaml`, y comparar. |

**Decisión de alcance explícita:** las 3 skills anteriores (`ceo-highlights`, `slide-comments`,
`discussion-topic`) NO se descartan — quedan como los "casos ya resueltos" que
`edit-slide-content` usa directamente en vez de reconstruir su lógica. El trabajo de esta
sesión no se pierde, se generaliza.

**Relación con la propuesta de Luis Caro (`deck.md`, sección anterior de esta misma
conversación de diseño):** se mantiene la misma decisión de no migrar a un renderer genérico
con specs de chart en JSON — el problema real que resolver era la experiencia de edición
guiada para no-técnicos, no la estructura de los templates en sí.

## 7.1 AGENTS.md — Board Agent no depende de una sola herramienta de IA (2026-07-10)

**El problema:** los `SKILL.md` (y `CLAUDE.md`) son convenciones propias de Claude Code — el
"auto-trigger" por `description` solo lo interpreta su harness. El equipo de datos usa Claude
Code para tareas pesadas, pero la mayoría del resto del equipo corre otras herramientas de IA
(OpenCode con DeepSeek, por ejemplo) — si Board Agent solo funcionara bien en Claude Code,
gran parte del equipo quedaría fuera del self-service que se construyó en la sección 7.

**Solución (inspirada directamente en el propio repo de Luis Caro,
`Alegra-Data/alegra-slides`, que mantiene un `AGENTS.md` junto a su `CLAUDE.md`):** se agregó
`Board Agent/AGENTS.md` — el mismo contenido esencial de las 3 skills nuevas y las reglas de
oro (no tocar Template Board sin avisar, nunca editar `output/*.html` a mano, usar
`redshift_guard.py`, confirmar visualmente), pero en el formato abierto (`AGENTS.md`) que
Cursor, Codex, OpenCode y otras herramientas cargan automáticamente. No requirió tocar el
pipeline: `run.py` y los scripts de `board_agent/` ya eran Python plano sin ninguna
dependencia de una IA específica — el único punto de bloqueo real era la capa de experiencia
guiada (skills), y esa capa ahora tiene una versión tool-agnostic.
