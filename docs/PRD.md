# PRD 02 (v4, final): the dance learning platform

Working name `stepwise`; public name chosen before launch (`NAMES.md`). Design system in `DESIGN.md`. Concepts in `CONCEPTS.md`.

This is the build document. It follows two Codex adversarial reviews and four source-code verification passes, the last of which corrected three assumptions that would have cost weeks. **The single most important change in v4: the first ~20 hours are a separately-funded feasibility gate, and the remaining ~70 are not committed until it passes.** Codex's verdict was "go with changes — fund the feasibility gate first." A fifth pass then resolved the licensing question by removing its cause: **Ultralytics is dropped and RTMO replaces it**, which deletes AGPL from the dependency tree entirely and happens to be faster and more accurate.

---

## 1. What this is

Upload a short dance clip filmed from one front camera. Get the dancer back as a clean stylized 3D body you can orbit, mirror, slow, loop, and step through part by part and count by count, alongside the original video.

**Learner:** a casual person who saw a dance online and wants to learn it. **Learn** means watch and follow — no camera, no scoring in v1. Free, cohort-first behind invite, then public. Repo public from day one — **your choice, not a licence requirement** (the SAM License's citation clause covers research publications only).

**Positioning:** *see the dance from any angle.* Precisely — and the precision cuts both ways:

- **A dancer turning away is tracked, and orbiting to see them is a legitimate claim.** A body facing away is still a visible body; the rotation is followed through the turn. This is the product's single most useful capability (in the flat video you cannot see what their arms are doing when their back is turned) and it must not be undersold out of excess caution.
- **What the model could not see, it did not recover.** Occluded parts (blocked by another dancer, or by the dancer's own torso) and out-of-frame parts are *estimated or absent*, marked as such in the contract and rendered as such. Never imply a recovered moment.

Front view is camera evidence; other viewpoints are synthesised from a tracked body and labeled "estimated". Back-facing frames carry higher depth ambiguity and should skew toward `uncertain` rather than `absent`. See `DESIGN.md` §7h for the full three-case table.

**Why it can exist now:** the March 2026 attempt stalled on a license gate (every good method depended on SMPL, non-commercial). Meta's SAM 3D Body + MHR (Apache body model) removed it. **Why nobody has it:** DanceFlowW is a solo-dev iOS app, zero ratings, 2D-class skeleton; Dance.AI markets "any link → 3D avatar" but its live UI has no upload control and it is SMPL-based; DanceSculpt proved the value in an academic study and never shipped.

---

## 2. The feasibility gate (~20h, do this before committing the rest)

Everything here is designed to fail fast and cheap. Order matters — each step blocks the next.

**G1. Request the gated weights before renting anything.** `facebook/sam-3d-body-dinov3` on HuggingFace is gated: login plus agreeing to share contact info under Meta's Privacy Policy. Approval is not instant and is a hard blocker. Do it first, today.

**G2. License: resolved by dropping Ultralytics — what remains is a packaging task.** The AGPL/SAM conflict was real. Verified against both license texts and FSF's published positions: the SAM License imposes at least seven "further restrictions" that AGPL-3.0 §7 does not permit — ITAR/military field-of-use limits, a citation requirement (FSF states explicitly that citation requirements are additional restrictions), a reverse-engineering ban, mandatory pass-through of the SAM Agreement, patent retaliation reaching model *outputs*, unilateral amendment by Meta, and California exclusive venue. It is not AGPL-compatible in either direction, and it is neither OSI-approved nor SPDX-listed. Worse, FSF's own guidance holds that modules in one Python interpreter share an address space and are "almost surely combined" into one program — so Fast-SAM-3D-Body's MIT label does not survive it importing both.

**Dropping `ultralytics` removes AGPL from the tree entirely and the conflict disappears.** That is now the plan (see the pipeline table). No separate-process gymnastics, no lawyer needed for that question.

What remains is SAM License *compliance*, which is bookkeeping, not a blocker:
- Keep SAM Materials in a clearly marked directory with a verbatim copy of the Agreement (§1.b.i requires derivatives carry it).
- State the ITAR/military prohibition and the citation obligation in the README.
- **The repo cannot honestly be labeled MIT or Apache overall.** Ship your own code MIT; the SAM-derived parts stay under the SAM License forever. Say so plainly in the README.
- Standing business risk: **§8 lets Meta amend the terms unilaterally, effective immediately.** Pinning a commit does not neutralize it, because continued use accepts the amendment. This is a real exposure to know about, not one to paper over.

**G3. Build TWO environments — they are incompatible, and this is the biggest install trap.** Fast-SAM-3D-Body's `setup_env.sh` pins **Python 3.11, Torch 2.5.1/cu124, CUDA 12.4** (Detectron2 compiles against it). But `pymomentum` v0.1.114's wheels target **Python 3.12/3.13 with Torch 2.8 and cu129**. "Python ≥3.11" describes the project's general support, *not* these wheels. Installing both in one environment will fail or produce a native-library mismatch.

**So: keep SAM inference on its pinned stack, and do glTF export in a separate environment, exchanging plain arrays (npz/JSON) between them.** Design for that boundary from the start — retrofitting it later means reworking the export path.

Two more install landmines: Detectron2 fails if the image lacks `nvcc` or builds against the wrong toolkit (use CUDA 12.4 dev tooling, set `CUDA_HOME` to match, and compile only after Torch is final). And **`setup_env.sh` still installs Ultralytics, TensorRT, and SMPL-X** — choosing RTMO does not remove them; edit the script.

**Version every reproducible image** and record which GPU model it was built for.

**G4. Eager inference first.** Get a correct result before a fast one. TensorRT engines are **not portable** — they must be built on the exact deploy GPU and TensorRT version, and rebuilt if the rented GPU model changes. Detector TensorRT alone moves the pipeline 3.50 → 3.58 FPS, so it earns nothing on day one. Skip it in the gate.

**G5. Prove the detector adapter (~30 lines).** Fast-SAM-3D-Body's estimator accepts external *boxes* but not external *keypoints* — passing boxes alone skips its detector and leaves the wrist keypoints unset, breaking the fast hand path. The fix is small and verified: write an RTMO wrapper exposing `run_human_detection()` that returns `{"boxes": (N,4), "keypoints": (N,17,3)}`, and register it in `tools/build_detector.py` alongside the existing `vitdet`/`yolo`/`yolo_pose` entries. The hand-box code itself needs no change — it is pure numpy keyed to COCO-17 wrist indices. Gate: one clip through RTMO → adapter → estimator with hands populated, no double detection, and correct coordinates (full-frame vs. crop-space is the classic break).

**G6. Export one animated, suppression-aware GLB and open it on a phone.** MHR assets are a separate release download (`v1.0.1`, `assets.zip`, ~190 MB, via `mhr-download-assets`) containing 7 LODs (0–6, not 0–4) — and **the asset LICENSE ships inside the zip; read it before shipping anything**. The repo is Apache-2.0 with no asset carve-out, but that is not the same as a verified asset license. The TorchScript path supports LOD 1 only. Export via `pymomentum` `Character.save_gltf_from_skel_states`, then load in three.js with `GLTFLoader` + `AnimationMixer`. **Phone playback is part of the gate, not a later concern.**

**G7. Measure honestly.** Cold and warm runtime, peak VRAM, and cost for one real 30-second clip. Note on the published numbers: 5.28 FPS uses **oracle boxes** — hand-labeled ground-truth boxes fed in by the researchers instead of a real detector, to measure the 3D stage in isolation. It is not achievable in production. The 3.50 FPS automatic-detection figure could not be re-verified in the repo; the README claims ~65 ms/frame on a 5090. **Trust neither — measure your own.** Treat any per-clip cost as **provisional warm compute only**, excluding cold start, storage, retries, and idle billing.

**G8. Book the pilot.** Name the six cohort members and put the session in a calendar. Every previous project skipped this step.

**The week-one deliverable, concretely:** one 10–15 second clip containing a turn, a wrist occlusion, and a re-entry — played on a phone beside its exported body, with raw detector overlays visible, suppression still correct while seeking, and measured runtime and VRAM. That single artifact tells you more than any amount of job-service scaffolding.

**Gate decision.** Continue only if: weights approved, SAM License compliance packaging done, one clip produces a body that reads as a person on a phone screen, and the measured cost per clip is acceptable. Otherwise stop and reconsider — that is a good outcome for 20 hours, not a failure.

---

## 3. The pipeline (exact pins)

| Stage | Choice | Pin | License | Notes |
|---|---|---|---|---|
| Ingest | Upload primary; ffprobe/FFmpeg normalize ≤1080p, 15 fps sample, ≤60 s; shot-boundary check rejects cuts | — | — | Paste-a-link (yt-dlp) deferred |
| Detect + track + 2D kp | **RTMO-m / body7 @ 640×640** via `rtmlib`, **ONNXRuntime CUDA** (rtmlib has no TensorRT branch) + **upstream ByteTrack** | rtmlib/mmpose **Apache-2.0**; ByteTrack **MIT** | Replaces YOLO11m-pose. RTMO-l is 74.8 AP on COCO val2017 and the paper reports +1.1% AP over YOLO-Pose at ~9× the speed on the same backbone (caveat: RTMO trains on the body7 multi-dataset, so not strictly apples-to-apples). YOLO11m-pose is 64.9 mAP50-95 / 4.9 ms T4. **Use upstream ByteTrack, not Ultralytics' — theirs is AGPL too.** Start at RTMO-m; one dancer does not reduce its full-image cost and 1080p is resized regardless. Go to -l only if wrists/ankles fail. Import Torch *before* creating the ORT session and verify CUDA actually activated |
| Adapter | Own `run_human_detection()` wrapper returning `{"boxes": (N,4), "keypoints": (N,17,3)}`, registered in `tools/build_detector.py` | — | own | **Bigger than 30 lines — rtmlib does not hand you what you need.** `RTMO(image)` returns keypoints `(N,17,2)` and scores `(N,17)`: its postprocessor computes boxes and detection scores and then **throws them away**, and on zero detections it **fabricates a single all-zero pose**. So: subclass the postprocessor to keep the post-NMS boxes, concatenate keypoint confidence into `(N,17,3)`, and return genuinely empty arrays when nothing is found. Keep `to_openpose=False` (wrists stay at indices 9/10). Lower RTMO's default 0.7 threshold so ByteTrack still sees low-score candidates, and do not let ByteTrack rescale coordinates a second time. The *downstream* half is still small: The hand path keys off the COCO-17 *format*, not YOLO: `_get_hand_box_from_yolo_pose` (line ~3430 of `sam_3d_body/models/meta_arch/sam3d_body.py`) is pure numpy, reads wrist indices 9/10, and touches nothing from ultralytics. The only coupling is upstream in `sam_3d_body_estimator.py` (~line 271), where the keypoint path activates when the detector returns a dict with `boxes` and `keypoints`. RTMO emits exactly that format |
| Per-frame 3D | **Your fork of** `Fast-SAM-3D-Body` → SAM 3D Body → MHR, external-keypoint hand path | commit **`808b53c`** (2026-06-18) — **no releases, pin the SHA** | MIT (code) | Research code: 22 commits, one author, inconsistent metadata (10.25× vs 10.9× speedup). MIT, so forking is explicitly allowed. **The 3.50 FPS figure could not be re-verified in the repo or README** — the published claims are ~65 ms/frame on a 5090 and a 10.25× speedup. Measure it yourself in G7 rather than trusting either number |
| Weights | `facebook/sam-3d-body-dinov3` | HF gated | SAM License | Upstream repo dormant since 2026-02-19 |
| Body model | MHR | release **`v1.0.1`**, `assets.zip` ~190 MB | Apache-2.0 (code); **assets: verify in-zip LICENSE** | Actively maintained (2026-09-11) — the live half of the stack |
| Temporal | **Own Kalman implementation** | — | own | **Do not fork sam-body4d's smoother.** Source read: its adaptive smoother uses EMA, *fills occluded spans*, and blends filled values into neighboring visible frames — the exact opposite of this product's promise |
| Export | `pymomentum-gpu` `Character.save_gltf_from_skel_states`, MHR LOD 3–4 | momentum **v0.1.114** | MIT | Python ≥3.11 |
| Viewer | three.js + React Three Fiber, `GLTFLoader` + `AnimationMixer` | three **0.186.0**, `@react-three/fiber` **9.7.0**, drei **10.7.8** | MIT | **R3F 9.7 peers `react >=19 <19.3`** — pin React accordingly |
| Sync | `requestVideoFrameCallback` → `mixer.setTime(mediaTime)` | — | — | 95.4% global, Safari 15.4+ |
| Beats (deferred) | librosa or madmom | — | — | **Not BeatNet** — unmaintained since 2023, no declared license |

**Excluded, with reasons.** Everything SMPL/SMPL-X (4D-Humans, WHAM, TRAM, GVHMR, PromptHMR, CoMotion, Multi-HMR 2, Human3R — non-commercial via the body model). NVIDIA GEM-X (verified: runs its own SAM 3D Body internally, consumes the decoder pose token, cannot accept external poses, single-person, no SLAM in released code, no per-frame confidence — an *alternative* path, not a stage; keep as a v2 option). **sam-body4d's Diffusion-VAS occlusion fill — its weights are fine-tunes of Stable Video Diffusion, whose card requires a commercial license from stability.ai; the MIT code label does not cover them.** Google GHUM (research-only). MediaPipe (single-person). **Anny-Fit is non-commercial** (verified — the Anny *body model* is Apache/CC0, but the Anny-Fit estimator's LICENSE is NC and its dependencies add restrictions), so it is not a cleaner replacement. **Sapiens is CC-BY-NC-4.0** — disqualified. No verified permissive replacement for SAM 3D Body currently exists; that is the one non-open component and it is unavoidable if you want this model.

**Cost (provisional).** At 15 fps sampling: a 30 s clip ≈ 450 frames ≈ 2 min; 60 s ≈ 900 frames ≈ 4 min, at the automatic-detection rate. **Modal has no RTX 4090** — its nearest is L40S at ~$1.95/hr, with $30/month free on Starter. RunPod has 4090s at $0.74/hr secure, $0.34 community, ~$1.10/hr serverless. So roughly **$0.07–0.13 per clip warm**, before cold start and retries. Modal's free tier plus simpler web-triggered job model probably wins for the MVP despite the pricier card; RunPod wins on raw cost. Decide in G7 with real numbers.

---

## 4. Uncertainty: what the product actually promises

Codex's correction, accepted: **"never guess" is not literally achievable and should not be claimed.** 17 detector keypoints cannot establish visibility for every rig joint (fingers and toes are not covered), low confidence cannot distinguish occlusion from motion blur, and a box touching the frame edge does not identify which limb left. The global shape and root estimates already contain inferred information regardless.

So the honest version, which is what ships:

- Three states per joint: `observed`, `uncertain`, `absent` — plus `unknown` where the detector simply cannot speak (fingers, toes). Conservative region mapping: a suppressed wrist suppresses the whole hand.
- **Hysteresis** on state transitions so limbs do not flicker between states frame to frame.
- Shape parameters frozen from well-observed frames only; where there are none, an explicitly assumed default, labeled.
- **Filtering, concretely (use FilterPy, do not hand-roll):** independent constant-velocity filters — one for translation, and one per *explicitly mapped, unwrapped scalar* rig angle. **Never filter quaternion components as ordinary scalars.** Independence is what lets you skip a suppressed block's update entirely instead of doing measurement-row surgery. Specify state, initial covariance, process noise, measurement noise, and reset duration. Recompute the transition matrix and process noise from the actual Δt. On re-entry after a gap, restart that block. Propagate suppression conservatively to descendants, and keep *visibility* separate from *covariance* — they are different things.
- **The trap that will actually bite: hiding a bone does not hide its skinned surface.** The mesh keeps rendering wherever those vertices are. You need mesh-region masks (or separately drawable regions) plus timestamped visibility to render a limb as uncertain or absent at all.
- **Missing GLB keyframes do not prevent interpolation** — the player will happily interpolate straight across a gap. Split the animation into segments, or explicitly prevent cross-gap evaluation.
- Rendering per `DESIGN.md` §4: observed = solid; uncertain = desaturated with a perturbed sketchy outline (beats blur in the literature; a lighter tint of a confident pose is still a confident pose); absent = not drawn, stub plus dotted line.

---

## 5. Scope

**MVP input:** one clip, ≤60 s, **one or more dancers**, one front camera, mostly steady, no cuts. Partly-out-of-frame is handled, not rejected.

**Multi-dancer, revised 2026-09-18.** An earlier draft capped the MVP at one dancer. That was wrong, and it would have cost *more* work rather than less: RTMO is multi-person by design, ByteTrack is multi-person by design, SAM 3D Body runs per-crop so N dancers is just N crops, and the frozen contract already declares `persons` as an unbounded array. Limiting to one would mean actively discarding tracks the pipeline already produced. Real TikTok dances frequently have two people.

What is in the MVP: detect, track, reconstruct and render every dancer; a picker to choose whose body you are learning from; per-dancer colours.

What stays in v2, because it is the genuinely expensive logic and not the reconstruction: cross-dancer consensus (using aligned dancers to correct one dancer's reconstruction errors), the sync check, the formation view (needs a solid floor solve first), and "which dancer in this group is me".

The costs this accepts, honestly: GPU time scales roughly linearly with dancer count, so a two-dancer clip is about twice the price (~$0.15–0.25 rather than ~$0.07–0.13, possibly sub-linear given crop batching and 47 GB of idle VRAM). And identity swaps when dancers cross are the known hard case — the existing uncertainty design covers it: when track confidence collapses at a crossing, mark it, never silently swap.

**MVP output:** hosted lesson page — video and 3D on a shared scrubber; orbit, mirror, front/back/side/top presets (non-front labeled *estimated*); speed 0.25–1×; A-B loop snapped to counts; **manually set** counts and named parts; invite-only shareable link.

**Irreducible core** (Codex's list, if everything else must go): upload, synchronized video + 3D, mirror, orbit, speed, loops, manual counts, video zoom, invite sharing.

**Cut first, in this order, if hours run short:**
1. Automatic beat detection and automatic part proposals → manual count-one + BPM and named loops.
2. Floor fitting and contact correction → a floorless, honestly-estimated body. (Floor fitting cannot guarantee travel or weight transfer anyway, and vertical root pinning can erase jumps.)
3. Custom sketchy-outline shader → hidden or dashed uncertain limbs.

**Out for v1:** groups and cross-dancer consensus, formation view, moving cameras, cut-heavy edits, VRM avatars, 3D hand articulation, record-yourself/scoring, paste-a-link, public API. Designs for these are preserved in §9.

---

## 6. The contract

`MotionResult v1` is a **frozen, versioned contract**, not a field inventory — the frontend is built against a recorded fixture from the first successful job, so a later break is expensive. Must specify: `schema_version`; **`sample_times_s` — the timestamp of every sample on the normalized video timeline, including failed ones. This is the field most likely to be missing and force a rewrite: array index plus nominal fps stops working the moment a frame drops, and it affects playback, visibility, seeking, and re-entry.** array shapes and axis order for every tensor; joint → GLB node mapping; animation clip id; normalized video dimensions and orientation; audio offset; camera intrinsics and camera→world transform; root trajectory; floor plane equation (or null); crop rectangles for the hands/feet close-ups; missing-frame semantics; **visibility separate from provenance** (a sample can be model-estimated *and* interpolated *and* suppressed — and no inferred 3D joint may be labeled `observed`); per-clip accent color; `model_report` with versions and license flags. Plus a **separate job status/error/retry contract**, and fixtures covering dropout, seeking, and re-entry.

Monorepo: `packages/motion-contract` (schema + generated TS/Python types), `services/motion-api` (FastAPI + queue + GPU worker), `apps/web` (Next.js + R3F). `git subtree split` if the API ever justifies its own repo.

---

## 7. The learning pilot

Honest framing, per Codex: six people is an **exploratory pilot**, not evidence of general superiority. It can reveal repeated usefulness or harmful errors. Design: six learners, six unfamiliar fragments, each fragment assigned equally across both conditions, balanced order, identical controls except the 3D panel, capped practice time, a **predefined correctness rubric**, **blinded** ratings of the recordings, and failures retained in the writeup. Report individual results — fragment attempts are not independent participants. Predefine which fragments are orientation-heavy and what improvement would count. Run it **before** counts polish, and use its variance to size a real study if one is ever warranted.

---

## 8. Milestones after the gate (~70h)

**A (~20h).** Freeze the first `MotionResult` as a fixture. Own Kalman + suppression chain. Viewer: sync, mirror, orbit, speed, loop, presets, per `DESIGN.md`.

**B (~20h).** Manual counts and parts. Hands/feet video crops. Invite auth and shareable links. Hosted.

**C (~15h).** The learning pilot. Fix what it surfaces.

**D (~15h).** Buffer — it will be consumed. If not: automatic beats, floor fitting, or paste-a-link.

Running alongside: trividha onboarding (~20h). **bolbox's model work moves to the next cycle**; its recording starts now and keeps.

---

## 9. Risks, and v2

**Biggest risk (Codex's words):** *confidently wrong motion during turns* — precisely the fragments that are supposed to justify the 3D. The pilot is designed to catch it; the uncertainty rendering is designed to disclose it.

Others: SAM's §8 unilateral-amendment clause (a standing business risk, not a blocker). Weights gate approval time (G1). Research-code fragility in Fast-SAM-3D-Body (one author, no releases). MHR asset license unverified until the zip is opened (G6). TensorRT engine non-portability across rented GPUs. Bone-length checks **cannot reliably identify symmetric mirror flips** — the L/R vote is weaker than v3 claimed; treat it as a flag, never a silent fix. Scope creep toward scoring.

**v2, designs preserved:** groups with a sync check and error-only consensus (flag only when a frame is both an outlier against time-aligned others *and* discontinuous with the dancer's own motion; fill from that dancer's own neighbors, never from others, never across suppressed spans; validate with synchronized front/side recordings, withholding the side view for adjudication, measuring false repairs and missed errors against uncorrected output). Default-teacher selection. Formation view. Moving cameras (ViPE, or GEM-X with an external trajectory). Cut-heavy edits as per-shot jobs stitched by counts. VRM avatars. 3D hand articulation gated on measured improvement. Record-yourself. Paste-a-link. The motion API as a product.

---

## 10. Scrapping and rebuilding the repo

The existing `stepwise` repo is 40 commits, a mock-adapter pipeline, and a 483-line viewer that renders spheres on a grid. Nothing in it is cheaper to adapt than to rewrite against the real contract. What survives is *decisions*, not code: the view-preset list (video / front / back / mirror / ghost / hands / footwork), the mobile layout that worked, the `MeshResultV1` field list as a starting point, and the processing-stages screen shape.

1. **Archive, do not delete.** `git tag archive/mock-pipeline-2026-03 && git push --tags`, then branch `archive/v1` and push it. The March work stays reachable.
2. New branch from an empty tree for the rebuild; `main` becomes the new structure when the gate passes.
3. Copy in `DESIGN.md`, `CONCEPTS.md`, and this PRD as `docs/`.
4. Keep `CLAUDE.md`'s rule that `DESIGN.md` is read before any visual decision. Update the skills list.
5. Scaffold in this order: `packages/motion-contract` → `services/motion-api` (job API against a *fake* worker first) → `apps/web` against the fixture → the real worker.

Do not delete anything until the gate passes and the new structure runs.

---

## 11. Day one

1. Archive the existing repo (§10.1).
2. Request the gated SAM 3D Body weights (G1).
3. Set up SAM License compliance: marked directory, verbatim Agreement copy, README obligations (G2).
4. Pick the GPU host and build the documented environment (G3).
5. Eager inference on one full-body frame and one crop (G4).
6. Prove the detector→estimator adapter (G5).
7. Export one animated suppression-aware GLB; open it on a phone (G6).
8. Measure cold/warm runtime, VRAM, cost (G7).
9. Book the pilot with six named people (G8).

## 12. Still open

GPU host (Modal's free tier and simpler job model vs. RunPod's cheaper 4090s) — decide with G7 numbers. The ten eval clips, including a hand-heavy one, a footwork-heavy one, and a Short with cropped feet. Cohort one, by name. The public name.
