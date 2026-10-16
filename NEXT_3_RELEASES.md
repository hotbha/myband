# The next three releases: 0.5, 0.6, 0.7

Planning from the **0.4 freeze** (song sections). The order is set by user value per unit of risk, and
every entry below names the measurement it rests on - from [SECTIONS_VALIDATION.md](SECTIONS_VALIDATION.md),
[PRODUCT_READINESS_V0_4.md](PRODUCT_READINESS_V0_4.md), [MIDI_WINDOW_REPORT.md](MIDI_WINDOW_REPORT.md)
and the register in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

The one-paragraph version: **0.5 makes the product safe and measurable to put in front of a stranger,
0.6 fixes the artifact with the largest measured gap, and 0.7 improves the artifact that is honest but
partial.** The next move overall is user acquisition (the recommendation in the audit) - and 0.5 is
what makes that move possible rather than reckless.

## Release 0.5 - "Say only what was measured, and let a stranger in"

**User value:** nothing a user is handed is empty, wrong or a dead end, and the funnel is visible so
the beta produces knowledge rather than anecdotes.

| #   | Item                                                                                                                                                                                                                       | Why it earns its place (measurement)                                                                                                                     |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Run the sections detector over the three real recordings in the local bucket, write the forms down                                                                                                                         | The artifact's entire evidence base is synthetic (L1). Hours, read-only, no new code path                                                                |
| 2   | Bump `MYBAND_PIPELINE_VERSION` to `0.4.0` (`config.py`, `.env.example`, the `0.2.0` gate line in the register)                                                                                                             | F1: without it a 0.4 row is indistinguishable from a 0.3 one. No test pins the value                                                                     |
| 3   | Correct the landing page's MIDI FAQ ("first 30 seconds" -> the 120 s cap)                                                                                                                                                  | The page's own rule is that every number was measured by the pipeline, and the cap has been 120 s since `v0.3-midi-window`                               |
| 4   | Instrument the funnel: upload started -> upload completed -> queued -> analysed -> timeline viewed -> form viewed -> MIDI downloaded                                                                                       | F3: zero analytics dependencies and zero `track(` calls today, so the beta would be blind. This is what turns 0.5's users into 0.6's and 0.7's decisions |
| 5   | A retry path for a failed song, and a cancel/delete for a stuck one (risks R3, and the register's "deliberately absent" cancel)                                                                                            | Today a failure is a dead end that costs the user a second upload; the register already lists the missing routes                                         |
| 6   | A per-account upload quota plus an R2 lifecycle rule (R5, R4)                                                                                                                                                              | The 200 MiB cap is per file and nothing limits an account; an open beta is otherwise an unbounded cost                                                   |
| 7   | The pre-beta gates that are not code: `MYBAND_METRICS_TOKEN` and alerts on `oldest_in_flight_seconds` / `failed_recently` (R8, R2), one rehearsed restore (R10), production SMTP and Google auth exercised end to end (R9) | Every one is a checkbox in `PRODUCTION_READINESS.md` and none is ticked                                                                                  |
| 8   | Refresh the landing demo to a 0.4-era run (`PIPELINE_VERSION`, the MIDI window) and add the fifth feature card                                                                                                             | The page currently sells four capabilities and the pipeline produces five                                                                                |

**Exit criteria** (each measurable): the pre-beta checklist in the register is ticked; the three
recordings' forms are recorded next to `MIDI_WINDOW_REPORT.md`; a self-test upload produces no empty
artifact; the funnel shows all seven events for that upload; a failed job can be retried from the UI
without a second upload.

**Explicitly not in 0.5:** any change to the detectors, any naming, any new artifact, any RunPod
dispatcher (which the register keeps out until it is needed).

## Release 0.6 - "A MIDI a musician can build something on"

**User value:** the export stops being a curiosity. It is the artifact with the largest measured gap -
monophonic, 69% of its notes in C2-C3 because it follows the loudest fundamental, and the recording's
tail is not transcribed at all.

| #   | Item                                                                                                                          | Why it earns its place (measurement)                                                                                                                                                                                                                                                                                                                                                                                                        |
| --- | ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Take the Basic Pitch decision on the evidence that already exists                                                             | `spike/basic-pitch-onnx/results.md` measured it end to end: the ONNX export ships inside `basic-pitch==0.4.0`'s own wheel (one SHA-256, four byte-identical copies), `onnxruntime 1.31.0` installs beside `librosa 1.0.0` / `numpy 2.5.3` on 3.12 with nothing moved, and the empty-MIDI bug it was meant to fix turned out to be one parameter (already fixed). Its own cost table: 1 day to de-risk on Linux, 2-3 days for a labelled set |
| 2   | A small labelled set: 5-8 recordings with note-level annotations                                                              | It is the shared prerequisite for _both_ remaining accuracy questions - "are the MIDI notes right" and "is the section form right". Nothing else in this list can be judged without it                                                                                                                                                                                                                                                      |
| 3   | Wire the winner in behind the existing seam (`transcription.name`, `midi.transcribe_with_pyin`), keeping pYIN as the fallback | The seam exists and `test_worker_midi.py` already asserts one instrument, so this is a swap the tests can see                                                                                                                                                                                                                                                                                                                               |
| 4   | Re-run the window sweep as the acceptance test and publish the numbers                                                        | `MIDI_WINDOW_REPORT.md` is the template, and the untracked harness behind it (F2) should move into the repository as part of this                                                                                                                                                                                                                                                                                                           |
| 5   | Ship a note-level score per recording, not a claim                                                                            | "Enough to arrange from" has to become a number a user can read for their own song                                                                                                                                                                                                                                                                                                                                                          |

**Exit criteria**: against the labelled set, precision/recall that beats the pYIN baseline, no empty or
near-empty artifact on any of the three beta recordings, and a published report with the raw numbers.

**Explicitly not in 0.6:** multitrack separation, per-instrument parts, or anything on the landing
page's roadmap (AI guitarist, drummer, band performance) - those are excluded by the product's own
rules and would need a labelled set, a dispatcher and a budget first.

## Release 0.7 - "Name what the form found"

**User value:** a musician who is told `A B A B C` still has to find the chorus themselves. Naming -
and being able to jump to a named part - is the difference between a novelty and a practice tool.

| #   | Item                                                                                                | Why it earns its place (measurement)                                                                                                    |
| --- | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | A second signal for naming: lyric alignment, or arrangement energy (RMS + band energy + repetition) | Chroma cannot separate verse from chorus - the current design says so in three places. Naming needs evidence the detector does not have |
| 2   | Bar-snapped boundaries on the grid `analysis.detect_tempo` already computes                         | Today boundaries land on a 4 s pool, up to four seconds from the real transition - the reason a section is hard to loop over            |
| 3   | A per-section confidence that means something, and the UI allowed to show one                       | Today's number is agreement with a cluster mean, high by construction, which is why it is not rendered                                  |
| 4   | Jump-to-section / loop, so the map becomes usable on the song page                                  | The one feature a player asks for after the map exists                                                                                  |

**Gate:** this release is done **only if 0.5's funnel shows users reading the form and asking for
names** (an FAQ, a support message, or a section on the page being viewed compared with uploads).
Naming a wrong chorus is worse than an honest letter, so naming ships with a measured accuracy against
human-labelled sections - no label without ground truth.

**Exit criteria**: on the labelled set, naming accuracy per section against human annotations,
boundaries within one beat of a human annotation, and a confidence that distinguishes a confident
name from a guess.

## Why this order

- **0.5 first** because it converts everything already built into knowledge: the funnel (F3) is the
  only instrument that can rank 0.6 against 0.7, and the three copy/version items are the difference
  between a release that can be reproduced (`MYBAND_PIPELINE_VERSION`, the harness) and one that cannot.
- **0.6 second** because the MIDI is the artifact with the largest _measured_ gap: monophonic, 69% of
  its notes in C2-C3, the tail untranscribed, and a feasibility study already done and unmerged.
- **0.7 third** because sections are already honest and already correct about the claim they make. Their
  gap is coverage (a letter is not a name, a 4 s grid is not a bar), and closing it costs a new signal
  plus ground truth - more than the two measurement items above, for less urgency.

Any reordering has to come from 0.5's data, not from this document's intuition. If the funnel shows
users ignoring the chord timeline and living in the section map, 0.7 moves ahead of 0.6; if it shows
MIDI downloads stopping at the preview, the MIDI is what users want fixed.

## Where the next release's bet should go

The audit's recommendation is **D - beta user acquisition**, and 0.5 is the honest way to do it: invite
the ten unfilled seats with the funnel instrumented, a retry path for failures, and a quota that makes
an open beta survivable. The reasoning, and why not Basic Pitch, a song coach or verse/chorus naming
next, is in the audit response alongside this file.
