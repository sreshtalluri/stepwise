# Guided step-by-step learning: research, prototype, design (2026-09-24)

**Short answer:** build it. v0 needs no model and no pipeline change. Cut each selected
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

- **Motion can check the count grid.** Of the step ends in each lesson, 54/103
  (bhangra), 45/72 (choreo), 13/24 (b822) and 9/19 (7995) land on an "and". Energy folded
  onto one count is stillest at about half a count after the count in choreo, 7995 and
  b822. The swing is small, only 5–13%. On bhangra this matches the known grid error.
  On choreo the grid was believed right. So either the style lands on the "and", or
  `sample_times_s` and the audio are offset. **Worth checking A/V sync on one clip
  before trusting any beat-aligned motion feature.** These documents were produced by
  the old librosa grid (`model_report`: `librosa.beat_track`). Re-run them after the Beat
  This! upgrade. If they still disagree, the body can vote on "try another 1".
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

## Files

- `tools/research/step_segments/segment.py`: the segmenter (`--check` runs the self-check)
- `tools/research/step_segments/fetch.sh`: downloads the 5 public MotionResults into `.cache/` (ignored)
- `tools/research/step_segments/out/steps.md`: the per-lesson tables (step, time, counts, leads, direction, whole body, quality, cut clarity, unsure)
- `tools/research/step_segments/out/steps.json`: the same data, used by the viewer and the cue prompt
- `tools/research/step_segments/out/viewer.html`: video, timeline and half-beat frame sheet for checking cuts (serve `out/` over http, since the video comes from the live API)
- `tools/research/step_segments/cue_prompt.py` and `out/cue_request.json`: the v1 prompt, schema, grounding validator, and the request we would send
- `tools/research/step_segments/mockup.html`: wireframes for the guided mode
