"""Interactive frontend test suite.

Tests real browser UI interactions:
1. Zero uncaught JavaScript errors across major user-facing routes
2. Silk ribbon bookmark interactive toggle & AJAX sync
3. Continuous View vs Book View switching and multi-page pagination navigation
4. Diary editor live word/character counters and mood pill selection
5. Diary editor dynamic tag pills preview
6. Password visibility eye-toggle interaction
7. Mobile responsive sidebar navigation drawer open/close
8. Theme toggle (light/dark) live DOM attribute switching
"""
from __future__ import annotations

import uuid
import pytest
from conftest import assert_no_horizontal_overflow, register_via_api


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def _login_user(page, base_url: str, prefix: str = "feuser") -> str:
    username = _uniq(prefix)
    register_via_api(page, base_url, username, f"{username}@example.com")
    page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")
    page.wait_for_url(f"{base_url}/dashboard", timeout=10_000)
    return username


def _create_entry(page, base_url: str, title: str, content: str, mood: str = "calm") -> None:
    page.goto(f"{base_url}/diaries/new", wait_until="domcontentloaded")
    page.fill("#diaryTitle", title)
    page.fill("#diaryContent", content)
    page.click(f'.mood-pill[data-mood="{mood}"]')
    page.click("#submitBtn")
    page.wait_for_url(lambda url: "/diaries/new" not in url, timeout=10_000)


def test_zero_console_errors_across_main_routes(page, live_server):
    """Navigating the primary routes must not trigger uncaught JavaScript exceptions."""
    js_errors: list[str] = []
    page.on("pageerror", lambda err: js_errors.append(str(err)))

    # 1. Unauthenticated routes
    for path in ["/", "/login", "/register"]:
        page.goto(f"{live_server}{path}")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(100)

    # 2. Authenticated user routes
    _login_user(page, live_server, "jschk")
    entry_title = _uniq("Console Test ")
    _create_entry(page, live_server, entry_title, "A clean entry to verify no runtime console errors occur.")

    page.goto(f"{live_server}/diaries")
    page.locator(f"text={entry_title}").first.click()
    page.wait_for_url("**/diaries/*")
    page.wait_for_load_state("networkidle")

    for path in ["/dashboard", "/diaries", "/diaries/new", "/settings", "/calendar", "/stats"]:
        page.goto(f"{live_server}{path}")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(100)

    assert js_errors == [], f"Uncaught JavaScript exceptions detected: {js_errors}"


def test_silk_ribbon_bookmark_toggle_and_sync(page, live_server):
    """Clicking the physical silk ribbon bookmark must toggle bookmark state via AJAX and update UI."""
    _login_user(page, live_server, "ribbon")
    title = _uniq("Ribbon Test ")
    _create_entry(page, live_server, title, "Testing the silk bookmark ribbon interactivity.")
    page.goto(f"{live_server}/diaries")
    page.locator(f"text={title}").first.click()
    page.wait_for_url("**/diaries/*")

    ribbon = page.locator("#diaryRibbonBookmark")
    assert ribbon.is_visible()

    # Ribbon initially not bookmarked
    assert "bookmarked" not in (ribbon.get_attribute("class") or "")

    # Click ribbon to bookmark
    ribbon.click()
    page.wait_for_timeout(600)
    assert "bookmarked" in (ribbon.get_attribute("class") or "")

    # Reload to verify persistence
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#diaryRibbonBookmark")
    assert "bookmarked" in (page.locator("#diaryRibbonBookmark").get_attribute("class") or "")

    # Click again to unbookmark
    page.locator("#diaryRibbonBookmark").click()
    page.wait_for_timeout(600)
    assert "bookmarked" not in (page.locator("#diaryRibbonBookmark").get_attribute("class") or "")


def test_book_mode_pagination_and_view_toggle(page, live_server):
    """Switching between Continuous View and Book View must paginate content and enable page turning."""
    _login_user(page, live_server, "bookview")
    title = _uniq("Epic Story ")
    # Create long content across multiple paragraphs that triggers pagination in book view
    paragraphs = [
        f"Paragraph {i}: " + ("This is a rich and memorable diary entry with detailed thoughts and reflections. " * 8)
        for i in range(1, 12)
    ]
    long_content = "\n\n".join(paragraphs)
    _create_entry(page, live_server, title, long_content)

    page.goto(f"{live_server}/diaries")
    page.locator(f"text={title}").first.click()
    page.wait_for_url("**/diaries/*")

    # Initially in Continuous View
    page_card = page.locator("#journalPageCard")
    assert "continuous-view" in (page_card.get_attribute("class") or "")
    page_text = page.locator("#bookPageText")
    assert page_text.inner_text().strip() == "Continuous View"

    # Toggle to Book View
    page.click("#btnBookToggleView")
    page.wait_for_timeout(300)

    # Page card is now in paginated book mode
    assert "continuous-view" not in (page_card.get_attribute("class") or "")
    assert "Page 1 of" in page_text.inner_text()
    assert page.locator("#btnBookNext").is_enabled()
    assert page.locator("#btnBookPrev").is_disabled()

    # Turn to next page using next button
    page.click("#btnBookNext")
    page.wait_for_timeout(500)
    assert "Page 2 of" in page_text.inner_text()
    assert page.locator("#btnBookPrev").is_enabled()

    # Turn backward using keyboard ArrowLeft
    page.keyboard.press("ArrowLeft")
    page.wait_for_timeout(500)
    assert "Page 1 of" in page_text.inner_text()

    # Turn forward using keyboard ArrowRight
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(500)
    assert "Page 2 of" in page_text.inner_text()

    # Switch back to Continuous View
    page.click("#btnBookToggleView")
    page.wait_for_timeout(300)
    assert "continuous-view" in (page_card.get_attribute("class") or "")
    assert page_text.inner_text().strip() == "Continuous View"


def test_diary_editor_word_counter_and_mood_pill(page, live_server):
    """Diary editor updates word & character counters dynamically and sets mood."""
    _login_user(page, live_server, "editor")
    page.goto(f"{live_server}/diaries/new")

    content_area = page.locator("#diaryContent")
    content_area.fill("The quick brown fox jumps over the lazy dog.")
    page.wait_for_timeout(200)

    # 9 words, 44 chars
    word_count_text = page.locator("#wordCount").inner_text()
    char_count_text = page.locator("#charCount").inner_text()
    assert "9 words" in word_count_text
    assert "44 chars" in char_count_text

    # Click excited mood pill
    excited_pill = page.locator('.mood-pill[data-mood="excited"]')
    excited_pill.click()
    page.wait_for_timeout(100)

    assert "selected" in (excited_pill.get_attribute("class") or "")
    mood_val = page.locator("#moodInput").get_attribute("value")
    assert mood_val == "excited"


def test_diary_editor_tag_pills_interactive(page, live_server):
    """Typing comma-separated tags updates the live tag pill preview badges."""
    _login_user(page, live_server, "tags")
    page.goto(f"{live_server}/diaries/new")

    page.fill("#tagsInput", "travel, adventure, memories")
    page.wait_for_timeout(200)

    preview = page.locator("#tagPillsPreview")
    badges = preview.locator(".tag-badge")
    assert badges.count() == 3
    assert "travel" in badges.nth(0).inner_text()
    assert "adventure" in badges.nth(1).inner_text()
    assert "memories" in badges.nth(2).inner_text()


def test_password_visibility_toggle(page, live_server):
    """Clicking the password toggle reveals and conceals the password text."""
    page.goto(f"{live_server}/login")
    pw_input = page.locator("#login-password")
    toggle_btn = page.locator(".password-wrap .toggle-pw")

    pw_input.fill("secretPassword123")
    assert pw_input.get_attribute("type") == "password"

    # Click eye icon to show password
    toggle_btn.click()
    assert pw_input.get_attribute("type") == "text"

    # Click again to hide password
    toggle_btn.click()
    assert pw_input.get_attribute("type") == "password"


def test_mobile_sidebar_drawer_toggle(page, live_server):
    """Mobile hamburger toggle opens and closes the navigation sidebar."""
    page.set_viewport_size({"width": 375, "height": 667})
    _login_user(page, live_server, "mobnav")

    page.goto(f"{live_server}/diaries")
    sidebar = page.locator("#appSidebar")
    toggle_btn = page.locator("#sidebarToggle")
    overlay = page.locator("#sidebarOverlay")
    close_btn = page.locator("#sidebarCloseBtn")

    assert toggle_btn.is_visible()
    assert "open" not in (sidebar.get_attribute("class") or "")

    # 1. Open sidebar and close via dedicated mobile close button
    toggle_btn.click()
    page.wait_for_timeout(200)
    assert "open" in (sidebar.get_attribute("class") or "")
    assert "open" in (overlay.get_attribute("class") or "")

    close_btn.click()
    page.wait_for_timeout(200)
    assert "open" not in (sidebar.get_attribute("class") or "")

    # 2. Open sidebar and close via backdrop click (tap outside drawer on exposed backdrop)
    toggle_btn.click()
    page.wait_for_timeout(200)
    assert "open" in (sidebar.get_attribute("class") or "")

    overlay.click(position={"x": 340, "y": 300})
    page.wait_for_timeout(200)
    assert "open" not in (sidebar.get_attribute("class") or "")


def test_theme_toggle_interactive(page, live_server):
    """Theme toggle updates the data-theme attribute on <html> dynamically."""
    page.goto(f"{live_server}/")
    html = page.locator("html")

    initial_theme = html.get_attribute("data-theme") or "light"
    expected_toggled = "dark" if initial_theme == "light" else "light"

    toggle_btn = page.locator(".theme-toggle").first
    toggle_btn.click()
    page.wait_for_timeout(200)

    new_theme = html.get_attribute("data-theme")
    assert new_theme == expected_toggled
