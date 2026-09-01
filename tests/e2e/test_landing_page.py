"""Landing page: renders, no horizontal scrollbar at any width (this is
the regression guard for the "gap on left/right in all devices" and the
diary-card horizontal-scrollbar bugs — see conftest.assert_no_horizontal_overflow)."""
from __future__ import annotations

import pytest

from conftest import assert_no_horizontal_overflow

WIDTHS = [360, 390, 768, 1024, 1440, 1920, 2560]


@pytest.mark.parametrize("width", WIDTHS)
def test_landing_page_no_horizontal_overflow(page, live_server, width):
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(live_server)
    assert_no_horizontal_overflow(page, context=f"landing page at {width}px")


def test_landing_page_hero_and_ctas_render(page, live_server):
    page.goto(live_server)
    assert page.locator(".landing-hero").is_visible()
    # The hero background should reach the true edge now (full-bleed
    # fix) -- assert its rendered box actually spans the viewport,
    # not just that the element exists.
    hero_box = page.locator(".landing-hero").bounding_box()
    viewport = page.viewport_size
    assert hero_box["x"] <= 1
    assert hero_box["width"] >= viewport["width"] - 1

    # Primary CTAs are present and point where they should
    assert page.locator('a[href="/register"]').first.is_visible()
    assert page.locator('a[href="/login"]').first.is_visible()


def test_landing_features_grid_renders(page, live_server):
    page.goto(live_server)
    cards = page.locator(".features-grid .card")
    assert cards.count() >= 4


def test_landing_get_started_cta_navigates_to_register(page, live_server):
    page.goto(live_server)
    page.locator('a[href="/register"]').first.click()
    page.wait_for_url(f"{live_server}/register")
    assert page.locator("#registerForm").is_visible()
