# Board Agent

Sistema que automatiza la generación del board ejecutivo mensual de Alegra: calcula los números (ARR, MRR, Churn, Headcount, NPS, Payback) desde Redshift, arma el HTML del board, y valida que todo cuadre matemáticamente antes de publicarlo.

**¿Primera vez acá?** Si no eres del equipo técnico, empieza por el **[Playbook del Board](https://wiki.alegra.com/doc/playbook-del-board-como-colaborar-sin-depender-de-sebastian-6s5Xu0UKD4)** en la wiki de Alegra — explica qué es esto, cómo pedir acceso, el RACI de quién entrega qué, y cómo proponer un cambio sin saber programar.

**¿Vas a correr el pipeline tú mismo por primera vez?** Lee **[`docs/ONBOARDING.md`](docs/ONBOARDING.md)** antes de tocar nada — tiene el checklist de prerrequisitos y el comando de diagnóstico (`check_setup.py`) que hay que correr primero.

## Qué hay en este repo

| Carpeta/archivo | Qué es |
|---|---|
| `board_agent/` | El código de las 6 fases del pipeline (freshness check, cálculo de métricas, armado de HTML, validador de reglas de negocio, diff contra el mes anterior, PDF) |
| `skills/discussion-topic/` | Skill de self-service para agregar una slide de "Discussion Topic" al board sin depender de Sebastián |
| `skills/ceo-highlights/` | Skill de self-service para editar Highlights/Lowlights/Financial Update del CEO |
| `skills/slide-comments/` | Skill de self-service para agregar un comentario/ask a las slides ARR Core/Lite |
| `preview.py` | Vista previa (screenshot) de una slide ya generada, sin tocar Template Board — solo lee `output/*.html` |
| `docs/AGENT_ARCHITECTURE.md` | Arquitectura técnica completa: las 6 fases, las 18 reglas del Validator, y qué falta por automatizar |
| `docs/BOARD_PLAYBOOK_DRAFT.md` | Borrador del Playbook (la versión publicada vive en la wiki, enlace arriba) |
| `docs/ONBOARDING.md` | Checklist de prerrequisitos para alguien nuevo — leer antes de correr el pipeline por primera vez |
| `check_setup.py` | Diagnóstico de arranque (solo lectura) — corre esto antes que `run.py` |
| `run.py` | Punto de entrada — corre el pipeline completo |
| `tests/` | 160 tests automatizados |

## Cómo correrlo

```bash
cd "Board Agent"

# Pipeline completo para un mes
uv run --with boto3 --with pyyaml python run.py --month 2026-05

# Solo validar un board ya generado
uv run --with pyyaml python run.py --validate-only --month 2026-05

# Correr los tests
uv run --with pyyaml --with pytest --with jinja2 --with boto3 python -m pytest tests/ -v

# Vista previa (screenshot) de una slide ya generada — después de usar una skill de self-service
uv run --with playwright python preview.py --template 3_arr_walk --slide "ARR Core"
```

Requiere sesión activa de AWS SSO (perfil `alegra`) para tocar Redshift — sin eso, Fase 1 y 2 fallan.

## Este repo NO modifica `../Template Board/`

Board Agent orquesta el pipeline existente de `Template Board/` llamándolo como subproceso (`fetch_metrics.py`, `generate.py`, `merge_standalone.py`) — nunca edita esos archivos directamente. Ver `CLAUDE.md` y `docs/AGENT_ARCHITECTURE.md` para el detalle completo.

## ¿Dudas?

Si tienes Claude Code con acceso a este repo, pregúntale directamente — tiene el contexto completo en `CLAUDE.md` y `docs/AGENT_ARCHITECTURE.md`. Si no, revisa el Playbook o escríbele a Sebastián Hernández.
