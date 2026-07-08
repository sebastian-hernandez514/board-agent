# Board Agent — Instrucciones para Claude

## Punto de entrada — leer primero

Antes de cualquier tarea, leer: `docs/AGENT_ARCHITECTURE.md` — tiene el inventario completo de fuentes, las 6 fases, las 19 reglas del Validator, la deuda técnica priorizada y la visión final del sistema.

---

## Qué es esto

Sistema multi-agente para generar el board ejecutivo mensual de Alegra de forma automatizada y validada. Es el sucesor del pipeline manual en `../Template Board/`.

**Regla fundamental:** este directorio NO modifica nada en `../Template Board/`. Si necesita ejecutar scripts del pipeline existente, los llama como subprocesos.

## Relación con Template Board

```
Board Agent/          ← este directorio (nuevo agente)
Template Board/       ← pipeline existente (no tocar)
```

El agente orquesta el pipeline existente:
- Llama a `../Template Board/scripts/fetch_metrics.py` como subproceso
- Llama a `../Template Board/scripts/generate.py` como subproceso
- Llama a `../Template Board/scripts/merge_standalone.py` como subproceso
- Lee `../Template Board/data/metrics.yaml` para validar
- Lee `../Template Board/output/board_standalone.html` para validar y diff

## Arquitectura — 6 fases

Ver `docs/AGENT_ARCHITECTURE.md` para el diseño completo.

```
Fase 0 — Human Inputs Gate     (temporal, debe desaparecer)
Fase 1 — Data Freshness Check
Fase 2 — Metrics Computation   (llama a fetch_metrics.py)
Fase 3 — HTML Builder          (llama a generate.py + merge)
Fase 4 — Business Rules Validator
Fase 5 — Diff Review
Fase 6 — PDF Generation        (trigger manual)
```

## Paths clave

```python
TEMPLATE_BOARD  = Path(__file__).parent.parent / "Template Board"
METRICS_YAML    = TEMPLATE_BOARD / "data" / "metrics.yaml"
BOARD_HTML      = TEMPLATE_BOARD / "output" / "board_standalone.html"
BOARDS_DIR      = TEMPLATE_BOARD / "boards"
FETCH_SCRIPT    = TEMPLATE_BOARD / "scripts" / "fetch_metrics.py"
GENERATE_SCRIPT = TEMPLATE_BOARD / "scripts" / "generate.py"
MERGE_SCRIPT    = TEMPLATE_BOARD / "scripts" / "merge_standalone.py"
PDF_SCRIPT      = TEMPLATE_BOARD / "scripts" / "generate_pdf.py"
```

## Cómo correr

```bash
cd "/Users/sebastian_alegra/Alegra IA/Board Agent"

# Pipeline completo
uv run --with boto3 --with pyyaml python run.py --month 2026-05

# Solo validar un board ya generado
uv run --with pyyaml python run.py --validate-only --month 2026-05

# Solo diff vs board anterior
uv run --with pyyaml python run.py --diff-only --month 2026-05
```

## Preferencias
- Comunicación en español
- No modificar nada en `../Template Board/`
