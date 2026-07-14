---
name: verify-data-point
description: >
  Verifica de forma independiente un número del board que alguien pone en duda — reconstruye
  el dato directo desde Metabase (sin confiar ciegamente en metrics.yaml) y compara. Úsala
  cuando alguien diga "esto no me cuadra", "yo tengo otro número", "¿de dónde sale esta
  cifra?", o quiera confirmar un ARR/MRR/Churn/etc. antes de confiar en el board. Trigger
  phrases: "verificar este dato", "este número no me cuadra", "revisar esta cifra", "confirmar
  el ARR/MRR de este mes".
allowed-tools: Read, Bash, Grep
metadata:
  team: Board
  domain: board-agent
  kind: verification
  status: stable
---

# Verificación Independiente de un Dato

## Propósito

Nace de un caso real (2026-07-08/09): el usuario dudó del ARR de junio ($30.9M) porque un
dashboard externo (mockeado, resultó) le daba $2.45M de MRR. En vez de solo repetir lo que dice
`metrics.yaml`, se reconstruyó el número **desde cero, directo de la fuente**, aplicando a mano
la misma lógica de negocio documentada — eso encontró que el número de Board Agent era correcto
y que la fuente del usuario era Budget, no Real. Esta skill formaliza ese procedimiento para
que se pueda repetir sin tener que inventarlo cada vez.

**Qué NO hace esta skill:** no asume que Board Agent tiene razón — el objetivo es encontrar la
verdad, no defender el número existente. Si la reconstrucción independiente confirma que
`metrics.yaml`/`fetch_metrics.py` están mal, hay que decirlo así de claro.

**Regla de acceso a datos (mandato de Arquitectura, 2026-07-10):** esta skill nunca se conecta
a Redshift ni usa credenciales embebidas — el único acceso a datos es el MCP de Metabase
(`mcp__metabase__*`, MBQL, OAuth ya autenticado en la sesión de Claude Code). Nunca escribir
ni pegar una API key de Metabase en ningún archivo de este repo.

---

## Auto-pilot

### Paso 1 — Entender la duda
Preguntar: ¿qué número exacto (ARR, MRR, Churn, New Logos, etc.)? ¿en qué slide/segmento/país?
¿tienen un número de referencia y de dónde sale (para poder comparar fuente contra fuente)?

### Paso 2 — Encontrar el origen del campo
Buscar en `scripts/fetch_metrics.py` de dónde sale ese campo específico en `metrics.yaml` — qué
`_SQL_*` (el SQL canónico, todavía presente como documentación/spec aunque ya no se ejecuta
contra Redshift), qué tabla, qué transformación (FX, filtros, agregación). Luego mirar
`board_agent/metabase_fetch_spec.py` para encontrar la tabla equivalente en Metabase (schema
`dm_strategic`/`dm_sales`/`dm_retention`/`dm_accountant`/`dm_alanube`) y el estado de esa query.

### Paso 3 — Reconstruir independiente desde Metabase
Usar el MCP de Metabase (`mcp__metabase__construct_query` / `execute_query`, MBQL — este
conector no soporta SQL nativo) para correr una query que reproduzca el cálculo **sin pasar por
el código de `fetch_metrics.py`** — mismo criterio que ya usa `R7` (Logos EoP) del Validator:
una verificación independiente que no confía en que el código ya calculó bien.

Los patrones de sintaxis MBQL ya resueltos (self-joins con `lib/uuid` explícito, `case` con
default posicional, joins anidados de 2+ stages, etc. — ver `memory/project_board_agent.md`,
sección "CIERRE DEFINITIVO") ya cubren la mayoría de la lógica de negocio de este pipeline; no
hay que redescubrirlos desde cero. Aplicar a mano las reglas documentadas: `amount_mrr / tasa_fx`
para CO/MX/AR/PE/ES, `amount_usd_mrr` directo para el resto.

### Paso 4 — Comparar y reportar
- Si coincide con `metrics.yaml`: confirmar que el número de Board Agent es correcto.
- Si NO coincide con lo que espera la persona: investigar la fuente de SU número antes de
  asumir que Board Agent está mal — puede ser una definición distinta (otro segmento, otro
  corte de fecha, un dashboard con datos mock, como pasó con el caso de Julian) o un bug real.
  **También considerar desfase de sincronización de Metabase** (ver
  `metabase_fetch_spec.py` — `tb_trm_banrep` y `accountant_master_table` tuvieron casos reales
  de datos desactualizados en Metabase pese a estar "copiados") antes de concluir que hay un bug.
- Reportar con números concretos — nunca "parece que sí" o "creo que está bien".

### Paso 5 — Si se encuentra un bug real
No corregir `fetch_metrics.py` sin confirmación explícita — es lógica de negocio central del
pipeline, alto impacto (afecta TODOS los boards, no solo el mes en cuestión). Reportar
el hallazgo claro y preguntar cómo seguir.

---

## Reglas de oro

1. **Reconstruir desde la fuente, no desde `metrics.yaml`** — si solo repetís lo que ya dice el
   YAML, no estás verificando nada, solo estás repitiendo el mismo resultado.
2. **Aplicar la lógica de negocio documentada, no inventar una propia** — el SQL canónico en
   `scripts/fetch_metrics.py` tiene las reglas de FX, filtros y buckets ya validadas; usarlas
   tal cual, traducidas a MBQL.
3. **Investigar la fuente del número "de referencia" antes de asumir que Board Agent está
   mal** — un dashboard externo puede estar mockeado, desactualizado, o medir algo distinto
   (Budget vs Real, con Alanube vs sin Alanube, etc.).
4. **Nunca corregir código de negocio sin confirmación explícita** — reportar el hallazgo,
   preguntar cómo seguir.
5. **Solo el MCP de Metabase, nunca Redshift ni una API key embebida** — es la regla de acceso a
   datos de todo el repo, no solo de esta skill.

## Cómo responder preguntas comunes

| Pregunta / pedido | Qué hacer |
|---|---|
| "Este ARR no me cuadra" | Paso 2-4: reconstruir vía MBQL en Metabase, comparar |
| "¿De dónde sale este número?" | Paso 2: rastrear el campo hasta su query/tabla en `fetch_metrics.py` / `metabase_fetch_spec.py` |
| "Yo tengo otro número en [dashboard/reporte]" | Preguntar la fuente exacta antes de comparar — puede ser una definición distinta, no un error |
| "¿Está bien el cálculo de FX de este país?" | Reconstruir manualmente con la tasa real de `tb_trm_banrep` (verificar primero que Metabase no esté desfasado) y la regla de redondeo documentada |

## Limitantes

- No reconstruye TODOS los números del board automáticamente — es una verificación puntual,
  a pedido, de un dato específico.
- No reemplaza el Validator (Fase 4) — eso corre solo, esta skill es para cuando alguien
  levanta la mano con una duda puntual.
- Construir una query MBQL nueva desde cero toma más iteraciones que escribir SQL directo —
  no correr reconstrucciones completas "por si acaso", solo cuando hay una duda real.
