# World placement: where the dancer actually is

Investigation of OPEN-DECISIONS **E6** (global vertical placement of the body),
on branch `world-placement` = `bone-constraints` + `grounding`.

Every number here is measured on real clips from Modal volume
`stepwise-results` (`solo-01.npz`, `solo-07.npz`, `group-synced-01.npz`) and the
source video in `stepwise-eval`. Reproduce with
`python services/motion-api/world_placement_probe.py <clip.npz>`.

---

## 0. The headline: a settled fact handed to this pass is wrong

The brief, `GATE-REPORT.md`'s grounding addendum, E6 and the comment in
`api.py::_build_motion_result` all rest on one claim:

> the detector bbox bottom holds while the top swings, so the dancer got low in
> one spot; the reconstruction turns "got low" into "moved away".

**I looked at the video. The dancer moves away.**

`solo-01` is a single static shot of one dancer who begins ~10 m from the
camera by a garage door, dances there for ~5 s, **runs toward the camera
between t=5 s and t=7 s**, dances close for ~10 s, and retreats at the end. The
background (garage door, fence, signs, tree) is pixel-stable throughout, so the
camera never moves and there are no cuts.

That changes the interpretation of every previously-recorded number:

| observation | previous reading | what it actually is |
|---|---|---|
| `corr(bbox_height, cam_t.z) = -0.933` | proof the depth tracks the crop box | the pinhole relation `size ∝ 1/depth`, working correctly |
| `pred_cam_t.z` swings 3.18 → 10.93 m | an 7.75 m error | ~7 m of **real travel** |
| PnP against detector keypoints agrees at r = 0.983 and still swings 8.10 m | the per-frame body is inconsistent with a dancer standing still | two independent estimators agreeing about real travel |
| bbox bottom 769→899 px while top 159→635 px | feet planted, head dropping | a camera **0.15 m off the ground pitched 13° up**: an approaching dancer's feet move *down* the image |

The dancer was never standing still. The 8 m was not the error; it was the
choreography. The real defect is one line further downstream: **the export
throws the translation away.** `root_trajectory[].position` is the
character-local root, constant at `(0, 0.924, 0)` on all 291 solo-01 frames,
and `pred_cam_t` — which carries the travel — is never composed into it.

## 1. Method

Three pieces, each independently checkable.

**Rigid body.** `skeleton_constraints.enforce_bone_lengths` (branch
`bone-constraints`) makes all 117 real bones exactly per-clip constant — CV
6.05% mean / 24.58% max → 0.0000% — while preserving every bone's observed 3D
direction. On solo-01 it moves joints a median 3.0 cm (p95 10.7 cm). This is
the "117 metric rulers" the brief asked for.

**Per-frame placement.** A 3-DoF Gauss-Newton fit of the body's translation so
that 12 of the detector's COCO-17 keypoints reproject onto it, under the clip's
real pinhole intrinsics (`focal_length` from the npz, principal point at the
image centre; verified at 0.00 px median error by the previous pass). Rotation
and shape are already in the body, so translation is the whole unknown.
*Perspective* constrains depth; the weak-perspective crop fit `pred_cam_t`
comes from does not.

Fitting to the **detector's** keypoints, not the model's own, is the point: the
model's `pred_keypoints_2d` reproduce from `pred_keypoints_3d + pred_cam_t` at
0.00 px by construction, so fitting to them measures nothing.

**Temporal median, 5 frames (0.33 s), on the translation only.** Not a filter
stage, just the cheapest thing that works — see §4.

## 2. The test that matters: one floor, many contacts

The strongest free test is not a jitter statistic. The camera is static by
contract, the ground in all three clips is visibly flat, and solo-01's dancer
covers 8.7 m of depth. **A correct placement puts every genuinely-contacting
foot, across that whole depth range, on one plane with three free parameters.**
Nothing in the pipeline arranges that; each frame is placed independently.

Contacts are gated by an **image-stationarity cue**: with a static camera, a
planted foot is a stationary pixel, whatever the depth. Converted to m/s using
the frame's own depth so one threshold covers 3 m and 10 m. This cue is
independent of the reconstruction, so it cannot inherit the reconstruction's
depth error.

| placement | contacts | on one plane | RMS | \|resid\| p90 | contact depth span |
|---|---|---|---|---|---|
| `pred_cam_t` (today's only depth) | 111 | **58 (52%)** | 2.58 cm | **73.2 cm** | 2.62 – 4.58 m |
| PnP, raw skeleton | 111 | 92 (83%) | 1.97 cm | 5.7 cm | 2.26 – 10.70 m |
| **PnP, rigid skeleton** | 111 | **100 (90%)** | 2.22 cm | **4.9 cm** | **2.18 – 10.91 m** |

`pred_cam_t` cannot place the far contacts on the near floor at all — its
inlier set collapses to a 2 m depth window. The PnP placement explains contacts
from 2.2 m to 10.9 m with a single plane, and the residual does not drift with
distance: median signed residual **−0.0 cm at 2–4 m, +1.9 cm at 4–6 m, −0.9 cm
at 8–13 m**.

The recovered camera is a plausibility check nobody fed it: **0.15 m above the
floor, pitched 12.9° nose-up** for solo-01; 0.04–0.05 m / 17.8° for solo-07;
0.02–0.10 m for group-synced-01. All three clips were shot with a phone on the ground
pointing up, which is exactly what the footage looks like.

### Multi-dancer cross-check (group-synced-01)

Five dancers, one floor, placed completely independently.

| placement | pooled contacts | on one plane | RMS | dancers disagree about floor height by |
|---|---|---|---|---|
| `pred_cam_t` | 882 | 687 (78%) | 2.38 cm | **37 cm** (std 17 cm) |
| **PnP, rigid** | 914 | **856 (94%)** | 2.02 cm | **5 cm** (std 2 cm) |

Three dancers reconstructed and placed with no knowledge of each other agree on
where the ground is to 5 cm. That is not something a wrong depth produces.

### Where it fails

`solo-07` track 3 — 48 frames, 7–9 m away, at the edge of the shot — puts the
floor 53 cm off track 1's. Short, distant tracks are not trustworthy, and the
probe should decline them rather than average them in.

## 3. Part B, the crouch test (the assignment's primary metric)

Crouch frames identified from the **image only**: inside the in-place window
(t = 8–18 s, where the video shows the dancer on one spot) find frames where
the shoulder-to-ankle pixel stature collapses below 88% of upright while the
ankles hold their pixel row. Nine runs, 39 frames.

| crouch | stature | depth swing, `pred_cam_t` | depth swing, PnP rigid |
|---|---|---|---|
| 10.73–10.87 | 86% | 0.08 m | 0.22 m |
| 11.13–11.33 | 77% | **1.06 m** | 0.17 m |
| 11.73–12.07 | 80% | **1.85 m** | 0.30 m |
| 12.80–12.93 | 84% | 0.48 m | 0.15 m |
| 16.20–16.47 | 82% | 0.49 m | 0.30 m |
| 16.67–16.87 | 87% | **1.05 m** | 0.41 m |
| 17.20–17.27 | 81% | 0.23 m | 0.04 m |
| 17.47–17.73 | 69% | **1.63 m** | 0.12 m |
| 17.93–18.00 | 70% | 0.13 m | 0.17 m |
| **median** | | **0.49 m** | **0.17 m** |

**The bone-ruler placement passes the crouch test and `pred_cam_t` fails it.**
On the deepest crouch in the clip (69% of upright stature) `pred_cam_t` slides
the dancer 1.63 m backwards; the rigid-body PnP moves 0.12 m. Corresponding
world horizontal drift over the same crouches: median 0.17 m, max 0.42 m — not
zero, but some of that is the dancer genuinely shifting weight.

Whole-clip frame-to-frame depth jitter, same three estimates, inside the
in-place window:

| | range in window | per-frame \|dz\| median | p95 | max |
|---|---|---|---|---|
| `pred_cam_t` | 2.19 m | 0.198 m | 0.991 m | 1.860 m |
| PnP raw body | 1.44 m | 0.089 m | 0.224 m | 0.432 m |
| **PnP rigid body** | 1.46 m | **0.073 m** | **0.181 m** | **0.330 m** |

Making the skeleton rigid buys an 18% cut in per-frame depth jitter, a 24% cut
in the worst frame, and a drop in median reprojection error from 13.84 px to
11.31 px. It is a real but **modest** gain; almost all of the improvement over
`pred_cam_t` comes from using perspective instead of weak perspective. The
rigid skeleton's larger contribution is to the floor fit — 8 more contacts on
the plane (92 → 100 of 111).

## 4. Part A, contact-gated foot locking: measured, and **do not ship it**

Implemented as specified: re-anchor only a foot the image says is genuinely
stationary; on release, freeze the correction rather than zero it, so flight
stays ballistic.

| variant | planted-foot slide/frame | reprojection error | lowest foot vs floor |
|---|---|---|---|
| PnP rigid, raw | 11.7 cm (p90 17.0) | **11.31 px** | −0.0 cm (p90 5.7) |
| **+ 5-frame median on translation** | **5.0 cm (p90 7.5)** | 13.18 px | +0.3 cm (p90 6.7) |
| + contact-gated lock | 0.0 cm (p90 4.6) | **43.69 px** | **+13.3 cm** (p90 18.5) |
| + smooth + lock | 0.0 cm (p90 6.3) | 37.31 px | +15.6 cm (p90 23.9) |

**Locking works on its own metric and breaks everything else.** It drives the
planted-foot slide to zero, and in exchange the body stops agreeing with the
video — median reprojection error nearly quadruples, 11.3 → 43.7 px — and the
dancer ends up floating a median 13 cm above the floor the same placement had
been sitting on.

The cause is accumulation, and it is measurable: the correction is a random
walk over 30 re-anchoring events, reaching a **median 37 cm, max 53 cm** of
accumulated offset. Only 67 of 291 frames have a gated contact, so 77% of the
clip is carrying a frozen correction that was fitted somewhere else.

This is §7h applied to the fix rather than to the bug: a body that has visibly
left the person in the video is a confident lie, whatever its feet are doing.

**The lazy alternative wins.** A 5-frame median on the translation cuts the
planted-foot slide by 57% (11.7 → 5.0 cm) for 1.9 px of reprojection error and
keeps the feet on the floor. Ship that; revisit locking only if a real contact
model arrives.

### Contact precision, measured explicitly

There is no contact annotation for these clips, so I rendered the samples and
labelled them by eye from the source video (both ankles marked, whole lower
body visible; sheets in the working set, not committed).

| detector | samples with weight > 0.5 | visually in contact | note |
|---|---|---|---|
| `grounding.detect_foot_contacts` (world space) | 9 of 564 visible | **9/9** | all but one inside a single 1.1 s window at t=0.67–1.73 s |
| image-stationarity cue | 36 of 564 visible | **30–35 of 36** (5 ambiguous) | spread over t=3.7–18.7 s |
| random sample of visible foot-samples | 36 | 24 clear / 4 clear non-contact / 8 ambiguous | **base rate ≈ 67–89%** |

Two honest caveats that matter more than the headline:

1. **The base rate is high.** On a clip where feet are on the ground ~75% of
   the time, "precision 9/9" is barely above chance. Precision is *not* the
   binding constraint here.
2. **Recall is the binding constraint.** The existing world-space detector
   finds 9 contacts in 291 frames and puts 8 of them in one second — which is
   exactly why `grounding.py` refuses with `contacts_not_spread_over_clip`.
   The image cue finds 4x more and spreads them over the clip, and still misses
   most of the real contacts (below).

### Slide preservation

Of the 302 foot-samples that are geometrically on the fitted floor (within
4 cm), **210 (70%) are moving faster than 0.30 m/s in the image** — median
0.96 m/s, p90 2.53 m/s. In this style, a foot on the ground and moving is the
normal case, not the exception.

The image-stationarity gate scores those ~0, so they are never anchored and
their world translation survives untouched: a sliding foot translates a median
12.4 cm per frame (1.86 m/s) in world space, unmodified. **Slides are preserved
by construction** — but the same property means the gate finds fewer than a
third of the real contacts, which is the ceiling on any locking scheme built
on it.

### Jumps

Flights found by "lowest foot more than 6 cm above the fitted floor", ≥3 frames:

| flight | peak | fitted vertical acceleration | parabola residual |
|---|---|---|---|
| 0.13–0.53 s | 21 cm | −3.57 m/s² | 3.1 cm |
| 5.00–5.20 s | 29 cm | −15.19 m/s² | 4.4 cm |
| 5.33–5.53 s | 21 cm | −7.37 m/s² | 4.6 cm |
| 5.87–6.00 s | 20 cm | −15.67 m/s² | 3.3 cm |

Four flights, all in the run-in, all with negative fitted acceleration of the
right order (gravity is −9.81 m/s²) and a 3–5 cm parabola residual. The arcs
are real, not flattened, and not jitter — jitter would scatter the sign. The
spread on g (−3.6 to −15.7) is the honest accuracy of this placement over a
0.2 s window at 15 fps, not a claim of ballistic fidelity.

## 5. What is still not pinned: absolute scale

The bone rulers fix *relative* depth; the overall metric scale rides on the
reconstruction's body size. Two checks:

* The rigid skeleton's head-to-foot span is **1.73 m (p90)** — a plausible
  adult dancer, so the scale is not wildly off.
* Rescaling the whole placed body by ±10% barely moves the floor fit: RMS
  2.03 → 2.25 cm, camera height 0.14 → 0.17 m. **The floor test cannot detect a
  10% scale error**, exactly as the brief predicted.

One weak prior closes it — a human-height prior, or the fact that all three
clips put the camera within 0.15 m of the ground, which is a phone-on-the-floor
prior a product can state.

### Conditioning caveat that limits every floor number above

The camera is ~0.15 m above the floor and looks along it, so a viewing ray to a
foot is nearly *parallel* to the floor plane: for solo-01, `n·r = 0.024`, i.e.
**1 cm of foot-to-floor distance costs ~42 cm of depth**. The plane fit is a
strong *necessary* test — `pred_cam_t` fails it outright — but it is weak at
certifying depth to centimetres. The planted-foot test (§4) and the crouch test
(§3) are the ones that measure depth directly, and they are the ones with the
larger error bars.

## 6. Licensing: no new model is needed

MoGe-2 was the proposed external metric-scale source. `docs/research/grounding-models.md`
§2.9 already verified MIT code and MIT weights (both HF cards checked
separately), and already flagged the gap: **the training-data axis is
unverified** — "I cannot tell you what MoGe-2 was trained on. Before adopting,
someone should check the MoGe-2 paper's dataset table against each dataset's
terms." That remains open and I did not close it.

**It does not need closing for this.** Everything in this document uses code
and data already in the repo: the vendored reconstruction, the vendored
detector's keypoints, the clip's own FOV estimate, and `skeleton_constraints`.
No new weights, no new licence surface. If absolute scale later needs an
external anchor, the MoGe-2 training-data check becomes a prerequisite again.

## 7. Recommendation for E6

**E6's two options were "proper per-frame world placement (WHAM/GVHMR-shaped)"
or "accept a floorless product". There is a third, and it is already in the
repo.**

Recommended, in order, each independently shippable:

1. **Correct the record first.** The comment in `api.py::_build_motion_result`
   and E6 both assert that solo-01's dancer barely travels. The video says
   otherwise. Nothing else should be built on top of that claim.
2. **Compose the translation into `root_trajectory`.** This is the actual
   defect: the pipeline has a depth estimate and the export discards it. The
   contract already has the field, in metres, in a world space it also puts
   `floor_plane` in.
3. **Place with the perspective fit, on the rigid skeleton, with a 5-frame
   median.** Measured: floor inliers 52% → 90%, worst-crouch slide 1.63 m →
   0.12 m, five dancers agreeing on one floor to 5 cm instead of 37 cm.
4. **Then let `grounding.py` decide again**, in camera space rather than the
   character-local frame, with the tilt prior removed (the real floors here are
   13–18° off +Y *because the camera is on the ground*, which is a true fact
   about the input, not a failure). On this evidence solo-01 would fit a floor
   at 2.2 cm RMS with contacts spread across the whole clip — the gate that
   currently refuses.
5. **Do not ship contact-gated locking.** Measured above: it trades a 12 cm
   foot slide for a 37 cm body-position lie.

What would make me wrong, and what I could not verify:

* **I could not verify this renders correctly.** No GLB was exported with a
  moving root and no viewer was opened. Everything here is measured on arrays.
* **Absolute scale is unverified to better than ±10%** (§5).
* **Short/distant tracks are not trustworthy** — solo-07 track 3 (48 frames at
  7–9 m) disagrees with track 1 about the floor by 53 cm. A minimum-frames and
  maximum-depth gate is needed before this is a solve rather than a probe.
* **Contact ground truth is my own eye**, on 81 labelled samples from one clip.
* **Only 3 clips**, all shot with a phone near the ground. A chest-height or
  tripod camera would have better-conditioned rays and is untested.
* **The bone rulers helped less than expected.** They are a clear win on the
  floor fit and a modest one on jitter; the large win is perspective over weak
  perspective. If a successor is choosing where to spend effort, spend it on
  the per-frame translation, not on more skeleton rigidity.

## 8. Open items still open

* **E6** — this document is a recommendation with measurements, not a decision.
  It touches `api.py`'s export and `grounding.py`'s coordinate frame; per
  `docs/AGENT-BRIEFS.md` standing rule 5 the grounding core belongs to the
  builder.
* **B3** (what a floating body looks like) — still live, but its urgency drops
  if (2)–(4) land, because clips would stop being floorless.
* **MoGe-2 training-data licence** (§6) — still unverified, still not needed.
* **E3** (mesh-region masking) — untouched by this pass.
