#!/usr/bin/env python3
"""Probe source videos and report the DISPLAY geometry, not the stored geometry.

Phone video is routinely stored landscape with a rotation flag. ffprobe's raw
width/height is the stored frame, so a portrait clip reads as 1920x1080 and you
build a landscape project by mistake. This applies the rotation and reports what
a viewer actually sees, plus the canvas you should set on the timeline.

Usage:
    probe_sources.py FILE [FILE ...]
    probe_sources.py --json FILE [FILE ...]
"""
import json
import subprocess
import sys
from fractions import Fraction


def ffprobe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {out.stderr.strip()}")
    return json.loads(out.stdout)


def rotation_of(stream):
    """Rotation in degrees, from either the tag or the display matrix."""
    tag = stream.get("tags", {}).get("rotate")
    if tag is not None:
        try:
            return int(float(tag)) % 360
        except ValueError:
            pass
    for sd in stream.get("side_data_list", []) or []:
        if "rotation" in sd:
            return int(round(float(sd["rotation"]))) % 360
    return 0


def describe(path):
    data = ffprobe(path)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if video is None:
        raise RuntimeError(f"{path} has no video stream")

    stored_w, stored_h = int(video["width"]), int(video["height"])
    rot = rotation_of(video)
    # 90 and 270 swap the axes; 0 and 180 do not.
    disp_w, disp_h = (stored_h, stored_w) if rot in (90, 270) else (stored_w, stored_h)

    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
    try:
        fps = float(Fraction(rate)) if Fraction(rate) != 0 else None
    except ZeroDivisionError:
        fps = None

    duration = float(data["format"].get("duration", 0) or 0)
    return {
        "path": path,
        "duration_seconds": round(duration, 3),
        "duration_hms": f"{int(duration // 3600)}:{int(duration % 3600 // 60):02d}:{duration % 60:05.2f}",
        "stored": [stored_w, stored_h],
        "rotation": rot,
        "display": [disp_w, disp_h],
        "orientation": "portrait" if disp_h > disp_w else ("square" if disp_h == disp_w else "landscape"),
        "container_fps": round(fps, 3) if fps else None,
        "codec": video.get("codec_name"),
        "has_audio": audio is not None,
        "audio_codec": audio.get("codec_name") if audio else None,
        "size_bytes": int(data["format"].get("size", 0) or 0),
    }


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return 2

    results, problems = [], []
    for p in paths:
        try:
            results.append(describe(p))
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller verbatim
            problems.append(f"{p}: {exc}")

    if as_json:
        print(json.dumps({"sources": results, "problems": problems}, indent=2))
        return 1 if problems else 0

    for r in results:
        print(f"\n{r['path']}")
        print(f"  duration   {r['duration_hms']}  ({r['duration_seconds']}s)")
        print(f"  stored     {r['stored'][0]}x{r['stored'][1]}   rotation {r['rotation']}deg")
        print(f"  DISPLAY    {r['display'][0]}x{r['display'][1]}   <- {r['orientation']}")
        print(f"  fps        {r['container_fps']}   codec {r['codec']}")
        print(f"  audio      {'yes (' + str(r['audio_codec']) + ')' if r['has_audio'] else 'NO AUDIO'}")
        print(f"  size       {r['size_bytes'] / 1e9:.2f} GB")
        if r["stored"] != r["display"]:
            print("  NOTE       stored != display. Trust DISPLAY. A rotation flag is in play.")

    if results:
        shapes = {tuple(r["display"]) for r in results}
        print("\n" + "=" * 60)
        if len(shapes) == 1:
            w, h = shapes.pop()
            print(f"CANVAS: set the project to {w}x{h} BEFORE placing any clip.")
            print("Adding the first clip can pull the project to the media's geometry;")
            print("setting it up front keeps text sizing predictable.")
        else:
            print("MIXED ORIENTATIONS across sources:")
            for r in results:
                print(f"  {r['display'][0]}x{r['display'][1]}  {r['path']}")
            print("Pick the canvas deliberately and plan how the odd ones out are framed.")
        total = sum(r["duration_seconds"] for r in results)
        print(f"TOTAL RUNTIME: {total / 60:.1f} minutes across {len(results)} source(s).")

    for p in problems:
        print(f"\nPROBLEM  {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
