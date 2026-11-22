"""Render-ready HyperFrames compositions for the three overlay kinds (transparent 1920x1080).

    gen.py OVERLAYS.json --dir RENDER_DIR [--theme theme.json]

  card  day title card: kicker tag, huge display word, local-script line, accent rule,
        spaced mono date label, one-line intro sentence, soft radial scrim. (after catalog `titlecard-lockup`)
  loc   place lower third: accent kicker, heavy name, local-script line, drawn baseline. (after `lt-kicker-name`)
  ff    burst tag top-right: accent pill with >> and speed, white chip saying what is happening.

Writes <id>.html into RENDER_DIR (fonts must sit in RENDER_DIR/fonts — fetch_fonts.sh) plus an
index.html. Render with render.sh. The theme swaps fonts/accent; the HIERARCHY is the style
(see references/style.md) — change the look freely, keep the three roles distinct.
"""
import json, sys, html, pathlib, argparse

THEME = json.loads((pathlib.Path(__file__).parent / "theme.json").read_text())

def fam(k): return "'" + THEME[k]["family"] + "'"
def fonts_css():
    out = []
    for k in ("display", "mono", "local"):
        for f in THEME[k]["files"]:
            out.append("@font-face{font-family:'%s';font-weight:%s;src:url('fonts/%s')}" % (THEME[k]["family"], f.get("weight", "400"), f["file"]))
    return "\n".join(out) + "\n*{margin:0;padding:0;box-sizing:border-box}\nhtml,body{background:transparent;overflow:hidden}\nbody{width:1920px;height:1080px}\n"
DISP, MONO, LOCAL, ACC = fam("display"), fam("mono"), fam("local"), THEME["accent"]

def doc(cid, dur, css, body, js):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{fonts_css()}{css}</style></head>
<body>
<div id="root" data-composition-id="{cid}" data-width="1920" data-height="1080" data-start="0" data-duration="{dur}" data-fps="30">
<div id="clip" class="clip" data-start="0" data-duration="{dur}" data-track-index="0">{body}</div>
</div>
<script>
window.__timelines = window.__timelines || {{}};
var tl = gsap.timeline({{ paused: true }});
{js}
window.__timelines["{cid}"] = tl;
</script></body></html>"""

e = html.escape

def card(o):
    d = o.get("dur", 5.0)
    css = f"""
#scrim{{position:absolute;inset:0;background:radial-gradient(ellipse 60% 55% at 50% 50%,rgba(0,0,0,.55),rgba(0,0,0,0) 75%)}}
#lock{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;text-shadow:0 2px 24px rgba(0,0,0,.45)}}
.kick{{font-family:{MONO},{LOCAL};font-weight:700;font-size:26px;letter-spacing:.42em;text-indent:.42em;color:{ACC};background:#fff;padding:6px 16px;text-shadow:none}}
.word{{font-family:{DISP};font-size:200px;line-height:1;letter-spacing:-.02em;margin-top:26px;text-transform:uppercase}}
.jp{{font-family:{LOCAL};font-weight:700;font-size:40px;letter-spacing:.3em;margin-top:6px;opacity:.92}}
.rule{{width:520px;height:4px;background:{ACC};margin-top:26px;transform-origin:0 50%}}
.lab{{font-family:{MONO};font-weight:700;font-size:28px;letter-spacing:.32em;text-indent:.32em;margin-top:22px;text-transform:uppercase}}
.intro{{font-family:{LOCAL};font-weight:500;font-size:36px;letter-spacing:.01em;margin-top:30px;max-width:1780px;white-space:nowrap;text-align:center;line-height:1.35}}
"""
    body = f"""<div id="scrim"></div><div id="lock">
<span class="kick" id="k">{e(o['kicker'])}</span>
<div class="word" id="w">{e(o['word'])}</div>
{f'<div class="jp" id="j">{e(o["jp"])}</div>' if o.get('jp') else ''}
<div class="rule" id="r"></div>
<div class="lab" id="l">{e(o['label'])}</div>
{f'<div class="intro" id="i">{e(o["intro"])}</div>' if o.get('intro') else ''}</div>"""
    js = f"""
gsap.set('#scrim',{{opacity:0}});gsap.set('#k',{{y:16,opacity:0}});gsap.set('#w',{{scale:.94,opacity:0}});
gsap.set('#j',{{y:10,opacity:0}});gsap.set('#r',{{scaleX:0}});gsap.set('#l',{{y:10,opacity:0}});
tl.to('#scrim',{{opacity:1,duration:.5,ease:'power2.out'}},0);
tl.to('#k',{{y:0,opacity:1,duration:.45,ease:'power3.out'}},.1);
tl.to('#w',{{scale:1,opacity:1,duration:.7,ease:'expo.out'}},.25);
tl.to('#j',{{y:0,opacity:.92,duration:.5,ease:'power3.out'}},.45);
tl.to('#r',{{scaleX:1,duration:.6,ease:'power4.out'}},.55);
tl.to('#l',{{y:0,opacity:1,duration:.5,ease:'power3.out'}},.75);
gsap.set('#i',{{y:12,opacity:0}});tl.to('#i',{{y:0,opacity:1,duration:.6,ease:'power3.out'}},1.05);
tl.to('#lock',{{y:-18,opacity:0,duration:.45,ease:'power2.in'}},{d-0.55});
tl.to('#scrim',{{opacity:0,duration:.5,ease:'power2.in'}},{d-0.5});
"""
    return doc(o["id"], d, css, body, js)

def loc(o):
    d = o.get("dur", 4.8)
    css = f"""
.lt{{position:absolute;left:110px;bottom:110px;display:flex;flex-direction:column;align-items:flex-start;gap:12px}}
.kw{{overflow:hidden}}
.kick{{display:inline-block;font-family:{MONO};font-weight:700;font-size:24px;color:#fff;background:{ACC};padding:6px 14px;letter-spacing:.14em;text-transform:uppercase;white-space:nowrap}}
.name{{font-family:{DISP};font-size:84px;color:#fff;line-height:.98;letter-spacing:-.01em;text-transform:uppercase;white-space:nowrap;text-shadow:0 2px 22px rgba(0,0,0,.55),0 0 2px rgba(0,0,0,.4)}}
.jp{{font-family:{LOCAL};font-weight:700;font-size:34px;color:#fff;letter-spacing:.18em;text-shadow:0 2px 16px rgba(0,0,0,.6)}}
.base{{height:6px;width:100%;background:{ACC};border-radius:3px;transform-origin:0 50%}}
"""
    body = f"""<div class="lt" id="lt"><div class="kw"><span class="kick" id="k">{e(o['kicker'])}</span></div>
<div class="name" id="n">{e(o['name'])}</div>
{f'<div class="jp" id="j">{e(o["jp"])}</div>' if o.get('jp') else ''}
<div class="base" id="b"></div></div>"""
    js = f"""
gsap.set('#k',{{y:-44}});gsap.set('#n',{{y:36,opacity:0}});gsap.set('#j',{{y:14,opacity:0}});gsap.set('#b',{{scaleX:0}});
tl.to('#k',{{y:0,duration:.42,ease:'back.out(2)'}},.1);
tl.to('#n',{{y:0,opacity:1,duration:.45,ease:'back.out(1.5)'}},.3);
tl.to('#j',{{y:0,opacity:1,duration:.4,ease:'power3.out'}},.45);
tl.to('#b',{{scaleX:1,duration:.5,ease:'power4.out'}},.5);
tl.to('#b',{{scaleX:0,duration:.3,ease:'power2.in'}},{d-0.55});
tl.to(['#n','#j'],{{y:-16,opacity:0,duration:.32,ease:'power2.in'}},{d-0.5});
tl.to('#k',{{y:-44,duration:.3,ease:'power2.in'}},{d-0.48});
tl.set('#lt',{{visibility:'hidden'}},{d-0.05});
"""
    return doc(o["id"], d, css, body, js)

def ff(o):
    d = o.get("dur", 6)
    tri = '<svg width="40" height="26" viewBox="0 0 34 22"><path d="M0 0L16 11L0 22Z M17 0L33 11L17 22Z" fill="#fff"/></svg>'
    css = f"""
.ff{{position:absolute;right:90px;top:80px;display:flex;align-items:center;gap:0;filter:drop-shadow(0 4px 18px rgba(0,0,0,.35))}}
.pill{{display:flex;align-items:center;gap:12px;background:{ACC};padding:14px 20px 14px 24px;border-radius:999px 0 0 999px}}
.x{{font-family:{MONO};font-weight:700;font-size:34px;color:#fff;letter-spacing:.06em}}
.txt{{font-family:{MONO};font-weight:700;font-size:32px;color:#111;background:#fff;padding:15px 26px;border-radius:0 999px 999px 0;letter-spacing:.06em;text-transform:lowercase;white-space:nowrap;clip-path:inset(0 0 0 0)}}
"""
    body = f"""<div class="ff" id="ff"><div class="pill" id="p">{tri}<span class="x">{e(o.get('speed','2×'))}</span></div><div class="txt" id="t">{e(o['text'])}</div></div>"""
    js = f"""
gsap.set('#ff',{{x:60,opacity:0}});gsap.set('#t',{{clipPath:'inset(0 100% 0 0)'}});
tl.to('#ff',{{x:0,opacity:1,duration:.4,ease:'back.out(1.6)'}},.05);
tl.to('#t',{{clipPath:'inset(0 0% 0 0)',duration:.5,ease:'power3.out'}},.3);
tl.to('#p svg',{{x:6,duration:.35,yoyo:true,repeat:{int((d-1)/0.7)},ease:'sine.inOut'}},.4);
tl.to('#t',{{clipPath:'inset(0 100% 0 0)',duration:.3,ease:'power2.in'}},{d-0.6});
tl.to('#ff',{{x:60,opacity:0,duration:.3,ease:'power2.in'}},{d-0.35});
"""
    return doc(o["id"], d, css, body, js)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("overlays"); ap.add_argument("--dir", required=True); ap.add_argument("--theme")
    a = ap.parse_args()
    if a.theme:
        THEME.update(json.loads(pathlib.Path(a.theme).read_text()))
        DISP, MONO, LOCAL, ACC = fam("display"), fam("mono"), fam("local"), THEME["accent"]
    items = json.loads(pathlib.Path(a.overlays).read_text()); d = pathlib.Path(a.dir); d.mkdir(parents=True, exist_ok=True)
    for o in items:
        (d / f"{o['id']}.html").write_text({"card": card, "loc": loc, "ff": ff}[o["kind"]](o))
    (d / "index.html").write_text((d / f"{items[0]['id']}.html").read_text())
    (d / "ids.txt").write_text("\n".join(o["id"] for o in items) + "\n")
    print(len(items), "compositions ->", d)
