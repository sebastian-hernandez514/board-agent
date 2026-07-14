"""Path constants — todo el pipeline (templates, scripts, data, csv) vive dentro de este repo
desde 2026-07-10 (absorbido de Template Board, ver memory/project_board_agent.md) — Board Agent
ya no depende de ninguna carpeta hermana en el disco de quien lo corre, ni de Redshift/AWS
(migración completa a Metabase vía MCP, mismo commit — cero credenciales, cero usuarios
personales de RS en este repo)."""

from pathlib import Path

BOARD_AGENT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = BOARD_AGENT_ROOT / "data"
METRICS_YAML = DATA_DIR / "metrics.yaml"
CONFIG_YAML = DATA_DIR / "config.yaml"
# Filas + freshness de Metabase que Claude Code escribe vía el MCP antes de correr el
# pipeline (migración 2026-07-10, ver board_agent/metabase_fetch_spec.py) — reemplaza
# el acceso directo a Redshift que tenían phase1_freshness.py y fetch_metrics.py.
METABASE_CACHE_FILE = DATA_DIR / ".metabase_cache.json"
EDITORIAL_DIR = DATA_DIR / "editorial"
CEO_YAML = EDITORIAL_DIR / "ceo.yaml"
DISCUSSION_TOPICS_YAML = EDITORIAL_DIR / "discussion_topics.yaml"
ARR_WALK_YAML = EDITORIAL_DIR / "arr_walk.yaml"
NPS_SNAPSHOT_YAML = DATA_DIR / "nps_snapshot.yaml"

TEMPLATES_DIR = BOARD_AGENT_ROOT / "templates"
FINANCIAL_PERFORMANCE_TEMPLATE = TEMPLATES_DIR / "4_financial_performance.j2"
DISCUSSION_TOPIC_TEMPLATE = TEMPLATES_DIR / "2_discussion_topic.j2"
HEADCOUNT_TEMPLATE = TEMPLATES_DIR / "7_headcount.j2"

# paises_fx.csv, chart_alanube.yaml y Payback.csv salieron de acá — fetch_metrics.py ahora
# los arma desde el cache de Metabase (ver phase0_gate.py y phase1_freshness.py).
CSV_DIR = BOARD_AGENT_ROOT / "csv"
PNL_ACTUAL_CSV = CSV_DIR / "P&L Histórico- ACtual.csv"
METRICAS_BUDGET_CSV = CSV_DIR / "Metricas_budget.csv"

OUTPUT_DIR = BOARD_AGENT_ROOT / "output"
BOARD_STANDALONE_HTML = OUTPUT_DIR / "board_standalone.html"
# boards/ arranca vacío a propósito — el historial de marzo-junio 2026 se queda en
# Template Board (167MB, nunca estuvo en git) y no se migra; desde acá en adelante
# cada corrida completa de Board Agent guarda su versión nueva en este árbol.
BOARDS_DIR = BOARD_AGENT_ROOT / "boards"

# output_integrity.py (F0.12) — detecta ediciones manuales en output/*.html hechas después de
# la última generación. El estado vive en Board Agent, no en Template Board, porque es Board
# Agent quien lo escribe.
HASH_STATE_FILE = BOARD_AGENT_ROOT / ".state" / "output_hashes.json"
MANUAL_EDITS_BACKUP_DIR = OUTPUT_DIR / ".manual-edits-backup"

SCRIPTS_DIR = BOARD_AGENT_ROOT / "scripts"
FETCH_SCRIPT = SCRIPTS_DIR / "fetch_metrics.py"
GENERATE_SCRIPT = SCRIPTS_DIR / "generate.py"
MERGE_SCRIPT = SCRIPTS_DIR / "merge_standalone.py"
PDF_SCRIPT = SCRIPTS_DIR / "generate_pdf.py"

# Selector real usado por generate_pdf.py para contar slides — confirmado: 47 elementos en board_May_2026_v37
SLIDE_CLASS_TOKENS = {"slide", "gtm-slide", "hc-slide", "board-slide", "dt-slide"}
EXPECTED_SLIDE_COUNT = 47
MIN_SLIDE_COUNT_WARNING = 40

# Abreviaturas de mes en inglés — mismo formato que usan los nombres de archivo ya
# existentes en boards/YYYY-MM/ (ej. "board_May_2026_v37.html").
MES_ABBR_EN = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}
