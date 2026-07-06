import base64
import subprocess

import pytest

from board_agent import paths, phase3_html_builder as f3


class _FakeProc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    data_dir.mkdir()
    output_dir.mkdir()
    monkeypatch.setattr(paths, "DATA_DIR", data_dir)
    monkeypatch.setattr(paths, "OUTPUT_DIR", output_dir)
    return data_dir, output_dir


def test_reembed_cr_image_warn_when_image_missing(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    (output_dir / "2_discussion_topic.html").write_text("<html></html>")
    r = f3._reembed_cr_image("2026-05")
    assert r.status == "WARN"


def test_reembed_cr_image_fail_when_html_missing(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    img_dir = data_dir / "assets" / "2026-05"
    img_dir.mkdir(parents=True)
    (img_dir / "cr-landing-icp.png").write_bytes(b"\x89PNG fake")
    r = f3._reembed_cr_image("2026-05")
    assert r.status == "FAIL"


def test_reembed_cr_image_pass_embeds_base64(isolated_dirs):
    data_dir, output_dir = isolated_dirs
    img_dir = data_dir / "assets" / "2026-05"
    img_dir.mkdir(parents=True)
    img_bytes = b"\x89PNG fake bytes"
    (img_dir / "cr-landing-icp.png").write_bytes(img_bytes)
    html_path = output_dir / "2_discussion_topic.html"
    html_path.write_text('<img src="assets/2026-05/cr-landing-icp.png">', encoding="utf-8")

    r = f3._reembed_cr_image("2026-05")
    assert r.status == "PASS"
    new_html = html_path.read_text(encoding="utf-8")
    expected_b64 = base64.b64encode(img_bytes).decode()
    assert f'src="data:image/png;base64,{expected_b64}"' in new_html
    assert "cr-landing-icp.png" not in new_html


def test_run_stops_early_if_generate_fails(monkeypatch, isolated_dirs):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _FakeProc(1, stderr="boom"))
    results = f3.run("2026-05")
    assert len(results) == 1
    assert results[0].id == "F3.1"
    assert results[0].status == "FAIL"


def test_run_stops_before_merge_reembed_still_runs(monkeypatch, isolated_dirs):
    data_dir, output_dir = isolated_dirs
    (output_dir / "2_discussion_topic.html").write_text("<html></html>")  # sin imagen -> WARN

    calls = {"n": 0}

    def fake_run(cmd, **kw):
        calls["n"] += 1
        return _FakeProc(0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    results = f3.run("2026-05")
    ids = [r.id for r in results]
    assert ids == ["F3.1", "F3.2", "F3.3"]
    assert results[0].status == "PASS"
    assert results[1].status == "WARN"  # imagen no existe en este test
    assert results[2].status == "PASS"
    assert calls["n"] == 2  # generate.py + merge_standalone.py


def test_run_fails_on_merge_error(monkeypatch, isolated_dirs):
    data_dir, output_dir = isolated_dirs
    (output_dir / "2_discussion_topic.html").write_text("<html></html>")

    call_order = []

    def fake_run(cmd, **kw):
        script = str(cmd[cmd.index("python3") + 1])
        call_order.append(script)
        if "merge_standalone" in script:
            return _FakeProc(1, stderr="merge broke")
        return _FakeProc(0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    results = f3.run("2026-05")
    assert results[-1].id == "F3.3"
    assert results[-1].status == "FAIL"
