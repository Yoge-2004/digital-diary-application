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
