---
name: verify-data-point
description: >
  Verifica de forma independiente un número del board que alguien pone en duda — reconstruye
  el dato directo desde Redshift (sin confiar ciegamente en metrics.yaml) y compara. Úsala
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
`metrics.yaml`, se reconstruyó el número **desde cero, directo de Redshift**, aplicando a mano
la misma lógica de negocio documentada — eso encontró que el número de Board Agent era correcto
y que la fuente del usuario era Budget, no Real. Esta skill formaliza ese procedimiento para
que se pueda repetir sin tener que inventarlo cada vez.

**Qué NO hace esta skill:** no asume que Board Agent tiene razón — el objetivo es encontrar la
verdad, no defender el número existente. Si la reconstrucción independiente confirma que
`metrics.yaml`/`fetch_metrics.py` están mal, hay que decirlo así de claro.

---

## Auto-pilot

### Paso 1 — Entender la duda
Preguntar: ¿qué número exacto (ARR, MRR, Churn, New Logos, etc.)? ¿en qué slide/segmento/país?
¿tienen un número de referencia y de dónde sale (para poder comparar fuente contra fuente)?

### Paso 2 — Encontrar el origen del campo
Buscar en `Template Board/scripts/fetch_metrics.py` de dónde sale ese campo específico en
`metrics.yaml` — qué query SQL, qué tabla, qué transformación (FX, filtros, agregación).
`Template Board/CLAUDE.md` documenta la lógica canónica (filtros base, conversión FX por
país, buckets del ARR Walk) — leerla ANTES de escribir cualquier query nueva, no asumir.

### Paso 3 — Reconstruir independiente desde Redshift
Usar `redshift_guard.py` (regla del proyecto — nunca queries directas sin el guard) para
correr una query que reproduzca el cálculo **sin pasar por el código de `fetch_metrics.py`**
— mismo criterio que ya usan `R7` (Logos EoP) y `R5` (Net Expansion) del Validator: una
verificación independiente que no confía en que el código ya calculó bien.

Ejemplo real (ARR de un país con conversión FX):
```python
import sys
sys.path.insert(0, '/Users/sebastian_alegra/Alegra IA')
from redshift_guard import run_query, fetch_results

PARAMS = dict(database="data_table_bi", cluster_identifier="redshift-cluster-2",
              db_user="sebastian-hernandez")
```
Aplicar a mano las reglas documentadas: `amount_mrr / tasa_fx` para CO/MX/AR/PE/ES,
`amount_usd_mrr` directo para el resto — ver tabla completa en `Template Board/CLAUDE.md`.

### Paso 4 — Comparar y reportar
- Si coincide con `metrics.yaml`: confirmar que el número de Board Agent es correcto.
- Si NO coincide con lo que espera la persona: investigar la fuente de SU número antes de
  asumir que Board Agent está mal — puede ser una definición distinta (otro segmento, otro
  corte de fecha, un dashboard con datos mock, como pasó con el caso de Julian) o un bug real.
- Reportar con números concretos — nunca "parece que sí" o "creo que está bien".

### Paso 5 — Si se encuentra un bug real
No corregir `fetch_metrics.py` sin confirmación explícita — es lógica de negocio central de
Template Board, alto impacto (afecta TODOS los boards, no solo el mes en cuestión). Reportar
el hallazgo claro y preguntar cómo seguir.

---

## Reglas de oro

1. **Reconstruir desde la fuente, no desde `metrics.yaml`** — si solo repetís lo que ya dice el
   YAML, no estás verificando nada, solo estás repitiendo el mismo resultado.
2. **Aplicar la lógica de negocio documentada, no inventar una propia** — `Template
   Board/CLAUDE.md` tiene las reglas de FX, filtros y buckets ya validadas; usarlas tal cual.
3. **Investigar la fuente del número "de referencia" antes de asumir que Board Agent está
   mal** — un dashboard externo puede estar mockeado, desactualizado, o medir algo distinto
   (Budget vs Real, con Alanube vs sin Alanube, etc.).
4. **Nunca corregir código de negocio sin confirmación explícita** — reportar el hallazgo,
   preguntar cómo seguir.
5. **Siempre usar `redshift_guard.py`** — nunca queries directas al cliente de Redshift.

## Cómo responder preguntas comunes

| Pregunta / pedido | Qué hacer |
|---|---|
| "Este ARR no me cuadra" | Paso 2-4: reconstruir desde RS, comparar |
| "¿De dónde sale este número?" | Paso 2: rastrear el campo hasta su query/tabla en `fetch_metrics.py` |
| "Yo tengo otro número en [dashboard/reporte]" | Preguntar la fuente exacta antes de comparar — puede ser una definición distinta, no un error |
| "¿Está bien el cálculo de FX de este país?" | Reconstruir manualmente con la tasa real de `tb_trm_banrep` y la regla de redondeo documentada |

## Limitantes

- No reconstruye TODOS los números del board automáticamente — es una verificación puntual,
  a pedido, de un dato específico.
- No reemplaza el Validator (Fase 4) — eso corre solo, esta skill es para cuando alguien
  levanta la mano con una duda puntual.
- Consultar Redshift tiene costo (tiempo + uso del cluster) — no correr reconstrucciones
  completas "por si acaso", solo cuando hay una duda real.
