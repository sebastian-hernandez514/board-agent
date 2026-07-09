---
name: edit-slide-content
description: >
  Editor general de contenido del board — comentarios, títulos, o slides nuevas, en CUALQUIER
  slide (NPS, ARR Walk, Headcount, Appendix, Country Performance, la que sea), no solo las 3
  que ya tenían skill dedicada. Úsala cuando alguien pida agregar/cambiar un comentario, un
  título, o una slide, y no sepas de entrada si esa slide ya tiene un mecanismo de datos
  conectado. Si detecta que el pedido es exactamente uno de los 3 casos ya resueltos (CEO
  Highlights, comentarios de ARR Core/Lite, Discussion Topics), sigue esa misma lógica en vez
  de reinventar nada. Trigger phrases: "agregar un comentario a la slide de NPS/Country
  Performance/Headcount/Appendix", "cambiar el título de esta slide", "corregir un título",
  "agregar una slide nueva", "modificar el contenido de".
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
metadata:
  team: Board
  domain: board-agent
  kind: authoring
  status: stable
---

# Editor General de Contenido de Slides

## Propósito

Nace de una reflexión del usuario (2026-07-09): construir una skill nueva por cada slide que
alguien quiera comentar no escala — el board tiene 47 slides, y solo 3 tenían mecanismo de
comentario/edición (CEO Highlights, ARR Walk Core/Lite, Discussion Topics). El equipo pidió
poder tocar **cualquier slide**, de forma muy fácil, en lenguaje natural. Esta skill generaliza
eso: en vez de "una receta por slide", una sola lógica que sabe **detectar** si el mecanismo ya
existe (y usarlo) o **construirlo** (si no existe todavía).

**Qué NO hace esta skill:** no inventa el contenido — la persona trae la idea (el comentario,
el título nuevo, el HTML de la slide), la skill se encarga del "cómo" técnico.

---

## Contexto — la arquitectura de 3 capas (leer antes de tocar nada)

Cada slide del board vive repartida en 3 lugares:

| Capa | Qué es | Ejemplo |
|---|---|---|
| **Template** (`Template Board/templates/*.j2`) | HTML + Jinja2, define el diseño | `3_arr_walk.j2` |
| **Datos calculados** (`metrics.yaml`) | Lo que arma `fetch_metrics.py` desde Redshift | `metrics.arr_walk_products` |
| **Datos editoriales** (`data/editorial/*.yaml`, o sentinels en el propio `.j2`) | Texto que una persona escribe | `arr_walk.yaml` → `asks` |

Un comentario/título persiste correctamente **solo si vive en la capa 2 o 3** — nunca edites
`output/*.html` a mano, se pierde en la próxima regeneración (ver `memory/project_board_agent.md`,
es exactamente el bug que se pasó media sesión arreglando el 2026-07-08).

---

## Auto-pilot

### Paso 1 — Entender el pedido
Preguntar: ¿cuál slide (nombre o descripción)? ¿qué querés cambiar — un comentario, un título,
agregar una slide nueva? ¿el contenido exacto?

### Paso 2 — Localizar la slide
Buscar en los 8 templates de `Template Board/templates/`:
```bash
grep -n "SLIDE.*<nombre o palabra clave>" Template\ Board/templates/*.j2
```
Los comentarios HTML (`<!-- SLIDE N — ... -->`) son el ancla — ya los usa Board Agent
(`R19`, `F3.6`, `F3.7`, `F3.8`) para ubicar slides sin clase propia.

### Paso 3 — Clasificar: ¿ya existe el mecanismo?

| Si la slide es... | El mecanismo ya existe — usar |
|---|---|
| CEO Highlights / Lowlights / Financial Update | Skill `ceo-highlights` |
| ARR Core o ARR Lite (comentarios) | Skill `slide-comments` |
| Discussion Topics (contenido nuevo) | Skill `discussion-topic` |
| Cualquier otra (NPS, Country Performance, Appendix, contadores, etc.) | **Caso nuevo — ver Paso 4** |

No reinventes estos 3 — ya están probados y documentados.

### Paso 4 — Caso nuevo: construir el enganche

Esto **sí toca el `.j2` fuente de Template Board** — es la única excepción real a "no tocar
Template Board", y requiere ir con cuidado:

1. **Leer el archivo completo alrededor de la slide** — nunca editar a ciegas.
2. **Decidir dónde vive el texto nuevo:**
   - Si la slide ya tiene un YAML editorial propio (poco común) → agregar el campo ahí.
   - Si no, crear (o extender) un YAML chico en `data/editorial/` — un archivo por slide o
     grupo de slides, mismo patrón que `ceo.yaml`/`arr_walk.yaml`.
3. **Reusar el patrón visual ya existente** — el panel de comentarios de ARR Walk
   (`.aw-comments-panel`/`.aw-comment-item`/`.aw-comment-dot-row`, ver `3_arr_walk.j2` líneas
   ~472-485) es el diseño de referencia. Copiar esa convención (mismo look & feel) en vez de
   inventar CSS nuevo — el board debe verse consistente entre slides.
4. **Agregar el bloque Jinja2 condicional** (`{% if slide_data.comment %}`) — nunca
   incondicional, para que si no hay contenido el panel no aparezca (mismo criterio que ARR
   Walk: `{% if product.asks %}`).
5. **Si el contenido es sensible al mes** (un comentario que puede quedar viejo), agregarle el
   mismo sentinel `<!-- updated_for_month: YYYY-MM -->` y una entrada nueva en
   `board_agent/slide_registry.py` (`SLIDE_SPECS`) — así queda cubierto por Fase 0/3
   automáticamente, sin escribir una función nueva.
6. **Avisar explícitamente antes de escribir en el `.j2`** — es un cambio a Template Board,
   igual que se hizo con los sentinels de Discussion Topics/Headcount. No asumas luz verde.
7. **Regenerar y verificar visualmente antes de dar por bueno:**
   ```bash
   cd "Template Board"
   uv run --with jinja2 --with pyyaml python3 scripts/generate.py --template <nombre>
   ```
   Después, usar `preview.py` (Board Agent) o Playwright directo para screenshotear la slide
   afectada Y una slide vecina (confirmar que no se rompió nada alrededor).

### Paso 5 — Agregar una slide nueva (no solo un comentario)

Caso más delicado — checklist adicional:
- Confirmar en qué template va (o si es una nueva, dónde en `8_appendix.j2` u otro).
- La persona puede traer el HTML ya armado, o pedir que la IA lo construya siguiendo el diseño
  existente (mismo criterio que la skill `discussion-topic`).
- Después de agregarla: correr el Validator (`R12` cuenta slides — puede pasar de PASS a WARN
  si el conteo cambia; no es necesariamente un error, pero avisar y decidir si actualizar
  `paths.EXPECTED_SLIDE_COUNT`) y `R16`/`R18` (dimensiones y overflow) para confirmar que la
  slide nueva no rompe nada.
- Confirmar visualmente con Playwright antes de decir que quedó lista.

---

## Reglas de oro

1. **Nunca editar `output/*.html` a mano** — siempre a través de `generate.py`.
2. **Nunca tocar más de lo pedido** — si vas a agregar un panel de comentarios a NPS, no
   toques Country Performance de paso.
3. **Avisar antes de escribir en un `.j2`** — no es un permiso permanente, es caso por caso.
4. **Reusar el patrón visual existente** (`.aw-comments-panel` como referencia) — no inventes
   un estilo nuevo cada vez, el board debe sentirse consistente.
5. **Si el contenido es sensible al mes, conectarlo a `slide_registry.py`** — no dejar otro
   hueco como el que tenía Headcount hasta el 2026-07-09.
6. **Confirmar visualmente (Playwright/`preview.py`) antes de dar el cambio por terminado.**

---

## Cómo responder preguntas comunes

| Pregunta / pedido | Qué hacer |
|---|---|
| "Quiero un comentario en la slide de NPS" | Caso nuevo — Paso 4: construir el enganche en `6_rd.j2`, reusando el patrón visual de ARR Walk |
| "Quiero un comentario en ARR Core" | Ya existe — usar skill `slide-comments` directo |
| "Quiero cambiar el título de la slide de Headcount" | Localizar el título (¿viene de `config`/`editorial` o está hardcodeado?), editar en la capa correcta |
| "Quiero agregar una slide al Appendix" | Paso 5 — más cuidado, checklist de Validator |
| "¿Esto va a romper algo?" | Correr el Validator después de cualquier cambio estructural — es literalmente para eso que existe |

## Limitantes

- Construir el enganche para una slide nueva (Paso 4) requiere criterio de diseño — no es
  100% mecánico, cada slide tiene su propio layout.
- No decide por su cuenta si algo "debería" ser editable — si el equipo pide tocar algo que
  hoy está deliberadamente congelado (ej. la tabla de ARR Walk GLO, marcada "NO CAMBIAR" en
  `Template Board/CLAUDE.md`), avisar eso explícitamente antes de proceder.
