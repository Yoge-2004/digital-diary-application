"""Regression guards for visual bugs that no unit test can see.

Each test asserts an *outcome* measured in a real browser (where a letter
sits relative to its ruled line, whether a page of text is clipped, what
contrast a filename has against its card) rather than "some JS ran" --
the older ruled-line tests only checked that --rule-offset fell in a
plausible 0-60px range, which the original 13px-off value also satisfied.
"""
from __future__ import annotations

import re
import uuid

import pytest

from conftest import register_via_api

PARAGRAPHS = [
    "Woke up early today and walked down to the river before the town was properly awake. "
    "The mist was still sitting low on the water and everything felt quiet and unhurried.",
    "Later I met Priya for coffee and we talked for almost three hours about nothing in particular: "
    "books we keep meaning to read, the trip we keep meaning to take, and whether it is too late to learn the cello.",
    "In the evening I rewrote the same paragraph of my letter five times and still hated it. "
    "Sometimes the words simply refuse to line up, and the only thing to do is put the pen down.",
    "Anyway. Small good things today: the river, the coffee, and the smell of rain arriving "
    "a full minute before the rain did.",
]
LONG_TEXT = "\n\n".join(PARAGRAPHS * 3)

DESKTOP = (1280, 720)
PHONE = (390, 844)


def _signup(page, base_url: str, prefix: str = "vis") -> str:
    username = f"{prefix}{uuid.uuid4().hex[:8]}"
    register_via_api(page, base_url, username, f"{username}@example.com")
    return username


def _make_entry(page, base_url: str, content: str, title: str = "A quiet morning") -> str:
    r = page.request.post(
        f"{base_url}/api/diaries",
        data={"title": title, "content": content, "mood": "happy", "visibility": "private"},
    )
    assert r.ok, r.text()
    return r.json()["id"]


def _open_entry(page, base_url: str, diary_id: str, size=DESKTOP) -> None:
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(f"{base_url}/diaries/{diary_id}")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(400)  # initRuledLineAlignment / pagination settle


# Distance in px from each text line's baseline down to the top of the ruled
# line that sits under it. Works for the reading article (via a Range over
# the real text) and for a textarea (via an identically-styled mirror div,
# since a textarea's lines can't be queried). Rule k's bottom edge is at
# backgroundPositionY + k * lineHeight and the line is the last 1px of it.
RULE_GAPS_JS = """
(sel) => {
  const el = document.querySelector(sel);
  const cs = getComputedStyle(el);
  const fs = parseFloat(cs.fontSize), lh = parseFloat(cs.lineHeight);
  const ctx = document.createElement('canvas').getContext('2d');
  ctx.font = `${cs.fontStyle} ${cs.fontWeight} ${fs}px ${cs.fontFamily}`;
  const ascent = ctx.measureText('Hg').fontBoundingBoxAscent;
  const pos = parseFloat(cs.backgroundPositionY.split(',').pop());
  let node, originTop, mirror = null;
  if (el.tagName === 'TEXTAREA') {
    mirror = document.createElement('div');
    Object.assign(mirror.style, {
      position: 'absolute', visibility: 'hidden', left: '0', top: '0', boxSizing: 'border-box',
      width: el.clientWidth + 'px', padding: cs.padding, fontFamily: cs.fontFamily, fontSize: cs.fontSize,
      fontWeight: cs.fontWeight, fontStyle: cs.fontStyle, lineHeight: cs.lineHeight,
      letterSpacing: cs.letterSpacing, whiteSpace: 'pre-wrap', overflowWrap: 'break-word',
    });
    mirror.textContent = el.value;
    document.body.appendChild(mirror);
    node = mirror.firstChild; originTop = mirror.getBoundingClientRect().top;
  } else {
    const raw = el.querySelector('#diaryContentRaw') || el;
    node = raw.firstChild;
    originTop = el.getBoundingClientRect().top + (parseFloat(cs.borderTopWidth) || 0);
  }
  const lines = new Map(), r = document.createRange();
  for (let i = 0; i < node.length; i++) {
    r.setStart(node, i); r.setEnd(node, i + 1);
    const q = r.getClientRects()[0]; if (!q || !q.width) continue;
    const k = Math.round(q.top); if (!lines.has(k)) lines.set(k, q.top);
  }
  if (mirror) mirror.remove();
  return [...lines.values()].sort((a, b) => a - b).map((top) => {
    const baseline = top - originTop + ascent;
    const n = Math.round((baseline + 1 - pos) / lh);
    return +((pos + n * lh - 1) - baseline).toFixed(2);
  });
}
"""


@pytest.mark.parametrize("size", [DESKTOP, PHONE], ids=["desktop", "phone"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_ruled_lines_sit_under_the_text_on_the_view_page(page, live_server, size, theme):
    """The bug: --rule-offset ignored the article's padding-top, so every
    ruled line landed ~13px too high and cut through the lettering. Gap
    is baseline -> top of the rule beneath it; ~1px when it's right."""
    page.add_init_script(f"localStorage.setItem('dd-theme', '{theme}')")
    _signup(page, live_server)
    _open_entry(page, live_server, _make_entry(page, live_server, LONG_TEXT), size)
    gaps = page.evaluate(RULE_GAPS_JS, "#diaryReading")
    assert len(gaps) >= 6, gaps
    assert all(-1.5 <= g <= 4 for g in gaps), f"ruled lines not under the text baseline (px gaps per line): {gaps}"


@pytest.mark.parametrize("size", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_ruled_lines_sit_under_the_text_on_the_write_page(page, live_server, size):
    _signup(page, live_server)
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(f"{live_server}/diaries/new")
    page.evaluate("document.fonts.ready")
    page.fill("#diaryContent", "\n".join(PARAGRAPHS[:2]))
    page.wait_for_timeout(300)
    gaps = page.evaluate(RULE_GAPS_JS, ".journal-textarea")
    assert len(gaps) >= 4, gaps
    assert all(-1.5 <= g <= 4 for g in gaps), f"ruled lines not under the text baseline (px gaps per line): {gaps}"


def test_no_phantom_blank_lines_around_the_entry_text(page, live_server):
    """white-space: pre-wrap used to sit on the whole <article>, so the
    whitespace between the template's tags rendered as real blank lines:
    two line-heights above the text and ~six before the end flourish, and
    the memorabilia label was pushed down the same way."""
    _signup(page, live_server)
    diary_id = _make_entry(page, live_server, LONG_TEXT)
    _open_entry(page, live_server, diary_id)
    m = page.evaluate(
        """() => {
          const art = document.getElementById('diaryReading'), raw = document.getElementById('diaryContentRaw');
          const fl = document.getElementById('diaryEndFlourish');
          return { padTop: parseFloat(getComputedStyle(art).paddingTop),
                   textTop: raw.getBoundingClientRect().top - art.getBoundingClientRect().top,
                   toFlourish: fl.getBoundingClientRect().top - raw.getBoundingClientRect().bottom,
                   lineHeight: parseFloat(getComputedStyle(art).lineHeight) };
        }"""
    )
    assert abs(m["textTop"] - m["padTop"]) <= 2, f"text starts {m['textTop']}px down, padding is {m['padTop']}px: {m}"
    assert m["toFlourish"] < m["lineHeight"] * 2, f"blank lines between the text and the end flourish: {m}"


@pytest.mark.parametrize("size", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_book_view_pages_fit_the_viewport_and_lose_no_text(page, live_server, size):
    """Pages were sized by a fixed 280-word budget unrelated to what the
    clipped viewport can show, so every page lost its last lines (and
    since the next page started where the budget ended, that text was
    never shown anywhere). Walk every page: nothing may sit below the
    clip edge (unless the page scrolls), the pages must add up to the
    entry, and the end flourish belongs on the last page only."""
    _signup(page, live_server)
    _open_entry(page, live_server, _make_entry(page, live_server, LONG_TEXT), size)
    page.click("#btnBookToggleView")
    page.wait_for_timeout(500)
    probe = """() => {
      const vp = document.getElementById('journalReadingViewport');
      let bottom = -Infinity;
      for (const id of ['diaryContentRaw', 'diaryEndFlourish', 'diaryAttachmentsBlock']) {
        const e = document.getElementById(id);
        if (e && getComputedStyle(e).display !== 'none') bottom = Math.max(bottom, e.getBoundingClientRect().bottom);
      }
      const raw = document.getElementById('diaryContentRaw');
      return { below: bottom - vp.getBoundingClientRect().bottom, scrolls: vp.style.overflowY === 'auto',
               text: getComputedStyle(raw).display === 'none' ? '' : raw.textContent,
               label: document.getElementById('bookPageText').textContent,
               flourish: getComputedStyle(document.getElementById('diaryEndFlourish')).display !== 'none',
               last: document.getElementById('btnBookNext').disabled };
    }"""
    texts, pages = [], 0
    for _ in range(40):
        s = page.evaluate(probe)
        pages += 1
        assert s["scrolls"] or s["below"] <= 1, f"{s['label']}: {s['below']:.0f}px of content is cut off below the page"
        assert s["flourish"] == s["last"], f"end flourish visibility wrong on {s['label']} (flourish={s['flourish']}, last={s['last']})"
        texts.append(s["text"])
        if s["last"]:
            break
        page.click("#btnBookNext")
        page.wait_for_timeout(600)
    assert pages > 1, "fixture entry should span several pages"
    norm = lambda t: re.sub(r"\s+", " ", t).strip()
    assert norm(" ".join(texts)) == norm(LONG_TEXT), "pages do not add up to the entry (text lost or duplicated)"


def test_book_view_reflows_when_the_window_is_resized(page, live_server):
    _signup(page, live_server)
    _open_entry(page, live_server, _make_entry(page, live_server, LONG_TEXT), (1280, 900))
    page.click("#btnBookToggleView")
    page.wait_for_timeout(500)
    before = page.evaluate("document.getElementById('bookPageText').textContent")
    page.set_viewport_size({"width": 1280, "height": 600})
    page.wait_for_timeout(700)
    after = page.evaluate("document.getElementById('bookPageText').textContent")
    assert before != after, f"page count did not change after shrinking the window ({before!r} -> {after!r})"


def test_page_turn_sheet_has_ruled_lines_and_lines_up_with_the_page(page, live_server):
    """The turning sheet is laid over the page mid-flip. It had no ruled
    lines on desktop (a later `background` shorthand wiped the image) and
    a different padding-top, so text jumped a few px when the flip landed."""
    _signup(page, live_server)
    _open_entry(page, live_server, _make_entry(page, live_server, LONG_TEXT))
    page.click("#btnBookToggleView")
    page.wait_for_timeout(500)
    m = page.evaluate(
        """() => {
          const first = (el) => { const t = el.firstChild, r = document.createRange(); r.setStart(t, 0); r.setEnd(t, 1); return r.getClientRects()[0].top; };
          const raw = document.getElementById('diaryContentRaw'), face = document.getElementById('turnFaceFront');
          const vp = document.getElementById('journalReadingViewport').getBoundingClientRect().top;
          face.textContent = raw.textContent;
          document.getElementById('pageTurnOverlay').classList.add('flipping');
          const cs = getComputedStyle(face);
          return { page: first(raw) - vp, sheet: first(face) - vp, rules: cs.backgroundImage.includes('repeating-linear-gradient'),
                   offsetSet: face.style.getPropertyValue('--rule-offset') !== '' };
        }"""
    )
    assert m["rules"], "turning sheet has no ruled-line background"
    assert m["offsetSet"], "turning sheet never got a --rule-offset"
    assert abs(m["page"] - m["sheet"]) <= 1, f"first line jumps {abs(m['page'] - m['sheet']):.1f}px when the flip lands: {m}"


def _luminance(rgb):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _rgb(css: str):
    return tuple(int(float(v)) for v in re.findall(r"[\d.]+", css)[:3])


PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63f8cfc0f01f0005000201a5f645400000000049454e44ae426082"
)


def test_attachment_filenames_are_readable_in_dark_theme(page, live_server):
    """The polaroid and paperclip cards are deliberately always light, but
    their filename text used a theme colour that's near-white in dark mode
    (measured contrast ~1.2:1 against a 4.5:1 minimum)."""
    page.add_init_script("localStorage.setItem('dd-theme', 'dark')")
    _signup(page, live_server)
    diary_id = _make_entry(page, live_server, PARAGRAPHS[0])
    for name, mime, body in [("summer_photo.png", "image/png", PNG_1PX), ("notes_from_the_trip.txt", "text/plain", b"hello")]:
        r = page.request.post(f"{live_server}/api/diaries/{diary_id}/attachments", multipart={"file": {"name": name, "mimeType": mime, "buffer": body}})
        assert r.ok, r.text()
    _open_entry(page, live_server, diary_id)
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    found = page.evaluate(
        """() => ['summer_photo.png', 'notes_from_the_trip.txt'].map((name) => {
          const card = [...document.querySelectorAll('.journal-polaroid, .journal-paperclip-card')].find((c) => c.textContent.includes(name));
          const label = [...card.querySelectorAll('div')].reverse().find((d) => d.textContent.trim() === name);
          return { name, color: getComputedStyle(label).color, bg: getComputedStyle(card).backgroundColor };
        })"""
    )
    for f in found:
        ratio = _contrast(_rgb(f["color"]), _rgb(f["bg"]))
        assert ratio >= 4.5, f"{f['name']}: text {f['color']} on {f['bg']} is only {ratio:.2f}:1 in dark theme"


def test_browser_tab_colour_follows_the_theme_toggle(page, live_server):
    _signup(page, live_server)
    page.goto(f"{live_server}/dashboard")
    meta = lambda: page.evaluate(
        "[document.documentElement.dataset.theme, document.querySelector('meta[name=theme-color]').content]"
    )
    start_theme, start_color = meta()
    page.click(".topbar .theme-toggle")
    page.wait_for_timeout(300)
    flipped_theme, flipped_color = meta()
    assert start_theme != flipped_theme
    assert start_color != flipped_color, f"theme-color stayed {start_color} when the theme changed"
    page.click(".topbar .theme-toggle")
    page.wait_for_timeout(300)
    assert meta() == [start_theme, start_color], "theme-color did not return with the theme"


def test_scrollbar_colour_is_theme_aware(page, live_server):
    _signup(page, live_server)
    page.goto(f"{live_server}/dashboard")
    colour = lambda: page.evaluate("getComputedStyle(document.documentElement).scrollbarColor")
    first = colour()
    assert first != "auto", "scrollbar colour is not themed at all"
    page.click(".topbar .theme-toggle")
    page.wait_for_timeout(300)
    assert colour() != first, "scrollbar colour did not change with the theme"
