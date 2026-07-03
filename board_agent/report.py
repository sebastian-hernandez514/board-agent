"""Formato común de resultados para todas las fases (Gate, Freshness, Validator)."""

from dataclasses import dataclass

STATUS_ICON = {
    "PASS": "✅",
    "WARN": "⚠️",
    "FAIL": "❌",
    "SKIP": "⏭️",
}

# Orden de severidad para decidir el exit code del CLI
BLOCKING_STATUSES = {"FAIL"}


@dataclass
class CheckResult:
    id: str
    description: str
    status: str  # PASS | WARN | FAIL | SKIP
    detail: str = ""

    def line(self) -> str:
        icon = STATUS_ICON.get(self.status, "?")
        base = f"{icon} [{self.id}] {self.description}"
        return f"{base} — {self.detail}" if self.detail else base


def print_report(title: str, results: list[CheckResult]) -> bool:
    """Imprime el reporte de una fase. Devuelve True si NO hay ningún FAIL (bloqueante)."""
    print(f"\n=== {title} ===")
    if not results:
        print("(sin checks)")
        return True
    for r in results:
        print(r.line())
    n_fail = sum(1 for r in results if r.status == "FAIL")
    n_warn = sum(1 for r in results if r.status == "WARN")
    n_pass = sum(1 for r in results if r.status == "PASS")
    n_skip = sum(1 for r in results if r.status == "SKIP")
    print(f"--- {n_pass} PASS · {n_warn} WARN · {n_fail} FAIL · {n_skip} SKIP ---")
    return n_fail == 0
