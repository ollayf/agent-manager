# Palmier Pro MCP: the operational traps

Mechanics that cost real time to discover. Read this before a long build; most of
these fail in ways that look like something else.

## Targeting: confirm the project before every mutation

Palmier is one desktop app with one active project, and **several Claude sessions can
share the same MCP server**. Another session opening its own project silently takes
the target away from yours, mid-job.

Reads keep working. Mutations fail with a message naming the other project. That
asymmetry is actually helpful — it means you get an error rather than writing into
someone else's timeline — but it means a long build can stall at an arbitrary point.

- `manage_project action:"list"` shows `active` and `visible`.
- `manage_project action:"open"` with the **project id** re-targets this session.
- After re-opening, `get_timeline` and confirm the `id` and `totalFrames` are yours
  before you resume. A returned clip or track name you do not recognise means you are
  in the wrong project — stop.
- If you are editing one of several timelines in a project, `set_active_timeline`
  as well; opening a project does not restore which timeline was active.

## Tracks

- **Track indices shift whenever a track is created.** `add_texts` with no
  `trackIndex` creates a new track at index 0 and pushes everything down. Re-read
  `get_timeline` before any index-based call that follows.
- **Prefer `trackId` over index** for anything destructive. `manage_tracks remove`
  by index is the worst case, because index 0 always exists somewhere — aimed at a
  scratch track it will always find *a* track to destroy.
- `add_clips` rejects a batch that mixes explicit and omitted `trackIndex`. Set it on
  every entry or none.
- **Clips on one track are sequential.** Overlap is not layering — the later clip
  trims, splits, or replaces the earlier one. To have two things on screen at once,
  they must be on different tracks. Titles and captions therefore need their own
  tracks, which also lets a scene title sit above a caption in the same frame.

## Time units

Two different units, and mixing them produces plausible-looking nonsense:

- **Timeline** positions (`startFrame`, `endFrame`, `frames`, gaps) are **project
  frames** at the timeline's fps.
- **Source** positions (`source: [start, end]`, `inspect_media` windows, transcript
  seconds from `inspect_media`) are **seconds** in the source media.
- `get_transcript` is the exception that makes this workable: it returns word and
  segment positions in **project frames**, already mapped through each clip's trim
  and position. That is why you caption *after* assembling, not before.
- `trimStartFrame` / `trimEndFrame` are offsets into the source expressed in
  **project** frames, not the source's own fps.

Source fps rarely matches timeline fps (29.769 and 29.698 against a 30fps timeline in
one real job). Let the tools convert; do not multiply by fps yourself.

## Transcription

`inspect_media` with `startSeconds`/`endSeconds` transcribes **only that window**, so
it is fast — a ten-minute window returns in seconds. Page through a long source in
windows of 450-600s. It returns sentence-level segments, which read better as
captions than word chunks do.

Re-transcribing a narrow window around an uncertain phrase often returns a cleaner
result than the same span inside a long window, because the model has less to align.
Use this as a cheap second opinion before writing a doubtful caption — but know its
limit: two passes agreeing is not proof. Local proper nouns come back confidently
wrong on every pass.

## Export

- **One export at a time, globally.** A second `export_project` while one is running
  is refused. Poll `manage_exports action:"list"` for `progress`/`status`.
- Roughly 40s of render per minute of finished video on a laptop, so a ten-minute cut
  is a seven-minute wait. This is the whole reason to batch edits.
- Exporting to the same path replaces the file. The size on disk changes slightly
  even when content is nearly identical, so "size stopped growing" is a weak
  completion signal — check `manage_exports` for `status: completed`.
- `resolution: "Match Timeline"` keeps the canvas you set. Export the final at
  `1080p` only if you need a platform-standard deliverable at a different size.

## Fades do not cross a link

A video clip and its linked audio are one thing in the UI and two things to
`set_clip_properties`. A fade applied to the video clip alone leaves the sound cutting
dead at full level — audible, but easy to miss when you are checking frames. Pass both
the visual clip id and its nested `audio.id` from `get_timeline`.

Same shape of trap as the orphaned-text one: the fade lives on a clip, so deleting
that clip silently takes the fade with it.

## Closing a gap: ripple, and the ordering trap

`ripple_delete_ranges` is less arithmetic than moving clips by an explicit delta, and
both work. Either way the ordering is the same and it is not obvious:

**Remove orphaned overlay text before you close the gap.** Sync-locked overlay tracks
*shift* under a ripple rather than being cut by it, so rippling first slides the
orphaned titles and captions backwards into a collision with the previous scene's
text — and on a single track the arriving clip trims or replaces what it lands on.
Delete the orphans, then close the gap.

## fontSize is not canvas pixels

Roughly 1.9 rendered pixels per unit of `fontSize` on a 1080-wide canvas. This is why
text sizing calibrated on one canvas size renders wrong on another, and why a
character-count wrap estimate drifts. See `references/text-style.md`.

## The preview pane is not the export

`inspect_timeline` composites quickly and is right about **position, layering, and
wrapping**. It is not right about everything: text background chips do not draw in
the preview but do render in the export. Treat the preview as a layout check and the
exported frames as the truth. `scripts/verify_export.py` exists for exactly this.

## Rebuilding beats patching

Once a text track has more than ~30 clips, threading new entries into the gaps
between existing ones is slow and error-prone. Removing the track by `trackId` and
re-adding the complete set from a plan file is faster, and it is the only way to be
sure the result matches your plan rather than matching your plan plus whatever was
already there.

Corollary: keep the plan file as the source of truth and regenerate from it, rather
than treating the timeline as the record of what you meant.

## Undo

`undo` exists and works — it restored a track plus 25 clips after a wrong-project
`manage_tracks remove`. It is a real safety net, but it is one level of protection
against a mistake that is easy to avoid by confirming the target first.
