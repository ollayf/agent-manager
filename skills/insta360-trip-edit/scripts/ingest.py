#!/usr/bin/env python3
"""Copy an Insta360 card to local storage — READ-ONLY on the camera — and inventory it.

    ingest.py --src /Volumes/<CARD>/DCIM/Camera01 --project <project dir> [--copy] [--verify]

Steps (each safe to re-run):
  --copy     rsync the card into <project>/storage/Camera01 (never --delete, skips ._ files).
             Long: run it in the background. The camera is only ever read.
  --verify   compare every camera file against the copy by size; list what is missing.
  (always)   hard-link each .lrv proxy as proxies/<stem>_proxy.mp4 (Palmier rejects .lrv),
             write inventory.json (+ a printed table) and say which apps still hold files
             open on the card, with the eject command.

The inventory is what the survey and the plan read. It is stamped with the skill version.
"""
import argparse, json, os, re, subprocess, sys, pathlib, datetime

SKILL_VERSION = (pathlib.Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()

def probe(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "format=duration:stream=codec_type,width,height,r_frame_rate",
                              "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
        j = json.loads(out); v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), {})
        n, d = (v.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
        return dict(duration=round(float(j["format"].get("duration", 0)), 3), width=v.get("width"),
                    height=v.get("height"), fps=round(float(n) / float(d or 1), 3) if float(d or 1) else None,
                    has_audio=any(s.get("codec_type") == "audio" for s in j.get("streams", [])))
    except Exception as e:
        return dict(error=str(e))

def stamp(name):
    """VID_20261031_101120_005 -> ('005', datetime)"""
    m = re.match(r"(?:VID|LRV|IMG)_(\d{8})_(\d{6})_(\d+)", name)
    if not m: return None, None
    return m.group(3), datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True); ap.add_argument("--project", required=True)
    ap.add_argument("--copy", action="store_true"); ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    src = pathlib.Path(a.src); proj = pathlib.Path(a.project).resolve()
    dst = proj / "storage" / "Camera01"; prox = proj / "proxies"
    dst.mkdir(parents=True, exist_ok=True); prox.mkdir(exist_ok=True)

    if a.copy:
        # NEVER --delete, never write to src. Trailing slashes copy contents.
        subprocess.run(["rsync", "-a", "--exclude", "._*", f"{src}/", f"{dst}/"], check=True)
        print("COPY_DONE")

    missing = []
    if src.exists():
        for f in sorted(src.iterdir()):
            if f.name.startswith(".") or not f.is_file(): continue
            c = dst / f.name
            if not c.exists() or c.stat().st_size != f.stat().st_size: missing.append(f.name)
    if a.verify:
        print("VERIFY:", "all files copied at full size" if not missing else f"{len(missing)} missing/short: {missing}")

    inv = dict(skill_version=SKILL_VERSION, format=1, project=str(proj), videos={}, photos={}, proxies={})
    for f in sorted(dst.iterdir()):
        cid, t = stamp(f.name)
        if f.suffix.lower() == ".lrv" and cid:
            link = prox / f"{f.stem.replace('LRV_', '')}_proxy.mp4"
            if not link.exists(): os.link(f, link)
            inv["proxies"][cid] = str(link)
        elif f.suffix.lower() == ".mp4" and f.name.startswith("VID_") and cid:
            p = probe(f); p.update(file=str(f), start=t.isoformat() if t else None,
                                   mtime_end=datetime.datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"))
            p["likely_test"] = (p.get("duration") or 0) < 30
            inv["videos"][cid] = p
        elif f.suffix.lower() in (".jpg", ".jpeg", ".insp", ".dng") and cid:
            inv["photos"][cid] = dict(file=str(f), taken=t.isoformat() if t else None)
    (proj / "inventory.json").write_text(json.dumps(inv, indent=1))

    print(f"\n{'clip':5} {'start':16} {'dur':>8} {'res':>10} {'fps':>6}  proxy  note")
    total = 0
    for cid, v in inv["videos"].items():
        d = v.get("duration") or 0; total += d
        print(f"{cid:5} {(v.get('start') or '')[:16]:16} {int(d)//60:5d}:{int(d)%60:02d} "
              f"{v.get('width')}x{v.get('height'):<5} {v.get('fps') or '':>6}  "
              f"{'yes' if cid in inv['proxies'] else 'NO ':5}  {'short — probably a test clip' if v['likely_test'] else ''}")
    print(f"total video {total/60:.1f} min · {len(inv['photos'])} photos → inventory.json")
    # Same-start-time or overlapping clips: order by mtime_end, not by filename.
    if missing and not a.verify: print(f"note: {len(missing)} camera files not copied yet (copy still running?)")
    if src.exists():
        held = subprocess.run(f"lsof +D '{src.parent.parent}' 2>/dev/null | awk 'NR>1{{print $1}}' | sort -u",
                              shell=True, capture_output=True, text=True).stdout.split()
        if held: print(f"apps holding card files open: {', '.join(held)} — close them before ejecting")
        print(f"eject when done: diskutil eject '{src.parent.parent}'")

if __name__ == "__main__":
    sys.exit(main())
