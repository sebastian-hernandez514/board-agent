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

`Template Board/templates/2_discussion_topic.j2` **NO es un template genérico que lee un YAML** —
son slides de HTML escritas a mano, una por una, cada mes. `data/editorial/discussion_topics.yaml`
existe pero está **desconectado**: tiene un schema propio que el `.j2` nunca lee. Es un scaffold
abandonado — **no pierdas tiempo llenándolo**, no hace nada.

Esto significa que "agregar un discussion topic" = escribir HTML nuevo dentro de
`2_discussion_topic.j2`, siguiendo los patrones visuales que ya existen ahí. Ver
`references/layouts.md` para los 5 patrones reales extraídos del archivo (cover, lista de insights,
dos columnas, imagen full-bleed, chart+tablas).

---

## Auto-pilot

1. Preguntar en lenguaje simple: título del topic, cuántas slides de contenido tiene (normalmente
   1-3), y para cada una qué layout encaja mejor (ver `references/layouts.md`) — si la persona no
   sabe, mostrarle los 5 patrones con una frase de "úsalo cuando..." cada uno y que elija.
2. Leer `2_discussion_topic.j2` completo para ver cuántos topics y slides ya existen ese mes (no
   asumir que está vacío — normalmente ya hay 1-2 topics de meses anteriores o del mismo mes).
3. Escribir el HTML nuevo **al final**, antes de `</body>`, copiando el patrón exacto de
   `references/layouts.md` y reemplazando los placeholders `{{...}}` con el contenido real.
4. Insertar `<div class="slide-divider">↓ &nbsp; N / M</div>` entre cada slide nueva (ver regla
   de numeración en `references/layouts.md` sección 0).
5. Si hay imágenes nuevas: pedirlas, convertirlas a base64, y ponerlas directo en el `src` — nunca
   como referencia a archivo (ver Regla de oro #4, es el bug que más ha dolido en este template).
6. Avisar al usuario qué se agregó y en qué líneas, y recordarle correr `generate.py --template
   2_discussion_topic` para ver el resultado.

---

## Reglas de oro

1. **Nunca inventes una clase CSS nueva sin confirmar primero.** Los 5 patrones de
   `references/layouts.md` cubren la enorme mayoría de casos. Si de verdad no encaja ninguno,
   dile al usuario "esto no encaja en los layouts existentes, ¿lo armamos con un patrón nuevo o lo
   ajustamos a uno de los 5?" — no improvises CSS sin avisar.
2. **Dimensiones fijas: 960×540px** (`--slide-width`/`--slide-height` de `styles/base.css`). Nunca
   fijar `width`/`height` manualmente en una slide — `.slide` o `.dt-slide` ya lo hacen.
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
7. **Los colores de delta en la tabla de resultados (patrón 4) son verde/gris, no verde/rojo.**
   Este template es narrativo, no financiero — no le apliques la lógica de semáforo rojo/verde de
   R13-15 del Validator (`board_agent/phase4_validator.py`), es un dominio distinto.

---

## Layouts disponibles

| # | Patrón | Úsalo cuando... |
|---|---|---|
| 0 | Cover (section-divider) | Siempre, al iniciar un topic nuevo — 1 por topic |
| 1 | Numbered insights list | 3-5 hallazgos/aprendizajes cualitativos con texto |
| 2 | Two-column: bullets + visual | 3-4 cambios/decisiones + un mockup o imagen de apoyo |
| 3 | Full-bleed image | Una sola imagen/diagrama que ya trae su propio contexto |
| 4 | Chart + comparison tables | Un resultado con evolución en el tiempo (antes/después) |

Snippets copy-paste completos de los 5 → `references/layouts.md`.

---

## Ejecución

```bash
cd "/Users/sebastian_alegra/Alegra IA/Template Board"
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
| "Quiero agregar un discussion topic sobre X" | Auto-pilot completo: preguntar contenido, elegir layout, escribir HTML |
| "¿Qué layouts hay disponibles?" | Mostrar la tabla de 5 patrones de arriba, con 1 frase de cuándo usar cada uno |
| "Tengo estos bullets y esta imagen, ¿cómo los meto?" | Patrón 2 (two-column) si hay bullets + visual, patrón 3 si es solo imagen |
| "Quiero mostrar cómo mejoró X desde que hicimos Y" | Patrón 4 (chart + tablas) |
| "¿Edito el discussion_topics.yaml?" | No — está desconectado, no hace nada. Ver Contexto. |
| "¿Cómo numero los slides?" | Ver `references/layouts.md` sección 0 — depende de cuántas slides tiene el topic |
| "Quiero un layout que no está en la lista" | Preguntar si conviene ajustar a uno de los 5 antes de crear CSS nueva (Regla de oro #1) |
| "La imagen no se ve en el board final" | Casi siempre es el bug de re-embed (Regla de oro #4) — revisar si el `src` es base64 o referencia a archivo |
| "¿Puedo borrar un topic de un mes anterior?" | Confirmar con el usuario primero — no es parte del auto-pilot por defecto |
| "¿Necesito correr el pipeline completo de RS?" | No — solo `generate.py --template 2_discussion_topic`, ver Ejecución |

---

## Recursos

- **`references/layouts.md`** — los 5 patrones de slide con HTML copy-paste, gotchas de cada uno, y checklist antes de agregar un topic.

## Limitantes

- Esta skill no valida contenido editorial (ortografía, tono, precisión de los datos que trae el usuario) — eso sigue siendo criterio humano.
- No genera gráficos SVG complejos automáticamente — para el patrón 4 (chart), ver la nota en `references/layouts.md` sobre generar coordenadas de `<polyline>` a partir de una serie de números.
- No corre ni valida el pipeline del Board Agent (Fases 0-6) — esta skill solo escribe la slide; el Validator y el Diff siguen corriendo aparte cuando se genera el board completo.
