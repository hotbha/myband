# MIDI window report

The MIDI stage writes a monophonic sketch of a recording's opening. Until this change it always
wrote the first 30 seconds of whatever was uploaded; it now writes the recording **up to a
120-second cap**, clamped to the recording's own duration
(`MYBAND_WORKER_MIDI_WINDOW_SECONDS`, `ge=5, le=600`, decided per job by
`WorkerTuning.midi_window_for`). This is the measurement the cap rests on: the same three beta
recordings, the same production functions, one number changed.

**Verdict: 120 s, implemented.** It is **2.0x-4.5x the notes for 2.8-9.1 s of extra pitch
tracking and under 90 MiB traced**, and it leaves the 900 s job budget two orders of magnitude of
headroom. The tail is still not transcribed: a whole-song pass carries 6.6x-12.7x the notes of the
30 s slice, at up to 232 MiB traced and 31 s on the 5:45 song. That is a different change, and
section 9 says what would have to be true to make it.

## 1. What changed

|                          | before                                 | after                                                                                  |
| ------------------------ | -------------------------------------- | -------------------------------------------------------------------------------------- |
| Setting                  | `MYBAND_WORKER_MIDI_WINDOW_SECONDS=30` | `MYBAND_WORKER_MIDI_WINDOW_SECONDS=120`; the field is `worker_midi_max_window_seconds` |
| Meaning                  | a slice: always the first 30 s         | a cap: the whole recording, or the first 120 s of it                                   |
| A 40 s song              | 30 s transcribed                       | all 40 s                                                                               |
| A 5:45 song              | 30 s transcribed                       | 120 s transcribed                                                                      |
| Pipeline version         | `0.2.0`                                | `0.3.0`                                                                                |
| `summary.window_seconds` | always `30`                            | what was actually transcribed (`63` for a 62 s song)                                   |

No model, algorithm, schema or UI change: the same `transcribe_with_pyin`, the same 11 kHz / hop
1024 configuration, the same artifact kind, the same `<title>.mid` download. Only _which seconds_
the tracker is handed.

## 2. How this was measured

`spike/basic-pitch-onnx/out/full_pipeline.py` is the harness: it calls the worker's own
`analysis.analyze`, `chords.detect_chords` and `midi.transcribe_with_pyin` on the real recordings,
writes the MIDI, then imports each file into MuseScore and counts what MuseScore made of it. The
MuseScore machinery is imported from `rerun_pyin.py` rather than copied, so "visible notes" means
the same thing in both harnesses. Songs, audio paths and the `stored_artifact` column below come
from `out/inventory.json`, a snapshot of the local database's analysis rows.

**The harness is the production path, not an estimate of it.** The MIDI bytes a shipped `0.2.0`
worker wrote are byte-for-byte what this harness writes for the same 30 s window: the database holds
198 bytes (ganesha), 298 bytes (jyoti) and 269 bytes (tera-suroor) against 198 / 298 / 269 in the
sweep, and the one file that was downloaded and compared is SHA-256-equal. It follows that the
120 s column is what `0.3.0` writes.

`--windows 30,60,120,full`: three second-counts plus `full` for the whole recording (345 s for the
longest song). The `120` and `full` rows coincide on the 62 s song — that is the clamp working: a
recording shorter than the cap is transcribed whole rather than padded or truncated.

## 3. The sweep

Source: `spike/basic-pitch-onnx/out/full/window-sweep.json`, 2026-10-10, Windows box, CPU only,
one run per cell. "notes" is the pipeline's own note count; "MuseScore" is what the imported score
contains. "MIDI stage" is decode + pYIN + MIDI write for that window, not the job.

### Ganesha Kartikeya Race Short Audio — 62.2 s, C# minor, 107.7 BPM

| window | window used | notes | MuseScore notes | measures | pages | bytes | MIDI stage | traced peak |
| ------ | ----------- | ----- | --------------- | -------- | ----- | ----- | ---------- | ----------- |
| 30 s   | 30 s        | 19    | 24              | 12       | 2     | 198   | 3.95 s     | 39.6 MiB    |
| 60 s   | 60 s        | 37    | 47              | 27       | 2     | 322   | 6.35 s     | 48.1 MiB    |
| 120 s  | **62 s**    | 38    | 48              | 28       | 2     | 330   | 6.74 s     | 49.0 MiB    |
| full   | 62 s        | 38    | 48              | 28       | 2     | 330   | 6.74 s     | 49.0 MiB    |

### Jyoti — 246.8 s, G major, 89.1 BPM

| window | window used | notes | MuseScore notes | measures | pages | bytes | MIDI stage | traced peak |
| ------ | ----------- | ----- | --------------- | -------- | ----- | ----- | ---------- | ----------- |
| 30 s   | 30 s        | 35    | 38              | 12       | 2     | 298   | 5.41 s     | 39.6 MiB    |
| 60 s   | 60 s        | 64    | 69              | 29       | 2     | 491   | 6.49 s     | 48.1 MiB    |
| 120 s  | 120 s       | 126   | 137             | 59       | 2     | 911   | 8.89 s     | 88.0 MiB    |
| full   | 247 s       | 232   | 257             | 98       | 3     | 1634  | 17.64 s    | 180.9 MiB   |

### Himesh Reshammiya - Tera Suroor — 344.9 s, C# minor, 117.5 BPM

| window | window used | notes | MuseScore notes | measures | pages | bytes | MIDI stage | traced peak |
| ------ | ----------- | ----- | --------------- | -------- | ----- | ----- | ---------- | ----------- |
| 30 s   | 30 s        | 29    | 39              | 22       | 2     | 269   | 3.72 s     | 39.6 MiB    |
| 60 s   | 60 s        | 63    | 69              | 15       | 2     | 508   | 7.00 s     | 48.1 MiB    |
| 120 s  | 120 s       | 130   | 145             | 48       | 2     | 976   | 12.83 s    | 80.9 MiB    |
| full   | 345 s       | 369   | 423             | 166      | 4     | 2668  | 30.71 s    | 232.2 MiB   |

Two independent things are visible in those columns. The pipeline's own counts rise monotonically
with the window (29 / 63 / 130 / 369 on the longest song) — every extra second of audio adds notes.
MuseScore's measure count does **not**: Tera Suroor reads 22 measures at 30 s and 15 at 60 s, because
the tracker follows a different voice in each slice and MuseScore re-bars whatever it is given. Treat
measures as a rendering, not a metric; notes and bytes are the pipeline's.

For scale, `analysis.analyze` peaks at 642.5 MiB and 36.04 s on that 345 s song. Even the whole-song
MIDI pass does not make MIDI the expensive stage.

## 4. What the user gets

| song        | duration | `0.2.0` notes | `0.3.0` notes       | ratio | extra pitch tracking | traced peak |
| ----------- | -------- | ------------- | ------------------- | ----- | -------------------- | ----------- |
| Ganesha     | 62.2 s   | 19 (30 s)     | **38** (whole song) | 2.0x  | +2.8 s               | 49.0 MiB    |
| Jyoti       | 246.8 s  | 35 (30 s)     | **126** (120 s)     | 3.6x  | +3.5 s               | 88.0 MiB    |
| Tera Suroor | 344.9 s  | 29 (30 s)     | **130** (120 s)     | 4.5x  | +9.1 s               | 80.9 MiB    |

The score a user opens goes from two pages of intro to two pages of a third of the song (Tera
Suroor) or half of it (Jyoti), and never becomes a multi-page document to scroll — which is what the
cap buys, more than the note count does. The one song under two minutes is transcribed entirely, so
the "window" caveat in the docs no longer applies to short uploads at all.

## 5. Two generations in the database, and the "half the MIDI files are empty" scare

The first read of `inventory.json` looked like a live defect: two of the three stored MIDI artifacts
carried `notes: 0`. They are not what this code produces.

| song        | stored artifact          | stored `window_seconds` | what it is                                  |
| ----------- | ------------------------ | ----------------------- | ------------------------------------------- |
| ganesha     | **66 bytes**, `notes: 0` | 30                      | pre-fix generation                          |
| jyoti       | 298 bytes, `notes: 35`   | 30                      | matches the sweep's 30 s file byte-for-byte |
| tera-suroor | **66 bytes**, `notes: 0` | 30                      | pre-fix generation                          |

66 bytes is a MIDI file with no notes in it — a tempo map and nothing else, which is what
`pretty_midi` writes for an instrument that holds no notes, and what the Viterbi decode produced
before `transition_min_prob` let it leave the unvoiced state. `RELEASE_READY.md` records the same
song and the same artifact: the 30 s MIDI "went from an empty 66-byte tempo map to 29 notes over 269
bytes" (`1e32e71`). The 29/269 pair is in the sweep table above; the 66-byte files in the database
predate that fix and were never rewritten, because nothing re-ran those jobs.

So the sample mixes generations, and no single field labels them: `summary.window_seconds` separates a
post-`0.3.0` row (`120`) from everything before it, while a 66-byte file with `notes: 0` is the
pre-`1e32e71` generation. An audit of "empty artifacts" has to establish the generation first — read
as one sample, this one looked like half the MIDI rows were broken.

## 6. The near miss: a legacy setting that would have failed silently

Widening the window changed what `MYBAND_WORKER_MIDI_WINDOW_SECONDS` meant, so the field was renamed
to `worker_midi_max_window_seconds`. That rename came within one line of silently overriding a
deployment's deliberate choice: `Settings` ignores unknown variables, so a deploy still setting
`MYBAND_WORKER_MIDI_WINDOW_SECONDS=30` — someone capping the job on purpose — would have had that
variable dropped, and a 30 s worker would have begun writing 120 s of transcription with nothing in
the logs saying why.

The field reads both names through `AliasChoices` instead: the old name still sets the new field, so
that deployment keeps the 30 s it asked for, and the alias can be deleted once nothing sets it.
`tests/test_config.py` pins the three cases — default `120`; the legacy name alone yields `30`; when
both are set the new name wins (`90` over `30`).

## 7. Caveats

- **`traced peak` is tracemalloc's Python-allocation peak, not RSS.** NumPy and librosa buffers live
  outside it, so it is a floor on what the stage holds, useful for comparing windows and not as a
  container-memory budget.
- **The bytes are reproducible; the clock is not.** Re-running this release's window from scratch on
  the same box reproduced the artifact exactly — 126 notes, 911 bytes, MuseScore 137 notes in 59
  measures, 88.0 MiB traced, on the dot — while the stage took 14.86 s instead of the sweep's 8.89 s.
  The sweep's rows were warm (earlier windows in the same process had already paid numba's one-off
  compile); a cold first call pays it again. Budget from the cold number, and note that this is how
  the older "~1 s per second of audio" figure in the docs was arrived at: one cold 4 s clip, which is
  roughly nine times the warm cost of the configuration that ships.
- **"MIDI stage" is one stage, not one job.** A job also runs `analysis.analyze` (36.04 s and 642.5
  MiB on the 5:45 song) and the chord detector, plus R2 I/O and dispatch. These numbers say nothing
  about those, beyond establishing that MIDI is not what presses on the 900 s watchdog.
- **One run per cell, one machine, Windows, CPU only.** RunPod's CPU profile is not measured here. A
  core count or clock 2-3x slower would put the 120 s stage near 25 s and a whole-song stage near
  90 s — still inside 900 s, but no longer negligible. Re-measure before raising the cap further.
- **MuseScore's columns are one importer's opinion.** Its measure count is not monotone in the window
  (§3), it depends on MuseScore being installed for the run, and it is the only reason "pages" exists
  in this report. Notes and bytes are the pipeline's own numbers.
- **Cost scales with duration; value was not measured.** All three songs are Indian film/pop with
  clear tempo and a bass line the tracker can follow. Nothing here is about transcription accuracy —
  how many of the added notes a musician would recognize as the song is an untested question.
- **The harness and the audio are under `spike/`, which is git-ignored.** A clone cannot regenerate
  this table without them, `out/inventory.json` and a MuseScore install.

## 8. Reproducing it

The full table is a few minutes: each song pays `analyze` once, then one MIDI pass per window, and
every MIDI is imported into MuseScore.

```
# the whole table: three songs x four windows
apps/api/.venv/Scripts/python.exe spike/basic-pitch-onnx/out/full_pipeline.py \
    --windows 30,60,120,full --label window-sweep

# the window this release ships, one song
apps/api/.venv/Scripts/python.exe spike/basic-pitch-onnx/out/full_pipeline.py \
    --windows 120 --match jyoti --label window-sweep-expansion
```

It needs `out/inventory.json` (audio paths and the stored artifact summaries the sample came from),
the same environment the worker reads (`MYBAND_ENV` and the database), and MuseScore — found
automatically here at `X:\Program Files\bin\MuseScore4.exe`, or pointed at with `--musescore`. Each
run merges into `out/full/<label>.json` per song, so a `--match` pass adds a song rather than erasing
the others, and leaves the files themselves at `out/full/<song>-<window>s.mid` for inspection.

## 9. Recommendation

**Keep the 120 s cap, as implemented.** The evidence is one-sided: 2.0x-4.5x the notes for 2.8-9.1 s
of pitch tracking and under 90 MiB traced, two pages of score at every window, and a stage that stays
proportional to the window instead of to the upload — even the `le=600` ceiling can only ever ask the
tracker for ten minutes (`~1 min` of work, measured at 30.7 s for 5:45). Anything shorter than two
minutes is now transcribed whole, which retires the limitation for one of the three recordings and
for whichever short clips users upload next.

What would change this answer:

- **If most uploads are long and the tail matters, whole-song is affordable but unverified.**
  Transcribing the 5:45 song entirely is 369 notes against 130 for 2.8x the traced memory (232.2 MiB)
  and 30.7 s of tracking. That fits a 900 s budget, but it is 3x the traced peak of the 120 s window
  and should be measured on the RunPod CPU profile before it becomes a default, along with what
  `le=600` and `window_seconds` should mean then.
- **If a 120 s stage shows up in the slowest jobs, the cap is the first knob**, and the sweep prices
  lowering it: 60 s would give 37 / 64 / 63 notes on the three songs for roughly half the tracking.
- **A change in accuracy is a different investigation.** This change hands the same model, unchanged,
  more of the song; whether the added notes are musically right is not something these columns claim.

Implemented in `core/config.py` (`worker_midi_max_window_seconds`, `ge=5, le=600`, aliased),
`workers/tuning.py` (`WorkerTuning.midi_window_for`, the clamp), `workers/stages.py` (passes the
effective window) and `workers/midi.py`.

---

Data: `spike/basic-pitch-onnx/out/full/window-sweep.json` — three songs, four windows, one run each,
2026-10-10 — plus `window-sweep-expansion.json`, the independent 120 s re-run that reproduced the
shipped window byte-for-byte (§7).
