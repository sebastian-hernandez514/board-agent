import subprocess

import pytest

from board_agent import paths, phase6_pdf as f6


class _FakeProc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def fake_pdf_script(tmp_path, monkeypatch):
    pdf_script = tmp_path / "generate_pdf.py"
    pdf_script.write_text(
        'HTML_FILE  = ROOT / "boards" / "2026-05" / "board_May_2026_v41.html"\n'
        'PDF_OUT    = ROOT / "boards" / "2026-05" / "board_May_2026_v41.pdf"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "PDF_SCRIPT", pdf_script)
    return pdf_script


def test_read_current_targets_parses_html_and_pdf(fake_pdf_script):
    targets = f6._read_current_targets()
    assert targets["HTML_FILE"] == "boards/2026-05/board_May_2026_v41.html"
    assert targets["PDF_OUT"] == "boards/2026-05/board_May_2026_v41.pdf"


def test_run_without_confirmed_is_readonly_skip(fake_pdf_script, monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    r = f6.run(confirmed=False)
    assert r.status == "SKIP"
    assert called["n"] == 0  # nunca debe ejecutar el subprocess sin --yes


def test_run_confirmed_success(fake_pdf_script, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(0, stdout="PDF generado"))
    r = f6.run(confirmed=True)
    assert r.status == "PASS"
    assert "board_May_2026_v41.pdf" in r.detail


def test_run_confirmed_failure(fake_pdf_script, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(1, stderr="playwright crash"))
    r = f6.run(confirmed=True)
    assert r.status == "FAIL"


def test_run_never_writes_to_pdf_script(fake_pdf_script, monkeypatch):
    """phase6_pdf.py es de solo LECTURA sobre generate_pdf.py — nunca debe reescribir
    HTML_FILE/PDF_OUT (eso es responsabilidad exclusiva de versioning.save_version())."""
    original = fake_pdf_script.read_text(encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(0))
    f6.run(confirmed=True)
    assert fake_pdf_script.read_text(encoding="utf-8") == original
