#!/usr/bin/env python3
"""Measure how wide a string will actually render, using the font's own metrics.

Counting characters is not good enough. "wwwwwwwwww" and "iiiiiiiiii" are the same
length and nowhere near the same width, and a character-count estimate drifts worst
exactly at the boundary where you need it — a caption predicted to fit at 34pt that
wraps at 34pt costs a whole re-render to discover.

So: sum the real glyph advances out of the font file.

    width_px = (sum of advances / unitsPerEm) * fontSize * SCALE

SCALE exists because an editor's "fontSize" is not necessarily canvas pixels. For
Palmier on a 1080-wide canvas it is about 1.9. Calibrate it for your own setup with
--calibrate (see below) rather than trusting the default.

Usage:
    measure_text.py --font Inter-Bold --size 40 "your caption here"
    measure_text.py --font Inter-Bold --size 40 --canvas 1080 --max-lines 2 "..."
    measure_text.py --calibrate

Exits 1 if the string will not fit in the given number of lines.
"""
import argparse
import glob
import os
import sys

# Editor fontSize -> rendered pixels, for Palmier on a 1080-wide canvas.
# Derived from three observed wrap boundaries; see references/text-style.md.
DEFAULT_SCALE = 1.9

FONT_DIRS = [
    os.path.expanduser("~/Library/Fonts"),
    "/Library/Fonts",
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
]

CALIBRATION_HELP = """
To calibrate SCALE for your editor:

  1. Put a known string on the timeline at a known fontSize, e.g.
     "abcdefghijklmnopqrstuvwxyz" at size 40.
  2. Render it and measure the fraction of the canvas width it spans
     (inspect_timeline draws a 0-1 grid over the frame).
  3. Run:  measure_text.py --font <PS name> --size 40 --em-only "abc...xyz"
     to get its width in em.
  4. SCALE = (observed_fraction * canvas_width) / (em_width * fontSize)

Re-run this whenever the editor, the canvas size, or the font changes.
"""


def find_font(ps_name):
    """Locate a font file by PostScript name. Returns (path, fontNumber) or None."""
    try:
        from fontTools.ttLib import TTFont, TTCollection
    except ImportError:
        return None
    candidates = []
    for d in FONT_DIRS:
        candidates += glob.glob(os.path.join(d, "*.ttf"))
        candidates += glob.glob(os.path.join(d, "*.otf"))
        candidates += glob.glob(os.path.join(d, "*.ttc"))
    # cheap pass first: filename usually contains the PostScript name
    stem = ps_name.lower().replace("-", "").replace(" ", "")
    candidates.sort(key=lambda p: stem not in os.path.basename(p).lower().replace("-", "").replace(" ", ""))
    for path in candidates:
        try:
            if path.lower().endswith(".ttc"):
                coll = TTCollection(path, lazy=True)
                for i, f in enumerate(coll.fonts):
                    if _ps_name(f) == ps_name:
                        return path, i
            else:
                f = TTFont(path, fontNumber=0, lazy=True)
                if _ps_name(f) == ps_name:
                    return path, 0
        except Exception:
            continue
    return None


def _ps_name(font):
    for rec in font["name"].names:
        if rec.nameID == 6:
            try:
                return rec.toUnicode()
            except Exception:
                continue
    return None


def em_width(text, ps_name):
    """Width of `text` in em units, or None if the font cannot be measured."""
    found = find_font(ps_name)
    if not found:
        return None
    from fontTools.ttLib import TTFont
    path, num = found
    font = TTFont(path, fontNumber=num, lazy=True)
    upem = font["head"].unitsPerEm
    hmtx = font["hmtx"]
    cmap = font.getBestCmap()
    fallback = cmap.get(ord("n"))
    total = 0
    for ch in text:
        g = cmap.get(ord(ch), fallback)
        if g is None:
            continue
        total += hmtx[g][0]
    return total / upem


def wrap_lines(text, ps_name, font_size, canvas_width, scale=DEFAULT_SCALE):
    """Predicted line count. Thin wrapper over layout() for callers that only count."""
    lines, how = layout(text, ps_name, font_size, canvas_width, scale)
    return len(lines), how


def orphan(lines):
    """The last line holding a single short word -- the defect that reads as a mistake.

    A caption that fits its line budget can still look broken: "...my homework" then
    "down" alone underneath. Two lines, within budget, and obviously wrong. Worth
    flagging separately from the budget because the fix is different -- reword or
    rebalance rather than resize.
    """
    if len(lines) < 2:
        return None
    last = lines[-1].split()
    if len(last) == 1 and len(last[0]) <= 12:
        return last[0]
    return None


def layout(text, ps_name, font_size, canvas_width, scale=DEFAULT_SCALE):
    """The actual wrapped lines, honouring explicit newlines AND the renderer's wrapping.

    Returns (lines, None) when measured, or (lines, 'estimate') when it had to fall
    back to counting characters.
    """
    ew = em_width("n" * 20, ps_name)
    estimating = ew is None
    if estimating:
        cpl = max(1, int(canvas_width * 1.111 / font_size * 0.92))
        fits = lambda s: len(s) <= cpl  # noqa: E731
    else:
        font_em = {}

        def fits(s):
            if s not in font_em:
                font_em[s] = em_width(s, ps_name)
            return font_em[s] * font_size * scale <= canvas_width

    lines = []
    for authored in text.split("\n"):
        words = authored.split()
        if not words:
            lines.append("")
            continue
        cur = ""
        for w in words:
            trial = w if not cur else f"{cur} {w}"
            if fits(trial):
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines, ("estimate" if estimating else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", nargs="*")
    ap.add_argument("--font", default="Inter-Bold", help="PostScript name")
    ap.add_argument("--size", type=float, default=40)
    ap.add_argument("--canvas", type=int, default=1080)
    ap.add_argument("--scale", type=float, default=DEFAULT_SCALE)
    ap.add_argument("--max-lines", type=int, default=2)
    ap.add_argument("--em-only", action="store_true", help="just print the em width")
    ap.add_argument("--calibrate", action="store_true")
    args = ap.parse_args()

    if args.calibrate:
        print(CALIBRATION_HELP)
        return 0
    if not args.text:
        ap.print_help()
        return 2

    text = " ".join(args.text)
    ew = em_width(text, args.font)
    if ew is None:
        print(f"could not measure {args.font} (fontTools missing, or font not installed) "
              f"-- falling back to a character-count estimate", file=sys.stderr)
    elif args.em_only:
        print(f"{ew:.4f}")
        return 0
    else:
        print(f"em width   {ew:.3f}")
        print(f"rendered   {ew * args.size * args.scale:.0f}px at size {args.size} "
              f"(scale {args.scale}) on a {args.canvas}px canvas")

    lines, how = layout(text, args.font, args.size, args.canvas, args.scale)
    print(f"lines      {len(lines)}{' (estimated)' if how else ''}  limit {args.max_lines}")
    for i, l in enumerate(lines, 1):
        print(f"  {i}. {l}")
    bad = False
    if len(lines) > args.max_lines:
        print("DOES NOT FIT -- shorten it or drop the size")
        bad = True
    o = orphan(lines)
    if o:
        print(f"ORPHAN -- \"{o}\" sits alone on the last line. Reword or rebalance; "
              f"resizing usually just moves the problem.")
        bad = True
    if not bad:
        print("fits")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
