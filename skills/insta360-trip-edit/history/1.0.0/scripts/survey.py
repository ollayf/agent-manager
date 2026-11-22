#!/usr/bin/env python3
"""Look at hours of footage for a few thousand tokens. Everything reads the 720p proxies.

    survey.py sheets  --project P [--every 20]            one sheet set per clip (36 tiles/sheet)
    survey.py scan    --project P                         motion / darkness flags per 10 s window
    survey.py zoom    --project P --clip 005 --start 1080 --end 1120 [--every 1]
    survey.py review  --project P --pieces out/pieces.json   2-3 thumbs of EVERY piece in the cut
    survey.py speech  (not a script — use Palmier inspect_media per clip, language=en, maxFrames=1)

Funnel: sheets (20 s) -> scan flags -> zoom (1-2 s) only where needed -> build plan ->
review the plan's pieces BEFORE assembling. The review step is where hands over the lens,
phone-in-face moments and walls at clip ends get caught; skipping it cost three fix-up rounds.
"""
import argparse, json, os, re, subprocess, statistics as st, pathlib, concurrent.futures as cf
from PIL import Image, ImageDraw, ImageFont

def proxies(project):
    inv = json.loads((pathlib.Path(project) / "inventory.json").read_text())
    return inv["proxies"], inv["videos"]

def grab(src, t, out, w):
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1",
                        "-vf", f"scale={w}:-2", out])
    return out

def tile(items, out, cols, w):
    """items: [(path, label)]"""
    ims = []
    for p, lab in items:
        try: im = Image.open(p).convert("RGB")
        except Exception: continue
        d = ImageDraw.Draw(im); f = ImageFont.load_default()
        d.rectangle([0, 0, len(lab) * 6 + 6, 12], fill="black"); d.text((3, 0), lab, fill="yellow", font=f)
        ims.append(im)
    if not ims: return None
    h = ims[0].height; rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), "black")
    for i, im in enumerate(ims): sheet.paste(im.resize((w, h)), ((i % cols) * w, (i // cols) * h))
    sheet.save(out, quality=82); return out

def mmss(t): return f"{int(t)//60}:{int(t)%60:02d}"

def sheets(a):
    P, V = proxies(a.project); out = pathlib.Path(a.project) / "survey"
    for cid, src in sorted(P.items()):
        dur = V.get(cid, {}).get("duration") or 0
        d = out / cid; d.mkdir(parents=True, exist_ok=True)
        ts = [t for t in range(0, int(dur), a.every)] or [0]
        with cf.ThreadPoolExecutor(8) as ex:
            items = list(ex.map(lambda t: (grab(src, t, str(d / f"{t:05d}.jpg"), 300), f"{cid} {mmss(t)}"), ts))
        for k in range(0, len(items), 36):
            print(tile(items[k:k + 36], str(d / f"sheet_{k//36:02d}.jpg"), 6, 300))

def scan(a):
    P, _ = proxies(a.project); out = pathlib.Path(a.project) / "survey" / "scan"; out.mkdir(parents=True, exist_ok=True)
    def run(item):
        cid, src = item; meta = out / f"{cid}.meta"
        if not meta.exists():
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", src, "-vf",
                            f"fps=2,scale=160:90,signalstats,select='gte(scene,0)',metadata=print:file={meta}",
                            "-an", "-f", "null", "-"])
        rows, cur = [], {}
        for line in open(meta):
            m = re.search(r"pts_time:([\d.]+)", line)
            if m:
                if cur: rows.append(cur)
                cur = {"t": float(m.group(1))}; continue
            m = re.match(r"lavfi\.(scene_score|signalstats\.YAVG)=([\d.]+)", line.strip())
            if m: cur[m.group(1)] = float(m.group(2))
        if cur: rows.append(cur)
        win = []
        for w in range(0, int(rows[-1]["t"]) + 1, 10):
            s = [r for r in rows if w <= r["t"] < w + 10]
            if s: win.append((w, st.mean(r.get("scene_score", 0) for r in s), max(r.get("scene_score", 0) for r in s),
                              st.mean(r.get("signalstats.YAVG", 0) for r in s)))
        med = st.median(x[1] for x in win)
        flags = [f"{mmss(w)}" for w, m, x, y in win if m > max(3 * med, .08) or x > .5 or y < 25]
        return cid, flags
    with cf.ThreadPoolExecutor(4) as ex:
        for cid, flags in ex.map(run, sorted(P.items())):
            print(f"{cid}: zoom on {' '.join(flags) or '— nothing flagged'}")
    print("Flags are candidates (whips, drops, covered lens). Spikes miss slow problems — an upside-"
          "down camera or a hand held over the lens — so the review step still matters.")

def zoom(a):
    P, _ = proxies(a.project); src = P[a.clip]
    d = pathlib.Path(a.project) / "survey" / "zoom" / f"{a.clip}_{int(a.start)}"; d.mkdir(parents=True, exist_ok=True)
    ts, t = [], a.start
    while t < a.end: ts.append(t); t += a.every
    items = [(grab(src, t, str(d / f"{t:08.2f}.jpg"), 180), f"{a.clip} {mmss(t)}") for t in ts]
    print(tile(items, str(d / "sheet.jpg"), 10, 180))

def review(a):
    P, _ = proxies(a.project); pieces = json.loads(pathlib.Path(a.pieces).read_text())["pieces"]
    d = pathlib.Path(a.project) / "survey" / "review"; d.mkdir(parents=True, exist_ok=True)
    jobs = []
    for i, p in enumerate(pieces):
        if p["kind"] == "photo": continue
        L = p["e"] - p["s"]; fr = (0.15, 0.85) if L <= 20 else (0.1, 0.5, 0.9)
        for k, x in enumerate(fr):
            t = p["s"] + L * x
            jobs.append((P[p["clip"]], t, str(d / f"{i:03d}_{k}.jpg"),
                         f"{i} {p['clip']} {mmss(t)} {dict(H='H', walk='w', burst='B').get(p['kind'], '?')}"))
    with cf.ThreadPoolExecutor(8) as ex:
        items = list(ex.map(lambda j: (grab(j[0], j[1], j[2], 160), j[3]), jobs))
    for k in range(0, len(items), 96):
        print(tile(items[k:k + 96], str(d / f"sheet_{k//96}.jpg"), 12, 160))
    print("Look for: hands/fingers over the lens, phone held in front, sky/upside-down, walls, black. "
          "Fix in the plan (cut range / move a burst), re-run plan.py, review again.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("sheets", "scan", "zoom", "review"):
        s = sub.add_parser(n); s.add_argument("--project", required=True)
        if n == "sheets": s.add_argument("--every", type=int, default=20)
        if n == "zoom":
            s.add_argument("--clip", required=True); s.add_argument("--start", type=float, required=True)
            s.add_argument("--end", type=float, required=True); s.add_argument("--every", type=float, default=1)
        if n == "review": s.add_argument("--pieces", required=True)
    a = ap.parse_args(); globals()[a.cmd](a)
