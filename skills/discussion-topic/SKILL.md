---
name: discussion-topic
description: >
  Self-service para agregar un "Discussion Topic" nuevo al board ejecutivo mensual de Alegra sin
  depender de Sebastián Hernández. Úsala cuando alguien del equipo (Luis Caro, Mayra Gutiérrez,
  Julian Turini, Santiago González, u otro) quiera agregar una sección de discusión estratégica al
  board (aprendizajes de campo, cambio de pricing, resultado de un experimento, actualización de un
  ICP, etc.). Si la pregunta es "cómo agrego un discussion topic" o ya trae el contenido (título,
  bullets, imágenes, datos), NO pidas que alguien más lo haga — sigue el workflow de esta skill y
  entrega el HTML listo. Trigger phrases: "discussion topic", "agregar tema de discusión al board",
  "nueva sección del board", "slide de discusión", "topic para el board", "agregar aprendizajes al
  board", "meter esto en el board de este mes", "2_discussion_topic".
allowed-tools: Read, Edit, Write, Glob, Grep
metadata:
  team: Board
  domain: board-agent
  kind: authoring
  status: stable
---

# Discussion Topic — Self-Service para el Board

## Propósito

Antes de esta skill, solo Sebastián sabía escribir una slide de "Discussion Topic" con el diseño
correcto — el conocimiento vivía en su cabeza, no en ningún documento (confirmado: no existía spec
de diseño en ningún `.md` del repo antes de esta skill). Eso lo convertía en cuello de botella,
justamente el problema que el equipo señaló en la reunión de Board del 19-jun-2026. Esta skill
documenta esas reglas de diseño para que cualquiera con acceso al repo y Claude Code pueda agregar
un topic nuevo sin esperar a Sebastián.

**Qué NO hace esta skill:** no toca datos de Redshift, no corre el pipeline de `fetch_metrics.py`,
no valida números — solo genera el HTML de la(s) slide(s) de discusión siguiendo el diseño existente.
El contenido (qué decir, qué datos mostrar) lo trae la persona que pide el topic.

---

## Contexto — cómo funciona hoy (importante, no es lo que parece)

`templates/2_discussion_topic.j2` **NO es un template genérico que lee un YAML** —
son slides de HTML escritas a mano, una por una, cada mes. `data/editorial/discussion_topics.yaml`
existe pero está **desconectado**: tiene un schema propio que el `.j2` nunca lee. Es un scaffold
abandonado — **no pierdas tiempo llenándolo**, no hace nada.

Esto significa que "agregar un discussion topic" = escribir HTML nuevo dentro de
`2_discussion_topic.j2`. **Corrección importante (2026-09-22):** no hay un sistema de "5
patrones genéricos" reutilizables — eso se documentó una vez pero nunca se construyó de
verdad (un compañero lo confirmó con grep: esas clases no existen en ningún CSS del repo).
Lo que existe de verdad: cada topic real (Expansion, Core Acquisition) es un mini-sitio
autocontenido con su propio prefijo CSS (`dtexp-`, `dtca-`) escrito a mano — agregar un topic
nuevo es **copiar uno existente completo y adaptarlo**, no rellenar una plantilla genérica.
Ver `references/layouts.md` para el recipe exacto y por qué.

---

## Auto-pilot

1. Preguntar en lenguaje simple: título del topic, cuántas slides de contenido tiene (normalmente
   1-3), y si la historia necesita interactividad (filtros, tablas que se expanden — como
   Expansion/`dtexp-`) o es una secuencia lineal de gráficos+texto (como Core Acquisition/`dtca-`)
   — eso decide cuál de los 2 topics existentes conviene copiar como base (ver `references/layouts.md`).
2. Leer `2_discussion_topic.j2` completo para ver cuántos topics y slides ya existen ese mes (no
   asumir que está vacío — normalmente ya hay 1-2 topics de meses anteriores o del mismo mes), y
   qué prefijos CSS ya están en uso (para no elegir un prefijo nuevo que choque).
3. **Copiar el bloque COMPLETO** del topic de referencia elegido (su `<style>`, sus
   `<div class="{prefijo}-board-slide">`, su `<script>` si tiene) al final del `<body>`, **renombrar
   el prefijo en TODAS las ocurrencias**, y reemplazar el contenido con el real. Ver
   `references/layouts.md` para el recipe completo — no es rellenar placeholders de un patrón, es
   adaptar una implementación real.
4. Insertar `<div class="slide-divider">↓ &nbsp; N / M</div>` entre cada slide nueva (ver
   `references/layouts.md`).
5. Si hay imágenes nuevas: pedirlas, convertirlas a base64, y ponerlas directo en el `src` — nunca
   como referencia a archivo (ver Regla de oro #4, es el bug que más ha dolido en este template).
6. **Registrar `"{prefijo}-board-slide"` en `board_agent/paths.py::SLIDE_CLASS_TOKENS` — paso
   OBLIGATORIO, no opcional.** Sin este paso el Validator y el PDF cuentan mal las slides del
   board (ya pasó 2 veces por saltarse esto: 2026-07-27 y 2026-08-19, ver el comentario en
   `paths.py` para el historial). No hay que tocar nada más — desde 2026-09-22
   `scripts/generate_pdf.py` importa esta misma lista, ya no mantiene una copia separada.
7. Avisar al usuario qué se agregó y en qué líneas, y recordarle correr `generate.py --template
   2_discussion_topic` para ver el resultado.

---

## Reglas de oro

1. **No escribas CSS desde cero — copiá un topic existente (`dtexp-` o `dtca-`) y adaptalo.**
   No hay un catálogo de patrones genéricos para elegir; los 2 topics reales de
   `2_discussion_topic.j2` son la referencia. Si de verdad ninguno de los dos se parece a lo
   que necesitás, decile al usuario "esto es bastante distinto a lo que ya existe, ¿lo armamos
   igual copiando el más parecido y ajustando bastante, o preferís que lo revisemos juntos
   antes?" — no improvises sin avisar.
2. **Dimensiones fijas: 960×540px** (`--slide-width`/`--slide-height` de `styles/base.css`, o
   el `width:960px;height:540px` fijo dentro de cada `-board-slide` prefijado). Nunca fijar
   `width`/`height` manualmente en una slide suelta — copiá esa regla del topic de referencia.
3. **Usa los tokens de color de `base.css`, nunca hex nuevos.** `--color-navy`, `--color-teal`,
   `--color-surface`, `--color-border`, `--color-text-primary`, `--color-text-secondary`. Si
   necesitas un color que no está en la paleta, pregunta antes de inventar uno.
4. **Imágenes nuevas van embebidas en base64 desde el inicio — nunca como `src="ruta/archivo.png"`.**
   La única automatización de re-embed que existe (`board_agent/phase3_html_builder.py::
   _reembed_cr_image`) está **hardcodeada al nombre `cr-landing-icp.png`** — cualquier imagen nueva
   con otro nombre queda con el link roto en el `board_standalone.html` sin que nadie lo note, el
   mismo bug silencioso que el equipo ya sufrió antes con esa imagen. Evítalo de raíz: convierte la
   imagen a base64 vos mismo al escribir el HTML (`base64.b64encode(...)` en Python) en vez de dejar
   que un paso posterior la reemplace.
5. **No toques el HTML de topics de meses anteriores o de otro topic del mismo mes.** Agregar
   siempre al final, antes de `</body>`. Si hay que corregir un topic viejo, es una tarea aparte —
   confirmar con el usuario primero.
6. **`data/editorial/discussion_topics.yaml` no se usa — ignóralo.** No lo llenes pensando que
   alimenta el template; hoy no hace nada (ver Contexto arriba).
7. **Los colores de delta son semánticos (verde=bien, rojo/coral=mal), no el semáforo del board
   financiero.** Este template es narrativo, no financiero — no le apliques la lógica invertida
   de Churn/CAC (R13-15 del Validator, `board_agent/phase4_validator.py`), es un dominio distinto.
8. **Registrá la clase `-board-slide` nueva en `board_agent/paths.py::SLIDE_CLASS_TOKENS` —
   siempre, sin excepción.** Es el paso que ya se olvidó 2 veces (2026-07-27, 2026-08-19) y
   rompió el conteo de slides del PDF/Validator ambas veces. No hace falta tocar
   `scripts/generate_pdf.py` — desde 2026-09-22 importa esta misma lista.

---

## Topics de referencia disponibles hoy

| Prefijo | Topic | Úsalo como base cuando... |
|---|---|---|
| `dtexp-` | Expansion / Cross-Sell & Up-Sell | necesitás interactividad — filtros por país, filas de tabla que se expanden, tooltips |
| `dtca-` | Core Acquisition | historia lineal de slides con gráficos (Chart.js) + callouts + KPIs, sin interactividad |

Más la portada compartida `section-divider` (siempre, ver arriba). El recipe completo (copiar,
renombrar prefijo, adaptar, registrar la clase) está en `references/layouts.md`.

---

## Ejecución

```bash
cd "/Users/sebastian_alegra/Alegra IA/Board Agent"
# después de editar 2_discussion_topic.j2:
uv run --with jinja2 --with pyyaml python3 scripts/generate.py --template 2_discussion_topic
# abrir output/2_discussion_topic.html en el navegador para revisar
```

No hace falta correr `fetch_metrics.py` — este template no lee `metrics.yaml`, solo el HTML propio
y `config.month_label`.

---

## Cómo responder preguntas comunes

| Pregunta / pedido | Qué hacer |
|---|---|
| "Quiero agregar un discussion topic sobre X" | Auto-pilot completo: preguntar contenido, elegir topic de referencia, copiar+adaptar, registrar clase |
| "¿Qué layouts/patrones hay disponibles?" | No hay un catálogo genérico — mostrar los 2 topics reales (`dtexp-`/`dtca-`) como referencia, ver tabla de arriba |
| "Tengo estos bullets y esta imagen, ¿cómo los meto?" | Copiar `dtca-` (más simple, sin interactividad) y adaptar una de sus slides de gráfico+callout |
| "Quiero mostrar cómo mejoró X desde que hicimos Y" | Copiar `dtca-` — ya tiene el patrón de KPI de portada + gráfico de evolución |
| "¿Edito el discussion_topics.yaml?" | No — está desconectado, no hace nada. Ver Contexto. |
| "¿Cómo numero los slides?" | Ver `references/layouts.md` — depende de cuántas slides tiene el topic |
| "Quiero un layout muy distinto a los 2 que existen" | Avisar que es más trabajo (no hay un tercer patrón listo) antes de improvisar CSS nueva (Regla de oro #1) |
| "La imagen no se ve en el board final" | Casi siempre es el bug de re-embed (Regla de oro #4) — revisar si el `src` es base64 o referencia a archivo |
| "El PDF/Validator cuenta mal las slides" | Revisar si se registró la clase `-board-slide` nueva en `paths.py::SLIDE_CLASS_TOKENS` (Regla de oro #8) |
| "¿Puedo borrar un topic de un mes anterior?" | Confirmar con el usuario primero — no es parte del auto-pilot por defecto |
| "¿Necesito correr el pipeline completo de RS?" | No — solo `generate.py --template 2_discussion_topic`, ver Ejecución |

---

## Recursos

- **`references/layouts.md`** — el recipe real (copiar/renombrar/adaptar/registrar), los 2 topics
  de referencia, convenciones de nombres, y checklist antes de agregar un topic.

## Limitantes

- Esta skill no valida contenido editorial (ortografía, tono, precisión de los datos que trae el usuario) — eso sigue siendo criterio humano.
- No genera gráficos complejos automáticamente — si el topic necesita un SVG a mano (como el
  scatter de `dtexp-`), ver la nota en `references/layouts.md` sobre generar coordenadas de
  `<polyline>`/`<canvas>` a partir de una serie de números, o directamente usar Chart.js como
  hace `dtca-` (más simple).
- No corre ni valida el pipeline del Board Agent (Fases 0-6) — esta skill solo escribe la slide; el Validator y el Diff siguen corriendo aparte cuando se genera el board completo.
