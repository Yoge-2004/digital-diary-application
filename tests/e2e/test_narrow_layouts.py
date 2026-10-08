"""Layout regressions found by sweeping 20 device sizes with awkward data (long usernames,
long locations, unbroken strings). Each test measures real boxes in a real browser."""
from __future__ import annotations

import uuid

import pytest

from conftest import register_via_api

NARROW = [280, 320, 360, 390]


def _signup(page, base_url, username=None):
    u = username or f"nl{uuid.uuid4().hex[:8]}"
    register_via_api(page, base_url, u, f"{u}@example.com")


def _entry(page, base, **extra):
    data = {"title": "T", "content": "body text", "mood": "neutral", "visibility": "private", **extra}
    r = page.request.post(f"{base}/api/diaries", data=data)
    assert r.ok, r.text()
    return r.json()["id"]


@pytest.mark.parametrize("width", NARROW)
def test_entry_header_blocks_do_not_overlap_when_narrow(page, live_server, width):
    """The title/date block was flex:1 (basis 0), so it never wrapped and was crushed under the
    mood seal and Edit button, which then overlapped the date text."""
    _signup(page, live_server)
    diary_id = _entry(page, live_server, title="FIRST DIARY....!", content="x")
    page.request.patch(f"{live_server}/api/diaries/{diary_id}", data={"is_pinned": True})
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{live_server}/diaries/{diary_id}")
    page.wait_for_selector(".journal-entry-header")
    page.wait_for_timeout(500)
    hits = page.evaluate(
        """() => { const row = document.querySelector('.journal-entry-header > div');
          const [left, right] = row.children; const r = right.getBoundingClientRect(); const out = [];
          // the squeezed date block spills its text under the seal/Edit button, so compare every
          // descendant (not just the block boxes) with the right-hand block
          for (const e of left.querySelectorAll('*')) { const b = e.getBoundingClientRect(); if (!b.width || !b.height) continue;
            const w = Math.min(b.right, r.right) - Math.max(b.left, r.left), h = Math.min(b.bottom, r.bottom) - Math.max(b.top, r.top);
            if (w > 1 && h > 1) out.push((e.className || e.tagName) + ' ' + (e.innerText || '').trim().slice(0, 20) + ' ' + Math.round(w) + 'x' + Math.round(h)); }
          return { out, rightEdge: r.right, leftEdge: left.getBoundingClientRect().left }; }"""
    )
    assert not hits["out"], f"{width}px: header text runs under the seal/Edit button: {hits['out']}"
    assert hits["rightEdge"] <= width + 0.5 and hits["leftEdge"] >= -0.5, f"{width}px: header leaves the screen {hits}"


def _overflows(page, selector):
    """Elements matching selector whose content is wider than their box or leaves the screen."""
    return page.evaluate(
        """(sel) => { const vw = document.documentElement.clientWidth; const bad = [];
          for (const e of document.querySelectorAll(sel)) { const r = e.getBoundingClientRect(); if (!r.width || getComputedStyle(e).visibility === 'hidden') continue;
            if (e.scrollWidth > e.clientWidth + 1) bad.push((e.id || e.className) + ' "' + (e.innerText || '').trim().slice(0, 28) + '" clipped ' + e.scrollWidth + '>' + e.clientWidth);
            if (r.right > vw + 1 || r.left < -1) bad.push((e.id || e.className) + ' "' + (e.innerText || '').trim().slice(0, 28) + '" off-screen ' + Math.round(r.left) + '..' + Math.round(r.right) + ' of ' + vw); }
          return bad; }""",
        selector,
    )


@pytest.mark.parametrize("width", [280, 320, 390, 1280])
def test_delete_account_button_label_is_not_cut_off(page, live_server, width):
    """'Delete my account permanently' was nowrap in a 184px button (235px of text), clipped at every
    screen size including 1280px."""
    _signup(page, live_server)
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{live_server}/settings")
    page.click('.settings-tab[data-panel="danger"]')
    page.click("#openDeleteAccountModal")
    page.wait_for_selector("#confirmDeleteAccount")
    page.wait_for_timeout(600)
    assert _overflows(page, "#confirmDeleteAccount, #cancelDeleteAccount") == []


@pytest.mark.parametrize("width", [280, 320, 360, 390])
def test_long_username_does_not_overflow_the_dashboard_greeting(page, live_server, width):
    """A 50-character username (the maximum) overflowed the greeting by ~290px and pushed
    'New entry' out of view."""
    _signup(page, live_server, username="u" + uuid.uuid4().hex[:7] + "LongUserName" * 3 + "x")
    _entry(page, live_server)
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{live_server}/dashboard")
    page.wait_for_timeout(600)
    assert _overflows(page, ".page-title, .page-header a.btn, .page-header .btn") == []


@pytest.mark.parametrize("width", [280, 320, 390])
def test_streak_button_label_is_not_cut_off(page, live_server, width):
    _signup(page, live_server)
    _entry(page, live_server)
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{live_server}/dashboard")
    page.wait_for_timeout(600)
    assert _overflows(page, "a.btn, button.btn") == []


@pytest.mark.parametrize("width", [280, 320, 390])
def test_long_location_stays_inside_the_entry_page(page, live_server, width):
    _signup(page, live_server)
    diary_id = _entry(page, live_server, location="A very long location name, Somewhere Far Away, Another Region, Country")
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{live_server}/diaries/{diary_id}")
    page.wait_for_timeout(600)
    assert _overflows(page, ".journal-location-stamp") == []


@pytest.mark.parametrize("width", [280, 320])
def test_location_row_fits_on_the_write_page(page, live_server, width):
    _signup(page, live_server)
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{live_server}/diaries/new")
    page.wait_for_timeout(600)
    assert _overflows(page, "#detectLocationBtn, .journal-location-input") == []


@pytest.mark.parametrize("width", [280, 320, 360])
def test_landing_header_fits_on_very_narrow_phones(page, live_server, width):
    page.set_viewport_size({"width": width, "height": 700})
    page.goto(f"{live_server}/")
    page.wait_for_timeout(600)
    assert _overflows(page, ".topbar-actions, .topbar-actions .btn, .topbar-actions .theme-toggle") == []
    assert page.get_attribute(".topbar-actions .theme-toggle", "aria-label"), "icon-only toggle needs an accessible name"


@pytest.mark.parametrize("width", [320, 375, 412])
def test_404_page_fits_a_phone_instead_of_being_laid_out_at_980px(browser, live_server, width):
    """The old raw-JSON 404 had no viewport tag, so a 375px phone laid it out 980px wide."""
    ctx = browser.new_context(viewport={"width": width, "height": 700}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    resp = page.goto(f"{live_server}/definitely-not-a-page")
    assert resp.status == 404
    assert page.evaluate("document.documentElement.clientWidth") == width
    assert not page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
    assert page.locator("a[href='/']").is_visible()
    ctx.close()
