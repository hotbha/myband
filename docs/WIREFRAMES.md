# Wireframes

Desktop-first, because the workspace's whole argument is that a wide display should be worth
having. Every screen below is drawn at desktop, tablet and mobile, and the value of the tablet and
mobile drawings is what they _drop_ - not how they shrink.

Values referenced here (widths, radii, colours, motion) are defined in
[DESIGN_SYSTEM.md](DESIGN_SYSTEM.md). This file is layout only.

## 0. The route map, before any drawing

The product has three routes, and every screen below is one of them or a region of one:

| Route         | Screen                                                   | Auth                                                |
| ------------- | -------------------------------------------------------- | --------------------------------------------------- |
| `/login`      | Sign in                                                  | Public (redirects to `next` when already signed in) |
| `/dashboard`  | The workspace: library, recent analyses, upload, metrics | Protected                                           |
| `/songs/[id]` | One song: measurements, chord timeline, exports          | Protected                                           |

That means **Library** (screen 3) and **Upload flow** (screen 5) are regions rather than routes.
This is deliberate and worth stating plainly: a navigation item that does not change what you can
do is a fake screen, and a product with three real destinations does not need seven menu entries.
Screens 3 and 5 are drawn where they live - the left and right columns of the workspace, and as
sections when there is no room for columns.

## 1. The breakpoints

| Name    | Range          | Columns | What happens                                                                                                                                         |
| ------- | -------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mobile  | `< 768px`      | 1       | Everything is a full-width section, in priority order: upload, recent analyses, library. The header keeps only the brand, a library link and logout. |
| Tablet  | `768 - 1023px` | 2       | Library rail + main column. Upload and metrics become full-width panels above the two columns.                                                       |
| Desktop | `>= 1024px`    | 3       | Library rail (17.5rem) + main column (`1fr`, min 32rem) + utility rail (20rem).                                                                      |

Container: `mx-auto w-full max-w-[96rem] px-5 sm:px-8`. Sticky header: `h-16`.

**The order of collapse is the design decision.** When the third column has nowhere to go, the
utility rail moves _above_ the main column rather than below it - because upload is the action a
returning user most often wants, and burying it under a list is how a dashboard becomes a page you
have to scroll to find things on. The library rail is last at mobile for the opposite reason: it is
the slowest thing on the screen to read and the least likely to be why somebody opened it.

## 2. The workspace frame

Every protected screen is this frame with different columns in it. It is drawn once here.

```
+==============================================================================+
|  [logo] MyBand.video     Library / Tera Suroor      beta.tester  [ Log out ] |
+==============================================================================+
|                                                                              |
|                        ( ambient canvas, behind everything )                  |
|                                                                              |
|   +------------------+  +------------------------------------+  +--------+   |
|   |  screen columns  |  |                                    |  |        |   |
|   |  per screen      |  |                                    |  |        |   |
|   +------------------+  +------------------------------------+  +--------+   |
|                                                                              |
+==============================================================================+
```

- The canvas (aurora, masked grid, grain, vignette) is `fixed inset-0 -z-10` and is mounted by the
  shell, never by a screen.
- The header is sticky and translucent, with a hairline that appears only once the page has
  scrolled.
- There is no sidebar of navigation, because there is nothing to navigate to. The library rail _is_
  the navigation: it is the list of things you can open.
- `<main>` carries `id="main"`, and the first focusable element in the DOM is a skip link.

## 3. Screen 1 - Sign in (`/login`)

### Desktop (>= 1024px)

```
+==============================================================================+
|                                                                              |
|  +-------------------------------------+  +-------------------------------+  |
|  |  [logo] MyBand.video                |  |                               |  |
|  |                                     |  |   Sign in to MyBand.video     |  |
|  |  Understand any song                |  |                               |  |
|  |  in minutes.                        |  |   Upload a track and get its  |  |
|  |                                     |  |   tempo, key, chords and a    |  |
|  |  Upload a track and get its tempo,  |  |   MIDI sketch back.           |  |
|  |  key, chords and a MIDI sketch.     |  |                               |  |
|  |                                     |  |   [ Continue with Google    ] |  |
|  |  - - - - - - - - - - - - - - - -    |  |                               |  |
|  |                                     |  |   ---------- or ----------    |  |
|  |  *  BPM Detection                   |  |                               |  |
|  |     117.45 BPM · 631 beats          |  |   Email                       |  |
|  |                                     |  |   [ you@example.com         ] |  |
|  |  *  Key Analysis                    |  |                               |  |
|  |     C# minor · strength 0.82        |  |   Password                    |  |
|  |                                     |  |   [                         ] |  |
|  |  *  Chord Timeline                  |  |                               |  |
|  |     170 segments · 74% mean         |  |   [Sign in] [Create account]  |  |
|  |                                     |  |                               |  |
|  |  *  MIDI Export                     |  |                               |  |
|  |     29 notes · 269 B                |  |                               |  |
|  +-------------------------------------+  +-------------------------------+  |
|                                                                              |
+==============================================================================+
        ^  48% - brand panel (L1 over aurora)      ^  52% - the form
```

Brand panel left, form right, both vertically centred (`min-h-dvh`, `lg:grid-cols-2`) inside a
`max-w-5xl` container. The form column is capped at `max-w-md` inside its half; the brand panel uses
its whole half. This is the only screen in the product that is genuinely two-up on desktop.

The brand panel is a landing-page panel, deliberately: it is the same logo tile, the same display
headline, the same four-capability list and the same top hairline as the marketing surface, so that
the first thing somebody sees after leaving the landing page is the same product.

### Tablet (768 - 1023px)

```
+==========================================================+
|                                                          |
|   +--------------------------------------------------+   |
|   |  [logo] MyBand.video                             |   |
|   |  Understand any song in minutes.                 |   |
|   |  Upload a track and get its tempo, key, chords   |   |
|   |  and a MIDI sketch back.                         |   |
|   +--------------------------------------------------+   |
|                                                          |
|   +--------------------------------------------------+   |
|   |  Sign in to MyBand.video                         |   |
|   |  [ Continue with Google ]                        |   |
|   |  --------------- or ---------------              |   |
|   |  Email   [................................]      |   |
|   |  Password [...............................]      |   |
|   |  [ Sign in ]  [ Create account ]                 |   |
|   +--------------------------------------------------+   |
|                                                          |
+==========================================================+
```

The brand panel collapses into a header block above the form. It keeps the logo and the one
sentence and drops the four-item list, which is a landing-page argument rather than a sign-in one.

### Mobile (< 768px)

```
+===========================+
|                           |
|   +---------------------+ |
|   | [logo] MyBand.video | |
|   | Understand any song | |
|   | in minutes.         | |
|   |                     | |
|   | Upload a track and  | |
|   | get its tempo, key, | |
|   | chords and a MIDI   | |
|   | sketch back.        | |
|   +---------------------+ |
|                           |
|   +---------------------+ |
|   | [ Google sign-in ]  | |
|   | ---- or ----        | |
|   | Email               | |
|   | [                 ] | |
|   | Password            | |
|   | [                 ] | |
|   | [     Sign in     ] | |
|   | [ Create account  ] | |
|   +---------------------+ |
+===========================+
```

One column: a `max-w-5xl` container with `px-5 py-12`, both panels filling it, and the brand panel
kept intact minus the four-item list - on a phone the form is the content. The two submit buttons
stack full-width, which is the shape `EmailAuthForm` already uses (`flex-col gap-2 sm:flex-row`) -
no change to the form's behaviour.

## 4. Screen 2 - The workspace (`/dashboard`)

Three regions, and each one answers a different question:

| Region                   | Question it answers                   | Data source                                                       |
| ------------------------ | ------------------------------------- | ----------------------------------------------------------------- |
| Library (left)           | "What do I have?"                     | `GET /songs?limit=20`                                             |
| Recent analyses (centre) | "What did I find out?"                | The same rows - `bpm`, `musical_key`, `duration_ms`, `created_at` |
| Upload + state (right)   | "What can I do, and what is running?" | The same rows, plus the uploader's own state                      |

All three read **one** array of rows, fetched once, in the request that renders the page. Nothing on
this screen fetches in the browser, so there is no spinner and nothing that can disagree with the
server.

The drawings below are schematic: region boundaries and content order are exact, character
alignment inside a region is not.

### Desktop (>= 1024px)

```
+==============================================================================+
| [logo] MyBand.video      Library                      beta.tester  [ Log out ]|
+==============================================================================+
|  LIBRARY  17.5rem     |  RECENT ANALYSES   1fr        |  UPLOAD  20rem       |
|                       |                              |                      |
|  Library       12 trk |  Tera Suroor                 |  +----------------+  |
|  - - - - - - - - - -  |  117.45 BPM   C# minor       |  |  Drag a track  |  |
|  [*] Tera Suroor      |  5:44 - analysed 12 Oct      |  |  here, or      |  |
|      117 BPM C# minor |                    [ Open ]  |  |  [ Choose ]    |  |
|      Analysed         |                              |  +----------------+  |
|  - - - - - - - - - -  |  --------------------------  |  MP3 or WAV, 200 MiB |
|  [ ] Jyoti            |  Ganesha                    |                      |
|      89 BPM G major   |  107.67 BPM   C# minor       |  AT A GLANCE         |
|      Analysed         |  1:02 - analysed 12 Oct      |  +------+------+     |
|  - - - - - - - - - -  |                    [ Open ]  |  |  12  |   9  |     |
|  [ ] Ganesha          |                              |  |tracks|analys|     |
|      107 BPM C# minor |  --------------------------  |  +------+------+     |
|      Analysing   o    |  Jyoti                       |  |   2  |  21m |     |
|  - - - - - - - - - -  |  89.1 BPM   G major          |  |runng |audio|     |
|                       |  ...                         |  +------+------+     |
|  (scrolls)            |                              |                      |
|                       |                              |  KEYS                |
|                       |                              |  C# minor ########   |
|                       |                              |  G major  ###        |
|                       |                              |  across 9 tracks     |
+==============================================================================+
```

Element by element:

- **Library rail.** A `Panel` with an `Eyebrow` ("Library"), a count, then one row per song. A row is
  a link to `/songs/[id]`: title, `describeSong`'s line, then the job status as a tag. The row for
  the song currently open carries `border-signal/25 bg-signal/[0.07]` - the same "this is the
  selected one" mark the chord strip uses for its top chord, so the two screens agree about what
  selection looks like.
- **Recent analyses.** One card per song that has a measurement, newest first: the title as
  `font-display`, then BPM, key and length as labelled mono values, then the date and an `Open` link.
  A song with no analysis yet is not in this column - it is in "Waiting" in the utility rail, which
  is where unfinished work belongs.
- **Utility rail.** Upload first (the action), then four metric tiles, then the key spread, then
  whatever is in flight. The order is "do, know, watch".

### Tablet (768 - 1023px)

```
+========================================================+
| [logo] MyBand.video   Library        beta.tester [out] |
+========================================================+
|  UPLOAD (full width)                                   |
|  +--------------------------------------------------+  |
|  |  Drag a track here, or  [ Choose a file ]         |  |
|  +--------------------------------------------------+  |
|  AT A GLANCE   12 tracks - 9 analysed - 2 running      |
|  [ 12 tracks ] [ 9 analysed ] [ 2 running ] [ 21m ]    |
+========================================================+
|  LIBRARY 17.5rem      |  RECENT ANALYSES               |
|  [*] Tera Suroor      |  Tera Suroor                   |
|      117 BPM C# minor |  117.45 BPM  C# minor          |
|      Analysed         |  5:44 - 12 Oct       [ Open ]  |
|  [ ] Jyoti            |  Ganesha                       |
|      89 BPM G major   |  107.67 BPM  C# minor          |
|  [ ] Ganesha          |  1:02 - 12 Oct       [ Open ]  |
|      Analysing        |                                |
+========================================================+
```

Upload and the metrics become full-width panels **above** the two columns. The key spread moves to
the bottom of the screen at this width - it is the one panel that is genuinely "nice to know".

### Mobile (< 768px)

```
+===========================+
| [logo] MyBand  [Lib] [out]|
+===========================+
|  Upload                   |
|  +---------------------+  |
|  | Drag a track here,  |  |
|  | or [ Choose file ]  |  |
|  +---------------------+  |
|  MP3 or WAV, up to 200 MiB|
|                           |
|  Recent analyses          |
|  -------------------------|
|  Tera Suroor              |
|  117.45 BPM   C# minor    |
|  5:44 - analysed 12 Oct   |
|              [ Open ]     |
|  -------------------------|
|  Ganesha                  |
|  107.67 BPM   C# minor    |
|              [ Open ]     |
|                           |
|  Library                  |
|  -------------------------|
|  Tera Suroor              |
|  117 BPM - C# minor       |
|                    Analysed
|  -------------------------|
|  Jyoti                    |
|  89 BPM - G major         |
|                    Analysed
|                           |
|  At a glance              |
|  12 tracks - 9 analysed   |
|  2 running - 21m of audio |
+===========================+
```

One column in the priority order from section 1: upload, recent analyses, library, metrics. The
header trades the full wordmark for "MyBand", a `Lib` link and logout - at 375px there is no room
for both a wordmark and a destination.

## 5. Screen 3 - Library

The library is one component in three places, and it is the same component each time: the dashboard's
left rail, the song page's breadcrumb context, and a full-width section at mobile. What changes is
how much of a row it can afford to show.

### Desktop (>= 1024px) - the rail

```
+==========================+
|  LIBRARY        12 trk   |   <- Eyebrow + count
|  - - - - - - - - - - - - |   <- hairline dividers, no zebra
|  [*] Tera Suroor         |   <- selected: border-signal/25 bg-signal/[0.07]
|      117 BPM C# minor    |   <- describeSong(): artist, BPM, key, length
|      Analysed            |   <- JobStatusBadge
|  - - - - - - - - - - - - |
|  [ ] Jyoti               |
|      89 BPM G major      |
|      Analysed            |
|  - - - - - - - - - - - - |
|  [ ] Ganesha             |
|      107 BPM C# minor    |
|      Analysing  o        |   <- in-flight tag, with the live dot
|  - - - - - - - - - - - - |
|  [ ] Untitled            |
|      2.1 MiB MP3         |   <- nothing measured yet
|      Not analysed        |
|  - - - - - - - - - - - - |
|  (20 rows, then "20 of    |
|   20 - the newest first") |
+==========================+
```

Row anatomy, in order: title (link, truncates), `describeSong`'s single line (truncates), status. The
whole row is the click target; the status is not a control.

### Tablet (768 - 1023px)

Same rail, one column narrower (the main column beside it takes the rest), and `describeSong`'s line
gets `truncate` rather than wrapping, because at 13rem a wrapped description makes every row a
different height and the list stops being scannable.

### Mobile (< 768px) - a section

```
+---------------------------+
|  Library            12 trk|
|  -------------------------|
|  Tera Suroor              |
|  117 BPM - C# minor       |
|                   Analysed|
|  -------------------------|
|  Jyoti                    |
|  89 BPM - G major         |
|                   Analysed|
+---------------------------+
```

Full rows, two lines each, no truncation, because there is nothing beside them to compete with. The
rail's fixed 17.5rem is dropped entirely - it exists to make the list a column, and there is no
column.

### Its states

| State           | What is drawn                                                                                                                                             |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Empty           | The dashed empty state: "Nothing here yet. Upload a track and it appears here with its analysis."                                                         |
| Populated       | Rows, newest first, `latest_job_id` deciding whether a song has ever been measured.                                                                       |
| In flight       | The affected row's tag becomes `Analysing` with the pulsing dot, and the rail's header gains "this list updates itself" (`LibraryRefresh`).               |
| API unreachable | `role="alert"` line inside the rail only. The screen keeps working: the uploader is still mounted, because retrying is why somebody would be on the page. |
| More than 20    | The API cap (`limit=20`) is printed under the list. A list that silently stops at 20 reads as "you only have 20 songs".                                   |

## 6. Screen 4 - Song analysis (`/songs/[id]`)

Three bands, top to bottom, and every one of them spans the full workspace width. This is the screen
the container was widened for.

| Band       | Contents                                                                                                       | Why it is this wide                                                                                                                |
| ---------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **Top**    | Song identity, then six measurements across the width                                                          | Six tiles in a row, not two rows of three - a row of measurements is read left to right, and a wrapped grid makes the eye zig-zag. |
| **Middle** | The chord timeline: a proportional lane, the toggle, the ranked progression, then the full list in two columns | The lane is a _time_ axis. Time is the one thing that gets better with width.                                                      |
| **Bottom** | Exports, and how the analysis was made                                                                         | Two reference panels, read once, at the end.                                                                                       |

### Desktop (>= 1024px)

```
+==============================================================================+
| [logo] MyBand.video     Library / Tera Suroor         beta.tester  [ Log out ]|
+==============================================================================+
|  Tera Suroor                                            [ Download MIDI ]     |
|  5:44 - 2.9 MiB - MP3 - pipeline 0.2.0                    [ Analysed ]        |
|  - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - |
|  +--------+ +--------+ +--------+ +--------+ +--------+ +--------+          |
|  | TEMPO  | | KEY    | | MEAN   | | CHORD  | | COVER- | | LENGTH |          |
|  | 117.45 | | C# min | | CONF.  | | SEG-   | | AGE    | | 5:44   |          |
|  | BPM    | | 0.824  | | 74 %   | | 170    | | 92 %   | | mm:ss  |          |
|  |tracked | |Krumhansl| |per chord| |bar by | |of the  | |decoded |          |
|  +--------+ +--------+ +--------+ +--------+ +--------+ +--------+          |
+==============================================================================+
|  CHORD TIMELINE                                       [ Simple | As detected ]|
|                                                                              |
|  +------------------------------------------------------------------------+  |
|  |##C#m7 ####C#maj7 #####C#sus2 ####G#maj7 ######Amaj7 ######C#            |  |
|  +------------------------------------------------------------------------+  |
|  0:00            1:26            2:52            4:19            5:44        |
|                                                                              |
|  Made of [C#m] [C#] [G#] [A]        92% of the recording #####------         |
|  Mean confidence 74%, and 57% to 86% on every chord it named.                |
|  - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - |
|  | 0:00  C#m     4.2s | | 0:10  G#maj7  3.4s |   <- the full list, two      |
|  | 0:04  C#      3.8s | | 0:13  Amaj7   2.8s |      columns; one <ol>, the   |
|  | 0:08  C#sus2  2.1s | | ...                |      lane above is its        |
|  | ...                | |                    |      decorative twin          |
+==============================================================================+
|  EXPORTS              1fr        |  HOW THIS WAS MEASURED   1fr             |
|  +----------------------------+  |  +-----------------------------------+   |
|  | MIDI sketch                |  |  | Detector    librosa-chroma-       |   |
|  | The pitch line read from   |  |  |             viterbi               |   |
|  | the recording, as a .mid   |  |  | Vocabulary  maj_min_7             |   |
|  | file for your DAW.         |  |  | Hop         46 ms                 |   |
|  | [ Download MIDI ]          |  |  | Key         C# minor              |   |
|  +----------------------------+  |  | Pipeline    0.2.0                 |   |
|                                  |  | Compute     4.7 s                 |   |
|                                  |  | Job         018f...c21            |   |
+==============================================================================+
```

Band by band:

- **Top.** The title, one `describeSong` line, the job's status as a tag, and the primary export
  action. The six tiles are the analysis headline: tempo, key (with its Krumhansl correlation as the
  hint), mean confidence, chord segments, coverage, and length. Every tile is the same `Metric`
  component, so the row is one rhythm rather than six variants.
- **Middle.** The lane is the new element and the reason this screen reads as an instrument: one
  segment per chord, `width` proportional to `end_ms - start_ms`, fill running signal to pulse so a
  long stretch is visibly long, rests drawn as gaps rather than as blocks. It carries a time axis in
  mono (`0:00` to the song's length) and is `aria-hidden` - the ordered list beneath it is the
  accessible reading of exactly the same data, which is what earns the lane the right to be
  decorative.
- **Bottom.** Exports and method, side by side. Both are "read once" panels, which is what puts them
  at the bottom rather than the top.

### Tablet (768 - 1023px)

```
+==========================================================+
|  Tera Suroor                          [ Download MIDI ]   |
|  5:44 - 2.9 MiB - MP3                       [ Analysed ]  |
|  +--------+ +--------+ +--------+                         |
|  | TEMPO  | | KEY    | | MEAN   |    <- tiles wrap 3-up    |
|  | 117.45 | | C# min | | 74 %   |       (grid-cols-3)      |
|  +--------+ +--------+ +--------+                         |
|  +--------+ +--------+ +--------+                         |
|  | CHORDS | | COVER  | | LENGTH |                         |
|  +--------+ +--------+ +--------+                         |
+==========================================================+
|  CHORD TIMELINE                   [ Simple | As detected ]|
|  +-----------------------------------------------------+  |
|  | proportional lane, full width                        |  |
|  +-----------------------------------------------------+  |
|  |  0:00  C#m      4.2s   <- one column: two columns at  |  |
|  |  0:04  C#       3.8s      this width puts a chord at  |  |
|  |  0:08  C#sus2   2.1s      the edge of readability     |  |
+==========================================================+
|  EXPORTS   (full width)                                   |
|  MIDI sketch - [ Download MIDI ]                          |
+==========================================================+
|  HOW THIS WAS MEASURED (full width)                       |
+==========================================================+
```

The tile grid becomes two rows of three, and the chord list drops to a single column. A timeline you
have to squint at is worse than one long list.

### Mobile (< 768px)

```
+===========================+
| [logo] MyBand  [Lib] [out]|
+===========================+
|  <- Library               |
|  Tera Suroor              |
|  5:44 - 2.9 MiB - MP3     |
|                 [Analysed]|
|  +---------+ +---------+  |
|  | TEMPO   | | KEY     |  |
|  | 117.45  | | C# minor|  |
|  | BPM     | | 0.824   |  |
|  +---------+ +---------+  |
|  +---------+ +---------+  |
|  | MEAN    | | CHORDS  |  |
|  | 74 %    | | 170     |  |
|  +---------+ +---------+  |
|  +---------+ +---------+  |
|  | COVERAGE| | LENGTH  |  |
|  | 92 %    | | 5:44    |  |
|  +---------+ +---------+  |
|                           |
|  Chord timeline           |
|  [ Simple | Detected ]    |
|  +---------------------+  |
|  | lane scrolls -------|->|
|  +---------------------+  |
|  0:00              5:44   |
|  0:00  C#m        4.2s    |
|  0:04  C#         3.8s    |
|  0:08  C#sus2     2.1s    |
|                           |
|  Exports                  |
|  [ Download MIDI ]        |
|                           |
|  How this was measured    |
|  Detector  chroma-viterbi |
|  Pipeline  0.2.0          |
+===========================+
```

A two-column tile grid, and the lane keeps its horizontal shape inside `overflow-x-auto` rather than
reflowing into a vertical list: it is a time axis, and a wrapped time axis is not an axis.

### Its states

| State                  | What is drawn                                                                                                                                                                                                                |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Fully analysed         | Everything above.                                                                                                                                                                                                            |
| Queued, not analysed   | The top band draws, the tiles are replaced by a dashed empty state: "This song has not been analysed yet. It is queued - the measurements appear here when the worker finishes." No `role="alert"`: a state is not an error. |
| Analysed, no chords    | Tempo, key and MIDI are still drawn - they were measured. The timeline band becomes a dashed empty state naming the likely reason (percussion or spoken word) and saying explicitly that it is not an error.                 |
| Failed                 | The error line in the top band (`role="alert"`), the measurements absent rather than zeroed. Never a `0 BPM`: a missing measurement is not a measurement.                                                                    |
| Not this caller's song | `notFound()`. A 404 is the honest answer, and it does not confirm that the id exists.                                                                                                                                        |

## 7. Screen 5 - Upload flow

One component, five states, and the states are drawn at all three widths because upload is the one
place in the product where the _same_ screen changes shape as the user acts. The component is the
right rail of the dashboard at desktop and a full-width panel at tablet and mobile.

| #   | State     | Trigger                                | What the user can do                    |
| --- | --------- | -------------------------------------- | --------------------------------------- |
| 1   | Idle      | Page renders                           | Drop a file, or press "Choose a file"   |
| 2   | Chosen    | A file passed `checkAudioFile`         | Analyse it, or clear it                 |
| 3   | Uploading | Bytes are going to storage             | Nothing. Progress is the answer.        |
| 4   | Finishing | The PUT returned                       | Nothing. Two API calls are left.        |
| 5   | Queued    | The API answered with a song and a job | Read it; open the song; or drop another |

A state that is not one of these five does not exist, and that is enforced by the component's own
machine (`idle | uploading | finishing`) rather than by a handful of booleans that can drift.

### State 1 - Idle

```
DESKTOP (rail)                 TABLET / MOBILE (full width panel)
+----------------------+       +==========================================+
|  UPLOAD              |       |  UPLOAD                                  |
|  +----------------+  |       |  +------------------------------------+  |
|  |                |  |       |  |                                    |  |
|  |  Drag a track  |  |       |  |   Drag a track here, or            |  |
|  |  here, or      |  |       |  |        [ Choose a file ]           |  |
|  |  [ Choose ]    |  |       |  |                                    |  |
|  |                |  |       |  +------------------------------------+  |
|  +----------------+  |       |  MP3 or WAV, up to 200 MiB               |
|  MP3 or WAV, 200 MiB |       +==========================================+
+----------------------+
```

The zone is dashed `border-border` at rest and `border-ring bg-accent` while a file is over it. The
hint under it is the one place the file rules are stated in the interface: `MAX_UPLOAD_MIB` and the
extension list come from `@myband/shared`, so the sentence cannot drift from the rule.

### State 2 - Chosen

```
+------------------------------------------+
|  midnight_drive.mp3              3.4 MiB |
|  [ Analyse ]  [ Clear ]                  |
+------------------------------------------+
```

The zone is replaced, not annotated. The file name truncates, the size comes from `formatBytes`, and
there are exactly two controls: the action and the way out of it.

### State 3 - Uploading, and state 4 - Finishing

```
+------------------------------------------+   +------------------------------------------+
|  midnight_drive.mp3              3.4 MiB |   |  midnight_drive.mp3              3.4 MiB |
|  ####################------------  68 %  |   |  ################################ 100 %  |
|  Uploading - 68%                         |   |  Uploaded. Confirming the file and       |
+------------------------------------------+   |  queueing the analysis...                |
                                               +------------------------------------------+
```

Two different sentences on purpose: the upload's progress is the browser's (`XMLHttpRequest` progress
events), and the pause after it is two server round trips that report nothing. Saying "Uploading"
during that pause would be a lie about what is happening, so it says what is happening instead.

### State 5 - Queued

```
+--------------------------------------------------+
|  midnight_drive.mp3 is queued for analysis.      |
|  Job 018f3c21 - queued - pipeline 0.2.0          |
+--------------------------------------------------+
```

`role="status"`, not `role="alert"`: this is good news and it should not interrupt a screen reader.
The job id is truncated to eight characters and set in mono, the status is the API's own word, and
the pipeline version is included because that is the number that answers "why did this song come back
different from the last one".

### Refusal

```
+--------------------------------------------------+
|  Files must be 200 MiB or smaller -              |
|  "master.wav" is 412.7 MiB.                      |
+--------------------------------------------------+
```

`role="alert"`, the `border-destructive/40 bg-destructive/10 text-destructive` treatment, full
width. It replaces the zone rather than sitting beside it, because a refusal that leaves the drop
zone looking ready invites the same failure twice.

### Shared with the rest of the screen

- While a job is in flight the dashboard's list is refreshed by `LibraryRefresh` on a 5s timer that
  stops when nothing is in flight, skips a hidden tab, and gives up after 15 minutes with a "Check
  again" control. It re-runs the Server Component rather than owning any rows.
- After a successful queue the component calls `router.refresh()` rather than inserting a row
  optimistically: the row that appears is the API's, and it is the same row a second device would
  see.

## 8. The component map

Which file draws what, so that a change lands in one place.

| Region                   | Component                                                  | Kind   |
| ------------------------ | ---------------------------------------------------------- | ------ |
| Canvas (both surfaces)   | `features/design-system/components/ambient-background.tsx` | Server |
| Glass panel + hairline   | `features/design-system/components/panel.tsx`              | Server |
| Eyebrow label            | `features/design-system/components/eyebrow.tsx`            | Server |
| Metric tile              | `features/design-system/components/metric.tsx`             | Server |
| Empty state              | `features/design-system/components/empty-state.tsx`        | Server |
| Header, shell, container | `features/shell/components/app-shell.tsx`                  | Server |
| Library rail + rows      | `features/uploads/components/library-rail.tsx`             | Server |
| Recent-analysis cards    | `features/uploads/components/analysis-card.tsx`            | Server |
| Job status tag           | `features/uploads/components/job-status-badge.tsx`         | Server |
| MIDI download            | `features/uploads/components/download-midi-button.tsx`     | Client |
| Upload zone (5 states)   | `features/uploads/components/upload-dropzone.tsx`          | Client |
| Chord lane (decorative)  | `features/uploads/components/chord-lane.tsx`               | Server |
| Chord list + toggle      | `features/uploads/components/chord-timeline.tsx`           | Client |
| Polling while in flight  | `features/uploads/components/library-refresh.tsx`          | Client |
| Auth forms               | `features/auth/components/*`                               | Client |

Everything that draws data is a Server Component. The Client Components exist for exactly five
reasons: `motion` needs a browser, `useActionState` needs a reducer, `XMLHttpRequest` needs a
progress event, a two-way toggle needs state, and a poll needs a timer. No Client Component owns a
row of data.

## 9. What this pass did not change

Stated here because it is the boundary of the whole exercise:

- **No measurement changed.** The worker is untouched: `pipeline_version` is still `0.2.0`, and BPM,
  key, chords and MIDI are read exactly as they were written.
- **No endpoint was added, and none was changed.** The dashboard calls `GET /songs?limit=20` once;
  the song page calls `GET /songs/{id}` and `GET /songs/{id}/chords` in parallel; exports still ask
  the API for a signed URL and then navigate to it.
- **No route was added.**
- **No dependency was added.** The only front-end dependency the landing page brought in was
  `motion`, and nothing was added for this pass.
- **No behaviour was removed.** Every control that worked before this pass still works: the
  simple/detected toggle, the per-row disclosure of the detected label, the coverage bar, the MIDI
  download, the poll, the upload's five states, and every auth action.
