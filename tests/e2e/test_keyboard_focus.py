"""Keyboard / focus-order regressions found by tabbing through every page.

A throwaway probe pressed Tab through each page at desktop and phone width,
recording each stop (position, visibility, focus indicator). Everything but
the navigation drawer was fine; these tests pin the drawer behaviour.
"""
from __future__ import annotations

import uuid

from conftest import register_via_api

PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1280, "height": 800}


def _login(page, base_url: str) -> None:
    u = f"kb{uuid.uuid4().hex[:8]}"
    register_via_api(page, base_url, u, f"{u}@example.com")


def _focus_info(page) -> dict:
    return page.evaluate(
        """() => { const e = document.activeElement;
          return { tag: e.tagName.toLowerCase(), label: (e.getAttribute('aria-label') || e.innerText || '').trim().slice(0, 40),
                   inSidebar: !!e.closest('#appSidebar'), inMain: !!e.closest('.app-main') }; }"""
    )


def _tab_stops(page, n: int) -> list[dict]:
    stops = []
    for _ in range(n):
        page.keyboard.press("Tab")
        stops.append(_focus_info(page))
    return stops


def test_close_nav_button_is_not_shown_or_tabbable_on_desktop(page, live_server):
    """base.html gave it Bootstrap's d-lg-none, which app.css never defined, so
    the drawer's close X showed in the desktop sidebar and took a tab stop."""
    page.set_viewport_size(DESKTOP)
    _login(page, live_server)
    page.goto(f"{live_server}/dashboard")
    assert not page.locator("#sidebarCloseBtn").is_visible()
    stops = _tab_stops(page, 20)
    assert all(s["label"] != "Close navigation menu" for s in stops), stops


def test_closed_mobile_drawer_is_not_in_the_tab_order(page, live_server):
    """Off-canvas isn't hidden: 13 sidebar links took tab stops with focus
    sliding off the left edge, ahead of the menu button and the page."""
    page.set_viewport_size(PHONE)
    _login(page, live_server)
    page.goto(f"{live_server}/dashboard")
    page.wait_for_timeout(500)
    stops = _tab_stops(page, 6)
    assert not any(s["inSidebar"] for s in stops), stops
    assert any(s["label"] == "Open navigation menu" for s in stops), stops


def test_mobile_drawer_keyboard_flow(page, live_server):
    """Open with Enter: focus moves into the drawer and the page behind is
    unreachable. Escape closes it and returns focus to the menu button."""
    page.set_viewport_size(PHONE)
    _login(page, live_server)
    page.goto(f"{live_server}/dashboard")
    page.focus("#sidebarToggle")
    page.keyboard.press("Enter")
    page.wait_for_selector("#appSidebar.open")
    assert page.evaluate("document.activeElement.id") == "sidebarCloseBtn"
    assert page.evaluate("document.querySelector('.app-main').inert") is True
    stops = _tab_stops(page, 20)
    assert not any(s["inMain"] for s in stops), "focus escaped the open drawer into the page behind it"
    assert any(s["label"] == "Dashboard" for s in stops)
    page.keyboard.press("Escape")
    page.wait_for_selector("#appSidebar:not(.open)", state="attached")
    assert page.evaluate("document.activeElement.id") == "sidebarToggle"
    assert page.evaluate("document.querySelector('.app-main').inert") is False
    assert page.get_attribute("#sidebarToggle", "aria-expanded") == "false"


def test_resizing_to_desktop_with_the_drawer_open_does_not_leave_the_page_inert(page, live_server):
    page.set_viewport_size(PHONE)
    _login(page, live_server)
    page.goto(f"{live_server}/dashboard")
    page.click("#sidebarToggle")
    page.wait_for_selector("#appSidebar.open")
    page.set_viewport_size(DESKTOP)
    page.wait_for_function("!document.querySelector('.app-main').inert")
    assert not page.evaluate("document.getElementById('appSidebar').classList.contains('open')")


def test_drawer_still_slides_closed_before_it_is_hidden(page, live_server):
    """visibility:hidden is what removes the closed drawer from the tab order,
    but applying it at once would make the close animation vanish. It must stay
    visible for the slide and only then hide."""
    page.set_viewport_size(PHONE)
    _login(page, live_server)
    page.goto(f"{live_server}/dashboard")
    page.click("#sidebarToggle")
    page.wait_for_selector("#appSidebar.open")
    page.wait_for_timeout(700)
    frames = page.evaluate(
        """async () => { const s = document.getElementById('appSidebar'); const out = [];
          document.getElementById('sidebarCloseBtn').click();
          for (let i = 0; i < 12; i++) { out.push([Math.round(s.getBoundingClientRect().x), getComputedStyle(s).visibility]);
                                         await new Promise(r => setTimeout(r, 50)); }
          return out; }"""
    )
    assert any(-260 < x < -10 and v == "visible" for x, v in frames), f"no visible mid-slide frame: {frames}"
    assert frames[-1][1] == "hidden", f"drawer never hid after sliding: {frames}"
