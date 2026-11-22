#!/usr/bin/env python3
"""trip.json -> every number the edit needs. No frame arithmetic by hand, ever.

    plan.py trip.json --out OUT [--media media.json] [--music music.json]

Writes into OUT/:
  pieces.json          every piece of the cut with its timeline frames (stamped)
  palmier/add_main.json      1x pieces + photos, spaced apart (first add_clips, no trackIndex)
  palmier/add_bursts_N.json  burst pieces, <=30 per file, includeAudio=false, trackIndex 0
  palmier/gaps.json          ranges to close with ripple_delete_ranges after speeds are set
  palmier/music.json         music bed entries filling the whole cut (if --music)
  overlays.json        day cards, place labels, burst tags -> overlays/gen.py
  placements.json      [id, startFrame, frames] for every overlay on the final timeline
  clipmap.md           per-clip table: source time | what happens | treatment | in final video

trip.json (see references/plan-format.md):
  {"fps":30, "pattern":{"burst_src":12,"burst_speed":2,"nice":[6,12],"boring":[4,40]},
   "days":[{"day":1,"start":["005",9.5],"kicker":"DAY 01","word":"Asakusa","local":"浅草",
            "label":"Sat · 31 Oct 2026 · Tokyo","intro":"..."}],
   "segments":[{"clip":"005","s":9.5,"e":200,"kind":"nice","tag":"exploring asakusa","what":"..."},
               {"clip":"005","s":677,"e":697,"kind":"cut","what":"fiddling with camera"}, ...],
   "labels":[["005",200,"Kobe beef stand",null], ...],
   "photos":{"godzilla":{"file":"photos/godzilla_push.mp4"}}}

kind: H (1x, sound on) | nice (beats + bursts) | boring (short beat, burst, skip ahead) |
      walk (one plain 1x piece) | photo (clip "photo:<name>", s=0, e=seconds) | cut (documented only)
"""
import argparse, json, re, pathlib, datetime, sys

SKILL_VERSION = (pathlib.Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()
FORMAT = 1

def pieces(T):
    pat = T.get("pattern", {}); B = pat.get("burst_src", 12); SP = pat.get("burst_speed", 2)
    PAT = {"nice": tuple(pat.get("nice", (6, 12))), "boring": tuple(pat.get("boring", (4, 40)))}
    out = []
    for i, g in enumerate(T["segments"]):
        k = g["kind"]
        if k == "cut": continue
        base = dict(clip=g["clip"], seg=i)
        if k in ("H", "walk", "photo"):
            out.append(dict(base, s=g["s"], e=g["e"], speed=1, kind=k)); continue
        beat, skip = g.get("beat", PAT[k][0]), g.get("skip", PAT[k][1])
        shift = {float(x): float(y) for x, y in g.get("burst_shift", {}).items()}
        pos, e = g["s"], g["e"]
        while e - pos > 0.5:
            one = min(beat, e - pos)
            if e - (pos + one) < B:                       # no room for a full burst: end on a 1x beat
                out.append(dict(base, s=pos, e=pos + min(e - pos, beat + 4), speed=1, kind="walk")); break
            out.append(dict(base, s=pos, e=pos + one, speed=1, kind="walk")); pos += one
            bs = shift.get(pos, pos)                      # move a burst off a bad moment, same length
            out.append(dict(base, s=bs, e=bs + B, speed=SP, kind="burst", tag=g.get("tag"))); pos += B + skip
    return out

def layout(P, fps):
    f = 0
    for p in P:
        p["f0"] = f; p["frames"] = round((p["e"] - p["s"]) * fps / p["speed"]); f += p["frames"]; p["f1"] = f
    return f

FPS = 30
def at(P, clip, src):
    for p in P:
        if p["clip"] == clip and p["e"] > src:
            return p["f0"] if p["s"] >= src else p["f0"] + round((src - p["s"]) * FPS / p["speed"])
    raise KeyError(f"{clip}@{src} is not in the cut")

def slug(t): return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")
def ts(sec): sec = int(round(sec)); return f"{sec//60}:{sec%60:02d}" if sec < 3600 else f"{sec//3600}:{sec%3600//60:02d}:{sec%60:02d}"

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trip"); ap.add_argument("--out", required=True)
    ap.add_argument("--media", help='{"005":"<mediaRef>", "photo:godzilla":"<mediaRef>"}')
    ap.add_argument("--music", help='[{"mediaRef":"..","duration":159.19}, ...] rotated under the cut')
    a = ap.parse_args()
    T = json.loads(pathlib.Path(a.trip).read_text()); fps = T.get("fps", 30)
    global FPS; FPS = fps
    out = pathlib.Path(a.out); (out / "palmier").mkdir(parents=True, exist_ok=True)
    M = json.loads(pathlib.Path(a.media).read_text()) if a.media else {}
    P = pieces(T); total = layout(P, fps)
    stamp = dict(skill_version=SKILL_VERSION, format=FORMAT, generated=datetime.datetime.now().isoformat(timespec="seconds"))

    # --- Palmier batches: place at 1x lengths with a 3-frame spacer, speed bursts, then ripple the gaps.
    f = 0
    for p in P: p["pf"] = f; f += round((p["e"] - p["s"]) * fps) + 3
    ref = lambda p: M.get(p["clip"], f"<{p['clip']}>")
    main = [dict(mediaRef=ref(p), source=[round(p["s"], 3), round(p["e"], 3)], startFrame=p["pf"],
                 **({"includeAudio": False} if p["kind"] == "photo" else {})) for p in P if p["kind"] != "burst"]
    (out / "palmier/add_main.json").write_text(json.dumps(main))
    B = [p for p in P if p["kind"] == "burst"]
    for k in range(0, len(B), 30):
        (out / f"palmier/add_bursts_{k//30}.json").write_text(json.dumps(
            [dict(mediaRef=ref(p), source=[round(p["s"], 3), round(p["e"], 3)], startFrame=p["pf"],
                  trackIndex=0, includeAudio=False) for p in B[k:k + 30]]))
    gaps = []
    for x, y in zip(P, P[1:]):
        end = x["pf"] + x["frames"]
        if y["pf"] > end: gaps.append([end, y["pf"]])
    (out / "palmier/gaps.json").write_text(json.dumps(gaps))

    if a.music:
        import math
        tracks = json.loads(pathlib.Path(a.music).read_text()); f, i, mus = 0, 0, []
        while f < total:
            t = tracks[i % len(tracks)]; L = math.ceil(t["duration"] * fps)
            if f + L > total:
                mus.append(dict(mediaRef=t["mediaRef"], source=[0, round((total - f) / fps, 3)], startFrame=f)); break
            mus.append(dict(mediaRef=t["mediaRef"], source=[0, round(t["duration"] - .05, 3)], startFrame=f)); f += L; i += 1
        (out / "palmier/music.json").write_text(json.dumps(mus))

    # --- Overlays
    items, place = [], []
    day_of = {}
    for d in T.get("days", []):
        i = f"card_d{d['day']}"; f0 = at(P, *d["start"])
        items.append(dict(kind="card", id=i, kicker=d["kicker"], word=d["word"], jp=d.get("local"),
                          label=d["label"], intro=d.get("intro"), dur=d.get("dur", 5.0)))
        place.append([i, f0, round(d.get("dur", 5.0) * fps)])
        day_of[d["start"][0]] = d
    # each clip inherits the day of the nearest earlier card
    order = [g["clip"] for g in T["segments"]]; cur = None; clip_day = {}
    for c in order:
        if c in day_of: cur = day_of[c]
        clip_day.setdefault(c, cur)
    cards = [(f0, f0 + n) for i, f0, n in place]
    for n, (c, s, name, jp) in enumerate(T.get("labels", [])):
        i = f"loc_{n:02d}"; f0 = at(P, c, s); d = clip_day.get(c)
        for c0, c1 in cards:
            if c0 <= f0 < c1: f0 = c1 + 6
        kick = f"Day {d['day']} · {d.get('short', '')}".rstrip(" ·") if d else ""
        items.append(dict(kind="loc", id=i, kicker=kick, name=name, jp=jp, dur=4.8))
        place.append([i, f0, 144])
    tags = {}
    for p in B:
        t = p.get("tag") or "walking"; i = tags.setdefault(t, "ff_" + slug(t))
        place.append([i, p["f0"], p["frames"]])
    for t, i in tags.items(): items.append(dict(kind="ff", id=i, text=t, speed=f"{T.get('pattern',{}).get('burst_speed',2)}×",
                                                dur=round(B[0]["frames"] / fps, 3) if B else 6))
    place.sort(key=lambda x: x[1])
    titles = [x for x in place if not x[0].startswith("ff_")]
    clash = [(x[0], y[0]) for x, y in zip(titles, titles[1:]) if x[1] + x[2] > y[1]]
    (out / "overlays.json").write_text(json.dumps(items, ensure_ascii=False, indent=0))
    (out / "placements.json").write_text(json.dumps(dict(stamp, placements=place)))
    (out / "pieces.json").write_text(json.dumps(dict(stamp, total_frames=total, pieces=P), indent=0))

    # --- Clip map: the "convince me you understood it" table
    rows = ["| Clip | Source | What happens | Treatment | In final video |", "|---|---|---|---|---|"]
    sym = dict(H="▶ normal", nice="⏩ mixed", boring="⏩ skims ahead", walk="▶ normal", photo="🖼 photo", cut="✂ cut")
    for i, g in enumerate(T["segments"]):
        mine = [p for p in P if p["seg"] == i]
        where = f"{ts(mine[0]['f0']/fps)}–{ts(mine[-1]['f1']/fps)}" if mine else "—"
        rows.append(f"| {g['clip']} | {ts(g['s'])}–{ts(g['e'])} | {g.get('what','')} | {sym[g['kind']]} | {where} |")
    (out / "clipmap.md").write_text("\n".join(rows) + "\n")

    n = {k: sum(1 for p in P if p["kind"] == k) for k in ("H", "walk", "burst", "photo")}
    print(f"pieces={len(P)} {n} total={total} frames = {ts(total/fps)} · bursts in {len(range(0,len(B),30))} batch file(s)"
          f" · {len(gaps)} gaps · {len(items)} overlays ({len(tags)} burst tags)")
    if clash: print("WARNING overlapping titles/labels:", clash); return 1
    if not M: print("note: no --media given, mediaRefs are <clip> placeholders")
    return 0

if __name__ == "__main__":
    sys.exit(main())
