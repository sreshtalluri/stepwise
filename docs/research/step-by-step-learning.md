# Guided step-by-step learning: research, prototype, design (2026-09-24)

> **Round 2 (same day)** adds §6–§11 below: the UI plan with click-through mockups, the
> not-dancing trim, detail levels, the grid and A/V sync check, sub-beat steps, and an
> updated plan. Its short answer:
> - **UI:** follow §6. The mockups are in `tools/research/step_segments/mockups/`.
> - **Not dancing:** trim the lead-in and outro by default (bhangra's walk-in ends at
>   4.47 s), and let the learner override it.
> - **Detail levels:** use Beginner, Intermediate and Advanced, cut as a nested tree. Default
>   to Beginner, which gives 1–2 counts per step at 62–86% on four lessons.
> - **The "and" worry is resolved.** The grid is right and the clips are in sync to
>   within about one video frame.
> - **Sub-beat:** none of these 5 clips has a 16th-note passage that can be found above
>   chance. Ship half-beat detail in v0. Add quarter-beat later from audio plus
>   native-fps video. Only raise the 3D fps (a ×2 cost) if a labelled fast clip set shows
>   it is needed.

**Short answer (round 1):** build it. v0 needs no model and no pipeline change. Cut each selected
loop into steps at half-beats where the 3D body stops or changes direction. Group the
steps into chunks of about 4 counts. Then walk the learner through
*step → add the next → put it together → loop the chunk → Build up → next chunk*,
using the loop, speed, Build up and metronome we already have. Every cut and name can
be edited. The prototype's cuts are plausible teacher cuts on the choreography lessons.
They are too fine on fast songs until the step length adapts to tempo, and they need a
"not dancing yet" trim at the start. v1 adds one Claude call per lesson that turns the
measured features into short cues. It costs about $0.02–0.05 per lesson on Sonnet 5.
Each cue is checked word by word against the features and dropped if it says anything
the features do not. Webcam feedback (v2) should wait.

Everything here is research. There are no production code changes. The prototype is in
`tools/research/step_segments/`.

---

## 1. How dance is actually taught

What teachers and the research agree on:

- **Break the phrase into steps in time, then build it back up.** Motor-learning
  research calls this *segmentation*: splitting a skill into serial parts in time
  ([Wightman & Lintern 1985](https://journals.sagepub.com/doi/10.1177/001872088502700304)).
  Two related methods are *fractionation* (parts that happen at the same time, such as
  feet first and arms after) and *simplification*. Part practice suits skills that are
  complex and loosely connected, and dance phrases qualify
  ([Naylor & Briggs 1963](https://pubmed.ncbi.nlm.nih.gov/13937802/)). Later studies
  support that hypothesis only partly.
- **Add-on, or cumulative, teaching.** Teach a bit, add the next bit, then go back to
  the start and run everything so far
  ([Richard Powers](https://www.richardpowers.com/teaching-tips),
  [West End in Schools](https://westendinschools.org.uk/blog/a-guide-to-teaching-dance-part-2-how)).
  This is exactly the owner's "learn step 1, step 2, combine, loop the chunk, add the
  next chunk".
- **Chunk size is about 4 counts, not a whole eight.** Repeat a chunk before moving on,
  give chunks nicknames, and call steps with sound cues ("step, snap, slide, pose")
  ([Dance Teacher Web 2025](https://www.danceteacherweb.com/articles/blog/2025/7/13/creative-ways-to-teach-choreography-and-improve-retention/)).
  Tie steps to detailed counts, name the moves, and teach feet first
  ([Dance Teacher 2017](https://dance-teacher.com/making-it-stick/)). Detailed passages
  are counted "1-e-&-a" ([CLI Studios](https://www.clistudios.com/dance-blog/training/how-to-pick-up-choreography/)).
  So a step is sometimes half a count or less, usually 1–2 counts. Our site's own rule
  (DESIGN §11) already bans "8 counts at a time" as a fixed unit.
- **Dancers remember movement in chunks, and the chunks change with practice.** Steps
  group into phrases and phrases into sections, and each run-through regroups them
  ([Stevens et al., choreographic cognition](https://ausdance.org.au/articles/details/choreographic-cognition);
  [Acta Psychologica 2019](https://www.sciencedirect.com/science/article/pii/S0001691818300131)).
  Experts' memory units follow the movement's mechanics and novices' do not
  ([Bläsing et al. 2009](https://www.sciencedirect.com/science/article/abs/pii/S1469029208000885)).
  **Design consequence:** the learner must be able to re-cut steps. Our cuts are a
  starting point, not the answer.
- **Where people put boundaries.** Viewers split dance where the direction, pose,
  position or speed changes. Expert boundaries hold only within the expert's own genre
  ([Di Nota et al. 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7559184/)). Those are
  the two cues the prototype uses.
- **Marking.** Doing a phrase smaller, or only partly, is a way of rehearsing its
  timing and order ([Kirsh](https://adrenaline.ucsd.edu/kirsh/Articles/Marking_In_Dance/MarkingInDance.pdf)).
  It is worth one line of copy in the step card ("mark it small first").
- **Mirroring.** A teacher facing the class says "right" and moves their left, so
  beginners don't have to flip sides in their heads
  ([Dance Teacher on left vs right](https://dance-teacher.com/left-vs-right/)). We have a
  Mirror toggle. Cues must therefore say *the dancer's* left, and the UI flips the word
  when Mirror is on.
- **Slow first, then tempo.** Slow-motion, real-time and mixed demo speeds all led to
  learning, with no difference between them
  ([Hum. Mov. Sci., PubMed 33421652](https://pubmed.ncbi.nlm.nih.gov/33421652/)). So
  slowing down is a comfort tool, not the method. Build up to full speed has to be part
  of the flow, not an optional extra.
- **What learners asked for.** A CHI 2026 study on accessible dance instruction found
  learners want learning in stages and descriptions that say *what* to do (mechanics,
  location, orientation) and *how* (speed, fluidity, timing)
  ([Das et al.](https://arxiv.org/abs/2511.09658)). Another study had 30 choreographers
  define what makes choreography complex. Simplified versions reduced novices' workload
  and helped them perform better ([Han et al. 2026](https://arxiv.org/abs/2604.10490)).
  That is a possible later "easy version" layer.
- **Common corrections.** Levels (how high or low), timing, isolations and shoulder
  tension ([Dance Teacher hip-hop guide](https://dance-teacher.com/a-dance-teachers-guide-to-hip-hop/)).
  "Late on the beat", "wrong foot" and "finish the move" are folk knowledge. I found no
  good source for them.

**How products do it**

| product | unit | what it shows | auto-segmented? |
|---|---|---|---|
| STEEZY ([help](https://steezy.zendesk.com/hc/en-us/articles/360052412431-Taking-a-Class)) | instructor-made sections | mirror, speed, loop any range, front/back camera, webcam beside the instructor (web) | no, the sections are made by hand, and how isn't documented |
| YouTube tutorials ([example](https://www.youtube.com/watch?v=HDBgY6Znhrc)) | one 8-count at a time, counted out loud | "slow + mirrored + counts", then full speed | no |
| Just Dance ([pictograms](https://justdance.fandom.com/wiki/Pictogram), [Gold Moves](https://justdance.fandom.com/wiki/Gold_Move)) | one pictogram per move, a few "Gold Moves" | a pictogram of the upcoming move, hit-or-miss scoring | authored by hand |
| LearnThatDance, UIST 2023 ([1](https://dl.acm.org/doi/10.1145/3586182.3615801), [2](https://dl.acm.org/doi/10.1145/3586182.3625119)) | chunks from music + pose | an automatic lesson plan, mirrored webcam, record and review, a sister demo with an LLM coach | **yes**, the closest prior work. We only saw the abstracts |
| Consumer "AI coach" apps (for example [Dance Buddy](https://apps.apple.com/us/app/dance-buddy-learn-any-dance/id6752668955), [DanceBetter](https://dancebetter.org/)) | not stated | webcam or upload comparison | unverified claims |

Nobody we found auto-cuts steps from a 3D reconstruction. STEEZY's sections are
human-made, and its product value is mirror, loop and speed, which we already have.

## 2. Deriving steps from our data

**State of the art, and what is cheap for us**

| approach | examples | cost to us | verdict |
|---|---|---|---|
| Kinematic cuts: velocity minima and direction changes | AIST++'s "kinematic beats" are local minima of velocity and the basis of the Beat Alignment Score ([Li et al. ICCV 2021](https://arxiv.org/abs/2101.08779)); [unsupervised skeleton segmentation 2025](https://arxiv.org/pdf/2508.04513) | numpy/TS over the existing MotionResult | **v0** |
| Key-pose anchors | Lodge's "characteristic dance primitives" ([CVPR 2024](https://arxiv.org/abs/2403.10518)); key-pose summaries ([ICCV 2021](https://openaccess.thecvf.com/content/ICCV2021/papers/Hu_Unsupervised_3D_Pose_Estimation_for_Hierarchical_Dance_Video_Recognition_ICCV_2021_paper.pdf)) | same | the pose at each cut is our key pose, free |
| Music-structured units | ChoreoMaster works in phrases and assumes 4-beat bars ([TOG 2021](https://dl.acm.org/doi/abs/10.1145/3450626.3459932)); Bailando's dance-unit codebook ([CVPR 2022](https://arxiv.org/abs/2203.13055)); EDGE ([CVPR 2023](https://arxiv.org/abs/2211.10658)); FineDance ([ICCV 2023](https://arxiv.org/abs/2212.03741)); OpenDance's 4 s phrases ([2025](https://arxiv.org/abs/2506.07565)) | generative models, a GPU | the idea is useful (cut on the grid), the models are not needed |
| Grounded text from 3D motion without training | **MotionScript** "posecodes/motioncodes" ([IROS 2025](https://arxiv.org/abs/2312.12634), [code](https://pjyazdian.github.io/MotionScript)); PoseScript/PoseFix pose and correction text ([ECCV 2022](https://github.com/naver/posescript), [ICCV 2023](https://arxiv.org/abs/2309.08480)) | CPU, rules | **the pattern for our feature vocabulary** |
| Learned motion↔text | TMR retrieval ([ICCV 2023](https://arxiv.org/abs/2305.00976)); MotionGPT ([NeurIPS 2023](https://github.com/OpenMotionLab/MotionGPT)); MotionLLM ([2024](https://arxiv.org/abs/2405.20340)); FineMotion ([2025](https://arxiv.org/abs/2507.19850)) | a GPU, SMPL retargeting from MHR | not now. The captions are generic ("a person waves") and can't be checked against our features |
| Coaching text from comparing a learner to a reference | CoachMe ([ACL 2025](https://arxiv.org/abs/2509.11698)); PoseForge, LLM feedback grounded in numbers ([VIS 2026](https://arxiv.org/abs/2608.05971)) | needs learner pose | v2 reference |

**What the prototype does** (`segment.py`, numpy only, about 1 s per lesson):

1. **Forward kinematics** over the contract's joint rotations, the same math as
   `apps/web/lib/footContact.ts`. The public result documents carry rotations plus the
   root trajectory, and positions come out of the FK. That gives five tips (wrists,
   balls of the feet, head) plus the pelvis.
2. **The dancer's own frame.** Right = the vector from left hip to right hip on the
   floor plane. Forward = up × right. Up = the grounded floor normal. Yaw comes from
   forward, so turns are measured as well as travel and level changes.
3. **An energy curve.** The sum of the tips' speeds relative to the body, plus 2× the
   pelvis speed. It is masked where a tip is `absent`.
4. **Cut cues for each sample.** (a) A *stop*: a local energy minimum, scored by how
   far it dips below the surrounding peaks. (b) A *change*: 1 − cos between the
   whole-body velocity pattern (all five tips as one 15-dimensional vector) just before
   and just after. Measuring each limb separately fired on every half-beat, because some
   limb is always reversing. The whole-body version is what made the cues selective.
5. **Place the cuts.** Each **half-beat** of the proposed grid gets the best cue within
   ±¼ count. A dynamic program then picks cuts that maximise the summed cue, minus a
   fixed cost per cut and a length penalty. Steps can be 0.25 s to 4 counts long. The
   preferred length is 1 count, or 2 counts above about 133 BPM.
6. **Chunks.** Close a chunk at the first cut at least 3 counts in that lands on count
   1 or 5, or on the "and" right after. Close it anyway past 6 counts.
7. **Features for each step.** The 1–2 leading body parts (by path length in the body
   frame). Each leader's direction at its furthest point, with "and back" if it returns.
   Travel, turn and drop/rise, claimed only where the pelvis was tracked. Quality is
   ranked *within this dance*: "small / hold", "sharp (hits and stops)", "smooth / even".
   A fixed threshold did not transfer between clips. Also recorded: `uncertain_parts`
   (a leading tip less than 50% `observed` during the step) and cut clarity.

**Results** (the full tables are in `tools/research/step_segments/out/steps.md`):

| lesson | BPM | steps | step lengths (half-beats: count) | chunks | how the cuts looked in the viewer |
|---|---|---|---|---|---|
| choreo `345b` (studio, well lit) | 104 | 72 | 1: 26, 2: 42, 3: 4 | 14 | **Good.** The frames at cuts are set poses, and the frames between are motion-blurred. Most cuts land on the "and" (see below). The first chunk includes the lead-in before count 1. |
| bhangra `5716` | 95 | 103 | 1: 66, 2: 33, 3: 3, 8: 1 | 18 | **Good shape, off-grid phase.** The knee-lift hops land on the "and" of the proposed grid, which is the half-beat grid error we already know about ([downbeat-models.md](downbeat-models.md)). The first 3.5 s of walking in became one "step" ("travel back 3.8 m"). |
| a106 (night, dark) | 113 | 33 | 1: 18, 2: 15 | 7 | **Plausible, too fine for a beginner.** The hits on 5, 6 and 7 are correct key poses, but half-count steps everywhere are more than a teacher would start with. |
| b822 | 152 | 24 | 2: 10, 3: 7, 4: 5, 5–6: 2 | 7 | **Plausible after the tempo fix.** For example 1–2, 2–4, 4–5. A teacher would probably split 2–4 at 3. |
| 7995 | 152 | 19 | 2: 5, 3: 7, 4: 7 | 6 | Before the tempo fix, almost every half-beat was a cut (noise). After it, the steps are 1–2 counts. |

Judged by looking at the frames on every half-beat of a chunk, with cut frames
outlined, in `out/viewer.html` in the Claude browser. This is not a user study. The
honest summary: **the cut *positions* are usable as a starting point, the direction
text is noisy, and the step *granularity* is the weakest part.** That is why the design
makes merge and split one tap each.

**Findings that matter beyond this feature**

- ~~**Motion can check the count grid.**~~ Of the step ends in each lesson, 54/103
  (bhangra), 45/72 (choreo), 13/24 (b822) and 9/19 (7995) land on an "and".
  **Superseded in round 2 (§9).** The grid in these documents is already Beat This!
  (only the `model_report` label is stale). With hits timed properly, the visible hits
  sit on the counts *and* the "and"s, 7–28 ms after the grid. So a half-beat cut is
  normal for these dances. It is not a grid error and not an A/V offset.
- **15 fps limits resolution below one count.** At 152 BPM, half a count is 0.2 s, which
  is 3 samples. Steps shorter than about 0.25 s are noise at our sample rate. Half-count
  steps are only trustworthy below about 120 BPM unless the pipeline samples at 30 fps.
- The public documents don't include `joints_3d`. Clients must do FK, which is cheap:
  127 joints × 700 samples in numpy takes milliseconds.

## 3. Language cues from features (v1)

**Can an LLM write useful teacher-style cues from structured features?** Yes, for the
*vocabulary* part ("right leg out to their right, left arm up", "drop and up", "sharp").
MotionScript shows that rule-based descriptions of 3D motion are readable, and an LLM
mainly makes them read like speech. It cannot supply what the features don't carry: the
name of a move ("body roll", "Harlem shake"), style, or intent. The prompt forbids
naming moves unless the features imply them.

**Prototype** (`cue_prompt.py`). No `ANTHROPIC_API_KEY` was set, so no call was made. The
exact request we would send is in `out/cue_request.json` (choreo, chunk 2). It uses:

- `claude-sonnet-5`, `output_config.effort: "low"`, structured output (a JSON schema:
  `step`, `cue`, `grounded_in[]`), and a system prompt with the grounding rules. The
  rules: the dancer's left/right only; no move names unless implied; skip detail on
  `uncertain_parts`; an empty cue beats a guess; at most 8 words.
- Input for each step is only `counts, lead, moves, whole_body, quality, uncertain_parts`.
  Example:
  `{"step": 11, "counts": "6&–7&", "lead": ["right leg","right arm"], "moves": ["right leg to their right and back", "right arm down"], "whole_body": [], "quality": "—", "uncertain_parts": []}`
- **A post-check on every cue** (`ungrounded()`, with a self-check). Each body-part,
  side, direction, turn, level and quality word in the cue must appear in that step's
  features, or the cue is dropped. For example "right arm up" on a left-arm step is
  dropped, and so are "spin" or "drop" with no turn or level feature. This is the
  mechanical form of §7h: the model can phrase things, it can't add facts.

**Honesty (DESIGN §7h) in the UI.** Label each cue as a suggestion ("Suggested from the
3D. Edit it if you call it something else."). Show no cue where the check dropped it or
the features were thin. Always offer Rename, and a learner's name always wins over
ours, just as authored counts do. Say "their right" by default and flip it with Mirror.
Never describe an `uncertain` or `absent` part, which follows the existing uncertainty
language.

**Hallucination risks, with their fixes:**

| risk | fix |
|---|---|
| Invented move names | forbid them in the prompt, and allow move names only from the learner |
| Left/right flipped | feature text is always from the dancer's side, and the validator catches side words |
| Describing the occluded body | send `uncertain_parts` in the input and keep the prompt rule |
| Our features being wrong, since the directions are noisy | the post-check can't catch this. Fix it with v0 editing plus a "this cue is wrong" tap (analytics), and measure before trusting it |
| Numbers sounding like facts ("turn 168°") | round to plain words ("half turn"), never send degrees to the UI |

**Keyframe images.** Optional and **not recommended for v1**. Frames at each cut would
improve move naming. But they send the dancer's image to a third-party API, which
`docs/legal/rights-and-privacy.md` would have to cover, and the gain is in exactly the
area we can't verify (names). Revisit only if v1 cues prove too generic.

**Cost.** Estimated from the request size, not measured. A lesson has about 20–100
steps at about 60–80 input tokens each, plus a 350-token system prompt, so about
2–8k input tokens. Output is about 20 tokens per cue, plus low-effort thinking.

| model (per MTok in/out) | per lesson | notes |
|---|---|---|
| Claude Haiku 4.5 ($1/$5) | ≈ $0.005–0.02 | worth an A/B. It may follow the grounding rules less well |
| **Claude Sonnet 5 ($2/$10)** | **≈ $0.02–0.05** | recommended |
| Claude Opus 5.5 ($4/$20) | ≈ $0.04–0.10 | not needed for 8-word cues |
| (the GPU pipeline itself, from `model_report`) | ≈ $0.13 | for scale |

Make one call per lesson (all chunks), cached with the job's result. Run it after
segmentation at the end of the pipeline, or lazily on the first "Learn it in steps".
Latency hasn't been measured. A single low-effort call is expected to take a few
seconds, so the flow must work fully before the cues arrive. When a learner edits
steps, the cues for edited steps are dropped, not regenerated. Regenerating is v1.1.

## 4. Design recommendation

**Name.** DESIGN §11 already uses "step by step" as the product's promise. Call the mode
**"Learn it in steps"** (button) and "guided" internally, so the tagline does not look
like a mode you can switch off.

**Entry point.** From any loop or part that the learner has selected in free practice, a
card below the transport says: "Learn this in steps. We found 7 places this loop could
split. You can change them." [Start: step 1 of 7]. With no loop selected, it offers the
current part. Free practice is untouched. Guided mode is a layer on the same page and
state, and "Exit to free practice" is always visible.

**The flow** (a path of chips at the top shows where you are):

```
step 1 → step 2 → (1+2) → step 3 → (1–3) → … → chunk at 0.5× → Build up to 1× → next chunk → (chunk 1 + chunk 2)
```

- **Step card:** large counts ("1& – 2"), the cue if there is one, a suggestion label,
  and Rename / Split / Merge with next / Skip. The loop is set to exactly this step, at
  the learner's chosen speed (default 0.5×). The 3D view defaults to the camera angle,
  and the learner can pick side or top as today, labelled "estimated" as today.
  [Watch again] [Got it · next].
- **Put it together:** loop steps 1..n at the same speed. After 4 loops it asks rather
  than advancing on its own ("Got it" / "Again").
- **Chunk at speed:** turn on the existing **Build up** (0.5 → 0.75 → 1×) with the
  **metronome** available. Then "Add the next chunk". The next chunk's steps run the
  same way, then the two chunks are joined.
- Nothing is locked. Every chip can be tapped, and you can skip anywhere. Later chunks
  are only *suggested* once the earlier chunk has been looped at speed.
- **Phone:** the two stages stay as they are, the step card sits above the transport,
  and "Got it · next" is the ≥88px primary button in thumb reach. **Desktop:** a steps
  rail replaces the parts rail while in guided mode, with keys N (next), B (back),
  E (edit cue) and space.

A wireframe is in `tools/research/step_segments/mockup.html`: entry, phone step card,
combine, chunk at speed, and the desktop rail. It was checked at phone and desktop widths
in the Claude browser.

**What the learner can edit.** Merge, split (at the playhead, snapped to the nearest
half-beat), rename (the learner's text replaces the cue), skip. Chunk boundaries can be
dragged to any step boundary. The edits reuse the authored-counts model:
machine-proposed steps are a starting point, and **the first human edit freezes them**.
They are never re-proposed.

**Storage.**
- *Machine proposal* (step times, features, cues) is derived from the video. It belongs
  with the job's server artifacts, computed on the client in v0 and cached in the result
  in v1, so the D6/D7 deletion path covers it.
- *Learner edits* (cut times, names, progress) go in localStorage next to
  `stepwise.lesson-structure.v1.*`, as `stepwise.lesson-steps.v1.<lesson>`, through the
  same `load`/`save` seam in `apps/web/lib/structure.ts`. Keep them to times plus the
  learner's own words. **Do not copy machine features or cues into the local blob.**
  `structure.ts`'s retention note says person-derived data there would fall outside the
  deletion promise.
- *Shareable later* (after D5 accounts): a steps layer on a shared lesson link, like
  shared parts.

**Analytics** (add to `EVENTS` in `apps/web/lib/analytics.ts`):

- `guided_started {steps, counts, source: loop|part}`
- `guided_advanced {kind: step|combine|chunk|buildup, index, loops, speed}`
- `guided_step_edited {action: split|merge|rename|skip}`
- `guided_chunk_done {at_speed: bool}`
- `guided_exited {at: index, of: total}`
- v1 adds `cue_edited` and `cue_flagged`

The question to answer from these: do people who start a guided run reach "chunk at
speed" more often than free-practice users loop the same part at 1×? And how many cuts
do they edit? The edit rate is our label set for tuning the segmenter.

## 5. Phased plan

| phase | what | effort | depends on |
|---|---|---|---|
| **v0: steps, no LLM** | Port `segment.py` to TS in `apps/web/lib/steps.ts`, reusing `footContact.ts` FK. That is about 300 lines plus a synthetic self-check. Add the guided layer: step card, path chips, desktop rail, combine/chunk states on the existing loop, speed, Build up and metronome. Add editing and local storage, and the analytics events. Before shipping: add the "not dancing yet" trim (skip leading and trailing spans with travel but low body-relative energy), and the tempo-aware minimum step length (done in the prototype). | **≈ 2 weeks** (algorithm 2–3 days, UI 5–6 days, edit/storage 2 days, QA on the 5 lessons plus fixtures 1–2 days) | nothing new; works on all existing lessons client-side |
| **v0.1** | Re-run on Beat This! grids and check A/V sync, as §2 flags. If motion and grid disagree on phase, feed that into "try another 1". | 2–3 days | Beat This! rollout |
| **v1: cues** | Server route: segment in the pipeline (Python, the prototype as-is), one Sonnet 5 call per lesson, the `ungrounded()` validator, results stored with the job. UI: the cue line with its suggestion label, Rename wins. Build an eval of about 50 hand-labelled steps across 5+ genres, measuring the grounded rate and "would a teacher say this" (see the `claude-api` skill's build-eval). | **≈ 1–1.5 weeks** | v0 usage showing people reach step cards |
| **v2: pose-match feedback** | Webcam pose in the browser (MediaPipe/RTMPose-class), aligned to the reference 3D per step, giving per-step "timing early/late" and "arm lower than reference" (PoseFix/CoachMe-style text from measured differences). | **≈ 4–6 weeks**, research-heavy | v0/v1 data; see the privacy notes below |

**v2 privacy.** Today the site stores no learner video and has no accounts. Webcam
feedback must run **entirely on the device**: frames never leave the browser, and
nothing is stored except a per-step score kept in localStorage if the learner wants it.
The copy must say that as a mechanism ("Your camera stays on this device. Nothing is
uploaded."), and the code must make it true (§7h: describe the mechanism, not a
guarantee). The camera permission prompt only appears on an explicit "Check me"
tap, never on page load. Accuracy claims need the same care as the 3D: a monocular
webcam pose is weaker than our reference, and back-facing moves (DESIGN §7h case 1) can't
be scored from a front camera. Those steps should say "can't check this one from the
front".

---

# Round 2

## 6. UI plan

**Principles** (the owner asked for guided mode not to feel crowded; every layout below
was scored against these):

1. **Progressive disclosure.** Show only the current step and one primary action.
   Editing (split, merge, rename, nudge, detail level) and step details sit behind one
   secondary control. They are never on screen by default.
2. **One primary action per state.** "Got it · next", "Put it together", "Speed up",
   "Next chunk": each state has exactly one filled button.
3. **The dancer is the hero.** Video and 3D keep their space. Guided mode takes the
   least space that works, and mostly *replaces* free-practice controls rather than
   adding to them.
4. **No more controls on screen than free practice has today.** The counts are in the
   table below.
5. **Generous spacing and touch targets of 44px or more on phone.** The site's larger
   targets stay where they already are.
6. **Same look.** Use the `front.css` / `lesson.css` tokens and the existing tiles, count
   band and speed panel. No new colours, and the accent is still the only accent.
7. **Hide rather than shrink** when space is short, especially at 844×390.

**Mockups.** Serve `tools/research/step_segments/` (`python3 -m http.server`) and open
`mockups/index.html` for the layout comparison and density table, then
`mockups/guided.html` (layout A) at 1440×900, 390×844 and 844×390.
`guided.html?layout=b` and `?layout=c` are the alternatives. The dashed "Mockup state"
menu jumps to any of the 20 states. It is review chrome, not part of the design. The
mockups use real bhangra data from `out/steps.json`: steps at all three levels, the
lead-in and outro, and a low-confidence cut. The cue text is hand-tidied in the v1
style.

**Three layouts, scored on density.** The table shows visible controls / text lines in
the step-card state, counted by `window.density()` in `guided.html`. It was run on the
live page as well as the mockups.

| | desktop 1440×900 | phone 390×844 | phone 844×390 | covers dancer |
|---|---|---|---|---|
| Live free practice today | 37 / 25 | 32 / 19 | 30 / 18 | — |
| Mockup free practice (baseline) | 28 / 28 | 22 / 18 | 19 / 18 | — |
| **A. Step card docked under the stages** | **22 / 37 (−6 / +9)** | **16 / 24 (−6 / +6)** | **13 / 23 (−6 / +5)** | no |
| B. Step list is the guided UI | 33 / 58 (+5 / +30) | 22 / 33 (0 / +15) | 16 / 24 | no, but the stages lose 400 px of width or 130 px of height |
| C. Steps on the band, floating card | 22 / 35 | 16 / 26 | 13 / 22 | yes: 12% on desktop, 31–48% on phone |

**Pick: A.** It is the calmest layout that still makes the flow obvious. It has the
fewest controls (tied with C) and never covers the dancer. Its single button says what
happens next ("Got it · put 1–2 together"). Applied to the live page, guided A has
fewer controls than free practice today at every size: about 31, 26 and 24. It adds
5–9 short text lines: the chunk and step, the counts, the cue, and "Suggested from the
3D". It fits the no-scroll rule in all 20 states at all three sizes. The phone's primary
button is 88 px or taller.

**How it fits the page:**
- **Stages.** Unchanged grid. On desktop they are 555 px tall in guided mode (694 in
  free practice). A phone on its side is unchanged.
- **Count band.** Follows the current chunk, with a thin step bar underneath: the
  current step filled, and an unclear cut drawn as a ring. While guided it is a readout,
  not 8 loop buttons, because the guide sets the loop. That is where most of the −6
  controls come from.
- **Step card (the dock).**
  - Desktop: above the transport, with the chunk, a dot path, the counts, the cue,
    Steps, Exit and one button.
  - Phone upright: above the transport, with an 88 px button.
  - Phone on its side: in the right rail, with the text on the left and the button on
    the right.
- **Speed panel and Build up.** The same pills. Steps and "put it together" play at
  0.5×. "At speed" turns Build up on (0.5× → 1×), shows its meter, and offers Click (the
  metronome).
- **Timeline.** Adds a chunk band under the track (current chunk in ink, done ones
  grey), ticks for the current chunk's steps, and hatched **not-dancing** regions.
- **More menu.** A new first group: "Learn it in steps", or Resume / Start over.

**Flow.** Step → *Got it · next step* → put 1–2 together → step 3 → put 1–3 together →
… → chunk at speed with Build up → next chunk → join the chunks. "Put it together"
loops 4 times, then waits ("Press play to go again"). Nothing is locked.

**Entry and discoverability:**
- A quiet link in the timeline hint on first visit: "…or learn it in steps".
- "Learn this loop in steps" when a loop is selected.
- "Learn it in steps" in More.
- No pop-up and no auto-start.

**Editing and details (progressive disclosure).** One **Steps** button opens a panel on
desktop or a sheet on phone. It holds:
- rename (the learner's words replace the suggested cue)
- split at the playhead (snaps to a half-beat)
- merge with next
- nudge a cut by ± half a count
- skip
- the detail level (Beginner / Intermediate / Advanced)
- the full step list
- "Include this" for a not-dancing region

Changing the level re-cuts only the steps the learner hasn't edited.

**Progress, resume and exit.** "Exit" returns to free practice, with the current loop set
to the step or chunk you were on. The More menu and the lesson then offer "Resume at step
4 of chunk 2". Progress is per browser, next to the authored counts.

**Empty and uncertain states:**
- *Low-confidence cut:* "This split is a guess — the move doesn't stop here."
- *Uncertain body part:* uses the §4 uncertainty language, and the cue skips that part.
- *No cue:* shows the counts only, plus "Name this step".
- *Not dancing:* a hatched region, "Dance starts at 0:04.5", and "Include this".
- *No steps in this loop:* "No clear steps here. Try the whole loop, or a longer one."
- *Advanced with no fast evidence:* "No quarter-count hits found in this chunk."

**Not verified:** real playback, real touch on devices, and the performance of the
extra timeline layers. The mockup stages are drawn placeholders.

## 7. Dancing vs not dancing

**What it catches.** People walk back from the phone, stand, and set up before the music
starts (bhangra's first 4.5 s). They walk off at the end, or the clip runs past the
music. Guided mode must not make "walk to your spot" step 1. Free-practice loops
shouldn't default to it either.

**Signals, per count** (`idle_counts()` in `segment.py`). Every signal is relative to
*this* dance's own level, because a fixed threshold didn't transfer between clips:

| signal | measured as | used? |
|---|---|---|
| limb motion | body-relative speed of the wrists, feet and head, divided by the dance's 75th percentile | yes |
| travel | pelvis speed, m/s | yes. Walking is limb < 0.5 with pelvis > 0.6 m/s |
| stillness | limb < 0.35 with pelvis < 0.6 m/s | yes |
| music present | audio RMS divided by its median, < 0.2 means no music | yes |
| in frame | share of samples with every limb tip not `absent` | yes, < 0.5 means not in frame |
| beat lock | share of limb-energy variance at the beat or half-beat frequency, over ±2 counts | **measured, not used.** It separates walking from dancing on bhangra (median 0.26 dancing vs 0.08 idle) but not on the others (7995: 0.11 vs 0.26) |

**Rules.**
- The dance starts at the first **two** dancing counts in a row, and ends at the last two.
- An edge is trimmed on motion alone (walking or still) only when there are 2 or more
  such counts. b822 opens with a travelling side step that one count of "walking"
  would have cut.
- "No music" and "not in frame" trim on their own.
- Inside the dance, only a run of 4 or more idle counts is a *pause*. Anything shorter
  is a hold, and holds are choreography.

**Results** (checked against frames in the viewer):

| lesson | detected | verdict |
|---|---|---|
| bhangra | lead-in 0–4.47 s (not in frame, walking, still), outro 46.8–48.0 s (walking, no music) | **Right.** He walks back from the phone until about 3.8 s and starts on the next count. We cut at most one count late. The outro is the walk-off. |
| choreo | outro 34.18–35.9 s (still, no music) | **Right to within a count.** The final pose is held from about 33.6 s, and the last "step" is hitting it. |
| b822 | none (after the 2-count guard) | **Right.** Before the guard, 0–0.69 s was a false "walking" trim. |
| a106 | outro 12.67–13.2 s (no music) | right |
| 7995 | none | right. The mid-dance "walking" counts at 5.5–5.9 s are a travelling move and are correctly kept |

There were no mid-dance pauses in these clips. The 2-count stillness at bhangra 18.4–19.0 s
is correctly treated as a hold.

**How it's shown** (mockups in §6):
- The timeline greys the idle region, labelled "Not dancing".
- The lesson says "Dance starts at 0:04.5" once, in the count band's caption.
- Default loops, guided mode and "play all" start at the dance start.
- Override: tapping the grey region offers **"Include this"**, which is stored like an
  authored count edit and wins from then on. There is also a "Start the dance here" at
  the playhead.
- We never delete or hide the video. We only change where the default loops start.

## 8. Step length: detail levels

**Round 1's weakness:** one fixed granularity, with 72 steps on choreo and 36% of them
half a count. That is too fine for a beginner and too coarse for someone who wants
the hits.

**What changed** (`analyse()` in `segment.py`):
1. **Candidates are quarter-beats.** Each quarter-beat's metrical position is recorded:
   count 1 or 5, other counts, "and", or "e"/"a". Its evidence is the best stop or
   direction-change cue within ±¼ count, and an audio percussive accent within ±40 ms
   multiplies it by up to ×1.3. The accent strengthens a cut the motion already supports.
   It never makes a cut on its own.
2. **Cuts are nested, coarse to fine.**
   - Beginner cuts first, on counts only.
   - Intermediate re-cuts only *inside* beginner steps, on counts and "and"s.
   - Advanced re-cuts inside intermediate steps and may add "e"/"a", but only where
     §10's fast test passes.

   So the tree is phrase → chunk → step → sub-step, and switching the detail level
   never moves a coarser cut.
3. **The cost of a cut is set by the dance itself.** It is a quantile of that level's
   candidate scores: 0.65 for beginner, 0.50 for intermediate, 0.40 for advanced. With a
   fixed cost, every count scored "some stop", and every level cut on every count.
4. **Length targets:**
   - Beginner: 1–3 counts. It prefers 2 counts at 110 BPM and above, and 1 count below.
   - Intermediate: ½–2 counts, preferring 1.
   - Advanced: ¼–1 count, preferring ½.
   - Minimum lengths are 0.30, 0.25 and 0.12 s.
5. **One continuous gesture stays one step.** If nothing inside a parent step beats the
   cost, the parent is kept whole at the finer level. On choreo, 34 of 43 beginner steps
   stay whole at intermediate. On bhangra it's 39 of 48.

**Measured.** This is not ground truth, which would need a teacher-labelled set. "In
range" is the share of steps inside the teacher range for that level: 1–2 counts for
beginner, ½–1 for intermediate, ¼–1 for advanced.

| lesson (BPM) | beginner: steps · median · in range | intermediate | advanced | round 1 (one level) |
|---|---|---|---|---|
| bhangra (95) | 48 · 1 count · 83% | 57 · 1 · 75% | 123 · ½ · 100% | 103 steps, 64% half-count |
| choreo (104) | 43 · 1 · 86% | 58 · 1 · 83% | 110 · ½ · 100% | 72 steps, 36% half-count |
| b822 (152) | 16 · 2 · 62% | 32 · 1 · 81% | 68 · ½ · 100% | 24 |
| a106 (113) | 9 · 3 · 33% | 20 · 1 · 70% | 44 · ½ · 100% | 33 |
| 7995 (152) | 13 · 2 · 62% | 26 · 1 · 69% | 59 · ½ · 100% | 19 |

Beginner is now a sensible default on four of five lessons. a106 is the outlier: it has
constant motion with few clear stops on counts, so beginner steps are mostly 3 counts.
There the learner should step down to Intermediate, and the UI offers that when a step
is longer than 2 counts. Advanced is always "in range" because its limits force it.
Whether its half-count cuts are *good* cuts still needs the teacher-labelled set (§11).
The full nested tables are in `out/steps.md`, and the viewer has a level picker.

**Recommended defaults:**
- Beginner for everyone the first time.
- Remember the level the learner picks, per browser.
- Offer "More detail" on any step longer than 2 counts, and "Fewer steps" when a chunk
  has more than 6 steps.

## 9. Count grid and A/V sync (re-check of the "cuts land on the and" finding)

- **The grid was already Beat This!** I ran the production `propose_grid`
  (`packages/beat-detect`, `audio.py`) on each video. Count 1 and tempo match the live
  documents to the millisecond on all five. Only the `model_report` still says
  `librosa.beat_track`. That label is stale and worth fixing separately. So the round-1
  finding was already on the new grid.
- **The hit detector was late, not the grid.** At native fps (`video2d.py`, 30 or 60 fps),
  frame differences inside the dancer's box are strongly periodic. Round 2 first timed
  a "hit" at the energy minimum *after* braking, and that sat a steady ⅛ count late on
  every clip. The body is already still by then. Timed at the moment of hardest
  braking, the hits line up with the grid:

| lesson | hits near a count / near an "and" | median offset from nearest half-beat | 3D vs video frames |
|---|---|---|---|
| bhangra | 60 / 46 | +28 ms | −25 ms |
| choreo | 41 / 32 | +15 ms | −45 ms |
| b822 | 9 / 15 | +7 ms | −20 ms |
| a106 | 36 / 24 | +13 ms | −50 ms |
| 7995 | 7 / 13 | −16 ms | −30 ms |

- **Reading it:**
  - Visible hits sit on the counts and the "and"s within one video frame (33 ms).
    The median lag of +7 to +28 ms includes the dancer's own timing, so **there is no
    A/V offset worth correcting.**
  - These are half-beat dances, so about half of all cuts landing on an "and" is
    correct. It is not an error.
  - The 3D timeline leads the video frames by 20–50 ms on all five clips (the
    correlation of the two energies peaks there). That is less than one 15 fps sample,
    but the sign is consistent. It could be a real one-frame offset in
    `sample_times_s`, or an artefact of comparing a central difference with a frame
    difference. **Low-priority check:** it doesn't move any cut, which snaps to a
    half-beat with ±¼ count slop.
- **What didn't work:**
  - Correlating the whole audio onset envelope with visible hits gives weak,
    inconsistent lags (r ≤ 0.17), because onsets are far denser than hits.
  - Hand contacts (claps) gave only 1–4 events per clip.
  - A beat-frequency "groove phase" of the pelvis height was too weak to use
    (strength ≤ 0.2).

  For a real sync check, film one clip with a slate clap.

## 10. Sub-beat steps (fast, pro choreography)

**How teachers do it.**
- **16ths are counted "1-e-&-a"** ([Songtive](https://www.songtive.com/blog/how-do-you-count-rhythms-using-1-e-a-2-e-a/),
  [LibreTexts](https://human.libretexts.org/Courses/Sierra_College/Equipping_the_Musical_Ear/07%3A_Beat_Divisions/7.02%3A_Simple_Meter_Beat_Divisions/7.2.02%3A_Sixteenth_Notes)).
  Round 1 found the same advice for detailed choreography
  ([CLI Studios](https://www.clistudios.com/dance-blog/training/how-to-pick-up-choreography/)).
  For a syncopated passage, dancers either keep "1-e-&-a" running and do only the hits,
  or say only the syllables that have a sound.
- **Hit the drum part, one body part at a time.** In popping and animation, teachers
  map the drum kit to the body: kicks to chest hits, snares to arm ticks, hi-hats to
  finger twitches ([MyGrooveGuide](https://www.mygrooveguide.com/dance-info/popping/what-is-popping)).
  The learning order is: on the beat first, then specific sounds
  ([SF Conservatory](https://sfconservatoryofdance.org/blog/how-to-learn-hip-hop-dance/)).
  Tutting doesn't always follow the beat, but hits land on accents
  ([About World](https://www.aboutworld.us/what-is-tutting-dance/)).
- **What this means for the product:**
  - A sub-beat step is taught as *a rhythm first*: say "1-e-&-a", tap it, then add the
    body part.
  - Keep the speed at 0.5× or below. At 1×, four hits in one count go past too fast
    to see.
  - The step card shows the *rhythm* ("hits on 1, e, &, a") and the body part leading
    it. Our 3D can't describe the shapes at this speed, and the card must say so.

**What it takes technically:**

| source | resolution | cost | what it gives |
|---|---|---|---|
| 3D at 15 fps (today) | 67 ms per sample. A 16th at 150 BPM is 100 ms, about 1.5 samples | none | a sub-beat move is 1–2 samples. Timing below ½ count is unreliable and there are no shapes |
| **3D at 30 fps** | 33 ms | about **×2** GPU time and cost | see below |
| 3D at 60 fps | 17 ms | about ×4 | overkill for most clips |
| 3D only in the fast windows | 33 or 17 ms where needed | about +10% if 10% of the clip is fast | the GLB exporter derives fps from uniform `sample_times_s` spacing (`modal_app.py`), so non-uniform samples need a sidecar or a contract change |
| **2D frame differences at native fps** (`video2d.py`) | 33 ms (30 fps clips) or 17 ms (a106 is 60 fps) | CPU, seconds, no model | *when* a hit happens, not *which* limb. Noisy in the dark (a106) |
| 2D keypoints (RTMO) at native fps | 17–33 ms | RTMO is small next to SAM 3D Body, but not profiled | when a hit happens *and* which limb. The best next step |
| Audio percussive onsets (`audio.py`, librosa on the percussive part, 5.8 ms hop) | about 6 ms | CPU, free | where the music has 16ths. Onsets are dense (3–6 per second), so an onset alone proves nothing |

The 3D fps is set by `run_clip(fps=15.0)` in `services/motion-api/modal_app.py` on an
L40S at $1.95/h. From the five lessons' `measured_performance`: cost is about
$0.02 + $0.000235 per sample. That is $0.07–0.19 per lesson and 1.2–4 minutes of GPU
at 15 fps. **At 30 fps** that becomes about $0.12–0.36 and 2.5–8 minutes, and the
MotionResult and GLBs double in size (choreo would go from 13 MB to about 26 MB).

**The fused test** (`fast_counts()`, reported by `sync.py`). A count is "fast" when at
least 3 of its four 16th positions have a visible hit within ±1/16 count *and* at least
3 have an audio onset, with at least one hit on an "e" or "a". The chance level comes
from re-running the test with the hits shifted off the grid (200 shuffles):

| lesson | fast counts | chance (mean / 95th pct) | verdict |
|---|---|---|---|
| bhangra | 1 / 71 | 0.9 / 3 | at chance |
| choreo | 0 / 59 | 0.1 / 1 | none |
| b822 | 0 / 33 | 0 / 0 | none |
| a106 | 0 / 20 | 0 / 0 | none. But its 6.3–7.4 s passage *looks* like a quick arm sequence with a new pose each 16th in the frame sheet. The dark footage makes the frame differences too noisy to confirm it |
| 7995 | 0 / 27 | 0 / 0 | none |

A first, looser test counted a single hit plus a single onset near an "e" or "a". It
"found" 41 sub-beat points on bhangra. That was exactly chance: 33% of e/a positions
have a hit and 56% have an onset, and 0.33 × 0.56 = the 18% observed. So the strict
test is the one to keep.

**Honest conclusion:** these five clips are half-beat choreography. The owner's case
(four hits in one count) isn't in our test set, so the fused method is **unvalidated,
not disproven**. Before building it, collect 5–10 fast clips (popping, tutting,
animation, footwork) and label their hits by hand at 0.25× speed.

**Recommendation:**
- **Adaptive resolution.**
  - Half-beat detail everywhere the 3D supports it (v0).
  - Quarter-beat only in counts that pass the fused test, cut at the 2D hit times and
    labelled "fast — follow the video" (§8's `note`).
  - The 3D never describes a sub-beat shape.
- **Upgrade the hit source before raising fps.** RTMO keypoints at native fps give
  hit timing *and* the limb. It is cheap compared with the 3D pass and needs no contract
  change: it could be a sidecar like `detections.json`.
- **Raise the 3D to 30 fps only if** the labelled fast set shows learners need 3D
  *shapes* at sub-beat speed, not just timing. Even then, prefer a per-lesson opt-in
  ("Rebuild in more detail", about ×2 cost and wait) or fast windows over a global
  change.

## 11. Updated phased plan

| phase | scope | effort | sub-beat |
|---|---|---|---|
| **v0** | Guided mode UI per §6. Segmenter in TS (FK + cues + nested DP + chunks), about 450 lines plus a self-check. Not-dancing trim with override. Beginner/Intermediate/Advanced detail. Edits (split/merge/rename/nudge/level), progress and resume, analytics. All client-side on the existing MotionResult. The audio accent weight needs the onset envelope: either compute it client-side with the Web Audio API or skip it in v0 (it moves few cuts). | **≈ 3–3.5 weeks.** Algorithm 4–5 days; UI 8–10 days (step card, list, nested timeline, count band, three layouts); editing and storage 3 days; not-dancing 1–2 days; QA on 5 lessons, fixtures and three viewports 2–3 days | half-beat everywhere. Advanced = ½ count |
| **v0.1** | A teacher-labelled set: 10 clips, including 5 fast ones, cut at all three levels by a dance teacher. Tune the quantiles and length targets against it. Fix the stale `model_report` label. Check the 3D↔video 20–50 ms lead. | 1 week, plus the teacher's time | produces the data v1 needs |
| **v1** | Claude cues (round 1 §3). Pipeline sidecar with audio onsets and native-fps hits (RTMO keypoints at native fps if profiling says it's cheap; else frame differences). Quarter-beat sub-steps where the fused test passes, shown as rhythm-first cards. | **≈ 2–2.5 weeks** | quarter-beat via audio + 2D, timing only |
| **v1.x (conditional)** | Only if v0.1's fast set shows the 3D shapes are needed: a 30 fps reconstruction as a per-lesson opt-in or for detected fast windows. Needs the GLB exporter or contract to accept windows. | 1–2 weeks, plus about ×2 GPU per opted-in lesson | 3D shapes at sub-beat |
| **v2** | Webcam pose feedback, on-device only (round 1 §5) | 4–6 weeks | — |

**Risks:**
- **Default granularity is judged by eye, not labels.** v0.1's teacher set is the fix.
  Until then, the level control and one-tap merge/split carry it.
- **Direction text is noisy.** Keep it secondary on the step card (the mockups show the
  counts and the video first), and let cues arrive only in v1 with the grounding
  validator.
- **Not-dancing false trims** (b822 before the guard). A trim only changes where default
  loops start, never hides video, and "Include this" is one tap.
- **Dark or low-contrast clips** (a106) break frame-difference hits. RTMO keypoints are
  more robust.
- **UI weight.** Guided mode adds a list, a card and a nested timeline to a page that
  must never scroll. §6's layout keeps it inside the existing regions. It needs a
  real-device pass on 390×844 and 844×390 before build.
- **Scope creep into sub-beat** before the labelled fast set exists. Hold v1's
  quarter-beat until v0.1 data says it works.

## Files

- `tools/research/step_segments/segment.py`: the segmenter: kinematics, not-dancing, nested detail levels, chunks (`--check` runs the self-check)
- `tools/research/step_segments/fetch.sh`: downloads the 5 public MotionResults (and the videos, with `--video`) into `.cache/` (ignored)
- `tools/research/step_segments/audio.py`: the production Beat This! grid plus percussive onsets, run with `uv run --project ../../../packages/beat-detect/python python audio.py`
- `tools/research/step_segments/video2d.py`: native-fps frame-difference energy in the dancer's box (ffmpeg + numpy)
- `tools/research/step_segments/sync.py`: the grid, sync and fast-passage measurements in §9–§10. `claps.py` is the hand-contact attempt
- `tools/research/step_segments/out/steps.md`: per-lesson tables: level stats, then beginner steps with the intermediate and advanced cuts nested
- `tools/research/step_segments/out/steps.json`: the same data, used by the viewer and the cue prompt
- `tools/research/step_segments/out/viewer.html`: video, timeline (not-dancing, chunks, cuts, onsets, hits), a level picker, and frame sheets down to 16ths. Serve the `step_segments/` folder and open `out/viewer.html`, which uses `.cache/` videos
- `tools/research/step_segments/mockups/`: round-2 high-fidelity guided-mode mockups (§6)
- `tools/research/step_segments/cue_prompt.py` and `out/cue_request.json`: the v1 prompt, schema, grounding validator, and the request we would send
- `tools/research/step_segments/mockup.html`: wireframes for the guided mode
