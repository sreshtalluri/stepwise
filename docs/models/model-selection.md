# Mesh Model Selection

## Product Direction

The viewer should feel closer to a Wii Fit Trainer / Just Dance / Swayformations-style simplified human than to a rectangular placeholder or stick figure. The render target is a smooth, stylized, full-body person surface with enough proportions to read head, torso, arms, hands, thighs, calves, and feet.

## V1 Architecture

Stepwise treats computer-vision models as replaceable adapters:

1. `VideoIngestor` / API upload path accepts either a social/video URL or already-downloaded raw video bytes.
2. The API probes duration, FPS, and resolution from the actual video. The website must not ask users to type seconds.
3. `PersonDetector` finds person boxes per frame.
4. `PersonTracker` stabilizes persistent `track_id` values through motion and occlusion.
5. `MeshRecoverer` emits a rest-pose skinned body mesh plus per-frame pose/global transforms.
6. The pipeline smooths identity/trajectory/contact signals, analyzes beats and difficulty, and packages partial results.

The default local implementation is a deterministic mock stack so API, contracts, and frontend rendering can be developed without GPU model weights. The mock mesh now emits a stylized humanoid body made from smooth body-part volumes, not a cuboid. Production model adapters should conform to the same interfaces in `services/mesh-api/src/mesh_api/adapters/base.py`.

## Candidate Adapters

| Layer | Candidate | Why it fits | Production concerns |
|---|---|---|---|
| URL/video ingest | `yt-dlp` + `ffprobe`/FFmpeg | Practical path for YouTube/TikTok/Instagram/direct links and metadata probing | Platform terms/rate limits; need robust sandboxing and storage. |
| Detection/tracking | YOLO-style person detector + ByteTrack/BoT-SORT tracker | Strong video front door with persistent IDs | Ultralytics licensing can require AGPL compliance or Enterprise licensing for closed-source use. Keep replaceable. |
| Mesh recovery | SAM 3D Body + MHR | Promptable full-body mesh recovery, with body surface, feet, and hands as the target output | Verify install footprint, runtime, asset packaging, and exact upstream licenses before enabling. |
| Video mesh/tracking | 4D Humans / HMR 2.0 | Designed for reconstructing/tracking people through video and occlusion | Confirm dependency stability and license before production/commercial use. |
| Research | Multi-HMR 2 | Unified multi-person mesh recovery, camera-space localization, and identity tracking | Keep optional until code/install/license status is verified. |
| Stylized output | Retarget recovered body/pose onto a neutral trainer mesh | Gives consistent Just Dance / Wii Fit-style readability even if recovered mesh is noisy | Requires body-shape fitting, identity scaling, and good skinning weights. |

## Production License Gate

Before a non-mock adapter is enabled in a public or commercial deployment:

- Record exact model/code/data licenses in this directory.
- Add a `LicenseFlag` in the adapter descriptor.
- Confirm whether commercial use is allowed, restricted, or unknown.
- Document required attribution and source-availability obligations.
- Confirm no proprietary SMPL/SMPL-X assets are loaded without a valid commercial license.
