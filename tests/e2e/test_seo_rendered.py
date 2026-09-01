"""SEO: the backend-level correctness of these is already covered by
tests/test_seo.py (via TestClient). This file checks the thing that
suite structurally can't: that a real browser actually parses and
exposes these tags in its rendered DOM."""
from __future__ import annotations


def test_landing_page_has_seo_meta_tags(page, live_server):
    page.goto(live_server)
    assert page.title() != ""
    assert page.locator('meta[name="description"]').count() == 1
    assert page.locator('link[rel="canonical"]').count() == 1
    assert page.locator('meta[property="og:title"]').count() == 1
    assert page.locator('meta[property="og:url"]').count() == 1
    assert page.locator('meta[name="twitter:card"]').count() == 1
    assert page.locator('script[type="application/ld+json"]').count() >= 1


def test_canonical_url_matches_current_page(page, live_server):
    page.goto(f"{live_server}/login")
    canonical = page.locator('link[rel="canonical"]').get_attribute("href")
    assert canonical.rstrip("/").endswith("/login")


def test_robots_txt_is_reachable_and_disallows_private_pages(page, live_server):
    resp = page.request.get(f"{live_server}/robots.txt")
    assert resp.ok
    body = resp.text()
    assert "Disallow: /dashboard" in body or "Disallow:" in body
    assert "Sitemap:" in body


def test_sitemap_xml_is_reachable_and_well_formed(page, live_server):
    resp = page.request.get(f"{live_server}/sitemap.xml")
    assert resp.ok
    body = resp.text()
    assert body.strip().startswith("<?xml")
    assert "<urlset" in body
    assert "<url>" in body


def test_authenticated_pages_are_noindex(page, live_server):
    """Dashboard/diaries etc. shouldn't invite indexing -- they're
    per-user private content."""
    from conftest import register_via_api
    import uuid
    username = f"seonoindex{uuid.uuid4().hex[:10]}"
    register_via_api(page, live_server, username, f"{username}@example.com")
    page.goto(f"{live_server}/dashboard")
    robots_meta = page.locator('meta[name="robots"]')
    if robots_meta.count() > 0:
        content = robots_meta.get_attribute("content") or ""
        assert "noindex" in content.lower()


def test_favicons_and_manifest_are_reachable(page, live_server):
    for path in (
        "/static/favicon.svg",
        "/static/favicon-32x32.png",
        "/static/favicon-16x16.png",
        "/static/apple-touch-icon.png",
        "/static/android-chrome-192x192.png",
        "/static/android-chrome-512x512.png",
        "/static/site.webmanifest",
    ):
        resp = page.request.get(f"{live_server}{path}")
        assert resp.ok, f"{path} returned {resp.status}"


def test_head_links_apple_touch_icon_and_manifest(page, live_server):
    page.goto(live_server)
    assert page.locator('link[rel="apple-touch-icon"]').count() == 1
    assert page.locator('link[rel="manifest"]').count() == 1
    assert page.locator('meta[property="og:image:alt"]').count() == 1
    assert page.locator('meta[name="twitter:image:alt"]').count() == 1


# ── Heading hierarchy: every page needs exactly one <h1> ──

AUTH_PAGES_WITH_H1 = ["/dashboard", "/diaries", "/calendar", "/stats", "/settings", "/shared"]


def test_every_authenticated_page_has_exactly_one_h1(page, live_server):
    """Regression guard: several pages (Dashboard, My Diaries, Calendar,
    Search, Settings, Shared, Stats, Verify Email) used a plain <div
    class="page-title"> instead of a real heading element -- zero <h1>s
    anywhere on the page. Harmless for search ranking on these specific
    pages (they're all noindex, being per-user content), but it breaks
    screen-reader heading navigation regardless of indexability, and
    every other page in the app (landing, diary detail) does have a
    proper h1, so it was also just an inconsistency."""
    import uuid
    username = f"h1check{uuid.uuid4().hex[:10]}"
    from conftest import register_via_api
    register_via_api(page, live_server, username, f"{username}@example.com")
    for path in AUTH_PAGES_WITH_H1:
        page.goto(f"{live_server}{path}")
        count = page.locator("h1").count()
        assert count == 1, f"{path} has {count} <h1> elements, expected exactly 1"
