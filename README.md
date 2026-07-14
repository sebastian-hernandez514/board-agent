# Board Agent

Sistema que automatiza la generación del board ejecutivo mensual de Alegra: calcula los números (ARR, MRR, Churn, Headcount, NPS, Payback) desde Metabase, arma el HTML del board, y valida que todo cuadre matemáticamente antes de publicarlo.

Self-contained desde 2026-07-10 (sin dependencia de ninguna carpeta hermana) y sin ningún acceso a Redshift/AWS (todo dato viene de Metabase vía su MCP con OAuth, corrido por Claude Code — ningún agente/skill de este repo tiene ni necesita credenciales embebidas). Ver `CLAUDE.md` y `board_agent/metabase_fetch_spec.py`.

**¿Primera vez acá?** Si no eres del equipo técnico, empieza por el **[Playbook del Board](https://wiki.alegra.com/doc/playbook-del-board-como-colaborar-sin-depender-de-sebastian-6s5Xu0UKD4)** en la wiki de Alegra — explica qué es esto, cómo pedir acceso, el RACI de quién entrega qué, y cómo proponer un cambio sin saber programar.

**¿Vas a correr el pipeline tú mismo por primera vez?** Lee **[`docs/ONBOARDING.md`](docs/ONBOARDING.md)** antes de tocar nada — tiene el checklist de prerrequisitos y el comando de diagnóstico (`check_setup.py`) que hay que correr primero.

**¿No sabes por dónde empezar?** No hace falta saber el nombre de ninguna skill — dile a Claude Code algo tan simple como *"quiero hacer un cambio al board"* o *"ayúdame con esto"* y la skill `board-assistant` te ofrece un menú simple (construir un board nuevo, actualizar uno existente, agregar/corregir contenido, o verificar un dato).

**¿No usas Claude Code?** Este repo también funciona con Cursor, Codex, OpenCode (con DeepSeek u otro modelo), o cualquier herramienta que lea `AGENTS.md` — es el mismo contenido que las skills, en el formato abierto que la mayoría de estas herramientas cargan automáticamente. El pipeline en sí (`run.py` y los scripts de `board_agent/`) es Python plano, sin ninguna dependencia de una IA en particular.

## Qué hay en este repo

| Carpeta/archivo | Qué es |
|---|---|
| `board_agent/` | El código de las 6 fases del pipeline (freshness check, cálculo de métricas, armado de HTML, validador de reglas de negocio, diff contra el mes anterior, PDF) |
| `skills/board-assistant/` | Punto de entrada guiado (menú) — úsalo si no sabes qué skill invocar |
| `skills/edit-slide-content/` | Editor general de contenido — comentarios/títulos/slides nuevas en CUALQUIER slide del board, no solo las 3 de abajo |
| `skills/verify-data-point/` | Verifica un número del board reconstruyéndolo independiente desde Metabase |
| `skills/discussion-topic/` | Skill de self-service para agregar una slide de "Discussion Topic" al board sin depender de Sebastián |
| `skills/ceo-highlights/` | Skill de self-service para editar Highlights/Lowlights/Financial Update del CEO |
| `skills/slide-comments/` | Skill de self-service para agregar un comentario/ask a las slides ARR Core/Lite |
| `preview.py` | Vista previa (screenshot) de una slide ya generada — solo lee `output/*.html` |
| `board_agent/metabase_fetch_spec.py` | Qué query MBQL corresponde a cada dato (tabla de Metabase, estado de migración) — leer antes de poblar `data/.metabase_cache.json` |
| `docs/AGENT_ARCHITECTURE.md` | Arquitectura técnica completa: las 6 fases, las 19 reglas del Validator, y qué falta por automatizar |
| `docs/BOARD_PLAYBOOK_DRAFT.md` | Borrador del Playbook (la versión publicada vive en la wiki, enlace arriba) |
| `docs/ONBOARDING.md` | Checklist de prerrequisitos para alguien nuevo — leer antes de correr el pipeline por primera vez |
| `check_setup.py` | Diagnóstico de arranque (solo lectura) — corre esto antes que `run.py` |
| `run.py` | Punto de entrada — corre el pipeline completo |
| `tests/` | Tests automatizados |

## Cómo correrlo

```bash
cd "Board Agent"

# 0) Con Claude Code: poblar data/.metabase_cache.json vía el MCP de Metabase
#    (ver board_agent/metabase_fetch_spec.py para qué correr)

# Chequeo de arranque (solo lectura, no ejecuta nada)
uv run --with pyyaml python check_setup.py --month 2026-05

# Pipeline completo para un mes
uv run --with pyyaml python run.py --month 2026-05

# Solo validar un board ya generado
uv run --with pyyaml python run.py --validate-only --month 2026-05

# Correr los tests
uv run --with pyyaml --with pytest --with jinja2 python -m pytest tests/ -v

# Vista previa (screenshot) de una slide ya generada — después de usar una skill de self-service
uv run --with playwright python preview.py --template 3_arr_walk --slide "ARR Core"
```

No requiere AWS CLI, sesión SSO ni ninguna credencial de Redshift — el único acceso a datos es el MCP de Metabase, ya autenticado por OAuth en la sesión de Claude Code que puebla el cache.

## Self-contained, cero Redshift

Todo el pipeline (templates, scripts, datos, CSVs) vive dentro de este mismo repo desde 2026-07-10 — ya no depende de una carpeta hermana (`Template Board/`) ni de ningún acceso directo a Redshift/AWS. Ver `CLAUDE.md` y `docs/AGENT_ARCHITECTURE.md` para el detalle completo, y `memory/project_board_agent.md` para el historial de la migración.

## ¿Dudas?

Si tienes Claude Code con acceso a este repo, pregúntale directamente — tiene el contexto completo en `CLAUDE.md` y `docs/AGENT_ARCHITECTURE.md`. Si no, revisa el Playbook o escríbele a Sebastián Hernández.
