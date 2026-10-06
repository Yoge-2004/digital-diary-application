"""End-to-end responsiveness and device-size compatibility tests.

Validates that all application routes, layout components, navigation drawers,
and modals properly adapt without horizontal scrollbars, layout breakage,
or accessibility issues across small mobile (320px), standard mobile (375-430px),
tablets (768-1024px), desktop (1280-1440px), and ultrawide/4K (1920-2560px).
"""
from __future__ import annotations

import uuid
import pytest
from conftest import assert_no_horizontal_overflow, register_via_api

DEVICE_VIEWPORTS = [
    {"name": "iPhone SE 1st gen (compact mobile)", "width": 320, "height": 568},
    {"name": "Standard Android (compact mobile)", "width": 360, "height": 640},
    {"name": "iPhone SE 2nd/3rd gen", "width": 375, "height": 667},
    {"name": "iPhone 12/13/14 base", "width": 390, "height": 844},
    {"name": "Pixel 7 / Galaxy S20", "width": 412, "height": 915},
    {"name": "iPhone Pro Max", "width": 430, "height": 932},
    {"name": "Mobile Landscape / Phablet", "width": 640, "height": 800},
    {"name": "iPad Portrait / Tablet", "width": 768, "height": 1024},
    {"name": "iPad Pro 11in", "width": 834, "height": 1194},
    {"name": "iPad Landscape / Small Laptop", "width": 1024, "height": 768},
    {"name": "Standard Laptop", "width": 1280, "height": 800},
    {"name": "Desktop 1440p", "width": 1440, "height": 900},
    {"name": "Full HD Desktop", "width": 1920, "height": 1080},
    {"name": "4K / Ultrawide Display", "width": 2560, "height": 1440},
]


def test_responsive_layout_sweep_across_all_devices(page, live_server):
    """Audit all primary pages across 14 device sizes for horizontal overflow."""
    uid = uuid.uuid4().hex[:8]
    username = f"respuser_{uid}"
    register_via_api(page, live_server, username, f"{username}@example.com")

    # Create a diary entry with tags, location, and long content to test rich layouts
    resp = page.request.post(
        f"{live_server}/api/diaries",
        data={
            "title": "A Responsive Journey in Zurich with Long Title to Test Text Wrapping",
            "content": "Exploring the city streets, architecture, and scenic views. " * 8,
            "mood": "calm",
            "tags": ["travel", "design", "responsive"],
            "location": "Zurich, Switzerland",
            "visibility": "private"
        },
        headers={"Content-Type": "application/json"}
    )
    assert resp.ok, resp.text()
    diary_id = resp.json()["id"]

    pages_to_test = [
        ("/", "Landing"),
        ("/login", "Sign In"),
        ("/register", "Registration"),
        ("/forgot-password", "Forgot Password"),
        ("/dashboard", "Dashboard"),
        ("/diaries", "Diaries List"),
        ("/diaries/new", "New Diary Form"),
        (f"/diaries/{diary_id}", "Diary Detail"),
        (f"/diaries/{diary_id}/edit", "Diary Edit"),
        ("/calendar", "Calendar"),
        ("/stats", "Statistics"),
        ("/search", "Search"),
        ("/settings", "Settings"),
        ("/shared", "Shared Stories"),
    ]

    failures = []
    for vp in DEVICE_VIEWPORTS:
        w, h = vp["width"], vp["height"]
        page.set_viewport_size({"width": w, "height": h})

        for path, label in pages_to_test:
            page.goto(f"{live_server}{path}")
            page.wait_for_timeout(50)
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            if overflow > 1:
                failures.append(f"{label} ({path}) at {w}x{h}: {overflow}px overflow")

    assert not failures, "Horizontal overflow detected:\n" + "\n".join(failures)


@pytest.mark.parametrize("width", [320, 375, 640, 768, 1024, 1440])
def test_sidebar_drawer_behavior_by_device_width(page, live_server, width):
    """Test mobile drawer toggle vs desktop static sidebar across breakpoints."""
    uid = uuid.uuid4().hex[:8]
    username = f"nav_{uid}"
    register_via_api(page, live_server, username, f"{username}@example.com")

    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{live_server}/dashboard")
    page.wait_for_timeout(100)

    toggle = page.locator("#sidebarToggle")
    sidebar = page.locator("#appSidebar")
    overlay = page.locator("#sidebarOverlay")

    if width < 1024:
        # On mobile/tablet, toggle is visible and sidebar is initially off-screen
        assert toggle.is_visible(), f"Sidebar toggle should be visible at {width}px"
        box = sidebar.bounding_box()
        assert (box["x"] + box["width"]) <= 1, f"Sidebar should be off-screen at {width}px"

        # Clicking toggle opens sidebar drawer
        toggle.click()
        page.wait_for_timeout(500)
        open_box = sidebar.bounding_box()
        # An eased slide approaches 0 asymptotically: under a loaded suite run it
        # read -0.0013px at 500ms, so allow sub-pixel slack rather than exactly 0.
        assert open_box["x"] >= -1, f"Sidebar should be visible when opened at {width}px"
        assert overlay.is_visible(), f"Overlay should be visible when sidebar is open at {width}px"

        # Clicking backdrop closes sidebar
        overlay.click(position={"x": max(width - 20, 270) if width > 280 else width - 10, "y": 200})
        page.wait_for_timeout(500)
        closed_box = sidebar.bounding_box()
        assert (closed_box["x"] + closed_box["width"]) <= 1, f"Sidebar should close after backdrop tap at {width}px"
    else:
        # On desktop, sidebar is permanently visible and toggle is hidden
        assert not toggle.is_visible(), f"Sidebar toggle should be hidden at {width}px"
        box = sidebar.bounding_box()
        assert box["x"] >= 0 and sidebar.is_visible(), f"Sidebar should be static and visible at {width}px"


@pytest.mark.parametrize("width", [320, 375, 768, 1440])
def test_modal_adaptation_across_devices(page, live_server, width):
    """Test that modal dialogs remain completely contained within any screen size."""
    uid = uuid.uuid4().hex[:8]
    username = f"modal_{uid}"
    register_via_api(page, live_server, username, f"{username}@example.com")

    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{live_server}/settings")
    page.click('.settings-tab[data-panel="danger"]')
    page.click("#openDeleteAccountModal")
    page.wait_for_timeout(200)

    overlay = page.locator("#deleteAccountOverlay")
    assert overlay.is_visible()

    panel_box = page.locator(".modal-panel").bounding_box()
    assert panel_box["x"] >= 0, f"Modal panel overflows left at {width}px"
    assert (panel_box["x"] + panel_box["width"]) <= width, f"Modal panel overflows right at {width}px"

    page.click("#cancelDeleteAccount")
    page.wait_for_timeout(200)
    assert not overlay.is_visible()
