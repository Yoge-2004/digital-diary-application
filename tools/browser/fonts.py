"""Serve the real web fonts and the icon font from npm to a Playwright context.

The app loads Inter/Playfair/Lora/Caveat from Google Fonts and Bootstrap Icons from jsdelivr. Sandboxes
(and offline CI) often block those hosts, so without this every screenshot uses fallback fonts and has no
icons, and layout measurements (handwriting widths, wrapping) are wrong. Usage: fonts.install(context).
"""
import pathlib
HERE = pathlib.Path(__file__).resolve().parent      # tools/browser
ROOT = HERE.parents[1]                                  # repository root
import os, re
FS = "" + str(HERE / "node_modules") + "/@fontsource/"
FAMS = {"inter": "Inter", "playfair-display": "Playfair Display", "lora": "Lora", "caveat": "Caveat"}
def build_css():
    out = []
    for pkg, fam in FAMS.items():
        d = FS + pkg + "/files/"
        for f in sorted(os.listdir(d)):
            m = re.match(rf"{pkg}-latin-(\d+)-(normal|italic)\.woff2$", f)
            if m: out.append(f"@font-face{{font-family:'{fam}';font-style:{m.group(2)};font-weight:{m.group(1)};src:url(https://fonts.gstatic.com/local/{pkg}/{f}) format('woff2');}}")
    return "\n".join(out)
def install(ctx):
    import re as _re
    BI = "" + str(HERE / "node_modules") + "/bootstrap-icons/font/"
    css = build_css()
    ctx.route(_re.compile(r"https://fonts\.googleapis\.com/css2.*"), lambda r: r.fulfill(body=css, content_type="text/css"))
    def gs(r):
        m = _re.search(r"/local/([\w\-]+)/([\w\-.]+)$", r.request.url)
        r.fulfill(path=f"{FS}{m.group(1)}/files/{m.group(2)}", content_type="font/woff2") if m else r.abort()
    ctx.route(_re.compile(r"https://fonts\.gstatic\.com/.*"), gs)
    def icons(r):
        u = r.request.url
        if u.endswith(".css"): r.fulfill(path=BI + "bootstrap-icons.min.css", content_type="text/css")
        else: r.fulfill(path=BI + "fonts/" + _re.search(r"fonts/([\w\-.]+)", u).group(1), content_type="font/woff2")
    ctx.route(_re.compile(r"https://cdn\.jsdelivr\.net/npm/bootstrap-icons.*"), icons)
