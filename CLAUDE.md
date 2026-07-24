# Board Agent — Instrucciones para Claude

## Primera interacción — si el pedido es vago, ofrecer el menú

Si quien escribe no especifica qué necesita (ej. "quiero editar el board", "ayúdame con
esto", "no sé por dónde empezar"), o es evidentemente su primera vez en este repo sin un
pedido concreto — invocar la skill `board-assistant` y ofrecer el menú guiado ahí definido
(construir board nuevo / actualizar / agregar-corregir contenido / verificar un dato). No
asumir que la persona conoce las skills, los templates, o cómo pedir las cosas "en el
lenguaje correcto" — el equipo que usa este repo va desde muy técnico hasta cero técnico
(pedido explícito del equipo, 2026-07-09). Si el pedido ya es específico, saltar el menú e ir
directo a la skill que corresponda (`edit-slide-content`, `verify-data-point`,
`ceo-highlights`, `slide-comments`, `discussion-topic`).

## Punto de entrada — leer primero

Antes de cualquier tarea, leer: `docs/AGENT_ARCHITECTURE.md` — tiene el inventario completo de fuentes, las 6 fases, las 19 reglas del Validator, la deuda técnica priorizada y la visión final del sistema.

---

## Qué es esto

Sistema multi-agente para generar el board ejecutivo mensual de Alegra de forma automatizada y validada.

**Self-contained desde 2026-07-10:** todo el pipeline (templates Jinja2, `fetch_metrics.py`,
`generate.py`, `merge_standalone.py`, `generate_pdf.py`, CSVs, YAMLs editoriales) vive dentro
de este mismo repo — ya no depende de ninguna carpeta hermana en el disco de quien lo corre
(antes vivía en `../Template Board/`, absorbido por completo — ver
`memory/project_board_agent.md`).

**Cero Redshift, cero AWS:** este repo no tiene credenciales, perfiles ni usuarios de Redshift
en ningún archivo. Todo dato viene de Metabase, corrido por Claude Code vía su MCP (OAuth) —
mandato de Arquitectura para cualquier agente/skill que quede disponible para el resto del
equipo (ver `memory/project_board_agent.md`, migración 2026-07-10).

## Cómo se obtienen los datos (fase manual de Claude, antes de correr el pipeline)

`fetch_metrics.py`, `phase1_freshness.py`, `phase4_validator.py` (R7) y
`scripts/update_appendix.py` no ejecutan ninguna query — leen resultados ya puestos por
Claude Code en `data/.metabase_cache.json`. **Antes de correr `run.py` o `check_setup.py`**,
Claude debe:

1. Leer `board_agent/metabase_fetch_spec.py` — ahí está la lista completa de qué correr
   (21 queries de negocio + 13 checks de freshness + 1 check de validador independiente),
   con la tabla de Metabase que respalda cada una y su estado de migración. Hay un 14º
   check de Fase 1 (F1.14) que NO requiere correr ninguna query nueva — valida la forma de
   las 21 queries de negocio ya puestas en `cache["queries"]` (nada vacío/mal formado/en
   blanco). Es una versión acotada (no valida columnas/tipos por query todavía — ver
   `metabase_fetch_spec.py` para el alcance pendiente).
2. Correr cada query vía `mcp__metabase__construct_query`/`execute_query` (MBQL — este
   conector no soporta SQL nativo) y escribir los resultados en
   `data/.metabase_cache.json` con la forma documentada en el docstring de
   `metabase_fetch_spec.py`.
3. Recién ahí correr el pipeline normal (`run.py --month YYYY-MM`).

Los patrones de sintaxis MBQL ya resueltos (self-joins con `lib/uuid` explícito, `case` con
default posicional, joins anidados de 2+ stages para replicar `ROW_NUMBER`, etc.) están en
`memory/project_board_agent.md`, sección "CIERRE DEFINITIVO" — no hay que redescubrirlos.

Las 20/20 queries del inventario original ya están migradas (ver `metabase_fetch_spec.py`) — la
última, `_SQL_VALUE_EVENTS` (slide Value Events/Supercontadores), se resolvió creando una tabla derivada
propia (`dm_accountant.value_events_monthly`) en vez de esperar a que Arquitectura copie la cruda
de Amplitude.

## ARR Walk v2 (2026-07-22) — estado local que NO se puede saltear un mes

El ARR Walk (New/Churn/Reactivated/Recovered/Upsell/Downsell) se calcula a nivel de
compañía (metodología validada contra el Excel real de Finance, ver
`memory/project_board_agent.md`). Depende de `data/.company_mrr_history.json` (gitignored,
sembrado una sola vez vía RS directo) — cada corrida de `fetch_metrics.py` lo actualiza
con el mes de corte. **Importante:** si se salta un mes (ej. se corre marzo y después
directamente mayo, sin abril), la clasificación de mayo va a leer un gap de 2 meses y
confundir compañías continuas con "Reactivated" — el pipeline debe correrse mes a mes, en
orden, sin huecos. La query nueva que hay que poblar en Metabase cada mes es "company mrr
mensual (ARR Walk v2)" (ver `metabase_fetch_spec.py`) — simple, sin self-join, un pull del
mes de corte nada más.

**Stock vs Flujo — por qué Core+Lite no siempre suma igual a GLO:** el STOCK (mrr_eop,
BoP/EoP/ARR total) SIEMPRE cuadra Core+Lite=GLO, por construcción (`build_seg_metrics()`
arma "all" como suma literal de segmentos) — el Validator lo verifica mes a mes (R20). El
FLUJO (New/Churn/Upsell/Downsell/Recovered/Reactivated) NO cuadra por diseño — compañías que
migran de plan Lite↔Core (pasa todos los meses) aparecen como "New" en un segmento y "Churn"
en el otro, sin ser plata nueva real; a nivel de compañía completa (GLO) es solo una
continuación. Por eso se retiró R2 (asumía esa igualdad para New MRR) — ver
`memory/project_board_agent.md` sección 2026-07-24 para el ejemplo real (compañía 213808).

**Re-correr un mes ya procesado es seguro (2026-07-24):** `_apply_arr_walk_v2()` detecta si
`state["as_of_month"] >= cutoff` (el mes ya quedó reflejado en `data/.company_mrr_history.json`)
y no hace nada — ni re-clasifica, ni toca el store histórico. Antes de este fix, re-correr un
mes ya cerrado caía en un gap<=0 (no-op de clasificación) que igual se agregaba al store
histórico, pisando con ceros el valor real que ya tenía ese mes — así se corrompió `2026-06`
en `data/arr_walk_v2_monthly_history.json` durante las corridas v8-v10 hasta detectarlo.

## ARR Walk v2 — histórico completo migrado (2026-07-24)

Todo el ARR Walk (no solo el mes de corte) usa la metodología v2 desde 2024-01 en adelante.
`data/arr_walk_v2_monthly_history.json` (SÍ se commitea — agregado por mes×segmento, sin PII,
~60KB) guarda los buckets ya clasificados de cada mes; `build_seg_metrics()` los aplica sobre
`segs_raw` para TODO mes presente ahí (`_apply_arr_walk_v2_historical_overrides`), no solo el
de corte. Se sembró con un backfill único (2022-10→2026-06, vía `redshift_guard.py`, SQL con
`LAG()`/`LEAD()` — MBQL no tiene window functions, por eso este backfill corrió directo contra
Redshift y no por Metabase) — validado contra `~/Downloads/arr_logo_walk_board_agent_v3.csv` y
el Excel de Finance, coincide a la décima en 1Q25-2Q26. De acá en adelante, cada corrida
mensual agrega su propio mes al store (`_append_arr_walk_v2_history`), así nunca vuelve a
hacer falta tocar Redshift para esto. R2 (New MRR Core+Lite ≈ Total) se retiró — su premisa
(Core+Lite siempre suma exacto al total) ya no aplica: GLO se clasifica independiente a nivel
de compañía completa, por diseño (ver docstring de `_apply_arr_walk_v2`).

## Arquitectura — 6 fases

Ver `docs/AGENT_ARCHITECTURE.md` para el diseño completo.

```
Fase 0 — Human Inputs Gate     (temporal, debe desaparecer)
Fase 1 — Data Freshness Check  (lee freshness del cache de Metabase)
Fase 2 — Metrics Computation   (llama a fetch_metrics.py, que lee el cache de Metabase)
Fase 3 — HTML Builder          (llama a generate.py + merge)
Fase 4 — Business Rules Validator
Fase 5 — Diff Review
Fase 6 — PDF Generation        (trigger manual)
```

## Paths clave

Ver `board_agent/paths.py` — todo relativo a `BOARD_AGENT_ROOT` (la raíz de este repo).

## Cómo correr

```bash
cd "/Users/sebastian_alegra/Alegra IA/Board Agent"

# 0) Poblar data/.metabase_cache.json vía el MCP de Metabase (ver metabase_fetch_spec.py)

# Chequeo de arranque (no ejecuta nada, solo diagnostica)
uv run --with pyyaml python check_setup.py --month 2026-05

# Pipeline completo
uv run --with pyyaml python run.py --month 2026-05

# Solo validar un board ya generado
uv run --with pyyaml python run.py --validate-only --month 2026-05

# Solo diff vs board anterior
uv run --with pyyaml python run.py --diff-only --month 2026-05
```

## Preferencias
- Comunicación en español
- Nunca embeber credenciales/API keys en ningún archivo de este repo (mandato de
  Arquitectura, ver `memory/project_board_agent.md`) — el único acceso a datos es el MCP de
  Metabase ya autenticado por OAuth en la sesión de Claude Code.
