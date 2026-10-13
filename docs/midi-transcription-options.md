# MIDI transcription: three options, and what each one costs

**Status: proposal.** No code has been changed to write this. It prices three ways out of the
dead end the MIDI stage is in, so the decision can be made once instead of three times.

The decision this asks for is _not_ "which model is best". It is: **how much of the pipeline's
budget, dependency surface and GPU story is the MIDI artifact worth**, given that the other four
outputs (BPM, key, chords, duration) are unaffected by any of these options and are already
producing correct results.

## The failure being priced

An audit of three real recordings through the deployed pipeline found:

| Song            | Notes | Job status  | Artifact                             |
| --------------- | ----- | ----------- | ------------------------------------ |
| Jyoti (control) | 35    | `succeeded` | 167 runs of pitch, 35 kept           |
| Tera Suroor     | **0** | `succeeded` | a valid 66-byte SMF: tempo, no notes |
| (second song)   | **0** | `succeeded` | a valid 66-byte SMF: tempo, no notes |

The mechanism, read out of the installed `librosa` 1.0.0 `core/pitch.py` and confirmed by running
the two stages separately: raw `librosa.yin` finds a fundamental in **323 of 323** frames on every
one of the three songs. `librosa.pyin`'s HMM then marks **0 of 323** frames voiced on both broken
songs, and 323 of 323 on Jyoti. pYIN initialises `p_init` _uniformly_ over its 122 states and
transitions with `switch_prob=0.01`, so voicing is effectively **all-or-nothing, decided mostly by
the first frame's evidence** - the song-level output is a coin flip weighted by frame one, not a
per-frame judgement. Two consequences worth carrying into every option below:

- **The render is not the bug.** `render_midi([])` emits a standards-valid 66-byte two-track SMF,
  so `object_bytes > 0`, `notes: 0`, and the job records `succeeded`. A user gets a `.mid` that
  opens in a DAW and is empty, with nothing in the system saying so. That is a product bug
  independent of which transcriber wins, and it is separable from this proposal.
- **Bypassing the voicing step is not enough on its own.** Re-running with `fill_na=None` to keep
  unvoiced frames as values still produced a single note, because the tracker's own output on that
  material is not stable enough to survive the note assembler. Two levers, not one.

## What any replacement owes the pipeline

The seam is deliberately narrow, and this is the checklist every option below is scored against:

| Obligation                          | Where                                                                                                                                                                                          |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Transcription` dataclass shape     | `app/workers/midi.py`; mirrored by `tests/fakes.FakeTranscription`, with a test asserting the field _names_ match                                                                              |
| Callable signature                  | `transcribe(path, *, bpm, window_seconds)` - `runner.build_pipeline` injects it, `stages.Stages` calls it                                                                                      |
| `name` travels into the row         | `artifacts.build_results` writes `{"notes", "window_seconds", "transcriber"}` into `analysis_results.summary`                                                                                  |
| A window, and honesty about it      | `MYBAND_WORKER_MIDI_WINDOW_SECONDS` exists because pYIN costs ~1 s per second of audio; a cheaper transcriber can widen or drop the window, but `window_seconds` has to keep meaning something |
| One valid SMF, never a missing file | `audio/midi` must be allowed by the bucket policy; a note-less file is currently a _success_                                                                                                   |
| A version bump                      | `MYBAND_PIPELINE_VERSION` is documented as "bump when the worker's output shape or algorithms change"                                                                                          |
| Fits the job budget                 | `MYBAND_WORKER_JOB_TIMEOUT_SECONDS` (900 s default) is checked _between_ stages, and the lease (`queue.STALE_AFTER`, 15 min) is beaten by the heartbeat thread                                 |
| Tests                               | `tests/test_worker_midi.py` asserts one instrument, the triad that was played, and the window bound                                                                                            |

Two notes that constrain the _design_ of any polyphonic option:

- `test_worker_midi.py` asserts `len(parsed.instruments) == 1`. Polyphony does **not** require
  multiple tracks - one track may hold overlapping notes, which is what a DAW expects from a
  piano roll - so this test can stay true if the writer keeps to one instrument.
- `tests/fakes.py` mirrors `Transcription` field-for-field and a test enforces it, because the
  pipeline's own tests must run without the audio stack installed. **Adding a field to
  `Transcription` is therefore a two-file change**, and that is the cheapest place to notice that
  a contract changed.

## Option 1 - Better pYIN tuning (fix the voicing collapse in place)

Everything stays inside `app/workers/midi.py`. The knobs are real, and were read from the installed
library rather than assumed:

```python
librosa.pyin(y, *, fmin, fmax, sr=22050, frame_length=2048, hop_length=None,
             n_thresholds=100, beta_parameters=(2, 18), boltzmann_parameter=2,
             resolution=0.1, max_transition_rate=35.92, switch_prob=0.01,
             no_trough_prob=0.01, fill_na=nan, center=True, pad_mode="constant",
             transition_min_prob=0.0001)
```

Four changes are plausible, cheapest first:

1. **Read the voicing decision differently.** `pyin` returns `(f0, voiced_flag, voiced_prob)` and
   the pipeline currently looks only at `f0` (NaN where unvoiced), discarding `voiced_prob`. Tera
   Suroor had 39 frames with `voiced_prob > 0.5` against Jyoti's 21 and was still marked entirely
   unvoiced - so a per-frame threshold on `voiced_prob`, or on raw `librosa.yin` plus an
   _independent_ stability floor, is a defensible reading of the same evidence. This is the change
   most likely to fix the 66-byte artifact on its own.
2. **Loosen the HMM's stickiness** (`switch_prob` up, `transition_min_prob` up) so voicing can
   change mid-song instead of being decided by frame one. Cheap, but it moves global behaviour and
   risks regressing Jyoti.
3. **`fill_na=None` plus our own stability floor.** Keep thinking in runs of frames and a minimum
   length, but stop letting the HMM's all-or-nothing flag gate the whole window. The audit already
   showed this _alone_ is not sufficient (one note on the broken songs), which is why it is listed
   third and paired with (1).
4. **Revisit `MIN_VOICED_FRAMES = 3`.** Jyoti's 35 notes came from 167 runs - **97 of them
   singletons**, 58% discarded - and its shortest kept note is _exactly_ 3 frames. That floor is
   calibrated against one song's worth of intuition; a vibrato-tolerant rule (hold a pitch, absorb a
   one-frame excursion) would recover notes the floor is throwing away. This is the lever that
   improves Jyoti's _musical_ quality and the lever that risks producing 20 ms note clusters, so it
   needs an eval set before it is turned.

| Axis                         | Assessment                                                                                                                                                                                                                                                                                                          |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Expected accuracy            | **Modest, and bounded by monophony.** It can plausibly take the 66-byte class of bug to near-zero and make Jyoti's output denser and truer. It cannot invent notes that are not the loudest fundamental, so a beatless or chordal intro still transcribes poorly - the ceiling is the monophonic sketch, unchanged. |
| Implementation effort        | **S** (1-3 days). One module, no new dependency, no new stage. `tests/test_worker_midi.py` already has a real-audio fixture whose pitch classes are known (A, C, E) and asserts the window bound. Most of the work is _choosing_ the reading and proving it on the three real songs as well as the fixtures.        |
| Dependency risk              | **None.** `librosa` is already in the `worker` group and already installed (1.0.0); no resolution change, no image change.                                                                                                                                                                                          |
| CPU/GPU                      | **CPU, and possibly cheaper than today.** Dropping the HMM pass or narrowing the `n_thresholds` sweep reduces work; the current cost (~1 s per second of audio at hop 1024, 11 kHz) remains the budget line.                                                                                                        |
| Suitability for MyBand.video | **High as a bug fix, low as a destination.** It is the only option that can ship without touching the deployment story, and it restores the meaning of the artifact: today "the MIDI is empty" is indistinguishable from "the analysis failed". Worth doing regardless of which other option is chosen.             |

## Option 2 - Stem separation, then pYIN

Run a source-separation model (Demucs `htdemucs`: drums / bass / vocals / other), then point the
existing pYIN stage at one stem. **Verified, not assumed:** `demucs==4.1.0` publishes a
`py3-none-any` wheel with `requires_python >= 3.10`, and `uv pip compile` against our actual target
resolves it - **29 packages on py3.12/Windows, 47 on py3.12/Linux, selecting `torch==2.14.1`**. Its
dependencies are `einops`, `huggingface-hub`, `julius`, `lameenc`, `pyyaml`, `safetensors`, `sphn`,
`torch>=2.1`, `tqdm`; `torchaudio` appears only in the `train` extra, so inference does not need it,
and the `numpy<2` / `torch<2.3` pins are macOS-x86-only and do not apply here.

The appeal is that a separated lead or vocal stem is exactly the input pYIN was designed for, which
is why this is a plausible cure for the voicing collapse.

| Axis              | Assessment                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Expected accuracy | **Better than option 1 on some material, no better on others.** A clean sung or solo line should transcribe well; the "other" stem is still a full chordal accompaniment and hits the same monophony wall. Separation brings its own errors - bleed, phase artefacts, octave jumps - so a stem that is 90% clean can move pitch errors rather than remove them. Separating _and then_ transcribing polyphonically (option 3) is the version that makes musical sense; buying a large model to feed a monophonic tracker is spending a lot to fix a narrow bug. |

## Option 3 - Polyphonic transcription (Basic Pitch or an MT3-class model)

This is the only option that produces what the product's own summary line promises: notes for the
_song_, not a monophonic reading of its intro. It is also the one the repo already tried and failed
to install - and that failure was re-verified for this proposal rather than trusted:

```text
$ "basic-pitch==0.4.0" | uv pip compile - --python-version 3.12 --python-platform windows
x No solution found when resolving dependencies:
  Because only the following versions of tensorflow{sys_platform != 'darwin'} are available:
  tensorflow{sys_platform != 'darwin'}<=2.4.1 ... ==2.8.2 ...
```

`basic-pitch` 0.4.0 is itself a pure-Python `py2.py3-none-any` wheel, so the _code_ is
version-tolerant; the blocker is its unconditional `tensorflow>=2.4.1,<2.15.1` on every non-Darwin
platform, and no TensorFlow in that range has a 3.12 wheel. Three ways around it, in ascending order
of risk:

1. **ONNX Runtime instead of TensorFlow.** `onnxruntime` resolves cleanly for py3.12/Windows
   (`1.31.0`, beside our existing `numpy 2.5.3`), is Microsoft-maintained, and its classifiers cover
   3.11-3.14. The catch is the weights: we would need an ONNX export of Basic Pitch, and we do not
   own one. Community conversions exist on Hugging Face (`AEmotionStudio/basic-pitch-onnx-models`,
   `daserge/basic-pitch-onnx`, `litert-community/Basic-Pitch-LiteRT`, `cstr/basic-pitch-GGUF`) but
   they are unvetted exports of unverified numerical fidelity - a **spike**, not a dependency. The
   official `spotify/basic-pitch` Hugging Face repo was checked and holds only a README, so no
   weights come from there.
2. **Move the transcription stage to Linux + Python 3.11.** Then the published TensorFlow range
   installs and Basic Pitch works as designed. This buys a real model at the cost of a second
   runtime (two interpreters in one image, or a second container), and it inverts the
   "one worker process, one dependency group" property the worker's whole design rests on.
3. **An MT3-class model, vendored.** Note the trap: **PyPI's `mt3` is not MT3** - it is an unrelated
   outlier-detection package (`requires_python <3.11`, "Modified Thompson Tau Test"). Google's MT3
   is JAX research code with downloadable checkpoints, not a pip dependency, so it means vendoring
   code and owning its environment. The pip-installable alternatives are research code or
   community repackaging: `yourmt3` 0.1.4 (pins `transformers==4.45.1`, needs `torchaudio`, no
   declared license) and `amt-tools` 0.3.2 (a framework that drags in `matplotlib`, `sacred`,
   `sounddevice`, `pynput`, `mirdata`, `tensorboard`). Neither is a good fit for a service.

| Axis                         | Assessment                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Expected accuracy            | **A step change, with a caveat that matters.** Basic Pitch is genuinely polyphonic and instrument-agnostic, but its own documentation says it "works best on one instrument at a time" - on a full mix expect a dense, muddy result rather than a chart, plus onset/velocity post-processing before it is usable. MT3-class multi-instrument models are the better answer to "transcribe this song", at far higher compute and licensing cost. Neither is validated by the three songs already audited; this option needs a small labelled eval set to be judged at all. |
| Implementation effort        | **L** (3-6 weeks). A new inference runtime and its weights pipeline; a new artifact shape (simultaneous notes; Basic Pitch also emits pitch bends); writer changes (one track, overlapping notes, distinct offsets - which keeps `len(instruments) == 1` true); the `Transcription` / `fakes` / summary contract; a `MYBAND_PIPELINE_VERSION` bump; a GPU-or-CPU budget decision; provenance and licence review; and an eval harness. The seam does hold: `runner.build_pipeline` injects the transcriber and the pipeline never learns how the bytes were made.         |
| Dependency risk              | **High as attempted today** (TensorFlow is uninstallable for us, proven twice). **Medium via ONNX Runtime** - a mainstream, version-tolerant dependency whose risk concentrates in _our own_ model export rather than in third-party packaging. **High for vendored MT3** (JAX, research code, checkpoint licensing).                                                                                                                                                                                                                                                    |
| CPU/GPU                      | **Basic Pitch is CPU-plausible** - "lightweight" is the premise of the ICASSP model and its wheel is 758 KB - a real advantage over option 2. An MT3-class model is GPU-only in practice and therefore needs the GPU dispatcher that does not exist yet.                                                                                                                                                                                                                                                                                                                 |
| Suitability for MyBand.video | **Highest ceiling, highest floor.** It is the only option that changes what the product _is_ (a MIDI file worth downloading), and the only one whose accuracy cannot be fixed later by tuning, because it is a model choice. It is also the only one that cannot be judged inside one afternoon on a laptop.                                                                                                                                                                                                                                                             |

| Implementation effort | **M/L** (1-2 weeks). A new stage; a decision about whether a stem is itself stored and where; the window question (separate the whole song, or only the window? - the model's cost profile is not pYIN's); weights to fetch or bake into the image; a slow new test fixture; and `Transcription.name` moving off `pyin-monophonic` so stored rows stay interpretable. |
| Dependency risk | **Medium.** `torch` is a multi-hundred-MB dependency in a worker image that today is `librosa` + `pretty_midi` + `soundfile`, and the CPU-vs-CUDA wheel choice is a different index and a different image. `demucs` 4.1.0 is new (2026-07-11) and its own README says the author is "not actively working on Demucs anymore... slow replies and no new feature for now"; the package also pulls weights from Hugging Face at runtime (`huggingface-hub`, `safetensors`, `sphn` are now dependencies), which is a new runtime network dependency and a new cache to manage. |
| CPU/GPU | **GPU strongly preferred; CPU possible but slow.** This is where the worker stops being "a process someone runs" (`pnpm worker:api`, CPU) and starts needing the RunPod path - which is **not wired**: `PRODUCTION_READINESS.md` lists "No GPU dispatcher" as an accepted gap, and the queue only has `queue.mark_dispatched` waiting for it (`queue-state-machine.md`: "exists for the case where something else owns the GPU lifecycle"). Option 2 therefore inherits the whole GPU-dispatch project. |
| Suitability for MyBand.video | **Medium - a component, not a stop.** If a stem separator ever feeds a product story (per-instrument MIDI), it belongs _inside_ option 3. As a standalone answer to the empty-MIDI bug it is the most expensive option per point of accuracy gained. |

## The three, side by side

|                        | 1. pYIN tuning                            | 2. Stems + pYIN                 | 3. Polyphonic model                                             |
| ---------------------- | ----------------------------------------- | ------------------------------- | --------------------------------------------------------------- |
| Polyphonic?            | no                                        | no                              | **yes**                                                         |
| Fixes the 66-byte bug? | **probably, cheaply**                     | probably, expensively           | yes, and it stops asking the question                           |
| Accuracy ceiling       | loudest fundamental, one line             | loudest fundamental of one stem | full mix, dense but real                                        |
| Effort                 | **S** - 1-3 days, one module              | M/L - 1-2 weeks                 | L - 3-6 weeks + eval                                            |
| New dependencies       | none                                      | `torch` + `demucs` + HF weights | `onnxruntime` + a model we must validate (or a 2nd interpreter) |
| Image size / build     | unchanged                                 | +hundreds of MB, index choice   | small (ONNX) or heavy (TF/JAX)                                  |
| Compute                | CPU, unchanged or cheaper                 | GPU preferred, CPU slow         | CPU-plausible (Basic Pitch) / GPU (MT3)                         |
| Needs GPU dispatcher?  | no                                        | yes                             | only for MT3-class                                              |
| Regresses Jyoti?       | possible (re-tuning)                      | low                             | low                                                             |
| What it can't do       | chords, real mixes, anything but a melody | same, one stem at a time        | needs evaluating before it can be trusted                       |

The asymmetry to notice: **option 1 is the only one that buys back trust in the artifact for one
module's worth of work, and options 2 and 3 are both gated on a GPU dispatcher that does not
exist.** Option 2 is dominated by option 3 wherever it is not simply an input to it.

## Recommendation

**Stage it, and do not let the choice of model block the bug fix.**

1. **Do option 1 now, as a correctness fix rather than an accuracy project.** A `.mid` that is
   valid, empty and reported as `succeeded` is a bug whatever the transcriber is, and it is fixable
   inside `app/workers/midi.py` with no new dependency. Two things belong in the same change,
   because they are the same complaint:
   - the voicing reading (`voiced_prob` and/or raw `yin` plus an independent stability floor, with
     `switch_prob` / `transition_min_prob` re-tuned behind the three real songs as a check);
   - a decision about _reporting_: a note count of zero should be visible in the row (`transcriber`
     already travels in the summary) rather than indistinguishable from a successful transcription.
2. **Spike option 3 before committing to it - 2-3 days, outside the repo if that is easier.** The
   spike answers exactly one question: does a Basic Pitch ONNX export of acceptable fidelity exist
   (ours, or a community export we validate against the three songs plus two or three known
   fixtures)? If yes, option 3 becomes an `onnxruntime` dependency plus an artifact-shape change and
   the GPU dispatcher is not on the critical path. If no, option 3 means TensorFlow on Linux/3.11 or
   a vendored MT3 - and _that_ is the point where the GPU dispatcher and the licensing review have
   to be paid for, at which point the honest comparison is against the whole RunPod phase rather
   than against `midi.py`.
3. **Treat option 2 as an input to option 3, not as a milestone.** Stems plus a monophonic tracker
   does not deliver a product-visible improvement that justifies `torch` in the worker image. If the
   spike in (2) lands on a polyphonic model that struggles on mixes, _then_ a stem-separated feed is
   the refinement to try - with the same polyphonic model, not pYIN.

**Explicitly not recommended:** shipping the TensorFlow dependency (uninstallable here, and the repo
has already paid for that knowledge once); adopting `yourmt3` or `amt-tools` as dependencies
(community repackaging and a research framework, respectively, with pinning and licensing left
open); and letting the empty-MIDI-is-success behaviour stand while a model is chosen.

## What has to be decided, and measured, before this leaves the proposal stage

- **An eval set.** Three songs is an anecdote. Five to eight recordings with hand-written note lists
  (or at least a melody/chord sketch a musician agrees with) turn "did this improve?" from an
  opinion into a number, and it is the missing input all three options share. Nothing else here is
  worth doing first.
- **What the MIDI artifact promises the user.** "A sketch of the intro" and "your song as MIDI" are
  different products with different budgets. `docs/analysis-worker.md`'s "Known limitations" is
  honest about today's answer; the recommendation above is that the _row_ says so too.
- **Whether the window survives the transcriber.** `MYBAND_WORKER_MIDI_WINDOW_SECONDS` exists purely
  because of pYIN's cost. If option 3 lands, the whole song becomes affordable and the artifact's
  meaning changes - a `MYBAND_PIPELINE_VERSION` bump and a doc change, not just a new default.
- **Where the model weights live.** In the image (build-time, reproducible) or fetched at runtime
  (fast, and a new network dependency on Hugging Face, which is how `demucs` 4.1.0 works today).
  This is a deployment decision the current CPU worker has never had to make.

## How this file is maintained

- **It is a proposal, not a contract.** Once a path is chosen, the decision and its consequences go
  where the code lives: `docs/analysis-worker.md` for what the stage does,
  `PRODUCTION_READINESS.md` for a risk the choice accepted. This file should then be marked
  superseded, so nothing cites a document that no longer describes the plan.
- **Every claim above is either verified in this repo or was verified for this document** -
  `uv pip compile` against py3.12/Windows and Linux, `inspect.signature(librosa.pyin)` against the
  installed 1.0.0, and the PyPI and Hugging Face metadata quoted. Where a number is an estimate
  (timings, effort, accuracy) it is written as one, because the same standard applies here as in
  `docs/analysis-worker.md`: measure it or say you have not.
