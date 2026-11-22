# Decided — insta360-trip-edit — the questions not to ask again

Read this **before** reaching for `AskUserQuestion`. Every row below has already been put to the
user and answered (session 2026-11-03, Tokyo walk). Quotes are the user's own words.

| # | The question | Decided | When |
|---|---|---|---|
| 1 | **Camera card** | **Read-only. Copy first, work from the copy, never delete/move anything on the card.** *"DO NOT DELETE ANYTHING IN THE INSTA360 ITSELF. copy it over"* | 2026-11-03 |
| 2 | **How to review hours of footage** | **Funnel, never frame-by-frame: 20 s sheets → scan flags → zoom → transcripts only where speech exists; Palmier is the editor.** *"most token efficient way… do not miss out any important part… rather than just looking at it frame by frame"* | 2026-11-03 |
| 3 | **Speech-led or visual-led selection** | **Visual-led for walking footage; speech is a bonus signal.** *"not a lot of it has any talking by the way"* | 2026-11-03 |
| 4 | **When to ask questions** | **Build the whole edit first; ask every open question in ONE list at the end.** *"cut everything first. then ill answer you full list of questions at the end"* / *"can you just put everything together first"* | 2026-11-03 |
| 5 | **Length / scope** | **One long video keeping all important information — not a highlight reel.** *"one long one, all important information not cut"* | 2026-11-03 |
| 6 | **What to cut** | **Only junk: camera drops, fingers/hands over the lens, fumbling, walls/elevators at clip ends, test clips.** *"cut certain parts (e.g. i dropped the camera)"* | 2026-11-03 |
| 7 | **Plain walking** | **Keep it, sped up — especially where the place is nice. Boring stretches may skim ahead.** *"speed up certain parts if its just walking but you dont want to cut it… if the place is nice"* | 2026-11-03 |
| 8 | **Speed-up style** | **Short 2x bursts (12 s of source → 6 s) alternating with ~6 s normal-speed beats. Never sustained 3x.** *"its tooo fast. do short bursts of speed ups then normal speed"* | 2026-11-03 |
| 9 | **Sound in bursts** | **Camera audio fully muted in every burst** (add bursts with `includeAudio:false`). *"silence the video sound when you are speeding up it looks bad"* | 2026-11-03 |
| 10 | **Music** | **A fitting bed under the entire video by default** (calm lofi for city walks, ~-15 dB, rotate tracks, crossfade). *"apply some audio behind the whole thing that makes sense"* | 2026-11-03 |
| 11 | **Text during speed-ups** | **Every burst carries a tag saying what is happening.** *"when speeding up write some text"* | 2026-11-03 |
| 12 | **Text design** | **Catalog-grade animated overlays (HyperFrames-style), not the editor's plain text.** Fonts/animations may change; the direction stays (see `references/style.md`). *"all the text looks bad… look at this to see what is good: hyperframes.heygen.com/catalog"* / *"no need to use the same fonts and animations but the direction is there"* | 2026-11-03 |
| 13 | **How scenes are labelled** | **Day number + place on every scene label; a day card opens each day.** *"label day number and location"* / *"just put by day number"* | 2026-11-03 |
| 14 | **Day intros** | **Each day card carries a one-line intro sentence, not just a date.** *"do you have any intro text for each day?"* | 2026-11-03 |
| 15 | **Real-world context in titles** | **Look it up first (holidays, local events), propose wording, then render.** *"can you first find out what day is it today in the japanese calendar"* → *"yes do it"* | 2026-11-03 |
| 16 | **Proving understanding** | **Hand over a per-clip table: source time → what happens → treatment → time in the final video.** *"map every video… so i am convinced you are clear… display this nicely in a table"* | 2026-11-03 |
| 17 | **Photos on the card** | **Look at them; include only ones that show something the clips don't, as a push-in with a place label.** *"the rest dont need to keep just show the Godzilla statue"* | 2026-11-03 |
| 18 | **Far-away performers / subjects** | **Zoom in (transform scale 1.6–2x on the 4K source) so the subject fills the frame.** *"can we zoom in on the street performer?"* | 2026-11-03 |
| 19 | **Reference style** | **The robinli / edit-large-video long-footage approach is the house method; this skill is its travel variant.** *"take the robinli project edit long video as reference"* | 2026-11-03 |

## Settled elsewhere, and still true here

Not restated — read them in `edit-large-video` (`~/.claude/skills/edit-large-video/`):

- **one export at a time, batch changes before exporting** → its "Batch every change, then export"
- **name places, don't describe them; flag guesses** → its review-sheet step

## What is still worth asking

- **Place names** — always batch the guesses into one list at the end (row 4). Locals know; you don't.
- **Which day is "special" and why**, when the user says so — offer the looked-up context (row 15), let them confirm.
- **Music mood**, only if the trip is not a calm city walk (night club, hike, beach…) — otherwise pick lofi.

## Asked and should not have been

| Asked | Where it was already answered |
|---|---|
| "How long should the final video be?" (asked before building) | row 5 — one long video; and row 4 — don't ask mid-build. Cost: a round trip and a correction. |
| Place names asked before the edit existed | row 4 — the user wanted them in one list *after* seeing the cut. |
