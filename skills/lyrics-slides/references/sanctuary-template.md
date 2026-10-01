# Sanctuary Template — Peaceful Light

A warm, minimal, worship-friendly aesthetic. Cream backgrounds, elegant serif typography, soft gold accents.

## Fonts

```html
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
```

- Lyrics: `Cormorant Garamond` (serif, elegant)
- Labels/Artist: `DM Sans` (clean sans-serif)

## Colors

```css
:root {
    --bg: #faf8f5;
    --text: #2d2a26;
    --text-muted: #a09889;
    --accent: #c4b69a;
    --font-serif: 'Cormorant Garamond', Georgia, serif;
    --font-sans: 'DM Sans', sans-serif;
}
```

## Background

Subtle layered radial gradients for warmth:
```css
.slide {
    background:
        radial-gradient(ellipse at 30% 70%, rgba(196, 182, 154, 0.08) 0%, transparent 50%),
        radial-gradient(ellipse at 70% 30%, rgba(196, 182, 154, 0.05) 0%, transparent 50%),
        var(--bg);
}
```

## Typography

```css
/* Title slide */
.song-title {
    font-family: var(--font-serif);
    font-size: clamp(1.8rem, 5.5vw, 4rem);
    font-weight: 400;
    letter-spacing: 0.02em;
    line-height: 1.2;
    color: var(--text);
}

.song-artist {
    font-family: var(--font-sans);
    font-size: clamp(0.75rem, 1.3vw, 1rem);
    color: var(--text-muted);
    font-weight: 400;
    letter-spacing: 0.15em;
    text-transform: uppercase;
}

/* Section labels */
.section-label {
    font-family: var(--font-sans);
    font-size: clamp(0.5rem, 0.9vw, 0.75rem);
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.25em;
    display: flex;
    align-items: center;
    gap: clamp(0.5rem, 1.5vw, 1.5rem);
}

.section-label::before,
.section-label::after {
    content: '';
    width: clamp(1rem, 3vw, 3rem);
    height: 1px;
    background: var(--accent);
}

/* Lyrics — default for sections up to 8 lines */
.lyrics {
    font-family: var(--font-serif);
    font-size: clamp(1.05rem, 2.6vw, 2rem);
    line-height: 1.85;
    font-weight: 400;
    color: var(--text);
    max-width: 800px;
}

/* Lyrics — compact for sections with 9+ lines (extended bridges, repeated sections) */
.lyrics-compact {
    font-size: clamp(0.9rem, 2.2vw, 1.6rem);
    line-height: 1.7;
}
```

## Animations

Gentle fade-up entrance:
```css
:root {
    --ease: cubic-bezier(0.25, 0.1, 0.25, 1);
}

.reveal {
    opacity: 0;
    transform: translateY(24px);
    transition: opacity 0.8s var(--ease), transform 0.8s var(--ease);
}

.slide.visible .reveal {
    opacity: 1;
    transform: translateY(0);
}

/* Stagger children */
.slide.visible .reveal:nth-child(1) { transition-delay: 0.1s; }
.slide.visible .reveal:nth-child(2) { transition-delay: 0.3s; }
.slide.visible .reveal:nth-child(3) { transition-delay: 0.5s; }
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
    width: clamp(5px, 0.5vw, 7px);
    height: clamp(5px, 0.5vw, 7px);
    border-radius: 50%;
    background: var(--text-muted);
    opacity: 0.25;
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
        --lyrics-size: clamp(0.95rem, 2.2vw, 1.6rem);
        --slide-padding: clamp(1.5rem, 3vw, 3rem);
    }
}
@media (max-height: 600px) {
    .nav-dots { display: none; }
    :root {
        --lyrics-size: clamp(0.85rem, 2vw, 1.3rem);
        --slide-padding: clamp(1rem, 2.5vw, 2rem);
    }
}
@media (max-height: 500px) {
    :root { --lyrics-size: clamp(0.75rem, 1.8vw, 1.1rem); }
}
@media (max-width: 600px) {
    :root { --title-size: clamp(1.5rem, 8vw, 3rem); }
    .lyrics { max-width: 95%; }
}
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        transition-duration: 0.2s !important;
    }
    html { scroll-behavior: auto; }
}
```
