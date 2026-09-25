"""Score every method on the labelled clips and print the comparison.

    python evaluate.py            -> table + per-clip scores (results.json)
"""
import glob, json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DANCE_GATE_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data")
L_WRIST, R_WRIST, L_ANK, R_ANK, L_KNEE, R_KNEE, L_ELB, R_ELB = 9, 10, 15, 16, 13, 14, 7, 8
L_SH, R_SH, L_HIP, R_HIP = 5, 6, 11, 12
LIMBS = [L_WRIST, R_WRIST, L_ANK, R_ANK, L_KNEE, R_KNEE, L_ELB, R_ELB]


def labels():
    out = {}
    for lab in ("pos", "neg", "amb"):
        for p in glob.glob(os.path.join(DATA, "clips", lab, "*.mp4")):
            out[os.path.splitext(os.path.basename(p))[0]] = lab
    return out


def main_person(K, B, H_over_W):
    """Per frame: the most confident person (score > 0.5), else NaN. Returns kpts (T,17,3), box (T,5)."""
    T = len(K)
    kp = np.full((T, 17, 3), np.nan, np.float32); bx = np.full((T, 5), np.nan, np.float32)
    for t in range(T):
        s = B[t, :, 4]
        if s.max() > 0.5:
            j = int(s.argmax())
            kp[t] = K[t, j]; bx[t] = B[t, j]
    return kp, bx


def features_a(npz, fps_sub=8, window_s=None):
    d = np.load(npz, allow_pickle=True)
    K, B, fps = d["K"], d["B"], int(d["fps"])
    W, H = float(d["W"]), float(d["H"])
    step = max(1, fps // fps_sub)
    K, B = K[::step], B[::step]
    f = fps / step
    if window_s:
        K, B = K[: int(window_s * f)], B[: int(window_s * f)]
    kp, bx = main_person(K, B, H / W)
    present = ~np.isnan(bx[:, 0])
    feats = {"person_frac": float(present.mean()) if len(present) else 0.0,
             "n_frames": int(len(K))}
    audio = json.loads(str(d["audio"]))
    feats.update({k: audio.get(k, 0.0) for k in ("has_audio", "pulse_clarity", "perc_ratio", "flatness", "rms_db")})
    beats = d["beats"]
    feats["n_beats"] = int(len(beats))
    if len(beats) > 3:
        ibi = np.diff(beats)
        feats["beat_cv"] = float(np.std(ibi) / np.median(ibi))
        feats["bpm"] = float(60 / np.median(ibi))
    else:
        feats["beat_cv"] = 9.0; feats["bpm"] = 0.0
    if present.sum() < 4:
        feats.update(limb=0.0, rhythm=0.0, full_body=0.0, height=0.0, travel=0.0, active=0.0)
        return feats
    # pixel coords (aspect-correct), body scale = box height
    xy = kp[..., :2] * np.array([W, H], np.float32)
    conf = kp[..., 2]
    hgt = (bx[:, 3] - bx[:, 1]) * H
    feats["height"] = float(np.nanmedian(bx[:, 3] - bx[:, 1]))
    fb = ((conf[:, L_ANK] > 0.4) | (conf[:, R_ANK] > 0.4)) & (conf[:, L_SH] > 0.4)
    feats["full_body"] = float(fb[present].mean())
    hip = np.nanmean(xy[:, [L_HIP, R_HIP]], axis=1)
    rel = (xy - hip[:, None, :]) / hgt[:, None, None]  # body-relative, body heights
    v = np.linalg.norm(np.diff(rel, axis=0), axis=-1) * f  # (T-1, 17) body heights / s
    ok = (conf[1:] > 0.3) & (conf[:-1] > 0.3)
    v = np.where(ok, v, np.nan)[:, LIMBS]
    v = np.clip(v, 0, 8)  # a keypoint jump is not a dance move
    limb = np.nanmean(v, axis=1)
    good = ~np.isnan(limb)
    feats["limb"] = float(np.nanmedian(limb)) if good.any() else 0.0
    feats["active"] = float(np.mean(limb[good] > 0.5)) if good.any() else 0.0
    pv = np.linalg.norm(np.diff(hip, axis=0), axis=-1) * f / hgt[1:]
    feats["travel"] = float(np.nanmedian(pv)) if np.isfinite(pv).any() else 0.0
    # rhythm: autocorrelation of the limb-speed signal, best peak at 0.3-2.0 s
    x = np.where(good, limb, np.nanmean(limb[good]) if good.any() else 0)
    x = x - x.mean()
    if len(x) > 3 * f and x.std() > 0:
        ac = np.correlate(x, x, "full")[len(x) - 1:] / (x.var() * len(x))
        lo, hi = int(0.3 * f), min(int(2.0 * f), len(ac) - 1)
        feats["rhythm"] = float(ac[lo:hi].max()) if hi > lo else 0.0
    else:
        feats["rhythm"] = 0.0
    return feats


def score_a(ft):
    """Option A as one number in [0,1]: person gate x movement evidence. Deliberately lenient.

    - No person in >= 30% of sampled frames -> 0 (nothing to reconstruct anyway).
    - Movement: body-relative limb speed, saturating at 1.0 body height/s.
    - Music/rhythm only ever ADD evidence; their absence never rejects (muted dances exist).
    """
    if ft["person_frac"] < 0.3:
        return 0.0
    move = min(ft["limb"] / 1.0, 1.0)
    rhythm = max(0.0, min(ft["rhythm"] / 0.5, 1.0))
    music = 1.0 if (ft["n_beats"] >= 8 and ft["beat_cv"] < 0.25) else 0.0
    return float(min(1.0, 0.6 * move + 0.2 * rhythm + 0.2 * music) * min(1.0, ft["person_frac"] / 0.6))


def auc(pos, neg):
    if not pos or not neg:
        return float("nan")
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg]))


def metrics(name, scores, lab, thr=None):
    pos = [s for k, s in scores.items() if lab.get(k) == "pos"]
    neg = [s for k, s in scores.items() if lab.get(k) == "neg"]
    ours = [s for k, s in scores.items() if lab.get(k) == "pos" and (k.startswith("job_") or k.startswith("eval_") or k.startswith("synth_"))]
    zero_fr = min(pos)  # the highest threshold that still passes every positive
    row = {"method": name, "n_pos": len(pos), "n_neg": len(neg), "auc": auc(pos, neg),
           "min_pos": zero_fr, "min_ours": min(ours) if ours else None,
           "neg_rejected_at_zero_false_reject": float(np.mean([n < zero_fr for n in neg]))}
    if thr is not None:
        tp = sum(p >= thr for p in pos); fn = len(pos) - tp
        fp = sum(n >= thr for n in neg); tn = len(neg) - fp
        row.update({"thr": thr, "recall": tp / len(pos), "false_rejects": fn,
                    "precision": tp / (tp + fp) if tp + fp else float("nan"),
                    "neg_rejected": tn / len(neg), "ours_rejected": sum(o < thr for o in ours)})
    return row


def load_json_scores(method):
    out = {}
    for p in glob.glob(os.path.join(DATA, "cache", method, "*.json")):
        try:
            out[os.path.splitext(os.path.basename(p))[0]] = json.load(open(p))
        except json.JSONDecodeError:
            print("corrupt cache (concurrent write), re-run:", p)
    return out


def main():
    lab = labels()
    rows, per_clip = [], {}
    A = {}
    for p in glob.glob(os.path.join(DATA, "cache", "a", "*.npz")):
        k = os.path.splitext(os.path.basename(p))[0]
        if k in lab:
            A[k] = features_a(p)
    for k, ft in A.items():
        per_clip.setdefault(k, {"label": lab[k]})["a_feats"] = ft
        per_clip[k]["a"] = score_a(ft)
    if A:
        rows.append(metrics("A: own signals", {k: per_clip[k]["a"] for k in A}, lab, thr=0.25))
        # cheaper sampling: 4 fps, first 20 s only
        A2 = {k: score_a(features_a(os.path.join(DATA, "cache", "a", k + ".npz"), fps_sub=4, window_s=20)) for k in A}
        for k, s in A2.items():
            per_clip[k]["a_4fps20s"] = s
        # the gate's budget: 2 fps over the first 16 s = 32 pose frames
        for k in A:
            per_clip[k]["a_lite_feats"] = features_a(os.path.join(DATA, "cache", "a", k + ".npz"), fps_sub=2, window_s=16)
        rows.append(metrics("A @4 fps, first 20 s", A2, lab, thr=0.25))
    thr = {"kinetics": 0.05, "xclip": 0.2, "clip": 0.2, "smolvlm": 0.3}
    for m in ("kinetics", "xclip", "clip", "smolvlm"):
        S = load_json_scores(m)
        S = {k: v for k, v in S.items() if k in lab}
        if len(S) < 5:
            continue
        for k, v in S.items():
            per_clip.setdefault(k, {"label": lab[k]})[m] = v["score"]
            per_clip[k][m + "_top"] = v.get("top")
        r = metrics(m, {k: v["score"] for k, v in S.items()}, lab, thr=thr[m])
        r["sec_median"] = float(np.median([v["seconds"] for v in S.values()]))
        rows.append(r)
    for m in ("falconsai", "nudenet"):
        S = {k: v for k, v in load_json_scores(m).items() if k in lab}
        if S:
            for k, v in S.items():
                per_clip.setdefault(k, {"label": lab[k]})[m] = v["score"]
            flagged = sorted([(round(v["score"], 3), k) for k, v in S.items() if v["score"] >= 0.5], reverse=True)
            print(f"{m}: {len(S)} clips, flagged >=0.5: {flagged}, median {np.median([v['seconds'] for v in S.values()]):.2f}s")
    json.dump({"rows": rows, "clips": per_clip}, open(os.path.join(DATA, "results.json"), "w"), indent=1, default=float)
    for r in rows:
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})


if __name__ == "__main__":
    main()
