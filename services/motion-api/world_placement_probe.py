# Measurement tool, not a pipeline stage -- see docs/research/world-placement.md.
"""Where is the dancer actually standing?  A probe, not a solve.

`grounding.py` fits a floor in the character-local frame, which has no depth in
it at all, and honestly returns `none` on every real clip.  OPEN-DECISIONS E6
asks whether a per-frame global placement is obtainable.  This measures it.

The method, in one line: take the reconstruction's metric body, make it rigid
with `skeleton_constraints.enforce_bone_lengths`, and solve a 3-DoF translation
per frame so it reprojects onto the DETECTOR's COCO-17 keypoints under the
clip's real pinhole intrinsics.  Then check the placement against evidence it
was never given -- do the foot contacts land on one flat floor, does a foot the
image says is stationary stay still in world space.

Why the detector's keypoints and not the model's own: the model's 2D keypoints
are its own fit by construction (reprojection error 0.00 px), so fitting to
them measures nothing.  RTMO's keypoints are an independent observation of the
same person.

Run:  python world_placement_probe.py <clip.npz> [more.npz ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "vendor/fast-sam-3d-body/tools"))

import grounding as g  # noqa: E402
import skeleton_constraints as sc  # noqa: E402

_JOINTS = json.loads((_HERE / "mhr_joint_hierarchy.json").read_text())["joints"]
JOINT_NAMES = [j["name"] for j in _JOINTS]
NIDX = {n: i for i, n in enumerate(JOINT_NAMES)}

# Detector COCO-17 index -> MHR joint, established by 2D nearest-neighbour vote
# over the first 120 frames of solo-01 (>=30/120 votes each) and checked to be
# anatomically sensible.  The face keypoints are deliberately excluded: COCO's
# ears vote for the MHR eyes, which is a real mismatch, and the head is the
# worst-conditioned part of the body for depth anyway.
COCO_TO_MHR = {c: NIDX[n] for c, n in {
    5: "l_uparm", 6: "r_uparm", 7: "l_lowarm", 8: "r_lowarm",
    9: "l_wrist_twist", 10: "r_wrist_twist", 11: "l_upleg", 12: "r_upleg",
    13: "l_lowleg", 14: "r_lowleg", 15: "l_foot", 16: "r_foot",
}.items()}
COCO_ANKLES = (15, 16)

KP_SCORE_MIN = 0.5          # for the PnP correspondences
MIN_CORRESPONDENCES = 8     # 3 unknowns; 8 points is ~5x redundancy
CONTACT_MAX_SPEED_MPS = 0.30   # same number grounding.py uses, applied in the image
FLOOR_TOL_M = 0.05
SMOOTH_WIN = 5              # frames; 0.33 s at 15 fps


def _pnp(X, uv, w, t0, focal, cx, cy, iters=40):
    """3-DoF Gauss-Newton translation fit under a pinhole camera.

    Rotation and body shape are already baked into `X`, so this is the whole
    remaining unknown.  Unlike the weak-perspective fit `pred_cam_t` comes
    from, perspective genuinely constrains depth -- but only through apparent
    size, which is why the rigid skeleton matters (see the module docstring of
    skeleton_constraints).
    """
    t = np.asarray(t0, dtype=np.float64).copy()
    for _ in range(iters):
        P = X + t
        Z = P[:, 2]
        if np.any(Z <= 0.05):
            return None, np.inf
        proj = np.column_stack([focal * P[:, 0] / Z + cx, focal * P[:, 1] / Z + cy])
        resid = (proj - uv) * w[:, None]
        J = np.zeros((len(uv) * 2, 3))
        J[0::2, 0] = focal / Z * w
        J[0::2, 2] = -focal * P[:, 0] / Z ** 2 * w
        J[1::2, 1] = focal / Z * w
        J[1::2, 2] = -focal * P[:, 1] / Z ** 2 * w
        step = np.linalg.lstsq(J, -resid.ravel(), rcond=None)[0]
        t = t + step
        if np.linalg.norm(step) < 1e-7:
            break
    P = X + t
    proj = np.column_stack([focal * P[:, 0] / P[:, 2] + cx, focal * P[:, 1] / P[:, 2] + cy])
    return t, float(np.median(np.linalg.norm(proj - uv, axis=1)))


def fit_plane(points, weights, tol_m=FLOOR_TOL_M, iterations=4000, seed=0):
    """Weighted RANSAC plane + weighted least-squares refit, NO tilt prior.

    grounding.fit_floor_plane assumes the floor is near +Y because it works in
    the camera-ALIGNED character-local frame.  Here the frame is the camera's
    own, the phone was lying nearly on the ground pointing up, and the floor
    normal is ~13-18 degrees off +Y.  Same estimator, prior removed.
    """
    points = np.asarray(points, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    if len(points) < 3:
        return None
    rng = np.random.default_rng(seed)
    probs = weights / weights.sum()
    best_score, normal, origin = -1.0, None, None
    for _ in range(iterations):
        trio = rng.choice(len(points), 3, replace=False, p=probs)
        a, b, c = points[trio]
        n = np.cross(b - a, c - a)
        nn = np.linalg.norm(n)
        if nn < 1e-9:
            continue
        n = n / nn
        score = weights[np.abs(((points - a) * n).sum(1)) <= tol_m].sum()
        if score > best_score:
            best_score, normal, origin = float(score), n, a
    if normal is None:
        return None
    for _ in range(3):
        inl = np.abs(((points - origin) * normal).sum(1)) <= tol_m
        if inl.sum() < 3:
            return None
        w = weights[inl]
        origin = (w[:, None] * points[inl]).sum(0) / w.sum()
        _, _, vh = np.linalg.svd((points[inl] - origin) * np.sqrt(w)[:, None], full_matrices=False)
        normal = vh[-1]
        if normal[1] < 0:
            normal = -normal
    dist = ((points - origin) * normal).sum(1)
    inl = np.abs(dist) <= tol_m
    rms = float(np.sqrt((weights[inl] * dist[inl] ** 2).sum() / weights[inl].sum()))
    return normal, origin, inl, rms, dist


def image_contact_weights(ankle_uv, visible, depth_m, times_s, focal,
                          max_speed_mps=CONTACT_MAX_SPEED_MPS):
    """Contact weight from the IMAGE: a static camera means a planted foot is
    a stationary pixel, whatever the dancer's depth.

    Converted to m/s with the frame's own depth so one threshold works at 3 m
    and at 10 m.  Blind spot, on purpose: a SLIDING foot is in contact and
    moving, so it scores ~0.  That is a false negative (decline to anchor), not
    a false positive (plant a foot that was in the air), which is the right way
    round for DESIGN.md section 7h.  Measured on solo-01: 70% of samples that
    are geometrically on the floor move faster than this threshold, so this cue
    finds well under half of the real contacts.
    """
    n = len(times_s)
    speed = np.full((n, 2), np.inf)
    for foot in range(2):
        idx = np.flatnonzero(visible[:, foot] & np.isfinite(depth_m))
        if idx.size < 2:
            continue
        du = np.gradient(ankle_uv[idx, foot, 0], times_s[idx])
        dv = np.gradient(ankle_uv[idx, foot, 1], times_s[idx])
        speed[idx, foot] = np.hypot(du, dv) * depth_m[idx] / focal
    return np.where(visible, np.clip(1.0 - speed / max_speed_mps, 0.0, 1.0), 0.0), speed


def _median_filter(t, win=SMOOTH_WIN):
    out = t.copy()
    half = win // 2
    for k in range(len(t)):
        seg = t[max(0, k - half):k + half + 1]
        seg = seg[np.isfinite(seg).all(1)]
        if seg.size:
            out[k] = np.median(seg, axis=0)
    return out


def place_track(npz_data, track_id, *, rigid=True, smooth=True):
    """Per-frame world placement for one dancer.  Returns everything measured."""
    per_frame, raw_det = npz_data["per_frame"], npz_data["raw_detections"]
    times_all = np.asarray(npz_data["sample_times_s"], dtype=np.float64)
    width = int(npz_data["frame_width"]) if "frame_width" in npz_data else 0
    height = int(npz_data["frame_height"]) if "frame_height" in npz_data else 0
    if not width or not height:
        raise ValueError("npz has no frame_width/frame_height -- re-run the clip")
    cx, cy = width / 2.0, height / 2.0

    rows = []
    for i in range(len(per_frame)):
        frame = per_frame[i]
        if not (isinstance(frame, dict) and track_id in frame):
            continue
        ids = list(np.asarray(raw_det[i]["track_ids"]))
        if track_id not in ids:
            continue
        rows.append((i, np.asarray(per_frame[i][track_id]["pred_joint_coords"], dtype=np.float64),
                     np.asarray(per_frame[i][track_id]["pred_cam_t"], dtype=np.float64),
                     float(per_frame[i][track_id]["focal_length"]),
                     np.asarray(raw_det[i]["keypoints"])[ids.index(track_id)].astype(np.float64)))
    if len(rows) < 25:
        return None

    idx = np.array([r[0] for r in rows])
    times = times_all[idx]
    joints = np.stack([r[1] for r in rows])
    cam_t = np.stack([r[2] for r in rows])
    focal = float(np.median([r[3] for r in rows]))
    kps = np.stack([r[4] for r in rows])
    if rigid:
        joints = sc.enforce_bone_lengths(joints).joints

    trans = np.full((len(rows), 3), np.nan)
    errs = np.full(len(rows), np.nan)
    for k in range(len(rows)):
        cs = [c for c in COCO_TO_MHR if kps[k, c, 2] >= KP_SCORE_MIN]
        if len(cs) < MIN_CORRESPONDENCES:
            continue
        t, e = _pnp(joints[k][[COCO_TO_MHR[c] for c in cs]], kps[k, cs, :2], kps[k, cs, 2],
                    cam_t[k], focal, cx, cy)
        if t is not None:
            trans[k], errs[k] = t, e
    if smooth:
        trans = _median_filter(trans)

    foot_idx = {s: [NIDX[n] for n in g.FOOT_JOINTS[s]] for s in g.FOOT_ORDER}
    feet = np.full((len(rows), 2, 3), np.nan)
    for k in range(len(rows)):
        if not np.isfinite(trans[k]).all():
            continue
        placed = joints[k] + trans[k]
        for s, side in enumerate(g.FOOT_ORDER):
            grp = placed[foot_idx[side]]
            feet[k, s] = grp[np.argmax(grp[:, 1])]   # camera +y points DOWN

    ankle_uv = np.stack([kps[:, COCO_ANKLES[0], :2], kps[:, COCO_ANKLES[1], :2]], axis=1)
    score = np.stack([kps[:, COCO_ANKLES[0], 2], kps[:, COCO_ANKLES[1], 2]], axis=1)
    visible = ((score >= g.ANKLE_SCORE_MIN)
               & (ankle_uv[..., 0] >= 0) & (ankle_uv[..., 0] < width)
               & (ankle_uv[..., 1] >= 0) & (ankle_uv[..., 1] < height))
    weights, speed = image_contact_weights(ankle_uv, visible, trans[:, 2], times, focal)

    return dict(times=times, joints=joints, trans=trans, reproj_px=errs, feet=feet,
                contact_w=weights, foot_speed=speed, visible=visible, focal=focal,
                width=width, height=height, cam_t=cam_t)


def probe(path):
    data = np.load(path, allow_pickle=True)
    name = Path(path).stem
    tracks = data["confident_track_ids"].tolist()
    print(f"\n=== {name}: tracks {tracks} ===")
    pooled_pts, pooled_w, per_track = [], [], []
    for tk in tracks:
        out = place_track(data, tk)
        if out is None:
            print(f"  track {tk}: fewer than 25 frames, skipped")
            continue
        good = np.isfinite(out["feet"]).all(2) & (out["contact_w"] > 0.05)
        if good.sum() < 12:
            print(f"  track {tk}: only {int(good.sum())} contact candidates, no floor")
            continue
        pts, w = out["feet"][good], out["contact_w"][good]
        fit = fit_plane(pts, w)
        normal, origin, inl, rms, dist = fit
        cam_h = float(abs(((np.zeros(3) - origin) * normal).sum()))
        print(f"  track {tk:2d}: {len(out['times']):3d} frames, reproj {np.nanmedian(out['reproj_px']):5.2f} px | "
              f"{int(good.sum()):3d} contacts, {int(inl.sum()):3d} on one plane ({100*inl.sum()/good.sum():3.0f}%), "
              f"RMS {100*rms:4.2f} cm | depth {np.nanmin(out['trans'][:,2]):4.1f}..{np.nanmax(out['trans'][:,2]):5.1f} m | "
              f"camera {cam_h:.2f} m up")
        pooled_pts.append(pts)
        pooled_w.append(w)
        per_track.append((tk, cam_h))
    if len(per_track) > 1:
        pts = np.concatenate(pooled_pts)
        w = np.concatenate(pooled_w)
        normal, origin, inl, rms, dist = fit_plane(pts, w)
        heights = np.array([h for _, h in per_track])
        print(f"  POOLED {len(per_track)} dancers: {len(pts)} contacts, {int(inl.sum())} on one plane "
              f"({100*inl.sum()/len(pts):.0f}%), RMS {100*rms:.2f} cm")
        print(f"  dancers disagree about the floor height by {100*np.ptp(heights):.0f} cm "
              f"(nothing in the pipeline makes them agree)")


def _self_check():
    """Synthetic scene: a known camera, a known floor, a known rigid body.

    Fails if the solver stops recovering translation, or if fit_plane stops
    finding a floor it is handed cleanly.
    """
    rng = np.random.default_rng(0)
    focal, cx, cy = 1174.88, 288.0, 512.0
    X = rng.normal(0, 0.4, (12, 3))
    for true_t in ([0.2, -0.9, 3.0], [-0.4, -0.8, 9.0]):
        true_t = np.array(true_t)
        P = X + true_t
        uv = np.column_stack([focal * P[:, 0] / P[:, 2] + cx, focal * P[:, 1] / P[:, 2] + cy])
        t, err = _pnp(X, uv, np.ones(len(X)), np.array([0.0, 0.0, 5.0]), focal, cx, cy)
        assert np.allclose(t, true_t, atol=1e-4), (t, true_t)
        assert err < 1e-3, err

    n_true = np.array([0.02, 0.975, -0.22])
    n_true /= np.linalg.norm(n_true)
    o_true = np.array([0.0, 0.15, 0.0])
    pts = rng.normal(0, 2.0, (200, 3))
    pts -= np.outer(((pts - o_true) @ n_true), n_true)          # project onto the plane
    pts += rng.normal(0, 0.005, pts.shape)                      # 5 mm of noise
    pts[:20] += np.outer(rng.uniform(0.3, 0.8, 20), n_true)     # 10% feet in the air
    normal, origin, inl, rms, _ = fit_plane(pts, np.ones(len(pts)))
    assert abs(abs(normal @ n_true) - 1.0) < 1e-2, normal
    assert rms < 0.01, rms
    assert inl.sum() >= 170, inl.sum()

    # the image contact cue: a stationary ankle scores 1, a fast one scores 0
    times = np.arange(10) * (1 / 15)
    uv_still = np.tile([[100.0, 800.0], [120.0, 800.0]], (10, 1, 1))
    uv_fast = uv_still + np.linspace(0, 200, 10)[:, None, None]
    vis = np.ones((10, 2), bool)
    depth = np.full(10, 4.0)
    w_still, _ = image_contact_weights(uv_still, vis, depth, times, focal)
    w_fast, _ = image_contact_weights(uv_fast, vis, depth, times, focal)
    assert np.allclose(w_still, 1.0), w_still
    assert np.allclose(w_fast, 0.0), w_fast
    print("self-check OK")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        _self_check()
    else:
        _self_check()
        for p in args:
            probe(p)
