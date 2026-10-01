# Ember Template — Warm Bold

A deep, warm, intimate aesthetic. Dark charcoal with amber accents, candlelight warmth. Bold but inviting.

## Fonts

```html
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,500;0,600;1,400;1,500&family=Montserrat:wght@400;500;600&display=swap" rel="stylesheet">
```

- Lyrics: `Playfair Display` (classic serif with personality)
- Labels/Artist: `Montserrat` (geometric sans)

## Colors

```css
:root {
    --bg: #1a1814;
    --bg-card: #23201a;
    --text: #f0e8da;
    --text-muted: #8a7e6b;
    --accent: #d4a056;
    --accent-glow: rgba(212, 160, 86, 0.15);
    --font-serif: 'Playfair Display', Georgia, serif;
    --font-sans: 'Montserrat', sans-serif;
}
```

## Background

Subtle warm glow from below, like candlelight:
```css
.slide {
    background:
        radial-gradient(ellipse at 50% 100%, rgba(212, 160, 86, 0.06) 0%, transparent 60%),
        radial-gradient(ellipse at 20% 20%, rgba(212, 160, 86, 0.03) 0%, transparent 40%),
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
    font-weight: 500;
    letter-spacing: 0.2em;
    text-transform: uppercase;
}

/* Section labels — underline accent style */
.section-label {
    font-family: var(--font-sans);
    font-size: clamp(0.5rem, 0.9vw, 0.75rem);
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.3em;
    font-weight: 600;
    padding-bottom: clamp(0.5rem, 1vw, 1rem);
    margin-bottom: clamp(1.2rem, 3vw, 3rem);
    border-bottom: 1px solid rgba(212, 160, 86, 0.25);
    display: inline-block;
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

/* Lyrics — compact for sections with 9+ lines */
.lyrics-compact {
    font-size: clamp(0.9rem, 2.2vw, 1.5rem);
    line-height: 1.7;
}
```

## Animations

Smooth fade with slight scale:
```css
:root {
    --ease: cubic-bezier(0.25, 0.1, 0.25, 1);
}

.reveal {
    opacity: 0;
    transform: translateY(20px);
    transition: opacity 0.9s var(--ease), transform 0.9s var(--ease);
}

.slide.visible .reveal {
    opacity: 1;
    transform: translateY(0);
}

.slide.visible .reveal:nth-child(1) { transition-delay: 0.15s; }
.slide.visible .reveal:nth-child(2) { transition-delay: 0.35s; }
.slide.visible .reveal:nth-child(3) { transition-delay: 0.55s; }
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
    background: var(--accent);
    opacity: 0.2;
    cursor: pointer;
    transition: opacity 0.3s, transform 0.3s;
}

.nav-dot.active {
    opacity: 0.8;
    transform: scale(1.5);
}
```

## Responsive

```css
@media (max-height: 700px) {
    :root {
        --lyrics-size: clamp(0.9rem, 2.1vw, 1.5rem);
        --slide-padding: clamp(1.5rem, 3vw, 3rem);
    }
}
@media (max-height: 600px) {
    .nav-dots { display: none; }
    :root {
        --lyrics-size: clamp(0.8rem, 1.9vw, 1.2rem);
        --slide-padding: clamp(1rem, 2.5vw, 2rem);
    }
}
@media (max-height: 500px) {
    :root { --lyrics-size: clamp(0.7rem, 1.7vw, 1rem); }
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
