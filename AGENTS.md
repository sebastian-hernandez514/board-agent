# AGENTS.md — Board Agent

Instrucciones para **cualquier agente de IA** (Claude Code, Cursor, Codex, OpenCode con
cualquier modelo — DeepSeek, GPT, etc.) que trabaje en este repo. `AGENTS.md` es el estándar
abierto que la mayoría de estas herramientas leen automáticamente al operar en una carpeta. Si
la tuya no lo hace, léelo de todos modos antes de tocar nada — las reglas de seguridad de este
repo valen sin importar qué IA lo esté operando. El equipo de datos usa Claude Code para tareas
pesadas, pero la mayoría del resto del equipo corre otras herramientas (OpenCode+DeepSeek,
etc.) — este repo tiene que funcionar igual de bien con cualquiera de las dos.

## Qué es esto

Board Agent automatiza la generación del board ejecutivo mensual de Alegra: calcula los
números (ARR, MRR, Churn, Headcount, NPS, Payback) desde Redshift, arma el HTML del board, y
valida que todo cuadre matemáticamente (19 reglas) antes de publicarlo. Es un orquestador que
envuelve el pipeline existente de `../Template Board/` — nunca lo modifica directamente, salvo
excepciones puntuales y siempre avisadas (ver Reglas de oro).

## Primera interacción — si el pedido es vago, ofrecer este menú

Si quien escribe no dice qué necesita ("quiero editar el board", "ayúdame con esto", "no sé
por dónde empezar"), o es evidentemente su primera vez sin un pedido concreto — preguntá:

```
¿Qué quieres hacer con el Board?

1. Construir el board de un mes nuevo (desde cero, con datos frescos de Redshift)
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
| 1. Board de un mes nuevo | Confirmar sesión de AWS SSO activa (`~/aws-cli-v2/aws-cli/aws sts get-caller-identity --profile alegra`; si expiró, `sso login` sin preguntar). Preguntar el mes (`YYYY-MM`). Correr `uv run --with boto3 --with pyyaml python run.py --month YYYY-MM --refresh`. Si Fase 0/1 bloquean (FAIL), explicar qué falta y quién lo provee — no forzar. |
| 2. Actualizar/revisar el actual | Solo ver: `run.py --validate-only --month YYYY-MM`. Regenerar con lo que ya existe: `run.py` normal. Ver una slide puntual ya generada: `preview.py`. |
| 3. Agregar/corregir contenido | Ver "Editar el contenido de una slide" abajo. |
| 4. Verificar un dato | Ver "Verificar un dato" abajo. |

## Editar el contenido de una slide (comentario, título, o slide nueva)

1. **Localizar la slide:** `grep -n "SLIDE.*<palabra clave>" Template\ Board/templates/*.j2` — los comentarios HTML (`<!-- SLIDE N — ... -->`) son el ancla.
2. **Clasificar:** si es CEO Highlights/Lowlights, ARR Core/Lite (comentarios), o Discussion Topics, ya existe un mecanismo hecho — ver el detalle completo en `skills/ceo-highlights/`, `skills/slide-comments/`, `skills/discussion-topic/` (son markdown simple, abrilos aunque tu herramienta no tenga el concepto de "skill").
3. **Si es cualquier otra slide (caso nuevo):** leer el procedimiento completo en `skills/edit-slide-content/SKILL.md` — resume: nunca editar `output/*.html` a mano, decidir si el texto va en un YAML editorial nuevo, reusar el patrón visual ya existente (no inventar CSS), avisar explícitamente antes de escribir en un `.j2`, y confirmar visualmente (Playwright/`preview.py`) antes de dar el cambio por terminado.

## Verificar un dato que no cuadra

Procedimiento completo en `skills/verify-data-point/SKILL.md` — resume: nunca confiar solo en
`metrics.yaml`, reconstruir el número independiente desde Redshift (vía `redshift_guard.py`)
aplicando las reglas de negocio documentadas en `Template Board/CLAUDE.md` (FX por país,
buckets del ARR Walk), y si el número de referencia de la persona no coincide, investigar SU
fuente antes de asumir que Board Agent está mal.

## Reglas de oro (aplican siempre, sin importar la herramienta que las ejecute)

1. **Este repo NO modifica `../Template Board/`** salvo excepciones puntuales ya avisadas
   (sentinels de mes, o construir el enganche de una slide nueva) — nunca asumir luz verde,
   preguntar cada vez.
2. **Nunca editar `output/*.html` a mano** — se pierde en la próxima regeneración. Todo cambio
   pasa por `generate.py` (vía `run.py` o directo).
3. **Siempre usar `redshift_guard.py`** para Redshift — nunca queries directas, nunca
   DROP/DELETE/TRUNCATE sin pasar por ahí.
4. **Confirmar visualmente antes de dar un cambio por terminado** — `preview.py` o Playwright
   directo, screenshot de la slide afectada y de una vecina.
5. **Comunicación en español.**

## Comandos

```bash
cd "Board Agent"

# Pipeline completo para un mes
uv run --with boto3 --with pyyaml python run.py --month 2026-05

# Solo validar un board ya generado
uv run --with pyyaml python run.py --validate-only --month 2026-05

# Correr los tests
uv run --with pyyaml --with pytest --with jinja2 --with boto3 python -m pytest tests/ -v

# Vista previa (screenshot) de una slide ya generada
uv run --with playwright python preview.py --template 3_arr_walk --slide "ARR Core"
```

## Más contexto

- `CLAUDE.md` — instrucciones específicas de Claude Code (mismo contenido base que este
  archivo, en su convención propia).
- `docs/AGENT_ARCHITECTURE.md` — arquitectura técnica completa: las 6 fases, las 19 reglas del
  Validator, deuda técnica priorizada.
- `README.md` — punto de entrada para humanos.
