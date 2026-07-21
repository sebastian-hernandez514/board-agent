"""Guarda cada corrida completa del pipeline como una versión nueva en boards/YYYY-MM/ —
sin pisar nada, con el HTML + snapshot de metrics.yaml + reporte de Validator/Diff, y deja
generate_pdf.py apuntando a la versión recién creada.

Única excepción autorizada a "Board Agent nunca escribe dentro de Template Board" —
aprobada explícitamente por el usuario 2026-07-03 (ver memory/project_board_agent.md).
Se versiona en CADA corrida completa del flujo default, pase o no pase el Validator —
un board que falló la validación sigue siendo un checkpoint útil del historial.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path

from . import paths
from .report import CheckResult

_VERSION_RE = re.compile(r"_v(\d+)\.html$")
_TARGET_RE = re.compile(r'(HTML_FILE|PDF_OUT)\s*=\s*ROOT\s*/\s*"boards"\s*/\s*"([^"]+)"\s*/\s*"([^"]+)"')


def next_version_number(cutoff_month: str, boards_dir: Path = None) -> int:
    """cutoff_month en formato 'YYYY-MM'. Ordena por el número de versión real, no
    alfabéticamente ('v9' quedaría después de 'v41' si se comparara como texto)."""
    board_dir = (boards_dir or paths.BOARDS_DIR) / cutoff_month
    files = list(board_dir.glob("*_v*.html")) if board_dir.exists() else []
    numbers = [int(m.group(1)) for f in files if (m := _VERSION_RE.search(f.name))]
    return max(numbers, default=0) + 1


def latest_version_number(cutoff_month: str, boards_dir: Path = None) -> int:
    """Número de la versión más alta ya guardada para este mes (0 si no hay ninguna)."""
    return next_version_number(cutoff_month, boards_dir) - 1


def mark_final(cutoff_month: str, version: int = None, boards_dir: Path = None,
                historico_dir: Path = None) -> dict:
    """Copia una versión YA guardada de boards/YYYY-MM/ a boards/historico/ con nombre
    limpio (sin '_vN') — a pedido explícito del usuario 2026-07-21: el histórico entre
    meses debe guardar SOLO la versión marcada como final, no todas las de trabajo (esas
    siguen intactas en boards/YYYY-MM/, sin cambios). Re-marcar el mismo mes sobreescribe
    la entrada anterior — un mes tiene una sola entrada en el histórico, siempre.

    `version=None` usa la más reciente ya guardada. Lanza RuntimeError si no hay ninguna
    versión para ese mes, o si la versión pedida no existe en disco."""
    board_dir = (boards_dir or paths.BOARDS_DIR) / cutoff_month
    target_version = version or latest_version_number(cutoff_month, boards_dir)
    if target_version == 0:
        raise RuntimeError(f"No hay ninguna versión guardada para {cutoff_month} en {board_dir}")

    stem = _file_stem(cutoff_month, target_version)
    html_src = board_dir / f"{stem}.html"
    if not html_src.exists():
        raise RuntimeError(f"No existe {html_src} — ¿la versión {target_version} es correcta para {cutoff_month}?")
    metrics_src = board_dir / f"{stem}.metrics.yaml"
    report_src = board_dir / f"{stem}.report.md"

    y, m = cutoff_month.split("-")
    final_stem = f"board_{paths.MES_ABBR_EN[int(m)]}_{y}"

    hist_dir = historico_dir or paths.HISTORICO_DIR
    hist_dir.mkdir(parents=True, exist_ok=True)
    html_out = hist_dir / f"{final_stem}.html"
    metrics_out = hist_dir / f"{final_stem}.metrics.yaml"
    report_out = hist_dir / f"{final_stem}.report.md"

    shutil.copy2(html_src, html_out)
    if metrics_src.exists():
        shutil.copy2(metrics_src, metrics_out)
    if report_src.exists():
        shutil.copy2(report_src, report_out)

    return {"version": target_version, "html": html_out, "metrics": metrics_out, "report": report_out}


def _file_stem(cutoff_month: str, version: int) -> str:
    y, m = cutoff_month.split("-")
    mes = paths.MES_ABBR_EN[int(m)]
    return f"board_{mes}_{y}_v{version}"


def _update_pdf_script_targets(html_rel: str, pdf_rel: str, pdf_script: Path = None) -> None:
    """Reescribe HTML_FILE/PDF_OUT en generate_pdf.py con regex — mismo patrón que
    phase6_pdf.py ya usa en modo lectura, ahora también para escribir.

    Si _TARGET_RE no matchea nada (ej. alguien reformatea generate_pdf.py y cambia el estilo
    de comillas o el nombre de la variable ROOT), re.sub() no fallaba — escribía el archivo
    sin cambios y save_version() reportaba éxito igual, dejando generate_pdf.py apuntando en
    silencio a la versión vieja. Corregido 2026-07-06 (mismo patrón de falso-positivo-por-regex
    encontrado en phase3_html_builder._reembed_cr_image): ahora cuenta los reemplazos y explota
    si no fueron exactamente 2 (HTML_FILE + PDF_OUT), en vez de fallar en silencio."""
    script_path = pdf_script or paths.PDF_SCRIPT
    content = script_path.read_text(encoding="utf-8")

    def _repl(m):
        var = m.group(1)
        rel = html_rel if var == "HTML_FILE" else pdf_rel
        folder, fname = rel.split("/", 1)
        return f'{var} = ROOT / "boards" / "{folder}" / "{fname}"'

    new_content, n_subs = _TARGET_RE.subn(_repl, content)
    if n_subs != 2:
        raise RuntimeError(
            f"_update_pdf_script_targets: se esperaban 2 reemplazos (HTML_FILE, PDF_OUT) en "
            f"{script_path}, se hicieron {n_subs} — el patrón _TARGET_RE ya no matchea el "
            f"formato real del archivo, revisar antes de confiar en el PDF generado."
        )
    script_path.write_text(new_content, encoding="utf-8")


def save_version(cutoff_month: str, validator_results: list[CheckResult],
                  diff_results: list[CheckResult]) -> dict:
    """Guarda la corrida actual (output/board_standalone.html + metrics.yaml + reporte)
    como una versión nueva en boards/YYYY-MM/, y actualiza generate_pdf.py. Devuelve las
    rutas guardadas."""
    version = next_version_number(cutoff_month)
    stem = _file_stem(cutoff_month, version)
    board_dir = paths.BOARDS_DIR / cutoff_month
    board_dir.mkdir(parents=True, exist_ok=True)

    html_out = board_dir / f"{stem}.html"
    metrics_out = board_dir / f"{stem}.metrics.yaml"
    report_out = board_dir / f"{stem}.report.md"
    pdf_target = board_dir / f"{stem}.pdf"

    shutil.copy2(paths.BOARD_STANDALONE_HTML, html_out)
    shutil.copy2(paths.METRICS_YAML, metrics_out)

    lines = [
        f"# Board {cutoff_month} — v{version}",
        f"Generado: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Fase 4 — Business Rules Validator",
    ]
    lines += [r.line() for r in validator_results]
    lines += ["", "## Fase 5 — Diff Review"]
    lines += [r.line() for r in diff_results]
    report_out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _update_pdf_script_targets(f"{cutoff_month}/{html_out.name}", f"{cutoff_month}/{pdf_target.name}")

    return {
        "version": version,
        "html": html_out,
        "metrics": metrics_out,
        "report": report_out,
        "pdf_target": pdf_target,
    }
