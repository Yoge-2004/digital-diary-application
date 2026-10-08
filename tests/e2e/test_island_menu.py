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


# ---- adaptive behaviour ------------------------------------------------------

def _many_entries(page, base_url: str, n: int = 10) -> None:
    for i in range(n):
        page.request.post(f"{base_url}/api/diaries", data={"title": f"Entry {i}", "content": "words " * 60, "mood": "happy", "visibility": "private"})


def _scroll_to(page, y: int) -> None:
    page.evaluate(f"window.scrollTo({{ top: {y}, behavior: 'instant' }})")
    page.wait_for_function(f"Math.abs(window.scrollY - {y}) < 2")
    page.wait_for_timeout(250)
    _settle(page)


def _island_width(page) -> float:
    return page.locator("#island").bounding_box()["width"]


def test_island_compacts_while_scrolling_down_and_returns_on_scroll_up(page, live_server):
    _login(page, live_server)
    _many_entries(page, live_server)
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server}/diaries")
    assert _island_width(page) > 150
    _scroll_to(page, 500)
    assert page.evaluate("document.getElementById('island').classList.contains('is-compact')")
    assert _island_width(page) < 60, "should be a small circle"
    # still operable and still named while compact
    assert "Quick navigation" in page.get_attribute("#islandToggle", "aria-label")
    page.click("#islandToggle")
    _settle(page)
    assert _is_open(page) and _island_width(page) > 300, "opening a compact island must expand it"
    page.click("#islandToggle")
    _scroll_to(page, 300)
    assert not page.evaluate("document.getElementById('island').classList.contains('is-compact')")
    assert _island_width(page) > 150


def test_island_expands_again_near_the_bottom_and_on_hover(page, live_server):
    _login(page, live_server)
    _many_entries(page, live_server)
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server}/diaries")
    _scroll_to(page, 500)
    assert _island_width(page) < 60
    page.locator("#island").hover()
    _settle(page)
    assert _island_width(page) > 150, "hovering the compact circle with a mouse should expand it"
    page.mouse.move(5, 5)
    _scroll_to(page, 600)
    page.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: 'instant' })")
    page.wait_for_function("Math.abs(window.scrollY + innerHeight - document.documentElement.scrollHeight) < 2")
    _settle(page)
    assert _island_width(page) > 150, "at the end of the page the nav should be back"


def test_island_hides_while_typing_on_a_phone_and_returns(page, live_server):
    _login(page, live_server)
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server}/diaries/new")
    page.focus("#diaryContent")
    page.wait_for_function("document.getElementById('island').classList.contains('is-typing')")
    _settle(page)
    assert page.evaluate("getComputedStyle(document.getElementById('island')).visibility") == "hidden"
    page.keyboard.type("hello")
    # While it is tucked away it must not be reachable: focusing a hidden element is a no-op.
    page.evaluate("document.getElementById('islandToggle').focus()")
    assert page.evaluate("document.activeElement.id") == "diaryContent", "hidden island took focus while typing"
    page.evaluate("document.activeElement.blur()")
    page.wait_for_function("!document.getElementById('island').classList.contains('is-typing')")
    _settle(page)
    assert page.locator("#island").is_visible()


def test_island_stays_put_while_typing_on_a_desktop(page, live_server):
    """The keyboard-avoidance is for phones only; on desktop the pill is useful while writing."""
    _login(page, live_server)
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server}/diaries/new")
    page.focus("#diaryContent")
    page.keyboard.type("hello there")
    page.wait_for_timeout(300)
    assert not page.evaluate("document.getElementById('island').classList.contains('is-typing')")
    assert page.locator("#island").is_visible()


def test_island_shows_a_live_word_count_on_the_write_page(page, live_server):
    _login(page, live_server)
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server}/diaries/new")
    assert page.inner_text("#islandMeta") == ""
    page.fill("#diaryContent", "one")
    assert page.inner_text("#islandMeta") == "1 word"
    page.fill("#diaryContent", "one two three four")
    assert page.inner_text("#islandMeta") == "4 words"
    # visible text must be in the accessible name (WCAG 2.5.3)
    assert page.get_attribute("#islandToggle", "aria-label").endswith("4 words")
    page.fill("#diaryContent", "")
    assert "words" not in page.get_attribute("#islandToggle", "aria-label")


def test_island_progress_hairline_follows_the_scroll_position(page, live_server):
    _login(page, live_server)
    _many_entries(page, live_server, 12)
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server}/diaries")
    read = lambda: float(page.evaluate("document.getElementById('island').style.getPropertyValue('--island-progress') || '0'"))
    page.wait_for_function("document.getElementById('island').dataset.scrollable === 'true'")
    assert read() < 0.05
    _scroll_to(page, 600)
    mid = read()
    page.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: 'instant' })")
    page.wait_for_function("Math.abs(window.scrollY + innerHeight - document.documentElement.scrollHeight) < 2")
    page.wait_for_timeout(300)
    end = read()
    assert 0.05 < mid < 0.95 and end > 0.97 and end <= 1.0, (mid, end)


@pytest.mark.parametrize("width,cols", [(390, 4), (640, 8), (700, 8), (1280, 8)])
def test_open_island_grid_adapts_to_the_screen_without_overflowing(page, live_server, width, cols):
    _login(page, live_server)
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{live_server}/dashboard")
    page.click("#islandToggle")
    _settle(page)
    tops = page.evaluate("[...document.querySelectorAll('#islandMenu .island-item')].map(e => Math.round(e.getBoundingClientRect().top))")
    assert len(set(tops)) == (2 if cols == 4 else 1), f"{width}px: expected {cols} columns, got rows at {sorted(set(tops))}"
    clipped = page.evaluate("[...document.querySelectorAll('#islandMenu .island-item')].filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.innerText.trim())")
    assert not clipped, f"labels overflow their tile at {width}px: {clipped}"
    box = page.locator("#island").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width + 0.5


@pytest.mark.parametrize("width", [390, 521, 768, 1023, 1024, 1100, 1280, 1920])
def test_island_is_centred_on_the_screen_at_every_width(page, live_server, width):
    """It used to centre on the content area beside the sidebar (135-150px right of the
    screen centre from 1024px up)."""
    _login(page, live_server)
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{live_server}/dashboard")
    _settle(page)
    for opened in (False, True):
        if opened:
            page.click("#islandToggle")
            _settle(page)
        box = page.locator("#island").bounding_box()
        centre = box["x"] + box["width"] / 2
        assert abs(centre - width / 2) <= 1, f"{width}px, open={opened}: island centre {centre}, screen centre {width / 2}"


@pytest.mark.parametrize("width", [1024, 1100, 1199, 1200, 1280])
def test_open_island_never_reaches_under_the_sidebar(page, live_server, width):
    _login(page, live_server)
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{live_server}/dashboard")
    page.click("#islandToggle")
    _settle(page)
    island = page.locator("#island").bounding_box()
    sidebar = page.locator("#appSidebar").bounding_box()
    assert island["x"] >= sidebar["x"] + sidebar["width"], f"{width}px: island starts at {island['x']}, sidebar ends at {sidebar['x'] + sidebar['width']}"
