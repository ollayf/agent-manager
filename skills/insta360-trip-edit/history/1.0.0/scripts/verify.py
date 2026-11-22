#!/usr/bin/env python3
"""Check the EXPORTED file, not the preview. Frames where defects live + audio levels + length.

    verify.py EXPORT.mp4 --plan OUT [--out verify/]

  - duration must equal pieces.json total_frames (± 2 frames)
  - one sheet: every day card (at 3.5 s in), every place label (at 1.5 s in), first+last burst tag
  - audio: mean volume in 3 bursts (expect music only, quieter) vs 3 normal-speed pieces
Then LOOK at the sheet. Reading the numbers is not verification.
"""
import argparse, json, subprocess, pathlib, re, sys
from PIL import Image, ImageDraw
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("export"); ap.add_argument("--plan", required=True); ap.add_argument("--out", default="verify")
a = ap.parse_args(); plan = pathlib.Path(a.plan); out = pathlib.Path(a.out); out.mkdir(exist_ok=True)
P = json.loads((plan / "pieces.json").read_text()); PL = json.loads((plan / "placements.json").read_text())["placements"]
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.export],
                           capture_output=True, text=True).stdout or 0)
want = P["total_frames"] / 30; ok = abs(dur - want) < 0.1
print(f"duration {dur:.2f}s vs plan {want:.2f}s -> {'OK' if ok else 'MISMATCH (timeline edited after planning?)'}")
pts = [(x[1] / 30 + 3.5, x[0]) for x in PL if x[0].startswith("card")] + [(x[1] / 30 + 1.5, x[0]) for x in PL if x[0].startswith("loc")]
ff = [x for x in PL if x[0].startswith("ff")]; pts += [(x[1] / 30 + 2, x[0]) for x in (ff[:1] + ff[-1:])]
tiles = []
for t, lab in sorted(pts):
    f = out / f"{t:08.2f}.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", a.export, "-frames:v", "1", "-vf", "scale=480:-2", str(f)])
    try:
        im = Image.open(f); ImageDraw.Draw(im).text((4, 2), f"{int(t)//60}:{int(t)%60:02d} {lab}", fill="yellow"); tiles.append(im)
    except Exception: pass
if tiles:
    cols = 4; rows = (len(tiles) + cols - 1) // cols; w, h = tiles[0].size
    s = Image.new("RGB", (cols * w, rows * h)); [s.paste(im, ((i % cols) * w, (i // cols) * h)) for i, im in enumerate(tiles)]
    s.save(out / "sheet.jpg", quality=82); print("look at:", out / "sheet.jpg")
def vol(t0, t1):
    r = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{t0:.2f}", "-t", f"{t1-t0:.2f}", "-i", a.export, "-af", "volumedetect",
                        "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: ([-\d.]+)", r); return float(m.group(1)) if m else None
bursts = [p for p in P["pieces"] if p["kind"] == "burst"][:3]; normal = [p for p in P["pieces"] if p["kind"] == "H"][:3]
bv = [vol(p["f0"] / 30 + .3, p["f1"] / 30 - .3) for p in bursts]; nv = [vol(p["f0"] / 30 + .3, min(p["f1"] / 30, p["f0"] / 30 + 15)) for p in normal]
print("bursts (music only) dB:", bv, "  normal-speed dB:", nv)
if bv and nv and max(x for x in bv if x is not None) > min(x for x in nv if x is not None):
    print("WARNING: a burst is as loud as normal speech — is the camera audio really muted in bursts?")
sys.exit(0 if ok else 1)
