# AGENTS.md — Board Agent

Instrucciones para **cualquier agente de IA** (Claude Code, Cursor, Codex, OpenCode con
cualquier modelo — DeepSeek, GPT, etc.) que trabaje en este repo. `AGENTS.md` es el estándar
abierto que la mayoría de estas herramientas leen automáticamente al operar en una carpeta. Si
la tuya no lo hace, léelo de todos modos antes de tocar nada — las reglas de seguridad de este
repo valen sin importar qué IA lo esté operando. El equipo de datos usa Claude Code para tareas
pesadas, pero la mayoría del resto del equipo corre otras herramientas (OpenCode+DeepSeek,
etc.) — este repo tiene que funcionar igual de bien con cualquiera de las dos.

**Importante para herramientas que no sean Claude Code:** desde 2026-07-10 el único acceso a
datos de este pipeline es el MCP de Metabase (OAuth), que hoy solo Claude Code puede invocar.
Si tu herramienta no tiene ese MCP conectado, no podés poblar `data/.metabase_cache.json` ni
correr Fase 1/2 del pipeline (`fetch_metrics.py`) — sí podés hacer todo lo demás (editar YAMLs
editoriales, revisar/generar HTML con `generate.py` si el cache ya está poblado, usar
`preview.py`). Nunca uses una API key de Metabase ni credenciales de Redshift para sortear esto
— es una regla de arquitectura, no una limitación técnica a rodear.

## Qué es esto

Board Agent automatiza la generación del board ejecutivo mensual de Alegra: calcula los
números (ARR, MRR, Churn, Headcount, NPS, Payback) desde Metabase, arma el HTML del board, y
valida que todo cuadre matemáticamente (19 reglas) antes de publicarlo. Todo el pipeline
(templates, scripts, datos, CSVs) vive dentro de este mismo repo — no depende de ninguna
carpeta hermana ni de Redshift/AWS.

## Primera interacción — si el pedido es vago, ofrecer este menú

Si quien escribe no dice qué necesita ("quiero editar el board", "ayúdame con esto", "no sé
por dónde empezar"), o es evidentemente su primera vez sin un pedido concreto — preguntá:

```
¿Qué quieres hacer con el Board?

1. Construir el board de un mes nuevo (desde cero, con datos frescos de Metabase)
2. Actualizar o revisar el board del mes actual (ya generado, quieres verlo o corregirlo)
3. Agregar o corregir contenido — un comentario, un título, o una slide nueva
4. Verificar un dato que no te cuadra (un número que parece raro)
```

No asumas — el equipo que usa este repo va desde muy técnico hasta cero técnico, y no todos
saben pedir las cosas "en el lenguaje correcto". Si el pedido ya es específico, saltate el menú
y anda directo al procedimiento correspondiente.

**Cómo derivar cada opción:**

| Opción | Qué hacer |
|---|---|
| 1. Board de un mes nuevo | Si sos Claude Code: poblar `data/.metabase_cache.json` para el mes objetivo (ver `board_agent/metabase_fetch_spec.py`, corriendo cada query vía el MCP de Metabase). Si no tenés ese MCP: avisar que este paso requiere una sesión de Claude Code. Preguntar el mes (`YYYY-MM`). Correr `uv run --with pyyaml python run.py --month YYYY-MM --refresh`. Si Fase 0/1 bloquean (FAIL), explicar qué falta y quién lo provee — no forzar. |
| 2. Actualizar/revisar el actual | Solo ver: `run.py --validate-only --month YYYY-MM`. Regenerar con lo que ya existe: `run.py` normal. Ver una slide puntual ya generada: `preview.py`. |
| 3. Agregar/corregir contenido | Ver "Editar el contenido de una slide" abajo. |
| 4. Verificar un dato | Ver "Verificar un dato" abajo. |

## Editar el contenido de una slide (comentario, título, o slide nueva)

1. **Localizar la slide:** `grep -n "SLIDE.*<palabra clave>" templates/*.j2` — los comentarios HTML (`<!-- SLIDE N — ... -->`) son el ancla.
2. **Clasificar:** si es CEO Highlights/Lowlights, ARR Core/Lite (comentarios), o Discussion Topics, ya existe un mecanismo hecho — ver el detalle completo en `skills/ceo-highlights/`, `skills/slide-comments/`, `skills/discussion-topic/` (son markdown simple, abrilos aunque tu herramienta no tenga el concepto de "skill").
3. **Si es cualquier otra slide (caso nuevo):** leer el procedimiento completo en `skills/edit-slide-content/SKILL.md` — resume: nunca editar `output/*.html` a mano, decidir si el texto va en un YAML editorial nuevo, reusar el patrón visual ya existente (no inventar CSS), avisar explícitamente antes de escribir en un `.j2`, y confirmar visualmente (Playwright/`preview.py`) antes de dar el cambio por terminado.

## Verificar un dato que no cuadra

Procedimiento completo en `skills/verify-data-point/SKILL.md` — resume: nunca confiar solo en
`metrics.yaml`, reconstruir el número independiente desde Metabase (vía MBQL, el MCP de
Metabase — solo Claude Code puede hacer este paso) aplicando las reglas de negocio
documentadas en el SQL canónico de `scripts/fetch_metrics.py` (FX por país, buckets del ARR
Walk), y si el número de referencia de la persona no coincide, investigar SU fuente antes de
asumir que Board Agent está mal.

## Reglas de oro (aplican siempre, sin importar la herramienta que las ejecute)

1. **El único acceso a datos es el MCP de Metabase (OAuth)** — nunca Redshift, nunca una API
   key embebida en ningún archivo de este repo. Si necesitás un dato y no tenés ese MCP
   disponible, avisar que hace falta una sesión de Claude Code, no buscar un atajo.
2. **Nunca editar `output/*.html` a mano** — se pierde en la próxima regeneración (y F0.12
   además lo detecta y bloquea el flujo si pasa). Todo cambio pasa por `generate.py` (vía
   `run.py` o directo).
3. **Avisar explícitamente antes de escribir en un `.j2`** — el diseño de las slides no se
   toca a la ligera; nunca asumir luz verde.
4. **Confirmar visualmente antes de dar un cambio por terminado** — `preview.py` o Playwright
   directo, screenshot de la slide afectada y de una vecina.
5. **Comunicación en español.**

## Comandos

```bash
cd "Board Agent"

# 0) Con Claude Code: poblar data/.metabase_cache.json vía el MCP de Metabase
#    (ver board_agent/metabase_fetch_spec.py para qué correr)

# Chequeo de arranque (solo lectura)
uv run --with pyyaml python check_setup.py --month 2026-05

# Pipeline completo para un mes
uv run --with pyyaml python run.py --month 2026-05

# Solo validar un board ya generado
uv run --with pyyaml python run.py --validate-only --month 2026-05

# Correr los tests
uv run --with pyyaml --with pytest --with jinja2 python -m pytest tests/ -v

# Vista previa (screenshot) de una slide ya generada
uv run --with playwright python preview.py --template 3_arr_walk --slide "ARR Core"
```

## Más contexto

- `CLAUDE.md` — instrucciones específicas de Claude Code (mismo contenido base que este
  archivo, en su convención propia).
- `board_agent/metabase_fetch_spec.py` — qué query MBQL corresponde a cada dato del pipeline.
- `docs/AGENT_ARCHITECTURE.md` — arquitectura técnica completa: las 6 fases, las 19 reglas del
  Validator, deuda técnica priorizada.
- `README.md` — punto de entrada para humanos.
