import subprocess

from board_agent import phase2_metrics as f2


class _FakeProc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_success(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _FakeProc(0, stdout="metrics.yaml escrito")
    monkeypatch.setattr(subprocess, "run", fake_run)

    r = f2.run("2026-05")
    assert r.status == "PASS"
    assert len(calls) == 1
    assert "--month" in calls[0] and "2026-05" in calls[0]
    assert "--refresh" not in calls[0]
    assert "boto3" not in calls[0]  # migración 2026-07-10: ya no habla con RS


def test_run_passes_refresh_flag(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _FakeProc(0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    f2.run("2026-05", refresh=True)
    assert "--refresh" in calls[0]


def test_run_fails_without_retry_when_cache_missing(monkeypatch):
    """Un RuntimeError propio de fetch_metrics.py (cache faltante/mes equivocado) es
    determinista — reintentar no cambia el resultado, así que falla en el primer intento."""
    attempts = {"n": 0}

    def fake_run(cmd, **kwargs):
        attempts["n"] += 1
        return _FakeProc(1, stderr="RuntimeError: No existe data/.metabase_cache.json")
    monkeypatch.setattr(subprocess, "run", fake_run)

    r = f2.run("2026-05")
    assert r.status == "FAIL"
    assert attempts["n"] == 1


def test_run_retries_on_non_runtime_error_failure(monkeypatch):
    """Bug corregido 2026-07-14: se había quitado TODO el retry, no solo el de RS. Una
    falla sin la firma de RuntimeError (ej. el propio `uv` no pudo resolver el paquete, o
    cualquier otro fallo del subproceso antes de que fetch_metrics.py llegue a correr)
    podría ser transitoria — debe reintentar, y si el segundo intento sí sale bien, PASS."""
    attempts = {"n": 0}

    def fake_run(cmd, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return _FakeProc(1, stderr="error: failed to fetch pyyaml (network blip)")
        return _FakeProc(0, stdout="metrics.yaml escrito")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("board_agent.phase2_metrics.time.sleep", lambda s: None)

    r = f2.run("2026-05")
    assert r.status == "PASS"
    assert attempts["n"] == 2


def test_run_gives_up_after_retries_if_still_failing(monkeypatch):
    """Si ninguno de los intentos tiene la firma de RuntimeError pero tampoco se
    recupera, debe agotar los reintentos y FAIL — no reintentar para siempre."""
    attempts = {"n": 0}

    def fake_run(cmd, **kwargs):
        attempts["n"] += 1
        return _FakeProc(1, stderr="error: red caída")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("board_agent.phase2_metrics.time.sleep", lambda s: None)

    r = f2.run("2026-05")
    assert r.status == "FAIL"
    assert attempts["n"] == 1 + len(f2._RETRY_BACKOFF_S)
