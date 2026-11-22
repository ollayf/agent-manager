# The look — direction, not a template

The user liked this look and said: *"no need to use the same fonts and animations but the
direction is there."* So the **roles, hierarchy and behaviour** below are fixed; typefaces,
accent colour and motion curves are free to change per trip (`scripts/overlays/theme.json`).
The source of the direction is the HyperFrames catalog (hyperframes.heygen.com/catalog) —
`titlecard-lockup`, `lt-kicker-name`, and the pill/chip family. Browse it for a fresh variant.

## Three text roles, never confused

| Role | Where | Anatomy | Motion | Length |
|---|---|---|---|---|
| **Day card** — opens a day | centre, soft radial scrim behind | small accent **kicker tag** (`DAY 03 · 文化の日 CULTURE DAY`) · huge heavy **area word** (ASAKUSA) · **local-script** line (浅草) · hairline **accent rule** · tracked mono **date label** · one-line **intro sentence** in sentence case | staggered rise/settle in ~1 s, still hold, lift-and-fade out | 5 s |
| **Place label** — names a scene | lower third, bottom-left | accent **kicker** (`Day 3 · 3 Nov`) · heavy uppercase **name** · local-script line · accent **baseline** that draws on | kicker drops, name pops up, baseline draws; reverse out | 4.8 s |
| **Burst tag** — during every 2x | top-right | accent **pill** with ▶▶ + speed · white **chip** with lowercase "what's happening" (*through the shophouses*) | slides in, chip wipes open, chevrons nudge; wipes out | = burst (6 s) |

## Rules that make it read well

- **One accent colour** (vermilion for Japan; pick from the place next time — e.g. a temple, a flag,
  a sign). Everything else white with a soft dark shadow; no boxes behind names.
- **Heavy display face for names, mono for meta (dates, kickers, tags), local script for the
  place's own name.** Three families, three jobs.
- **Name the place, don't describe it.** Guessed names go on the end-of-edit list (decided.md row 4).
- **Intro lines are human:** what the day felt like, and anything special (holiday, festival, a
  movie premiere). Look facts up before writing them (decided.md row 15).
- **Tags say what's happening, not where** (*finding my fortune drawer*, *snack hunting*) — the
  place label already said where.
- **Check one-line fit.** Long intros wrap and orphan a word; widen the box (`white-space:nowrap`,
  max-width ~1780 px) or shorten the line, and look at a rendered frame.
- **No labels over a day card**; a label that would collide moves to just after the card.

## Sound

- Normal-speed pieces: camera sound on (conversations, vendors, performers).
- Bursts: camera sound **off**; the music carries them.
- Music: calm lofi for city walks, ~-15 dB under speech, tracks rotated and crossfaded (45 frames),
  long fade at the end. The music bed in the reference build is in `~/Movies/music` (pixabay lofi
  tracks catalogued by robinli's `music-library` skill).
