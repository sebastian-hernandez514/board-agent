# Cómo se arma un Discussion Topic — el patrón REAL (no un sistema genérico)

> **Corregido 2026-09-22.** La versión anterior de este archivo documentaba 5 "patrones"
> (`.dt-slide`, `.dt-body`, `.dt-subtitle`, `.cr-chart`, `.cr-funnel`, `.insight-row`,
> `.pricing-cols`, etc.) que **nunca existieron en ningún CSS real del repo** — ni en
> `styles/base.css`, ni en `templates/2_discussion_topic.j2`. Confirmado con grep sobre todo
> el repo (hallazgo de un compañero usando esta skill por primera vez, 2026-09-22): parece
> que alguien diseñó ese sistema genérico y lo abandonó en cuanto el primer topic real
> (Expansion) empezó a resolver su propio layout a mano. Si seguías el archivo viejo al pie
> de la letra, el resultado era un slide sin tamaño (960×540) y sin ningún layout real — la
> skill literalmente producía HTML roto.

## Cómo funciona de verdad hoy

Cada Discussion Topic es un **mini-sitio autocontenido** dentro de `2_discussion_topic.j2`:
su propio bloque `<style>` con un prefijo único (`dtexp-`, `dtca-`), sus propias slides
(`<div class="{prefijo}-board-slide">`), y opcionalmente su propio `<script>` con datos e
interactividad (filtros, tooltips, charts). No hay componentes compartidos entre topics —
cada uno se escribió copiando y adaptando el topic anterior, no rellenando una plantilla.

**Lo único genuinamente compartido** es la portada de sección, definida una sola vez en el
`<style>` de arriba del archivo (líneas ~13-35):

```html
<div class="slide section-divider">
  <div class="eyebrow">{{ CATEGORÍA — ej. "Growth", "Product" }}</div>
  <div class="section-title">{{ TÍTULO DEL TOPIC — acepta <br> para 2 líneas }}</div>
  <div class="topic-label">{{ config.month_label }}</div>
</div>
<div class="slide-divider">↓</div>
```

Usa la clase `slide` (no una prefijada) — ya tiene 960×540 y el fondo navy vía `base.css`.
Poné esto SIEMPRE al iniciar un topic nuevo, con tu propio eyebrow/título.

## El recipe real para agregar un topic — copiar, no rellenar

1. **Elegí un topic existente como referencia** — hoy hay 2 en `templates/2_discussion_topic.j2`:
   - `dtexp-` ("Expansion / Cross-Sell & Up-Sell", líneas ~58-256) — tablas con filas
     colapsables + filtro por país + un chart de dispersión, todo con JS custom.
   - `dtca-` ("Core Acquisition", líneas ~274-627) — 11 slides: KPIs de portada, gráficos
     de barra/línea con Chart.js, callouts de color, grid de acciones — más simple que
     dtexp-, buen punto de partida si tu topic es "gráficos + texto", no interactivo.
   Elegí el que se parezca más a lo que necesitás contar (¿necesitás que alguien haga click
   para explorar datos, como dtexp-? ¿O es una historia lineal de slides con gráficos fijos,
   como dtca-?).
2. **Copiá el bloque COMPLETO** de esa referencia: su `<style>{prefijo}...</style>`, sus
   `<div class="{prefijo}-board-slide">...</div>` (una por slide), y su `<script>` si lo
   tiene — todo, no solo un fragmento.
3. **Renombrá el prefijo en TODO lo que copiaste** (`dtca-` → `dtnuevo-` en cada clase CSS,
   cada `class="..."`, cada `id="..."` referenciado desde JS) — un find & replace del
   prefijo completo. Si dejás clases sin renombrar, van a chocar con el topic que copiaste
   (mismo nombre de clase, dos definiciones de CSS distintas en el mismo archivo — gana la
   que venga después en el orden del documento, comportamiento impredecible).
4. **Adaptá el contenido** (textos, números, datos del chart) al topic real. Los datos van
   embebidos directo en el HTML/JS — no hay YAML que alimente esto (`data/editorial/
   discussion_topics.yaml` existe pero está desconectado, ver SKILL.md).
5. **Registrá la clase nueva — paso obligatorio, no opcional.** Agregá
   `"{prefijo}-board-slide"` a `board_agent/paths.py::SLIDE_CLASS_TOKENS` — es la ÚNICA
   lista que hay que tocar desde el 2026-09-22 (antes `scripts/generate_pdf.py` mantenía su
   propia copia separada, y desincronizarse ahí ya rompió el PDF dos veces: 42/56 slides,
   2026-07-27 y 2026-08-19 — ver el comentario en `paths.py` para el historial completo). Si
   te salteás este paso, el Validator y el PDF van a contar mal las slides del board.
6. **Poné la portada de sección** (`section-divider`, ver arriba) antes de tus slides.
7. **Generá y revisá en el navegador** — ver sección "Ejecución" del `SKILL.md`.

## Convenciones de nombres que SÍ vale la pena imitar

No son clases compartidas (cada topic las redefine con su propio prefijo), pero los 2
topics existentes siguen la misma convención de nombres — mantenerla ayuda a que el CSS que
escribas/adaptes sea predecible:

| Sufijo | Para qué |
|---|---|
| `-board-slide` | el contenedor de la slide (960×540, el que va en `SLIDE_CLASS_TOKENS`) |
| `-head` | barra superior navy con el título de la slide |
| `-body` | contenido principal |
| `-foot` | pie de página (marca + "Topic · N/M") |
| `-lede` / `-eye` | línea de contexto justo debajo del título |
| `-kpi-row` / `-kpi` | tarjetas de números destacados (portada, típicamente) |
| `-callout` (+ `.warn`, `.note`) | recuadro de "so what" / hallazgo clave |
| `-tbl` | tabla de datos |
| `-take` | conclusión/mensaje final de la slide |

**Gotcha de color heredado de `dtca-`:** usa verde/rojo semántico (`-pos`/`-neg`,
`-vpos`/`-vneg`) para bien/mal — está bien para este dominio narrativo (a diferencia del
board financiero, que además invierte el color para Churn/CAC — R13-15 de
`phase4_validator.py` no aplica acá, es un dominio distinto). No hace falta el criterio
neutro verde/gris que se documentaba antes para un "Patrón 4" que no existe.

## Imágenes — sigue aplicando igual que antes

Si tu topic usa una imagen nueva, va embebida en **base64 directo en el `src`** desde que
escribís el HTML — nunca como `src="ruta/archivo.png"`. La única automatización de re-embed
que existe (`board_agent/phase3_html_builder.py::_reembed_cr_image`) está hardcodeada al
nombre `cr-landing-icp.png` de un topic viejo — cualquier imagen nueva con otro nombre queda
con el link roto en el `board_standalone.html` sin que nadie lo note.

## Checklist antes de dar por terminado un topic nuevo

1. ¿Copiaste un topic COMPLETO (CSS+HTML+JS) como base, en vez de escribir desde cero o
   seguir un "patrón" de una lista? (la lista de patrones genéricos no existe más — ver
   arriba)
2. ¿Renombraste el prefijo en TODAS las ocurrencias (CSS, `class=`, `id=`, JS)? Un grep del
   prefijo viejo dentro de tu bloque nuevo no debería devolver nada.
3. ¿Registraste `"{prefijo}-board-slide"` en `board_agent/paths.py::SLIDE_CLASS_TOKENS`?
4. ¿Hay imágenes nuevas? → base64 directo en el `src`, nunca referencia a archivo.
5. ¿Pusiste la portada de sección (`section-divider`) antes de tus slides, con tu propio
   eyebrow/título?
6. ¿Corriste `generate.py --template 2_discussion_topic` y abriste el resultado en el
   navegador para confirmar que se ve bien? (no asumas que "compila" = "se ve bien")
