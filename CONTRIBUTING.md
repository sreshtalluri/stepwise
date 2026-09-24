# Contributing

`main` is the trunk. Everything lands through a pull request with green CI;
nothing is pushed to `main` directly and nothing is force-pushed anywhere
shared.

## Branches

Branch from an up-to-date `origin/main`:

| Prefix | For |
|---|---|
| `feat/…` | new behaviour |
| `fix/…` | a bug fix |
| `docs/…` | documentation only |

Keep one concern per branch. Delete the branch once its PR merges.
`archive/*` branches and the `v1-final` tag are frozen history — never
move or delete them (INTEGRATION.md §30).

## Pull requests

1. Push the branch, open a PR against `main`.
2. All **nine** checks in `.github/workflows/test.yml` must pass. Branch
   protection blocks the merge otherwise.
3. Merge. Then deploy from `main` if the change needs it — the order is in
   `docs/DEPLOYMENT.md` §2, and §7.1 (the warm-container trap) applies to
   every backend deploy.

## Running the nine checks locally

CI uses Python 3.12 and Node 22. Run from the repo root with a fresh
virtualenv (`uv venv --python 3.12`), mirroring the workflow:

| Check | Command |
|---|---|
| `python (motion-api)` | `uv pip install -r services/motion-api/requirements-api.txt pytest scipy filterpy pygltflib trimesh` (and `ffmpeg` on PATH), then in `services/motion-api`: `python -m pytest -q -rs test_grounding.py test_retention.py test_fingerprint.py test_api_rotations.py test_schema.py test_observability.py test_ratelimit.py test_analytics.py tools/test_region_mask.py` |
| `python (motion-contract)` | `uv pip install pytest jsonschema pydantic`; in `packages/motion-contract/python`: `python -m pytest -q` |
| `python (beat-detect)` | `uv pip install pytest librosa numpy soundfile imageio-ffmpeg==0.6.0`; in `packages/beat-detect/python`: `python -m pytest -q` |
| `python (cv-tools)` | `uv pip install pytest numpy scipy filterpy onnxruntime rtmlib`; **from inside** `services/motion-api/vendor/fast-sam-3d-body/tools`: `python -m pytest -q .` |
| `postgres schema + job-state backend` | `docker run --rm -d -p 5432:5432 -e POSTGRES_PASSWORD=stepwise postgres:16`, then in `services/motion-api`: `DATABASE_URL=postgresql://postgres:stepwise@localhost:5432/postgres python -m pytest -q test_schema.py test_ratelimit.py test_analytics.py` |
| `node (packages/motion-contract)` | `npm ci && npm test` in `packages/motion-contract` |
| `node (packages/navigation)` | `npm ci && npm test` in `packages/navigation` |
| `node (apps/web)` | `npm ci && npm run assets && npm test` in `apps/web` |
| `apps/web build + typecheck` | `npm ci` in `packages/navigation`, then in `apps/web`: `npm ci && npm run typecheck && npm run assets && npm run build` |

`npm run assets` generates the fixtures `apps/web` reads; they are not
committed, and skipping it looks like a missing-file failure.

## Secrets

Secrets live in `~/.stepwise-secrets/*.env` on the developer machine and in
Modal / Cloudflare Secrets in production. They are **never committed and never
printed** — not in a PR, a log, a commit message or a terminal transcript. Load
them with `set -a; . ~/.stepwise-secrets/<name>.env; set +a` and generate new
ones straight into a file (`umask 077; … > ~/.stepwise-secrets/…`), as
`docs/DEPLOYMENT.md` §3 does. If one leaks, rotate it; deleting the commit is
not enough.

## Visual QA

Any change a learner can see gets checked in a real browser before the PR
merges: run `apps/web` (`npm run dev`) and look at the affected pages in the
Claude browser, at desktop and phone widths, in light and dark. Unit tests and
a green build do not prove a page looks right.
