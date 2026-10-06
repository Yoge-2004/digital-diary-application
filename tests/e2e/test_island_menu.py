"""The floating "island" quick-nav: a pill that expands into a grid of destinations."""
from __future__ import annotations

import uuid

import pytest

from conftest import register_via_api

PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1280, "height": 800}


def _login(page, base_url: str) -> None:
    u = f"is{uuid.uuid4().hex[:8]}"
    register_via_api(page, base_url, u, f"{u}@example.com")


def _is_open(page) -> bool:
    return page.get_attribute("#islandToggle", "aria-expanded") == "true"


def _settle(page) -> None:
    page.evaluate(
        """async () => { await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
          const f = document.getAnimations().filter(a => a.effect && a.effect.getComputedTiming().iterations !== Infinity);
          await Promise.race([Promise.all(f.map(a => a.finished.catch(() => {}))), new Promise(r => setTimeout(r, 4000))]); }"""
    )


def test_island_is_only_for_signed_in_pages(page, live_server):
    page.goto(f"{live_server}/login")
    assert page.locator("#island").count() == 0
    _login(page, live_server)
    page.goto(f"{live_server}/dashboard")
    assert page.locator("#island").is_visible()


@pytest.mark.parametrize("path,label", [("/dashboard", "Dashboard"), ("/calendar", "Calendar"), ("/diaries/new", "New"), ("/settings", "Settings")])
def test_pill_names_the_current_section_and_marks_it_current(page, live_server, path, label):
    _login(page, live_server)
    page.goto(f"{live_server}{path}")
    assert page.inner_text("#islandToggle .island-current").strip() == label
    # the visible text must be part of the accessible name (WCAG 2.5.3)
    assert label in page.get_attribute("#islandToggle", "aria-label")
    page.click("#islandToggle")
    assert page.locator('#islandMenu a[aria-current="page"]').inner_text().strip() == label


def test_an_entry_page_counts_as_diaries_but_new_does_not(page, live_server):
    _login(page, live_server)
    r = page.request.post(f"{live_server}/api/diaries", data={"title": "t", "content": "c", "mood": "happy", "visibility": "private"})
    page.goto(f"{live_server}/diaries/{r.json()['id']}")
    assert page.inner_text("#islandToggle .island-current").strip() == "Diaries"
    page.goto(f"{live_server}/diaries/new")
    assert page.inner_text("#islandToggle .island-current").strip() == "New"


def test_closed_island_menu_is_not_in_the_tab_order(page, live_server):
    """Same trap as the sidebar drawer: collapsed to zero height is not hidden."""
    _login(page, live_server)
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server}/dashboard")
    assert not _is_open(page)
    stops = []
    for _ in range(60):
        page.keyboard.press("Tab")
        stops.append(page.evaluate("document.activeElement.closest('#islandMenu') ? 'island-link' : (document.activeElement.id || document.activeElement.tagName)"))
    assert "islandToggle" in stops
    assert "island-link" not in stops, "closed island links took tab stops"
    assert page.locator("#islandMenu a").first.is_hidden()


def test_island_opens_and_closes_from_the_keyboard(page, live_server):
    _login(page, live_server)
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server}/dashboard")
    page.focus("#islandToggle")
    page.keyboard.press("Enter")
    page.wait_for_function("document.getElementById('islandToggle').getAttribute('aria-expanded') === 'true'")
    _settle(page)
    page.keyboard.press("Tab")
    assert page.evaluate("!!document.activeElement.closest('#islandMenu')"), "Tab from the open pill should enter the menu"
    page.keyboard.press("Escape")
    page.wait_for_function("document.getElementById('islandToggle').getAttribute('aria-expanded') === 'false'")
    assert page.evaluate("document.activeElement.id") == "islandToggle", "Escape should return focus to the pill"


def test_island_closes_on_outside_click_and_when_focus_leaves(page, live_server):
    _login(page, live_server)
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server}/dashboard")
    page.click("#islandToggle")
    assert _is_open(page)
    page.mouse.click(700, 150)
    assert not _is_open(page)
    page.click("#islandToggle")
    _settle(page)
    page.focus("#islandMenu .island-item:last-child")
    page.keyboard.press("Tab")  # past the last item: out of the island
    page.wait_for_function("document.getElementById('islandToggle').getAttribute('aria-expanded') === 'false'")


def test_island_navigates_and_toggles_the_theme(page, live_server):
    _login(page, live_server)
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server}/dashboard")
    page.click("#islandToggle")
    _settle(page)
    before = page.evaluate("document.documentElement.getAttribute('data-theme') || 'light'")
    page.click("#islandMenu .theme-toggle")
    after = page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert after != before
    assert _is_open(page), "toggling the theme shouldn't collapse the menu"
    page.click('#islandMenu a[href="/calendar"]')
    page.wait_for_url("**/calendar")
    assert not _is_open(page), "a fresh page starts collapsed"


@pytest.mark.parametrize("size", [PHONE, {"width": 320, "height": 568}, DESKTOP], ids=["390", "320", "1280"])
def test_island_stays_inside_the_viewport_and_never_covers_the_last_content(page, live_server, size):
    _login(page, live_server)
    for i in range(6):
        page.request.post(f"{live_server}/api/diaries", data={"title": f"Entry {i}", "content": "words " * 40, "mood": "happy", "visibility": "private"})
    page.set_viewport_size(size)
    page.goto(f"{live_server}/dashboard")
    page.click("#islandToggle")
    _settle(page)
    box = page.locator("#island").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= size["width"] + 0.5, box
    assert box["y"] >= 0 and box["y"] + box["height"] <= size["height"], box
    assert not page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"), "horizontal scroll"
    page.click("#islandToggle")
    _settle(page)
    page.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: 'instant' })")
    page.wait_for_function("Math.abs(window.scrollY + innerHeight - document.documentElement.scrollHeight) < 2")
    island_top = page.locator("#island").bounding_box()["y"]
    last_bottom = page.evaluate(
        "(() => { const m = document.getElementById('main-content'); const kids = [...m.querySelectorAll('*')].filter(e => e.getBoundingClientRect().height > 0);"
        " return Math.max(...kids.map(e => e.getBoundingClientRect().bottom)); })()"
    )
    assert last_bottom <= island_top + 0.5, f"island covers the end of the page ({last_bottom} > {island_top})"


def test_reduced_motion_opens_without_animating(browser, live_server):
    ctx = browser.new_context(reduced_motion="reduce", viewport=PHONE)
    page = ctx.new_page()
    _login(page, live_server)
    page.goto(f"{live_server}/dashboard")
    page.click("#islandToggle")
    width = page.evaluate("document.getElementById('island').getBoundingClientRect().width")
    assert width > 300, f"island still mid-animation under reduced motion: {width}px"
    ctx.close()
