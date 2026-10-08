"""The edit form must not print Python's None into fields."""
from __future__ import annotations

import uuid

from conftest import register_via_api


def _entry(page, base, **extra):
    r = page.request.post(f"{base}/api/diaries", data={"title": "T", "content": "body text", "mood": "neutral", "visibility": "private", **extra})
    assert r.ok, r.text()
    return r.json()["id"]


def test_edit_form_shows_an_empty_location_not_the_word_none(page, live_server):
    """{{ diary.location }} rendered None as the text 'None', and saving the form then stored
    it, so the entry page showed a location pin reading 'None'."""
    u = f"ef{uuid.uuid4().hex[:8]}"
    register_via_api(page, live_server, u, f"{u}@example.com")
    diary_id = _entry(page, live_server)
    page.goto(f"{live_server}/diaries/{diary_id}/edit")
    assert page.input_value(".journal-location-input") == ""
    page.fill("#diaryContent", "body text, edited")  # an untouched form is not submitted
    page.click("#submitBtn")
    page.wait_for_selector(".diary-reading")
    assert page.locator(".journal-location-stamp").count() == 0, "saving an untouched edit form invented a location"


def test_edit_form_keeps_a_real_location(page, live_server):
    u = f"ef{uuid.uuid4().hex[:8]}"
    register_via_api(page, live_server, u, f"{u}@example.com")
    diary_id = _entry(page, live_server, location="Paris, France")
    page.goto(f"{live_server}/diaries/{diary_id}/edit")
    assert page.input_value(".journal-location-input") == "Paris, France"
