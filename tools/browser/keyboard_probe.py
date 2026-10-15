"""Keyboard probe: presses Tab through every page and records each stop (position, visibility, focus indicator
on the element or its ancestors, positive tabindex, order jumps).

  python tools/browser/keyboard_probe.py desktop|phone

Note: transitions are disabled inside the probe, otherwise getComputedStyle right after blur() returns the
pre-transition value and every input looks like it has no focus indicator.
"""
import pathlib
HERE = pathlib.Path(__file__).resolve().parent      # tools/browser
ROOT = HERE.parents[1]                                  # repository root
import sys, json, uuid, os, tempfile
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests" / "e2e")); os.chdir(str(ROOT))
from playwright.sync_api import sync_playwright
from conftest import _ServerThread, _free_port, _wait_until_up, _BASE_TEST_SETTINGS
from app.core.config import Settings
from app.main import create_app
tmp = tempfile.mkdtemp()
s = Settings(database_url=f"sqlite:///{tmp}/d.db", **_BASE_TEST_SETTINGS)
port = _free_port(); t = _ServerThread(create_app(s), port); t.start(); _wait_until_up(port); base = f"http://127.0.0.1:{port}"
INFO = """() => { const e = document.activeElement; if (!e || e === document.body) return null;
  if (!e.dataset.kbdId) e.dataset.kbdId = String(++window.__kbd);
  const r = e.getBoundingClientRect();
  const snap = (n) => { const c = getComputedStyle(n); return [c.outlineStyle, c.outlineWidth, c.outlineColor, c.boxShadow, c.borderColor, c.backgroundColor, c.color, c.textDecorationLine, c.transform].join('|'); };
  const chain = (n) => { const a = [n]; for (let i = 0; i < 3 && a[a.length-1].parentElement; i++) a.push(a[a.length-1].parentElement); return a; };
  const els = chain(e); const on = els.map(snap); e.blur(); const off = els.map(snap); e.focus({focusVisible: true});
  const own = on[0] !== off[0]; const ancestor = on.some((v, i) => i > 0 && v !== off[i]);
  const cs = getComputedStyle(e);
  const label = (e.getAttribute('aria-label') || e.innerText || e.value || e.getAttribute('title') || e.getAttribute('href') || '').trim().replace(/\\s+/g,' ').slice(0,34);
  return { kid: e.dataset.kbdId, tag: e.tagName.toLowerCase(), id: e.id, cls: (e.className||'').toString().slice(0,30), label, role: e.getAttribute('role'), ti: e.getAttribute('tabindex'),
    x: Math.round(r.x), y: Math.round(r.y + scrollY), w: Math.round(r.width), h: Math.round(r.height),
    vis: r.width > 0 && r.height > 0 && cs.visibility !== 'hidden',
    offscreen: r.right <= 0 || r.left >= innerWidth || r.bottom + scrollY <= 0,
    ring: own || ancestor, ownRing: own, outline: cs.outlineStyle + ' ' + cs.outlineWidth }; }"""
SETTLE = """async () => { window.__kbd = window.__kbd || 0; await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  await Promise.race([Promise.all(document.getAnimations().filter(a => a.effect && a.effect.getComputedTiming().iterations !== Infinity).map(a => a.finished.catch(() => {}))), new Promise(r => setTimeout(r, 4000))]); }"""
def tab_through(page, name, limit=70):
    page.keyboard.press("Tab") if False else None
    page.add_style_tag(content='*,*::before,*::after{transition:none!important;animation:none!important}'); page.evaluate(SETTLE); seen = []; first = None
    for i in range(limit):
        page.keyboard.press("Tab"); page.wait_for_timeout(40)
        info = page.evaluate(INFO)
        if info is None: seen.append(None); continue
        key = info['kid']
        if seen and seen[-1] and seen[-1]['kid'] == key: continue  # native sub-fields (date input): one stop
        if first is None: first = key
        elif key == first: break
        seen.append(info)
    issues = []
    for i, e in enumerate(seen):
        if e is None: continue
        if not e['vis'] or e['offscreen']: issues.append(f"#{i} INVISIBLE/OFFSCREEN FOCUS {e['tag']} {e['id'] or e['cls']} '{e['label']}' at x={e['x']} {e['w']}x{e['h']}")
        if not e['ring']: issues.append(f"#{i} NO FOCUS INDICATOR {e['tag']} {e['id'] or e['cls']} '{e['label']}' (outline {e['outline']})")
        if e['ti'] and e['ti'].isdigit() and int(e['ti']) > 0: issues.append(f"#{i} POSITIVE TABINDEX {e['ti']} on {e['tag']} '{e['label']}'")
        if e['tag'] in ('button','input','select') and (e['w'] < 24 or e['h'] < 24): issues.append(f"#{i} SMALL TARGET {e['w']}x{e['h']} {e['tag']} {e['id']} '{e['label']}'")
    # order: big backwards jumps in y (> 300px) within one pass
    prev = None
    for i, e in enumerate(seen):
        if e is None: continue
        if prev and e['y'] < prev['y'] - 300: issues.append(f"#{i} ORDER JUMP up {prev['y']}->{e['y']}: '{prev['label']}' -> '{e['label']}'")
        prev = e
    print(f"\n=== {name}: {len(seen)} stops"); 
    print("   order:", " > ".join((e['label'] or e['id'] or e['tag'])[:16] if e else '[body]' for e in seen)[:600])
    for x in issues: print("  !", x)
    return seen
with sync_playwright() as p:
    b = p.chromium.launch(); mode = sys.argv[1] if len(sys.argv) > 1 else "desktop"
    ctx = b.new_context(viewport={"width": 1280, "height": 800} if mode == "desktop" else {"width": 390, "height": 844}); page = ctx.new_page()
    for path in ("/", "/login", "/register"):
        page.goto(base + path); page.wait_for_timeout(500); tab_through(page, path)
    u = "k" + uuid.uuid4().hex[:7]
    page.request.post(base + "/api/auth/register", data={"username": u, "email": u + "@example.com", "password": "password123"})
    ids = [page.request.post(base + "/api/diaries", data={"title": f"Entry {i}", "content": "words " * 80, "mood": "happy", "visibility": "private", "tags": ["a", "b"]}).json()["id"] for i in range(3)]
    for path in ("/dashboard", "/diaries", "/diaries/new", f"/diaries/{ids[0]}", f"/diaries/{ids[0]}/edit", "/calendar", "/stats", "/settings", "/search?q=words"):
        page.goto(base + path); page.wait_for_timeout(600); tab_through(page, path)
    b.close()
t.stop()
