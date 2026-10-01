#!/usr/bin/env python3
"""Look at the exported file, not the timeline.

The editor's preview and the exported frames are not the same picture. Text
background chips render in the export but not in the preview pane; wrapping is
resolved at render time; a clip deleted by hand can silently take a fade with it.
Every defect that ever shipped from this workflow was visible in the export and
invisible in the manifest, so this is the last gate before you hand the file over.

By default it samples the middle of every title and a spread of captions from the
plan file -- those are exactly the frames where text defects live. It also checks
the export's duration against the timeline you think you built.

Usage:
    verify_export.py EXPORT.mp4 --plan PLAN.json --out DIR
    verify_export.py EXPORT.mp4 --out DIR --every 45
    verify_export.py EXPORT.mp4 --out DIR --at 3,156,300,578

Then LOOK at the sheets it writes. Reading the JSON is not verification.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from contact_sheet import duration_of, grab, tile  # noqa: E402


def sample_points(plan, fps, duration):
    """Midpoint of every title, plus a spread of captions. These are where text breaks."""
    pts = []
    for t in plan.get("titles", []):
        mid = (int(t["start"]) + int(t["end"])) / 2 / fps
        pts.append((round(mid, 2), f'T: {t["text"].splitlines()[0][:28]}'))
    caps = plan.get("captions", [])
    if caps:
        # longest captions first -- they are the ones that wrap badly
        by_len = sorted(caps, key=lambda c: -len(c["text"]))[:12]
        for c in by_len:
            mid = (int(c["start"]) + int(c["end"])) / 2 / fps
            pts.append((round(mid, 2), f'C: {c["text"].splitlines()[0][:28]}'))
    pts = [(t, lbl) for t, lbl in pts if 0 <= t < duration]
    pts.sort(key=lambda x: x[0])
    return pts


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export")
    ap.add_argument("--out", required=True)
    ap.add_argument("--plan", help="the plan file used to build the edit")
    ap.add_argument("--at", help="comma-separated seconds to sample")
    ap.add_argument("--every", type=float, help="sample every N seconds instead")
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--per-sheet", type=int, default=15)
    ap.add_argument("--width", type=int, default=300)
    args = ap.parse_args()

    if not os.path.exists(args.export):
        print(f"no such file: {args.export}", file=sys.stderr)
        return 2

    duration = duration_of(args.export)
    problems = []

    plan = None
    if args.plan:
        with open(args.plan) as fh:
            plan = json.load(fh)
        fps = plan.get("fps", 30)
        expected_frames = 0
        f = 0
        for c in plan.get("clips", []):
            if "start_frame" in c:
                f = int(c["start_frame"])
            if "source" in c:
                f += int(round((float(c["source"][1]) - float(c["source"][0])) * fps))
            elif "duration_frames" in c:
                f += int(c["duration_frames"])
        expected_frames = f
        expected = expected_frames / fps
        drift = abs(duration - expected)
        if drift > 0.5:
            problems.append(
                f"duration mismatch: export is {duration:.2f}s but the plan describes "
                f"{expected:.2f}s ({expected_frames} frames). A clip was dropped, trimmed, "
                f"or the export covered a different timeline.")
        else:
            print(f"duration    {duration:.2f}s matches the plan ({expected:.2f}s)")

    if args.at:
        points = [(float(t), f"{float(t):g}s") for t in args.at.split(",") if t.strip()]
    elif args.every:
        points, t = [], 0.0
        while t < duration:
            points.append((round(t, 2), f"{int(t)}s"))
            t += args.every
    elif plan:
        points = sample_points(plan, plan.get("fps", 30), duration)
    else:
        step = max(1.0, duration / 20)
        points, t = [], 0.0
        while t < duration:
            points.append((round(t, 2), f"{int(t)}s"))
            t += step

    frames_dir = os.path.join(args.out, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    got = []
    for i, (t, label) in enumerate(points):
        path = os.path.join(frames_dir, f"{i:04d}_{int(t):06d}.jpg")
        if grab(args.export, t, path, args.width, label, ""):
            got.append((t, path, label))

    sheets = []
    for i in range(0, len(got), args.per_sheet):
        chunk = [p for _, p, _ in got[i:i + args.per_sheet]]
        sheet = os.path.join(args.out, f"verify_{i // args.per_sheet:02d}.jpg")
        if tile(chunk, sheet, args.cols):
            sheets.append(sheet)

    print(f"sampled     {len(got)} of {len(points)} points")
    if len(got) < len(points):
        problems.append(f"{len(points) - len(got)} frame grab(s) failed -- "
                        f"the export may be truncated or corrupt")
    for s in sheets:
        print(f"sheet       {s}")

    for p in problems:
        print(f"\nFAIL   {p}")

    print("\nNow LOOK at the sheets. You are checking for:")
    print("  - text on three lines, or a word orphaned onto its own line")
    print("  - a title and the caption under it saying the same thing")
    print("  - text running outside the frame, or sitting over a face")
    print("  - the last shot: does it fade, or does it just stop?")
    print("  - anything unreadable against the footage behind it")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
