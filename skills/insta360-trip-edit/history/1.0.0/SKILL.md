---
name: insta360-trip-edit
description: >-
  Turn an Insta360 card (or any pile of long POV walking / travel clips) into one long, labelled,
  music-backed trip video in Palmier Pro — read-only ingest, cheap survey, a plan file that does
  all frame maths, short 2x bursts instead of fast-forward, muted bursts with tags, day cards with
  intros, place lower thirds, photos as push-ins, and a per-clip map that proves the footage was
  understood. Use whenever someone plugs in an Insta360 / action cam / phone footage of a trip or
  walk and wants it edited: "go through my insta360", "edit my trip footage", "make a video of my
  walk through X", "label each day", "speed up the walking parts", "copy the files off the camera
  and edit them". Builds on edit-large-video; not for talking-head or short social cuts.
---

# Insta360 trip edit

> **Before you ask the user anything, read [`decided.md`](decided.md).** It lists the questions
> already put to them and answered. Asking one of them again costs a round trip and their patience.

The finished thing: **one long video that keeps everything that matters** — every conversation,
show, purchase and landmark at normal speed with sound; walking kept as short 2x bursts between
normal-speed beats; junk (drops, fingers on the lens, walls) gone; each day opened by a title
card with an intro line; each place named by a lower third; a music bed under all of it.

The reference build is [`examples/tokyo-2026.trip.json`](examples/tokyo-2026.trip.json): 83 min
of footage → 40:28. `plan.py` reproduces that edit frame-for-frame — read it before writing a plan.

## The workflow

Each step has a script; each script prints `--help`. `S=<this skill's directory>`, `P=<project dir>`.

**1. Ingest — the card is read-only.** `ingest.py --src /Volumes/<CARD>/DCIM/Camera01 --project P --copy`
in the background (35 GB ≈ 30 min), then `--verify`. Never delete, move or write anything on the
card. Proxies (`.lrv`, 720p) are hard-linked as `proxies/*_proxy.mp4`; everything below reads
those, and Palmier gets the 4K originals. Tell the user when it is safe to eject (the script
names apps still holding card files open). Filename times can overlap (two clips "starting" 35 s
apart, one 30 min long) — order clips by `mtime_end` in `inventory.json`, not by name; short
clips (<30 s) are usually camera tests.

**2. Survey — never frame by frame.** `survey.py sheets` (one frame / 20 s, 36 tiles per image —
83 min fits in ~16 images), `survey.py scan` (motion/darkness flags), `survey.py zoom` on flags.
Speech: Palmier `inspect_media` per clip with `language:"en"` (and the local language for
performers/vendors), `maxFrames:1` — it is fast and returns only the talking. Expect little
speech; find moments visually. Photos on the card: look at them — a photo can show a place no
clip does (the Yūrakuchō Godzilla); include those only, as a push-in (`photo.py`).

**3. Plan — one JSON, no arithmetic by hand.** Write `trip.json` ([format](references/plan-format.md)):
segments in story order with a `kind` (`H` moment / `nice` / `boring` / `walk` / `photo` / `cut`)
and a one-line `what`, day cards, place labels. Rules for choosing kinds are in
[`decided.md`](decided.md). Then `plan.py trip.json --out P/plan` → pieces, Palmier batches,
overlay list, placements, and `clipmap.md`.

**4. Review the cut BEFORE building.** `survey.py review --pieces P/plan/pieces.json` thumbnails
every piece. Hunt hands/fingers over the lens, phone held in front of it, sky, walls, black.
Fix in `trip.json` (`cut` segment, shorter `e`, or `burst_shift`) and re-plan. In the reference
build this step was skipped first time and cost three fix-up rounds after export.

**5. Overlays.** `overlays/gen.py P/plan/overlays.json --dir P/overlays` (+ `fetch_fonts.sh`),
then `render.sh P/overlays` in the background — transparent ProRes MOVs. Style and what may
change: [`references/style.md`](references/style.md).

**6. Build in Palmier** exactly as [`references/palmier-recipe.md`](references/palmier-recipe.md):
place → speed bursts → ripple gaps → music → overlays → zooms → one export. The recipe carries the
traps (ids capped at 30 per response, resolution snapping to 4K, one inspect at a time, ...).

**7. Verify the exported file**, then hand over. `verify.py EXPORT --plan P/plan` — duration,
a sheet of every card/label/tag in the *render*, burst-vs-normal audio levels. Look at the sheet.
Hand over with the path, the length, `clipmap.md` (the per-clip table), and **one batched list**
of every place name you guessed.

## After handover

Expect place-name corrections, "zoom in on X", "add that photo", "special day" text. Change
`trip.json`, re-run `plan.py` + `gen.py` for the touched overlays, and patch the timeline
(`swap_clip_media` for re-rendered overlays, imported under a NEW filename). Re-export once per
round of feedback, not per change. Real-world context (holidays, events) gets looked up before it
is written into a card — then confirmed with the user.

## What's here

| | |
|---|---|
| `scripts/ingest.py` | read-only copy, verify, proxies, inventory, eject advice |
| `scripts/survey.py` | sheets / scan / zoom / review — the token-cheap way to see footage |
| `scripts/plan.py` | trip.json → pieces, Palmier batches, gaps, music, overlays, placements, clip map |
| `scripts/overlays/` | `gen.py` + `theme.json` (swappable look), `fetch_fonts.sh`, `render.sh` |
| `scripts/photo.py` | still → 16:9 push-in clip with blurred fill |
| `scripts/verify.py` | checks the exported file |
| `references/` | `palmier-recipe.md`, `style.md`, `plan-format.md` |
| `examples/tokyo-2026.trip.json` | the reference build |
| `decided.md` | the user's settled answers — read first |

Artifacts are stamped with `VERSION` (`skill_version`, `format`). Released versions are frozen in
`history/<version>/` with `SHA256SUMS`; never edit a released folder — bump the version.
