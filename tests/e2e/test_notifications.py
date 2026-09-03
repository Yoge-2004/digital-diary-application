"""Daily reminder / notification settings UI.

Actually subscribing to Web Push requires the browser to reach a real
push service (Chrome uses Google's FCM) -- that's an external network
call this sandbox's egress rules don't allow (same restriction that
blocks Google Fonts and the Bootstrap Icons CDN elsewhere in this
suite). So instead of skipping this feature's UI entirely, these tests
stub navigator.serviceWorker.register and PushManager.subscribe with an
init script before the page loads, which lets everything downstream of
that -- permission request, the fetch calls to /api/push/subscribe and
/settings/notifications, the UI state update -- run for real and get
verified for real. Only the "does a real push service accept this
subscription" part is faked.
"""
from __future__ import annotations

import uuid

from conftest import register_via_api

VALID_VAPID_PUBLIC = "BCGCn-yeILV0uhDO8aZnbcxUm6NUWsz0wM_bYhnaE8R1XSFPovf-94ksfCVfuJGgtGKj0o1FanNT9eg_CYxuDgU"
VALID_VAPID_PRIVATE = "ixTDQ6Ph0wSAp7t4kkegB9bhvg45y2nQiK0kB2wk5dk"

_STUB_SCRIPT = """
(() => {
  const fakeSubscription = {
    endpoint: "https://fcm.example.test/fake-endpoint-" + Math.random().toString(36).slice(2),
    toJSON() {
      return { endpoint: this.endpoint, keys: { p256dh: "fake-p256dh-key", auth: "fake-auth-key" } };
    },
    unsubscribe() { return Promise.resolve(true); },
  };
  const fakePushManager = {
    _sub: null,
    getSubscription() { return Promise.resolve(this._sub); },
    subscribe() { this._sub = fakeSubscription; return Promise.resolve(fakeSubscription); },
  };
  const fakeRegistration = { pushManager: fakePushManager };
  const fakeServiceWorkerContainer = {
    register: () => Promise.resolve(fakeRegistration),
    getRegistration: () => Promise.resolve(fakeRegistration),
    ready: Promise.resolve(fakeRegistration),
  };
  // navigator.serviceWorker is a native getter-only property on real
  // browsers -- plain assignment (navigator.serviceWorker = ...) silently
  // no-ops instead of throwing, which looks like it worked but leaves the
  // real ServiceWorkerContainer in place underneath (and its PushManager
  // needs a real push service, unreachable from this sandbox).
  // defineProperty actually replaces it.
  Object.defineProperty(navigator, 'serviceWorker', { value: fakeServiceWorkerContainer, configurable: true });
  // Playwright's context.grant_permissions() updates the Permissions API
  // (navigator.permissions.query) but not the legacy, synchronous
  // Notification.permission getter in headless Chromium -- a documented
  // tool limitation, not something real browsers do (there it's always
  // in sync). Stubbing it directly here is the correct fix for that gap
  // rather than changing production code to work around a test-only quirk.
  Object.defineProperty(Notification, 'permission', { get: () => 'granted', configurable: true });
  window.__fakePushManager = fakePushManager;
})();
"""


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def test_notifications_tab_absent_when_push_not_configured(page, live_server):
    username = _uniq("nopush")
    register_via_api(page, live_server, username, f"{username}@example.com")
    page.goto(f"{live_server}/settings")
    assert page.locator('.settings-tab[data-panel="notifications"]').count() == 0
    assert page.locator("#reminderToggle").count() == 0


def test_notifications_tab_present_when_push_configured(page, live_server_factory):
    url = live_server_factory(vapid_public_key=VALID_VAPID_PUBLIC, vapid_private_key=VALID_VAPID_PRIVATE)
    username = _uniq("haspush")
    register_via_api(page, url, username, f"{username}@example.com")
    page.goto(f"{url}/settings")
    assert page.locator('.settings-tab[data-panel="notifications"]').count() == 1
    page.click('.settings-tab[data-panel="notifications"]')
    assert page.locator("#reminderToggle").is_visible()
    assert page.locator("#reminderTime").is_visible()


def test_toggle_on_subscribes_and_saves_preferences(page, live_server_factory):
    url = live_server_factory(vapid_public_key=VALID_VAPID_PUBLIC, vapid_private_key=VALID_VAPID_PRIVATE)
    page.context.grant_permissions(["notifications"])
    page.add_init_script(_STUB_SCRIPT)

    username = _uniq("toggleon")
    register_via_api(page, url, username, f"{username}@example.com")
    page.goto(f"{url}/settings")
    page.click('.settings-tab[data-panel="notifications"]')

    with page.expect_response(lambda r: "/api/push/subscribe" in r.url) as subscribe_resp_info:
        with page.expect_response(lambda r: "/settings/notifications" in r.url) as save_resp_info:
            page.click("#reminderToggle")

    assert subscribe_resp_info.value.ok
    # /settings/notifications is a traditional web-form POST route (like
    # every other /settings/* route in this app) -- it redirects back to
    # /settings on success, so a 302/303 here is the *correct* outcome,
    # not a failure. .ok only covers 200-299.
    assert save_resp_info.value.status in (302, 303)
    page.wait_for_timeout(200)
    assert page.locator("#reminderStatusText").inner_text() == "On"
    assert page.locator("#reminderTime").is_enabled()

    # Now that it's on, change the time -- this should trigger its own save.
    page.fill("#reminderTime", "21:15")
    with page.expect_response(lambda r: "/settings/notifications" in r.url):
        page.locator("#reminderTime").dispatch_event("change")

    # Reload for real and confirm the DB actually persisted it, not just the UI.
    page.goto(f"{url}/settings")
    page.click('.settings-tab[data-panel="notifications"]')
    assert page.locator("#reminderToggle").is_checked()
    assert page.locator("#reminderTime").input_value() == "21:15"


def test_toggle_off_unsubscribes_and_saves_preferences(page, live_server_factory):
    url = live_server_factory(vapid_public_key=VALID_VAPID_PUBLIC, vapid_private_key=VALID_VAPID_PRIVATE)
    page.context.grant_permissions(["notifications"])
    page.add_init_script(_STUB_SCRIPT)

    username = _uniq("toggleoff")
    register_via_api(page, url, username, f"{username}@example.com")
    page.goto(f"{url}/settings")
    page.click('.settings-tab[data-panel="notifications"]')
    page.click("#reminderToggle")  # turn on first
    page.wait_for_timeout(300)
    assert page.locator("#reminderToggle").is_checked()

    with page.expect_response(lambda r: "/api/push/unsubscribe" in r.url) as unsub_info:
        page.click("#reminderToggle")  # now turn off
    assert unsub_info.value.ok
    page.wait_for_timeout(200)
    assert page.locator("#reminderStatusText").inner_text() == "Off"
    assert page.locator("#reminderTime").is_disabled()

    page.goto(f"{url}/settings")
    page.click('.settings-tab[data-panel="notifications"]')
    assert not page.locator("#reminderToggle").is_checked()


def test_denied_permission_shows_note_and_reverts_toggle(page, live_server_factory):
    url = live_server_factory(vapid_public_key=VALID_VAPID_PUBLIC, vapid_private_key=VALID_VAPID_PRIVATE)
    page.context.grant_permissions([])  # explicitly no notifications permission
    page.add_init_script(
        _STUB_SCRIPT + "\nObject.defineProperty(Notification, 'permission', { get: () => 'denied', configurable: true });"
    )

    username = _uniq("denied")
    register_via_api(page, url, username, f"{username}@example.com")
    page.goto(f"{url}/settings")
    page.click('.settings-tab[data-panel="notifications"]')
    page.click("#reminderToggle")
    page.wait_for_timeout(300)

    assert page.locator("#reminderPermissionNote").is_visible()
    assert not page.locator("#reminderToggle").is_checked()


def test_sw_js_is_reachable(page, live_server_factory):
    url = live_server_factory(vapid_public_key=VALID_VAPID_PUBLIC, vapid_private_key=VALID_VAPID_PRIVATE)
    resp = page.request.get(f"{url}/sw.js")
    assert resp.ok
    assert "application/javascript" in resp.headers.get("content-type", "")
    body = resp.text()
    assert "addEventListener(\"push\"" in body
    assert "addEventListener(\"notificationclick\"" in body
