"""F0.12 — detecta ediciones manuales en output/*.html hechas después de la última generación.

Por qué existe: `Template Board/output/` está en `.gitignore` (confirmado 2026-07-10) — no hay
NINGÚN historial ahí. Si alguien edita un título o agrega un comentario directo en el HTML ya
generado (en vez de a través de una skill de self-service, que escribe en la capa correcta —
YAML editorial o el propio `.j2`), ese cambio se pierde sin dejar rastro en cuanto alguien
vuelve a correr `generate.py`, porque ese script reescribe `output/*.html` entero desde
templates + metrics.yaml + YAMLs editoriales. Reportado como "muy grave" por el usuario
2026-07-10 — este módulo lo convierte en un FAIL visible con backup automático, en vez de una
pérdida silenciosa.

Mecanismo: `record_generated_state()` guarda el hash de cada `output/*.html` al final de una
Fase 3 exitosa (después de generate.py + reembed de imágenes + overlays de contenido stale +
merge_standalone.py — es decir, el estado YA terminado de esa corrida, no a medio camino).
`check_for_manual_edits()` corre en Fase 0 de la SIGUIENTE corrida, antes de que nada toque
`output/`, y compara el hash actual contra el guardado. Si no coincide, alguien escribió ahí a
mano entre una corrida y la otra — hace backup del archivo y FAIL duro antes de dejar que se
sobrescriba.
"""

import hashlib
import json
import shutil
from datetime import datetime

from . import paths
from .report import CheckResult


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_state() -> dict:
    if not paths.HASH_STATE_FILE.exists():
        return {}
    return json.loads(paths.HASH_STATE_FILE.read_text(encoding="utf-8"))


def _save_state(state: dict) -> None:
    paths.HASH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    paths.HASH_STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _current_output_htmls() -> dict:
    if not paths.OUTPUT_DIR.exists():
        return {}
    return {
        f.name: f for f in paths.OUTPUT_DIR.iterdir()
        if f.is_file() and f.suffix == ".html"
    }


def check_for_manual_edits() -> CheckResult:
    """F0.12 — corre en Fase 0, antes de que Fase 2/3 toquen nada. Ver docstring del módulo."""
    label = "Sin ediciones manuales no sincronizadas en output/*.html"
    state = _load_state()

    if not state:
        return CheckResult("F0.12", label, "PASS",
                            "sin baseline todavía (primera corrida registrada de este repo) — "
                            "se registra al terminar esta corrida")

    current = _current_output_htmls()
    drifted = []
    missing = []
    for fname, recorded_hash in state.items():
        f = current.get(fname)
        if f is None:
            # Bug real corregido 2026-07-14: antes esto hacía `continue` — trataba un archivo
            # borrado como "no es una edición de contenido" y dejaba pasar PASS en silencio,
            # justo el caso (edición manual perdida) que este módulo existe para atrapar. Si
            # alguien editó el archivo a mano y LUEGO lo borró (o se borró por accidente), no
            # hay nada que respaldar, pero sigue siendo una discrepancia real que hay que FAIL.
            missing.append(fname)
            continue
        if _sha256(f) != recorded_hash:
            drifted.append(fname)

    if not drifted and not missing:
        return CheckResult("F0.12", label, "PASS",
                            f"{len(state)} archivo(s) verificados, sin cambios desde la última generación")

    backups = []
    if drifted:
        paths.MANUAL_EDITS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        for fname in sorted(drifted):
            src = current[fname]
            dst = paths.MANUAL_EDITS_BACKUP_DIR / f"{src.stem}.{ts}{src.suffix}"
            shutil.copy2(src, dst)
            backups.append(dst.name)

    parts = []
    if drifted:
        parts.append(f"{len(drifted)} archivo(s) editado(s) a mano después de la última generación: "
                      f"{sorted(drifted)} — backup guardado en output/.manual-edits-backup/ ({backups})")
    if missing:
        parts.append(f"{len(missing)} archivo(s) de la baseline desaparecieron sin dejar rastro "
                      f"(no hay nada que respaldar): {sorted(missing)}")

    return CheckResult("F0.12", label, "FAIL",
                        " · ".join(parts) +
                        " — mové ese contenido a la capa correcta (YAML editorial / skill de self-service) "
                        "antes de regenerar, o confirmá explícitamente que se puede perder borrando "
                        f"{paths.HASH_STATE_FILE.name} para resetear la baseline")


def record_generated_state() -> None:
    """Llamar SOLO al final de una Fase 3 exitosa (generate.py + post-procesos + merge OK) —
    guarda el hash de cada output/*.html como la nueva baseline 'buena conocida'. Si Fase 3
    falla a medio camino, NO se debe llamar — output/ puede quedar en un estado inconsistente
    y no queremos aprender esa mezcla como si fuera válida."""
    _save_state({name: _sha256(f) for name, f in _current_output_htmls().items()})
