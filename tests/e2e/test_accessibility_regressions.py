"""Regression guards for problems an axe-core sweep of every page found.

The contrast checks assert on the design tokens and components directly
(computed colours in a real browser), so they keep working as pages change.
"""
from __future__ import annotations

import re
import uuid

import pytest

from conftest import register_via_api

MOODS = ["happy", "sad", "neutral", "angry", "anxious", "excited", "grateful", "calm", "melancholy", "hopeful"]


def _rgb(css: str):
    return tuple(int(float(v)) for v in re.findall(r"[\d.]+", css)[:3])


def _lum(rgb):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _signup(page, base_url: str) -> None:
    u = f"a11y{uuid.uuid4().hex[:8]}"
    register_via_api(page, base_url, u, f"{u}@example.com")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_muted_and_accent_text_tokens_meet_contrast_on_every_surface(page, live_server, theme):
    """Dark-mode --txt-muted was 3.5-3.75:1 and the crimson used as text was
    2.75:1 (needs 4.5:1), across ~10 pages. This checks the tokens themselves."""
    page.add_init_script(f"localStorage.setItem('dd-theme', '{theme}')")
    page.goto(f"{live_server}/login")
    colours = page.evaluate(
        """() => {
          const probe = (prop, v) => { const e = document.createElement('div'); e.style[prop] = `var(${v})`;
            document.body.appendChild(e); const c = getComputedStyle(e)[prop]; e.remove(); return c; };
          return { muted: probe('color', '--txt-muted'), accent: probe('color', '--accent-text'),
                   body: probe('backgroundColor', '--bg-body'), surface: probe('backgroundColor', '--bg-surface'),
                   surface2: probe('backgroundColor', '--bg-surface-2') };
        }"""
    )
    for text in ("muted", "accent"):
        for surface in ("body", "surface", "surface2"):
            ratio = _contrast(_rgb(colours[text]), _rgb(colours[surface]))
            assert ratio >= 4.5, f"{theme}: {text} text {colours[text]} on {surface} {colours[surface]} is {ratio:.2f}:1"


def test_every_mood_badge_is_readable(page, live_server):
    """Badges were white text on the mood colour: 2.0:1 on amber, 2.4:1 on
    teal... Each mood now picks white or dark ink, whichever passes."""
    page.goto(f"{live_server}/login")
    found = page.evaluate(
        """(moods) => moods.map((m) => { const e = document.createElement('span'); e.className = `mood-badge mood--${m}`;
          e.textContent = m; document.body.appendChild(e); const s = getComputedStyle(e);
          const out = { mood: m, color: s.color, bg: s.backgroundColor }; e.remove(); return out; })""",
        MOODS,
    )
    bad = [(f["mood"], round(_contrast(_rgb(f["color"]), _rgb(f["bg"])), 2)) for f in found if _contrast(_rgb(f["color"]), _rgb(f["bg"])) < 4.5]
    assert not bad, f"mood badges below 4.5:1: {bad}"


def test_landing_book_card_text_is_readable_in_dark_theme(page, live_server):
    """The landing 'book' is a fixed white page, but its text followed the
    theme and was near-white on white in dark mode (2.4:1, 2.9:1)."""
    page.add_init_script("localStorage.setItem('dd-theme', 'dark')")
    page.goto(f"{live_server}/")
    rows = page.evaluate(
        """() => [...document.querySelectorAll('.book-open h2, .book-open p, .book-open span')]
              .filter((e) => e.textContent.trim()).map((e) => ({ t: e.textContent.trim().slice(0, 24), c: getComputedStyle(e).color }))"""
    )
    assert len(rows) >= 3, rows
    for r in rows:
        ratio = _contrast(_rgb(r["c"]), (255, 255, 255))
        assert ratio >= 4.5, f"landing book text {r['t']!r} ({r['c']}) is {ratio:.2f}:1 on white"


def test_dashboard_entry_cards_are_valid_and_fully_clickable(page, live_server):
    """Each recent-entry card was wrapped in an <a> that also contained tag
    <a>s. Nested anchors are invalid; the parser repaired them into two
    EMPTY extra links per card (nameless tab stops) and a card whose edges
    weren't clickable."""
    _signup(page, live_server)
    r = page.request.post(
        f"{live_server}/api/diaries",
        data={"title": "Rainy Tuesday", "content": "The rain kept on all day. " * 8, "mood": "sad", "visibility": "private", "tags": ["journal", "travel"]},
    )
    assert r.ok, r.text()
    diary_id = r.json()["id"]
    page.goto(f"{live_server}/dashboard")
    page.wait_for_selector(".diary-card")
    info = page.evaluate(
        """() => { const card = document.querySelector('.diary-card');
          const anchors = [...card.querySelectorAll('a')];
          return { nested: document.querySelectorAll('a a').length,
                   unnamed: anchors.filter((a) => !(a.textContent.trim() || a.getAttribute('aria-label'))).length,
                   entryLinks: anchors.filter((a) => a.getAttribute('href').startsWith('/diaries/') && !a.getAttribute('href').includes('?')).length };
        }"""
    )
    assert info["nested"] == 0, info
    assert info["unnamed"] == 0, f"links without an accessible name inside the card: {info}"
    assert info["entryLinks"] == 1, info
    box = page.locator(".diary-card").first.bounding_box()
    page.mouse.click(box["x"] + box["width"] - 12, box["y"] + 12)  # an edge that used to be dead
    page.wait_for_url(f"**/diaries/{diary_id}")


def test_calendar_grid_cells_sit_inside_rows(page, live_server):
    """role=grid needs role=row parents for its headers and cells."""
    _signup(page, live_server)
    page.goto(f"{live_server}/calendar")
    stray = page.evaluate(
        """() => [...document.querySelectorAll('.calendar-grid [role=columnheader], .calendar-grid [role=gridcell]')]
              .filter((c) => !c.parentElement || c.parentElement.getAttribute('role') !== 'row').length"""
    )
    assert stray == 0, f"{stray} calendar cells are not inside a role=row"
    # display: contents rows must not change the 7-column layout
    cols = page.evaluate(
        "new Set([...document.querySelectorAll('.cal-header')].map((h) => Math.round(h.getBoundingClientRect().left))).size"
    )
    assert cols == 7, f"calendar headers span {cols} distinct columns, expected 7"


def test_in_text_links_on_the_auth_pages_are_underlined(page, live_server):
    """'Sign in instead' was distinguished from its sentence by colour alone."""
    page.goto(f"{live_server}/register")
    deco = page.evaluate("getComputedStyle(document.querySelector('.auth-form-sub a')).textDecorationLine")
    assert "underline" in deco, deco
