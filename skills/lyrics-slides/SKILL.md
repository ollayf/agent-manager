---
name: lyrics-slides
description: "Generate beautiful HTML worship/lyrics slide presentations from song files or online lyrics. Use this skill whenever the user mentions song lyrics, worship slides, church presentations, lyric displays, or wants to turn lyrics into slides. Also trigger when the user provides .txt files with song lyrics and chords, or asks to search for song lyrics and display them as slides. This skill is especially relevant for worship leaders, church media teams, or anyone preparing song slides for a service or gathering."
---

# Lyrics Slides

Create zero-dependency HTML slide presentations from song lyrics. Each section (verse, chorus, bridge) becomes its own slide, with a title slide per song.

The output is designed for worship settings by default — warm, readable, distraction-free — but works for any song genre.

## Workflow

### Step 0: Check for songs.json

Before doing anything else, check if a `songs.json` file exists in the current working directory.

`songs.json` is the canonical song data format used by the Lyrica autoscroll system. If it exists, all lyrics are already parsed and structured — skip fetching and parsing entirely.

**If `songs.json` exists:**
1. Read the file. It's a JSON array of song objects with this structure:
   ```json
   [
     {
       "title": "Song Title",
       "artist": "Artist Name",
       "slides": [
         { "type": "title" },
         { "section": "Verse 1", "lines": ["Line 1", "Line 2", ...] },
         { "section": "Chorus", "lines": ["Line 1", "Line 2", ...] }
       ]
     }
   ]
   ```
   Slides with `"type": "title"` are title slides (no lines). All other slides have a `"section"` name and `"lines"` array.

2. Tell the user you found `songs.json` and list the songs it contains (title + artist). Ask which songs they want slides for, or all of them.

3. **Skip Steps 2** entirely — lyrics are already available. Jump straight to Step 1 (purpose/folder name), then Step 3 (output format), Step 4 (template), and Step 5 (generate).

4. When generating slides in Step 5, map the songs.json structure directly:
   - `{ "type": "title" }` → title slide with song title + artist
   - `{ "section": "Verse 1", "lines": [...] }` → section slide with the section label and each line as a `<p>`
   - Repeated section names (e.g., multiple "Chorus" slides) each get their own slide — this is intentional, not a bug

**If `songs.json` does not exist:** proceed with Step 1 as normal.

---

### Step 1: What is this for?

This is the first question to ask. It sets the folder name and gives context for the rest of the workflow.

Use AskUserQuestion with header "Purpose" and question:
"What are these slides for?"

This is a free-text question. Use the answer to:
- Create the output folder name in the format `YYYY-MM-DD-{name}` where `{name}` is a short kebab-case version of their answer (e.g., "Sunday worship" → `2025-04-19-sunday-worship`, "Youth group Friday" → `2025-04-18-youth-group-friday`)
- **Create the folder immediately** (including a `lyrics/` subfolder) — this is the working directory for everything that follows. All intermediate and final output goes here from the start. No more losing work if something fails halfway through.

### Step 2: Get Lyrics

**If lyrics files exist in the working directory:**
- Scan for `*.txt` files (or whatever pattern the user points to)
- Read each file, extract song name and lyrics
- Strip chord notations, parse into labeled sections (details in "Parsing Lyrics" below)

**If no files are found**, ask the user for song names + artists. Fetch lyrics using the browser harness (see below). If all online sources fail, tell the user and ask them to paste the lyrics or provide a file.

#### Searching Lyrics Online (Browser Harness)

Use the browser harness (`browser-harness`) to fetch lyrics. **Open all songs in parallel tabs in the same script** — this is much faster than fetching them one at a time.

**Priority order for worship songs:**

1. **pnwchords.com first** — it works reliably, has clean chord+lyric format, and covers most modern worship songs. Construct the URL as `https://www.pnwchords.com/chords/{kebab-song-title}` (e.g., `build-my-life`, `here-i-bow`, `worthy-of-it-all`). If that 404s, try appending the artist name: `build-my-life-housefires`.

2. **Tavily search as fallback** — if pnwchords returns 404, use `mcp__tavily__tavily_search` with query `"{Song Name}" {Artist Name} lyrics` (max_results: 5), then `mcp__tavily__tavily_extract` on the best result. Do NOT use `WebSearch` or `mcp__web-search-prime` (they return empty results). Note that Genius and AZLyrics block WebFetch but may work via Tavily extract.

3. **Google search via browser** — as a last resort, open a Google search in the browser and extract URLs from the results, then fetch the best one.

**Parallel fetching pattern:**

```python
browser-harness <<'PY'
# Open all songs at once — one tab per song
new_tab("https://www.pnwchords.com/chords/song-one")
wait_for_load()
js("window.scrollTo(0, document.body.scrollHeight)")
import time; time.sleep(1)
song1 = js("document.body.innerText")

new_tab("https://www.pnwchords.com/chords/song-two")
wait_for_load()
js("window.scrollTo(0, document.body.scrollHeight)")
time.sleep(1)
song2 = js("document.body.innerText")

# ... repeat for each song
print("SONG1:", song1[:6000])
print("SONG2:", song2[:6000])
PY
```

**Always scroll before reading** — after `wait_for_load()`, run `js("window.scrollTo(0, document.body.scrollHeight)")` and wait ~1 second before reading `innerText`. Some sites (including pnwchords) lazy-load content or have "show more" sections that won't appear in the first render. Skipping this step may silently truncate lyrics.

**Step — Parse:** From the fetched content, pull out the lyrics text. pnwchords pages interleave chord lines with lyric lines — strip lines that contain only chord tokens (see "Parsing Lyrics" section below for the chord-stripping rules). Look for section markers (Verse1, Verse2, Chorus, Bridge, etc.) and treat them as section labels.

**Section labels to use:**
- Verse 1, Verse 2, Verse 3... — numbered in order of appearance
- Pre-Chorus — if present before the chorus
- Chorus — label every occurrence
- Bridge — contrasting section
- Interlude — only if there are vocal/sung parts (skip purely instrumental interludes)
- Outro — closing section if distinct from the last chorus
- Intro — only if there are sung/spoken lines

#### Save Parsed Lyrics

After parsing lyrics for each song, save them as markdown files in the `lyrics/` subfolder. This creates a checkpoint — if HTML generation fails or needs changes, the lyrics are already captured and don't need to be re-fetched.

For each song, create `lyrics/{song-name}.md` with this structure:

```markdown
# Song Name — Artist Name

**Source:** URL where lyrics were found (e.g., `https://genius.com/...`)
**Fetched:** YYYY-MM-DD

---

## Verse 1
Line 1
Line 2
...

## Chorus
Line 1
Line 2
...

## Verse 2
...
```

For songs sourced from `.txt` files, use the file path as the source. Each section gets a `##` heading with its label, and the lyrics lines follow without `>` markers or bullet points — just plain text.

### Step 3: Ask Output Format

Use AskUserQuestion with header "Output" and question:
"How do you want the slides organized?"

Options:
1. **Separate files** (Recommended) — one HTML file per song, easier to reorder or swap
2. **Combined** — all songs in a single HTML file, good for a fixed set
3. **Both** — separate files plus one combined file

### Step 4: Preview Templates

Generate 3 mini preview HTML files showing a sample slide for each template vibe. This lets the user see the actual typography, colors, and feel before committing.

For each template (Sanctuary, Ember, Horizon):
1. Read the corresponding reference file from `references/`
2. Generate a single-slide HTML file with:
   - A sample chorus from one of the user's actual songs (use real lyrics, not placeholder text — this shows how their content looks in each style)
   - Full CSS from the template reference
   - The section label styled correctly
3. Save to `.claude-design/slide-previews/` (create if needed) as `preview-sanctuary.html`, `preview-ember.html`, `preview-horizon.html`
4. Open all 3 in the browser with `open`

Then use AskUserQuestion with header "Vibe" and question:
"Which style do you prefer? All 3 previews should be open in your browser."

Options:
1. **Sanctuary** — Warm cream, elegant serif, soft gold accents. Peaceful and minimal.
2. **Ember** — Deep charcoal, warm amber glow. Bold and intimate.
3. **Horizon** — Soft blue-white, teal accents, card layout. Fresh and modern.

After the user picks, clean up the preview files (delete `.claude-design/slide-previews/`) and proceed with the chosen template.

### Step 5: Generate Slides

For each song, create slides following this structure:
1. **Title slide** — Song name (large) + Artist (small, uppercase, muted)
2. **Section slides** — One per section, in song order
3. **Repeated sections** — Each occurrence gets its own slide (e.g., chorus appearing 3 times = 3 separate chorus slides)

All code goes into a single self-contained HTML file per output unit. No external dependencies beyond Google Fonts.

#### Font Sizing Guide

Getting lyrics to fit well across screen sizes is the trickiest part. Use these clamp ranges — they're tuned so lyrics are readable on a big projector but don't overflow on smaller screens:

| Element | clamp range | Notes |
|---------|-------------|-------|
| Song title | `clamp(1.8rem, 5.5vw, 4rem)` | Large but not overwhelming |
| Lyrics (up to 8 lines) | `clamp(1.05rem, 2.6vw, 2rem)` | Default for most sections |
| Lyrics (9-12 lines) | `clamp(0.9rem, 2.2vw, 1.6rem)` | Use a `.lyrics-compact` class with smaller sizing for bridge sections or extended repetitions |
| Section label | `clamp(0.5rem, 0.9vw, 0.75rem)` | Small, uppercase, decorative |
| Artist name | `clamp(0.75rem, 1.3vw, 1rem)` | Subtle, below the title |

When a section has many lines (like a bridge repeated 4x), add the `.lyrics-compact` class to reduce font size so everything fits within 100vh without scrolling. The key constraint: **never let content overflow a slide**. If in doubt, go smaller.

#### HTML Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[Song Name] or "Worship Slides"</title>
    <!-- Google Fonts link for chosen template -->
    <style>
        /* Theme variables (from template reference) */
        /* Reset */
        /* Viewport fitting (from template reference) */
        /* Slide styles */
        /* Typography (with font sizing guide above) */
        /* Animations (from template reference) */
        /* Nav dots (from template reference) */
        /* Responsive breakpoints (from template reference) */
        /* Reduced motion */
    </style>
</head>
<body>
    <nav class="nav-dots" aria-label="Slide navigation"></nav>

    <!-- Title slide -->
    <section class="slide">
        <div class="slide-content">
            <h1 class="song-title reveal">Song Name</h1>
            <p class="song-artist reveal">Artist</p>
        </div>
    </section>

    <!-- Section slide -->
    <section class="slide">
        <div class="slide-content">
            <span class="section-label reveal">Verse 1</span>
            <div class="lyrics reveal">
                <p>Line 1</p>
                <p>Line 2</p>
            </div>
        </div>
    </section>

    <!-- Compact slide for sections with many lines -->
    <section class="slide">
        <div class="slide-content">
            <span class="section-label reveal">Bridge</span>
            <div class="lyrics lyrics-compact reveal">
                <p>Line 1</p>
                <p>...</p>
            </div>
        </div>
    </section>

    <script>
        /* SlidePresentation class (see "Slide JS" section below) */
    </script>
</body>
</html>
```

#### Slide JS

Every presentation needs this SlidePresentation class. Include it verbatim:

```javascript
class SlidePresentation {
    constructor() {
        this.slides = document.querySelectorAll('.slide');
        this.currentSlide = 0;
        this.isScrolling = false;
        this.setupIntersectionObserver();
        this.setupKeyboardNav();
        this.setupTouchNav();
        this.setupWheelNav();
        this.setupNavDots();
    }
    setupIntersectionObserver() {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                    const index = Array.from(this.slides).indexOf(entry.target);
                    this.updateNavDots(index);
                }
            });
        }, { threshold: 0.5 });
        this.slides.forEach(slide => observer.observe(slide));
    }
    goToSlide(index) {
        if (index >= 0 && index < this.slides.length) {
            this.slides[index].scrollIntoView({ behavior: 'smooth' });
            this.currentSlide = index;
        }
    }
    setupKeyboardNav() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown' || e.key === ' ' || e.key === 'PageDown') {
                e.preventDefault(); this.goToSlide(this.currentSlide + 1);
            } else if (e.key === 'ArrowUp' || e.key === 'PageUp') {
                e.preventDefault(); this.goToSlide(this.currentSlide - 1);
            } else if (e.key === 'Home') {
                e.preventDefault(); this.goToSlide(0);
            } else if (e.key === 'End') {
                e.preventDefault(); this.goToSlide(this.slides.length - 1);
            }
        });
    }
    setupTouchNav() {
        let startY = 0;
        document.addEventListener('touchstart', (e) => {
            startY = e.touches[0].clientY;
        }, { passive: true });
        document.addEventListener('touchend', (e) => {
            const diff = startY - e.changedTouches[0].clientY;
            if (Math.abs(diff) > 50) {
                this.goToSlide(this.currentSlide + (diff > 0 ? 1 : -1));
            }
        });
    }
    setupWheelNav() {
        document.addEventListener('wheel', (e) => {
            if (this.isScrolling) return;
            this.isScrolling = true;
            if (e.deltaY > 0) this.goToSlide(this.currentSlide + 1);
            else if (e.deltaY < 0) this.goToSlide(this.currentSlide - 1);
            setTimeout(() => { this.isScrolling = false; }, 800);
        }, { passive: true });
    }
    setupNavDots() {
        const nav = document.querySelector('.nav-dots');
        this.slides.forEach((_, i) => {
            const dot = document.createElement('div');
            dot.className = 'nav-dot' + (i === 0 ? ' active' : '');
            dot.setAttribute('role', 'button');
            dot.setAttribute('aria-label', 'Slide ' + (i + 1));
            dot.addEventListener('click', () => this.goToSlide(i));
            nav.appendChild(dot);
        });
        this.dots = nav.querySelectorAll('.nav-dot');
    }
    updateNavDots(index) {
        this.currentSlide = index;
        this.dots.forEach((d, i) => d.classList.toggle('active', i === index));
    }
}
new SlidePresentation();
```

### Step 6: Deliver

The output folder already exists from Step 1. The final structure looks like:

```
YYYY-MM-DD-name/
├── 01-worthy-of-it-all.html
├── 02-way-maker.html
├── worship-slides.html          (if "combined" or "both" was chosen)
├── notes.md                     (song order, template used, any notes)
└── lyrics/                      (parsed lyrics + sources, saved in Step 2)
    ├── worthy-of-it-all.md
    ├── way-maker.md
    └── ...
```

1. Save all HTML files into the folder with a zero-padded order number prefix followed by the kebab-case song name (e.g., `01-song-name.html`, `02-another-song.html`). This makes the song order immediately visible in the filesystem and keeps files sorted correctly.
2. Create a `notes.md` file with:
   - Event/purpose name
   - Date
   - Template used
   - Song order (numbered list with song name + artist)
   - Slide count per song
   - Navigation instructions (Arrow keys, Space, scroll/swipe, click the dots on the right)
3. Open each HTML file with `open [folder]/[filename].html`
4. Tell the user the folder location and what's inside

## Parsing Lyrics from .txt Files

Song files typically look like this:

```
Song Name: Worthy Of It All - David Brymer

[Verse]
C                  D  C
All the saints and angels
     C               D  C
They bow before Your throne
```

**How to strip chords and extract lyrics:**

The pattern is consistent: chord symbols sit on their own line (or at the start of a line) above or interleaved with the lyric lines. Chord symbols are short tokens made of letters, numbers, and a few special characters.

Identify a line as a chord line if:
- It contains ONLY tokens that match the chord pattern: capital letters (A-G), optional modifiers (m, maj, min, dim, aug, sus, add), optional numbers, optional `/` for slash chords, optional `7`, and `///` markers
- It has no words longer than 4 characters (words like "the", "and" might appear in chord annotations, but real lyrics always have longer words)
- Common chord tokens: `G`, `Am7`, `C/D`, `F#m`, `Bbmaj7`, `///`

A line that mixes chords and lyrics (e.g., `G              D`) where the chords are spaced far apart to align with lyrics below — treat this as a chord-only line and skip it.

Keep the actual sung lyrics, preserving line breaks within a section.

**Extracting song name:**
- Look for a first line like `Song Name: X - Y` → X is the title, Y is the artist
- If no such line, use the filename (stripped of extension) as the song name

## Technical Requirements

- Every slide: `height: 100vh; height: 100dvh; overflow: hidden;`
- All font sizes use `clamp()` — never fixed px/rem for typography or spacing
- Responsive breakpoints at 700px, 600px, 500px height and 600px width
- `prefers-reduced-motion: reduce` support
- Navigation dots on right side, vertically centered
- Animations triggered by IntersectionObserver adding `.visible` class
- No scrolling within slides — use the compact font class for dense sections
