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
