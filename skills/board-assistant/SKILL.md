---
name: board-assistant
description: >
  Punto de entrada guiado para cualquiera que abra el repo de Board Agent sin saber por dónde
  empezar — desde muy técnico hasta cero técnico. Úsala cuando alguien pida algo vago ("quiero
  editar el board", "ayúdame con esto", "qué puedo hacer acá", "no sé por dónde arrancar") o
  cuando sea la primera interacción de la sesión en este repo sin un pedido específico ya
  claro. Presenta un menú simple en español y deriva al flujo correcto — no intentes adivinar
  qué quiere la persona, pregunta. Trigger phrases: "qué puedo hacer", "ayuda con el board",
  "empezar", "menu", "no sé por dónde empezar", "quiero hacer un cambio al board".
allowed-tools: Read, Bash, Glob, Grep
metadata:
  team: Board
  domain: board-agent
  kind: router
  status: stable
---

# Board Assistant — Punto de Entrada Guiado

## Propósito

Nace de un pedido explícito del equipo (workshop de colaboración, reunión de OKRs 2026-07):
el board debe ser colaborativo para gente que va **desde muy técnica hasta cero técnica**. No
todos van a saber pedir las cosas "en el lenguaje correcto" — esta skill existe para que no
tengan que saberlo. Es el "menú del videojuego": abrís el repo, corrés Claude Code, y en vez de
enfrentarte a una terminal vacía, te preguntan qué querés hacer.

## Auto-pilot

Si el pedido de la persona ya es específico y claro (ej. "agrega este highlight: ..."), **no
muestres el menú** — anda directo a la skill que corresponda. Este menú es solo para cuando el
pedido es vago o es la primera interacción.

Cuando aplique, preguntá (en este orden, en español simple):

```
¿Qué quieres hacer con el Board?

1. Construir el board de un mes nuevo (desde cero, con datos frescos de Metabase)
2. Actualizar o revisar el board del mes actual (ya generado, quieres verlo o corregirlo)
3. Agregar o corregir contenido — un comentario, un título, o una slide nueva
4. Verificar un dato que no te cuadra (un número que parece raro)
```

## Cómo derivar cada opción

### 1. Construir el board de un mes nuevo
Antes de correr `run.py`, poblar `data/.metabase_cache.json` para el mes objetivo: leer
`board_agent/metabase_fetch_spec.py` y correr cada query MBQL vía el MCP de Metabase
(`mcp__metabase__*`) — este pipeline ya no usa Redshift ni AWS SSO. Preguntar el mes (`YYYY-MM`). Correr:
```bash
cd "Board Agent"
uv run --with pyyaml python run.py --month YYYY-MM --refresh
```
Si Fase 0/1 bloquean (FAIL), explicar exactamente qué falta y quién lo provee (el reporte ya
lo dice) — no forzar el flujo sin que la persona entienda que los números pueden no ser
reales todavía.

### 2. Actualizar o revisar el board actual
Si solo quiere VER el estado: `uv run --with pyyaml python run.py --validate-only --month
YYYY-MM`. Si quiere regenerar con los datos/contenido que ya existen: correr `run.py` normal.
Si quiere ver una slide puntual ya generada: usar `preview.py` (ver su propia documentación).

### 3. Agregar o corregir contenido
Derivar a la skill **`edit-slide-content`** — es la que sabe manejar cualquier slide (ya sea
un caso ya resuelto como CEO Highlights/ARR Walk/Discussion Topics, o uno nuevo que necesita
construirse).

### 4. Verificar un dato
Derivar a la skill **`verify-data-point`**.

## Reglas de oro

1. **No asumas — preguntá.** Si no está claro qué slide, qué mes, o qué tipo de cambio, es
   mejor una pregunta de más que una edición equivocada.
2. **No muestres el menú si ya sabés qué hacer.** Es una guía para cuando hace falta, no un
   ritual obligatorio en cada mensaje.
3. **Recordar el límite de siempre:** los `.j2` de `templates/` son el diseño del board, no
   contenido editorial — si el pedido requiere tocar uno, avisar antes de hacerlo (ver
   `edit-slide-content`).

## Limitantes

- No reemplaza el criterio humano — para pedidos ambiguos, sigue siendo mejor preguntar que
  adivinar, aunque exista un menú.
- No cubre gestión de accesos (GitHub/Metabase) — eso es acción del equipo, no de esta skill.
