# TASKS — scrap, rebuild, and who can do what in parallel

Work packages sized for one agent each. **The contract-first architecture is what makes this parallelizable**: because `MotionResult` is frozen early and the frontend builds against a recorded fixture, the entire web app can be built without the GPU pipeline existing.

Legend: 🧍 human only · 🤖 agent-ready · ⛓ blocked by · ⚡ can start immediately

---

## Phase 0 — human only, start today

| # | Task | Why only you | Lead time |
|---|---|---|---|
| H1 | 🧍 Request gated weights at `huggingface.co/facebook/sam-3d-body-dinov3` (and `-vith` as fallback) | Tied to your HF identity; you accept Meta's terms | **Blocks W1. Not instant — do it first.** |
| H2 | 🧍 Ask six cohort members by name, book the week-6 session | Social, and the whole project's point | Blocks the pilot, nothing else |
| H3 | 🧍 Create the GPU account (Modal or RunPod) | Needs your payment method | Blocks W1 |
| H4 | 🧍 Choose 10 eval clips + 3 stress cases (hand-heavy, footwork-heavy, cropped-feet Short) | Needs your taste and cohort knowledge | Blocks W1's gate measurement |
| H5 | 🧍 Archive the old repo: `git tag archive/mock-pipeline-2026-03 && git push --tags`, push branch `archive/v1` | Destructive-adjacent; you should own it | Blocks W3 |

---

## Phase 1 — three agents can run at once

### W1 🤖 The feasibility gate (pipeline) ⛓ H1, H3, H4
**The hard one. One strong agent, sequential inside.** Deliver in this order and stop at the first failure:
1. Two environments (they are incompatible — this is the #1 install trap): SAM inference on **Python 3.11 / Torch 2.5.1 / cu124**; glTF export on a **separate** env for `pymomentum` (wheels target Python 3.12–3.13 / Torch 2.8 / cu129). Arrays over the boundary, not shared imports.
2. Edit `setup_env.sh` — it still installs Ultralytics, TensorRT and SMPL-X. Remove them.
3. RTMO via `rtmlib` + ONNXRuntime CUDA (no TensorRT branch exists). Import Torch *before* creating the session; verify CUDA actually activated.
4. **The adapter.** Subclass rtmlib's postprocessor to retain post-NMS boxes (it computes and discards them), concatenate keypoint confidence to `(N,17,3)`, and return genuinely empty arrays on no-detection (it currently fabricates one all-zero pose). Keep `to_openpose=False`. Lower the 0.7 threshold so ByteTrack sees low-score candidates. Don't let ByteTrack rescale coordinates twice. Register via `run_human_detection()` in `tools/build_detector.py`.
5. Eager inference on one clip → MHR → GLB → opened on a phone.
6. **Week-one deliverable:** one 10–15s clip containing a turn, a wrist occlusion, and a re-entry, played on a phone beside its exported body, with raw detector overlays, suppression correct while seeking, and measured runtime + VRAM + cost.

**Brief the agent with:** `02-stepwise-mesh-learning.md` §2 and §3 in full. Tell it to measure, not to trust, the published FPS numbers.

### W2 🤖 License compliance packaging ⚡ no dependencies
Small, self-contained, start now. Marked directory for SAM Materials with a verbatim copy of the SAM Agreement (§1.b.i requires derivatives carry it). README section stating: your code is MIT, SAM-derived parts are under the SAM License, the ITAR/military prohibition, and the research-citation obligation. A `NOTICE` file. A short `LICENSES.md` mapping every dependency to its licence. **Brief with:** §2 G2 of the PRD.

### W3 🤖 Monorepo scaffold + the contract ⛓ H5 ⚡ otherwise
The foundation everything else imports. `packages/motion-contract`: the `MotionResult v1` JSON schema plus generated TypeScript and Python types, and **a hand-written fixture file** representing one plausible finished lesson (this unblocks W5/W6 entirely). Must include `sample_times_s`, per-joint provenance (`observed` / `interpolated` / `suppressed:*` / `unknown`), `camera_model`, `grounding_status`, the per-clip accent colour, immutable asset ids, and a separate job status/error/retry contract. Plus `services/motion-api` and `apps/web` skeletons, CI, and `DESIGN.md` + `CONCEPTS.md` copied into `docs/`.
**Brief with:** PRD §6 and §10. **This is the highest-leverage early task** — get the contract wrong and two other agents rework.

---

## Phase 2 — four agents, all parallel ⛓ W3's fixture

### W4 🤖 Job service against a fake worker
FastAPI + queue + object storage + signed URLs. A **fake worker** that sleeps and returns the fixture — so the whole job lifecycle, polling, retries, and error paths are built and tested before the real GPU pipeline exists. Swap in the real worker later behind the same interface.

### W5 🤖 The viewer
React Three Fiber against the fixture. Load GLB, `requestVideoFrameCallback` → `mixer.setTime`, orbit with the moving contact shadow, view presets with "estimated" labels, mirror, speed, A-B loop, compare mode (inset on phone / side-by-side on desktop). **Brief with:** `DESIGN.md` §6, §7, §7b, §10.

### W6 🤖 Navigation + authoring
The two-tier overview bar and count strip, play-all vs loop-part modes, part create/rename/split/merge, count anchoring ("set 1 here", half/double, manual tap-in). **Brief with:** `DESIGN.md` §7, and `OPEN-DECISIONS.md` A4/A5 — some of this is still undesigned, so the agent should surface questions rather than invent.

### W7 🤖 Marketing site + processing + reveal
The marketing site (loud front door, live spinnable demo in the hero), the in-app upload screen, the processing screen, and the reveal orbit. Processing's core idea: the learner's video plays immediately with speed/mirror/loop working, so there is no dead time. **Brief with:** `DESIGN.md` §7c, §7d, §7e, §7f, §11, and **§7h — the honest-copy trap, which was violated twice during design and will be violated again.**

### W13 🤖 The share clip generator ⛓ W3 fixture, W5 viewer
**Added after the design pass — it was missing from the plan and it is the single highest-leverage thing for reach.** Auto-generate a 9:16 vertical video on lesson completion: original clip on top, the same moment with the 3D body slowly spinning below, active count overlaid, small "made with [name]" mark, silent by default. Server-side render (ffmpeg + headless three.js) or client-side canvas capture — evaluate both; server-side is more reliable but costs GPU-adjacent time. **Brief with:** `DESIGN.md` §7g and §7h.

---

## Phase 3 — after W1 passes its gate

| # | Task | Note |
|---|---|---|
| W8 | 🤖 Real worker replaces the fake one | Same interface as W4 |
| W9 | 🤖 Own Kalman + suppression | FilterPy, independent constant-velocity filters, unwrapped scalar angles, never quaternion components as scalars. Skip suppressed blocks entirely. |
| W10 | 🤖 Mesh-region masking | **Hiding a bone does not hide its skinned surface.** Affects the export format — coordinate with W3 before the contract freezes. |
| W11 | 🤖 Beat detection | librosa/madmom, not BeatNet (unmaintained, no licence). Auto-proposal only; manual always wins. |
| W12 | 🧍🤖 The learning pilot | You run it; an agent can build the rubric and the recording harness. |

---

## Rules for every agent

1. **Read `DESIGN.md` before any visual decision.** Repo `CLAUDE.md` enforces this.
2. **Get the honesty boundary exactly right — `DESIGN.md` §7h.** A dancer *turning away* is tracked and orbiting to see them is a legitimate claim (this is the best thing the product does — do not undersell it). A part that was *blocked* or *out of frame* was not recovered — never imply it was. Both overclaiming and underclaiming have already happened in draft copy.
3. **Surface questions, don't invent answers.** `OPEN-DECISIONS.md` lists 25 genuinely open items. If a task hits one, stop and ask.
4. **Measure, don't trust.** Published FPS and cost numbers in the PRD are vendor claims on different hardware; several could not be re-verified.
5. **Bucket B is the builder's.** Per the learning plan, the core algorithms (HNSW-equivalent here: the adapter, the Kalman, the grounding, the suppression logic) are hand-written by the builder with agents reviewing — not written by agents. Agents own Bucket A scaffolding and Bucket C optimization.

## The critical path

`H1 (weights) → W1 (gate) → W8/W9/W10 → integration`

Everything in Phase 2 runs beside it. If the gate fails, Phase 2 is still a working video-practice app with counts and parts — which is the honest fallback the PRD already names.
