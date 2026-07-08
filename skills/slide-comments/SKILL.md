---
name: slide-comments
description: >
  Self-service para agregar un comentario/ask a una slide del board sin depender de Sebastián
  Hernández — hoy funciona para las slides "ARR Core" y "ARR Lite" (`3_arr_walk.j2`). Úsala
  cuando alguien pida agregar, cambiar o quitar un comentario/nota/ask en una de esas slides.
  Si la persona pide un comentario en una slide DISTINTA (ej. "New Logos"), avísale que ese
  patrón todavía no está conectado ahí — ver sección "Cómo extender a otra slide" antes de
  intentarlo a ciegas. Trigger phrases: "agregar un comentario a la slide", "poner una nota en
  ARR Core/Lite", "team asks", "agregar un ask", "comentario en la diapositiva".
allowed-tools: Read, Edit, Write, Glob, Grep
metadata:
  team: Board
  domain: board-agent
  kind: authoring
  status: stable
---

# Comentarios en una Slide — Self-Service

## Propósito

En el workshop de colaboración del 2026-07-08, Luis Caro pidió explícito "Habilidad 2: agregar
o cambiar un comentario en una diapositiva". Se investigó y se encontró que el mecanismo para
esto **ya existía a medias**: el YAML lo soportaba y había hasta CSS definido, pero **el
template nunca lo renderizaba** — era un panel fantasma. Se conectó el 2026-07-08 para las
slides ARR Core y ARR Lite. Esta skill documenta cómo usarlo.

**Qué NO hace esta skill:** no inventa el comentario — la persona trae el texto, la skill solo
lo escribe en el YAML correcto con el formato correcto.

---

## Contexto — dónde vive y cómo se conecta

Archivo: `Template Board/data/editorial/arr_walk.yaml`, bajo `products` (uno por `id: core` /
`id: lite`):

```yaml
products:
  - id: core
    action_title: "Team Asks"      # título del panel — opcional, si está vacío dice "Comments"
    asks:
      - "Primer comentario/ask."
      - "Segundo comentario/ask."
  - id: lite
    action_title: ""
    asks: []
```

`generate.py` (`_merge_arr_walk_editorial()`) mete `asks`/`action_title` en
`metrics.arr_walk_products[i]`. El template (`3_arr_walk.j2`, slides "ARR Core"/"ARR Lite")
renderiza un panel a la derecha de la tabla **solo si `product.asks` no está vacío** — si la
lista está vacía, el panel no aparece y la tabla ocupa el ancho completo, exactamente como
siempre. Verificado visualmente 2026-07-08 (screenshot con y sin comentario, ambos casos limpios,
la tabla se encoge sin romperse cuando el panel aparece).

---

## Auto-pilot

1. Preguntar: "¿para cuál slide es el comentario — ARR Core o ARR Lite? ¿qué quieres decir?"
2. Leer `data/editorial/arr_walk.yaml` para ver el estado actual de `asks` en ese producto.
3. Agregar el comentario nuevo a la lista `asks` del producto correspondiente (no reemplazar los
   que ya había, salvo que la persona lo pida explícito). Si `action_title` está vacío y la
   persona quiere un título para el panel, agregarlo también.
4. Avisar que hay que correr `generate.py --template 3_arr_walk` para ver el resultado.

---

## Reglas de oro

1. **Máximo 3 comentarios por producto** (ya lo dice el propio comentario del YAML) — el panel
   es angosto (220px), más de 3 se ve apretado o se puede desbordar.
2. **Cada comentario es una idea corta**, no un párrafo — mira el ejemplo real probado: una
   oración con la acción o el pedido, sin relleno.
3. **`action_title` es opcional** — si se deja vacío, el panel muestra "Comments" por defecto
   (viene del propio template: `{{ product.action_title or "Comments" }}`).
4. **No se puede usar todavía en ninguna otra slide** — ver la sección de abajo antes de prometerle
   a alguien que funciona en "New Logos" o cualquier otra.
5. **`alanube_insight` (mismo archivo) sigue sin conectar a ningún template** — es un campo
   hermano de `asks` pero nadie lo renderiza en ningún lado todavía. No lo llenes pensando que
   sirve; queda como deuda técnica pendiente, no arreglada en esta pasada.

---

## Cómo extender a otra slide (para la próxima, no lo hagas sin avisar)

El patrón que se conectó hoy es reusable: un panel lateral (`~200-220px`, `flex-shrink:0`) que
solo aparece si hay contenido, dentro de un contenedor `display:flex`. Para agregarlo a una slide
nueva (ej. "New Logos" en `1_inicio.j2` o `5_go_to_market.j2`) hace falta, por cada slide:
1. Confirmar que el contenedor principal de esa slide sea `display:flex` (o convertirlo) para que
   el panel pueda "quitarle" espacio al contenido sin romper el layout — **probar con Playwright
   o abriendo el HTML antes de dar por bueno**, como se hizo hoy.
2. Agregar el campo `comment`/`asks` correspondiente al YAML editorial de esa slide (puede que
   haga falta crear uno si esa slide no tiene YAML propio todavía).
3. Conectar `generate.py` para que lo pase a `metrics`.
4. Repetir el mismo patrón condicional (`{% if ... %}`) en el template.

**No asumas que esto ya funciona en otra slide solo porque funciona en ARR Walk** — cada slide
tiene su propio layout y puede romperse distinto.

---

## Ejecución

```bash
cd "/Users/sebastian_alegra/Alegra IA/Template Board"
uv run --with jinja2 --with pyyaml python3 scripts/generate.py --template 3_arr_walk
```

Abrir `output/3_arr_walk.html` para revisar antes de dar por bueno.

---

## Cómo responder preguntas comunes

| Pregunta / pedido | Qué hacer |
|---|---|
| "Quiero agregar un comentario a ARR Core" | Auto-pilot: agregar a `products[0].asks` |
| "Quiero un comentario en New Logos" | Explicar que ese patrón no está conectado ahí todavía — ver sección de arriba, es trabajo de desarrollo, no solo de contenido |
| "¿Por qué no aparece mi comentario?" | Revisar que se corrió `generate.py --template 3_arr_walk` después de editar el YAML |
| "Quiero quitar todos los comentarios" | Dejar `asks: []` — el panel desaparece solo, no rompe nada |

## Limitantes

- Solo funciona en ARR Core y ARR Lite hoy — no es un mecanismo genérico para "cualquier slide" todavía, pese a que la idea original del equipo (Luis) era esa.
- `alanube_insight` sigue sin conectar — mismo tipo de deuda que existía en `asks` antes de hoy.
- No valida el contenido del comentario — es texto libre, criterio editorial.
