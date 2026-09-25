# Body shape in the 3D lesson: keep it, drop it, or coarsen it?

Tracker item 28 (`README.md`). Written 2026-09-25 against `main` at `429e331`. **Not legal advice.**
Nobody who wrote this is a lawyer. It says which risks look real, what each option costs, and
which questions need counsel. The measurements are from public lesson files and were rerun for this
doc (§2).

---

## Summary (one screen)

**What the GLB actually carries.** Two different things get called "the dancer's body shape". The
decision is only about the first one.

| | What it is | In every GLB since | What it changes on screen |
|---|---|---|---|
| **Surface shape** | 45 MHR `shape_params`, median over the clip, baked into the rest mesh (`_character_with_shape`) | `8f4ae48` (2026-09-18) | Only soft-tissue girth. Measured: mean surface change 0.03 to 0.48 cm per dancer, 3.5 cm at most, mostly torso depth (chest 21.8 to 28.3 cm across dancers vs 28.2 cm for the mean body) |
| **Skeleton size** | Per-dancer bone lengths (MHR `scale_params`, inside `skel_state`, held constant per clip by `skeleton_constraints.py`) | Always, before and after `8f4ae48` | Limb lengths, stature, reach, where hands and feet land. Measured: legs 0.90 to 1.02 and arms 0.73 to 1.01 of the mean body's |

**Findings.**

1. **A generic surface changes nothing about the moves.** Surface shape is a mesh corrective.
   The animation is bit-identical with and without it (GATE-REPORT, shape addendum). Hands and
   feet land in the same place. The learner loses a slightly slimmer or fuller torso on a flat
   toon-shaded body drawn over the real video.
2. **Option (d) is the same as (b) here.** Using the estimated shape "only server-side to place
   joints" is not possible, because shape never places joints. Joints come from the skeleton.
3. **Proportions that matter for learning live in the skeleton, and they were always shipped.**
   R&P §2's "stock body, motion not proportions" was never fully true. A generic *skeleton*
   would move wrists and feet 2 to 7 cm on average (up to 16 cm) relative to the pelvis. That
   breaks the overlay on the dancer's video and moves foot contacts.
4. **Legally, neither the surface nor the skeleton is on BIPA's or CUBI's closed lists.** Every
   broader law (CCPA, Colorado, Washington MHMDA, GDPR Art. 9) turns on identification. Colorado's
   "can be processed" to identify is the only capability test, and so it is the closest fit.
   Anthropometrics can help re-identify a person, but the motion itself is the stronger
   identifier (94% of 55,541 VR users from 100 s of head and hand motion). The motion is the
   product. Dropping the surface shape removes the one artifact that is a **stored,
   time-invariant, per-person shape fit**. R&P §4e and §6.8 already said not to keep that kind of
   artifact ("per-frame pose yes, persisted per-person shape fit no"). It does not change the
   overall exposure much.

**Recommendation.**

- **Beta (now):** make the surface generic again. That means not calling `_character_with_shape`,
  re-exporting existing lessons, and no longer writing the vector to `export-manifest.json`. Keep
  the dancer-sized skeleton. Change `/privacy` to say what the body is: "a 3D body for each
  dancer, sized to their estimated limb lengths; the surface is a standard body." The cost is
  about 1 line of code, a re-export of roughly a dozen lessons, and one copy line. The learning
  loss is close to zero. If the owner wants to keep the shaped surface for beta, option (a)
  (disclose it on `/privacy`) is defensible, but do it this week, because `/privacy` is stale
  today.
- **Public launch:** keep generic surface + dancer skeleton. Ask counsel one question
  (§5). Do not build bucketed shapes (c) or per-lesson opt-in (e). Revisit only if a feature ever
  shows the learner their *own* body, or if anything matches or links people across lessons.

---

## 1. What the code does

- **Estimator output.** SAM-3D-Body returns, per person per frame, `shape_params` (45),
  `scale_params` (28), `expr_params`, `pred_vertices` and `skel_state` (127 × 8: translation,
  quaternion, scale). `process_clip.py` drops `pred_vertices` and `expr_params`
  (`UNREAD_PER_FRAME_KEYS`). It keeps `shape_params` and `skel_state` in the npz.
- **Skeleton size.** `scale_params` are folded into `skel_state` by the estimator.
  `skeleton_constraints.constrain_clip` fixes each bone to one per-clip target length (the
  per-frame wobble was up to 24.6% CV). The GLB's node translations therefore carry one constant
  set of bone lengths per dancer. This was the case before `8f4ae48` too. GATE-REPORT, shape
  addendum: "the skeleton is already dancer-scaled".
- **Surface shape.** `modal_app._export_clip_gltf` takes the per-dim median of the per-frame
  `shape_params` and computes `rest + Σ shape_k · shape_vectors_k`. That is transferred to the
  lod3 mesh by nearest vertex (`_character_with_shape`), and the vector is written to
  `{clip_id}.export-manifest.json`. GATE-REPORT measured: "Shape moves only the mesh": rest joints
  differ by 0.0000 cm, and animation channels by 0.000e+00.
- **Served JSON.** `MotionResult.persons[].shape_params` carries only `source`
  (`well_observed_frames` or `default_assumed`), not the vector (`motion_result.py`). Joint samples
  are local rotations. `joint_hierarchy.rest_translation` is the mean skeleton, the same for
  everyone. So per-dancer bone lengths and the shaped surface reach the browser **only through the
  GLB**.
- **Viewer.** `Stage3D.tsx` loads the GLB with `useGLTF` and plays its animation with flat
  toon materials. Nothing in `apps/web` reads `shape_params.source`.
- **Recoverability.** The shape basis is linear, so anyone holding the MHR model can
  least-squares the 45 numbers back out of a shaped GLB. Serving the mesh is, in effect, serving
  the vector.

## 2. Measurements on real lessons

**Method.** On 2026-09-25 I downloaded 12 public lessons' MotionResults and 20 GLBs from the
public site (`/api/jobs/job_<id>/result`, `/api/assets/<glb_asset_id>`), the same bytes any browser
gets. Lesson ids are not listed here (tracker item 29). One GLB had zero-norm quaternions in its
animation and was excluded. That leaves 19 dancer tracks. The script parsed each GLB with
`pygltflib`:

- Mean skeleton: bind pose, from `inverseBindMatrices`. The lod3 skeleton is the mean MHR body.
- Dancer skeleton: bone lengths from full forward kinematics of the animation, median over 40
  frames.
- "Generic skeleton" test: keep every bone's world direction on every frame, set its length to
  the mean body's, rebuild from the pelvis, and measure how far the wrists and feet move relative
  to the pelvis.
- Surface: slab depths on the rest mesh (chest y 1.2–1.4 m, hip y 0.9–1.1 m, the same slabs as
  GATE-REPORT), plus vertex-wise distance to the cohort's mean surface (18 meshes with the same
  topology).

Two of the 20 GLBs have exactly the mean body's slabs (28.21 / 39.36 cm, matching GATE-REPORT's
"before" row). They were exported before `8f4ae48` and are **not** shaped. So "every lesson is
shaped" is not quite true. It is true of every lesson exported since 2026-09-18.

**Results (18 shaped tracks for surface, 19 tracks for skeleton).**

| Measure | Range across dancers | Mean MHR body |
|---|---|---|
| Chest depth (surface) | 21.8 – 28.3 cm, median 25.6 (−9%) | 28.2 cm |
| Hip depth (surface) | 36.5 – 39.6 cm | 39.4 cm |
| Surface distance from cohort mean, per dancer | mean 0.03 – 0.48 cm, max 0.2 – 3.5 cm | — |
| Pairwise surface difference between dancers | median 0.18 cm, max 0.70 cm (mean over vertices) | — |
| Stature chain (shin + thigh + spine + neck + head) | 0.94 – 1.02 × mean | 1.00 |
| Leg (thigh + shin) | 0.90 – 1.02 × mean | 1.00 |
| Arm (upper + forearm + wrist) | 0.73 – 1.01 × mean | 1.00 |
| Wrist/foot shift if retargeted to the mean skeleton | mean 2.1 – 6.8 cm, max 2.9 – 15.9 cm | 0 |

**What that says.**

- **Surface shape is small.** Every estimated dancer is at or below the mean body's torso depth.
  The difference shows in a side view as a slimmer torso and in nothing else. At the viewer's
  size and with flat shading, a 2 mm average change is below what anyone would notice.
- **The skeleton is where dancers differ.** Leg and arm ratios spread by 10–27%. Retargeting to a
  mean skeleton moves the hands by centimetres. That is the size of error a learner can see
  ("reach higher", "hands in front of the hips or at them").
- **The estimates are noisy.** Three lessons show arms at 0.73–0.79 of the mean (upper arm 18.5–19.8
  cm against 25.7). That is anatomically unlikely, and it matches the known SAM-3D-Body arm
  length bias (`skeleton_constraints.py` header). "Estimated proportions" means estimated. As an
  identifier it is weak and biased. As a teaching aid it still matches the video, because the
  pose was fitted to the image with those bones.
- Those three lessons also have near-identical skeletons (leg 1.006–1.019, arm 0.728–0.786,
  stature 1.015–1.017). I do not know whether they show the same person. If they do, it shows
  why anthropometrics count as linkable across lessons.

## 3. Learning value: does an individualised body help?

**Evidence for "looks like someone" helping learning is about the learner's own likeness, not the
teacher's proportions.**

- Fitton et al., CHI 2023 (n = 97; screen and VR): an instructor avatar matched to the *learner*
  on gender, skin tone and hair colour gave more vivid imagery of the dance moves than a
  dissimilar avatar
  ([ACM](https://dl.acm.org/doi/full/10.1145/3544548.3580944),
  [Bath](https://researchportal.bath.ac.uk/en/publications/dancing-with-the-avatars-minimal-avatar-customisation-enhances-le/)).
  Body proportions were not manipulated.
- Waltemate et al., IEEE TVCG 2018: personalised (scanned) self-avatars raised body ownership and
  presence in VR
  ([ResearchGate](https://www.researchgate.net/publication/322583684_The_Impact_of_Avatar_Personalization_and_Immersion_on_Virtual_Body_Ownership_Presence_and_Emotional_Response)).
  Again this is the user's *own* body, in an embodied first-person setup. Stepwise shows a third
  person's body on a phone.
- I found no study showing that rendering a *demonstrator's* soft-tissue girth (as opposed to a
  standard surface on the right skeleton) improves imitation. Absence of evidence, stated as that.

**Evidence that proportions change the motion is about the skeleton.** Motion retargeting exists
because the same joint angles on different segment lengths put hands and feet in different
places, and contacts and reach have to be re-solved (Gleicher, SIGGRAPH 1998,
[paper](https://graphics.cs.wisc.edu/Papers/1998/Gle98/)). The measurement above shows the size of
that effect here: 2–7 cm on average and up to 16 cm. Stepwise draws the body **over the real
clip** (`copy.ts`: "3D body on your video"), so a generic skeleton would also visibly misalign
with the video.

**Answer.** The individualised *skeleton* has real learning value: reach, levels, where the hands
land, and overlay alignment. The individualised *surface* has close to none for learning. Its value
is cosmetic ("that's her silhouette"), and the evidence does not support a learning claim for it.
If likeness is ever wanted for learning, the research points to making the demonstrator
resemble the **learner**, which is a different feature and a different consent picture.

## 4. Legal and privacy

Short version: the analysis in R&P §4–5 holds, with two corrections. First, the proportions were
always partly present, through the skeleton. Second, the surface bake adds a stored per-person
shape fit that R&P said to avoid.

| Law | Does an estimated shape vector or shaped mesh qualify? | Notes |
|---|---|---|
| **BIPA** (Illinois), [740 ILCS 14/10](https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=3004&ChapterID=57) | **Unlikely.** The closed list is retina/iris, fingerprint, voiceprint, hand or face geometry. It excludes "physical descriptions such as height, weight". Body girth and limb lengths sit closer to the exclusion than to the list | The identification requirement is growing: *Zellmer v. Meta* (9th Cir. 2024), *Martell v. X* (N.D. Ill. 2024); *Colombo v. YouTube* is the counterweight (R&P §4b). The 2024 single-violation amendment applies retroactively (*Clay v. Union Pacific*, 7th Cir. 2026). In 2025 BIPA suits were still about fingerprints and faces; I found no body-geometry case ([NLR 2025 review](https://natlawreview.com/article/2025-year-review-biometric-privacy-litigation)). The face mesh region is the only hook, and the shaped mesh has no face detail beyond the mean head at lod3 resolution |
| **CUBI** (Texas), Bus. & Com. Code §503.001 | **Unlikely.** Same closed list, with no photo exclusion and AG-only enforcement | TRAIGA (HB 149, in force 1 Jan 2026) exempts AI processing not used to uniquely identify someone, and treats media the person made public differently ([Covington](https://www.insideprivacy.com/artificial-intelligence/texas-enacts-ai-consumer-protection-law/)) |
| **Washington** RCW 19.375 / MHMDA RCW 19.373 | **No / unlikely.** 19.375 excludes data "generated from" video. MHMDA needs consumer health data that "identifies a consumer" | R&P §4d |
| **CCPA/CPRA**, [Civ. Code §1798.140](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CIV&sectionNum=1798.140.) | **Probably not "biometric information".** The definition covers physiological characteristics "used or … intended to be used … to establish individual identity" (gait is named as an example). We neither use nor intend that. It is **sensitive** PI only when processed "for the purpose of uniquely identifying" | Thresholds (revenue, 100k consumers) not met. If they were, it is still ordinary personal information: notice plus the existing deletion path |
| **Colorado** HB24-1130 (amends the CPA, from 1 Jul 2025) | **The closest fit.** A "biometric identifier" is data from processing physical characteristics that "can be processed for the purpose of uniquely identifying". It applies to any controller that processes biometric identifiers, regardless of volume ([Venable](https://www.venable.com/insights/publications/2024/06/colorado-amends-state-privacy-law-to-include), [leg.colorado.gov](https://leg.colorado.gov/bills/hb24-1130)) | "Can be processed" is a capability test, and anthropometrics can in principle help re-identify. The duties are a written retention policy, a deletion schedule, and notice, all of which exist or are cheap (tracker 7, 12). AG enforcement only |
| **GDPR / UK GDPR** Art. 4(14), Art. 9(1) | **Personal data, not special category.** Art. 9 needs processing "for the purpose of uniquely identifying". The ICO's 2024 guidance ties special-category status to that purpose ([ICO](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/biometric-data-guidance-biometric-recognition/)) | Data minimisation (Art. 5(1)(c)) is the live point. A time-invariant shape fit that adds no learning value is hard to justify under minimisation. That is an argument for (b) |

**Is body shape re-identifying?** Yes, somewhat, and less so than motion.

- Skeleton-based re-identification uses exactly limb lengths, height, upper/lower body ratio, and
  chest and hip size as features. Early Kinect work combined them with motion (Barbosa et al.,
  ECCV-W 2012; Munsell et al., ECCV-W 2012,
  [Springer](https://link.springer.com/chapter/10.1007/978-3-642-33885-4_10); survey
  [arXiv 2401.15296](https://arxiv.org/abs/2401.15296)). Anthropometrics alone are "soft
  biometrics". They narrow a population and do not single someone out at scale, especially from
  a noisy monocular estimate (§2).
- Motion is the strong identifier. Nair et al., USENIX Security 2023, identified 55,541 VR users
  at 94.33% from 100 s of head and hand motion
  ([USENIX](https://www.usenix.org/conference/usenixsecurity23/presentation/nair-identification)).
  Stepwise publishes full-body motion by design. Removing the surface shape does not change
  whether a lesson could in principle be linked to a person. The source video, which is public and
  credited, identifies them far better anyway.

**Facts that help, whichever option is chosen.** No matching, search or identification feature
(tracker 20). Public source videos with a credit line. Per-lesson storage with no cross-lesson
index. Deletion on request and a 180-day retention ceiling (tracker 1, 7). Lessons unlisted and
`noindex`.

**Facts that hurt.** Every viewer's browser downloads the GLB. Browser download is
"disclosure". It is not identification, but it means we cannot pull the data back. `/privacy` does
not say the body is shaped or sized to the dancer. That is the certain problem: a stale privacy
statement is an FTC Act §5 and state UDAP issue regardless of the biometric question (SR §1).

## 5. Options

Effort is in this codebase. "Re-export" means running the existing standalone
`export_clip_gltf(clip_id)` over each lesson's npz. Asset names are content-hashed, so browsers
pick up the new GLB, and `_prune_old_versions` removes the old one.

| Option | Learning impact | Legal risk | Engineering | Re-export? |
|---|---|---|---|---|
| **(a) Keep estimated surface + disclose on `/privacy`** | None (status quo) | Low. Fixes the stale-notice problem. Leaves a stored per-person shape fit in every GLB and in `export-manifest.json`, against R&P's own design rule | One copy line in `copy.ts` `privacy`, plus an R&P §2 edit | No |
| **(b) Generic surface for everyone** (keep dancer skeleton) | ≈ none. Torso girth becomes the mean body's; hands, feet and overlay are unchanged (animation bit-identical) | Lowest practical. No shape fit anywhere. The skeleton still carries limb lengths, which have to be disclosed | Skip `_character_with_shape` (or pass zeros), stop writing `shape_params` to the manifest, and add `shape_params` to `UNREAD_PER_FRAME_KEYS`. Decide the `source` label: `default_assumed` becomes the honest value for the surface | Yes, every lesson exported since 2026-09-18 (about a dozen today). CPU only |
| **(b′) Generic skeleton too** (retarget to mean bone lengths) | **Real loss.** Hands and feet move 2–7 cm on average (up to 16), the overlay no longer sits on the dancer, and foot contacts slide | Lowest on paper, but motion still identifies (§4) | Medium: reuse `skeleton_constraints.enforce_bone_lengths` with mean targets, then re-solve ground contact | Yes |
| **(c) Coarsened: few body-type buckets or height-only** | Buckets: tiny, since the surface barely matters. "Height-only" does not apply to the surface: stature is not in the 45 shape dims, it is in the skeleton. A uniform skeleton scale would keep stature but lose limb ratios (same loss as b′ for arms) | Buckets still carry a coarse per-person fit and add little over (b) | Clustering over the manifests, a bucket table, re-export. More work than (b) for no gain over it | Yes |
| **(d) Shape server-side only, generic mesh shipped** | Same as (b). Shape never places joints in MHR | Same as (b) | Same as (b) | Yes |
| **(e) Uploader opt-in per lesson** | Per lesson: (a) or (b) | Weak. The uploader is usually not the dancer (link lessons), so their opt-in is not the data subject's consent | UI toggle, API field, job-meta, re-export on toggle, and copy. Most work of all | On toggle |

## 6. Recommendation

**Beta: (b), generic surface, dancer-sized skeleton, plus an honest `/privacy` line.**

1. In `_export_clip_gltf`, stop baking the surface (keep the guard code or delete it; one call
   site). Stop writing the vector to `export-manifest.json`. Add `shape_params` to
   `UNREAD_PER_FRAME_KEYS` so the npz stops keeping per-frame shape. Set `shape_params.source`
   to `default_assumed`, which is what the viewer's honesty label should say for a standard
   surface. Nothing in `apps/web` reads it today.
2. Re-export existing lessons (all are recent, and there are few).
3. `/privacy` "What we build from it": *"a 3D body for each dancer, sized to their estimated
   limb lengths (the body's surface is a standard shape, not theirs)"*. Update R&P §2 finding 2 to
   say the skeleton was always dancer-sized.

Why (b) over (a): it removes the one artifact that is a per-person shape fit, at almost no cost
and with no visible learning loss. The skeleton, which is what matters for learning, stays. If the
owner prefers (a) for beta, it is defensible, but only with step 3 done at once.

**Public launch: same as beta. No new mechanism.** Before sign-up opens, add one question for
counsel to tracker item 18: *"Under the Colorado Privacy Act as amended by HB24-1130 and CCPA §1798.140(c), is a per-dancer
set of estimated bone lengths, used only to animate a lesson and never to identify, a 'biometric
identifier', and if so is a retention policy plus notice sufficient?"* Revisit the decision if any
of these happen: a feature compares or links people across lessons, a feature shows the learner
their own shaped body (then it is the learner's data and consent is possible), shape or size is
sold or used for ads, or a paid tier launches.

## 7. What I could not verify

- The Fitton et al. full text (paywalled). I used the abstract and the Bath portal summary.
- Whether the three lessons with near-identical skeletons show the same person.
- I did not read the per-lesson shape vectors from the Modal Volume, so vector norms are not
  reported. The surface effect was measured from the public meshes instead.
- No court has ruled on a body mesh or bone-length vector under any statute listed here (as of
  September 2026, from the 2025 year-in-review sources above).
