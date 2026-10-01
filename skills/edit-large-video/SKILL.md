---
name: edit-large-video
description: >
  Turn a large pile of raw footage — an hour of phone video, several long unwatched clips —
  into a finished, captioned, titled, exported cut. Use it whenever someone hands over long
  source video and wants something watchable out of it: "edit this footage", "make something
  out of these videos", "cut this down", "I filmed my trip, can you edit it", "make a
  highlights reel", "add captions and titles to my video", "put a title on each scene". Reach
  for it as soon as the source is longer than anyone wants to watch end to end, even if the
  request sounds casual — finding what is worth keeping without watching it all, text that
  does not wrap wrong, and not burning an hour on repeat exports are what it carries. Also
  covers mid-edit asks: "the captions are wrong", "why did the text wrap onto three lines",
  "the export looks different from the preview", "I deleted some clips, tidy it up". Assumes
  Palmier Pro. Not for sequencing pieces already cut to length.
---

# Edit a large video

Someone has more footage than they want to watch. The job is to find what is worth
keeping, cut it together, put readable text on it, and hand back a finished file.

Most of the work is judgment, and most of the *failure* is mechanical — text that
wraps onto three lines, a caption hanging over the next scene, an hour lost to
re-exporting. The scripts here take the mechanical half off your hands so your
attention goes where it counts.

## The one idea worth internalising

**You will get local knowledge wrong, and no amount of care will fix that. Surface it
cheaply instead.**

On the job this skill came from, every single correction the owner made was a word no
model could have recovered from the audio: "stack of **paper**", not people. "We
**cheer**", not chill. **PhD**, not "PG". The rock wall scene was called **level 7**.
Each was a confident, plausible, wrong guess.

The failure was not the guessing — it was guessing *silently*, and only finding out
after five exports. So: do the whole edit, then **show the text layer as a list and
ask once, before the first render.** Thirty seconds of the owner's attention buys
what an hour of yours cannot.

Before a long build, read
**[`references/palmier-mcp.md`](references/palmier-mcp.md)** — project targeting,
track indices, the two time units, and why the preview and the export disagree. Those
traps fail in ways that look like something else, so recognising them afterwards is
much more expensive than reading about them first.

## Workflow

### 1. Survey before you cut

Never watch it all, and never transcribe it the slow way.

```bash
python3 scripts/probe_sources.py <files...>
```

Reports duration, fps, audio, and — importantly — the **display** geometry after
rotation. Phone video is routinely stored landscape with a rotation flag, so raw
ffprobe says `1920x1080` for a portrait clip. Set the canvas from the DISPLAY figure
*before* placing any clip; adding the first clip can otherwise pull the project to
the media's geometry and every text size you pick afterwards will be calibrated to
the wrong canvas.

```bash
python3 scripts/contact_sheet.py VIDEO --out survey/ --every 30 --prefix "A "
```

Then *look* at the sheets. Thirty-second sampling over an hour is ~120 tiles and
shows you in one pass where the pockets, ceilings and walls are, where people are on
camera, and where the light changes.

For the audio, use the editor's own windowed transcription (`inspect_media` with
`startSeconds`/`endSeconds`, 450-600s at a time). It returns sentence segments in
seconds and is fast.

> **Do not reach for local Whisper on long footage.** `small.en` on CPU quoted
> **4 hours 57 minutes** for 67 minutes of audio and had to be killed. The editor's
> built-in transcription did the same work in under a minute per window. This one
> fact is worth the price of the skill.

### 2. Build the cut list as data

Write the selects as a table — source, start, end, and *why it earns its place* —
before touching the timeline. Aim at what the footage is actually about. In a
conversational source that means following the talk: the stories, the jokes, the
moments someone reacts. Silent walking is connective tissue, not content.

Put it in a plan file and gate it:

```bash
python3 scripts/plan_cuts.py plan.json --emit all
```

It derives every `startFrame`, proves the plan is internally consistent, and prints
`add_clips` / `add_texts` arguments ready to send. Frame arithmetic done by hand is
how captions end up overlapping; let the script do it.

Then place the clips in **one** `add_clips` call.

### 3. Get the transcript of the *cut*, then write the text

`get_transcript` on the assembled timeline returns positions in project frames,
already mapped through every trim — which is why captioning happens after assembly,
not before. Write captions from those segments.

Two things that decide whether captions land:

- **Cover whole talking sections**, not just the best lines. A caption here and there
  reads as a highlight reel of itself. When someone is talking, caption them.
- **Skip what you genuinely cannot make out.** Crosstalk and mumbles transcribe as
  confident nonsense. A gap is honest; garbage is not. Say which parts you skipped
  and why when you hand over.

Titles label each new scene — a location, a topic, a turn in the conversation. Keep
them short. They go on their **own track** so a title and a caption can share a frame.

Give `plan_cuts.py` a `fontName` in the style block so it measures wrapping from the
font's real glyph advances instead of counting characters — counting drifts worst
right at the boundary, which is where it costs a re-render to find out. Near the edge,
put the line on the timeline and look at the composited frame; that is free and it is
ground truth.

Style values, the measurement model, and how to resolve font names:
**[`references/text-style.md`](references/text-style.md)**.

### 4. The review sheet — do not skip this

Before the first export, print the text layer as a numbered list and **flag what you
are unsure about**. Flag:

- proper nouns, place names, institution-specific words, anything a local would know
- anything where two transcription passes disagreed
- every title that *describes* rather than *names* — `the view`, `the flex`,
  `the rock wall`. These are the ones that get rewritten.
- any title that restates the caption beneath it (`plan_cuts.py` warns on these)

Ask in **one batch**. Not a question per item, and not a question after each stage —
one list, one round. Then apply and move on.

This step is the difference between one export and five.

### 5. Export once, then verify the pixels

```bash
python3 scripts/verify_export.py EXPORT.mp4 --plan plan.json --out verify/
```

It samples the middle of every title and the longest captions — where defects live —
tiles them, and checks the export's duration against the plan. Then **look at the
sheets**. Reading the JSON is not verification.

On the originating job this caught two real defects the timeline preview did not: a
caption orphaning a word onto a third line, and a title and caption saying the same
thing with a mid-word break underneath.

### 6. When the owner edits it themselves

Expect it, and expect it to be the most useful feedback you get. After they have been
in the app:

- Re-read the timeline and **diff it against your plan** — deleted clips, retimed
  text, rewritten titles, corrected words.
- **Delete orphaned text.** Captions and titles belonging to a removed clip do not go
  with it automatically.
- **Re-apply the tail fade**, to the picture *and* the linked audio. The fade-out
  lives on the last clip; delete that clip and the cut ends on a hard stop, with the
  sound cutting dead. Easy to miss because nothing errors.
- **Read their corrections as data.** A rewritten title tells you what that place is
  called. A corrected word tells you what the audio actually said. Fold both into
  anything you write next — and leave their edits alone otherwise.

## The laws, and the afternoon each one cost

**Confirm the active project before every mutation.** Several sessions share one
Palmier app; another session opening its own project takes the target from yours
mid-job. Reads keep working, mutations fail. A `manage_project list` costs nothing.

**Batch every change, then export.** One ten-minute cut went through five exports at
~7 minutes each because the text layer was revised in three rounds. Work through the
whole plan, review it on paper, then render.

**Name the place; don't describe it.** Generic titles get rewritten by the person who
was there. Write your best guess, then ask.

**A title must not restate its caption.** One idea, two thirds of the screen. Label
the scene or quote the line.

**Verify rendered frames, never the manifest or the preview.** Chips render in the
export and not in the preview; wrapping resolves at render time. Gates passing is not
evidence the picture is right.

**Deleting a clip orphans its text and its fade.** Nothing warns you. When you restore
a fade, apply it to the video clip *and* its linked audio — fades do not cross the
link, and a video-only fade leaves the sound cutting dead at full level.

## What's here

| Path | What it is |
|---|---|
| `scripts/probe_sources.py` | Display geometry after rotation, duration, fps, audio; tells you the canvas |
| `scripts/contact_sheet.py` | Timestamped sampled frames tiled into sheets — how you survey without watching |
| `scripts/plan_cuts.py` | Validates the plan (overlaps, cut-crossing, wrap budget) and emits tool arguments |
| `scripts/measure_text.py` | Predicts wrapping from real glyph advances; `--flag-orphans`, `--calibrate` |
| `scripts/verify_export.py` | Samples the finished file where defects live; checks duration against the plan |
| `references/text-style.md` | Title/caption spec, the chars-per-line arithmetic, font-name resolution |
| `references/palmier-mcp.md` | Targeting, tracks, time units, transcription, export, preview-vs-export |

Every script prints its own usage with `--help` and exits non-zero on a real problem,
so they work as gates in a loop.

## Scope

This owns **raw footage to finished file**: survey, selection, assembly, text layer,
verification, export.

It does **not** own assembling pieces that are already cut to length and only need
sequencing — a talking-head post with its clips and voiceover already made is a
different job with a different skill. If the footage is already the video and only
needs putting in order, you are in the wrong place.
