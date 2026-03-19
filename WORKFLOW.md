# Gstack Workflow Playbook

## Skill Reference (ordered by workflow stage)

| Stage | Skill | What it does |
|-------|-------|-------------|
| Ideate | `/office-hours` | Brainstorm and validate ideas before building |
| Plan (strategy) | `/plan-ceo-review` | Challenge scope, think bigger, find the 10-star product |
| Plan (architecture) | `/plan-eng-review` | Lock in architecture, data flow, edge cases |
| Plan (design) | `/plan-design-review` | Rate design dimensions, fix gaps before implementation |
| Design system | `/design-consultation` | Create DESIGN.md — fonts, colors, spacing, motion |
| Debug | `/investigate` | Systematic root cause analysis (no fixes without cause) |
| Browse/test | `/browse` | Headless browser — navigate, click, screenshot, verify |
| QA (fix) | `/qa` | Find bugs + fix them + commit each fix atomically |
| QA (report only) | `/qa-only` | Find bugs, report with screenshots, don't touch code |
| Visual polish | `/design-review` | Find visual issues + fix them with before/after evidence |
| Code review | `/review` | Pre-landing diff review for SQL safety, trust boundaries, etc. |
| Ship | `/ship` | Merge base, test, review, bump version, PR, push |
| Post-ship docs | `/document-release` | Update README, CHANGELOG, CLAUDE.md to match what shipped |
| Retrospective | `/retro` | Weekly analysis of commits, patterns, and quality trends |
| Cookie auth | `/setup-browser-cookies` | Import real browser cookies for authenticated QA testing |

---

## Single-Developer Sprint Workflow

### Phase 1: Ideation (once per feature)
```
/office-hours
```
- Validates whether the idea is worth building
- Produces a design doc with forcing questions answered
- Do this BEFORE writing any code

### Phase 2: Planning (once per feature)
```
/plan-ceo-review    → scope and strategy
/plan-eng-review    → architecture and edge cases
/plan-design-review → UI/UX quality (if applicable)
```
- Run in this order: strategy → engineering → design
- Each review is interactive — it asks questions, you answer
- Output: a solid plan ready for implementation

### Phase 3: Implementation
```
Use superpowers:writing-plans → superpowers:executing-plans
```
- Writing plans creates step-by-step implementation from your spec
- Executing plans runs through it with review checkpoints
- For parallel features, use git worktrees for isolation

### Phase 4: QA + Polish
```
/qa              → find and fix bugs (commits each fix)
/design-review   → find and fix visual issues
/browse          → manual verification of specific flows
```
- Run `/qa` first (functional), then `/design-review` (visual)
- Use `/browse` for targeted spot-checks

### Phase 5: Ship
```
/review   → final code review of the diff
/ship     → version bump, changelog, PR, push
```

### Phase 6: Post-Ship
```
/document-release   → sync all docs with what shipped
/retro              → weekly retrospective (end of sprint)
```

---

## Multi-Terminal Strategy

The fastest way to roll out features is to run 3-4 Claude terminals in parallel,
each with a dedicated role. Here's how to set it up:

### Terminal Layout

```
┌─────────────────────────────────────────────────┐
│  Terminal 1: BUILDER A     │  Terminal 2: BUILDER B     │
│  (Feature implementation)  │  (Feature implementation)  │
│                            │                            │
├─────────────────────────────────────────────────┤
│  Terminal 3: QA/TESTER     │  Terminal 4: OPS/SHIPPER   │
│  (/qa, /design-review,     │  (/review, /ship, /retro,  │
│   /browse, /qa-only)       │   conflict resolution)     │
└─────────────────────────────────────────────────┘
```

### Terminal Roles

#### Terminal 1 & 2: Builders
- Each works on a separate feature
- Use **git worktrees** so they don't conflict:
  ```
  git worktree add ../stepwise-feature-a feature/a
  git worktree add ../stepwise-feature-b feature/b
  ```
- Workflow per builder:
  1. Start with the plan (already created in planning phase)
  2. Implement using `superpowers:executing-plans`
  3. Commit frequently with atomic commits
  4. Signal to Terminal 3 when ready for QA

#### Terminal 3: QA/Tester
- Runs against the dev server or built output
- Cycle:
  1. Wait for a builder to signal "ready for QA"
  2. Run `/qa` on the feature branch → fixes bugs automatically
  3. Run `/design-review` → fixes visual issues
  4. Run `/qa-only` for a final clean report
  5. If clean, signal to Terminal 4 for shipping
- Can also run `/browse` for manual flow verification
- Use `/setup-browser-cookies` if testing authenticated pages

#### Terminal 4: Ops/Shipper
- Handles integration and delivery:
  1. Run `/review` on completed feature branches
  2. Merge feature branches back to main (resolve conflicts)
  3. Run `/ship` to create PRs and push
  4. Run `/document-release` after shipping
  5. Run `/retro` at end of sprint

### The Pipeline in Action

```
Time →
Builder A:  [implement feat 1] ──────────── [implement feat 3] ────────
Builder B:  [implement feat 2] ──────────── [implement feat 4] ────────
QA/Tester:  ·····[qa feat 1][qa feat 2]····[qa feat 3][qa feat 4]·····
Ops:        ···········[ship feat 1][ship feat 2]···[ship feat 3]······
```

Key: as soon as a builder finishes, QA picks it up. As soon as QA passes,
Ops ships it. No terminal is idle.

### Communication Between Terminals

Since terminals don't talk to each other directly, use these coordination methods:

1. **Git branches** — builders push to feature branches, QA pulls them
2. **A shared file** (e.g., `SPRINT.md`) — track what's in progress, ready for QA, shipped
3. **Naming convention** — branch names signal state:
   - `feature/xyz` → in progress
   - `qa/xyz` → ready for QA
   - `ship/xyz` → QA passed, ready to ship

### Sprint Cadence (suggested)

| Day | Focus |
|-----|-------|
| Monday AM | `/office-hours` for new features, `/plan-*-review` for planning |
| Monday PM–Thursday | Builders implement, QA tests in parallel |
| Thursday PM | All features QA'd, `/review` + `/ship` remaining work |
| Friday AM | `/document-release`, `/retro` |
| Friday PM | `/office-hours` for next sprint ideas |

---

## Tips

- **Always `/office-hours` before coding.** The 20 minutes of brainstorming saves hours of rework.
- **Run `/plan-eng-review` before implementation.** Catches architecture issues early.
- **Use `/qa` not `/qa-only`** unless you explicitly want a report without fixes. `/qa` saves time by auto-fixing.
- **`/design-review` after `/qa`.** Fix functional bugs first, then visual polish.
- **`/investigate` for mysterious bugs.** Don't guess — systematic root cause analysis.
- **`/retro` weekly.** It tracks trends across weeks, so consistency matters.
- **Git worktrees are essential for multi-terminal.** Without them, builders will conflict.
- **`/setup-browser-cookies` once per session** if you're testing authenticated pages.
