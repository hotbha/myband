# The design system

One product, one surface. This file is the source of truth for how MyBand.video looks and
moves, and every token in it is a value that already ships.

The landing page was designed first and the app was not, which is why this file exists. It was
written by reading the values out of `apps/web/app/globals.css` rather than by inventing a
palette and asking the app to move to it: **the marketing surface was already correct, so the
marketing surface is the specification.** Nothing here is aspirational.

> **Status:** implemented. Palette, typography, surfaces, motion and the component recipes below
> are live. Section 12 lists the two rules that are deliberately _not_ implemented yet.

## 1. The one mechanism worth knowing

There is exactly one theming mechanism, and it is a CSS custom-property override:

```css
.marketing,      /* the landing page                  */
.product {
  /* the dashboard, song page, login   */
  --canvas: oklch(0.145 0.018 285);
  --signal: oklch(0.66 0.19 287);
  --background: oklch(0.145 0.018 285);
  --foreground: oklch(0.975 0.004 285);
  /* ...and the rest of the neutral scale */
}
```

Inside either surface, **every shadcn/ui component is already on-palette** - `Card`, `Badge`,
`Button`, `Input`, `Tabs`, `Accordion` - because they are built from the same token names. That is
why there is no fork of `components/ui`, why `variant="outline"` looks right on a dark surface, and
why adding a new shadcn component cannot break the theme.

Two rules follow from the mechanism, and they are not negotiable:

1. **Never hard-code a colour in a component.** Reach for a token (`text-foreground`,
   `border-border`, `text-signal-soft`). A literal `#1a1a22` is invisible to the surface switch and
   is the one way to break the "same product everywhere" guarantee.
2. **Dark is the product's own theme, not a user preference.** A surface opts in by carrying
   `product` (or `marketing`) and `dark` on its root element, plus `data-surface` so the document
   behind it can match. There is no light mode and no toggle.

`app/layout.tsx` sets neither class. Surfaces own their own palette, which is what lets a
screen be added without a stylesheet change.

## 2. Colour

Five accents do all the work. Everything else is a neutral on a violet-tinted ramp, which is the
difference between "a dark theme" and "the same dark theme as the landing page" - the hue, not the
lightness, is what carries the identity.

| Token             | Value (oklch)     | Job                                                                            |
| ----------------- | ----------------- | ------------------------------------------------------------------------------ |
| `--canvas`        | `0.145 0.018 285` | The document behind everything. Also `themeColor` in the layout.               |
| `--signal`        | `0.66 0.19 287`   | **The** accent. Primary actions, the first chord chip, one hairline per panel. |
| `--signal-soft`   | `0.79 0.11 288`   | Eyebrows, icon strokes, meta text that should read as accent rather than grey. |
| `--signal-strong` | `0.55 0.22 287`   | The dark end of every signal gradient. Never used alone as a fill.             |
| `--pulse`         | `0.84 0.13 195`   | The second accent: live states, success, the far end of the waveform gradient. |

Neutrals:

| Token                | Value                | Job                                               |
| -------------------- | -------------------- | ------------------------------------------------- |
| `--background`       | `0.145 0.018 285`    | Surface background (equals canvas).               |
| `--foreground`       | `0.975 0.004 285`    | Body text. Never pure white.                      |
| `--card`             | `0.195 0.02 285`     | One step up from the canvas.                      |
| `--popover`          | `0.185 0.02 285`     | Menus, popovers.                                  |
| `--muted`            | `0.24 0.02 285`      | Inset wells (progress tracks, quiet chips).       |
| `--muted-foreground` | `0.75 0.02 285`      | Secondary text. The most-used colour on the site. |
| `--secondary`        | `0.26 0.02 285`      | Chip fills, selected segments.                    |
| `--accent`           | `0.28 0.035 287`     | Hover state for ghost/outline controls.           |
| `--border`           | `oklch(1 0 0 / 9%)`  | The only structural border.                       |
| `--input`            | `oklch(1 0 0 / 12%)` | Form controls, one step louder than `--border`.   |
| `--ring`             | `0.62 0.19 287`      | Focus. Same family as signal, deliberately.       |
| `--destructive`      | `0.68 0.19 25`       | Failures only. Never decoration.                  |

### How the accents are spent

- **Signal** is a budget, not a colour. One gradient CTA per view; one `via-signal/60` hairline per
  panel; the signal-tinted hover glow on a card that is genuinely interactive. A screen with three
  signal-filled buttons has no primary action.
- **Pulse** marks _live_ and _good_: the heartbeat dot in the header, the `MIDI ready` badge, the
  success end of a gradient. It is never used for a failure.
- **Destructive** appears as a 10% tint + 40% border + full-strength text
  (`border-destructive/40 bg-destructive/10 text-destructive`). A solid red fill is reserved for
  the destructive button variant, which this product does not currently use.
- Everything else is grey. When a value needs emphasis and is not an accent, it gets weight,
  monospace or a hairline - not a colour.

## 3. Typography

Three families, each with one job, all self-hosted through `next/font` (no render-blocking
third-party request, no layout shift).

| Role    | Family              | Class                 | Job                                                                                                     |
| ------- | ------------------- | --------------------- | ------------------------------------------------------------------------------------------------------- |
| Display | Bricolage Grotesque | `font-display`        | H1, H2, and the values that read as titles: a song title, a chord name, a big metric.                   |
| Body    | Plus Jakarta Sans   | `font-sans` (default) | Everything read as a sentence.                                                                          |
| Data    | JetBrains Mono      | `font-mono`           | **Every measurement.** BPM, key strength, timings, note counts, byte sizes, job ids, pipeline versions. |

The monospace is not decoration. It exists so a column of numbers lines up, and so that "measured
by a machine" and "written by a person" are distinguishable at a glance. When a value came out of
the analyser it is mono; when it is a label for one it is not.

| Style       | Recipe                                                                                                     | Used for                                              |
| ----------- | ---------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| Hero        | `font-display text-[2.7rem] leading-[0.97] font-semibold tracking-[-0.035em] sm:text-6xl lg:text-[4.1rem]` | The one headline on the landing page.                 |
| Page title  | `font-display text-2xl font-semibold tracking-tight sm:text-3xl`                                           | Screen titles.                                        |
| Panel title | `font-display text-lg tracking-tight`                                                                      | A section inside a screen.                            |
| Eyebrow     | `font-mono text-[0.7rem] tracking-[0.22em] text-signal-soft uppercase`                                     | Above every titled section.                           |
| Micro-label | `font-mono text-[0.6rem] tracking-[0.16em] text-muted-foreground uppercase`                                | Above a metric, inside a tile.                        |
| Body        | `text-sm text-muted-foreground`                                                                            | Prose, descriptions, hints.                           |
| Lede        | `text-base/relaxed text-pretty text-muted-foreground sm:text-lg/relaxed`                                   | Under a title, once.                                  |
| Data value  | `font-mono tabular-nums`                                                                                   | Any number. `tabular-nums` is required, not optional. |
| Footnote    | `text-xs/relaxed text-muted-foreground`                                                                    | The sentence that keeps a claim honest.               |

Rules: headings get `text-balance`, prose gets `text-pretty`, and a sentence that qualifies a
number sits directly under it in `text-xs` - never in a tooltip, never behind a hover.

## 4. Layout widths

Two widths, because a page that is read and a page that is worked in are not the same width.

| Name              | Width                            | Where                                                    |
| ----------------- | -------------------------------- | -------------------------------------------------------- |
| Marketing content | `max-w-6xl` (72rem / 1152px)     | Every landing page section. A reading measure.           |
| Workspace         | `max-w-[96rem]` (96rem / 1536px) | `AppShell`'s container. The dashboard and the song page. |
| Reading column    | `max-w-3xl` (48rem / 768px)      | A left-aligned block of prose inside a workspace.        |
| Auth card         | `max-w-md` (28rem / 448px)       | The form side of `/login`.                               |

**Why the workspace is wider than the landing page.** 1152px is the widest a line of prose should
be read at, and the landing page is prose. The workspace is not: it is a set of panels whose
contents are numbers, chords and lists, and none of them get harder to read when they get more
room. A 1536px canvas is what lets the dashboard carry a library rail, a centre column and a
utility rail on a 1920px display with real gaps rather than at 100% width.

The `AppShell` container is the only place that decides this. Individual screens set columns
inside it and never set their own `max-w` - otherwise a screen added later silently ends up
narrower than the one beside it.

Screen padding is `px-5 sm:px-8` in the workspace and `px-5 sm:px-6` on the landing page, with
`py-10 lg:py-12` above the fold in the workspace (the landing page's `pt-28 sm:pt-36` accounts for
a fixed header over a hero, which no workspace screen has).

## 5. Spacing scale

A 4px base, and the steps that are actually used. Anything off this list is a mistake rather than a
new decision.

| Step  | px  | Used for                                            |
| ----- | --- | --------------------------------------------------- |
| `1`   | 4   | Icon-to-label, `gap-1` inside a pill.               |
| `1.5` | 6   | A label and its value.                              |
| `2`   | 8   | Rows in a list, gap between chips.                  |
| `2.5` | 10  | Inside a metric tile.                               |
| `3`   | 12  | Gaps between form fields, `gap-3` in a toolbar.     |
| `4`   | 16  | Gap between cards in a grid; padding inside a tile. |
| `5`   | 20  | Panel padding at mobile.                            |
| `6`   | 24  | Panel padding at desktop; gap between panels.       |
| `8`   | 32  | Gap between a screen's regions.                     |
| `10`  | 40  | Section padding at mobile.                          |
| `14`  | 56  | Heading to its first panel.                         |
| `20`  | 80  | Section padding at desktop.                         |

Landing page sections are `py-20 sm:py-28`; workspace regions are `gap-6` / `gap-8` inside a
`py-10`. A workspace is denser than a landing page by design - it has to hold three columns.

## 6. Borders and radius

`--radius` is `0.625rem` (10px), which drives `--radius-sm/md/lg/xl` as `calc()` offsets. Panels do
not use that scale - they are `rounded-3xl` (24px), because a 24px radius against a 10px control
radius is what reads as "surface" rather than "button".

| Element          | Radius                      | Note                                                                |
| ---------------- | --------------------------- | ------------------------------------------------------------------- |
| Panel (glass)    | `rounded-3xl`               | The landing page's analyser and beta card; the workspace's regions. |
| Inner tile       | `rounded-xl`                | Metric tiles, chord chips on the timeline.                          |
| Control          | `rounded-md` / `rounded-lg` | shadcn's own scale, via `--radius`.                                 |
| Auth-scale input | `rounded-xl`                | The taller inputs (`h-11`).                                         |
| Pill             | `rounded-full`              | Status badges, the beta counter.                                    |

Every border is one of exactly four things:

1. **A structural hairline** - `border-border`, which is `oklch(1 0 0 / 9%)` inside a surface.
2. **A glass edge** - `border-white/[0.07]` to `border-white/[0.09]`, one notch softer than
   `--border`, for the outermost edge of a panel over the aurora.
3. **A dashed edge** - empty states and upload zones only. Dashed means "nothing here yet", and it
   is never used for anything that exists.
4. **A semantic tint** - `border-destructive/40`, `border-signal/30`, `border-pulse/30`.

There is no third grey. A `border-zinc-700` in a component is a bug: it will not survive a surface
switch and it is not in the ramp.

## 7. Glass surfaces

Four levels, and the rule is that a level-1 panel never sits inside another level-1 panel.

| Level           | Recipe                                                                                      | Example                                              |
| --------------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| **L0 - Canvas** | `bg-canvas` + aurora blobs + masked grid + 3.5% grain + vignette                            | `AmbientBackground`, behind everything, `-z-10`.     |
| **L1 - Panel**  | `rounded-3xl border border-white/[0.07] bg-white/[0.025] backdrop-blur-xl` + a top hairline | The analyser, the beta card, every workspace region. |
| **L2 - Tile**   | `rounded-xl border border-white/[0.07] bg-white/[0.02]`                                     | A metric, a chord slot, a library row.               |
| **L3 - Chip**   | `rounded-lg border border-white/10 bg-white/[0.05] font-mono`                               | A chord label, a job id, a small tag.                |

The **top hairline** is the signature move and it belongs to every L1 panel:

```tsx
<div className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-signal/60 to-transparent" />
```

It is what makes a translucent panel read as a lit surface rather than a grey box, and it is the
only place signal appears as a _line_ rather than a fill. `via-signal/70` on the hero,
`via-signal/60` elsewhere - one deliberate exception, not a rule.

`backdrop-blur-xl` is used on L1 only. Blurring forty rows is how a list becomes slow on a laptop,
and the tiles do not need it: they sit on an already-blurred panel.

The canvas is `position: fixed`, `-z-10`, `aria-hidden`, and never re-renders - it is one element
per surface, mounted by the shell, not by a screen.

## 8. Shadows

Shadows here are two different tools and they are not interchangeable.

| Shadow           | Value                                            | Meaning                                           |
| ---------------- | ------------------------------------------------ | ------------------------------------------------- |
| Ambient          | `shadow-[0_40px_120px_-50px_oklch(0_0_0/0.95)]`  | Depth. On a hero-scale L1 panel, over the aurora. |
| Brand chip       | `shadow-[0_8px_24px_-10px_var(--signal)]`        | The logo tile.                                    |
| Primary CTA      | `shadow-[0_16px_40px_-16px_var(--signal)]`       | A filled signal button.                           |
| Interactive lift | `hover:shadow-[0_28px_70px_-40px_var(--signal)]` | A card that is a link.                            |

The rule: **black shadows for structure, signal-tinted shadows for interaction.** A grey drop
shadow on a coloured button is what makes a dark theme look like a light theme with the lights
off. Nothing in this product uses Tailwind's default `shadow-sm`/`shadow-md` for anything
decorative - `shadow-sm` survives only inside `components/ui`, where shadcn put it.

If it does not move on hover, it does not get a signal glow.

## 9. Motion

One easing curve, five durations, and one rule about where motion is allowed to be decided.

**Easing: `cubic-bezier(0.16, 1, 0.3, 1)`** - a long decelerating curve. Everything settles; nothing
snaps. In `motion` it is written `ease: [0.16, 1, 0.3, 1]`.

| Duration    | Where                                                       |
| ----------- | ----------------------------------------------------------- |
| `0.35s`     | A reading changes (the chord toggle, a filtered list).      |
| `0.45-0.5s` | Chips and secondary elements arriving behind a primary one. |
| `0.6-0.7s`  | An entrance: a hero line, a section reveal.                 |
| `0.9s`      | The one hero-scale object on the page.                      |
| `0.2-0.3s`  | Hover and colour transitions, in CSS only.                  |

Distance: `y: 24` for a section reveal, `y: 20` for a hero line, `y: 32` with `scale: 0.985` for the
analyser panel. Never more, and never `x` on a page that reads vertically.

Stagger is `0.05-0.07s` per item, so a sequence is legible as a sequence rather than as noise.
Section reveals use `viewport={{ once: true }}`: a section that has been read must not animate again
when somebody scrolls back up to check a number, which on this product people do.

### Reduced motion is CSS, not JavaScript

Anything that arrives with an animation carries **`data-reveal`**, and `globals.css` neutralises it:

```css
@media (prefers-reduced-motion: reduce) {
  [data-reveal] {
    opacity: 1 !important;
    transform: none !important;
    animation: none !important;
  }
}
```

This is deliberately _not_ a `useReducedMotion()` branch. `prefers-reduced-motion` cannot be read
during a server render, so a JavaScript branch means the server and the client disagree about the
first paint - which is a hydration mismatch on the most prominent element of the page, and it was
one. The same hook serves `<noscript>`, where an unanimated page beats a page stuck at
`opacity: 0` forever.

Two consequences for anyone adding a component:

- Any element that `motion` animates from `opacity: 0` **must** carry `data-reveal`.
- Ambient loops (the aurora's `animate-drift`, the header's `animate-live-dot`) are CSS animations,
  so they are covered by the same rule only if they carry `data-reveal` or a `motion-reduce:`
  variant. The waveform bars use `animate-rise motion-reduce:animate-none`.

### Where motion lives

Motion is decided **per surface, in CSS**, and only three things animate on a hover:
`transform` (a 1px lift), `border-color`, and `background-color` - all at `duration-300`. Nothing
animates its size, and nothing animates on hover in the app chrome. A workspace that moves under
the cursor is a workspace nobody can aim in.

## 10. Card hierarchy

A screen is not a set of equal boxes. Every screen in this product is built from four roles, and
each role has one job:

| Role            | Component                       | Job                                                       | Count per screen |
| --------------- | ------------------------------- | --------------------------------------------------------- | ---------------- |
| **Region**      | `Panel` (L1)                    | A named area of work: Library, Recent analyses, Upload.   | 3-5              |
| **Measurement** | `Metric` (L2)                   | One number, its unit, and the sentence that qualifies it. | 3-6              |
| **Item**        | A row or card                   | One song, one chord, one job.                             | Any              |
| **Tag**         | `Badge` / `JobStatusBadge` (L3) | State in one word.                                        | Any              |

Rules that keep this legible:

- **One level-1 panel per region, never nested.** A library rail, a results column and a utility
  rail are three siblings. Insisting on a Card inside a Card is how a dashboard becomes a
  spreadsheet with shadows.
- **One accent per panel.** The panel's top hairline, or a counted metric in signal, or a CTA -
  not all three.
- **A metric is a value, a unit, and a hint.** Always three parts. The hint is what stops a number
  being a mystery: `117.45` `BPM` `tracked, not guessed`. A tile with a bare number is incomplete.
- **Hover lift is a promise.** `hover:-translate-y-1` plus a signal glow belongs to an element that
  is a link. A decorative card that lifts on hover is lying about being clickable.
- **The first item of a ranked set is marked.** The top chord in a progression gets
  `border-signal/25 bg-signal/[0.07]`; the rest do not. Rank is shown once, not repeated per row.

## 11. Component recipes

These are the shapes a new screen should copy. Each one exists in the codebase already.

### Empty states

```
+---------------------------------------------------------------+
|                                                               |
|   Nothing here yet. Upload a track and it appears here        |  <- dashed border
|   with its analysis.                                          |     text-sm text-muted-foreground
|                                                               |
+---------------------------------------------------------------+
       dashed border-border, rounded-3xl (panel) or rounded-xl (tile), p-6
```

- A dashed border, a `p-6`, and **one sentence that says what will happen**, not "No data".
- Never a dead end. If the empty state has an action, the action is inside it.
- Never a colour, never an illustration, never an icon standing in for a sentence.
- Three real examples: the library before the first upload; a recording with no chords
  ("usually a percussion or spoken-word track, and it is not an error - the tempo, key and MIDI
  were still measured"); an analysis that is queued but not finished.
- An empty state that is a _state_ (queued, not analysed yet) uses the dashed border and muted
  text, the same as one that is a failure - but **never** `role="alert"`. A state is not an error
  and must not interrupt a screen reader.

### Forms

- Label above the field, `gap-2`. Placeholder is never a label.
- `Input` is `h-9` in a workspace and `h-11 rounded-xl` at auth scale. Never both in one view.
- Validation is wired, not just coloured: `aria-invalid={Boolean(error)}` plus
  `aria-describedby={error ? errorId : undefined}`, with the message in a `<p id={errorId}>`.
- A field-level error is `text-sm text-destructive` **under the field**. A form-level error is
  `FormMessage` (`role="alert"` for a failure, `role="status"` for a notice).
- One Zod schema per rule, shared between the browser and the Server Action, so a typo is caught
  the same way twice (`z.email` is defined once and imported by both).
- A submit control is disabled while pending and says what it is doing ("Working...", "Opening...").
  A button that goes silent for two seconds gets clicked twice.

### Tables

**There are no tables in this product, and that is a decision.** A list of songs is a set of rows
with a title, a description and a status - it is a list, and it renders as one. A chord timeline is
an ordered list of labelled stretches. Both are `<ul>`/`<ol>` with hairline dividers:

```
<li className="flex items-center gap-3 border-b border-white/[0.07] p-3 last:border-0">
```

When a real table is unavoidable, the rules are: no zebra striping, hairline dividers only,
`tabular-nums` on every numeric column and right-aligned, and the header row styled as an
eyebrow (`font-mono text-[0.6rem] tracking-[0.16em] uppercase text-muted-foreground`) rather than
as bold text. A generic admin table is the single clearest signal that a product is internal
tooling, which is why the default is not to have one.

### Charts

**Charts are CSS. There is no charting dependency and there will not be one for this.**

Three shapes cover everything the product measures:

| Shape        | Implementation                                   | Live example                             |
| ------------ | ------------------------------------------------ | ---------------------------------------- |
| Waveform     | A `<span>` per bar, `height: n%`, gradient fill  | `Waveform`, 64 bars                      |
| Distribution | A `<span>` per row, `width: n%`                  | The library's key spread, the chord lane |
| Share        | `Progress` (Radix) with a `tabular-nums` caption | Chord coverage: "92% of the recording"   |

Rules: bars are `rounded-full`, the fill is a signal-to-pulse gradient, the track is `bg-black/25`
or `bg-primary/20`, and every chart carries its scale in words ("across the 20 tracks shown"),
because a percentage with no denominator is decoration. Bars animate with
`animate-rise motion-reduce:animate-none`, staggered by `animation-delay` in CSS rather than by
animating N motion components - this keeps the first paint free of JavaScript work.

### Upload zones

```
+---------------------------------------------------------------+
|                                                               |
|              Drag a track here, or                            |
|              [ Choose a file ]          <- one control only   |
|                                                               |
|              MP3 or WAV, up to 200 MiB                         |
+---------------------------------------------------------------+
   border-dashed border-border, p-8, centred
   while dragging: border-ring bg-accent
```

- Dashed at rest; `border-ring bg-accent` while a file is over it. The colour change is the only
  feedback that the drop registered, so it must be immediate.
- Exactly **one** control. A second button ("browse", "paste a URL") turns a clear action into a
  decision.
- The file input is hidden and driven by that one button, and `event.target.value` is reset after a
  choice so the same file can be picked twice in a row.
- After a file is chosen the zone is replaced by: file name, size, and **Analyse**. State is one
  small machine (`idle | uploading | finishing`), never a handful of booleans that can drift.
- The five states, in order, and each one looks different on screen:
  `idle` (dashed) -> `chosen` (a row with the file) -> `uploading` (progress bar + percent) ->
  `finishing` (progress + "Confirming the file and queueing the analysis...") ->
  `queued` (a card naming the song, the job and the pipeline version).
- Refusals are checked in the browser first (`checkAudioFile`) so a 200 MiB file is never uploaded
  to be rejected - and the API checks all of it again, because the browser's rules are a courtesy
  and the API's are the boundary.

## 12. Not implemented, on purpose

Two things this document deliberately does not specify, so that nobody adds them by accident:

- **No light mode.** The palette has one set of values. A light theme would mean a second ramp,
  a second set of shadows and a contrast audit of every screen - and the product's reference
  surfaces (Linear, Vercel, Arc, ElevenLabs) are all dark. If a light mode is ever wanted it is a
  project, not a toggle.
- **No component documentation site.** The recipes here are the documentation, and the components
  live in `features/design-system/`. A Storybook would be a second place for the truth to live.

## 13. Checklist for a new screen

1. Wrap it in `AppShell` (workspace) or `MarketingShell` (a public page). Never re-implement the
   canvas or the header.
2. Give it regions - 3 to 5 `Panel`s. Name each one with an `Eyebrow` and, where the screen is read
   by a screen reader, label it with `aria-labelledby`.
3. Numbers are `font-mono tabular-nums`; every metric tile has a hint.
4. Every list ends in an `EmptyState` with a sentence.
5. Anything animated from `opacity: 0` carries `data-reveal`.
6. Run `pnpm format:check`, `pnpm --filter @myband/web lint` and `pnpm typecheck`.
7. Check it at 375px, 768px and 1536px. The workspace is desktop-first: if the third column has
   nowhere to go, the answer is that it becomes a section, not that it shrinks.
