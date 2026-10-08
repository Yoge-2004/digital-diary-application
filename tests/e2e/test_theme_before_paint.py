"""The saved theme must be on <html> before app.js (end of <body>) runs, otherwise a
navigation can paint -- and a cross-document view transition can snapshot -- the new
page in the default light theme and then switch it."""
from __future__ import annotations

import pytest


def _without_app_js(page):
    """Serve an empty app.js so the page is exactly what exists before any app JS ran."""
    page.route("**/static/js/app.js*", lambda r: r.fulfill(body="", content_type="application/javascript"))
    page.route("**/static/js/motion.js*", lambda r: r.fulfill(body="", content_type="application/javascript"))


@pytest.mark.parametrize("path", ["/login", "/register", "/"])
def test_saved_dark_theme_is_applied_without_any_app_js(browser, live_server, path):
    ctx = browser.new_context()
    ctx.add_init_script("localStorage.setItem('dd-theme', 'dark')")
    page = ctx.new_page()
    _without_app_js(page)
    page.goto(f"{live_server}{path}")
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "dark", (
        "theme is only applied by app.js: the page paints light first on every navigation"
    )
    meta = page.evaluate("document.querySelector('meta[name=theme-color]') && document.querySelector('meta[name=theme-color]').content")
    assert meta == "#0f0d17", f"browser chrome colour not set with the theme ({meta})"
    ctx.close()


def test_saved_light_theme_beats_a_dark_os_preference_without_app_js(browser, live_server):
    ctx = browser.new_context(color_scheme="dark")
    ctx.add_init_script("localStorage.setItem('dd-theme', 'light')")
    page = ctx.new_page()
    _without_app_js(page)
    page.goto(f"{live_server}/login")
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "light"
    ctx.close()


def test_no_saved_theme_follows_the_os_preference_without_app_js(browser, live_server):
    ctx = browser.new_context(color_scheme="dark")
    page = ctx.new_page()
    _without_app_js(page)
    page.goto(f"{live_server}/login")
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"
    ctx.close()
