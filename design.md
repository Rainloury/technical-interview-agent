# Design — Technical Interview Agent

A locked design system for the local interview workspace. Every page uses the
same paper, ink, type pairing, control geometry, and state language. New screens
should extend this system rather than inventing a new theme.

## Genre

modern-minimal

## Macrostructure family

- Marketing / public entry: Edge-aligned auth intro with a working form.
- App pages: Workbench. The product surface is the content; pages use a
  functional page head, one primary work region, and a ledger for supporting
  records.
- Content / detail pages: Workbench detail. Evidence, report turns, and task
  states keep the same hairline and mono-metadata treatment.

## Theme

Cobalt.

- `--color-paper` oklch(98.4% 0.004 252)
- `--color-paper-2` oklch(96.2% 0.007 252)
- `--color-paper-3` oklch(93.3% 0.009 252)
- `--color-canvas` oklch(96.7% 0.006 252)
- `--color-surface` oklch(99.2% 0.003 252)
- `--color-ink` oklch(20% 0.018 258)
- `--color-ink-2` oklch(32% 0.018 257)
- `--color-muted` oklch(44% 0.015 255)
- `--color-rule` oklch(88% 0.01 254)
- `--color-accent` oklch(55% 0.205 260)
- `--color-accent-ink` oklch(98% 0.004 252)
- `--color-focus` oklch(58% 0.19 260)

The cobalt signal is limited to active navigation, primary actions, focus,
short rules, and evidence-state emphasis. Paper and graphite carry the layout.

## Typography

- Display: Space Grotesk, weight 500/600, roman only
- Body: Avenir Next → Segoe UI → PingFang SC, weight 400/500/600
- Mono: JetBrains Mono, weight 400/500
- Display tracking: `-0.035em` for large page heads
- Type scale anchor: `--text-display-s` =
  `clamp(2.25rem, 3vw + 1rem, 3.5rem)`
- Metadata uses the mono family at the `--text-xs` / `--text-2xs` tokens.

No italic display type. Headings carry emphasis through weight, scale, and
occasional accent rules, never through italic words.

## Spacing

The 4-point named scale lives in `web/tokens.css`. Pages use semantic spacing
tokens (`var(--space-md)`, `var(--space-lg)`) and never hard-coded visual
spacing values.

## Motion

- Easings: `--ease-out`, `--ease-in`, `--ease-in-out`
- Reveal pattern: none; the app is composed and stays still
- Hover / press: colour, border, and one-pixel press feedback
- Reduced motion: spatial movement collapses to `0.01ms`

Motion is limited to loading spinners, progress width, and local control
feedback. There are no scroll reveals or decorative loops.

## Microinteractions stance

- Silent success; visible state changes carry the confirmation.
- Focus rings appear instantly and never animate in.
- Press feedback goes down one pixel; there is no bounce or overshoot.
- Hover is additive to keyboard focus, never the only affordance.
- Primary buttons and navigation labels remain single-line.

## CTA voice

- Primary CTA: cobalt fill, 6px radius, 44px minimum height, icon plus named
  destination.
- Secondary CTA: transparent paper surface, hairline border, 6px radius.
- Destructive actions: keep the confirmation dialog; use danger ink and border,
  never a red flood.

## Per-page allowances

- Public entry: the auth intro may use a graphite canvas and one compact typed
  command illustration.
- App pages: no decorative imagery. The dashboard, records, forms, and report
  data are the visual material.
- Detail pages: evidence and report panels may use a top accent rule; they must
  not become nested cards.

## What pages MUST share

- The `T/` wordmark and mono `INTERVIEW AGENT` descriptor.
- Cobalt accent placement and cool paper band.
- Space Grotesk display, system-sans body, JetBrains Mono metadata.
- 6px control radius and 8px maximum card radius.
- Hairline rules, flat surfaces, and restrained shadows.
- Functional page heads; no stacked eyebrow-and-heading columns.

## What pages MAY differ on

- Density (workspace ledger vs. form-focused setup vs. reading-heavy report).
- Number of supporting columns within the Workbench family.
- Whether a supporting panel is graphite (session context) or paper (records).

## Exports

### tokens.css

The canonical tokens live in [`web/tokens.css`](./web/tokens.css). That file is
the portable source for colour, type, spacing, motion, radius, and elevation.
The global stylesheet imports it before the page rules.

### Tailwind v4 `@theme`

```css
@theme {
  --color-paper: oklch(98.4% 0.004 252);
  --color-paper-2: oklch(96.2% 0.007 252);
  --color-canvas: oklch(96.7% 0.006 252);
  --color-ink: oklch(20% 0.018 258);
  --color-ink-2: oklch(32% 0.018 257);
  --color-accent: oklch(55% 0.205 260);
  --color-accent-ink: oklch(98% 0.004 252);
  --color-focus: oklch(58% 0.19 260);
  --font-display: "Space Grotesk", "Avenir Next", "PingFang SC", sans-serif;
  --font-body: "Avenir Next", "Segoe UI", "PingFang SC", sans-serif;
  --font-mono: "JetBrains Mono", "SFMono-Regular", monospace;
  --spacing-md: 1rem;
  --spacing-lg: 1.5rem;
  --radius-card: 0.5rem;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
}
```

### DTCG `tokens.json`

```json
{
  "color": {
    "paper": { "$value": "oklch(98.4% 0.004 252)", "$type": "color" },
    "canvas": { "$value": "oklch(96.7% 0.006 252)", "$type": "color" },
    "ink": { "$value": "oklch(20% 0.018 258)", "$type": "color" },
    "accent": { "$value": "oklch(55% 0.205 260)", "$type": "color" },
    "focus": { "$value": "oklch(58% 0.19 260)", "$type": "color" }
  },
  "font": {
    "display": { "$value": "Space Grotesk", "$type": "fontFamily" },
    "body": { "$value": "Avenir Next", "$type": "fontFamily" },
    "mono": { "$value": "JetBrains Mono", "$type": "fontFamily" }
  },
  "space": {
    "md": { "$value": "1rem", "$type": "dimension" },
    "lg": { "$value": "1.5rem", "$type": "dimension" }
  }
}
```

### shadcn/ui CSS variables

```css
:root {
  --background: 98.4% 0.004 252;
  --foreground: 20% 0.018 258;
  --primary: 55% 0.205 260;
  --primary-foreground: 98% 0.004 252;
  --muted: 96.2% 0.007 252;
  --muted-foreground: 44% 0.015 255;
  --border: 88% 0.01 254;
  --input: 88% 0.01 254;
  --ring: 58% 0.19 260;
  --radius: 0.375rem;
}
```
