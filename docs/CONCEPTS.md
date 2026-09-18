# Concepts — plain-language reference for the three projects

Defined once, in the order you'll meet them. Skip what you already know.

## Stepwise (video → 3D body)

**Detection + keypoints.** Finding each person in a frame as a box, and locating their 17 body joints in 2D. **RTMO** does both in a single forward pass (one-stage), which is why it replaced YOLO11m-pose here — same job, Apache-2.0 instead of AGPL, and the paper reports higher accuracy at ~9× the speed on a matched backbone.

**Tracking / identity association.** Deciding that the box in frame 41 is the same dancer as the box in frame 40. ByteTrack does this with motion prediction and box overlap. The hard case is two dancers crossing: for a few frames the boxes overlap and the tracker has to decide who came out on which side. **Hungarian matching** is the assignment algorithm — given a cost for pairing each old track with each new detection, it finds the lowest-total-cost pairing. **SAM 3 masklets** are pixel-accurate masks tracked over time; they survive occlusion better than boxes.

**3D body recovery / human mesh recovery (HMR).** From one image crop of a person, predict a 3D body — its pose (joint rotations), shape (proportions), and position relative to the camera. **SAM 3D Body** is Meta's model for this; it outputs parameters of the **MHR (Momentum Human Rig)** body model — a parametric template of the human body where a small vector of numbers produces a full mesh. **SMPL / SMPL-X** are the older, dominant body models from the Max Planck Institute; their license forbids commercial use, which is why nearly every research method is off the table for a product and MHR (Apache) matters so much.

**Camera-relative vs. world-grounded.** SAM 3D Body tells you where the body is *relative to the camera*. If the camera moves, the body appears to move even when the dancer is still. World-grounding means solving for a fixed floor and a moving camera — which is why feet "slide" without it. **MoGe-2** estimates the camera's field of view and scene depth from a single image; a **foot-contact root fix** detects which foot is planted and pins it while solving the body's trajectory.

**Temporal smoothing.** Per-frame predictions jitter. A **low-pass filter** (e.g. Butterworth, Savitzky-Golay) averages over neighboring frames — but a fixed filter smears a fast turn into mush. The fix is smoothing whose strength drops when angular velocity spikes. **Motion blur** makes fast frames individually unreliable, which is why this matters for dance more than for PT.

**Monocular / single-view reconstruction.** Recovering a 3D body from one ordinary camera — a TikTok, a Short, a performance filmed from the audience. It works because the body model constrains what a human can look like; the price is that *depth along the viewing axis* (toward/away from the camera) is estimated, not measured. Side and top views are therefore derived, and the product labels them *estimated*.

**Suppression / never-guess rule.** A parametric body model always outputs *some* pose for every joint, even ones outside the frame. So out-of-frame, low-confidence, or occluded joints are marked `suppressed` in the result (with the reason), withheld from the smoother rather than interpolated, and rendered **fuzzy** — translucent, desaturated, no shadow — so the learner sees "unknown" instead of a confident wrong foot. If the feet are cropped for most of a clip, there is no floor solve at all: the body honestly floats.

**Left/right flip.** The classic monocular ambiguity: a body facing away and a body facing toward you can produce similar silhouettes, so the model sometimes swaps left and right limbs for a few frames. A **consistency vote** across the whole track (bone lengths, joint ordering) catches most of these.

**Skinned mesh / glTF / GLB.** A skinned mesh is a surface attached to a skeleton so that moving a bone deforms the surface. **glTF** is the standard web 3D format; **GLB** is its binary form. **LBS (linear blend skinning)** is the simple deformation rule browsers run fast; MHR's extra "pose correctives" (learned bulges) don't survive export — fine for learning choreography. **LOD (level of detail)** is a lower-polygon version of the mesh; LOD 3–5 keeps phones fast.

**Three.js / React Three Fiber (R3F).** The browser 3D engine and its React wrapper — what the existing viewer uses. `AnimationMixer` plays the exported clip; `timeScale` is slow-mo; flipping `scale.x` mirrors.

**Oracle input (benchmarking).** When a research paper reports a number using "oracle" boxes or labels, it means the authors fed the model *perfect, hand-labeled* data instead of running a real detector — to measure one stage in isolation. It is never achievable in production, because a real system has to find the person first. Always look for the "automatic" number.

**Adapter / glue code.** Two models from different research repos rarely fit together: each assumes it owns the whole pipeline. The adapter translates one model's output into exactly the arrays, coordinate space, and confidence format the next one expects. Here it is ~30 lines: a wrapper exposing `run_human_detection()` that returns `{"boxes": (N,4), "keypoints": (N,17,3)}`. This is the part that is *your* code.

**Copyleft vs. permissive licenses.** Permissive (MIT, Apache-2.0) = use it however, just keep the notice. Copyleft (GPL, **AGPL**) = if you distribute — or, for AGPL, if you *host it as a network service* — you must offer the corresponding source, and you may **not** add restrictions of your own downstream. That last clause is why AGPL and the SAM License collide: the SAM License adds field-of-use limits (no military/ITAR), a citation requirement, and a reverse-engineering ban, all of which AGPL §7 treats as forbidden "further restrictions." Dropping the AGPL component removes the conflict.

**GEM-X / SOMA.** NVIDIA's video-to-motion model on its SOMA body model. Verified from source: it runs its own SAM 3D Body forward internally and consumes the decoder's pose token — it does *not* accept external poses — is single-person per call, has no SLAM in the released code (static-camera fallback), and reports no per-frame confidence. So it is an *alternative* to SAM 3D Body, not a stage after it. Weights: NVIDIA Open Model License (commercial OK, revocable, Notice file). Kept as a v2 option.

**ViPE.** NVIDIA's pip-installable video pose engine: camera intrinsics + trajectory + near-metric depth from an ordinary video. Used here so all dancers can be placed on one floor. **RANSAC floor**: fit a plane to the foot joints of every dancer across the clip, ignoring outliers (feet in the air) — that plane is the stage.

**VRM / three-vrm.** VRM is a humanoid avatar format with a standard bone map; three-vrm (MIT) loads it in three.js. Driving a VRM from MHR joint rotations needs a **rest-pose correction** — MHR's rest is A-pose, VRM's is T-pose — applied per bone as `q_local = parentRestWorld · q_srcWorld · srcRestWorld⁻¹`. Skipping it gives backward hands and inverted feet.

**Formation view.** A second, orthographic camera looking straight down at the floor grid, with each dancer's root position drawn as a trail — the Swayformations-style stage view, derived from motion instead of hand-placed.

**Motion API / MotionResult contract.** The pipeline is its own service — video in, per-person world-grounded motion out — with a versioned JSON + GLB result document as the boundary. The learning platform consumes that document and never talks to a model directly. Building the platform against a *recorded* result (a fixture) means the two halves can be built and tested independently.

**Learning test.** A small counterbalanced study: the same short dance fragments learned with slowed/mirrored video alone vs. video + 3D, each person seeing both conditions on different fragments; measure time to an instructor-rated correct attempt. It's the gate for building more 3D — if 3D doesn't win on turns/back-facing/footwork, the product becomes the best player with counts.

**Sync check / error-only consensus.** When several dancers do the same choreography, align them in time (cross-correlate movement energy). The aligned others are used only to *detect* reconstruction errors — a frame that is both an outlier against the group and a discontinuity in that dancer's own motion. Fixes are interpolated from the dancer's own neighboring frames, never copied from others, so personal style survives. Solo videos skip it; out-of-sync dancers are shown but excluded.

**Step segmentation.** Splitting a dance into parts. Auto-proposed from valleys in movement energy snapped to 8-count boundaries, then editable — the unit the lesson mode walks through.

**DTW (dynamic time warping).** Aligns two sequences that run at different speeds — used when comparing a learner to a reference. Not in v1, but it's what every scoring app uses.

**Beat / 8-count detection.** Onset detection finds percussive hits in audio; tempo estimation fits a steady pulse; aligning that to movement energy gives the count markers dancers think in.

## bolbox (speech → notation)

**Mel spectrogram.** Audio sliced into short overlapping frames (the **hop** is the step between frames), each turned into an energy-per-frequency-band picture, with bands spaced the way human hearing is (the **mel** scale). It's the standard input for speech models. The hop size decides whether a 300 ms compound bol survives as four events or blurs into one.

**CTC (Connectionist Temporal Classification).** A loss and decoding rule for when you have an audio sequence and its transcript but *no alignment* of which frame corresponds to which syllable. The model emits a label or a special **blank** per frame; repeated labels collapse and blanks are removed, so many frame-level paths map to one transcript. Training sums over all of them (the **forward algorithm**). Without the blank, `ta ta` and `ta` would be indistinguishable.

**Greedy vs. beam-search decoding.** Greedy takes the best label per frame. **Beam search** keeps the top-k partial transcripts and can incorporate a **language-model prior** — here an **n-gram** over bol sequences (how often `kita` follows `tira`) — so the acoustic model doesn't have to separate permutations alone.

**Lexicon.** A dictionary from surface forms (`tirakita`, `tirkit`, `trkt`) to the canonical stroke sequence — realization varies with tempo and gharana (school).

**Syllable error rate.** Edit distance between decoded and true syllable sequences, divided by true length. The honest headline number. **Held-out** means compositions the model never saw at any tempo.

**ONNX / ONNX Runtime Web.** A portable model format and a browser runtime for it, so inference runs locally with no server. **AudioWorklet** keeps audio processing off the main thread.

**Augmentation.** Synthetic variation of training data — here tempo perturbation, which is valid because bols are genuinely performed across a wide tempo range.

**MFCCs.** Mel-frequency cepstral coefficients — a compact (~20-number) summary of a short audio frame's spectral shape, the classic hand-crafted "sound fingerprint." Good enough to tell most tabla strokes apart from their onset burst without a neural net.

**Onset detection / spectral flux.** Finding the instant a sound starts by watching for a sudden jump in spectral energy frame to frame. The live instrument triggers on this, then has a ~12–35 ms budget (measured by Stowell & Plumbley) before a drummer notices the delay.

**Concatenative synthesis / corpus-based retrieval.** Store a corpus of sound units in a feature space; at run time, analyze the input and play the nearest stored unit. CataRT (IRCAM) is the classic; MIT's Nebula/Constellation is the voice-driven version bolbox's Version B follows. Nearest-neighbor over your own recorded strokes — no vocabulary, no classifier.

**RAVE.** IRCAM's real-time neural audio autoencoder: a learned latent space you can encode into and decode from, used for live timbre transfer in Max (`nn~`). Its encoder is a possible embedding for Version B; its decoder smears percussive transients, so it isn't used for playback.

**Per-user calibration / z-scoring.** Record a few examples of each sound you want to trigger; normalize incoming features by *your* voice's statistics so the match is relative to how you vocalize, not to an absolute template. This is the "normalize toward the cluster" step and what lets any sound you choose mean `dha`.

## trividha (shipping to real users)

**TestFlight.** Apple's beta distribution: invite specific people to install a build before it's on the App Store. Enough for a real cohort; no App Store review needed.

**COPPA / Kids Category.** US rules for under-13 users (parental consent) and Apple's stricter category for kids' apps. The decision affects what the privacy policy can say and whether analytics are ever allowed. Blocks the App Store, not a private TestFlight cohort.

**CORS / JWT / secrets rotation.** The production-hardening basics: only your app's origins may call the API; tokens are signed with a secret that must be regenerated before real users exist; demo seed data must be off.

## The learning method (all three)

**Bucket A / B / C.** A: scaffolding an agent writes (nothing to learn from hand-writing it). B: the core logic you write yourself from a skeleton containing only the public API and a failing test — no parameter names or hints that pre-decide the design. C: a later optimization pass, collaborative.

**Predict-then-measure.** Write down the expected number before every run. The wrong predictions are where your mental model gets corrected.

**Question-only review.** After writing a B component, explain it to a blank file, list what you're unsure of, and ask the AI *those questions* — never "find my bug." Retention comes from generating the diagnosis, not receiving it.

**Deliberate breakage.** Remove the smoothing, swap the tracker for naive nearest-box, halve the hop size — keep a table of what broke and by how much. That table is what interviews ask about.
