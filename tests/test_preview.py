import sys
import types

import pytest

from board_agent import paths
import preview


class _FakeElement:
    def __init__(self, text):
        self._text = text
        self.screenshot_calls = []

    def inner_text(self):
        return self._text

    def screenshot(self, path):
        self.screenshot_calls.append(path)


class _FakePage:
    def __init__(self, elements):
        self._elements = elements
        self.goto_calls = []

    def goto(self, uri):
        self.goto_calls.append(uri)

    def query_selector_all(self, selector):
        assert selector == ".slide"
        return self._elements


class _FakeBrowser:
    def __init__(self, page):
        self._page = page
        self.closed = False

    def new_page(self, viewport=None):
        return self._page

    def close(self):
        self.closed = True


class _FakeChromium:
    def __init__(self, browser):
        self._browser = browser

    def launch(self):
        return self._browser


class _FakePlaywrightContext:
    def __init__(self, browser):
        self.chromium = _FakeChromium(browser)


class _FakeSyncPlaywright:
    def __init__(self, browser):
        self._browser = browser

    def __enter__(self):
        return _FakePlaywrightContext(self._browser)

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_playwright(monkeypatch):
    """Inyecta un módulo playwright.sync_api falso — playwright no es dependencia
    del proyecto (ver pyproject.toml), así que el import local dentro de
    screenshot_slide() debe resolverse contra este doble, no contra el paquete real."""
    page_holder = {}

    def _install(elements):
        page = _FakePage(elements)
        browser = _FakeBrowser(page)
        fake_module = types.ModuleType("playwright.sync_api")
        fake_module.sync_playwright = lambda: _FakeSyncPlaywright(browser)
        monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
        monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_module)
        page_holder["page"] = page
        page_holder["browser"] = browser
        return page

    return _install


@pytest.fixture
def fake_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "OUTPUT_DIR", tmp_path)
    return tmp_path


def test_find_matching_slides_case_insensitive():
    elements = [_FakeElement("ARR Core"), _FakeElement("New Logos"), _FakeElement("arr core detail")]
    fake_page = _FakePage(elements)
    matches = preview._find_matching_slides(fake_page, "arr core")
    assert len(matches) == 2


def test_screenshot_slide_missing_html_raises(fake_output_dir):
    with pytest.raises(FileNotFoundError, match="3_arr_walk"):
        preview.screenshot_slide("3_arr_walk", "ARR Core", fake_output_dir / "out.png")


def test_screenshot_slide_no_match_raises(fake_output_dir, fake_playwright):
    (fake_output_dir / "3_arr_walk.html").write_text("<html></html>", encoding="utf-8")
    fake_playwright([_FakeElement("New Logos")])
    with pytest.raises(ValueError, match="no se encontró"):
        preview.screenshot_slide("3_arr_walk", "ARR Core", fake_output_dir / "out.png")


def test_screenshot_slide_multiple_matches_raises(fake_output_dir, fake_playwright):
    (fake_output_dir / "3_arr_walk.html").write_text("<html></html>", encoding="utf-8")
    fake_playwright([_FakeElement("ARR Core"), _FakeElement("ARR Core detalle")])
    with pytest.raises(ValueError, match="2 slides"):
        preview.screenshot_slide("3_arr_walk", "ARR Core", fake_output_dir / "out.png")


def test_screenshot_slide_success_saves_png(fake_output_dir, fake_playwright, tmp_path):
    (fake_output_dir / "3_arr_walk.html").write_text("<html></html>", encoding="utf-8")
    matching = _FakeElement("ARR Core")
    page = fake_playwright([_FakeElement("ARR Lite"), matching])

    out_path = tmp_path / "previews" / "shot.png"
    result = preview.screenshot_slide("3_arr_walk", "ARR Core", out_path)

    assert result == out_path
    assert out_path.parent.exists()
    assert matching.screenshot_calls == [str(out_path)]
    assert page.goto_calls == [(fake_output_dir / "3_arr_walk.html").resolve().as_uri()]
