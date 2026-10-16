# Beta user recruitment

The operating plan for the closed beta: which ten people, what the message says, what the tester is
asked to do, what comes back, and what would make the round a success. Its companion is
[BETA_SIGNOFF.md](BETA_SIGNOFF.md) - that file is the evidence that the release works on one machine;
this one is the plan for what happens when it is put in front of somebody who did not build it. The
release under invite is certified in [V0_4_RELEASE_SIGNOFF.md](V0_4_RELEASE_SIGNOFF.md), the pipeline
it runs is described in [docs/analysis-worker.md](docs/analysis-worker.md), and the plan that consumes
the results is [NEXT_3_RELEASES.md](NEXT_3_RELEASES.md).

**Status: drafted, not sent. Ten seats, none filled.** Nothing in this file is a measurement. The
thresholds in section 7 are choices written down before recruiting began, so that the round can fail a
criterion rather than be judged by feel. Section 2 lists what has to be true before the first message
goes out, and one of those items is a sentence in the product that is currently false.

## 1. What the ten people are being given

The product's own account of itself, not a pitch written for recruits. Every row is something the
v0.4 worker produces and the web app draws.

| They get        | Exactly what it is, limitations included                                                                                                                                   | Where that is stated                                                      |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Duration, tempo | Duration from the container header; tempo from beat tracking across the whole recording, with the beat count alongside it                                                  | `docs/analysis-worker.md`, `copy.ts` "BPM Detection"                      |
| Key             | The winning key of all 24, with the correlation that won it - and a weak winner is shown as weak (0.26 on one 62-second clip)                                              | `copy.ts` "Key Analysis" and the FAQ on accuracy                          |
| Chord timeline  | Every stretch in order, two readings on one toggle (the plain triad, or the label the detector heard), the mean confidence, and how much of the recording the chords cover | `/songs/[id]`, `chord-timeline.tsx`, `docs/analysis-worker.md`            |
| Song form       | Which stretches are the same music, in order, as letters - `A B A B C` - compared four seconds at a time. A letter is not a name                                           | `section-map.tsx`, the FAQ on sections                                    |
| MIDI            | A monophonic pYIN sketch of the melody, tempo map included, up to 120 s clamped to the recording, saved as `<title>.mid`                                                   | `docs/analysis-worker.md`, [MIDI_WINDOW_REPORT.md](MIDI_WINDOW_REPORT.md) |
| A seat          | Free while the beta runs, no card on file, ten seats handed out by hand                                                                                                    | The landing page's beta panel (`beta-access.tsx`)                         |

And the other column, because the invite has to carry it too:

| They do not get                 | Why                                                                                     | Id  |
| ------------------------------- | --------------------------------------------------------------------------------------- | --- |
| A delete, a cancel, a retry     | A failed song stays failed until it is uploaded again, which makes a second song        | R3  |
| A quota                         | One account can fill the bucket; an open beta is a cost exposure                        | R5  |
| Names for the sections          | Naming a chorus takes the lyrics, and a wrong chorus is worse than an honest letter     | -   |
| A transcription of the mix      | One line: no bass, no drums, no harmony - a sketch to arrange from, not a finished part | -   |
| A player                        | A download fetches the whole object, so there is no scrubbing                           | -   |
| In-app feedback or analytics    | No analytics dependency and no `track(` call anywhere, so the beta is run by hand       | F3  |
| Google sign-in, until it is off | No `[auth.external.google]` block locally, so only email and password were exercised    | -   |

**One consequence worth stating on its own line: nothing in the bucket is ever deleted** (R4 ties to
R5). "We will remove it afterwards" is not a promise this release can make, which is why section 3
makes "holds the rights to what they upload" a requirement rather than a preference.

## 2. Before the first invite goes out

Four items. Three are conditions the release already carries (section 6 of
[BETA_SIGNOFF.md](BETA_SIGNOFF.md)); the first is new here, and it is the one that has to be settled
before anything else, because it is a sentence on the page every recruit will land on.

### 2.1 The landing page promises a delete the product does not have

`apps/web/features/marketing/components/beta-access.tsx` lines 142-145 tell the visitor:

> This takes you to sign-up with your address filled in. Seats are activated by hand, and you can
> delete a track - and its files - whenever you want.

That is not true today, and there are three independent pieces of evidence rather than one:

| Evidence                                                            | What it says                                                                                     |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `apps/api/app/api/routes/`                                          | GET and POST only. There is no `DELETE` handler anywhere in the API                              |
| `README.md`, "Rules that are not negotiable"                        | "no table has a DELETE or INSERT policy" - so a direct Data API delete is refused by RLS as well |
| `PRODUCT_READINESS_V0_4.md:166-168` and `BETA_SIGNOFF.md` section 8 | "there is no cancel path and no delete"; "a delete" is listed among what the product cannot give |

The `deleted_at` guards in `routes/songs.py` are read-side only: they exist so a soft-deleted row
answers `404`, not so one can be created. The only delete path in the tree is `auth.users` cascading.

Two ways out, and they are not equal in size: **delete the clause** (one sentence, and it is what
`copy.ts`'s own first rule already demands - nothing is claimed that the product does not do today),
or **ship a delete** (a route, a policy, a GC path and a test - release 0.5's item 5). Under the
v0.4 feature freeze neither is done in this file. Until one is, this document cannot recommend
sending the message in section 4, because a tester who reads that sentence and then hunts for the
control has been taught that the page is not to be trusted - which is a more expensive lesson than
any chord label this round could correct.

### 2.2 Google sign-in, decided one way or the other

The login page offers "Continue with Google" and there is no `[auth.external.google]` block in
`supabase/config.toml`, so on the local stack that button has nothing behind it and only email and
password were ever exercised. Either enable the provider on the deployed project (the dashboard steps
are listed in `apps/web/.env.example`) or invite people who will use email - and if it is the second,
say so in the invite so nobody's first two minutes are spent on a button that does not answer.

### 2.3 The deployment agrees with the pipeline it is running

`MYBAND_PIPELINE_VERSION=0.4.0` has to be set on the **API and the worker**, and a worker has to be
alive. Both halves matter for a cohort:

- A stale value silently wins over the shipped default, so a deployment still set to `0.2.0` stamps
  `0.2.0` on rows the sections pipeline produced, and every result this round is filed under the
  wrong pipeline.
- With no worker running, nothing reaps a job whose worker died and the song says "Analysing"
  forever (R2). The sweep at startup clears the backlog on the next worker start, so this is an
  alert to watch, not a fix.

## 3. Ideal tester profile

### 3.1 The hard requirements

Five, and a person who fails any of them is the wrong seat however useful their opinion would be.

1. **They make music and can hand over a recording of their own** - MP3 or WAV, under 200 MiB. Not a
   file they found: their own bounce, their own take, something they hold the rights to. Nothing in
   the bucket is ever deleted (R4/R5), so this is a consent requirement, not a licensing formality.
2. **They can answer "is this chord wrong?" without asking us.** The whole point of the round is an
   ear the pipeline does not have: a tester who has to be told what the chords are cannot supply it
   (N3 - the labels have never been checked against a musician, which is why this round exists).
3. **They have a reference for tempo and key** - a DAW session tempo, a tap-tempo, a chart. A verdict
   of "the BPM is right" only means something against a number they already held.
4. **They are reachable one-to-one** and will reply for about twenty minutes, once. Feedback that
   arrives as a specific ("0:42 heard F, product says Dm") is a fix; feedback that arrives as a mood
   is a mystery, and the specifics only come out in a one-to-one conversation, not a group thread.
5. **Nothing depends on the product for them.** No billing, no retry, no delete, no quota and one
   region - so nobody with a deadline riding on it. That is a limit of this release, not a preference.

### 3.2 The ten seats

The mix is taken from [BETA_SIGNOFF.md](BETA_SIGNOFF.md) section 8, which is the same recommendation
this file is executing. Each seat is written against the question only that seat can answer.

| Seat | Who                                                     | What only this seat can answer                                                                        |
| ---- | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| 1-6  | An independent producer or songwriter, known personally | Whether the chords are the ones a musician hears, and where a specific one is wrong - the N3 question |
| 7-8  | A DAW user who works with MIDI daily                    | Whether the sketch is importable, editable and useful, judged as a sketching aid rather than a part   |
| 9    | The one who will try to break the upload rules          | Whether the refusals behave: a 250 MiB file, a `.flac`, a text file renamed `.mp3`, no extension      |
| 10   | The one who will use a non-Latin title                  | Whether a Devanagari title travels from the filename into the library intact                          |

Seat 9 exists because the rules are implemented twice (`file-rules.ts` client-side,
`upload_rules.py` server-side) and the signed-off run only ever fed them three well-behaved MP3s.
Seat 10 is a smaller bet: a Devanagari title has rendered correctly in the library before, from an
earlier upload, but nothing in the v0.4 run exercised it and titles come straight off the filename.

### 3.3 Who not to invite

- **Anyone uploading commercial masters they do not own.** Nothing is ever deleted, so "we will
  remove it later" cannot be said. Not a label, not a stranger from a public link, not a mailing list.
- **Anyone who has been told the roadmap exists.** The AI guitarist, the AI drummer and band
  generation are labelled _Planned_ on the page and in the footer; a tester who signs up expecting an
  AI drummer is a tester who leaves on day one.
- **Anyone who needs the delete.** Until 2.1 is settled, do not put a person in front of a page that
  offers one.
- **Anyone who wants to send "general feedback".** The round has five specific questions; a tester
  with no song of their own has nothing to compare against.

---

## 4. Outreach message

### 4.1 The rules the message obeys

The invite is a product claim by another name, so it follows `copy.ts`'s two rules and adds two more:

1. **It promises only what section 1 lists** - the six rows, in the same terms.
2. **It carries one limitation per artifact, in the same breath as the good news.** "It is a beta" is
   not a disclaimer; "the MIDI is one line and stops at 2:00" is.
3. **It asks for one song and one form.** Not "give us lots of feedback" - a defined twenty minutes is
   something a person can say yes to.
4. **It tells the delete truth**, which today is the opposite of what the landing page says (2.1), and
   says outright that the tester should upload only what they are happy to leave there.

### 4.2 The invite

Subject: `MyBand.video beta - a seat, and one song you know well`

```text
Hi <name>,

I'm building MyBand.video. You upload a recording and it hands back the tempo, the key, the chord
timeline, the song's form and a MIDI sketch of the melody. Ten seats, free, no card - and I would
rather the ten were people who can tell me when it is wrong than people I can count.

So, honestly, both columns.

What it does, on real recordings: a 5:45 track came back 117 BPM, C# minor, 170 chord segments, in
about ten seconds.

What it does not do yet:
- The MIDI is one monophonic line, not a transcription of the mix. No bass, no drums, no harmony, and
  it covers up to the first 120 seconds, clamped to the song - something under two minutes is
  transcribed whole.
- The chords are confident, not verified. Nothing has yet checked the labels against a musician's ear.
  That is the thing I am asking you for.
- The sections are the song's form written as letters, A B A B C. It will not call one of them a
  chorus: that takes the lyrics, and a wrong chorus is worse than an honest letter.
- The key arrives with a strength, and on short or sparse recordings it can be near a coin toss - 0.26
  on one 62-second clip. The page shows you the number instead of hiding it.

Two things to know before you upload anything:
- Nothing you upload is ever deleted yet. I cannot remove it for you afterwards, so please make it one
  of your own recordings rather than a commercial master.
- There is no cancel and no re-run: if a song fails, uploading it again makes a second song. And please
  use email and password to sign up - the Google button is not wired up for this beta.

What I am asking for: one song you know well (MP3 or WAV, under 200 MiB), the five steps in the note
below, and about twenty minutes of your time. Import the MIDI into your DAW before you answer - the
question I care about most is whether the notes land on a track and whether the chords are the ones
you hear.

Analysis can take a minute or two, and it runs one song at a time, so a queue can build up if a few
of us upload at once.

The beta is free and there is no card on file. Pricing for whatever comes after the beta is not
settled, and beta testers hear the number first.

When you are done, the form: <form link>

Thanks - <you>
```

Two notes on the wording, so it does not get edited into a lie later. "About ten seconds" is one
measurement from one run on a CPU-only box ([BETA_SIGNOFF.md](BETA_SIGNOFF.md) section 4: 16.3 s /
10.5 s / 2.4 s for 246.8 s / 344.9 s / 62.2 s recordings), stated as a number rather than as a rate.
And the delete paragraph is the awkward one: it stays until 2.1 is settled, because a tester who has
been told up front cannot be surprised afterwards.

### 4.3 The two shorter messages

The first cohort is people you already know, so most seats will be filled by a direct message rather
than by the letter above. Same content, fewer words, no formality:

```text
Hi <name> - I'm building MyBand.video: upload a song, get the tempo, key, chord timeline, the song's
form and a MIDI sketch back. Ten beta seats, free, no card. All I need is one song you know well and
your ear on whether the chords are right - nothing has checked them yet, which is the whole point of
asking you.

The MIDI is one monophonic line, up to the first 2 minutes, and it imports into your DAW. There is no
delete yet, so it has to be your own recording, and use email/password rather than the Google button.
About 20 minutes. Want a seat?
```

And a nudge on day 3 or 4, for anyone who said yes and went quiet:

```text
No rush at all. If 20 minutes is the blocker, the short version is two questions: is the tempo right,
and is the key right? One line each and you have done your bit. The rest can wait until you have time.
```

The close-out, when the round ends, is the one message worth writing carefully: it says what changed
because of them, and it is where the pricing promise from the invite is kept. A tester who is told what
their answer moved is a tester for the next round; a tester who is thanked generically is not.

---

## 5. Feedback form

### 5.1 How the feedback travels

Two channels, and both are outside the product - which is itself the finding release 0.5 fixes.

- **There is no in-app capture.** No analytics dependency and no `track(` call anywhere (`F3`), and no
  contact address in the product either, so nothing inside the app could receive an answer even if a
  tester looked for somewhere to put one.
- **The form** (a link in the invite) is the written record, and **the reply thread** the invite came
  from is where the specifics land. The form is the thing that can be tallied; the thread is where
  "0:42 is Dm, not F" usually arrives first.
- **The manual substitute for the missing funnel** is section 6's step log: the tester writes down
  which panels they opened. That is the honest version of "the timeline was viewed" when no such event
  exists - and it is a person's memory, so it is treated as a hint rather than a number until release
  0.5 instruments the seven real steps.

### 5.2 The fields

Fourteen, in this order. Numbered here so a form builder can be filled in without inventing anything.

| #   | Field                                                            | Answer                                 | Why it is on the form                                                               |
| --- | ---------------------------------------------------------------- | -------------------------------------- | ----------------------------------------------------------------------------------- |
| 1   | Name, and the email you signed up with                           | Text                                   | Matches a reply to a song without asking twice                                      |
| 2   | What you do, and which DAW                                       | Text                                   | A verdict from seat 7 means something different from a verdict from seat 2          |
| 3   | The song's title, and why you know it well                       | Text                                   | The reference. Without it a chord verdict is not possible                           |
| 4   | What you compared the tempo and key against                      | DAW tempo / tap tempo / chart / memory | A verdict against a number you already held is evidence; memory is a hint           |
| 5   | May we quote you                                                 | By name / anonymously / no             | Asked rather than assumed                                                           |
| 6   | May we keep the recording, and until when                        | Yes / no, and a date                   | The honest inversion: nothing is deleted, so consent is the only thing that ends it |
| 7   | Five verdicts - BPM, key, chords, sections, MIDI                 | The scale below, plus a sentence each  | The round's five questions, each with a number and a reason                         |
| 8   | Chord errors, in time order                                      | One line each (5.4)                    | The difference between a fix and a mystery                                          |
| 9   | Section verdict                                                  | Text                                   | Does the form match the shape you hear, and where does a repeat start wrong         |
| 10  | MIDI import report                                               | Text (5.5)                             | The only artifact that leaves the product, and a DAW is the thing that judges it    |
| 11  | A bug: what you did, what you saw, what you expected             | Repeatable text                        | "It broke" is not reproducible                                                      |
| 12  | Which artifact you would keep, and which you would drop tomorrow | Two answers                            | This is the pair that ranks 0.6 against 0.7                                         |
| 13  | What you would have paid, if anything                            | Text, or "nothing"                     | Keeps the pricing promise, and "nothing" is a real answer                           |
| 14  | One thing you would tell the next tester                         | Text                                   | The cheapest recruiting copy there is                                               |

### 5.3 The scale for field 7

Pinned to what the tester can defend, not to enthusiasm:

| Score | Means                                    |
| ----- | ---------------------------------------- |
| 5     | Right, and I would use it as it stands   |
| 4     | Right, but I would still check it by ear |
| 3     | Mostly right, wrong in places            |
| 2     | Wrong in places I care about             |
| 1     | Wrong, and confident about it            |
| N/A   | I never opened this panel                |

**`N/A` is a finding, not a missing answer.** It is the closest thing this round has to a funnel
measurement - five `N/A`s on the section map while everyone scored the chords is exactly the signal
that reorders 0.6 and 0.7 - so it is never nagged away or filled in by whoever collects the forms.

### 5.4 The chord-error line

One shape, so the answers can be read in one pass:

```text
0:42   heard: F        product says: Dm
1:15   heard: C/G      product says: C
2:03   heard: nothing  product says: Am
```

Three rules. **A timestamp per error**, not a general verdict. **`heard:` is optional but valuable** -
"The third chord in the chorus is wrong" is a fix, "the chords are wrong" is a mystery (N3). And **if a
whole progression is wrong, say so once** rather than forty times: forty identical lines are one
finding, and a form that looks like it took an hour will not be filled in twice.

### 5.5 The MIDI import report

The one artifact that leaves the product, so it is asked about where it arrives - in a DAW:

- Which DAW and version, and did the file import at all.
- Notes: how many landed, and whether the notes are on the beat or drifting against it.
- What is missing that the tester expected: bass, chords, drums, the back half of the song.
- **The tempo and key the DAW displays, if it displays one.** These are the DAW's own guess and not
  ours: the file carries no key signature and the notation apps derive both. A tester who reports
  "MuseScore says A major and the page says C# minor, one of you is wrong" has found N2, not a bug -
  and the form says so in one line so the round does not spend an hour on it.
- Whether they would import it again for the next song they learn. That last question is the honest
  measure of the sketch, and it is a better predictor of 0.6's value than any note count.

### 5.6 The form as plain text

For whoever builds it, or for a round run entirely by email. Same fourteen fields, no tool implied:

```text
MyBand.video beta feedback

1. Name and the email you signed up with:
2. What you do, and which DAW:
3. The song's title, and why you know it well:
4. What you compared the tempo and key against (DAW tempo / tap tempo / chart / memory):
5. May we quote you? (by name / anonymously / no)
6. May we keep the recording, and until when?
7. Verdicts - 5 right and I'd use it, 4 right but I'd check, 3 mostly right, 2 wrong in places,
   1 wrong and confident, N/A I never opened it:
     BPM       score:      why:
     Key       score:      why:
     Chords    score:      why:
     Sections  score:      why:
     MIDI      score:      why:
8. Chord errors, one per line:  time - heard: X - product says: Y
9. Sections: does A B A B C match the shape you hear? Where does a repeat start too early or late?
10. MIDI: DAW and version, did it import, how many notes, what is missing, would you import the next one?
11. Bugs: what you did, what you saw, what you expected (one block each):
12. Which artifact would you keep if the other four were deleted, and which would you drop tomorrow?
13. What would you have paid for this, if anything?
14. One thing you would tell the next tester:

Which panels did you open? (tick what you actually looked at - this stands in for the analytics the
product does not have yet)
  [ ] the measurement tiles   [ ] the chord timeline   [ ] the section map
  [ ] the MIDI download       [ ] the library row's status
```

---

## 6. Testing script

What the tester is handed, verbatim. Twenty minutes for the happy path; seats 9 and 10 get ten more.
Steps 1-7 are the product; the log in 6.4 is the part that stands in for the funnel the product does
not measure yet.

### 6.1 The seven steps

| #   | What you do                                                        | What you should see                                                           | If it goes wrong                                                                                     |
| --- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| 1   | Sign up from the invite link, with email and password              | The dashboard: an empty library and a dropzone                                | Do not use the Google button for this beta (2.2). Tell us if you tried it                            |
| 2   | Choose one song you own the rights to - MP3 or WAV, under 200 MiB  | A file picker that accepts it                                                 | A refusal for a `.flac` or an oversize file **before** anything uploads is correct, not a bug        |
| 3   | Upload it, and note the clock                                      | The row moving Queued -> Starting -> Analysing -> Analysed, without a refresh | Stuck on "Analysing" past 15 minutes is the one to report immediately (R2)                           |
| 4   | Read the measurement tiles                                         | Duration, tempo, key - and the key's strength                                 | An absent tile means that measurement does not exist. `0 BPM` would be a bug, and there is none      |
| 5   | Read the chords in the default reading, then tap to the detector's | Chords in time order, a mean confidence and a coverage bar                    | An empty timeline is a state, not an error: it means nothing was played in the recording             |
| 6   | Compare the section letters with how you would describe the song   | Letters, and the same letter twice means the same music twice                 | Boundaries land on a four-second grid, so one can be up to four seconds out. That is by design       |
| 7   | Download the MIDI and import it into your DAW                      | `<title>.mid` opens, and the notes land on a track you can edit               | Your DAW shows its own tempo and key: the file carries neither. An empty file is the loudest finding |

Two habits the script asks for, because they are what turns an afternoon into a fix: **write the clock
down at step 3** - Analysed time minus upload time, the only timing this round measures, on one machine

- and **write the timestamp of every chord you disagree with**, in the 5.4 shape.

### 6.2 Seat 9 - the break-it pass

Five tries, all of them expected to be refused, none of them harmful:

| Try                        | Expected                                           | What to report                                         |
| -------------------------- | -------------------------------------------------- | ------------------------------------------------------ |
| A 250 MiB file             | Refused before a byte is sent                      | Did the message say why, and in plain words?           |
| A `.flac`                  | Refused before a byte is sent                      | Same                                                   |
| A text file renamed `.mp3` | Refused, at the server if the browser lets it past | Which of the two refused it                            |
| A file with no extension   | Refused                                            | Same                                                   |
| A filename with an emoji   | Accepted, tidied into the library                  | What the title became, and whether it is still legible |

The one thing worth watching for: **a refusal that leaves a song row behind.** The rules are enforced
twice on purpose (`file-rules.ts` client-side, `upload_rules.py` server-side), and a rejection that
still creates a library entry is a different bug from one that does not.

### 6.3 Seat 10 - the non-Latin pass

Upload a file whose name is in Devanagari, for example `ज्ञानज्योतिः.mp3`. The title comes straight off
the filename, and the library has rendered a Devanagari title correctly before - from an earlier
upload, in an earlier release, which is not the same as this one having exercised it.

Report the three places the name appears: the library row, the song page's heading, and the MIDI
filename handed to the DAW. A mangled name in one of the three and not the others is a more useful
report than "the encoding is broken".

### 6.4 The step log

The seven events release 0.5 will instrument, written down by hand instead. The tester ticks each one,
with a time. This is the section that decides what 0.6 and 0.7 are for, so it is asked for explicitly
rather than left to memory:

| Event                                           | Tick and time     | 0.5's event         |
| ----------------------------------------------- | ----------------- | ------------------- |
| Upload started                                  | `____` at `__:__` | `upload_started`    |
| Upload completed                                | `____` at `__:__` | `upload_completed`  |
| Song queued                                     | `____` at `__:__` | `queued`            |
| Song analysed                                   | `____` at `__:__` | `analysed`          |
| The chord timeline was opened                   | `____` at `__:__` | `timeline_viewed`   |
| The section map was opened                      | `____` at `__:__` | `form_viewed`       |
| The MIDI was downloaded                         | `____` at `__:__` | `midi_downloaded`   |
| Which of those did you return to a second time? | text              | nothing measures it |

---

## 7. Success criteria

Two kinds: numbers a human counts, and verdicts on the five artifacts. **Every threshold below is a
choice, not a measurement.** Nothing has been recruited yet, so there is no baseline - they are written
down before the round starts so that the round can fail a criterion instead of being judged by feel.

### 7.1 Recruitment and activation

| Criterion                                               | Target | Fails below |
| ------------------------------------------------------- | ------ | ----------- |
| Seats filled - invited, signed up, in the library       | 10/10  | 8           |
| Activated - first song reaches "Analysed" within 7 days | 8/10   | 6           |
| Repeat use - a second song uploaded by the same tester  | 5/10   | 3           |
| Forms returned                                          | 8/10   | 6           |
| Threads containing at least one specific correction     | 4      | 2           |

The repeat-use line is the one worth defending: a product everybody tries once and nobody returns to is
a demo with a nicer colour scheme, and the round would be measuring the pitch rather than the product.

### 7.2 Per-artifact coverage - the point of the round

Each of the five artifacts needs five independent verdicts, and at least three of those need to name
something specific enough to act on.

| Artifact | A verdict is                                                   | "Wrong" has to include                                   | Target                               | Now |
| -------- | -------------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------ | --- |
| BPM      | The number compared with one you already held                  | Their number, ours, and which song                       | 5 verdicts                           | 0   |
| Key      | The key you hear, against the key and strength the page showed | Whether the strength warned you off, in hindsight        | 5 verdicts                           | 0   |
| Chords   | A listen against the timeline                                  | At least one timestamped error in the 5.4 shape          | 5 verdicts, 3 stampable              | 0   |
| Sections | The form compared with how you would describe the song         | Which repeat lines up wrong, and where the boundary sits | 5 verdicts                           | 0   |
| MIDI     | An import into a DAW                                           | Whether notes landed, and what is missing                | 5 verdicts, 1 from a daily MIDI user | 0   |

The "Now" column is filled in as the forms come back; it is the only place in this file that holds a
count, and it stays empty until a real person has answered.

### 7.3 What counts as data

- **A verdict is a comparison, not an impression.** "The tempo is right, my DAW says 117.45" is a
  verdict. "It feels accurate" is not one, however kind it is.
- **Compliments are not verdicts.** If every seat is filled and every form comes back saying "cool",
  the round produced no evidence about any of the five artifacts and it failed - which is the exact
  failure mode this file exists to prevent, because the funnel has no instrumentation behind it to
  catch it (F3).
- **Specificity is the currency.** "The chords are wrong" is one verdict, not one bug. Three
  timestamped errors are worth more than ten scores, and they are also the only thing that can be
  carried into a fix without a second conversation.
- **Absence is data.** An `N/A` on the section map while the chords were scored tells us where these
  users actually live, which is precisely the input the 0.6-against-0.7 decision needs. It is never
  filled in on the tester's behalf.

### 7.4 Abort criteria

The round stops, rather than collecting a full ten, if any of these happens:

- **Two testers report a song stuck on "Analysing" past 15 minutes.** Stop inviting and check that a
  worker is alive (R2): with no worker, nothing reaps a job whose worker died, and the startup sweep
  only clears the backlog on the next worker start.
- **A tester says they uploaded something they do not own.** Stop, and say so plainly - nothing in the
  bucket is ever deleted (R4/R5), so silence is the only thing that makes it worse.
- **The delete sentence in 2.1 is still on the landing page when the first invite is due to go.** Do
  not send it. Every other item in section 2 costs a decision; this one costs a sentence.
- **The same failure with no retry path (R3) is reported by two or more testers.** Record it as the
  round's most expensive finding and stop adding seats until release 0.5 has a position on retries: a
  failure that costs a tester their upload is not offset by a fourth ear on the section map.

### 7.5 The decision this round exists to make

[NEXT_3_RELEASES.md](NEXT_3_RELEASES.md) sets the order as 0.6 (MIDI) then 0.7 (sections), and says in
the same breath that any reordering has to come from data rather than from that document's intuition:
if testers ignore the chord timeline and live in the section map, 0.7 moves ahead of 0.6; if MIDI
downloads stop at the preview, the MIDI is what gets fixed. Fields 12-14 and the step log in 6.4 are
the inputs to that call, and the close-out message to the cohort is where the answer is stated.

### 7.6 What success is not

- Ten accounts and no opinions.
- A count of songs uploaded. That measures the funnel, not the artifacts, and the funnel is not
  instrumented (`F3`) so the count would not even be trustworthy.
- An accuracy figure. This round produces ten verdicts from ten ears on one song each; the only thing
  that can produce an accuracy claim is the labelled set - five to eight recordings with an ear on
  them, the item `N3` already scoped - and paying for that is a release decision, not a beta outcome.

---

## 8. The tracker

Ten rows, filled in as the round runs. It exists so the seats can be counted without reading a mail
thread, and so the section 7.2 tally has somewhere to be summed from.

| Seat | Name | Why this seat       | Invited | Activated | Songs | Form back | Artifacts covered | Notes |
| ---- | ---- | ------------------- | ------- | --------- | ----- | --------- | ----------------- | ----- |
| 1    |      | Producer/songwriter |         |           |       |           |                   |       |
| 2    |      | Producer/songwriter |         |           |       |           |                   |       |
| 3    |      | Producer/songwriter |         |           |       |           |                   |       |
| 4    |      | Producer/songwriter |         |           |       |           |                   |       |
| 5    |      | Producer/songwriter |         |           |       |           |                   |       |
| 6    |      | Producer/songwriter |         |           |       |           |                   |       |
| 7    |      | DAW / MIDI daily    |         |           |       |           |                   |       |
| 8    |      | DAW / MIDI daily    |         |           |       |           |                   |       |
| 9    |      | Break-it pass       |         |           |       |           |                   |       |
| 10   |      | Non-Latin title     |         |           |       |           |                   |       |

## How this file is maintained

- **It describes one round, not the programme.** When the ten seats are filled and the forms are in,
  the results become a findings document - or, more likely, the evidence behind release 0.5's first
  item - and this file is rewritten for the next cohort rather than appended to. The tracker is the
  one part that is meant to be edited in place while the round runs.
- **Every claim above about the product is a claim about a file**, so four of them can go stale and
  this file is wrong until they are re-checked: `copy.ts` and `beta-access.tsx` for what the landing
  page says, `docs/analysis-worker.md` for what the pipeline does, and the register's R3/R4/R5 lines
  for what is deliberately absent.
- **Nothing here is evidence of anything yet.** It becomes evidence when a person who did not build
  the product has answered field 7, and not before - which is the same rule
  [BETA_SIGNOFF.md](BETA_SIGNOFF.md) applies to every number it states.
- **Do not send it until section 2 is settled**, and 2.1 first: a page that offers a delete the
  product does not have is a worse first impression than any artifact this round could correct.
