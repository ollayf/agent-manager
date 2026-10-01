# The text layer: style, sizing, and the wrap arithmetic

A settled house look for titles and captions on a 1080x1920 vertical cut, plus the
arithmetic that stops text from wrapping badly. Start from these values rather than
re-deriving them; change them when the footage or the user asks for something else.

## The two roles must not look alike

Titles and captions do different jobs, and a viewer should be able to tell which is
which without reading. Distinguish them on **four axes at once** — typeface, colour,
position, and weight of treatment. Distinguishing on size alone is not enough; it
reads as one system with an inconsistency rather than two systems.

| | Title (labels the scene) | Caption (transcribes speech) |
|---|---|---|
| font | `TikTokSans-Bold` | `Inter` + `bold: true` |
| colour | amber `#FFC94A` | white `#FFFFFF` |
| outline | 1px black | none |
| shadow | black, opacity 0.95, blur 20, offset y 3 | black, opacity 0.85, blur 16, offset y 3 |
| background | none | none |
| position | top-left, `x 0.06 / y 0.135`, left-aligned | lower third, `x 0.5 / y 0.76`, centred |
| size | 50 (44 when it runs to two lines) | 40 |
| case | lowercase | lowercase |

The opening title card is the one exception: same font and colour, centred at
`x 0.5 / y 0.44`, size 60.

Two settled preferences behind these values: **no ALL-CAPS** (reads shouty) and **no
coloured keyword highlight** (reads gimmicky). A translucent dark chip behind titles
was tried and dropped — the 1px outline plus shadow carries legibility without the
box, which was heavy over busy footage.

## Predicting wrapping

Nearly every text defect is a wrap defect, so it pays to know the width of a line
before you render it.

**Measure, do not count characters.** `wwwwwwwwww` and `iiiiiiiiii` are the same
length and nowhere near the same width, so a character-count rule drifts worst
exactly at the boundary where you need it. `scripts/measure_text.py` sums the real
glyph advances out of the font file:

```
width_px = (sum of glyph advances / unitsPerEm) * fontSize * SCALE
```

```bash
python3 scripts/measure_text.py --font Inter-Bold --size 40 "your caption here"
```

`plan_cuts.py` uses this automatically when the plan's `caption_style` /
`title_style` carries a `fontName`; without one it falls back to counting characters
and says so.

### SCALE, and why it exists

An editor's `fontSize` is not necessarily canvas pixels. For Palmier on a 1080-wide
canvas the factor is **about 1.9**, derived from three observed wrap boundaries and
checked against a fourth:

| string | em | size | predicted px | observed |
|---|---|---|---|---|
| "i always sneak my homework down" | 17.26 | 34 | 1115 | wrapped |
| same | 17.26 | 32 | 1050 | fit on one line |
| "that's where we used to stand" | 14.68 | 40 | 1116 | wrapped |
| same | 14.68 | 36 | 1004 | fit |

Recalibrate rather than trusting the default when the editor, canvas or font changes:
`measure_text.py --calibrate` prints the procedure (render a known string, read the
fraction of frame it spans, divide).

**Near the boundary, confirm with the renderer.** A prediction is a prediction. When a
line lands within a few percent of the edge, put it on the timeline and look at the
composited frame — that check is free and it is ground truth.

### Orphans are a taste call, not a defect

A short word alone on the last line — "...my homework" / "down" — fits any budget and
still looks slightly wrong to some eyes. `plan_cuts.py --flag-orphans` reports them
with a size that would remove each one. It is **off by default on purpose**: on a real
87-caption cut it fires on sixteen of them, almost all of which read perfectly well,
and a warning that cries wolf sixteen times hides the three that matter. Turn it on
when you are polishing a short piece, not when you are gating a long one.

Note the trap it reveals, though: shrinking 40 -> 36 -> 34 did not clear one real
orphan, because each smaller size simply rewrapped to the same shape. Only 32, where
the whole line collapsed to one, fixed it. If you are chasing an orphan by resizing,
check whether you are moving it rather than removing it.

## Resolving font names

Pass the **PostScript name**, and get it from the font file rather than guessing:

```python
from fontTools.ttLib import TTFont
f = TTFont(path, fontNumber=0)
{r.nameID: r.toUnicode() for r in f["name"].names if r.nameID in (1, 4, 6)}
# nameID 1 = family, 4 = full name, 6 = PostScript name  <- pass this one
```

Guessing is unreliable in a way that fails silently — the editor falls back to a
default face rather than erroring, so the first sign of trouble is the export looking
wrong. `Inter` with `bold: true` resolves to `Inter-Bold`, but `Inter Black` is a
*separate family* and asking for a bolder `Inter` will not reach it. For `.ttc`
collections (most macOS system fonts) iterate the collection — `Avenir Next.ttc`
holds twelve faces, only one of which is `AvenirNext-Heavy`.

## Naming scenes

Titles get rewritten by the owner when they **describe** rather than **name**. From a
real pass: `the view` became `morning assembly view`, `the rock wall` became
`level 7`, `the flex` became `phd flexing`, `campfire` became `campfire spot`. The
pattern is that the editor labelled what it could see, and the person who was there
labelled what the place is *called*.

**In a conversational piece, title the topic, not the picture.** The camera is rarely
pointed at the subject of the sentence — a shot of an empty corridor during a story
about campfires is the campfire section, and labelling it "corridor" would be both
accurate and useless. An evaluation run flagged a "campfire" title as wrong because no
fire was visible; that was the guidance misfiring, not the title. Name the beat.

You cannot infer these from the footage, and that is the point — don't try. Write the
best descriptive title you can, then put it on the review sheet so the one person who
knows the real name can supply it in five seconds.

Also: **a title that restates the caption under it gets deleted.** `every batch had
one` over a caption reading "every batch had one fellow with the mushroom haircut" is
one idea taking up two thirds of the screen. Label the scene *or* quote the line.
`plan_cuts.py` warns on this overlap.
