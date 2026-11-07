"""Integration tests for the page snapshot and element references.

These launch a real headless Chromium but never touch the network: the page is
built with ``set_content``. The module is skipped when a Playwright browser is
not available (for example before ``playwright install chromium`` has run).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from playwright.async_api import Page, async_playwright

from browser.snapshot import element_for_ref, ref_metadata, take_snapshot

FORM_HTML = """
<!doctype html>
<html><head><title>Snapshot fixture</title></head>
<body>
  <h1>Sign in</h1>
  <label for="user">Username</label>
  <input id="user" type="text" placeholder="Your username">
  <label for="pw">Password</label>
  <input id="pw" type="password" value="sekret">
  <select id="colour"><option>Red</option><option>Blue</option></select>
  <button id="go" onclick="document.title='Clicked!'">Continue</button>
  <button id="danger" onclick="document.title='Deleted!'">Delete account</button>
  <a href="https://example.com/next">Next page</a>
  <div style="display:none"><button>Hidden</button></div>
</body></html>
"""


@pytest.fixture
async def page() -> AsyncIterator[Page]:
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
    except Exception as err:
        pytest.skip(f"playwright chromium is unavailable: {err}")

    context = await browser.new_context(viewport={"width": 1280, "height": 720})
    live_page = await context.new_page()
    await live_page.set_content(FORM_HTML)
    try:
        yield live_page
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()


def _by_role(snapshot: object) -> dict[str, str]:
    elements = snapshot.elements  # type: ignore[attr-defined]
    return {element["ref"]: element["role"] for element in elements}


async def test_snapshot_lists_interactive_elements(page: Page) -> None:
    snapshot = await take_snapshot(page)
    roles = _by_role(snapshot)

    assert snapshot.title == "Snapshot fixture"
    assert list(roles.values()).count("textbox") == 2
    assert "button" in roles.values()
    assert "combobox" in roles.values()
    assert "link" in roles.values()


async def test_hidden_elements_are_excluded(page: Page) -> None:
    snapshot = await take_snapshot(page)
    names = [element["name"] for element in snapshot.elements]
    assert "Hidden" not in names


async def test_password_value_is_redacted(page: Page) -> None:
    snapshot = await take_snapshot(page)
    password = next(
        element for element in snapshot.elements if element.get("type") == "password"
    )
    assert password["value"] == "(hidden)"
    assert "sekret" not in snapshot.format()


async def test_select_options_are_reported(page: Page) -> None:
    snapshot = await take_snapshot(page)
    combo = next(
        element for element in snapshot.elements if element.get("role") == "combobox"
    )
    assert combo["options"] == ["Red", "Blue"]


async def test_click_by_ref_changes_the_page(page: Page) -> None:
    snapshot = await take_snapshot(page)
    button = next(
        element
        for element in snapshot.elements
        if element.get("role") == "button" and element["name"] == "Continue"
    )
    await element_for_ref(page, button["ref"]).click()
    assert await page.title() == "Clicked!"


async def test_ref_metadata_reports_the_target(page: Page) -> None:
    snapshot = await take_snapshot(page)
    button = next(
        element
        for element in snapshot.elements
        if element.get("role") == "button" and element["name"] == "Delete account"
    )
    metadata = await ref_metadata(page, button["ref"])
    assert metadata["tag"] == "button"
    assert "Delete" in metadata["text"]


async def test_stale_or_invalid_refs_are_rejected() -> None:
    sentinel = object()
    with pytest.raises(ValueError, match="not a valid reference"):
        element_for_ref(sentinel, "nonsense")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="No element reference"):
        element_for_ref(sentinel, "")  # type: ignore[arg-type]
