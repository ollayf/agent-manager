# Horizon Template — Fresh Modern

A clean, uplifting, contemporary aesthetic. Soft blue-white tones, teal accents, card-style layout with gentle shadows. Fresh and bright.

## Fonts

```html
<link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;0,600;1,400;1,500&family=Nunito+Sans:wght@400;500;600&display=swap" rel="stylesheet">
```

- Lyrics: `Lora` (contemporary serif, friendly)
- Labels/Artist: `Nunito Sans` (soft rounded sans)

## Colors

```css
:root {
    --bg-start: #f0f5fa;
    --bg-end: #e8eff8;
    --card-bg: #ffffff;
    --text: #2a3342;
    --text-muted: #7b8a9e;
    --accent: #3d8b8b;
    --accent-light: rgba(61, 139, 139, 0.1);
    --shadow: rgba(42, 51, 66, 0.06);
    --font-serif: 'Lora', Georgia, serif;
    --font-sans: 'Nunito Sans', sans-serif;
}
```

## Background

Soft gradient with subtle card:
```css
.slide {
    background: linear-gradient(160deg, var(--bg-start) 0%, var(--bg-end) 100%);
}

.slide-content {
    background: var(--card-bg);
    border-radius: clamp(12px, 2vw, 24px);
    box-shadow: 0 4px 24px var(--shadow), 0 1px 3px var(--shadow);
    margin: clamp(1rem, 2vw, 2rem);
    max-width: 900px;
    width: 100%;
    margin-left: auto;
    margin-right: auto;
}
```

## Typography

```css
/* Title slide */
.song-title {
    font-family: var(--font-serif);
    font-size: clamp(1.8rem, 5.5vw, 4rem);
    font-weight: 500;
    letter-spacing: 0;
    line-height: 1.2;
    color: var(--text);
}

.song-artist {
    font-family: var(--font-sans);
    font-size: clamp(0.75rem, 1.3vw, 1rem);
    color: var(--text-muted);
    font-weight: 600;
    letter-spacing: 0.15em;
    text-transform: uppercase;
}

/* Section labels — pill badge style */
.section-label {
    font-family: var(--font-sans);
    font-size: clamp(0.5rem, 0.85vw, 0.7rem);
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.2em;
    font-weight: 600;
    padding: clamp(4px, 0.5vw, 8px) clamp(12px, 1.5vw, 24px);
    background: var(--accent-light);
    border-radius: 100px;
    display: inline-block;
    margin-bottom: clamp(1rem, 2.5vw, 2.5rem);
}

/* Lyrics — default for sections up to 8 lines */
.lyrics {
    font-family: var(--font-serif);
    font-size: clamp(1.05rem, 2.5vw, 2rem);
    line-height: 1.85;
    font-weight: 400;
    color: var(--text);
    max-width: 700px;
}

/* Lyrics — compact for sections with 9+ lines */
.lyrics-compact {
    font-size: clamp(0.9rem, 2vw, 1.5rem);
    line-height: 1.7;
}
```

## Animations

Subtle scale-in entrance:
```css
:root {
    --ease: cubic-bezier(0.25, 0.1, 0.25, 1);
}

.reveal {
    opacity: 0;
    transform: scale(0.96) translateY(12px);
    transition: opacity 0.7s var(--ease), transform 0.7s var(--ease);
}

.slide.visible .reveal {
    opacity: 1;
    transform: scale(1) translateY(0);
}

.slide.visible .reveal:nth-child(1) { transition-delay: 0.1s; }
.slide.visible .reveal:nth-child(2) { transition-delay: 0.25s; }
.slide.visible .reveal:nth-child(3) { transition-delay: 0.4s; }
```

## Nav Dots

```css
.nav-dots {
    position: fixed;
    right: clamp(0.5rem, 1.5vw, 1.5rem);
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    flex-direction: column;
    gap: clamp(5px, 0.6vw, 9px);
    z-index: 100;
}

.nav-dot {
    width: clamp(6px, 0.5vw, 8px);
    height: clamp(6px, 0.5vw, 8px);
    border-radius: 50%;
    background: var(--accent);
    opacity: 0.2;
    cursor: pointer;
    transition: opacity 0.3s, transform 0.3s;
}

.nav-dot.active {
    opacity: 0.7;
    transform: scale(1.5);
}
```

## Responsive

```css
@media (max-height: 700px) {
    :root {
        --lyrics-size: clamp(0.9rem, 2vw, 1.4rem);
        --slide-padding: clamp(1.5rem, 3vw, 3rem);
    }
}
@media (max-height: 600px) {
    .nav-dots { display: none; }
    :root {
        --lyrics-size: clamp(0.8rem, 1.8vw, 1.1rem);
        --slide-padding: clamp(1rem, 2.5vw, 2rem);
    }
}
@media (max-height: 500px) {
    :root { --lyrics-size: clamp(0.7rem, 1.6vw, 0.95rem); }
}
@media (max-width: 600px) {
    :root { --title-size: clamp(1.5rem, 7vw, 2.8rem); }
    .lyrics { max-width: 95%; }
    .slide-content { border-radius: 12px; margin: 0.5rem; }
}
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        transition-duration: 0.2s !important;
    }
    html { scroll-behavior: auto; }
}
```
