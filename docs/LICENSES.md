# Licenses

This maps every dependency named in `PRD.md` §3 (the pipeline table) to its
licence and the obligations that licence creates. See `NOTICE` for the short
version and `SAM Materials/LICENSE` for the verbatim SAM License text.

**The repository as a whole cannot be honestly labeled MIT or Apache-2.0.**
Code written in this repository (`packages/`, `services/`, `apps/`, minus any
third-party code copied in) is MIT — see `LICENSE`. The SAM 3D Body model and
anything derived from it stay under the SAM License forever, regardless of
what license the surrounding code carries.

| Dependency | License | SPDX | Obligation |
|---|---|---|---|
| Original stepwise code | MIT | `MIT` | None beyond MIT's own notice-preservation requirement — we set these terms. |
| `rtmlib` / `mmpose` | Apache License 2.0 | `Apache-2.0` | Permissive. If source is vendored or redistributed, preserve copyright/licence notices and state changes made; carry forward any upstream `NOTICE` file content (none currently vendored). No copyleft, no obligation on our own code. |
| ByteTrack — **upstream** `ifzhang/ByteTrack` (not Ultralytics' fork) | MIT | `MIT` | Preserve the copyright and license notice if redistributed. This is why the PRD insists on the upstream repo specifically — Ultralytics' own ByteTrack integration is AGPL-3.0, which is why `ultralytics` is dropped from the dependency tree entirely (PRD §2 G2). |
| Fast-SAM-3D-Body (`yangtiming/Fast-SAM-3D-Body`, forked, pinned at commit `808b53c`) | MIT (code) | `MIT` | Preserve copyright/license notice in the fork. MIT permits forking and modification, which the PRD relies on. **This MIT label covers only the acceleration/wrapper code** — it imports and runs SAM 3D Body internally, so using it pulls in every SAM License obligation below regardless of this file's own license. |
| SAM 3D Body — model code (`facebookresearch/sam-3d-body`) and weights (`facebook/sam-3d-body-dinov3`, HF-gated) | **SAM License** (Meta, custom — not OSI-approved, not SPDX-listed) | `LicenseRef-SAM-License` | See "SAM License obligations" below. Full text: `SAM Materials/LICENSE`. |
| MHR — **code** (`facebookresearch/MHR`) | Apache License 2.0 | `Apache-2.0` | Standard Apache-2.0 obligations for the code. **Does not cover the model assets.** |
| MHR — **assets** (`assets.zip`, release `v1.0.1`, ~190 MB, downloaded separately via `mhr-download-assets`) | **Unverified** | — | The PRD (§3, §9, §11) flags this explicitly: the asset LICENSE ships inside the zip and has not been read. The repo being Apache-2.0 is not evidence the assets are — mesh/weight assets are commonly licensed separately from code in projects like this. **Do not ship or represent these assets as Apache-2.0 until the in-zip LICENSE is opened and read.** This is an open item, not a resolved one. |
| momentum / pymomentum (`facebookresearch/momentum`, pinned `v0.1.114`) | MIT | `MIT` | Preserve copyright/license notice if redistributed. |
| three.js, `@react-three/fiber`, `drei` | MIT | `MIT` | Preserve copyright/license notice if redistributed (standard for a bundled frontend build — the notice ships in bundled license comments / a generated `THIRD-PARTY-NOTICES` file at build time, not this repo's source tree). |
| Next.js | MIT | `MIT` | Same as above. |
| React | MIT | `MIT` | Same as above. Note the version constraint from PRD §3: `@react-three/fiber` 9.7 peers on `react >=19 <19.3`. |

## SAM License obligations, in full

The SAM License (last updated 2025-11-19, reproduced verbatim at
`SAM Materials/LICENSE`) is not AGPL-compatible, not OSI-approved, and not
SPDX-listed (PRD §2, G2). Its obligations that matter here:

- **§1.b.i — pass-through.** Anyone we distribute the SAM Materials or a
  derivative work to must receive a copy of this Agreement. Satisfied by
  keeping `SAM Materials/LICENSE` in the repository and referencing it from
  `README.md` and `NOTICE`.
- **§1.b.ii — citation, scoped to research publications only.** If *you*
  submit for publication the results of research performed using the SAM
  Materials, you must acknowledge that use in the publication. **This does
  not apply to running stepwise as a hosted product or service** — there is
  no publication, so no citation obligation arises from normal use. Don't
  overstate this: it binds research papers, not the app.
- **§1.b.iii — legal compliance.** Use must comply with applicable law,
  including Trade Control Laws and privacy/data-protection law.
- **§1.b.iv — no reverse engineering.** Must not reverse-engineer, decompile,
  or attempt to discover the underlying components of the SAM Materials, or
  encourage others to.
- **§1.b.v — ITAR / military-use prohibition.** Must not use, and must not
  permit others to use, the SAM Materials for anything subject to the
  International Traffic in Arms Regulations, or for military/warfare,
  nuclear, espionage, or illegal-weapons purposes, and must not be a target
  of Trade Controls.
- **§8 — unilateral amendment.** Meta may modify the Agreement at any time,
  effective immediately; continued use after a modification counts as
  accepting it. Pinning a commit or model version does not neutralize this.
  This is a standing business risk, not something this documentation can
  resolve — see PRD §2 and §9.

## What is not a licence obligation

Two things worth being precise about, because it is easy to overstate them:

- **Making this repository public is the builder's choice, not something the
  SAM License requires or forbids.** (PRD §1.)
- **The citation obligation above applies to research publications, not to
  operating a hosted service.** Shipping stepwise as a product does not, by
  itself, trigger §1.b.ii.
