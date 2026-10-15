"""axe-core (WCAG 2.0/2.1 A+AA) over every page x light/dark, including hidden-by-default states
(settings tabs, delete modal, open island, drawer, book view, error states, mail-enabled and push-enabled pages).

  python tools/browser/axe_sweep.py phone|desktop      -> prints per page counts, writes /tmp/sweep_<mode>.json
"""
import pathlib
HERE = pathlib.Path(__file__).resolve().parent      # tools/browser
ROOT = HERE.parents[1]                                  # repository root
import sys, json, uuid, socket, threading, time, tempfile, os, re
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests" / "e2e"))
os.chdir(str(ROOT))
import uvicorn
from playwright.sync_api import sync_playwright
from conftest import _ServerThread, _free_port, _wait_until_up, _BASE_TEST_SETTINGS
from app.core.config import Settings
from app.main import create_app

MODE = sys.argv[1] if len(sys.argv) > 1 else "phone"
SIZE = {"phone": (390, 844), "desktop": (1280, 720)}[MODE]
AXE = open(str(HERE / "node_modules" / "axe-core" / "axe.min.js"), encoding="utf-8").read()
MOODS = ["happy","sad","neutral","angry","anxious","excited","grateful","calm","melancholy","hopeful"]
tmp = tempfile.mkdtemp()
def start(**o):
    s = Settings(database_url=f"sqlite:///{tmp}/db{uuid.uuid4().hex[:6]}.db", **{**_BASE_TEST_SETTINGS, **o})
    port = _free_port(); t = _ServerThread(create_app(s), port); t.start(); _wait_until_up(port)
    return f"http://127.0.0.1:{port}", t

base, t1 = start()
base_mail, t2 = start(smtp_host="smtp.example.invalid", smtp_from="diary@example.invalid")
base_push, t3 = start(vapid_public_key="BFakePublicKeyForSweepOnly", vapid_private_key="fake-private")
results = {}

def run_axe(page, label):
    page.wait_for_timeout(300)
    page.evaluate("""async () => { await Promise.race([Promise.all(document.getAnimations().filter(a=>a.effect && a.effect.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{}))), new Promise(r=>setTimeout(r,4000))]); }""")
    page.wait_for_timeout(200)
    r = page.evaluate("""async () => { const res = await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa']}});
      return res.violations.map(v => ({id:v.id, impact:v.impact, n:v.nodes.length, nodes:v.nodes.slice(0,3).map(n => ({t:n.target.join(' '), s:(n.any[0]||n.all[0]||n.none[0]||{}).message}))})); }""")
    results[label] = r
    print(f"{label:55s} {sum(v['n'] for v in r):3d} nodes / {len(r)} rules", flush=True)

with sync_playwright() as p:
    b = p.chromium.launch()
    for theme in ("light", "dark"):
        ctx = b.new_context(viewport={"width": SIZE[0], "height": SIZE[1]})
        ctx.route(re.compile(r"https://(fonts\.googleapis|fonts\.gstatic|cdn\.jsdelivr)\.net?.*|https://fonts\..*"), lambda r: r.abort())
        ctx.add_init_script(f"localStorage.setItem('dd-theme','{theme}')")
        page = ctx.new_page()
        def go(url, label, pre=None):
            try:
                page.goto(url, wait_until="load", timeout=30000)
                page.evaluate(AXE)
                if pre:
                    pre(page); page.wait_for_load_state('load'); page.evaluate(AXE)
                run_axe(page, f"{MODE}/{theme}/{label}")
            except Exception as e:
                print(f"{MODE}/{theme}/{label}: ERROR {str(e)[:120]}", flush=True)
        # public pages
        for path in ("/", "/login", "/register"): go(base+path, path)
        go(base_mail+"/forgot-password", "/forgot-password(mail on)")
        go(base_mail+"/reset-password?token=abc", "/reset-password?token")
        go(base_mail+"/login", "/login(mail on)")
        # notifications tab needs push enabled: separate server + user
        pu = f"pn{uuid.uuid4().hex[:8]}"
        page.request.post(base_push+"/api/auth/register", data={"username":pu,"email":f"{pu}@example.com","password":"password123"})
        go(base_push+"/settings", "settings tab notifications (push on)", lambda pg: (pg.click('.settings-tab[data-panel="notifications"]'), pg.wait_for_timeout(600)))
        page.context.clear_cookies()
        def bad_login(pg):
            pg.fill("#login-username","nobody"); pg.fill("#login-password","wrongpass1"); pg.click("#loginForm button[type=submit]"); pg.wait_for_timeout(1200)
        go(base+"/login", "login after failed attempt", bad_login)
        def bad_reg(pg):
            pg.fill("#reg-username","a"); pg.fill("#reg-email","not-an-email"); pg.fill("#reg-password","x"); pg.fill("#reg-confirm","y"); pg.keyboard.press("Tab"); pg.wait_for_timeout(600)
        go(base+"/register", "register with invalid fields", bad_reg)
        # authed, EMPTY state first
        u = f"sw{uuid.uuid4().hex[:8]}"
        r = page.request.post(base+"/api/auth/register", data={"username":u,"email":f"{u}@example.com","password":"password123"}); assert r.ok, r.text()
        for path in ("/dashboard","/diaries","/search","/calendar","/stats","/shared","/settings","/diaries/new"):
            go(base+path, "EMPTY "+path)
        # seed
        ids = []
        for i, m in enumerate(MOODS):
            body = {"title": ("An extremely long title that keeps going and going to test wrapping behaviour " * 2 if i == 0 else f"Entry {i} {m}"),
                    "content": ("Some words for the diary. " * (60 if i == 1 else 6)), "mood": m, "visibility": "private",
                    "tags": ["tag-one","a-really-long-tag-name-for-wrapping","x"] if i < 3 else []}
            rr = page.request.post(base+"/api/diaries", data=body); assert rr.ok, rr.text(); ids.append(rr.json()["id"])
        page.request.post(base+f"/api/diaries/{ids[1]}/attachments", multipart={"file":{"name":"photo-with-a-very-long-file-name-here.png","mimeType":"image/png","buffer":bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")}})
        page.request.post(base+f"/api/diaries/{ids[1]}/attachments", multipart={"file":{"name":"notes.txt","mimeType":"text/plain","buffer":b"hello"}})
        page.request.post(base+f"/api/diaries/{ids[2]}", data={}) if False else None
        for path in ("/dashboard","/diaries","/diaries?favorite=true","/search?q=words","/calendar","/stats","/shared","/settings"):
            go(base+path, path)
        for path in ("/dashboard","/diaries","/calendar","/settings"):
            go(base+path, "ISLAND OPEN "+path, lambda pg: (pg.click("#islandToggle"), pg.wait_for_timeout(900)))
        go(base+"/diaries", "ISLAND compact", lambda pg: (pg.evaluate("window.scrollTo({top: 500, behavior: 'instant'})"), pg.wait_for_timeout(900)))
        go(base+"/diaries/new", "ISLAND meta (word count)", lambda pg: (pg.fill("#diaryContent", "some words here to count"), pg.wait_for_timeout(500)))
        go(base+f"/diaries/{ids[1]}", "ISLAND OPEN entry", lambda pg: (pg.click("#islandToggle"), pg.wait_for_timeout(900)))
        go(base+f"/diaries/{ids[0]}", "entry (long title+tags)")
        go(base+f"/diaries/{ids[1]}", "entry (attachments)")
        go(base+f"/diaries/{ids[1]}", "entry book view", lambda pg: (pg.click("#btnBookToggleView"), pg.wait_for_timeout(600)))
        for tab in ("profile","password","appearance","danger"):
            go(base+"/settings", "settings tab "+tab, lambda pg, tab=tab: (pg.click(f'.settings-tab[data-panel="{tab}"]'), pg.wait_for_timeout(500)))
        go(base+f"/diaries/{ids[1]}/edit", "entry edit")
        go(base+"/settings", "settings + delete modal", lambda pg: pg.evaluate("[...document.querySelectorAll('button')].find(b=>/delete/i.test(b.textContent))?.click()"))
        ctx.close()
    b.close()
json.dump(results, open(f"/tmp/sweep_{MODE}.json","w"), indent=1)
t1.stop(); t2.stop(); t3.stop()
tot = sum(v['n'] for r in results.values() for v in r)
print("TOTAL nodes:", tot, "pages with violations:", sum(1 for r in results.values() if r))
