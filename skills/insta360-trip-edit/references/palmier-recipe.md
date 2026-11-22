# Building the trip edit in Palmier — the exact sequence

Everything here was learned the hard way on the reference build. Read `edit-large-video`'s
`references/palmier-mcp.md` too (project targeting, time units, preview vs export).

## 0. Project

- `manage_project create` with `fps:30, aspectRatio:"16:9", quality:"1080p"`. Several sessions share
  one Palmier app — `manage_project open` your project again before every batch of mutations.
- Import the **4K originals** (`import_media path:`), one file per call. If the copy is still running,
  import the proxies now and `swap_clip_media` to 4K later — the edit survives the swap.
- **The first `add_clips` snaps the canvas to the media (3840×2160 or 1280×720).** Immediately
  `set_project_settings width:1920 height:1080` after it. Clips refit automatically.

## 1. Place → speed → ripple (the bursts trick)

`plan.py` already spaced every piece at its 1x length + 3 frames, so nothing overlaps yet.

1. `add_clips` with `palmier/add_main.json` (no trackIndex → creates V1 + A1).
2. `add_clips` with each `palmier/add_bursts_N.json` (trackIndex 0, `includeAudio:false` — this is
   what mutes the bursts). **Each file is ≤30 entries because a response lists at most 30 clip ids**
   — collect the ids from every response.
3. `set_clip_properties clipIds:[all burst ids] speed:2` — clips shrink in place.
4. `ripple_delete_ranges trackIndex:<V1> ranges:gaps.json` — closes every gap in one call.
5. Check: `get_timeline` windowed at the end → `totalFrames` must equal `pieces.json.total_frames`.
   If it does, every overlay placement is valid as computed.

## 2. Music

`import_media` the tracks, `add_clips palmier/music.json` (no trackIndex → new audio track), then
`set_clip_properties volumeDb:-15 fadeInFrames:45 fadeOutFrames:45`, longer fade-out on the last.
Name tracks (`Main`, `Ambience`, `Music`, `Titles`, `Speed`).

## 3. Overlays

- `import_media path:<render dir>/out` (directory import). ProRes 4444 alpha composites correctly.
- Metadata loads lazily: if `add_clips` says *"endFrame is required — source length is unknown"*,
  call `get_media ids:[…]` once and retry.
- Titles (cards + labels) in ONE `add_clips` call → its own new track; burst tags in another call →
  another new track (always `includeAudio:false`; HyperFrames MOVs carry a silent audio track).
- Replacing an overlay later: re-render, import under a **new filename** (avoids stale caches),
  `swap_clip_media`, then `set_clip_properties durationFrames` if the length changed.

## 4. Zoom on a far subject

`set_clip_properties transform:{width:s, height:s, centerX, centerY}` with
`centerX = ax + (0.5 − px)·s`, `centerY = ay + (0.5 − py)·s` — (px,py) the subject in the source
(0–1), (ax,ay) where it should land on screen (use ay≈0.55 to push crowd heads down). Check
coverage: `centerX ± s/2` must contain [0,1]. 1.6–2x on 4K stays full 1080p sharpness.
Check 4–6 frames across the clip: performers wander.

## 5. Photos

`photo.py IMG out.mp4` → `insert_clips trackIndex:<V1> atFrame:<end of the day's last piece>`.
Unlock the music track first (`manage_tracks set syncLocked:false`) so the bed doesn't open a
silent gap, extend the last music clip by the inserted length, re-lock. Add its label with
`add_clips` on the titles track (end it before the next card starts).

## 6. Fixing a piece after the build

Order matters: **remove the orphaned burst tag first**, then the piece, then
`ripple_delete_ranges` on V1 with `ignoreSyncLockedTracks:[<music index>]`, then trim the music tail
to the new end. Moving a burst off a bad moment without changing timing: set `trimStartFrame`
(project frames = source seconds × 30) **and** `durationFrames` in the same call.

## 7. Inspect, export, wait

- **One `inspect_timeline` at a time.** Four in parallel on 4K + ProRes dropped the MCP connection.
- Export once per feedback round: `export_project outputPath:<existing dir>/x.mp4 resolution:"1080p"`
  (the directory must exist). A 40-min cut renders in ~30–45 min.
- Wait with a background shell, not polling: loop until `ffprobe` duration ≥ expected and the
  file size is stable for 20 s, then `verify.py`.
