"""Propose teachable "steps" and "chunks" from a MotionResult. Research prototype, not production.

No new models: forward kinematics over the contract's joint rotations, a body-relative motion
energy curve, and a small dynamic program that places step boundaries on the count grid's
half-beats where the body is closest to a held pose.

    sh fetch.sh                      # public MotionResults -> .cache/
    python segment.py                # out/steps.md (tables), out/steps.json, out/viewer.html
    python segment.py --check        # self-check on a synthetic clip

Needs numpy only (pyenv 'stepwise' has it).
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LESSONS = {
    "job_5716ecd319064b329b53df005b736757": "bhangra",
    "job_345b747b1edb406a90e8f0d847b9c518": "choreo",
    "job_b8223229f23240d39305493bbe628d7d": "b822",
    "job_a10682e744734f0fb4034149fb4c0569": "a106",
    "job_7995c97829a942aba13301fcd14704dd": "7995",
}

# End effectors per body part (MHR names). Motion of a part = motion of its tip in the dancer's frame.
PARTS = {
    "left arm": "l_wrist", "right arm": "r_wrist",
    "left leg": "l_ball", "right leg": "r_ball",
    "head": "c_head",
}
EXTRA = ["root", "l_upleg", "r_upleg", "l_lowarm", "r_lowarm", "l_lowleg", "r_lowleg", "c_spine3"]

# Tunables (the calibration knobs). Chosen by eye on the five lessons, not fitted.
MAX_HALF = 8                      # a step is at most 4 counts
MIN_STEP_S = 0.25                 # ...and at least this long: at 15 fps a shorter step is 4 samples of noise
FAST_SPC = 0.45                   # faster than ~133 BPM, prefer 2-count steps instead of 1-count
LEN_PENALTY = 0.15                # cost per octave away from PREF_HALF
BOUNDARY_COST = 0.35              # a cut has to be at least this clear to be worth making
CHUNK_COUNTS = 4                  # chunks aim for 4 counts (half an eight)
TRAVEL_M, TURN_DEG, LEVEL_M = 0.20, 45.0, 0.10


# ---------------------------------------------------------------- kinematics

def qmul(a, b):
    ax, ay, az, aw = np.moveaxis(a, -1, 0)
    bx, by, bz, bw = np.moveaxis(b, -1, 0)
    return np.stack([aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz], -1)


def qrot(q, v):
    x, y, z, w = np.moveaxis(q, -1, 0)
    t = 2 * np.stack([y * v[..., 2] - z * v[..., 1], z * v[..., 0] - x * v[..., 2], x * v[..., 1] - y * v[..., 0]], -1)
    tx, ty, tz = np.moveaxis(t, -1, 0)
    return v + w[..., None] * t + np.stack([y * tz - z * ty, z * tx - x * tz, x * ty - y * tx], -1)


def world_positions(doc, person, names):
    """(T, len(names), 3) world positions; same FK as apps/web/lib/footContact.ts jointWorldPosition."""
    joints = doc["joint_hierarchy"]["joints"]
    root_idx = doc["joint_hierarchy"]["root_joint_index"]
    by_name = {j["name"]: j["index"] for j in joints}
    rt = person["root_trajectory"]
    T = len(rt)
    rot = {root_idx: np.array([r["rotation"] for r in rt], float)}
    pos = {root_idx: np.array([r["position"] for r in rt], float)}
    local = np.array([[j["rotation"] for j in s["joints"]] for s in person["samples"]], float)  # (T,127,4)

    def solve(i):
        if i in pos:
            return
        p = joints[i]["parent_index"]
        solve(p)
        pos[i] = pos[p] + qrot(rot[p], np.broadcast_to(np.array(joints[i]["rest_translation"], float), (T, 3)))
        rot[i] = qmul(rot[p], qmul(np.broadcast_to(np.array(joints[i]["rest_rotation"], float), (T, 4)), local[:, i]))

    out = []
    for n in names:
        solve(by_name[n])
        out.append(pos[by_name[n]])
    return np.stack(out, 1)


def visibility(person, doc, names):
    by_name = {j["name"]: j["index"] for j in doc["joint_hierarchy"]["joints"]}
    code = {"observed": 2, "uncertain": 1, "absent": 0}
    return np.array([[code.get(s["joints"][by_name[n]].get("visibility"), 0) for n in names] for s in person["samples"]])


def smooth(x, k=3):
    """Centered moving average along axis 0 (k samples each side), edge-padded."""
    pad = np.concatenate([np.repeat(x[:1], k, 0), x, np.repeat(x[-1:], k, 0)])
    c = np.cumsum(pad, 0)
    c = np.concatenate([np.zeros_like(c[:1]), c])
    return (c[2 * k + 1:] - c[:-2 * k - 1]) / (2 * k + 1)


# ---------------------------------------------------------------- analysis

def analyse(doc):
    person = doc["persons"][0]  # ponytail: first dancer only; group lessons need a dancer picker
    t = np.array(doc["sample_times_s"], float)
    names = list(PARTS.values()) + EXTRA
    P = smooth(world_positions(doc, person, names), 1)
    vis = visibility(person, doc, names)
    ix = {n: i for i, n in enumerate(names)}
    root_ok = np.array([r["provenance"].get("suppressed") is None for r in person["root_trajectory"]])

    g = doc.get("grounding") or {}
    up = np.array(g["floor_plane"]["normal"], float) if g.get("status") == "grounded" else np.array([0, 1, 0.0])
    up /= np.linalg.norm(up)
    right = P[:, ix["r_upleg"]] - P[:, ix["l_upleg"]]
    right -= (right @ up)[:, None] * up
    right /= np.linalg.norm(right, axis=1, keepdims=True) + 1e-9
    right = smooth(right, 3)
    right /= np.linalg.norm(right, axis=1, keepdims=True) + 1e-9
    fwd = np.cross(up, right)
    e1 = np.cross(up, [0, 0, 1.0]) if abs(up[2]) < 0.9 else np.cross(up, [1.0, 0, 0])
    e1 /= np.linalg.norm(e1)
    yaw = np.unwrap(np.arctan2(fwd @ np.cross(up, e1), fwd @ e1))  # + = counter-clockwise from above = toward dancer's left

    root = P[:, ix["root"]]
    rel = P - root[:, None]
    # dancer frame: x = dancer's right, y = up, z = dancer's forward
    body = np.stack([np.einsum("tjk,tk->tj", rel, right), rel @ up, np.einsum("tjk,tk->tj", rel, fwd)], -1)  # (T, J, 3)

    dt = np.gradient(t)
    vel = np.gradient(body, axis=0) / dt[:, None, None]
    speed = np.linalg.norm(vel, axis=2)                      # (T, J) body-relative
    root_v = np.linalg.norm(np.gradient(root, axis=0) / dt[:, None], axis=1)
    part_cols = [ix[n] for n in PARTS.values()]
    ok = vis[:, part_cols].min(1) > 0                        # every tip at least "uncertain"
    energy = speed[:, part_cols].sum(1) + 2 * root_v
    energy = np.where(ok, energy, np.nan)
    energy_s = smooth(np.nan_to_num(energy, nan=np.nanmedian(energy)), 1)

    pc = doc["proposed_counts"]
    one, spc = pc["count_one_s"], pc["seconds_per_count"]
    half = spc / 2
    # half-beat grid over the span where the dancer is in frame
    active = np.where(ok)[0]
    t0, t1 = t[active[0]], t[active[-1]]
    k0 = math.ceil((t0 - one) / half)
    k1 = math.floor((t1 - one) / half)
    grid_k = np.arange(k0, k1 + 1)
    grid_t = one + grid_k * half

    # Candidate cut points, per sample, from two cues viewers use to split dance (Di Nota et al. 2020):
    # (a) the body nearly stops: a local minimum of energy ("kinematic beat", AIST++), scored by prominence;
    # (b) a leading limb changes direction: 1 - cos between velocity just before and just after.
    n, w = len(t), max(2, int(round(half / np.median(np.diff(t)))))
    stop = np.zeros(n)
    for i in range(1, n - 1):
        if ok[i] and energy_s[i] <= energy_s[max(0, i - 2):i + 3].min():
            ref = min(energy_s[max(0, i - w):i].max(initial=0), energy_s[i + 1:i + 1 + w].max(initial=0))
            stop[i] = max(0.0, (ref - energy_s[i]) / (ref + 1e-6))
    # whole-body velocity pattern (all five tips as one 15-d vector): a new move changes the pattern,
    # one limb reversing inside a move does not.
    vel_s = smooth(vel[:, part_cols], 1).reshape(n, -1)
    norms = np.linalg.norm(vel_s, axis=1)
    med = np.median(norms[ok]) + 1e-6
    turn_sig = np.zeros(n)
    for i in range(3, n - 3):
        a, b = vel_s[i - 3:i].mean(0), vel_s[i + 1:i + 4].mean(0)
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        cos = a @ b / (na * nb + 1e-9)
        turn_sig[i] = (1 - cos) / 2 * min(1.0, min(na, nb) / med) if ok[i] else 0.0
    cue = np.maximum(stop, turn_sig)

    # Score each half-beat by the best cue within +-1/4 count (timing slop), and remember the offset.
    score, offset = np.zeros(len(grid_t)), np.zeros(len(grid_t))
    for gi, tt in enumerate(grid_t):
        m = np.where(np.abs(t - tt) <= half / 2)[0]
        if len(m):
            j = m[np.argmax(cue[m])]
            score[gi], offset[gi] = cue[j], t[j] - tt

    # Diagnostic: do the body's own clear stops land on counts or on "and"s?
    clear = np.where(stop > 0.4)[0]
    phase = ((t[clear] - one) / spc) % 1.0                        # 0 = on the count, 0.5 = on the "and"
    align = {"clear_stops": int(len(clear)),
             "near_count": int(np.sum((phase < 0.2) | (phase > 0.8))),
             "near_and": int(np.sum((phase > 0.3) & (phase < 0.7)))}
    # Energy folded onto one count (8 bins, bin 0 = on the count, bin 4 = on the "and"), as % of the mean.
    # The bin where the body is stillest is where this dance "lands" relative to the proposed grid.
    ph = (((t - one) / spc) % 1.0 * 8).astype(int)[ok]
    fold = np.array([energy_s[ok][ph == b].mean() for b in range(8)])
    align["fold_pct"] = [int(round(100 * x / fold.mean())) for x in fold]
    align["stillest_phase"] = f"{np.argmin(fold) / 8:.3f} of a count after the count"

    steps = dp_steps(score, max(1, math.ceil(MIN_STEP_S / half)), 4 if spc < FAST_SPC else 2)
    rows = []
    for a, b in zip(steps[:-1], steps[1:]):
        rows.append(step_features(t, grid_t[a], grid_t[b], grid_k[a], grid_k[b], body, root, yaw, up, right, fwd, speed,
                                  energy_s, vis, part_cols, ix, score[b], offset[b], root_ok))
    label_quality(rows)
    chunks = make_chunks(rows)
    return {"t_range": [float(t0), float(t1)], "count_one_s": one, "seconds_per_count": spc, "bpm": pc["bpm"],
            "steps": rows, "chunks": chunks, "alignment": align,
            "grid": [[round(float(a), 3), round(float(b), 2)] for a, b in zip(grid_t, score)],
            "energy": [[round(float(a), 3), round(float(b), 3)] for a, b in zip(t, energy_s)]}


def dp_steps(score, min_half=1, pref_half=2):
    """Pick boundary indices into the half-beat grid: maximise summed boundary score, penalise odd step lengths."""
    n = len(score)
    best = np.full(n, -np.inf)
    prev = np.full(n, -1)
    best[0] = 0
    for j in range(1, n):
        for L in range(min_half, MAX_HALF + 1):
            i = j - L
            if i < 0:
                break
            v = best[i] + score[j] - BOUNDARY_COST - LEN_PENALTY * abs(math.log2(L / pref_half))
            if v > best[j]:
                best[j], prev[j] = v, i
    out, j = [], n - 1
    while j >= 0:
        out.append(j)
        j = prev[j]
    return out[::-1]


def count_label(k):
    """Half-beat index k (0 = count 1) -> '1', '1&', ... cycling through an eight."""
    c = (k // 2) % 8 + 1
    return f"{c}&" if k % 2 else f"{c}"


def step_features(t, ta, tb, ka, kb, body, root, yaw, up, right, fwd, speed, energy, vis, part_cols, ix,
                  end_score, end_off, root_ok):
    idx = np.where((t >= ta) & (t <= tb))[0]
    parts = list(PARTS)
    path = np.array([np.sum(speed[idx, c]) * np.median(np.diff(t)) for c in part_cols])  # metres moved, body frame
    lead = [parts[i] for i in np.argsort(-path) if path[i] >= 0.6 * path.max() and path[i] > 0.15][:2]

    moves = []
    for p in lead:
        tr = body[idx, ix[PARTS[p]]] - body[idx[0], ix[PARTS[p]]]
        far = int(np.argmax(np.linalg.norm(tr, axis=1)))
        back = np.linalg.norm(tr[-1]) < 0.5 * np.linalg.norm(tr[far])
        moves.append(f"{p} {direction(tr[far])}{' and back' if back and far < len(idx) - 1 else ''}")
    whole = []
    if root_ok[idx[0]] and root_ok[idx[-1]]:  # only claim travel/level where the pelvis was really tracked
        travel = root[idx[-1]] - root[idx[0]]
        travel -= (travel @ up) * up
        if np.linalg.norm(travel) > TRAVEL_M:
            d = np.array([travel @ right[idx[0]], 0, travel @ fwd[idx[0]]])  # dancer's frame at step start
            whole.append(f"travel {direction(d, 0.5 * TRAVEL_M)} {np.linalg.norm(travel):.1f} m")
        lv = (root[idx] - root[idx[0]]) @ up
        if lv.min() < -LEVEL_M:
            whole.append("drop" + (" and up" if lv[-1] > 0.5 * lv.min() else ""))
        elif lv.max() > LEVEL_M:
            whole.append("jump/rise")
    turn = math.degrees(yaw[idx[-1]] - yaw[idx[0]])
    if abs(turn) > TURN_DEG:
        whole.append(f"turn {abs(turn):.0f}° to their {'left' if turn > 0 else 'right'}")

    e = energy[idx]
    seen = vis[idx][:, part_cols]
    unsure = [p for i, p in enumerate(parts) if p in lead and (seen[:, i] < 2).mean() > 0.5]
    return {"start_s": round(float(ta), 3), "end_s": round(float(tb), 3),
            "counts": f"{count_label(ka)}–{count_label(kb)}", "half_beats": int(kb - ka),
            "lead": lead, "moves": moves, "whole_body": whole,
            "mean_energy": round(float(e.mean()), 2), "peakiness": round(float(e.max() / (e.mean() + 1e-6)), 2),
            "end_cue": round(float(end_score), 2), "end_offset_s": round(float(end_off), 3),
            "path_m": {p: round(float(x), 2) for p, x in zip(parts, path)},
            "turn_deg": round(turn, 1), "uncertain_parts": unsure, "k": [int(ka), int(kb)]}


def label_quality(rows):
    """Quality words relative to THIS dance: no absolute threshold holds across dancers and cameras."""
    me = np.array([r["mean_energy"] for r in rows])
    pk = np.array([r["peakiness"] for r in rows])
    lo_e, hi_pk, lo_pk = np.percentile(me, 20), np.percentile(pk, 75), np.percentile(pk, 30)
    for r in rows:
        if r["mean_energy"] <= lo_e:
            r["quality"] = "small / hold"
        elif r["peakiness"] >= hi_pk and r["end_cue"] >= 0.5:
            r["quality"] = "sharp (hits and stops)"
        elif r["peakiness"] <= lo_pk:
            r["quality"] = "smooth / even"
        else:
            r["quality"] = "—"


def direction(d, floor=0.12):
    """Dominant axes of a displacement in the dancer's frame (x right, y up, z forward)."""
    words = []
    for axis, (neg, pos) in enumerate([("to their left", "to their right"), ("down", "up"), ("back", "forward")]):
        if abs(d[axis]) > floor and abs(d[axis]) >= 0.5 * np.abs(d).max():
            words.append(pos if d[axis] > 0 else neg)
    return " & ".join(words) or "in place"


def make_chunks(steps):
    """Group steps into ~CHUNK_COUNTS-count chunks: cut at a step boundary within half a count of a half-eight
    (count 1 or 5, or the "and" after, since some dances land on the "and"), else once it passes 6 counts."""
    chunks, cur = [], []
    for s in steps:
        cur.append(s)
        span = (cur[-1]["k"][1] - cur[0]["k"][0]) / 2
        near_half_eight = cur[-1]["k"][1] % 8 in (0, 1)
        if (span >= CHUNK_COUNTS - 1 and near_half_eight) or span >= CHUNK_COUNTS + 2:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return [{"steps": [steps.index(s) for s in c], "start_s": c[0]["start_s"], "end_s": c[-1]["end_s"],
             "counts": f"{c[0]['counts'].split('–')[0]}–{c[-1]['counts'].split('–')[1]}"} for c in chunks]


# ---------------------------------------------------------------- output

def table(job, name, r):
    lines = [f"## {name} (`{job}`)", "",
             f"{r['bpm']:.1f} BPM, {r['seconds_per_count']:.3f} s/count, count 1 at {r['count_one_s']:.2f} s. "
             f"{len(r['steps'])} steps in {len(r['chunks'])} chunks over {r['t_range'][0]:.1f}–{r['t_range'][1]:.1f} s.", "",
             "| chunk | step | time (s) | counts | leads | direction (dancer's frame) | whole body | quality | cut clarity | unsure |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for ci, c in enumerate(r["chunks"], 1):
        for n, si in enumerate(c["steps"]):
            s = r["steps"][si]
            lines.append(f"| {ci if n == 0 else ''} | {si + 1} | {s['start_s']:.2f}–{s['end_s']:.2f} | {s['counts']} | "
                         f"{', '.join(s['lead']) or '—'} | {'; '.join(s['moves']) or '—'} | {', '.join(s['whole_body']) or '—'} | "
                         f"{s['quality']} | {s['end_cue']:.2f} | {', '.join(s['uncertain_parts']) or ''} |")
    return "\n".join(lines) + "\n"


def check():
    """Synthetic: score peaks every count -> DP must put a boundary on every count."""
    score = np.tile([1.0, 0.0], 16)
    b = dp_steps(score)
    assert all(k % 2 == 0 for k in b[:-1]), b  # last index is the forced clip end
    assert all(2 <= y - x <= 2 for x, y in zip(b[:-2], b[1:-1])), b
    assert count_label(0) == "1" and count_label(3) == "2&" and count_label(16) == "1"
    assert direction(np.array([0.3, 0, 0])) == "to their right"
    print("ok")


def main():
    if "--check" in sys.argv:
        return check()
    out = os.path.join(HERE, "out")
    os.makedirs(out, exist_ok=True)
    summary, data = [], {}
    for job, name in LESSONS.items():
        path = os.path.join(HERE, ".cache", f"{job}.json")
        if not os.path.exists(path):
            print(f"skip {job}: run fetch.sh first")
            continue
        r = analyse(json.load(open(path)))
        r["job_id"], r["name"] = job, name
        data[name] = r
        summary.append(table(job, name, r))
    open(os.path.join(out, "steps.md"), "w").write(
        "# Proposed steps per lesson\n\nGenerated by `segment.py`. Counts are on each lesson's machine-proposed grid, "
        "not authored counts. Left/right are the DANCER's. \"cut clarity\" is the boundary cue at the step's end (0–1).\n\n"
        + "\n".join(summary))
    json.dump(data, open(os.path.join(out, "steps.json"), "w"))
    page = open(os.path.join(HERE, "viewer.html")).read().replace("/*DATA*/null", json.dumps(data))
    open(os.path.join(out, "viewer.html"), "w").write(page)
    print("\n".join(summary))


if __name__ == "__main__":
    main()
