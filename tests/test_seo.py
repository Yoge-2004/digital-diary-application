from __future__ import annotations

from tests.test_security_and_features import build_client, api_register


def test_robots_txt_served_and_disallows_private_pages():
    client, tmp = build_client()
    with client, tmp:
        resp = client.get("/robots.txt")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        body = resp.text
        assert "Allow: /$" in body
        assert "Disallow: /dashboard" in body
        assert "Disallow: /diaries" in body
        assert "Disallow: /api/" in body
        assert "Sitemap:" in body
        assert "sitemap.xml" in body


def test_sitemap_xml_only_lists_public_pages():
    client, tmp = build_client()
    with client, tmp:
        resp = client.get("/sitemap.xml")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/xml")
        body = resp.text
        assert "<urlset" in body
        assert "/login</loc>" in body
        assert "/register</loc>" in body
        # No private/per-user pages should ever appear here.
        assert "/dashboard" not in body
        assert "/diaries" not in body


def test_landing_page_is_indexable():
    client, tmp = build_client()
    with client, tmp:
        resp = client.get("/")
        assert 'content="index, follow"' in resp.text
        assert 'rel="canonical"' in resp.text
        assert "application/ld+json" in resp.text


def test_login_and_register_pages_are_indexable():
    client, tmp = build_client()
    with client, tmp:
        for path in ("/login", "/register"):
            resp = client.get(path)
            assert 'content="index, follow"' in resp.text


def test_authenticated_pages_are_noindex():
    """Every page that only makes sense for a logged-in, specific user
    (dashboard, diary list, settings, ...) must never be indexed."""
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        # api_register logs in via API cookies; also log in through the
        # web form so page-rendering routes see the session cookie.
        client.post("/login", data={
            "username": "alice", "password": "Password123!",
            "csrf_token": client.get("/login").cookies.get("csrf_token") or "x",
        })

        for path in ["/dashboard", "/diaries", "/calendar", "/stats", "/settings", "/search", "/shared", "/verify-email"]:
            resp = client.get(path)
            assert 'content="noindex, nofollow, noarchive"' in resp.text, f"{path} should be noindex"


def test_diary_entry_page_has_article_open_graph_tags():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        client.post("/login", data={
            "username": "alice", "password": "Password123!",
            "csrf_token": client.get("/login").cookies.get("csrf_token") or "x",
        })
        create = client.post("/api/diaries", json={
            "title": "My Entry", "content": "Some real content for the meta description to draw from.",
        })
        diary_id = create.json()["id"]

        resp = client.get(f"/diaries/{diary_id}")
        assert 'property="og:type" content="article"' in resp.text
        assert "article:published_time" in resp.text
        assert 'content="noindex, nofollow, noarchive"' in resp.text  # still private regardless of content type


def test_canonical_url_strips_flash_message_params_but_keeps_real_query_params():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        client.post("/login", data={
            "username": "alice", "password": "Password123!",
            "csrf_token": client.get("/login").cookies.get("csrf_token") or "x",
        })

        resp = client.get("/dashboard?msg=Entry+created")
        # The canonical tag should not carry our own transient flash param.
        assert "?msg=" not in resp.text.split('rel="canonical"')[1][:200]

        resp2 = client.get("/diaries?favorite=true")
        # But a real content-affecting query param should be preserved.
        assert 'href="http://testserver/diaries?favorite=true"' in resp2.text


def test_every_page_has_a_favicon_link():
    client, tmp = build_client()
    with client, tmp:
        for path in ["/", "/login", "/register", "/forgot-password"]:
            resp = client.get(path)
            assert 'rel="icon"' in resp.text, f"{path} is missing a favicon link"
