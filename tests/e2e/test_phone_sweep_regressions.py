"""Regression guards for what a phone-viewport axe sweep found in states the
earlier (desktop, mostly-static) sweeps never reached: the delete-account
modal, the write/edit page, a non-image attachment in dark theme, and the
attachment upload zone.

Contrast is measured on the real element with opacity and translucent
backgrounds composited, because two of these bugs were exactly that: a
token that passes on its own, blended into something that doesn't.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import register_via_api

PHONE = {"width": 390, "height": 844}

# Effective contrast of an element's text against what is actually behind it.
CONTRAST_JS = """(el) => {
  const parse = (c) => { const m = c.match(/[\\d.]+/g).map(Number); return { r: m[0], g: m[1], b: m[2], a: m[3] === undefined ? 1 : m[3] }; };
  const over = (top, under) => ({ r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a),
                                   b: top.b * top.a + under.b * (1 - top.a), a: 1 });
  const chain = []; for (let n = el; n; n = n.parentElement) chain.unshift(n);
  let bg = { r: 255, g: 255, b: 255, a: 1 }, opacity = 1;
  for (const n of chain) { const s = getComputedStyle(n); bg = over(parse(s.backgroundColor), bg); opacity *= parseFloat(s.opacity); }
  const fg = over({ ...parse(getComputedStyle(el).color), a: parse(getComputedStyle(el).color).a * opacity }, bg);
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
                       return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const [hi, lo] = [lum(fg), lum(bg)].sort((x, y) => y - x);
  return { ratio: (hi + 0.05) / (lo + 0.05), opacity };
}"""


def _signup(page, base_url: str) -> None:
    u = f"sw{uuid.uuid4().hex[:8]}"
    register_via_api(page, base_url, u, f"{u}@example.com")


def _entry(page, base_url: str) -> str:
    r = page.request.post(
        f"{base_url}/api/diaries",
        data={"title": "Memo", "content": "Some words for the diary.", "mood": "happy", "visibility": "private"},
    )
    assert r.ok, r.text()
    return r.json()["id"]


def _contrast(page, selector: str) -> dict:
    return page.eval_on_selector(selector, CONTRAST_JS)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_delete_account_confirm_word_is_readable(page, live_server, theme):
    """The word DELETE in the confirm label was --clr-danger text: 4.39:1 on
    white, 4.06:1 on the dark surface."""
    page.add_init_script(f"localStorage.setItem('dd-theme', '{theme}')")
    page.set_viewport_size(PHONE)
    _signup(page, live_server)
    page.goto(f"{live_server}/settings")
    page.click('.settings-tab[data-panel="danger"]')  # the button lives in the Danger tab
    page.click("#openDeleteAccountModal")
    page.wait_for_selector("#deleteAccountOverlay", state="visible")
    page.wait_for_timeout(600)  # modal entrance animation
    got = _contrast(page, ".modal-confirm-label strong")
    assert got["ratio"] >= 4.5, f"{theme}: {got['ratio']:.2f}:1"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_danger_text_token_meets_contrast_on_every_surface(page, live_server, theme):
    """.form-feedback.invalid and .btn-outline-danger set text to this token
    in states a static sweep doesn't reach (validation errors)."""
    page.add_init_script(f"localStorage.setItem('dd-theme', '{theme}')")
    page.goto(f"{live_server}/login")
    got = page.evaluate(
        """() => { const out = {};
          for (const [k, cls, prop] of [['fb', 'form-feedback invalid', 'color'], ['btn', 'btn btn-outline-danger', 'color']]) {
            const e = document.createElement('div'); e.className = cls; e.textContent = 'x'; document.body.appendChild(e);
            out[k] = getComputedStyle(e)[prop]; e.remove(); }
          for (const v of ['--bg-body', '--bg-surface', '--bg-surface-2']) {
            const e = document.createElement('div'); e.style.backgroundColor = `var(${v})`; document.body.appendChild(e);
            out[v] = getComputedStyle(e).backgroundColor; e.remove(); }
          return out; }"""
    )
    rgb = lambda c: tuple(int(float(x)) for x in __import__("re").findall(r"[\d.]+", c)[:3])

    def lum(c):
        f = lambda v: (v / 255 / 12.92) if v / 255 <= 0.03928 else ((v / 255 + 0.055) / 1.055) ** 2.4
        r, g, b = map(f, c)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    for key in ("fb", "btn"):
        for surf in ("--bg-body", "--bg-surface", "--bg-surface-2"):
            hi, lo = sorted((lum(rgb(got[key])), lum(rgb(got[surf]))), reverse=True)
            ratio = (hi + 0.05) / (lo + 0.05)
            assert ratio >= 4.5, f"{theme}: {key} text {got[key]} on {surf} {got[surf]} is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("path", ["/diaries/new", "edit"])
def test_autosave_indicator_is_readable(page, live_server, theme, path):
    """Inline opacity:.7 on muted text measured 2.70:1 (light) / 3.09:1 (dark)."""
    page.add_init_script(f"localStorage.setItem('dd-theme', '{theme}')")
    page.set_viewport_size(PHONE)
    _signup(page, live_server)
    url = f"{live_server}/diaries/new" if path == "/diaries/new" else f"{live_server}/diaries/{_entry(page, live_server)}/edit"
    page.goto(url)
    page.wait_for_selector("#autosaveIndicator")
    page.wait_for_timeout(600)
    got = _contrast(page, "#autosaveIndicator")
    assert got["ratio"] >= 4.5, f"{theme} {path}: {got['ratio']:.2f}:1 (opacity {got['opacity']})"


def test_paperclip_card_size_text_is_readable_in_dark_theme(page, live_server):
    """The card is fixed pale yellow in both themes; its size line used the
    theme's light-grey --txt-muted: 3.20:1 in dark."""
    page.add_init_script("localStorage.setItem('dd-theme', 'dark')")
    page.set_viewport_size(PHONE)
    _signup(page, live_server)
    diary_id = _entry(page, live_server)
    r = page.request.post(
        f"{live_server}/api/diaries/{diary_id}/attachments",
        multipart={"file": {"name": "notes.txt", "mimeType": "text/plain", "buffer": b"hello"}},
    )
    assert r.ok, r.text()
    page.goto(f"{live_server}/diaries/{diary_id}")
    page.wait_for_selector(".journal-paperclip-card")
    page.wait_for_timeout(600)
    got = _contrast(page, ".journal-paperclip-card > div:nth-child(3)")
    assert got["ratio"] >= 4.5, f"{got['ratio']:.2f}:1"


def test_upload_zone_can_be_operated_from_the_keyboard(page, live_server):
    """The zone was role=button + tabindex=0 with no key handler (Enter and
    Space did nothing) and it contained a second focusable button, so axe
    flagged nested-interactive. The real button is now the keyboard control
    and, with no file chosen yet, opens the file picker."""
    _signup(page, live_server)
    diary_id = _entry(page, live_server)
    page.goto(f"{live_server}/diaries/{diary_id}")
    zone = page.locator("#uploadZone")
    assert zone.get_attribute("role") != "button", "a role=button zone can't contain the Upload button"
    assert zone.get_attribute("tabindex") is None, "zone must not be a second tab stop"
    page.focus("#uploadBtn")
    with page.expect_file_chooser(timeout=3000):
        page.keyboard.press("Enter")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_delete_account_card_in_the_danger_tab_is_readable(page, live_server, theme):
    """axe skips hidden panels, so the Danger tab was never swept: the heading
    was --clr-danger text (4.14:1) and the button white on it (4.39:1)."""
    page.add_init_script(f"localStorage.setItem('dd-theme', '{theme}')")
    page.set_viewport_size(PHONE)
    _signup(page, live_server)
    page.goto(f"{live_server}/settings")
    page.click('.settings-tab[data-panel="danger"]')
    page.wait_for_timeout(600)
    for selector in (".danger-zone > h2", "#openDeleteAccountModal"):
        got = _contrast(page, selector)
        assert got["ratio"] >= 4.5, f"{theme} {selector}: {got['ratio']:.2f}:1"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_password_strength_label_and_requirements_are_readable(page, live_server, theme):
    """Label colours came from the bar's fill palette (3.29:1 for 'weak');
    a met requirement was --clr-sage text (3.87:1). Type passwords that hit
    each strength level and check what is actually shown."""
    page.add_init_script(f"localStorage.setItem('dd-theme', '{theme}')")
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server}/register")
    seen = set()
    for pw in ("a", "abcdefgh", "Abcdefg1", "Abcdefg1!xyz-long"):
        page.fill("#reg-password", pw)
        page.wait_for_timeout(500)
        if page.inner_text("#pwStrengthLabel").strip():
            seen.add(page.get_attribute("#pwStrengthLabel", "data-strength"))
            got = _contrast(page, "#pwStrengthLabel")
            assert got["ratio"] >= 4.5, f"{theme} label for {pw!r}: {got['ratio']:.2f}:1"
        got = _contrast(page, "#req-lower")
        assert got["ratio"] >= 4.5, f"{theme} requirement for {pw!r}: {got['ratio']:.2f}:1"
    assert len(seen) >= 3, f"fixture should reach several strength levels, got {seen}"


def test_calendar_days_with_entries_are_readable_in_dark_theme(page, live_server):
    """--accent-text passes on dark surfaces but was drawn on the lighter accent
    tint of a day with entries: 4.25:1."""
    page.add_init_script("localStorage.setItem('dd-theme', 'dark')")
    page.set_viewport_size(PHONE)
    _signup(page, live_server)
    _entry(page, live_server)
    page.goto(f"{live_server}/calendar")
    page.wait_for_selector(".cal-day.has-entries")
    page.wait_for_timeout(600)
    got = _contrast(page, ".cal-day.has-entries")
    assert got["ratio"] >= 4.5, f"{got['ratio']:.2f}:1"


def test_calendar_day_under_the_pointer_is_readable_in_dark_theme(page, live_server):
    """:hover paints --accent-text on the accent tint, same 4.25:1 as a day
    with entries. Found because the sweep's pointer happened to rest on a cell."""
    page.add_init_script("localStorage.setItem('dd-theme', 'dark')")
    page.set_viewport_size(PHONE)
    _signup(page, live_server)
    page.goto(f"{live_server}/calendar")
    cell = page.locator(".cal-day:not(.empty):not(.has-entries):not(.today)").first
    cell.hover()
    page.wait_for_timeout(600)  # transition: all
    ratio = cell.evaluate(CONTRAST_JS)["ratio"]
    assert ratio >= 4.5, f"{ratio:.2f}:1"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_forgot_password_footer_links_do_not_rely_on_colour_alone(page, live_server_factory, theme):
    """Inline links in running text need an underline (WCAG 1.4.1); in dark
    theme the link colour was 2.7:1 against the muted sentence around it."""
    base = live_server_factory(smtp_host="smtp.example.invalid", smtp_from="diary@example.invalid")
    page.add_init_script(f"localStorage.setItem('dd-theme', '{theme}')")
    page.goto(f"{base}/forgot-password")
    for href in ("/login", "/register"):
        deco = page.eval_on_selector(f'.inline-links a[href="{href}"]', "e => getComputedStyle(e).textDecorationLine")
        assert "underline" in deco, f"{href} link is not underlined ({deco})"
