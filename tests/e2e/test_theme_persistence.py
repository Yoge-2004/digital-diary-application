"""Theme (dark/light) persistence bugs: staying in sync after a
bfcache-restored back-navigation, across tabs, and between the Settings
page's Light/Dark/Auto buttons and the sidebar's quick-toggle icon."""
from __future__ import annotations

from conftest import register_via_api


def test_theme_reapplies_on_bfcache_style_restore(page, live_server):
    """Regression guard for: change the theme on page B, hit the
    browser Back button to return to page A, page A still shows the old
    theme. That happens because Back very often restores a page from
    the back-forward cache instead of reloading it -- no script re-runs,
    so nothing re-reads localStorage. This simulates exactly that
    restore (a genuine 'pageshow' event with persisted=true) without
    depending on whether this specific browser/automation context
    performs a real bfcache restore for page.go_back()."""
    page.goto(f"{live_server}/login")
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "light"

    # Simulate the theme having changed elsewhere (another page, before
    # this one was cached) without this page's own JS re-running.
    page.evaluate("localStorage.setItem('dd-theme', 'dark')")
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "light", (
        "sanity check: changing localStorage alone must NOT retroactively repaint an "
        "already-rendered page -- that's not how this works, and if it did this test "
        "wouldn't be isolating what pageshow's persisted flag actually does"
    )

    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))")
    page.wait_for_timeout(100)
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"


def test_theme_syncs_across_tabs(page, live_server, context):
    """Same underlying bug, different trigger: two tabs open, theme
    changed in one, the other never hears about it. The `storage` event
    is the fix -- it fires in other tabs when localStorage changes."""
    tab2 = context.new_page()
    page.goto(f"{live_server}/login")
    tab2.goto(f"{live_server}/register")
    assert tab2.evaluate("document.documentElement.getAttribute('data-theme')") == "light"

    page.click(".theme-toggle")
    page.wait_for_timeout(200)
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"

    tab2.wait_for_timeout(300)
    assert tab2.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"
    tab2.close()


def test_settings_theme_buttons_sync_sidebar_toggle_icon(page, live_server):
    """Regression guard for: settings.html used to define its own local
    applyThemeBtn() that silently shadowed the real one in app.js
    (script load order meant it executed second and won) -- clicking
    Light/Dark/Auto there changed the page's actual colours but left the
    sidebar's quick-toggle icon/label showing the previous state until
    the next full page load."""
    import uuid
    username = f"themeicon{uuid.uuid4().hex[:10]}"
    register_via_api(page, live_server, username, f"{username}@example.com")
    page.goto(f"{live_server}/settings")
    page.click('.settings-tab[data-panel="appearance"]')

    page.click("#setDark")
    page.wait_for_timeout(200)
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"
    icon_class = page.eval_on_selector(".theme-toggle i", "el => el.className")
    assert "sun" in icon_class, f"sidebar toggle icon didn't sync to dark theme (got {icon_class!r})"

    page.click("#setLight")
    page.wait_for_timeout(200)
    icon_class = page.eval_on_selector(".theme-toggle i", "el => el.className")
    assert "moon" in icon_class, f"sidebar toggle icon didn't sync to light theme (got {icon_class!r})"


def test_skip_to_content_link_is_first_tab_stop_and_works(page, live_server):
    """Every page previously made a keyboard/screen-reader user tab
    through the entire sidebar nav before reaching page content. The
    skip link should be the very first tabbable element and should
    actually move focus to <main> when activated (a fragment link to a
    non-natively-focusable element like <main> only scrolls to it,
    doesn't focus it, unless the target has tabindex="-1")."""
    page.goto(live_server)
    page.keyboard.press("Tab")
    page.wait_for_timeout(150)
    assert page.evaluate("document.activeElement.className") == "skip-link"
    page.keyboard.press("Enter")
    page.wait_for_timeout(150)
    assert page.evaluate("document.activeElement.id") == "main-content"


def test_delete_account_modal_traps_focus(page, live_server):
    """Regression guard: Tab used to walk focus straight out of the
    open modal onto background page content (still focusable, just
    invisible behind the backdrop) after only 2 tabs -- a real
    WAI-ARIA dialog-pattern violation for a modal confirming an
    irreversible, destructive action."""
    import uuid
    username = f"focustrap{uuid.uuid4().hex[:10]}"
    register_via_api(page, live_server, username, f"{username}@example.com")
    page.goto(f"{live_server}/settings")
    page.click('.settings-tab[data-panel="danger"]')
    page.click("#openDeleteAccountModal")
    page.wait_for_timeout(200)

    for _ in range(12):
        page.keyboard.press("Tab")
        inside = page.evaluate(
            "document.getElementById('deleteAccountOverlay').contains(document.activeElement)"
        )
        assert inside, "focus escaped the open delete-account modal"
