"""Path constants — Board Agent nunca escribe dentro de Template Board, solo lee o invoca como subproceso."""

from pathlib import Path

BOARD_AGENT_ROOT = Path(__file__).resolve().parent.parent
ALEGRA_IA_ROOT = BOARD_AGENT_ROOT.parent
TEMPLATE_BOARD = ALEGRA_IA_ROOT / "Template Board"

DATA_DIR = TEMPLATE_BOARD / "data"
METRICS_YAML = DATA_DIR / "metrics.yaml"
CONFIG_YAML = DATA_DIR / "config.yaml"
CHART_ALANUBE_YAML = DATA_DIR / "chart_alanube.yaml"
EDITORIAL_DIR = DATA_DIR / "editorial"
CEO_YAML = EDITORIAL_DIR / "ceo.yaml"
DISCUSSION_TOPICS_YAML = EDITORIAL_DIR / "discussion_topics.yaml"
ARR_WALK_YAML = EDITORIAL_DIR / "arr_walk.yaml"

CSV_DIR = TEMPLATE_BOARD / "csv"
PAISES_FX_CSV = CSV_DIR / "paises_fx.csv"
PAYBACK_CSV = CSV_DIR / "Payback.csv"
PNL_ACTUAL_CSV = CSV_DIR / "P&L Histórico- ACtual.csv"
METRICAS_BUDGET_CSV = CSV_DIR / "Metricas_budget.csv"

OUTPUT_DIR = TEMPLATE_BOARD / "output"
BOARD_STANDALONE_HTML = OUTPUT_DIR / "board_standalone.html"
BOARDS_DIR = TEMPLATE_BOARD / "boards"

SCRIPTS_DIR = TEMPLATE_BOARD / "scripts"
FETCH_SCRIPT = SCRIPTS_DIR / "fetch_metrics.py"
GENERATE_SCRIPT = SCRIPTS_DIR / "generate.py"
MERGE_SCRIPT = SCRIPTS_DIR / "merge_standalone.py"
PDF_SCRIPT = SCRIPTS_DIR / "generate_pdf.py"

# redshift_guard.py vive en la raíz de Alegra IA, no dentro de Template Board
REDSHIFT_GUARD_MODULE_DIR = ALEGRA_IA_ROOT

AWS_PROFILE = "alegra"

# Cluster 2 — donde vive casi todo lo que usa Template Board
# db_user: fetch_metrics.py usa "sebastian-hernandez" (sin -lcl) para todas sus queries de
# cluster-2 — Board Agent hace lo mismo para no competir por el pool de conexiones del
# usuario "-lcl" (se saturó el 2026-07-03, ver memory/project_board_agent.md).
RS_CLUSTER = "redshift-cluster-2"
RS_DATABASE = "data_table_bi"
RS_DB_USER = "sebastian-hernandez"

# Cluster 1 — solo dm_retention.bi_customer_monthly_status vive acá
RS_CLUSTER_1 = "data-redshift-cluster"
RS_DATABASE_1 = "bi_data_source"
RS_DB_USER_1 = "aws-data-user-master"

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
