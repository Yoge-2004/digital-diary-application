"""My Diaries list: search, mood filter, favourite/bookmark toggles,
archived view, and the horizontal-overflow regression guard across
several viewport widths (this is the page from the original bug
report)."""
from __future__ import annotations

import uuid

import pytest

from conftest import assert_no_horizontal_overflow, register_via_api


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def _login(page, base_url: str, prefix: str) -> str:
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


@pytest.mark.parametrize("width", [360, 768, 1440, 1920, 2560])
def test_diaries_list_no_horizontal_overflow(page, live_server, width):
    _login(page, live_server, "listoverflow")
    _create_entry(page, live_server, _uniq("Entry "), "Some normal-length diary content for this entry.")
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{live_server}/diaries")
    assert_no_horizontal_overflow(page, context=f"My Diaries list at {width}px")


def test_search_finds_matching_entry(page, live_server):
    _login(page, live_server, "search")
    unique_word = _uniq("Zephyrine")
    _create_entry(page, live_server, f"Entry about {unique_word}", "Body text here.")
    _create_entry(page, live_server, "Unrelated Entry", "Different body text.")
    page.goto(f"{live_server}/diaries?q={unique_word}")
    assert page.locator(f"text={unique_word}").first.is_visible()
    assert page.locator("text=Unrelated Entry").count() == 0


def test_search_box_actually_submits_a_working_filter(page, live_server):
    """Regression guard: the search <input> is name="q" and used to be
    bound to a route parameter named `search`, which only ever matched
    ?search=... in the URL -- so typing in the real search box and
    clicking "Apply filters" silently did nothing. This drives the
    actual UI control (not a hand-built URL) to make sure that stays
    fixed even if someone renames the input or the route param again."""
    _login(page, live_server, "searchui")
    unique_word = _uniq("Marigold")
    _create_entry(page, live_server, f"Entry about {unique_word}", "Body text here.")
    _create_entry(page, live_server, "Something Else Entirely", "Different body text.")
    page.goto(f"{live_server}/diaries")
    page.fill("#diariesSearch", unique_word)
    page.click('button:has-text("Apply filters")')
    page.wait_for_load_state("networkidle")
    assert f"q={unique_word}" in page.url or f"q=%20{unique_word}" in page.url or unique_word in page.url
    assert page.locator(f"text={unique_word}").first.is_visible()
    assert page.locator("text=Something Else Entirely").count() == 0


def test_mood_filter_narrows_results(page, live_server):
    _login(page, live_server, "moodfilter")
    happy_title = _uniq("Happy Entry ")
    sad_title = _uniq("Sad Entry ")
    _create_entry(page, live_server, happy_title, "A happy moment.", mood="happy")
    _create_entry(page, live_server, sad_title, "A sad moment.", mood="sad")
    page.goto(f"{live_server}/diaries?mood=sad")
    assert page.locator(f"text={sad_title}").first.is_visible()
    assert page.locator(f"text={happy_title}").count() == 0


def test_favourite_toggle(page, live_server):
    _login(page, live_server, "favtoggle")
    title = _uniq("Favourite Me ")
    _create_entry(page, live_server, title, "Content for favouriting.")
    page.goto(f"{live_server}/diaries")
    card = page.locator(".diary-card", has_text=title)
    fav_btn = card.locator('button[aria-label^="Favourite"]')
    fav_btn.click()
    page.wait_for_timeout(500)
    # Button should now be in the "unfavourite" state
    assert card.locator('button[aria-label^="Unfavourite"]').count() == 1

    page.goto(f"{live_server}/diaries?favorite=true")
    assert page.locator(f"text={title}").first.is_visible()


def test_bookmark_toggle(page, live_server):
    _login(page, live_server, "bookmarktoggle")
    title = _uniq("Bookmark Me ")
    _create_entry(page, live_server, title, "Content for bookmarking.")
    page.goto(f"{live_server}/diaries")
    card = page.locator(".diary-card", has_text=title)
    bm_btn = card.locator('button[aria-label^="Bookmark"]')
    bm_btn.click()
    page.wait_for_timeout(500)
    assert card.locator('button[aria-label^="Unbookmark"]').count() == 1

    page.goto(f"{live_server}/diaries?bookmarked=true")
    assert page.locator(f"text={title}").first.is_visible()


def test_empty_state_when_no_entries(page, live_server):
    _login(page, live_server, "emptystate")
    page.goto(f"{live_server}/diaries")
    assert page.locator(".diary-card").count() == 0
