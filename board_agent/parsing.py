"""Parsers de los valores pre-formateados que fetch_metrics.py escribe en metrics.yaml.

Todas las reglas del Validator dependen de estas dos funciones, así que se
prueban contra fixtures reales (ver tests/test_parsing.py), no solo casos
inventados.
"""


def parse_cell(raw) -> float:
    """Parsea un valor literal respetando su escala explícita.

    '$29.2M' -> 29_200_000.0   '$611K' -> 611_000.0   '(0.9)' -> -0.9
    '5.2%'   -> 5.2            '26.5'  -> 26.5         '23.4k' -> 23_400.0
    '3,714'  -> 3714.0         '—' / '' -> ValueError
    """
    s = str(raw).strip()
    if not s or s in ("—", "-", "N/A"):
        raise ValueError(f"celda vacía o no numérica: {raw!r}")

    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]

    s = s.replace(",", "").replace("$", "").replace("%", "").strip()

    if s.endswith("M"):
        val = float(s[:-1]) * 1_000_000
    elif s.endswith(("K", "k")):
        val = float(s[:-1]) * 1_000
    else:
        val = float(s)

    return -val if negative else val


def parse_money_cell(raw) -> float:
    """Como parse_cell, pero para celdas donde un número SIN sufijo representa
    dólares en millones (el caso de las filas de arr_walk_table: 'ARR BoP',
    'Additions', 'Net Churn', etc. — ej. '26.5' significa $26.5M, no $26.5).
    """
    s = str(raw).strip().strip("()")
    has_explicit_suffix = s.endswith(("M", "K", "k"))
    val = parse_cell(raw)
    if not has_explicit_suffix:
        val *= 1_000_000
    return val


def find_row(rows: list[dict], label: str) -> list:
    """Busca una fila por 'label' exacto en una lista de rows de arr_walk_table.sections[i]['rows'].
    Lanza KeyError con las labels disponibles si no la encuentra — mejor fallar
    ruidoso que devolver silenciosamente una fila equivocada.
    """
    for row in rows:
        if row.get("label") == label:
            return row["cells"]
    available = [r.get("label") for r in rows]
    raise KeyError(f"fila '{label}' no encontrada. Disponibles: {available}")


def last(cells: list):
    return cells[-1]
