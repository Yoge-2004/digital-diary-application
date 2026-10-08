from __future__ import annotations

from tests.test_security_and_features import build_client


def test_unknown_page_gets_a_real_responsive_404_page():
    """Browsers used to get the raw JSON {"detail":"Not Found"}: no viewport tag, so phones laid it out
    at 980px wide and shrank it."""
    client, tmp = build_client()
    with client, tmp:
        resp = client.get("/no-such-page", headers={"accept": "text/html"})
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("text/html")
        assert 'name="viewport"' in resp.text and "width=device-width" in resp.text
        assert "Page not found" in resp.text
        assert 'href="/"' in resp.text
        assert 'noindex' in resp.text, "error pages should not be indexed"


def test_api_and_static_404s_keep_their_default_responses():
    client, tmp = build_client()
    with client, tmp:
        api = client.get("/api/no-such-endpoint")
        assert api.status_code == 404
        assert api.headers["content-type"].startswith("application/json")
        assert api.json() == {"detail": "Not Found"}
        static = client.get("/static/no-such-file.png")
        assert static.status_code == 404
        assert "Page not found" not in static.text


def test_other_http_errors_are_unchanged():
    client, tmp = build_client()
    with client, tmp:
        # an unauthenticated API call is still the API's own 401 JSON
        resp = client.get("/api/diaries")
        assert resp.status_code in (401, 403)
        assert resp.headers["content-type"].startswith("application/json")
