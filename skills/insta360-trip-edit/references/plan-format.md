# trip.json — the plan format (format 1)

One file holds every editorial decision; `plan.py` derives every number. Full example:
[`../examples/tokyo-2026.trip.json`](../examples/tokyo-2026.trip.json).

```jsonc
{
  "fps": 30,
  "pattern": {"burst_src": 12, "burst_speed": 2, "nice": [6, 12], "boring": [4, 40]},
  //          12 s of source per burst at 2x = 6 s on screen
  //          nice:   6 s normal beat, burst, skip 12 s   (≈2.5x overall, keeps the feel)
  //          boring: 4 s normal beat, burst, skip 40 s   (skims ahead)
  "days": [{"day": 3, "start": ["014", 0], "short": "3 Nov",
            "kicker": "DAY 03 · 文化の日 CULTURE DAY", "word": "Asakusa", "local": "浅草",
            "label": "Tue · 3 Nov 2026 · a national holiday in Japan",
            "intro": "A special day — Culture Day in Asakusa: …"}],
  "segments": [ // story order; source seconds; every second of every clip ideally accounted for
    {"clip": "005", "s": 0,   "e": 9.5, "kind": "cut",  "what": "Setting up, arm over the lens"},
    {"clip": "005", "s": 9.5, "e": 200, "kind": "nice", "tag": "exploring asakusa", "what": "…"},
    {"clip": "005", "s": 200, "e": 250, "kind": "H",    "what": "Steak stand vendor chat"},
    {"clip": "016", "s": 720, "e": 960, "kind": "nice", "tag": "around the temple grounds",
     "burst_shift": {"786": 789.5}},          // move one burst off a finger-on-lens moment
    {"clip": "photo:godzilla", "s": 0, "e": 5, "kind": "photo", "what": "Godzilla photo"}
  ],
  "labels": [["005", 200, "Kobe beef stand", null], ["016", 260, "Sensō-ji", "浅草寺"]],
  "photos": {"godzilla": {"file": "storage/Camera01/IMG_….jpg", "seconds": 5}},
  "zoom":   {"014": {"scale": 1.7, "subject": [0.42, 0.58], "at": [0.5, 0.55]}}
}
```

## Choosing a kind

| kind | when | result |
|---|---|---|
| `H` | anything happens: talking, buying, a show, a landmark moment, a ritual | 1x, sound on |
| `nice` | walking somewhere worth seeing (busy streets, temples, neon) | beats + muted 2x bursts |
| `boring` | walking that only connects places (residential, to the hotel) | short beat, burst, skip |
| `walk` | a single clean 1x shot (e.g. the first clean seconds after a bad start) | 1x, sound on |
| `photo` | a still worth showing (`photo.py` makes the clip; media key `photo:<name>`) | push-in, no sound |
| `cut` | junk — documented so the clip map shows it | nothing |

Bursts land wherever the pattern puts them; `survey.py review` shows if one lands on a bad
moment. Fix with `burst_shift`, a `cut`, or a shorter `e` — never by editing the timeline alone,
or the plan and the timeline disagree and every later placement is wrong.

`media.json` (given to `plan.py --media`) maps clip ids to Palmier mediaRefs:
`{"005": "DDDD0C8D", "photo:godzilla": "1911F32A"}`. `music.json`: `[{"mediaRef": "…", "duration": 159.19}]`.
`zoom` is applied by hand in Palmier (palmier-recipe §4); it is recorded here so a rebuild repeats it.
