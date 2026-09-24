# Learned foot-contact / ground-plane models: survey, licensing verdict, recommendation

Branch: `research-contact-models` (off `w4-jobservice`). Research document only —
**nothing here is integrated, and no pipeline code was modified.** Written for the
agent building the geometric grounding solve on `grounding`.

Date: 2026-09-18.

**Intended end state (confirmed by the builder, 2026-09-18):** stepwise will be a
**public platform anyone can sign up for and use** — free to users, but publicly
accessible and operated as a product. §1.5 works out what that does to the licensing
bar. Short version: it disqualifies every non-commercial research licence for anything
that ships, and "free to users" does not rescue them.

Every candidate below carries one of two labels:

- **SHIPPABLE** — may be adopted into the product.
- **EVALUATE-ONLY** — may be run for research and comparison (which is exactly what
  those licences grant), but may never ship. Kept in the survey deliberately, so the
  decision is made knowing what the restricted option would have bought.

---

## 0. TL;DR for the builder

**Recommendation: (a) — keep the geometric solve, add no learned contact model.**

Single strongest reason: **every learned contact model that is legally usable here
predicts a strictly weaker version of a signal the pipeline already computes in 3D.**
The vendored MHR keypoint set (`sam_3d_body/metadata/mhr70.py`, indices 13–20) is:

```
13: left_ankle        14: right_ankle
15: left_big_toe_tip  16: left_small_toe_tip   17: left_heel
18: right_big_toe_tip 19: right_small_toe_tip  20: right_heel
```

Those eight 3D points, per frame, per tracked dancer, are already in
`pred_keypoints_3d` in `sam_3d_body_estimator.py`'s per-person output dict — alongside
`pred_vertices` (full mesh, so the sole surface is available too). The best legally
usable learned contact model found (ContactVision) takes **2D** keypoints and emits a
`(T, 4)` binary toe/heel array. That is the same quantity, inferred from less
information, at the cost of a new model, new weights, a new 2D detector, and a
non-commercial upstream dependency.

Secondary reason: the two models that predict something genuinely *new* — world
trajectory under a moving camera (WHAM, GVHMR, TRAM) — are each disqualified on
licensing (§2), and the thing they buy you (camera motion via SLAM) is explicitly out
of scope in `docs/PRD.md` §5 and unrepresentable in the frozen `Camera` contract
(`"model": {"const": "pinhole"}`, one static `camera_to_world` per clip).

**Fallback held in reserve, not adopted now: MoGe-2** (§2.9). MIT code, MIT weights,
*already vendored* in this repo at
`services/motion-api/vendor/fast-sam-3d-body/tools/build_fov_estimator.py`, and
deliberately dropped from `setup_env.sh` Step 7 during the gate with a written reason.
It is the only candidate in the whole survey with a licence cleaner than what the repo
already carries. If the geometric plane fit turns out to be under-determined on
`solo-07` (floor work), this is the one thing worth reaching for — and it is a
*scene-geometry* prior, not a contact model.

**The gap to the best EVALUATE-ONLY option, stated honestly:** the strongest
non-shippable candidate is **GVHMR**, which predicts per-frame stationary labels for
hands *and* feet in a gravity-aligned world frame and uses them with an IK solver to
suppress sliding. That is a genuinely richer signal than a height-and-velocity
heuristic — most of all because it was trained to distinguish *stationary but airborne*
(a held heel-up position, which dancers do constantly) from *planted*, which is exactly
where velocity heuristics are documented to fail. **I did not measure that gap. No
model in this survey was run, and §6.5 scopes what measuring it would actually cost.**
The recommendation below does not depend on the gap being small; it depends on the
shippable alternative already holding the same quantity in 3D (§0, §4).

---

## 1. What the problem actually is, framed against the frozen contract

The builder's framing is correct and worth restating in contract terms, because it
bounds what any learned model could even be plugged into.

`packages/motion-contract/schema/motion-result.schema.json` `$defs.Grounding` is:

```json
"Grounding": {
  "required": ["status", "floor_plane"],
  "status":      { "enum": ["grounded", "none"] },
  "floor_plane": { "oneOf": [ {"type": "null"},
                              {"required": ["normal", "point"]} ] }
}
```

Three consequences that matter more than any benchmark number:

1. **The output is one static plane for the entire clip.** Not per-frame. A per-frame
   contact signal is therefore *never* a contract field — it can only ever be an
   internal input to the plane fit and to the `grounded` / `none` decision. This is
   exactly the builder's "feeds, not replaces" intuition, and the contract enforces it.
   Any evaluation of contact accuracy must instrument the solver's internals; it cannot
   be scored from a `MotionResult`.

2. **`status: "none"` is a first-class, designed-for outcome.** `DESIGN.md` §10: "When
   grounding fails (feet cropped for most of the clip): **no floor at all** … Never
   fake a plane." `evaluation/clips.yaml`'s `stress-cropped-feet` makes this a negative
   success criterion. A learned contact model that confidently hallucinates contact on
   cropped feet is an *active liability* against the product's stated honesty
   boundary, not a neutral addition.

3. **The camera is static by construction.** `Camera.model` is `const: "pinhole"`, one
   `camera_to_world` per clip, and PRD §5 puts moving cameras out of MVP scope.
   Per-frame world-space root position *is* representable (`PersonResult.root_trajectory`
   → `RootTrajectorySample.position`), so a world-grounded method's trajectory output
   would fit — but its *reason for existing*, recovering camera ego-motion so the world
   frame stays fixed while the camera moves, buys the product nothing it promises.

### 1.5 The licensing bar, and why "free to users" does not lower it

**The bar a new dependency must clear is the SAM License**, because the stack already
depends on it and it already clears the bar: a royalty-free licence to use, reproduce,
distribute and create derivative works, with **no commercial restriction, no
field-of-use limit, and no user-count threshold**. Its real constraints are pass-through
on redistribution (§1.b.i), the ITAR/military/nuclear prohibition (§1.b.v), a citation
requirement for research publications (§1.b.ii), no reverse engineering, compliance with
privacy law, and unilateral amendment by Meta (§8) — all recorded in `NOTICE` and PRD §2
G2. A new dependency that is *less* permissive than that makes the product's licensing
story strictly worse, and the mixed-licence `NOTICE` exists precisely so that there is
exactly one such exception to explain.

**"Free to users" is irrelevant to the non-commercial test, and it is worth being
blunt about why.** These licences do not grant "use unless you charge money". They grant
a *positively enumerated scope*, and a public consumer platform is outside it on the
face of the text. Read the actual grants:

- **SMPL** (smpl.is.tue.mpg.de/modellicense.html) grants use for "non-commercial
  scientific research, non-commercial education, or non-commercial artistic projects",
  then closes it: "Any other use, in particular any use for commercial purposes, is
  prohibited." A signup-and-upload dance product is not scientific research, not
  education in the sense meant, and not an artistic project. It fails the *inclusion*
  test before the commercial question is even reached.
- **AMASS** uses the same three-purpose framing and the same closing sentence.
- **BEDLAM** is more explicit still, naming the exact failure mode: prohibited is "any
  use commercial, pornographic, military, surveillance, purposes", expressly including
  "incorporation in commercial product, **use in commercial service**".
- **InterDigital (UnderPressure)** is the single most on-point clause in the whole
  survey for a hosted product — it excludes "**any use Software provide service third
  party**". Serving users *is* the product.
- **Adobe (Rempe)** defines the boundary itself: noncommercial research "include
  academic research, teaching, testing, but do not include commercial licensing or
  distribution", nor "development commercial products".

And all four of the MPI-family licences reach **through training**, so the restriction
survives even where the body model itself is stripped out. SMPL: "This license also
prohibits the use of the Software to train methods/algorithms/neural networks/etc. for
commercial use of any kind." AMASS: "prohibits use Dataset train
methods/algorithms/neural networks/etc. commercial use any kind." BEDLAM: same
construction, extended to "commercial, pornographic, military, surveillance, defamatory
use any kind."

**Consequence: SMPL, SMPL-X, and anything requiring them at inference are OUT for
adoption. Not "probably fine because it is free" — out.** That is not a hedge and it
does not depend on how the product is monetised.

**They are still worth evaluating, and evaluating them is licensed.** Every one of those
grants explicitly covers non-commercial scientific research, which is what a benchmark
comparison on eval clips is. §6.5 scopes that arm of the evaluation. The distinction to
hold onto is **adopt vs. measure** — measuring GVHMR to learn the size of the gap is
permitted; shipping it is not; and a checkpoint produced by fine-tuning on our clips
*from* an AMASS-trained model is not laundered by our doing the fine-tuning.

### 1.6 The three-axis licence test

The trap this project has already been bitten by is treating a licence as one fact.
It is three, and each must be checked separately:

1. **Code** — the repo's `LICENSE` file. Often permissive, often the only thing a README
   or a GitHub sidebar badge reports.
2. **Weights** — frequently a *different* licence, stated in a README section or on the
   model-hub page rather than in the repo. **Depth Anything V2 is the live proof**: an
   Apache-2.0 repo whose Base/Large/Giant checkpoints are CC-BY-NC-4.0 (§2.7).
3. **Runtime assets** — third-party files the model cannot execute without, fetched
   separately under their own terms. **WHAM and TRAM are the live proof**: MIT code that
   will not produce a mesh without `SMPL_NEUTRAL.pkl`, downloaded with your own MPI
   credentials (§2.1, §2.3).

To which this survey adds a fourth, discovered while reading AMASS:

4. **Training-data terms**, which can reach forward into the released checkpoint even
   when code, weights and assets all look clean. A model whose code is MIT and whose
   weights are labelled MIT may still have been trained on a corpus that forbids
   commercial use of anything trained on it.

`docs/LICENSES.md` currently models axes 1–3 well (it splits MHR code from MHR assets
explicitly). Axis 4 is not represented there and probably should be.

### 1.7 Ethical-use and acceptable-use clauses

Flagged per the coordinator's request. **This is not privacy-law analysis — another
agent has that** — these are contractual clauses in licences this survey read, quoted so
that analysis has them.

- **BEDLAM** is the one to notice. It prohibits "surveillance" use outright, and
  separately prohibits use to "create fake, libelous, misleading, defamatory content any
  kind excluding analyses in peer-reviewed scientific research". A platform that
  reconstructs 3D bodies of identifiable people from user-uploaded video sits closer to
  the first clause than is comfortable. It is EVALUATE-ONLY regardless, so this does not
  change any verdict here — but it is the clearest example of the clause type, and any
  future BEDLAM-trained candidate inherits it.
- **SMPL** and **AMASS** both carry a content clause: the material "may not be used for
  pornographic purposes or to generate pornographic material **whether commercial or
  not**" — i.e. it binds even a purely non-commercial research use.
- **No biometric or re-identification clause appears in the SMPL model licence.** I
  looked specifically; the text has nothing on biometrics, re-identification, or
  data-protection obligations. It links a separate privacy policy I did not read.
- **The SAM License already carries the relevant clauses for the shipping stack** —
  ITAR/military/nuclear/espionage prohibition and a privacy-law compliance obligation,
  both already recorded in `NOTICE` and reflected in `OPEN-DECISIONS.md` D8 ("Both Meta
  and NVIDIA licences restrict processing people without consent").
- **MIT, Apache-2.0, BSD-2-Clause and the MoGe MIT weights carry no acceptable-use
  clause at all.** That is a genuine, under-appreciated advantage of the recommended
  option: it adds zero new field-of-use surface to a product that will process video of
  identifiable people.

---

`OPEN-DECISIONS.md` has **no open item on grounding method**. The nearest entries are
B3 ("Feet cropped for most of the clip → no floor", LEANING — needs a drawn mockup, a
design question not a model question) and E5 (two-environment split, SETTLED). Per the
ground rules: I am not inventing an answer to an unlisted decision; I am answering the
question the builder actually asked, and flagging that the method choice was never an
OPEN-DECISIONS item to begin with.

---

## 2. Survey and licensing verdict

Licence text was read from the repositories' own `LICENSE` files, not from README
summaries or model-hub badges. Quotations below are from the files as fetched on
2026-09-18; the fetch tool normalises whitespace and drops some stop-words, so treat
the quoted strings as *faithful in substance and distinctive wording* but re-read the
canonical file before relying on any of them in a legal filing.

### Summary table

Columns follow the three-axis test of §1.6. "Assets" means third-party files the model
cannot run without.

| Candidate | Predicts | Code | Weights | Runtime assets (SMPL at inference?) | Status |
|---|---|---|---|---|---|
| **MoGe / MoGe-2** | **metric point map + camera intrinsics** | MIT (verified) | **MIT** (verified on HF) | none | **SHIPPABLE — cleanest in survey** |
| **Depth Anything V2 — Small** | relative depth | Apache-2.0 (verified) | **Apache-2.0** | none | **SHIPPABLE, weak** |
| **Depth Pro (Apple)** | metric depth | Apple Sample Code (verified) | same licence | none | **SHIPPABLE, not recommended** |
| **ContactVision** | `(T,4)` toe/heel contact from 2D keypoints | MIT | unverified (WIP repo) | OpenPose BODY_25 → **CMU non-commercial** | **NOT SHIPPABLE as-is** (asset axis) |
| **Metric3D / v2** | metric depth | BSD-2-Clause | **not stated anywhere** | none | **UNVERIFIED — do not adopt** |
| **Depth Anything V2 — Base/L/Giant** | relative depth | Apache-2.0 | **CC-BY-NC-4.0** | none | **EVALUATE-ONLY** (weights axis) |
| **UniDepth** | metric depth + intrinsics | **CC BY-NC 4.0** (verified) | same | none | **EVALUATE-ONLY** |
| **WHAM** | SMPL pose + world trajectory + foot-contact **probability** | MIT (verified) | AMASS/BEDLAM/3DPW-trained (axis 4) | **Yes** — `fetch_demo_data.sh` fetches `SMPL_NEUTRAL.pkl` | **EVALUATE-ONLY** (assets + training data) |
| **GVHMR** | SMPL pose, gravity-view coords, **stationary labels** for hands/feet | **Non-commercial** (verified) | same NC licence + AMASS-trained | **Yes** | **EVALUATE-ONLY** (all four axes) — *strongest restricted option* |
| **TRAM** | SMPL + world trajectory via SLAM | MIT (verified) | not separately stated | **Yes** — README requires SMPL/SMPLify registration | **EVALUATE-ONLY** (assets axis) |
| **Rempe et al.** | 4 binary foot contacts from **2D pose only** | **Adobe non-commercial** (verified) | same | OpenPose → also non-commercial | **EVALUATE-ONLY** |
| **UnderPressure** | vGRF → derived contact, from **mocap skeleton** | **InterDigital non-commercial** (verified) | same | none (but mocap input, not video) | **EVALUATE-ONLY**, wrong-shaped |
| **PhysCap / physics-based HMR** | contact + physics-plausible motion | research-only | research-only | Yes | **EVALUATE-ONLY** (not re-verified; §5) |
| **OnlineHMR (CVPR 2026)** | world-grounded mesh + trajectory, online | not verifiable from abstract | not released/verifiable | almost certainly yes | **NOT ASSESSED** |

Only four rows are SHIPPABLE, and three of those are scene-geometry models rather than
contact models. **There is no shippable learned foot-contact model.** That is the
survey's central finding, and it is not a close call.

### 2.1 WHAM — `yohanshin/WHAM`

**Predicts:** SMPL body pose in camera coords, global root trajectory, and an explicit
**foot-ground contact probability** from its Local Motion Decoder, which its Trajectory
Refiner then consumes to kill foot sliding. On paper this is the single best match to
the builder's "learned contact feeds the geometry" idea — the architecture literally
does that internally.

**Code licence — read, and it is genuinely MIT.** `LICENSE` is the standard MIT text,
`Copyright (c) 2023 Soyong Shin`, granting rights to "use, copy, modify, merge,
publish, distribute, sublicense, and/or sell copies". No field-of-use clause, no
citation requirement, no non-commercial term. **The MIT label is real.** This is
precisely the trap the builder warned about: stopping here would give the wrong answer.

**Disqualifier 1 — SMPL is required at inference, not just training.**
`fetch_demo_data.sh` is unambiguous. It defines a `urle()` URL-encoder specifically to
POST your credentials to `download.is.tue.mpg.de`, then:

- prompts for **smplify.is.tue.mpg.de** credentials, downloads
  `mpips_smplify_public_v2.zip`, extracts
  `basicModel_neutral_lbs_10_207_0_v1.0.0.pkl` and renames it `SMPL_NEUTRAL.pkl`;
- prompts for **smpl.is.tue.mpg.de** credentials, downloads `SMPL_python_v.1.0.0.zip`,
  extracts `SMPL_FEMALE.pkl` / `SMPL_MALE.pkl`;
- `gdown`s `body_models.tar.gz` (J_regressor and friends).

These land in `dataset/body_models/` and are loaded by the demo path, not by a training
script. WHAM's outputs *are* SMPL parameters; without the `.pkl` there is no mesh and
no joint regressor. **This is the exact case the brief asked to be called out plainly:
the code is permissively licensed but cannot run without a non-commercially-licensed
body model, so it is not usable here.**

**Disqualifier 2, independent of SMPL — the weights are AMASS-derived.** The released
checkpoints are `wham_vit_w_3dpw.pth.tar` / `wham_vit_bedlam_w_3dpw.pth.tar`, trained
on AMASS + BEDLAM + 3DPW. The AMASS licence (amass.is.tue.mpg.de/license.html), read
directly, grants use for "non-commercial scientific research, non-commercial education,
or non-commercial artistic projects" and states "Any other use, in particular any use
for commercial purposes, prohibited." Critically it reaches *through* training:

> "prohibits use Dataset train methods/algorithms/neural networks/etc. commercial use
> any kind"

So even a hypothetical SMPL-free WHAM shipping MIT-licensed *code* would ship weights
whose training data forbids commercial deployment. **Code licence and weights licence
diverge here for a third reason beyond the two the brief anticipated: training-data
licence.** Worth adding to `docs/LICENSES.md`'s mental model — it is a distinct axis
from "code vs weights".

**Verdict: EVALUATE-ONLY.** Two independent, sufficient grounds against shipping. Worth
measuring (§6.5) because its contact-probability head is the closest published thing to
what the geometric solve is being asked to do.

### 2.2 GVHMR — `zju3dv/GVHMR`

**Predicts:** SMPL in gravity-view coordinates plus **stationary probability labels for
hands and feet**, used with an IK solver to suppress foot sliding. Functionally the
closest thing in the literature to "a learned model that tells you when a foot is
planted, in a world frame".

**The code licence itself is non-commercial.** Not the body model — the repo's own
`LICENSE`, © 3D Vision Group, State Key Lab of CAD&CG, Zhejiang University, 2022–2023:

> "Permission use, copy, modify distribute software its documentation educational,
> research non-profit purposes only."

and, separately:

> "Any modification based on this work must open-source prohibited commercial use."

with commercial enquiries directed to `xwzhou@zju.edu.cn`. There is also a citation
requirement ("If you use software, please cite corresponding publications listed on
above website") and an attribution-retention clause.

Two notes for this repo specifically. First, that citation requirement is the same
species of term that FSF classifies as an additional restriction — the one that PRD §2
G2 identified as making the SAM License AGPL-incompatible. Second, "any modification …
must open-source" is a copyleft-flavoured obligation that would collide with shipping
SAM-derived material under a licence that forbids exactly that kind of downstream
relicensing. So GVHMR is not merely non-commercial; it is non-commercial *and*
structurally the same shape as the conflict that got Ultralytics removed.

It additionally requires SMPL at inference and is AMASS/BEDLAM-trained.

**Verdict: EVALUATE-ONLY**, disqualified from shipping on all four axes of §1.6. This is
the one where reading the licence rather than the README changes the answer most:
GVHMR's landing page reads as an open release with "all code and weights publicly
available", and it is — for research.

**It is also the restricted candidate most worth measuring.** Its stationary-label head
covers hands as well as feet, is gravity-aligned by construction, and was trained to
separate *stationary but airborne* from *planted* — the documented failure mode of the
height/velocity heuristics the geometric solve will use. If any learned model would
beat the hand-rolled solve, it is this one, and knowing the size of that gap is worth
the research licence it is offered under. See §6.5.

### 2.3 TRAM — `yufu-wang/tram`

**Predicts:** SMPL in world coordinates by combining HMR with SLAM-recovered camera
motion; the headline capability is a metric-scale global trajectory from a *moving*
camera.

**Code licence:** MIT, `Copyright (c) 2024 Yufu Wang`, verified against the file — full
grant including "sell copies", no restrictions. The README adds only "Note thirdparty
models own licenses."

**Disqualifier — SMPL at inference.** README, Prepare data:

> "Register at [SMPLify](https://smplify.is.tue.mpg.de) [SMPL](https://smpl.is.tue.mpg.de),
> whose usernames passwords used by script download SMPL models."

`bash scripts/download_models.sh` uses those credentials to populate `data/`. Same
structure as WHAM: MIT wrapper, MPI body model underneath, no runtime without it.

**Also irrelevant to us even if it were clean:** TRAM's value is camera-motion recovery.
PRD §5 excludes moving cameras; the `Camera` contract cannot express one. We would be
paying a SLAM stack's install cost and runtime for a capability the product refuses to
offer.

**Verdict: EVALUATE-ONLY**, and low priority even for that — it has no dedicated contact
head, so it would tell us less per hour of setup than GVHMR or WHAM.

### 2.4 Rempe et al., "Contact and Human Dynamics from Monocular Video" — `davrempe/contact-human-dynamics`

This is, conceptually, *the* right paper for the builder's question. Its contact module
is a small temporal network over a **2D pose sequence** that emits four binary labels
per frame (left heel, left toe, right heel, right toe) into `foot_contacts.npy`, an
`Fx4` array. No body model involved. The repo explicitly supports running contact
detection alone: "only necessary to install OpenPose" if you skip the physics
optimisation. Reported benefit over the obvious hand-rolled baseline is real and
specific — the paper reports downstream optimisation converging on 94.9% of test videos
using network contacts vs 69.2% using a velocity heuristic, and notes the velocity
baseline mislabels stationary-but-airborne heels. **That 94.9%/69.2% pair is a vendor
number on the authors' own test set and I did not re-verify it; treat it as a direction,
not a magnitude.**

**Disqualifier 1 — the licence is Adobe's, non-commercial.** `LICENSE.txt` (not
`LICENSE`; the first path 404s), licensor "Adobe Inc., having place business at 345 Park
Avenue, San Jose, California 95110-2704":

> grant covers reproduction, modification, display and performance for **"noncommercial
> research purposes only"**, and redistribution likewise "noncommercial research
> purposes only, provided you give recipients copy this License"

with the boundary defined explicitly:

> "noncommercial research purposes include academic research, teaching, testing, but do
> not include commercial licensing or distribution"

and excluding "development commercial products, or any other activity results in
commercial gain".

**Disqualifier 2 — OpenPose.** The input pipeline is OpenPose BODY_25. CMU's `LICENSE`,
read directly, is headed **"ACADEMIC OR NON-PROFIT ORGANIZATION NONCOMMERCIAL RESEARCH
USE ONLY"**, granting a "non-exclusive, non-transferable license use Software
noncommercial research purposes, without right sublicense", with derivatives usable
"your own noncommercial internal research purposes" only.

*(A secondary search result asserted OpenPose's commercial licence carves out sports and
athletic competition. **I could not find that clause in the `LICENSE` file** — if it
exists it is in the separate commercial/Flintbox terms, which I did not read. Do not
repeat that claim without reading those terms.)*

**Verdict: EVALUATE-ONLY.** Notable as the strongest technical argument *for* learned
contact that the project cannot legally ship. Its published 94.9%-vs-69.2% convergence
gap over a velocity heuristic is the single most relevant prior number in this survey —
which is exactly why §6.5 proposes measuring it rather than quoting it.

### 2.5 UnderPressure — `InterDigitalInc/UnderPressure`

**Predicts:** vertical ground reaction forces from motion, from which binary contact
labels are derived. Trained against pressure-insole ground truth, which is the most
honest contact supervision in the field.

**Licence** (`LICENCE.txt`, British spelling — the American-spelled path 404s),
licensor InterDigital Communications, Inc.:

> permits "any use Software fundamental research work exclusion any commercial use",
> where commercial includes "any sublicense granted on Software fee whatever its
> nature", "any use Software provide service third party", and "any use Software create
> competing product Software"

It also forbids modification outright:

> "Licensee shall not have right correct, adapt, modify, reverse engineer, disassemble,
> decompile"

"any use to provide a service to a third party" is the most precisely fatal clause in
the survey for a public platform — it is not a commercial-vs-free distinction at all, it
is a *serving users* prohibition, and serving users is the product.

**Also wrong-shaped:** input is mocap skeleton data (Xsens `.mvnx`), not video. It would
sit *after* the 3D estimator, consuming what we already have — so it is not a way to
improve the estimate, it is a second opinion on it.

**Verdict: EVALUATE-ONLY**, and the no-modification clause makes even that awkward.

### 2.6 ContactVision — `DaeeYong/ContactVision` (CGF 2026)

**Predicts:** exactly what we would want — a `(T, 4)` binary array ordered
`['left_toe', 'right_toe', 'left_heel', 'right_heel']`, per frame, from 2D keypoints.
Trained with contact labels derived from mocap GRF, and validated against pressure-mat
data. **Repo licence is MIT**, and it has **no SMPL dependency**. On licence grounds
alone this is the only learned contact model in the survey that survives.

**Why it still does not get adopted, three reasons:**

1. **Its input is OpenPose BODY_25** — README: "uses 2D body keypoints extracted
   OpenPose as input", converted `(T,25,3)` → `(T,13,3)` lower-body, pelvis-relative.
   OpenPose is CMU-noncommercial (§2.4). Feeding it different keypoints is not a
   drop-in: BODY_25 has indices 19–24 for `LBigToe/LSmallToe/LHeel/RBigToe/RSmallToe/RHeel`,
   and **our detector is RTMO on COCO-17, which has no foot keypoints at all** (ankles
   at 15/16 and nothing below). We would have to swap to an RTMW / COCO-WholeBody model
   (Apache-2.0, available in `rtmlib`) *and* re-map, and the network was not trained on
   that keypoint distribution. Realistically: retraining.
2. **The weights are unverified.** The repo describes itself as work-in-progress with a
   fuller release targeted **December 2026** — i.e. in the future relative to today. A
   `checkpoints/best_model.pth` path is referenced; I could not confirm a real
   checkpoint is committed, nor find any separate licence statement for it. The MIT repo
   label does not automatically cover a checkpoint, as Depth Anything V2 demonstrates
   below.
3. **It predicts less than we already have.** Its whole job is to infer, from 2D
   lower-body keypoints, which of four foot points are on the ground. We already have
   those four points **in 3D**, per frame, from MHR (§0). Spending a retrain to recover
   a 2D-derived estimate of something we hold in 3D is backwards.

**Verdict: NOT SHIPPABLE as-is.** The *code* axis is clean (MIT, no SMPL) — this is the
only learned contact model that clears axes 1 and 3 — but it fails the runtime-asset
axis on OpenPose, has an unverified weights axis, and is redundant against a 3D signal
we already hold. Worth re-checking after its December 2026 release *only if* §3's
geometric solve proves inadequate on real footage. It is also the only candidate that a
clean-room re-implementation could plausibly rescue, since the architecture is small and
published — but that is a training project, not a dependency decision.

### 2.7 Depth Anything V2 — `DepthAnything/Depth-Anything-V2`

This is the clearest live example of the code/weights split the brief warned about, and
it is worth putting in `docs/LICENSES.md` as a reference case.

- **Code:** the repo's `LICENSE` is the verbatim Apache License 2.0 (checked: §2
  copyright grant, §3 patent grant with retaliation, §4 redistribution conditions
  including "cause any modified files carry prominent notices stating You changed
  files", §6 trademark carve-out).
- **Weights**, from the README's own LICENSE section, quoted exactly:

  > "Depth-Anything-V2-Small model is under Apache-2.0 license. Depth-Anything-V2-Base/Large/Giant models are under CC-BY-NC-4.0"

So `depth_anything_v2_vits.pth` (24.8M params) is commercially usable; `vitb` (97.5M),
`vitl` (335.3M) and Giant (1.3B) are not. **An engineer who reads only the repo badge —
which says Apache-2.0 — and downloads the Large checkpoint because it scores best has
just taken a CC-BY-NC dependency into a commercial product.**

Technically: V2 outputs *relative* (affine-invariant) depth. That constrains a floor
plane's **orientation** but not its metric position, so it cannot by itself place the
plane in the same metric world space as `root_trajectory`. Its metric-depth variants are
fine-tuned from the larger encoders, i.e. back in CC-BY-NC territory.

**Verdict: Small is SHIPPABLE and clean; Base/Large/Giant are EVALUATE-ONLY on the
weights axis. Not recommended either way, because MoGe-2 does strictly more under a
cleaner licence.**

### 2.8 Metric3D / Metric3Dv2, UniDepth, Depth Pro

- **Metric3D** (`YvanYin/Metric3D`): README states "*Metric 3D* code is under 2-clause
  BSD License", sidebar agrees. **The weights have no stated licence.** The HF repo
  `JUGGHM/Metric3D` has no model card at all and no licence tag. Given Depth Anything's
  example one directory over, a permissive *code* licence is not evidence about
  checkpoints. **UNVERIFIED — flagged, not cleared.** Do not adopt on the strength of
  the BSD badge.
- **UniDepth** (`lpiccinelli-eth/UniDepth`): `LICENSE` is verbatim CC BY-NC 4.0 —
  "reproduce Share Licensed Material, in whole or in part, for **NonCommercial purposes
  only**", with §1(i) "NonCommercial means not primarily intended for or directed
  towards commercial advantage monetary compensation." **EVALUATE-ONLY.** This is the
  one licence whose wording ("not *primarily* intended for commercial advantage") could
  tempt a free-to-users argument. It should not be attempted: a public platform operated
  as a product is directed toward commercial advantage whatever it charges today, and
  §1.5's whole point is that the product should not rest on a clause someone would have
  to argue about.
- **Depth Pro** (`apple/ml-depth-pro`): README applies the *same* file to both —
  "This sample code is released under the LICENSE terms" and "The model weights are
  released under the LICENSE terms", both linking the repo-root `LICENSE`. That file is
  Apple's Sample Code Licence: a "personal, non-exclusive license, under Apple's
  copyrights" to "use, reproduce, modify redistribute", with redistribution conditioned
  on "you must retain this notice following text disclaimers in all redistributions".
  No non-commercial clause. **But**: "no other rights licenses, express or implied, are
  granted", specifically excluding "any patent rights that may infringed by your
  derivative works", plus a trademark clause and a subcomponents carve-out deferring to
  `ACKNOWLEDGEMENTS`.

  **Usable, but not recommended here for a repo-specific reason:** this repo already
  carries one non-OSI, non-SPDX licence (SAM) and `NOTICE` exists to make that single
  exception legible. Adding a second bespoke licence with no patent grant makes the
  mixed-licence story materially harder to state honestly, for a model that MoGe-2
  matches under plain MIT.

### 2.9 MoGe / MoGe-2 — `microsoft/MoGe` — **the one worth knowing about**

**Predicts:** a metric-scale point map (not just depth), a validity mask, surface
normals, and **camera intrinsics / FOV**, all from a single RGB frame. MoGe-2
checkpoints are metric-scale; MoGe-1 is not.

**Licence, both halves, read directly:**
- Code `LICENSE`: "MIT License Copyright (c) Microsoft Corporation", with the file also
  carrying the full Apache-2.0 text for the vendored DINOv2 module. README: "MoGe code
  is released under MIT license, except DINOv2 code in `moge/model/modules/dinov2` is
  released by Meta AI under Apache 2.0 license."
- Weights: HF `Ruicheng/moge-2-vitl-normal` → metadata **`License: mit`**.
  `Ruicheng/moge-2-vits-normal` → **`License: mit`**. Checked separately from the code,
  precisely because that split is where this project has been bitten.

**MIT code and MIT weights is cleaner than anything else in this survey, and cleaner
than most of what the repo already depends on.** Against the §1.5 bar: strictly more
permissive than the SAM License on every axis — no field-of-use limit, no ITAR clause,
no citation obligation, no unilateral-amendment clause, no acceptable-use policy, and
nothing to add to `NOTICE` beyond a standard MIT attribution. **SHIPPABLE**, subject to
the training-data caveat below.

**And it is already in the tree.** `services/motion-api/vendor/fast-sam-3d-body/tools/build_fov_estimator.py`
is a complete MoGe-2 wrapper — `FOVEstimator` class, `MOGE_MODELS` mapping s/b/l to
`Ruicheng/moge-2-vit{s,b,l}-normal`, `run_moge` / `run_moge_fast`, `denormalize_f` to
convert normalised intrinsics to pixel units, an optional TensorRT encoder path, and
FP16 support. It imports `from moge.model.v2 import MoGeModel`.

**This project already considered it and dropped it, with a stated reason.**
`setup_env.sh`:

```
# Step 7: [REMOVED] MoGe -- FOV/depth estimator, unused in the gate. The MVP
# camera model is "single_front_static" (docs/PRD.md); FOV estimation is
# optional in demo.py (only loaded if --fov_name is passed) and not worth the
# extra dependency until the contract needs it.
```

and `PROVENANCE.md` line 47 records it among the removals. I checked: neither
`tools/process_clip.py` nor `services/motion-api/modal_app.py` references `moge` or
`fov`, and it is not in `requirements-api.txt`.

**Why this matters for the grounding work:** the removal note says "not worth the extra
dependency **until the contract needs it**". The contract now has a `Grounding` object
with a required `floor_plane`, and `Camera.intrinsics` is a required field. That is
arguably the condition the note anticipated. It is still not needed *yet* (see §3), but
it is the correct first thing to reach for if the geometric fit is under-determined —
and the reach is unusually short, because the adapter is written, the env is the right
env (upstream's `setup_env.sh` installs MoGe into the same Python 3.11 / torch
2.5.1+cu124 conda env), and the licence is MIT/MIT.

**Caveat I could not close:** both HF model cards are **empty** — no training-data
documentation at all. The AMASS lesson from §2.1 is that training-data licence is a real
third axis. I cannot tell you what MoGe-2 was trained on. Before adopting, someone
should check the MoGe-2 paper's dataset table against each dataset's terms. Flagged, not
cleared.

### 2.10 Not assessed

- **OnlineHMR** (CVPR 2026, arXiv 2603.17355): online world-grounded HMR with causal
  KV-cache inference, evaluated on EMDB. The abstract page does not state the body
  model, and licence/weights terms are not determinable from it. Almost certainly
  SMPL-based. **Not assessed — do not treat its absence from the table as clearance.**
- **PhysCap and physics-based HMR generally**: uniformly MPI/research-licensed and
  SMPL-based. I did not re-fetch each licence; I am relying on the PRD's existing
  exclusion list plus the category pattern. **Flagged as taken on faith.**
- **"World-Coordinate Human Motion Retargeting via SAM 3D Body"** (arXiv 2512.21573):
  interesting as *literature support for option (a)* rather than as a dependency — it
  takes SAM 3D Body as a frozen backbone, converts to MHR, and recovers global root
  trajectories with "a differentiable soft foot-ground contact model and contact-aware
  global optimization", i.e. contact probability as a smooth function of foot-to-ground
  height. That is the hand-rolled geometric approach, published, on our exact backbone.
  **No code release is announced and no benchmark numbers are reported** — the
  evaluation is qualitative ("stable world trajectories"). Useful as a design
  reference for the soft-contact formulation; not citable as an accuracy result.

### 2.11 Accuracy and runtime — why this section is thin, deliberately

The brief asks for stated accuracy and runtime per candidate. For every disqualified
candidate those numbers are moot, and reproducing vendor benchmark tables for models
we cannot legally run would be exactly the "published figures as fact" failure mode PRD
§2 G7 warns about. The only figures reported above are Rempe's 94.9%/69.2%
convergence pair (flagged as unverified vendor numbers on the authors' own test set)
and parameter counts, which are checkable facts rather than performance claims.

Runtime, the one number that would change a decision: **MoGe-2-vitl is 331M params,
MoGe-2-vits is 35M.** For comparison, the measured pipeline today runs at 3.79 fps with
peak VRAM 3.69 GB of 47.2 GB (GATE-REPORT, solo-01, real L40S). VRAM is not the
constraint; wall-clock is, since cost is `$0.058/clip` at 3.79 fps. **I have not
measured MoGe-2 on this hardware and will not guess a per-frame cost.** If it is ever
adopted, note that a static floor plane does not require running it on every frame — a
handful of well-chosen frames would do, which is a large lever on cost that should be
measured before assuming the dependency is expensive.

---

## 3. Integration cost, against what this repo has actually paid

The brief asks for realism here, and `docs/GATE-REPORT.md` supplies the calibration: it
took **seven separate, individually-verified environment bugs** to get one CV image
green (bytetracker's `lap==0.4.0` pin, clang-vs-gcc autodetect, cuDNN/cuBLAS session
creation, `preload_dlls` ordering, ldconfig registration, rtmlib's CPU `onnxruntime`
silently clobbering `onnxruntime-gpu` so `CUDAExecutionProvider` vanished with no error,
and finally an unpinned `onnxruntime-gpu==1.30.0` demanding CUDA 13 against a
CUDA-12.4-pinned image). Several of those would have silently produced a CPU-only
pipeline — wrong by 10–50× on cost and throughput, with no error.

The repo also already runs a **two-environment split** (E5, SETTLED): SAM inference on
Python 3.11 / torch 2.5.1+cu124, glTF export on Python 3.12/3.13 + torch 2.8 for
`pymomentum-gpu`, exchanging plain arrays.

Cost tiers for the options:

| Option | Env impact | Realistic cost |
|---|---|---|
| **(a) geometry only** | none | zero new dependencies. Pure numpy/scipy on arrays already in `process_clip.py`'s npz. |
| **(d) + MoGe-2** | **same env** — upstream's own `setup_env.sh` installed it into the identical py3.11/torch2.5.1+cu124 conda env, and the adapter is already vendored | one `pip install moge` + weight download + a rebuild. Watch `--index-url`: MoGe's `requirements.txt` is now just `-e .` deferring to `pyproject.toml`, with README guidance pointing at cu128/cu130 wheels, so install it `--no-deps` in the style already used for `rtmlib`, or it will resolve a newer torch and silently break the CUDA-12.4 image. **That is bug #7 from the gate report waiting to happen again.** |
| **(b) + a learned contact model** | new env, probably | the only licence-clean one (ContactVision) also needs a different 2D detector and a retrain. Not a dependency add — a research project. |
| **(c) full world-grounded HMR** | **third environment** | WHAM wants Python 3.9 + torch 1.11 + cudatoolkit 11.3 + a source build of DPVO (Eigen 3.4.0, pytorch-scatter, cudatoolkit-dev, GCC 9.5 fallback). That is not compatible with either existing env. On the gate's own evidence, budget a multi-day environment fight before the first correct output — and it is disqualified on licensing anyway. |

**The brief's own rule applies cleanly: a model that is technically better but drags in
an incompatible torch is not worth it. (c) is that model, twice over.**

---

## 4. Recommendation

**Adopt (a): SAM 3D Body's existing per-frame output plus the geometric solve. Add no
learned contact model.**

Concretely, what the `grounding` builder already has to work with, verified in the
vendored source rather than assumed:

- `pred_keypoints_3d` → MHR70 indices 13–20 = both ankles, both heels, and both
  big-toe/small-toe tips, per frame, per person
  (`sam_3d_body/metadata/mhr70.py`).
- `pred_vertices` → the full skinned mesh, so the actual sole surface is available if
  keypoints prove too sparse.
- `skel_state` (J,8) → the raw `[translation, quaternion, scale]` MHR state, added in
  W8, which is what drives the GLB.
- `pred_cam_t` and `focal_length` per frame.
- The rig itself has `l_foot` / `l_ball` / `r_foot` / `r_ball` joints
  (`services/motion-api/mhr_joint_hierarchy.json`), so contact can be expressed in rig
  terms for the exporter.

That is a per-frame, per-foot, 3D height-and-velocity signal. The classical solve —
soft contact weight as a function of foot height and horizontal speed, then a robust
(RANSAC / trimmed least-squares) plane fit over the low-height, low-speed foot points
across the clip, with `status: "none"` when too few frames qualify — is the same
formulation arXiv 2512.21573 publishes on this exact backbone. It is maybe 60 lines,
has no licence surface at all, and every intermediate is inspectable, which matters a
great deal for a product whose differentiator is honest uncertainty.

**What would change my mind, specifically:**

1. **The plane fit is under-determined on `solo-07` (floor work).** When the dancer is
   on the floor, hips/hands/torso are all near-ground and the "lowest points are feet"
   heuristic degrades. If the fitted normal swings by more than a few degrees across the
   clip, or the plane latches onto the torso, reach for **MoGe-2** (§2.9) — one metric
   point map on a handful of frames gives an independent floor-plane prior from the
   *scene*, which is a different and complementary error mode from a prior derived from
   the *body*. MIT/MIT, adapter already vendored, same environment. This is the only
   escalation I would sign off on today.
2. **`stress-cropped-feet` produces `grounded` instead of `none`.** That is a *decision
   rule* bug, not a model-capacity bug, and adding a contact model would most likely
   make it worse (a model asked "is this foot in contact?" about a foot that is not in
   frame will answer something). Fix the abstention threshold.
3. **Contact frames are systematically wrong on `stress-footwork` in a way that is not a
   thresholding artefact** — e.g. precision and recall both poor across every threshold
   sweep, not trading off. Only then is model capacity the problem, and even then the
   first move is MoGe-2 or a wholebody 2D detector, not an NC-licensed HMR stack.
4. **Scope changes to allow moving cameras.** Then (c) becomes genuinely motivated — and
   the licensing survey would need redoing from scratch, because the answer today is
   "there is no permissive, SMPL-free, world-grounded HMR model", which is the same
   conclusion PRD §3's exclusion list reached and which this survey independently
   re-confirms.

**Explicitly not recommended:** (b) and (c). (b) because the only licence-clean learned
contact model is dependency-blocked, retrain-shaped, and redundant against a 3D signal
we already hold. (c) because all three candidates are EVALUATE-ONLY, all three need SMPL
at inference, all three need a third environment, and the capability they add is out of
MVP scope.

**On the public-platform confirmation specifically:** it does not change the
recommendation, it hardens it. Before the confirmation, (b) and (c) were arguable on a
"we might get a commercial licence later" basis. After it, WHAM / GVHMR / TRAM / Rempe /
UnderPressure are not deferred decisions — they are closed ones, and the only way any of
them re-opens is a negotiated commercial licence from MPI, Adobe, ZJU or InterDigital
respectively. Given the product is free to users, none of those negotiations has an
obvious budget behind it. **Plan as though the answer is permanent.**

---

## 5. What I could not verify

Stated plainly, per the ground rules.

1. **Whether MoGe-2's training data permits commercial use.** Both HF model cards are
   empty. Given §2.1's AMASS finding, training-data licence is a real third axis and I
   did not close it. **Must be checked before MoGe-2 is adopted, not after.**
2. **Metric3D's weights licence.** Not stated in the repo, not on the HF page, no model
   card. Reported as unverified rather than assumed permissive.
3. **3DPW's licence.** Not read. AMASS, BEDLAM and SMPL *were* read directly and each is
   independently sufficient for the WHAM/GVHMR verdicts, so nothing turns on 3DPW — but
   do not quote me on it.
   **(BEDLAM is now verified, after the coordinator's update: non-commercial, with an
   explicit training-use prohibition and a surveillance clause. See §1.5 and §1.7.)**
4. **ContactVision's checkpoint.** The repo references `checkpoints/best_model.pth` and
   describes a fuller release for December 2026. I could not confirm a real checkpoint is
   committed, its size, or any licence statement covering it separately from the MIT
   code.
5. **Any accuracy or runtime figure in this document.** Nothing here was measured. The
   only numbers I trust are the ones already in `GATE-REPORT.md`, which were measured on
   real hardware (3.79 fps, 98.3% frame reconstruction, 3.69 GB peak VRAM,
   $0.058/clip on solo-01, warm compute only).
6. **PhysCap / physics-based HMR licences individually.** Taken on faith from the PRD's
   exclusion list and the category pattern.
7. **The OpenPose "sports field-of-use" clause.** Asserted by a search result; **not
   present in the `LICENSE` file I read.** If it exists it is in separate commercial
   terms I did not fetch. Do not repeat the claim as verified.
8. **SMPL-X's licence text.** `smplx.is.tue.mpg.de` did not resolve (DNS failure) at the
   time of writing, so I read the **SMPL** model licence directly and am treating SMPL-X
   as carrying materially the same MPI terms. That inference is consistent with PRD §3's
   existing exclusion of everything SMPL/SMPL-X, but it is an inference, not a reading.
9. **Whether any MoGe-2 checkpoint carries an acceptable-use clause.** The HF pages show
   only `License: mit` with empty model cards; MIT has no AUP, but an empty card is an
   absence of evidence, not evidence of absence. Same gap as item 1, same fix.
10. **`docs/LICENSES.md` is stale on this branch's terms** — it still lists MHR assets as
   "**Unverified**", while `GATE-REPORT.md` records that assets.zip's in-zip
   `LICENSE.txt` was opened and is "plain Apache-2.0, no extra restriction". That file
   lives only on `licensing-compliance` (it is not on `w4-jobservice`), and the gate
   report already notes the branch "should updated reflect it". Not fixed here — this
   branch modifies no pipeline or licensing files — but it is a real, known
   inconsistency between two documents, and the MHR verdict in the brief ("verified
   Apache-2.0") matches the gate report, not `LICENSES.md`.

---

## 6. Evaluation plan

Designed around one constraint the brief insisted on: **do not propose an evaluation
that silently requires data nobody has.** Each item below says what footage it needs and
whether that footage exists today.

### 6.0 The structural problem: contact is not in the contract

`Grounding` exposes one static plane and a `grounded`/`none` status. Per-frame contact
never appears in a `MotionResult`. So contact precision/recall **cannot be measured from
pipeline output** — the solver must expose its per-frame contact array through a debug
side-channel (an extra key in the npz that `process_clip.py` already writes via
`save_clip_result`, or a separate artefact). **This is a small ask of the `grounding`
builder and it should be built in from the start**, because retrofitting observability
into a solver after it ships is how you end up unable to answer "why did it say none".

### 6.1 Ground truth that is genuinely obtainable, without a mocap rig

**Obtainable — per-frame foot contact, by hand annotation.** At 15 fps a 20-second clip
is ~300 samples × 4 foot points. A human can label these from the video frames. Two
rules that make the labels worth having:

- **Label a tri-state, not a binary:** `contact` / `airborne` / `ambiguous`. Motion blur
  and heel-hover are genuinely undecidable on 576×1024 phone footage, and forcing a
  binary manufactures disagreement that then shows up as fake model error.
- **Score only the unambiguous frames**, and report the ambiguous fraction alongside the
  score. If 40% of `stress-footwork` is ambiguous, that is itself the finding.

Honest cost: **1–2 hours of human labelling per clip**, plus a second annotator on a
10% sample to get an inter-annotator agreement number. Without that agreement number the
precision/recall figures have no error bar and should not be quoted. This is real,
unglamorous work, and it is the only contact ground truth available here.

**Not obtainable — the true floor plane.** There is no mocap rig, no calibrated scene,
no depth sensor, and the eval clips are third-party TikTok videos. **A metric
ground-truth plane for these clips does not exist and cannot be produced.** Do not
propose an MAE-against-true-normal metric; it cannot be computed. Two honest substitutes:

- **Temporal stability (no GT needed):** fit the plane independently on overlapping
  windows of the clip and report the spread of the normal in degrees and of the offset
  in cm. A correct solve on a static camera should be near-constant. This catches the
  `solo-07` failure mode directly.
- **Foot-sliding (no GT needed, but needs contact labels):** during human-labelled
  contact spans, measure the horizontal displacement of the contacting foot point in
  world space. Physics says it should be ~0. This is the metric the learned models exist
  to improve, so it is also the metric that would justify revisiting them.

**Optionally obtainable, labour-heavy:** for a clip on a visibly tiled or planked floor,
annotate two sets of parallel floor lines and derive the floor's orientation from their
vanishing points — a plane up to scale, enough to score the *normal* though not the
offset. Worth doing for exactly one clip as a sanity anchor; not worth doing for all.

### 6.2 Per-clip plan and footage status

| Clip | Tests | Footage status | What it measures |
|---|---|---|---|
| `solo-01` | baseline | **Have it.** 19.7 s, 576×1024, already in `stepwise-eval`, and 291 reconstructed frames already exist from the gate run | Plane temporal stability; contact P/R against hand labels. The cheapest first result available — the reconstruction is already done. |
| `solo-07` | `floor-work` | **Have it.** 23.6 s, 576×1022 @24fps, already in `stepwise-eval` | **The hardest positive case.** Dancer leaves the standing-on-a-plane assumption. Success: the plane stays where the *floor* is while the dancer lies on it; it must not migrate to torso height. Measured by temporal stability across windows that straddle the transition to floor work. |
| `solo-02` | `fast-motion` | **Have it.** 32.5 s @30fps | Partial stand-in for `stress-footwork` — fast motion and blur stress the same contact signal. Not a substitute for real footwork, but it is available today and `stress-footwork` is not. |
| `stress-cropped-feet` | `grounding-none` | **No URL, never sourced.** **But it can be synthesised**: crop `solo-01` and `solo-02` to knees-up and re-run. This is legitimate and cheap, and it gives a *paired* test — same clip, known-correct answers of `grounded` (full frame) and `none` (cropped). | **The negative criterion, and the highest-value test in the set.** Success is `status: "none"` and `floor_plane: null`, with no foot drawn solid. Report as a rate over several crop heights (knees, mid-thigh, hips) — the interesting output is *where* the abstention threshold sits, not a single pass/fail. **Caveat to state in results:** a synthetic crop is not a real knees-up clip. Real framing changes the dancer's behaviour and RTMO's box statistics. A real one should still be sourced eventually; the synthetic version is what makes the test runnable *now*. |
| `stress-footwork` | `feet`, `grounding` | **No URL. Genuinely needs sourcing.** | Contact-frame precision/recall at high step rate, and foot-sliding during contact. **This is the one grounding test that cannot be run today and cannot be faked from existing footage.** |
| `group-synced-01` | multi-dancer | **Have it.** 33.1 s | One plane, two dancers: both dancers' contacts should fit the *same* plane. A cheap, strong consistency check that needs no annotation — disagreement between per-dancer plane fits is a bug signal for free. |
| `solo-03` | turn, back-facing | **No URL. Still unsourced** — flagged in GATE-REPORT W8 and still open. | Not primarily a grounding clip, but back-facing frames are where depth sign errors appear, and a sign error puts the floor through the dancer. Worth re-running once it exists. |

### 6.3 Footage that must actually be sourced

Stated exactly, per the brief:

1. **`stress-footwork`** — fast footwork, feet clearly visible, static camera, no cuts,
   10–30 s. Not sourced. Per `evaluation/clips.yaml`'s header, the right source is the
   builder's own community (dance school, DJ's teams) with permission recorded in
   `rights:`, or a TikTok clip under `personal-test-only` for private testing. **Until
   this exists, the headline claim "contact detection works under fast footwork" cannot
   be made.**
2. **A real `stress-cropped-feet` clip** — knees-up framing, naturally shot. Lower
   priority than #1 because the synthetic crop covers most of the signal.
3. **`solo-03`** — carried over from the gate report, still open, still the PRD's
   actual named week-one deliverable.

Everything else in §6.2 runs on footage that is already downloaded and sitting in the
`stepwise-eval` Volume.

### 6.4 The EVALUATE-ONLY arm: measuring what a restricted model would have bought

The coordinator asked for the restricted candidates to be measured rather than merely
ruled out, so that the decision is made knowing the gap. That is the right instinct and
the licences permit it — every one of them grants non-commercial scientific research,
and a benchmark comparison run on eval clips, never shipped and never serving a user, is
squarely inside that grant. Three conditions keep it inside:

- **It runs on a research machine, never in the product's Modal app, never on
  user-uploaded video.** The eval clips only.
- **No artefact derived from a restricted model reaches the product** — not the
  checkpoint, not a distillation of it, not pseudo-labels used to train a shippable
  model. §1.5's training clauses reach forward; ours would too.
- **The result is a number in a document, which is what this arm is for.**

**Recommended scope: one model, GVHMR, on three clips.** It is the strongest restricted
candidate (§2.2), its stationary-label head is the closest analogue to what the
geometric solve computes, and one model is enough to answer the only question that
matters: *is the gap small enough to ignore, or large enough to change the roadmap?*
Running WHAM as well would roughly double the cost for a second sample of the same
answer; do it only if GVHMR's result is ambiguous.

**Metric: the same three already defined.** Contact precision/recall against the §6.1
hand labels, foot-sliding during labelled contact spans, and — the one that actually
decides things — the **`none` rate on the cropped variants**. A restricted model that
beats the geometric solve on contact but hallucinates contact on cropped feet has not
beaten it at all, because `stress-cropped-feet`'s criterion is negative and the honesty
boundary is the product.

**Honest cost, and why this is a real decision rather than a free extra.** GVHMR needs
its own environment — a third, on top of the two the repo already maintains (§3) — and
`docs/GATE-REPORT.md`'s seven-bug history is the calibration for what one new CV
environment costs here. Plus SMPL registration and download, plus checkpoint downloads,
plus the §6.1 annotation hours which this arm shares with the main plan. **Budget this
as days, not hours, and sequence it after §6.4's steps 2 and 3** — which cost almost
nothing and may well close the question before the arm is needed.

**If GVHMR wins by a lot,** the actionable output is *not* "adopt GVHMR". It is a
specific, transferable finding — most likely "the geometric solve mislabels
stationary-but-airborne feet, here are the frames" — which can be fixed in the
hand-rolled solve by adding the feature the learned model evidently uses. That is the
realistic value of this arm: it is a **diagnostic on the shippable solve**, not a
shortlist for adoption. Framing it that way also keeps it honestly inside the research
grant.

### 6.5 Suggested order

1. Add the contact-array debug side-channel to the solver output (§6.0). Nothing else is
   measurable without it.
2. Run plane temporal stability on `solo-01`, `solo-07`, `group-synced-01`. **No
   annotation needed, runs today, and `solo-07` alone will tell you whether the
   geometric solve is adequate.**
3. Synthesise the cropped variants and measure the `none` rate across crop heights.
   **No annotation needed, runs today.**
4. Only then spend the annotation hours: hand-label `solo-01` and `solo-02` and compute
   contact P/R and foot-sliding.
5. Source `stress-footwork`. Re-run 4 on it.
6. **Only if 2–5 leave the question open:** stand up the §6.4 EVALUATE-ONLY arm with
   GVHMR, on a research machine, on eval clips only.

Steps 2 and 3 cost nothing but compute and answer the recommendation's mind-changing
criteria #1 and #2 directly. If they pass, the learned-model question is closed, step 6
is never paid for, and this document's job is done.

---

## 7. One-paragraph answer, if you read nothing else

stepwise is a public product, so every non-commercial research licence is out for
anything that ships — and that removes **every** learned foot-contact model in the
literature except one, which is itself blocked by a non-commercially-licensed 2D
detector. What survives is scene-geometry depth models, which do not predict contact at
all. Meanwhile the pipeline already computes, per frame and per dancer, the exact eight
3D points a contact model would be asked to reason about: both ankles, both heels, and
both toe tips, at `mhr70` indices 13–20, plus the full mesh. **Keep the geometric solve.
The one thing worth holding in reserve is MoGe-2 — MIT code, MIT weights, already
vendored in this repo, already written as an adapter, already installable into the
existing environment — and reach for it only if `solo-07` shows the plane fit is
under-determined.**
