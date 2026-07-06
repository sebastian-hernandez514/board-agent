# Layouts de Discussion Topic — extraídos de `2_discussion_topic.j2` (mayo-26)

Cada topic mensual es una secuencia de slides: **1 cover** + 2-3 slides de contenido. Estos 5 patrones son
los que existen hoy en el archivo real — no son un sistema genérico, son los layouts que Sebastián ya
dibujó a mano. Reusar las clases CSS tal cual; **no inventar clases nuevas** salvo que ninguno de los 5
patrones sirva (ver SKILL.md, regla de oro #6).

Todas las medidas ya asumen el slide de `960×540` (`--slide-width`/`--slide-height` en `base.css`) — no
hace falta fijar tamaño manualmente, `.dt-slide` ya lo hace.

---

## 0. Cover (section-divider) — obligatorio al iniciar un topic nuevo

```html
<div class="slide section-divider">
  <div class="eyebrow">Discussion Topic</div>
  <div class="section-title">{{TITULO_TOPIC}}</div>
  <div class="topic-label">{{ config.month_label }}</div>
  <div class="slide-num">{{NUMERO_SLIDE_GLOBAL}}</div>
</div>
```

- `section-title` acepta `<br>` para partir el título en 2 líneas (ver ejemplo "Mexico Strategy:<br>Learnings & Next Steps").
- `slide-num` solo aparece en el PRIMER cover del board completo — los covers de topics siguientes no lo llevan (ver ejemplo "ICP Split Costa Rica" en el archivo real, sin `.slide-num`).
- Después de cada slide (incluido el cover) va un separador: `<div class="slide-divider">↓ &nbsp; N / M</div>` donde N = posición dentro del topic, M = total de slides del topic. Si el topic tiene una sola sección de contenido después del cover, usar `<div class="slide-divider">↓</div>` sin contador (ver ejemplo Costa Rica cover→imagen).

---

## 1. Numbered insights list — para 3-5 hallazgos/aprendizajes con texto

Úsalo cuando el contenido es una lista de insights cualitativos (research de campo, aprendizajes de una sesión, feedback de clientes).

```html
<div class="dt-slide">
  <div class="slide-header">
    <span class="title">{{TITULO_SLIDE}}</span>
    <span class="period">{{FUENTE}} · {{ config.month_label }}</span>
  </div>
  <div class="dt-body">
    <div class="dt-subtitle">{{SUBTITULO_CONTEXTO}}</div>
    <div class="insights-list">
      <div class="insight-row">
        <div class="insight-num">1</div>
        <div class="insight-content">
          <div class="insight-title">{{TITULO_INSIGHT}}</div>
          <div class="insight-desc">{{DESCRIPCION_INSIGHT}}</div>
          <div class="insight-hl">{{TAKEAWAY_ACCIONABLE}}</div>
        </div>
      </div>
      <!-- repetir .insight-row, cambiando insight-num, máximo 4-5 filas o no caben en el slide -->
    </div>
  </div>
</div>
```

**Gotcha:** `.insight-row` usa `flex: 1` — si pones más de 4-5 filas, el texto se aplasta o se corta (overflow oculto por `.dt-body { overflow: hidden }`). Con 4 filas de 2-3 líneas cada una ya se llena el slide. Si sobra contenido, es una señal de que necesitas 2 slides, no 1 con letra más chica.

---

## 2. Two-column: bullets + visual — para "qué está cambiando" con mockup/imagen de apoyo

Úsalo cuando el contenido son 3-4 cambios/decisiones con una pieza visual de apoyo (mockup de producto, captura, diagrama).

```html
<div class="dt-slide">
  <div class="slide-header">
    <span class="title">{{TITULO_SLIDE}}</span>
    <span class="period">{{ config.month_label }}</span>
  </div>
  <div class="dt-body">
    <div class="dt-subtitle">{{SUBTITULO_CONTEXTO}}</div>
    <div class="pricing-cols">
      <div class="left-col">
        <div class="col-label">{{ETIQUETA_LISTA}}</div>
        <div class="moves-list">
          <div class="move-item">
            <div class="move-num">1</div>
            <div class="move-text">
              <div class="move-title">{{TITULO_CAMBIO}}</div>
              <div class="move-desc">{{DESCRIPCION_CAMBIO}} — <span class="accent">{{DATO_DESTACADO}}</span>.</div>
            </div>
          </div>
          <!-- repetir .move-item, máximo 4 -->
        </div>
        <div class="bottom-boxes">
          <div class="info-box neutral">
            <div class="box-label">↔ {{ETIQUETA_NO_CAMBIA}}</div>
            <div class="box-title">{{TITULO_CORTO}}</div>
            <div class="box-desc">{{DESCRIPCION_CORTA}}</div>
          </div>
          <div class="info-box accent">
            <div class="box-label">🔓 {{ETIQUETA_POR_QUE}}</div>
            <div class="box-desc">{{JUSTIFICACION}}</div>
          </div>
        </div>
      </div>
      <div class="right-col">
        <!-- Opción A: imagen simple. OJO: .icp-img-stage/.icp-chip-row/.icp-chip están definidas
             en el CSS (líneas 254-268) pero HOY no se usan en ninguna slide real del archivo —
             nadie las probó dentro de .right-col. Si las usas, revisa el resultado en el navegador
             antes de darlo por bueno; no asumas que "compila con el CSS" = "se ve bien aquí". -->
        <div class="icp-img-stage" style="flex:1;">
          <img src="{{RUTA_IMAGEN_BASE64}}" alt="{{ALT_TEXT}}">
        </div>
        <!-- Opción B (preferida, sí está probada en producción): copiar el bloque .browser-wrap
             completo de 2_discussion_topic.j2 líneas 430-481 y reemplazar textos -->
      </div>
    </div>
  </div>
</div>
```

`.bottom-boxes` es opcional — solo úsalo si de verdad hay un "qué NO cambia" y un "por qué ahora" que valga la pena aclarar. Si no aplica, `.left-col` puede terminar directo después de `.moves-list`.

---

## 3. Full-bleed image — para una sola imagen/diagrama que necesita todo el slide

```html
<div class="dt-slide" style="padding:0;">
  <img src="{{RUTA_IMAGEN_BASE64}}" alt="{{ALT_TEXT}}" style="width:100%;height:100%;object-fit:cover;display:block;">
</div>
```

Sin `.slide-header` ni `.dt-body` — la imagen ocupa el slide completo. Úsalo solo cuando la imagen ya tiene su propio título/contexto incrustado (ej. un screenshot de un dashboard con su propio header).

**Nota importante:** el slide real de mayo-26 que usa este patrón (Costa Rica ICP) hoy tiene `src="../data/assets/2026-05/image-2.png"` — una ruta relativa, exactamente el antipatrón que la Regla de oro #4 del SKILL.md prohíbe. Es contenido viejo, de antes de que existiera esta skill; el pipeline (`phase3_html_builder.py::_reembed_cr_image`) lo re-embebe automáticamente en base64 al generar el standalone (corregido 2026-07-06 para no depender de un nombre de archivo fijo), pero **no confíes en esa automatización al escribir un topic nuevo** — pon el `{{RUTA_IMAGEN_BASE64}}` directo en el `src` desde que escribes el HTML, como dice la regla de oro. La automatización es una red de seguridad para contenido viejo, no el mecanismo recomendado para contenido nuevo.

---

## 4. Chart + comparison tables — para mostrar un resultado con evolución en el tiempo

Úsalo cuando hay una métrica que mejoró/cambió y quieres mostrar tanto la tendencia (chart) como el detalle por etapa (tabla).

```html
<div class="dt-slide">
  <div class="slide-header">
    <span class="title">{{TITULO_RESULTADO}}</span>
    <span class="period">{{ config.month_label }}</span>
  </div>
  <div class="dt-body" style="gap:6px;">
    <div class="dt-subtitle">{{RESUMEN_UNA_LINEA_CON_EL_NUMERO_CLAVE}}</div>
    <div class="cr-body">
      <div class="cr-chart">
        <div class="chart-label">{{TITULO_CHART}} <span>({{UNIDAD}})</span></div>
        <!-- El SVG de líneas es a mano (ver líneas 525-552 del .j2) — para un topic nuevo,
             evaluar si conviene generar el SVG con un script en vez de escribir puntos a mano.
             Si el dato es simple, considera una tabla sola (sin chart) usando solo cr-funnel. -->
        <div class="chart-note">{{NOTA_AL_PIE_DEL_CHART}}</div>
      </div>
      <div class="cr-funnel">
        <div class="ft-block">
          <div class="ft-cap">{{TITULO_TABLA}}</div>
          <table class="cr-ft">
            <thead><tr><th>{{COL1}}</th><th>{{COL2}}</th><th>{{COL3}}</th><th>{{COL4}}</th></tr></thead>
            <tbody>
              <tr><td>{{FILA}}</td><td>{{VAL1}}</td><td class="post">{{VAL2}}</td><td class="pos">{{DELTA}}</td></tr>
              <!-- clase "pos" = verde/mejora, "neg" = gris/deterioro (NO usar rojo aquí, ver gotcha) -->
              <tr class="total"><td>{{FILA_TOTAL}}</td><td>{{VAL1}}</td><td>{{VAL2}}</td><td class="pos">{{DELTA}}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</div>
```

**Gotcha de color:** en esta tabla `.neg` es gris (`var(--color-text-secondary)`), no rojo — es un patrón deliberadamente neutro porque "Discussion Topic" es contenido narrativo/estratégico, no una métrica de negocio con semáforo rojo/verde estricto como el Validator (R13-15 de `phase4_validator.py`). No copiar la lógica de colores de deltas del board financiero a este template.

**El SVG a mano no es reusable fácil** — si el topic nuevo necesita un chart de línea, lo más simple es: (a) usar solo la tabla (`cr-funnel` sin `cr-chart`, cambiando `flex: 0 0 56%` del contenedor padre), o (b) pedirle a Claude que genere las coordenadas del `<polyline>` a partir de una serie de números reales (viewBox fijo `0 0 620 300`, eje Y invertido — y=275 es el piso).

---

## Checklist antes de agregar un topic nuevo

1. ¿El contenido encaja en uno de estos 4 layouts de contenido (insights / two-col / imagen / chart+tabla)? Si no, avisar al usuario antes de improvisar CSS nueva — ver SKILL.md regla de oro #6.
2. ¿Cuántas slides de contenido tiene el topic? (1, 2 o 3 — define los contadores `N / M` del `slide-divider`).
3. ¿Hay imágenes nuevas? → deben ir embebidas en base64 directamente en el `src`, NO como referencia a archivo (ver SKILL.md regla de oro #4 — la automatización de re-embed solo cubre `cr-landing-icp.png`).
4. ¿El topic se agrega al final de los topics existentes del mes, o reemplaza uno de un mes anterior? Casi siempre es "agregar al final" — nunca borrar contenido de otro topic sin confirmar con el usuario.
