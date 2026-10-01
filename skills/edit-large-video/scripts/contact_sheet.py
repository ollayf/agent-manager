#!/usr/bin/env python3
"""Sample frames from a video into timestamped contact sheets.

You cannot watch 67 minutes of footage, and you should not try. Sampling a frame
every N seconds and tiling them tells you in one look where the dead footage is
(pockets, walls, ceilings), where people are on camera, and where the light
changes. Every tile is stamped with its timestamp so you can go straight from a
tile you like to a source range in the cut list.

Also works on a finished export, which is the only honest way to check what
actually rendered -- pass --label-seconds to stamp plain seconds instead of mm:ss.

Usage:
    contact_sheet.py VIDEO --out DIR [--every 30] [--cols 4] [--per-sheet 20]
    contact_sheet.py VIDEO --out DIR --at 12,45,300,412      # explicit moments
    contact_sheet.py VIDEO --out DIR --start 600 --end 900 --every 5

Requires ffmpeg on PATH. Grabs are input-seeks (fast) and run in parallel.
"""
import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys


def duration_of(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {out.stderr.strip()}")
    return float(out.stdout.strip())


def stamp(seconds, plain):
    if plain:
        return f"{int(seconds)}s"
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def _escape(text):
    """Make a string safe inside ffmpeg drawtext's single-quoted text= option.

    A literal apostrophe cannot be backslash-escaped there -- the quoting is
    handled by the filtergraph parser before drawtext sees it, so \' ends the
    string early and the remaining filter options leak into the rendered label.
    Swapping in a typographic apostrophe sidesteps the parser entirely and looks
    better anyway. Colons, backslashes and percent signs still need escaping.
    """
    return (text.replace("\\", r"\\")
                .replace("'", "\u2019")
                .replace("%", r"\%")
                .replace(":", r"\:"))


def grab(video, seconds, out_path, width, label, prefix):
    text = _escape(f"{prefix}{label}")
    vf = (
        f"scale={width}:-2,"
        f"drawtext=text='{text}':x=8:y=8:fontsize=22:fontcolor=yellow:"
        f"box=1:boxcolor=black@0.65:boxborderw=5"
    )
    res = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{seconds}", "-i", video,
         "-frames:v", "1", "-vf", vf, "-q:v", "4", "-y", out_path],
        capture_output=True, text=True,
    )
    return out_path if res.returncode == 0 and os.path.exists(out_path) else None


def tile(paths, out_path, cols):
    """Tile with ImageMagick if present (handles ragged rows), else ffmpeg xstack."""
    if shutil.which("montage"):
        res = subprocess.run(
            ["montage", *paths, "-tile", f"{cols}x", "-geometry", "+2+2",
             "-background", "#111111", out_path],
            capture_output=True, text=True,
        )
        if res.returncode == 0:
            return True
    # xstack needs a full grid, so pad the last row by repeating the final frame.
    n = len(paths)
    if n < 2:
        shutil.copy(paths[0], out_path)
        return True
    rows = (n + cols - 1) // cols
    padded = list(paths) + [paths[-1]] * (rows * cols - n)
    layout = []
    for i in range(len(padded)):
        r, c = divmod(i, cols)
        x = "0" if c == 0 else "+".join(["w0"] * c)
        y = "0" if r == 0 else "+".join(["h0"] * r)
        layout.append(f"{x}_{y}")
    inputs = []
    for p in padded:
        inputs += ["-i", p]
    fc = ("".join(f"[{i}:v]" for i in range(len(padded)))
          + f"xstack=inputs={len(padded)}:layout=" + "|".join(layout) + "[v]")
    res = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", fc,
         "-map", "[v]", "-q:v", "4", out_path],
        capture_output=True, text=True,
    )
    return res.returncode == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--out", required=True, help="output directory for sheets")
    ap.add_argument("--every", type=float, default=30.0, help="seconds between samples")
    ap.add_argument("--at", help="comma-separated explicit timestamps in seconds")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--per-sheet", type=int, default=20)
    ap.add_argument("--width", type=int, default=320, help="tile width in px")
    ap.add_argument("--prefix", default="", help="text prefix on every tile, e.g. 'A '")
    ap.add_argument("--label-seconds", action="store_true",
                    help="stamp plain seconds instead of mm:ss")
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()

    if args.at:
        times = [float(t) for t in args.at.split(",") if t.strip()]
    else:
        end = args.end if args.end is not None else duration_of(args.video)
        times, t = [], args.start
        while t < end:
            times.append(round(t, 3))
            t += args.every
    if not times:
        print("no sample points", file=sys.stderr)
        return 2

    frames_dir = os.path.join(args.out, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    jobs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for i, t in enumerate(times):
            path = os.path.join(frames_dir, f"{i:05d}_{int(t):06d}.jpg")
            jobs.append(pool.submit(grab, args.video, t, path, args.width,
                                    stamp(t, args.label_seconds), args.prefix))
        grabbed = [f.result() for f in jobs]

    got = [(t, p) for t, p in zip(times, grabbed) if p]
    missed = [t for t, p in zip(times, grabbed) if not p]

    sheets = []
    for i in range(0, len(got), args.per_sheet):
        chunk = [p for _, p in got[i:i + args.per_sheet]]
        sheet = os.path.join(args.out, f"sheet_{i // args.per_sheet:02d}.jpg")
        if tile(chunk, sheet, args.cols):
            sheets.append({
                "sheet": sheet,
                "first_timestamp": got[i][0],
                "last_timestamp": got[min(i + args.per_sheet, len(got)) - 1][0],
                "tiles": len(chunk),
            })

    print(json.dumps({
        "video": args.video,
        "sampled": len(got),
        "missed_timestamps": missed,
        "sheets": sheets,
    }, indent=2))
    print(f"\n{len(sheets)} sheet(s) in {args.out} -- open them, "
          f"or Read them if you are an agent.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
