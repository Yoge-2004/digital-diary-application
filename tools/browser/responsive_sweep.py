"""Responsive sweep: 20 device sizes x ~30 pages/states with hostile data (50-char username, long location,
unbroken strings). Per page it reports horizontal overflow, elements off-screen or clipped, overlapping
controls, controls under 24px, broken images and console errors, and saves a screenshot for any page with an issue.

  python tools/browser/responsive_sweep.py all /tmp/resp.jsonl
  python tools/browser/responsive_sweep.py se-320,iphone-390,laptop-1280 /tmp/resp.jsonl

Known false positives: textarea vs mood pills on the edit page (the paper scrolls internally by design),
elements behind an open modal, collapsed panels. Read the screenshot before believing a finding.
"""
import pathlib
HERE = pathlib.Path(__file__).resolve().parent      # tools/browser
ROOT = HERE.parents[1]                                  # repository root
import sys, json, uuid, os, tempfile, time, re
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests" / "e2e")); sys.path.insert(0, str(HERE)); os.chdir(str(ROOT))
from playwright.sync_api import sync_playwright
from conftest import _ServerThread, _free_port, _wait_until_up, _BASE_TEST_SETTINGS
from app.core.config import Settings
from app.main import create_app
import fonts

DEVICES = {  # name: (w, h, dpr, touch)
 "fold-280": (280, 653, 3, True), "se-320": (320, 568, 2, True), "mini-375": (375, 812, 3, True), "iphone-390": (390, 844, 3, True),
 "pixel-412": (412, 915, 2.6, True), "promax-430": (430, 932, 3, True),
 "se-land-568": (568, 320, 2, True), "iphone-land-844": (844, 390, 3, True), "pixel-land-915": (915, 412, 2.6, True),
 "ipadmini-768": (768, 1024, 2, True), "ipad-land-1024": (1024, 768, 2, True), "ipadair-820": (820, 1180, 2, True),
 "ipadpro-1024": (1024, 1366, 2, True), "ipadpro-land-1366": (1366, 1024, 2, True),
 "narrow-500": (500, 700, 1, False), "split-640": (640, 800, 1, False), "laptop-1280": (1280, 720, 1, False),
 "laptop-1440": (1440, 900, 2, False), "desk-1920": (1920, 1080, 1, False), "qhd-2560": (2560, 1440, 1, False),
}
DARK = {"se-320", "iphone-390", "ipadmini-768", "laptop-1280"}
names = sys.argv[1].split(",") if len(sys.argv) > 1 and sys.argv[1] != "all" else list(DEVICES)
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/resp.jsonl"

CHECK = r"""() => {
  const vw = document.documentElement.clientWidth;
  const res = { docOverflow: document.documentElement.scrollWidth - vw, offenders: [], clipped: [], small: [], touchSmall: 0, overlaps: [], broken: [], tiny: [] };
  const clippedAway = (e) => { const r = e.getBoundingClientRect(); for (let p = e.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) { const s = getComputedStyle(p); if (s.overflowX === 'visible' && s.overflowY === 'visible') continue; const q = p.getBoundingClientRect(); if (r.right <= q.left || r.left >= q.right || r.bottom <= q.top || r.top >= q.bottom) return true; } return false; };
  const visible = (e) => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !clippedAway(e); };
  const clippedBy = (e) => { for (let p = e.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) { const s = getComputedStyle(p); if (s.overflowX !== 'visible') { const pr = p.getBoundingClientRect(); if (pr.right <= vw + 1 && pr.left >= -1) return true; } } return false; };
  const desc = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && e.className.toString ? '.' + e.className.toString().trim().split(/\s+/).slice(0, 2).join('.') : '') + ' "' + (e.innerText || e.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 26) + '"';
  const off = new Set();
  for (const e of document.body.querySelectorAll('*')) {
    if (e.closest('svg') && e.tagName.toLowerCase() !== 'svg') continue;
    if (!visible(e)) continue;
    if (e.closest('.ambient-glow, .sr-only, [aria-hidden="true"] .ambient-glow')) continue;
    const r = e.getBoundingClientRect();
    if ((r.right > vw + 1 || r.left < -1) && !clippedBy(e)) { off.add(e); if (!off.has(e.parentElement)) res.offenders.push(desc(e) + ' [' + Math.round(r.left) + '..' + Math.round(r.right) + ' of ' + vw + ']'); }
    const s = getComputedStyle(e);
    if ((s.overflowX === 'hidden' || s.overflowX === 'clip') && e.scrollWidth > e.clientWidth + 1 && s.textOverflow !== 'ellipsis' && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
      res.clipped.push(desc(e) + ' (' + e.scrollWidth + '>' + e.clientWidth + ')');
    if ([...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1) && parseFloat(s.fontSize) < 11) res.tiny.push(desc(e) + ' ' + s.fontSize);
    if (e.tagName === 'IMG' && e.complete && e.naturalWidth === 0) res.broken.push(e.src.slice(-50));
  }
  const inter = [...document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, [role=button], [tabindex="0"]')]
    .filter(e => visible(e) && !e.closest('#island') && !e.closest('.sidebar-overlay') && !e.closest('[inert]'));
  const inline = (e) => e.tagName === 'A' && getComputedStyle(e).display === 'inline' && e.closest('p, li, span.hint, .form-hint, small, label');
  for (const e of inter) {
    if (e.type === 'checkbox' || e.type === 'radio' || e.classList.contains('sr-only') || inline(e)) continue;
    const r = e.getBoundingClientRect(); const m = Math.min(r.width, r.height);
    if (m < 24) res.small.push(desc(e) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
    else if (m < 44) res.touchSmall++;
  }
  for (let i = 0; i < inter.length; i++) for (let j = i + 1; j < inter.length; j++) {
    const a = inter[i], b = inter[j]; if (inline(a) || inline(b) || a.classList.contains('toggle-pw') || b.classList.contains('toggle-pw') || a.contains(b) || b.contains(a) || a.closest('label') === b.closest('label') && a.closest('label')) continue;
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    const w = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left), h = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
    if (w > 2 && h > 2 && (w * h) / Math.min(ra.width * ra.height, rb.width * rb.height) > 0.4) res.overlaps.push(desc(a) + '  ×  ' + desc(b));
  }
  for (const k of ['offenders', 'clipped', 'small', 'overlaps', 'tiny', 'broken']) res[k] = [...new Set(res[k])].slice(0, 8);
  return res;
}"""

tmp = tempfile.mkdtemp()
def start(**o):
    s = Settings(database_url=f"sqlite:///{tmp}/db{uuid.uuid4().hex[:6]}.db", **{**_BASE_TEST_SETTINGS, **o})
    port = _free_port(); t = _ServerThread(create_app(s), port); t.start(); _wait_until_up(port); return f"http://127.0.0.1:{port}", t
base, t1 = start()
base_mail, t2 = start(smtp_host="smtp.example.invalid", smtp_from="diary@example.invalid")
base_push, t3 = start(vapid_public_key="BFakePublicKeyForSweepOnly", vapid_private_key="fake-private")
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")
LONGWORD = "Pneumonoultramicroscopicsilicovolcanoconiosis" * 2

def seed(page):
    ids = []
    spec = [
      dict(title="An extremely long diary title that goes on and on to test how headings wrap on tiny screens " * 2, mood="angry", tags=["tag-one", "a-really-long-tag-name-for-wrapping-behaviour", "x", "family", "work", "travel", "ideas"], location="A very long location name, Somewhere Far Away, Another Region, Country", content="Paragraph one. " * 120),
      dict(title=LONGWORD, mood="anxious", tags=["unbroken"], content="https://example.com/" + "a" * 140 + "\n\n" + LONGWORD + "\n\n" + "words " * 40),
      dict(title="Book view stress", mood="calm", tags=[], content=("Dear diary, today was long. " * 20 + "\n\n") * 14),
      dict(title="With attachments", mood="happy", tags=["files"], content="Short body."),
    ] + [dict(title=f"Entry {i} {m}", mood=m, tags=["t"], content="Some words for the diary. " * 12) for i, m in enumerate(["happy","sad","neutral","excited","grateful","melancholy","hopeful","calm"])]
    for sp in spec:
        r = page.request.post(base + "/api/diaries", data={**sp, "visibility": "private"}); assert r.ok, r.text(); ids.append(r.json()["id"])
    page.request.post(base + f"/api/diaries/{ids[3]}/attachments", multipart={"file": {"name": "photo-with-a-very-long-file-name-here-to-test-wrapping.png", "mimeType": "image/png", "buffer": PNG}})
    page.request.post(base + f"/api/diaries/{ids[3]}/attachments", multipart={"file": {"name": "notes.txt", "mimeType": "text/plain", "buffer": b"hello"}})
    for k, flag in ((4, "is_favorite"), (5, "is_bookmarked"), (6, "is_pinned")):
        page.request.patch(base + f"/api/diaries/{ids[k]}", data={flag: True})
    return ids

def run_device(b, name):
    w, h, dpr, touch = DEVICES[name]
    for theme in (("light", "dark") if name in DARK else ("light",)):
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr, has_touch=touch, is_mobile=touch and w < 900)
        fonts.install(ctx); ctx.add_init_script(f"localStorage.setItem('dd-theme','{theme}')")
        page = ctx.new_page(); logs = []
        page.on("console", lambda m: logs.append("console." + m.type + ": " + m.text[:140]) if m.type in ("error",) else None)
        page.on("pageerror", lambda e: logs.append("pageerror: " + str(e)[:140]))
        page.on("requestfailed", lambda r: logs.append("reqfailed: " + r.url[-60:]) if "fonts" not in r.url and "jsdelivr" not in r.url else None)
        def visit(url, label, pre=None):
            logs.clear()
            try:
                page.goto(url, wait_until="load", timeout=30000); page.wait_for_timeout(500)
                page.add_style_tag(content="*,*::before,*::after{animation-duration:0s!important;animation-delay:0s!important;transition-duration:0s!important}")
                if pre: pre(page); page.wait_for_timeout(300)
                page.wait_for_timeout(250)
                res = page.evaluate(CHECK)
            except Exception as e:
                res = {"error": str(e)[:160]}
            res.update(device=name, theme=theme, page=label, logs=[l for l in logs if "net::ERR_ABORTED" not in l and not (label == '/does-not-exist' and '404' in l)][:4])
            bad = res.get("error") or res.get("docOverflow", 0) > 0 or res.get("offenders") or res.get("clipped") or res.get("overlaps") or res.get("small") or res.get("broken") or res.get("logs")
            if bad:
                shot = f"/tmp/resp_shots/{name}_{theme}_{re.sub(r'[^a-z0-9]+','_',label.lower())}.png"; os.makedirs("/tmp/resp_shots", exist_ok=True)
                try: page.screenshot(path=shot); res["shot"] = shot
                except Exception: pass
            with open(OUT, "a") as f: f.write(json.dumps(res) + "\n")
            print(f"{name:16s}{theme:6s}{label:38s} {'OK' if not bad else 'ISSUES'}", flush=True)
        # public
        for path in ("/", "/login", "/register", "/does-not-exist"): visit(base + path, path)
        visit(base_mail + "/forgot-password", "/forgot-password (mail)")
        # signed-in
        u = "u" + uuid.uuid4().hex[:7] + "LongUserName" * 3
        r = page.request.post(base + "/api/auth/register", data={"username": u[:50], "email": ("very.long.email.address." + u)[:60] + "@example-company-domain.com", "password": "password123"}); assert r.ok, r.text()
        ids = seed(page)
        for path in ("/dashboard", "/diaries", "/diaries?favorite=true", "/diaries/new", "/calendar", "/stats", "/shared", "/search?q=words"): visit(base + path, path)
        visit(base + f"/diaries/{ids[0]}", "entry: long title+tags")
        visit(base + f"/diaries/{ids[1]}", "entry: unbroken strings")
        visit(base + f"/diaries/{ids[3]}", "entry: attachments")
        visit(base + f"/diaries/{ids[2]}", "entry: book view", lambda pg: (pg.click("#btnBookToggleView"), pg.wait_for_timeout(700)))
        visit(base + f"/diaries/{ids[3]}", "entry: share form", lambda pg: pg.evaluate("document.getElementById('expires_in_hours')?.scrollIntoView()"))
        visit(base + f"/diaries/{ids[0]}/edit", "entry: edit")
        visit(base + "/dashboard", "island open", lambda pg: pg.click("#islandToggle"))
        visit(base + "/diaries", "island compact (scrolled)", lambda pg: pg.evaluate("window.scrollTo({top: 700, behavior: 'instant'})"))
        if w < 1024: visit(base + "/dashboard", "sidebar drawer open", lambda pg: pg.click("#sidebarToggle"))
        for tab in ("profile", "password", "appearance", "danger"):
            visit(base + "/settings", "settings: " + tab, lambda pg, tab=tab: pg.click(f'.settings-tab[data-panel="{tab}"]'))
        visit(base + "/settings", "settings: delete modal", lambda pg: (pg.click('.settings-tab[data-panel="danger"]'), pg.click("#openDeleteAccountModal")))
        ctx.close()
        # push-enabled notifications tab on its own server
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr, has_touch=touch, is_mobile=touch and w < 900); fonts.install(ctx)
        ctx.add_init_script(f"localStorage.setItem('dd-theme','{theme}')"); page = ctx.new_page(); logs = []
        pu = "pn" + uuid.uuid4().hex[:8]; page.request.post(base_push + "/api/auth/register", data={"username": pu, "email": pu + "@example.com", "password": "password123"})
        visit_url = base_push + "/settings"
        try:
            page.goto(visit_url); page.wait_for_timeout(500); page.click('.settings-tab[data-panel="notifications"]'); page.wait_for_timeout(500); res = page.evaluate(CHECK)
        except Exception as e: res = {"error": str(e)[:160]}
        res.update(device=name, theme=theme, page="settings: notifications (push on)", logs=[])
        with open(OUT, "a") as f: f.write(json.dumps(res) + "\n")
        ctx.close()

with sync_playwright() as p:
    b = p.chromium.launch()
    for n in names:
        try: run_device(b, n)
        except Exception as e: print("DEVICE FAILED", n, str(e)[:200], flush=True); open(OUT, "a").write(json.dumps({"device": n, "error": "device run failed: " + str(e)[:200], "page": "*"}) + "\n")
    b.close()
for t in (t1, t2, t3): t.stop()
print("DONE", flush=True)
