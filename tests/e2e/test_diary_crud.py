"""Diary entry lifecycle: create, view, edit, delete. Includes the two
regression tests that map directly to bugs reported in this project:
a long unbroken run of characters in the content must NOT cause a
page-wide horizontal scrollbar (My Diaries / view page), and the ruled
background lines must sit under the actual rendered text baseline."""
from __future__ import annotations

import uuid

from conftest import assert_no_horizontal_overflow, register_via_api


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def _login_fresh_user(page, base_url: str, prefix: str) -> str:
    # /api/auth/register signs the user in immediately via cookies, so
    # there's no separate login step needed here.
    username = _uniq(prefix)
    register_via_api(page, base_url, username, f"{username}@example.com")
    page.goto(f"{base_url}/dashboard")
    page.wait_for_url(f"{base_url}/dashboard", timeout=10_000)
    return username


def _create_entry(page, base_url: str, title: str, content: str, mood: str = "happy") -> None:
    page.goto(f"{base_url}/diaries/new")
    page.fill("#diaryTitle", title)
    page.fill("#diaryContent", content)
    page.click(f'.mood-pill[data-mood="{mood}"]')
    page.click("#submitBtn")
    page.wait_for_url(lambda url: "/diaries/new" not in url, timeout=10_000)


def test_create_entry_and_see_it_in_list(page, live_server):
    _login_fresh_user(page, live_server, "create")
    title = _uniq("My Trip To ")
    _create_entry(page, live_server, title, "It was a wonderful day at the beach.")
    page.goto(f"{live_server}/diaries")
    assert page.locator(f"text={title}").first.is_visible()


def test_view_entry_shows_full_content(page, live_server):
    _login_fresh_user(page, live_server, "view")
    title = _uniq("Detail Entry ")
    body = "This is the full body of the entry, written for the view-page test."
    _create_entry(page, live_server, title, body)
    page.goto(f"{live_server}/diaries")
    page.locator(f"text={title}").first.click()
    page.wait_for_url("**/diaries/*")
    assert page.locator(".diary-reading", has_text=body).is_visible()


def test_edit_entry_updates_content(page, live_server):
    _login_fresh_user(page, live_server, "edit")
    title = _uniq("Editable Entry ")
    _create_entry(page, live_server, title, "Original content before editing.")
    page.goto(f"{live_server}/diaries")
    page.locator(f"text={title}").first.click()
    page.wait_for_url("**/diaries/*")
    page.click('a:has-text("Edit"), a[href$="/edit"]')
    page.wait_for_selector("#diaryContent")
    page.fill("#diaryContent", "Updated content after editing.")
    page.click("#submitBtn")
    page.wait_for_timeout(1000)
    assert page.locator(".diary-reading", has_text="Updated content after editing.").is_visible()


def test_delete_entry_removes_it_from_list(page, live_server):
    _login_fresh_user(page, live_server, "delete")
    title = _uniq("Deletable Entry ")
    _create_entry(page, live_server, title, "This entry is going to be deleted.")
    page.goto(f"{live_server}/diaries")
    page.locator(f"text={title}").first.click()
    page.wait_for_url("**/diaries/*")

    page.once("dialog", lambda dialog: dialog.accept())
    page.click('button[aria-label="Delete entry"]')
    page.wait_for_url(lambda url: url.startswith(f"{live_server}/diaries") and "/diaries/" not in url, timeout=10_000)
    assert page.locator(f"text={title}").count() == 0


# ── Regression: long unbroken content must not blow out page width ──

def test_long_unbroken_content_does_not_cause_horizontal_scroll_on_list(page, live_server):
    _login_fresh_user(page, live_server, "overflow")
    title = _uniq("Overflow Test ")
    long_token = "H" * 400  # exactly the shape of the originally-reported bug
    _create_entry(page, live_server, title, long_token)
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{live_server}/diaries")
    assert_no_horizontal_overflow(page, context="My Diaries list with a long unbroken content token")


def test_long_unbroken_content_does_not_cause_horizontal_scroll_on_view(page, live_server):
    _login_fresh_user(page, live_server, "overflow2")
    title = _uniq("Overflow Detail ")
    long_token = "X" * 500
    _create_entry(page, live_server, title, long_token)
    page.goto(f"{live_server}/diaries")
    page.locator(f"text={title}").first.click()
    page.wait_for_url("**/diaries/*")
    assert_no_horizontal_overflow(page, context="diary detail/view page with a long unbroken content token")


# ── Regression: ruled-line background must align to the real text baseline ──

def test_ruled_line_alignment_view_page(page, live_server):
    """The fix for this bug (see initRuledLineAlignment in app.js) sets
    --rule-offset on the element after measuring the real rendered
    baseline. This asserts that measurement actually ran and produced a
    plausible value, not that the pixels are visually perfect (that part
    still needs a human/visual check) -- it catches the JS silently
    failing to run or the CSS var never being consumed, which is exactly
    the class of regression a future refactor could reintroduce.

    Where the letters actually sit relative to the rules is asserted in
    test_visual_regressions.py; a plausible-range check alone passed for
    the original 13px-off value too. --rule-offset is normalised into
    (-lineHeight, 0] (see align() in app.js), hence the negative range."""
    _login_fresh_user(page, live_server, "ruled")
    title = _uniq("Ruled Line Entry ")
    _create_entry(page, live_server, title, "Checking the ruled line offset on this entry.")
    page.goto(f"{live_server}/diaries")
    page.locator(f"text={title}").first.click()
    page.wait_for_url("**/diaries/*")
    page.wait_for_timeout(300)  # let initRuledLineAlignment's align() run
    offset = page.locator(".diary-reading").evaluate(
        "el => getComputedStyle(el).getPropertyValue('--rule-offset')"
    )
    assert offset.strip() != "", "‑-rule-offset was never set — initRuledLineAlignment did not run"
    px_value = float(offset.strip().replace("px", ""))
    assert -60 < px_value <= 0, f"--rule-offset ({offset}) is outside the expected (-lineHeight, 0] range"


def test_ruled_line_alignment_edit_page(page, live_server):
    _login_fresh_user(page, live_server, "ruled2")
    page.goto(f"{live_server}/diaries/new")
    page.wait_for_timeout(300)
    offset = page.locator(".journal-textarea").evaluate(
        "el => getComputedStyle(el).getPropertyValue('--rule-offset')"
    )
    assert offset.strip() != "", "--rule-offset was never set on .journal-textarea"
    px_value = float(offset.strip().replace("px", ""))
    assert -60 < px_value <= 0, f"--rule-offset ({offset}) is outside the expected (-lineHeight, 0] range"
