---
name: ceo-highlights
description: >
  Self-service para escribir o actualizar los Highlights, Lowlights y el Financial Update del
  CEO en el board mensual de Alegra — sin depender de Sebastián Hernández. Úsala cuando alguien
  (Mayra Gutiérrez u otra persona del equipo) quiera agregar, cambiar o revisar el contenido de
  la slide "CEO Highlights & Lowlights". Si la persona ya trae el contenido en lenguaje natural
  (lo bueno del mes, lo malo del mes, el resumen financiero), NO pidas que alguien más lo escriba
  — sigue el workflow de esta skill y actualiza el archivo directo. Trigger phrases: "highlights
  del CEO", "lowlights", "CEO high and lows", "agregar un highlight", "actualizar los puntos
  altos y bajos", "resumen financiero del board", "financial update".
allowed-tools: Read, Edit, Write, Glob, Grep
metadata:
  team: Board
  domain: board-agent
  kind: authoring
  status: stable
---

# CEO Highlights / Lowlights — Self-Service

## Propósito

La slide 2 del board ("CEO Highlights & Lowlights") es texto puro — no requiere ningún dato de
Redshift ni diseño complejo. Antes, solo Sebastián la escribía. Esta skill permite que **Mayra
(dueña de este insumo según el RACI) o cualquier otra persona** lo actualice directamente,
sin depender de él.

**Qué NO hace esta skill:** no inventa contenido — la persona trae las ideas (qué pasó bien, qué
pasó mal, el resumen financiero), la skill solo las escribe en el formato y archivo correctos.

---

## Contexto — el archivo y cómo se usa

Todo vive en `data/editorial/ceo.yaml`. El template (`1_inicio.j2`, slide 2) lo
lee así:
- `ceo_title` → título de la slide (casi nunca cambia: "CEO Highlights & Lowlights").
- `highlights` → lista de strings, columna izquierda.
- `lowlights` → lista de strings, columna derecha (arriba).
- `financial_update` → un párrafo opcional, columna derecha (abajo de lowlights). Si se omite o
  queda vacío, ese bloque simplemente no aparece — no rompe nada.
- `updated_for_month` → campo que **no es del template**, es para `phase0_gate.py` (Fase 0 del
  Board Agent): le dice al sistema para qué mes es este contenido, para no dar un falso "todo
  bien" si el archivo quedó con texto de un mes anterior. **Siempre actualízalo.**

---

## Auto-pilot

1. Preguntar en lenguaje simple: "¿qué highlights (lo bueno) y lowlights (lo malo) quieres para
   este mes? ¿hay un resumen financiero (financial update) que agregar?"
2. Leer `ceo.yaml` actual para ver el formato y el mes que tiene ahora mismo.
3. Escribir la nueva versión: reemplazar `highlights`/`lowlights`/`financial_update` con el
   contenido nuevo, actualizar `updated_for_month` al mes que corresponde, dejar `ceo_title`
   igual salvo que la persona pida cambiarlo.
4. Avisar cuántos highlights/lowlights quedaron y recordar correr `generate.py --template
   1_inicio` para ver el resultado.

---

## Reglas de oro

1. **El slide tiene tamaño fijo (960×540) y el contenido que se desborda se corta en silencio**
   — no hay scroll ni aviso. Con el volumen real de mayo-26 (9 highlights, 4 lowlights, 1
   párrafo de financial update) el slide queda lleno pero legible — no te pases mucho de ahí sin
   avisarle a la persona que puede que no quepa todo.
2. **Cada highlight/lowlight es una idea completa por bullet**, no una lista de sub-puntos — mira
   los ejemplos reales en el archivo: una oración con el dato, el contexto, y por qué importa.
3. **Usa números y comparativos siempre que existan** (MoM, YoY, vs budget) — el tono real del
   archivo es "conciso, específico, con la cifra al frente", no genérico ("las ventas mejoraron").
4. **Distingue causa de ruido**: los lowlights reales del archivo explican explícitamente si algo
   es un problema real o un patrón esperado (ej. "Colombia contrajo... driven by a macro pattern
   — not a product or competitive signal"). Si la persona no aclara la causa, pregúntale.
5. **`financial_update` es opcional** — si no hay resumen financiero ese mes, se puede omitir la
   clave por completo o dejarla vacía (`""`); el template no lo va a mostrar ni va a fallar.
6. **Siempre actualiza `updated_for_month`** al mes real (`"YYYY-MM"`) — es lo que evita que Fase
   0 del Board Agent dé un falso PASS con contenido viejo (bug real encontrado 2026-07-08).
7. **No toques `gtm_new_logos_title`/`gtm_acq_title`/`gtm_funnel_title`** al final del archivo —
   son títulos de otras slides (Go to Market), no de esta.

---

## Ejecución

```bash
cd "/Users/sebastian_alegra/Alegra IA/Board Agent"
uv run --with jinja2 --with pyyaml python3 scripts/generate.py --template 1_inicio
```

Abrir `output/1_inicio.html` para revisar. No hace falta correr `fetch_metrics.py` — este
contenido no depende de Redshift.

---

## Cómo responder preguntas comunes

| Pregunta / pedido | Qué hacer |
|---|---|
| "Quiero agregar un highlight sobre X" | Auto-pilot: agregar el bullet nuevo a la lista existente, no reemplazar todo |
| "Quiero rehacer los highlights de este mes" | Confirmar con la persona antes de borrar los anteriores — reemplazar solo si lo pide explícito |
| "¿Cuántos highlights/lowlights debería poner?" | Referencia real: ~9 highlights, ~4 lowlights suele llenar bien el slide sin desbordar |
| "No tengo financial update este mes" | Dejar la clave vacía o quitarla — no es obligatoria |
| "¿Por qué el board sigue mostrando el mes pasado?" | Revisar si `updated_for_month` quedó desactualizado — ver Regla de oro #6 |
| "Quiero ver cómo se ve antes de que se publique" | Correr el comando de Ejecución y abrir el HTML — no hace falta esperar al board completo |

## Limitantes

- No genera contenido por su cuenta — necesita que la persona traiga las ideas y los datos.
- No valida que las cifras mencionadas sean correctas — eso es criterio editorial, igual que antes.
- No controla el desborde de texto automáticamente — ver Regla de oro #1.
