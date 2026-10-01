#!/usr/bin/env python3
"""Validate an edit plan and emit ready-to-send Palmier tool arguments.

The point is to stop doing frame arithmetic in your head. Give it the cut list in
source seconds and the text in timeline frames, and it computes every startFrame,
proves the plan is internally consistent, and prints the JSON for add_clips and
add_texts. Every check here corresponds to a defect that shipped at least once:

  overlapping text on one track  -> clips on a track are sequential, so the later
                                    one silently trims or replaces the earlier one
  text crossing a cut            -> a caption that outlives its clip reads as a
                                    stray line over the next scene
  text outside the timeline      -> renders over black or not at all
  caption too long               -> wraps to three lines and orphans a word
  manual newline plus autowrap   -> the classic three-line orphan

Plan file (JSON). Every section is optional; it checks what you give it.

{
  "fps": 30,
  "canvas": [1080, 1920],
  "clips": [
    {"media": "01192F96", "source": [231.5, 238.5], "note": "cold open"},
    {"media": "01192F96", "source": [165.0, 180.0], "note": "walk into canteen"}
  ],
  "captions": [
    {"start": 7, "end": 59, "text": "you are absolutely right"},
    {"start": 61, "end": 185, "text": "a stubborn long one", "fontSize": 36}
  ],
  "titles": [
    {"start": 20, "end": 170, "text": "back for one night"}
  ],
  "caption_style": {"fontSize": 40, "maxLines": 2},
  "title_style":   {"fontSize": 50, "maxLines": 2}
}

Clips are laid end to end in the order given; startFrame is derived. If you need a
clip at a specific frame, set "start_frame" on it explicitly and the rest follow.

Usage:
    plan_cuts.py PLAN.json                 # validate + human-readable report
    plan_cuts.py PLAN.json --emit clips    # add_clips entries
    plan_cuts.py PLAN.json --emit texts    # add_texts entries (captions + titles)
    plan_cuts.py PLAN.json --emit all      # both, plus the clip boundary table

Exit code is 0 when clean, 1 when any problem is found -- so it works as a gate.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from measure_text import layout as _layout, orphan as _orphan, DEFAULT_SCALE
except Exception:  # pragma: no cover - degrade rather than fail the gate
    _layout, _orphan, DEFAULT_SCALE = None, None, 1.9

# A 1080-wide canvas fits roughly 1200/fontSize characters on a line. Measured by
# rendering real strings at several sizes and reading the box widths back, so it
# already accounts for the font's average advance width -- close enough that a
# 10% safety margin keeps every string inside the frame.
CHAR_WIDTH_FACTOR = 1.111
SAFETY = 0.92


def chars_per_line(font_size, canvas_width):
    return max(1, int(canvas_width * CHAR_WIDTH_FACTOR / font_size * SAFETY))


def predicted_lines(text, font_size, canvas_width, font_name=None, scale=None):
    """Lines after honouring explicit newlines AND the renderer's own wrapping.

    Measures real glyph advances from the font file when it can, because counting
    characters drifts worst exactly at the boundary -- a caption predicted to fit at
    34pt that actually wraps costs a whole re-render to find out. Falls back to the
    character estimate when the font cannot be read.
    """
    cpl = chars_per_line(font_size, canvas_width)
    if _layout and font_name:
        sc = scale or DEFAULT_SCALE
        lines, how = _layout(text, font_name, font_size, canvas_width, sc)
        orph = _orphan(lines)
        # Only report an orphan that is worth acting on. A short trailing word on a
        # two-line caption is ordinary and reads fine; what is worth a human's
        # attention is an orphan a small size change would remove. If nothing in a
        # modest range fixes it, the text is simply that long and saying so is noise.
        fix = None
        if orph:
            for cand in range(int(font_size) - 1, int(font_size * 0.82) - 1, -1):
                cl, _ = _layout(text, font_name, cand, canvas_width, sc)
                if len(cl) < len(lines) or _orphan(cl) is None:
                    fix = cand
                    break
            if fix is None:
                orph = None
        return len(lines), cpl, (how is None), (orph, fix)
    lines = 0
    for authored in text.split("\n"):
        words, cur = authored.split(), ""
        if not words:
            lines += 1
            continue
        n = 0
        for w in words:
            trial = w if not cur else f"{cur} {w}"
            if len(trial) <= cpl:
                cur = trial
            else:
                n += 1
                cur = w
        lines += n + 1
    return lines, cpl, False, (None, None)


def build_clips(plan):
    fps = plan["fps"]
    frame = 0
    out = []
    for i, c in enumerate(plan.get("clips", [])):
        if "start_frame" in c:
            frame = int(c["start_frame"])
        if "source" in c:
            s, e = float(c["source"][0]), float(c["source"][1])
            dur = int(round((e - s) * fps))
        elif "duration_frames" in c:
            s = e = None
            dur = int(c["duration_frames"])
        else:
            raise ValueError(f"clip {i} needs either 'source' or 'duration_frames'")
        out.append({
            "index": i,
            "media": c.get("media"),
            "source": [s, e] if s is not None else None,
            "start_frame": frame,
            "end_frame": frame + dur,
            "duration_frames": dur,
            "note": c.get("note", ""),
        })
        frame += dur
    return out, frame


def check_track(items, label, boundaries, total_frames, style, canvas_width, problems,
                warnings, flag_orphans=False):
    default_size = style.get("fontSize", 40)
    default_lines = style.get("maxLines", 2)
    font_name = style.get("fontName")
    scale = style.get("scale")
    ordered = sorted(items, key=lambda x: x["start"])

    for i, t in enumerate(ordered):
        s, e, text = int(t["start"]), int(t["end"]), t["text"]
        # A single stubborn line can carry its own size rather than shrinking the
        # whole track -- that is what you end up doing in practice.
        font_size = int(t.get("fontSize", default_size))
        max_lines = int(t.get("maxLines", default_lines))
        where = f'{label} "{text[:44]}" [{s},{e})'

        if e <= s:
            problems.append(f"{where}: end is not after start")
        if total_frames and (s < 0 or e > total_frames):
            problems.append(
                f"{where}: outside the timeline (0..{total_frames}) -- it would render over black")
        if i + 1 < len(ordered):
            nxt = ordered[i + 1]
            if e > int(nxt["start"]):
                problems.append(
                    f"{where}: overlaps the next {label} at {nxt['start']} "
                    f'("{nxt["text"][:30]}") -- on one track the later clip wins, '
                    f"so one of these disappears. End this at {nxt['start']} or earlier.")

        if boundaries:
            lo = max((b for b in boundaries if b <= s), default=None)
            hi = min((b for b in boundaries if b > s), default=None)
            if lo is not None and hi is not None and e > hi:
                problems.append(
                    f"{where}: crosses the cut at frame {hi} (its clip is [{lo},{hi})) -- "
                    f"it would hang over the next scene. Trim to {hi} or move it.")

        lines, cpl, measured, orph = predicted_lines(
            text, font_size, canvas_width, t.get("fontName", font_name), scale)
        if lines > max_lines:
            how = "measured from the font" if measured else f"estimated at ~{cpl} chars/line"
            problems.append(
                f"{where}: renders on {lines} lines at size {font_size} (limit {max_lines}; "
                f"{how}). Shorten it, or drop its size -- you can set \"fontSize\" on this "
                f"one item rather than the whole track.")
        elif flag_orphans and orph[0]:
            warnings.append(
                f'{where}: "{orph[0]}" is left alone on the last line. '
                f'Dropping this one item to fontSize {orph[1]} removes it.')
        elif lines == max_lines and len(text.split("\n")) > 1:
            warnings.append(
                f"{where}: exactly at the {max_lines}-line limit with a manual newline. "
                f"One more word and it orphans onto a third line.")
    return ordered


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("--emit", choices=["clips", "texts", "all"])
    ap.add_argument("--caption-track", type=int, default=None,
                    help="trackIndex to stamp on emitted caption entries")
    ap.add_argument("--title-track", type=int, default=None,
                    help="trackIndex to stamp on emitted title entries")
    ap.add_argument("--flag-orphans", action="store_true",
                    help="also warn when a short word is left alone on the last line. "
                         "Off by default: a trailing word on a two-line caption is "
                         "ordinary typography, and flagging every one drowns the real "
                         "problems. Turn it on when you are polishing.")
    args = ap.parse_args()

    with open(args.plan) as fh:
        plan = json.load(fh)
    plan.setdefault("fps", 30)
    canvas_w = plan.get("canvas", [1080, 1920])[0]

    problems, warnings = [], []
    clips, total_frames = build_clips(plan)
    boundaries = sorted({c["start_frame"] for c in clips} | {c["end_frame"] for c in clips})

    for i in range(1, len(clips)):
        if clips[i]["start_frame"] < clips[i - 1]["end_frame"]:
            problems.append(
                f"clip {i} starts at {clips[i]['start_frame']} but clip {i-1} runs to "
                f"{clips[i-1]['end_frame']} -- they overlap on one track")
        elif clips[i]["start_frame"] > clips[i - 1]["end_frame"]:
            warnings.append(
                f"gap of {clips[i]['start_frame'] - clips[i-1]['end_frame']} frames before "
                f"clip {i} -- black frames unless that is deliberate")

    caps = check_track(plan.get("captions", []), "caption", boundaries, total_frames,
                       plan.get("caption_style", {"fontSize": 40, "maxLines": 2}),
                       canvas_w, problems, warnings, args.flag_orphans)
    tits = check_track(plan.get("titles", []), "title", boundaries, total_frames,
                       plan.get("title_style", {"fontSize": 50, "maxLines": 2}),
                       canvas_w, problems, warnings, args.flag_orphans)

    # A title that repeats its caption is the pair the user deletes by hand.
    for t in tits:
        tl = t["text"].lower().replace("\n", " ").strip()
        for c in caps:
            if not (c["start"] < t["end"] and t["start"] < c["end"]):
                continue
            cl = c["text"].lower().strip()
            if tl and (tl in cl or cl in tl):
                warnings.append(
                    f'title "{t["text"]}" restates the caption under it '
                    f'("{c["text"][:44]}"). Label the scene or quote the line, not both.')

    if args.emit:
        emitted = {}
        if args.emit in ("clips", "all"):
            emitted["add_clips"] = [
                {k: v for k, v in (
                    ("mediaRef", c["media"]),
                    ("startFrame", c["start_frame"]),
                    ("source", c["source"]),
                ) if v is not None}
                for c in clips
            ]
        if args.emit in ("texts", "all"):
            def entries(items, track):
                out = []
                for t in items:
                    e = {"startFrame": int(t["start"]), "endFrame": int(t["end"]),
                         "content": t["text"]}
                    if track is not None:
                        e["trackIndex"] = track
                    if "fontSize" in t:
                        e["style"] = {"fontSize": int(t["fontSize"])}
                    out.append(e)
                return out
            emitted["add_texts_captions"] = entries(caps, args.caption_track)
            emitted["add_texts_titles"] = entries(tits, args.title_track)
        if args.emit == "all":
            emitted["clip_boundaries"] = [
                {"index": c["index"], "frames": [c["start_frame"], c["end_frame"]],
                 "note": c["note"]} for c in clips]
        print(json.dumps(emitted, indent=2))

    rep = sys.stderr if args.emit else sys.stdout
    print(f"\nclips      {len(clips)}", file=rep)
    print(f"runtime    {total_frames} frames = {total_frames / plan['fps']:.1f}s "
          f"({total_frames / plan['fps'] / 60:.1f} min)", file=rep)
    print(f"captions   {len(caps)}", file=rep)
    print(f"titles     {len(tits)}", file=rep)
    if caps:
        cs = plan.get("caption_style", {"fontSize": 40})
        fn = cs.get("fontName")
        mode = (f"measured from {fn}" if (_layout and fn)
                else "ESTIMATED by character count -- set caption_style.fontName to measure properly")
        print(f"wrap check      {mode}", file=rep)

    for w in warnings:
        print(f"\nWARN   {w}", file=rep)
    for p in problems:
        print(f"\nFAIL   {p}", file=rep)

    if problems:
        print(f"\n{len(problems)} problem(s). Fix these before sending anything to the editor.",
              file=rep)
        return 1
    print(f"\nPlan is consistent{' (' + str(len(warnings)) + ' warning(s) to eyeball)' if warnings else ''}.",
          file=rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
