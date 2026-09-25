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
# Everything below is in QUARTER-count units (q): q=0 is count 1, q=2 its "and", q=1/3 its "e"/"a".
# Detail levels, nested: each level only re-cuts inside the level above (phrase > chunk > step > sub-step).
LEVELS = {  # name: (finest metrical position allowed, min q, max q, preferred q, min seconds, cut quantile)
    "beginner": (1, 4, 12, None, 0.30, 0.65),    # on counts; 1-2 counts per step (preferred set by tempo), max 3
    "intermediate": (2, 2, 8, 4, 0.25, 0.50),    # counts and "and"s; half to 2 counts, preferring 1
    "advanced": (3, 1, 4, 2, 0.12, 0.40),        # adds "e"/"a" ONLY where video hits + audio onsets agree
}
# A cut must beat this dance's own evidence at that level: the cost of a cut is the given quantile of the
# scores of that level's candidate points. Absolute thresholds did not transfer: every clip has "some" stop
# near most counts, so a fixed cost cut on every count at every level.
LEN_PENALTY = 0.25                # cost per octave away from the preferred length
ACCENT_W = 0.3                    # an audio accent strengthens a cut the motion already supports, never makes one
CHUNK_COUNTS = 4                  # chunks aim for 4 counts (half an eight)
TRAVEL_M, TURN_DEG, LEVEL_M = 0.20, 45.0, 0.10
IDLE_INSIDE = 4                   # a not-dancing run inside the dance must last this many counts (else it's a hold)


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

def kinematics(doc):
    """Dancer-frame kinematics at the MotionResult's sample rate. Shared by every research script."""
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
    return dict(t=t, body=body, root=root, yaw=yaw, up=up, right=right, fwd=fwd, vel=vel, speed=speed,
                root_v=root_v, part_cols=part_cols, ok=ok, energy=energy_s, vis=vis, ix=ix, root_ok=root_ok)


def idle_counts(k, one, spc, audio=None):
    """Per-count dancing / not-dancing, from signals relative to THIS dance:
    limb  = body-relative limb speed / the dance's 75th percentile;  root = pelvis speed (m/s);
    lock  = share of limb-energy variance at the beat or half-beat frequency over +-2 counts (reported only:
            it separates walking from dancing on bhangra but not reliably on the others);
    music = audio RMS / its median;  seen = share of samples with every limb tip in frame."""
    t, ok = k["t"], k["ok"]
    limb = k["speed"][:, k["part_cols"]].sum(1)
    lvl = np.percentile(limb[ok], 75) + 1e-9
    rms = rt = None
    if audio:
        rms = np.array(audio["rms"])
        rt = np.arange(len(rms)) * audio["rms_hop_s"]
        rms = rms / (np.median(rms[rms > 0]) + 1e-9)
    out = []
    for c in range(math.floor((t[0] - one) / spc), math.floor((t[-1] - one) / spc) + 1):
        a, b = one + c * spc, one + (c + 1) * spc
        m = (t >= a) & (t < b)
        if not m.any():
            continue
        w = (t >= a - 2 * spc) & (t < b + 2 * spc) & ok
        x = limb[w] - limb[w].mean()
        lock = 0.0
        if w.sum() > 8 and x.std() > 0:
            ph = 2 * np.pi * (t[w] - one) / spc
            p = sum(abs(np.sum(x * np.exp(-1j * f * ph))) ** 2 for f in (1, 2)) * 2 / (len(x) * np.sum(x ** 2))
            lock = float(min(1.0, p))
        row = {"c": c, "t0": round(a, 3), "t1": round(b, 3), "seen": float(ok[m].mean()),
               "limb": round(float(limb[m].mean() / lvl), 2), "root": round(float(k["root_v"][m].mean()), 2),
               "lock": round(lock, 2), "music": float(np.interp((a + b) / 2, rt, rms)) if rms is not None else 1.0}
        why = None
        if row["seen"] < 0.5:
            why = "not in frame"
        elif row["music"] < 0.2:
            why = "no music"
        elif row["limb"] < 0.5 and row["root"] > 0.6:
            why = "walking"
        elif row["limb"] < 0.35 and row["root"] < 0.6:
            why = "still"
        row["why"] = why
        out.append(row)
    return out


def idle_spans(counts):
    """Lead-in, outro, and long pauses. The dance starts at the first TWO dancing counts in a row (one
    lively count mid-walk is not a start). Inside the dance only runs of >= IDLE_INSIDE idle counts
    count: a shorter stillness is a hold, and holds are choreography."""
    idle = [r["why"] is not None for r in counts]
    n = len(counts)
    lead = next((i for i in range(n - 1) if not idle[i] and not idle[i + 1]), n)
    tail = next((j + 1 for j in range(n - 1, lead, -1) if not idle[j] and not idle[j - 1]), lead)
    # A single walking/still count at an edge is more often a travelling first step than a walk-in
    # (b822 opens with a side step): trim on motion alone only with 2+ such counts.
    motion_only = lambda rs: sum(r["why"] in ("walking", "still") for r in rs) < 2 and all(  # noqa: E731
        r["why"] in ("walking", "still", None) for r in rs)
    if lead < n and motion_only(counts[:lead]):
        lead = 0
    if tail > lead and motion_only(counts[tail:]):
        tail = n
    why = lambda rs: sorted({r["why"] or "one lively count" for r in rs})  # noqa: E731
    spans = []
    if lead:
        spans.append({"t0": counts[0]["t0"], "t1": counts[lead - 1]["t1"], "kind": "lead-in", "why": why(counts[:lead])})
    i = lead
    while i < tail:
        j = i
        while j < tail and idle[j]:
            j += 1
        if j - i >= IDLE_INSIDE:
            spans.append({"t0": counts[i]["t0"], "t1": counts[j - 1]["t1"], "kind": "pause", "why": why(counts[i:j])})
        i = j + 1 if j == i else j
    if tail < n:
        spans.append({"t0": counts[tail]["t0"], "t1": counts[-1]["t1"], "kind": "outro", "why": why(counts[tail:])})
    start = counts[lead]["t0"] if lead < n else counts[0]["t0"]
    end = counts[tail - 1]["t1"] if tail > lead else counts[-1]["t1"]
    return spans, start, end


def metrical(q):
    """0 = count 1 or 5, 1 = other counts, 2 = "and", 3 = "e"/"a"."""
    return 0 if q % 16 == 0 else 1 if q % 4 == 0 else 2 if q % 2 == 0 else 3


def count_label(q):
    """Quarter index q (0 = count 1) -> '1', '1e', '1&', '1a', '2', ... cycling through an eight."""
    return f"{(q // 4) % 8 + 1}{['', 'e', '&', 'a'][q % 4]}"


def cut_cues(k, spc):
    """Per-sample cut evidence from two cues viewers use to split dance (Di Nota et al. 2020):
    (a) the body nearly stops: a local energy minimum ("kinematic beat", AIST++), scored by prominence;
    (b) the whole-body velocity pattern changes direction (all five tips as one 15-d vector)."""
    t, ok, e, vel = k["t"], k["ok"], k["energy"], k["vel"]
    n, w = len(t), max(2, int(round(spc / 2 / np.median(np.diff(t)))))
    stop = np.zeros(n)
    for i in range(1, n - 1):
        if ok[i] and e[i] <= e[max(0, i - 2):i + 3].min():
            ref = min(e[max(0, i - w):i].max(initial=0), e[i + 1:i + 1 + w].max(initial=0))
            stop[i] = max(0.0, (ref - e[i]) / (ref + 1e-6))
    vs = smooth(vel[:, k["part_cols"]], 1).reshape(n, -1)
    med = np.median(np.linalg.norm(vs, axis=1)[ok]) + 1e-6
    turn = np.zeros(n)
    for i in range(3, n - 3):
        a, b = vs[i - 3:i].mean(0), vs[i + 1:i + 4].mean(0)
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        turn[i] = (1 - a @ b / (na * nb + 1e-9)) / 2 * min(1.0, min(na, nb) / med) if ok[i] else 0.0
    return np.maximum(stop, turn), stop


def fast_evidence(audio, video2d, one, spc):
    """Sub-beat support, from the two sources that see faster than the 15 fps 3D: visible hits in
    native-fps frame differences (video2d) and percussive onsets (audio).
    Returns (hit times, onset times, {q: True} for each "e"/"a" quarter where BOTH land within 1/8 count)."""
    if not audio or not video2d:
        return np.array([]), np.array([]), {}
    from sync import hits_2d  # local import: sync imports this module
    hits = np.array([h[0] for h in hits_2d(video2d)[3]])
    ons = np.array([o[0] for o in audio["onsets"] if o[1] > 0.25])
    fast = {}
    for c in fast_counts(hits, ons, one, spc):
        fast[4 * c + 1] = fast[4 * c + 3] = True
    return hits, ons, fast


def fast_counts(hits, ons, one, spc, tol_frac=1 / 16, need=3):
    """Counts with a 16th-note passage: at least `need` of the count's four 16th positions have a visible
    hit within tol, AND at least `need` have an audio onset within tol, with at least one e/a hit.
    One stray hit near an "e" proves nothing: onsets are dense in busy music (5+/s on bhangra), so a
    single coincidence happens at chance rate. Returns count indices (0 = count 1)."""
    if not len(hits) or not len(ons):
        return []
    tol = spc * tol_frac
    out = []
    for c in range(int((hits.min() - one) / spc) - 1, int((hits.max() - one) / spc) + 1):
        ts = one + (c + np.arange(4) / 4) * spc
        h = [bool(np.any(np.abs(hits - x) <= tol)) for x in ts]
        o = [bool(np.any(np.abs(ons - x) <= tol)) for x in ts]
        if sum(h) >= need and sum(o) >= need and (h[1] or h[3]):
            out.append(c)
    return out


def dp_cut(qs, score, minq, maxq, prefq, min_s, spc, cost=0.35):
    """Choose cuts among candidate quarters `qs` (first and last are forced): maximise summed score,
    minus a cost per cut and a penalty for straying from the preferred length."""
    n = len(qs)
    best = np.full(n, -np.inf)
    prev = np.full(n, -1)
    best[0] = 0
    for j in range(1, n):
        for i in range(j - 1, -1, -1):
            L = qs[j] - qs[i]
            if L > maxq:
                break
            if L < minq or L * spc / 4 < min_s - 1e-6:
                continue
            gain = (score[j] - cost) if j < n - 1 else 0.0
            v = best[i] + gain - LEN_PENALTY * abs(math.log2(L / prefq))
            if v > best[j]:
                best[j], prev[j] = v, i
    if not np.isfinite(best[-1]):
        return [qs[0], qs[-1]]  # nothing fits: keep the parent whole
    out, j = [], n - 1
    while j >= 0:
        out.append(qs[j])
        j = prev[j]
    return out[::-1]


def analyse(doc, audio=None, video2d=None):
    k = kinematics(doc)
    t, body, root, yaw, up, right, fwd = k["t"], k["body"], k["root"], k["yaw"], k["up"], k["right"], k["fwd"]
    speed, part_cols, energy_s, vis, ix, root_ok = (k[x] for x in (
        "speed", "part_cols", "energy", "vis", "ix", "root_ok"))
    pc = doc["proposed_counts"]
    one, spc, bpm = pc["count_one_s"], pc["seconds_per_count"], pc["bpm"]
    qs_ = spc / 4

    # 1. where the dance is
    counts = idle_counts(k, one, spc, audio)
    idle, d0, d1 = idle_spans(counts)
    q_start, q_end = round((d0 - one) / qs_), round((d1 - one) / qs_)

    # 2. evidence at every quarter of the dance
    cue, _ = cut_cues(k, spc)
    hits, ons, fast_q = fast_evidence(audio, video2d, one, spc)
    env = env_t = None
    if audio:
        env = np.array(audio["env"])
        env_t = np.arange(len(env)) * audio["env_hop_s"]
    score, offset = {}, {}
    for q in range(q_start, q_end + 1):
        tq = one + q * qs_
        m = np.where(np.abs(t - tq) <= (qs_ if metrical(q) < 3 else qs_ / 2))[0]
        if not len(m):
            score[q] = 0.0
            continue
        j = m[np.argmax(cue[m])]
        sc = float(cue[j])
        if env is not None:
            acc = float(np.clip(env[(env_t >= tq - 0.04) & (env_t <= tq + 0.04)].max(initial=0), 0, 1))
            sc = min(1.0, sc * (1 + ACCENT_W * acc))
        if metrical(q) == 3:  # too fast for the 3D alone: needs a visible hit AND an onset
            sc = 0.9 if fast_q.get(q) else 0.0
        score[q], offset[q] = sc, float(t[j] - tq)

    # 3. nested cuts, coarse to fine
    pref_beg = 8 if bpm >= 110 else 4  # beginner: 2 counts at dance tempo, 1 count when the song is slow
    levels, parents = {}, [(q_start, q_end)]
    for name, (finest, minq, maxq, prefq, min_s, quant) in LEVELS.items():
        prefq = prefq or pref_beg
        pool = [v for q, v in score.items() if metrical(q) <= finest and (metrical(q) < 3 or fast_q.get(q))]
        cost = float(np.quantile(pool, quant)) if pool else 0.35
        cuts = []
        for a, b in parents:
            cand = [q for q in range(a, b + 1)
                    if q in (a, b) or (metrical(q) <= finest and (metrical(q) < 3 or fast_q.get(q)))]
            c = dp_cut(cand, [score.get(q, 0.0) for q in cand], min(minq, b - a), maxq, prefq,
                       min(min_s, (b - a) * qs_), spc, cost)
            cuts.extend(c if not cuts else c[1:])
        rows = []
        for a, b in zip(cuts[:-1], cuts[1:]):
            ta, tb = one + a * qs_, one + b * qs_
            r = step_features(t, ta, tb, a, b, body, root, yaw, up, right, fwd, speed, energy_s, vis, part_cols, ix,
                              score.get(b, 0.0), offset.get(b, 0.0), root_ok)
            r["parent"] = None if name == "beginner" else next(i for i, (pa, pb) in enumerate(parents) if pa <= a < pb)
            r["sub_beat"] = metrical(a) == 3 or metrical(b) == 3
            if tb - ta < 3 * np.median(np.diff(t)):
                r["moves"], r["lead"] = [], []
                r["note"] = "too fast for the 3D to describe; follow the video"
            rows.append(r)
        label_quality(rows)
        levels[name] = rows
        parents = list(zip(cuts[:-1], cuts[1:]))

    chunks = make_chunks(levels["beginner"])
    of = {si: ci for ci, c in enumerate(chunks) for si in c["steps"]}
    for s_i, s in enumerate(levels["beginner"]):
        s["chunk"] = of[s_i]
    for up_name, name in (("beginner", "intermediate"), ("intermediate", "advanced")):
        for s in levels[name]:
            s["chunk"] = levels[up_name][s["parent"]]["chunk"]
    return {"t_range": [float(t[0]), float(t[-1])], "count_one_s": one, "seconds_per_count": spc, "bpm": bpm,
            "dance_span": [d0, d1], "idle": idle,
            "counts_idle": [{x: r[x] for x in ("t0", "why", "limb", "root", "lock")} for r in counts],
            "levels": levels, "steps": levels["beginner"], "chunks": chunks,
            "fast_quarters": sorted(fast_q), "hits_2d": [round(float(x), 3) for x in hits],
            "onsets": [round(float(x), 3) for x in ons],
            "energy": [[round(float(a), 3), round(float(b), 3)] for a, b in zip(t, energy_s)]}


def make_chunks(steps):
    """Group beginner steps into ~CHUNK_COUNTS-count chunks: close at a cut on count 1 or 5 (or the "and"
    after) once the chunk has 3+ counts, or anyway past 6 counts."""
    chunks, cur = [], []
    for s in steps:
        cur.append(s)
        span = (cur[-1]["k"][1] - cur[0]["k"][0]) / 4
        if (span >= CHUNK_COUNTS - 1 and cur[-1]["k"][1] % 16 in (0, 2)) or span >= CHUNK_COUNTS + 2:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return [{"steps": [steps.index(s) for s in c], "start_s": c[0]["start_s"], "end_s": c[-1]["end_s"],
             "counts": f"{c[0]['counts'].split('–')[0]}–{c[-1]['counts'].split('–')[1]}"} for c in chunks]


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
            "counts": f"{count_label(ka)}–{count_label(kb)}", "quarters": int(kb - ka),
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


# ---------------------------------------------------------------- output

TARGET = {"beginner": (1, 2), "intermediate": (0.5, 1), "advanced": (0.25, 1)}  # counts per step a teacher uses


def level_stats(r):
    """Per level: step count, median counts/step, share inside the teacher range, where cuts land."""
    out = {}
    for name, rows in r["levels"].items():
        L = np.array([s["quarters"] / 4 for s in rows])
        lo, hi = TARGET[name]
        ends = [s["k"][1] % 4 for s in rows[:-1]]
        out[name] = {"steps": len(rows), "median_counts": float(np.median(L)),
                     "in_range_pct": int(round(100 * np.mean((L >= lo) & (L <= hi)))),
                     "cuts_on_count": sum(e == 0 for e in ends), "cuts_on_and": sum(e == 2 for e in ends),
                     "cuts_on_e_a": sum(e in (1, 3) for e in ends)}
    return out


def table(job, name, r):
    ls = level_stats(r)
    idle = "; ".join(f"{s['kind']} {s['t0']:.1f}–{s['t1']:.1f} s ({', '.join(s['why'])})" for s in r["idle"]) or "none"
    lines = [f"## {name} (`{job}`)", "",
             f"{r['bpm']:.1f} BPM, {r['seconds_per_count']:.3f} s/count, count 1 at {r['count_one_s']:.2f} s. "
             f"Dance {r['dance_span'][0]:.2f}–{r['dance_span'][1]:.2f} s. Not dancing: {idle}.", "",
             "| level | steps | median counts/step | in teacher range | cuts on count / & / e,a |", "|---|---|---|---|---|"]
    for lv, s in ls.items():
        lines.append(f"| {lv} | {s['steps']} | {s['median_counts']:g} | {s['in_range_pct']}% | "
                     f"{s['cuts_on_count']} / {s['cuts_on_and']} / {s['cuts_on_e_a']} |")
    lines += ["", "Beginner steps, with the intermediate and advanced cuts nested inside each:", "",
              "| chunk | step | time (s) | counts | intermediate | advanced | leads / direction (dancer's frame) | whole body | quality | cut clarity | unsure |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    inter, adv = r["levels"]["intermediate"], r["levels"]["advanced"]
    for ci, c in enumerate(r["chunks"], 1):
        for n, si in enumerate(c["steps"]):
            s = r["steps"][si]
            kids = [i for i, x in enumerate(inter) if x["parent"] == si]
            mid = " · ".join(inter[i]["counts"] for i in kids) if len(kids) > 1 else "—"
            sub = [x for x in adv if x["parent"] in kids]
            fine = " · ".join(x["counts"] + ("*" if x["sub_beat"] else "") for x in sub) if len(sub) > len(kids) else "—"
            lines.append(f"| {ci if n == 0 else ''} | {si + 1} | {s['start_s']:.2f}–{s['end_s']:.2f} | {s['counts']} | {mid} | {fine} | "
                         f"{'; '.join(s['moves']) or '—'} | {', '.join(s['whole_body']) or '—'} | "
                         f"{s['quality']} | {s['end_cue']:.2f} | {', '.join(s['uncertain_parts']) or ''} |")
    return "\n".join(lines) + "\n"


def check():
    """Synthetic: evidence on every count and nothing between -> cuts on counts, lengths as preferred."""
    qs = list(range(0, 33))
    score = [1.0 if q % 4 == 0 else 0.0 for q in qs]
    cand = [q for q in qs if metrical(q) <= 2]
    cuts = dp_cut(cand, [score[q] for q in cand], 2, 8, 4, 0.1, 0.5)
    assert all(q % 4 == 0 for q in cuts), cuts
    assert all(b - a == 4 for a, b in zip(cuts[:-1], cuts[1:])), cuts
    assert dp_cut([0, 1], [0, 0], 4, 16, 8, 0.3, 0.5) == [0, 1]  # too short to cut: parent kept whole
    assert count_label(0) == "1" and count_label(2) == "1&" and count_label(7) == "2a" and count_label(32) == "1"
    assert [metrical(q) for q in (0, 4, 2, 1, 16)] == [0, 1, 2, 3, 0]
    assert direction(np.array([0.3, 0, 0])) == "to their right"
    counts = [{"t0": i, "t1": i + 1, "why": w} for i, w in enumerate(["walking", "walking", None, "walking", None, None,
                                                                          None, "still", "still", None, None, "no music"])]
    spans, a, b = idle_spans(counts)
    assert (a, b) == (4, 11) and [s["kind"] for s in spans] == ["lead-in", "outro"], (a, b, spans)
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
        side = {}
        for kind in ("audio", "video2d"):  # optional: from audio.py and video2d.py
            p = os.path.join(HERE, ".cache", f"{job}.{kind}.json")
            side[kind] = json.load(open(p)) if os.path.exists(p) else None
        r = analyse(json.load(open(path)), **side)
        r["job_id"], r["name"] = job, name
        r["stats"] = level_stats(r)
        data[name] = r
        summary.append(table(job, name, r))
    open(os.path.join(out, "steps.md"), "w").write(
        "# Proposed steps per lesson\n\nGenerated by `segment.py`. Counts are on each lesson's machine-proposed grid "
        "(Beat This!), not authored counts. Left/right are the DANCER's. \"cut clarity\" is the cut evidence at the "
        "step's end (0–1). `*` marks a sub-beat (e/a) cut, made only where a visible hit and an audio onset agree.\n\n"
        + "\n".join(summary))
    json.dump(data, open(os.path.join(out, "steps.json"), "w"))
    page = open(os.path.join(HERE, "viewer.html")).read().replace("/*DATA*/null", json.dumps(data))
    open(os.path.join(out, "viewer.html"), "w").write(page)
    print("\n".join(summary))


if __name__ == "__main__":
    main()
