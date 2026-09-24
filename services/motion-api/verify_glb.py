"""Measure a shipped GLB, rather than trusting the export log.

Everything here is read back out of the file the pipeline actually wrote:
non-finite values, the 18 region meshes, the sampler interpolation mode, the
keyframe rate, and the bone-length CV. Nothing is inferred from stdout.

    python verify_glb.py <file.glb> [--expect-fps 15.0]
"""
from __future__ import annotations

import argparse
import collections
import json
import struct
import sys

import numpy as np
import pygltflib

COMPONENT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_accessor(g: pygltflib.GLTF2, blob: bytes, idx: int) -> np.ndarray:
    acc = g.accessors[idx]
    bv = g.bufferViews[acc.bufferView]
    fmt = COMPONENT[acc.componentType]
    n = NCOMP[acc.type]
    itemsize = struct.calcsize("<" + fmt)
    start = (bv.byteOffset or 0) + (acc.byteOffset or 0)
    stride = bv.byteStride or (itemsize * n)
    out = np.empty((acc.count, n), dtype=np.dtype(fmt))
    for i in range(acc.count):
        off = start + i * stride
        out[i] = struct.unpack_from("<" + fmt * n, blob, off)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("--expect-fps", type=float, default=None)
    args = ap.parse_args()

    g = pygltflib.GLTF2().load(args.glb)
    blob = g.binary_blob()
    report: dict = {"file": args.glb, "bytes": len(open(args.glb, "rb").read())}

    # --- interpolation + keyframe rate --------------------------------------
    modes = collections.Counter()
    n_channels = 0
    dts: list[float] = []
    for anim in g.animations or []:
        for s in anim.samplers:
            modes[s.interpolation] += 1
        n_channels += len(anim.channels)
        for s in anim.samplers:
            t = read_accessor(g, blob, s.input).astype(np.float64).ravel()
            if len(t) > 1:
                dts.append(float(np.median(np.diff(t))))
    report["n_animations"] = len(g.animations or [])
    report["n_channels"] = n_channels
    report["interpolation"] = dict(modes)
    if dts:
        dt = float(np.median(dts))
        report["keyframe_dt_s"] = round(dt, 6)
        report["keyframe_fps"] = round(1.0 / dt, 4) if dt else None

    # --- non-finite animation values ----------------------------------------
    bad = total = 0
    for anim in g.animations or []:
        for s in anim.samplers:
            v = read_accessor(g, blob, s.output).astype(np.float64)
            total += v.size
            bad += int((~np.isfinite(v)).sum())
    report["animation_values"] = {"total": total, "non_finite": bad}

    # --- meshes: region coverage + non-finite vertices -----------------------
    region_tris: dict[str, int] = {}
    vert_total = vert_bad = 0
    for m in g.meshes or []:
        tris = 0
        for prim in m.primitives:
            pos = read_accessor(g, blob, prim.attributes.POSITION).astype(np.float64)
            vert_total += pos.size
            vert_bad += int((~np.isfinite(pos)).sum())
            if prim.indices is not None:
                tris += g.accessors[prim.indices].count // 3
        if (m.name or "").startswith("region_"):
            region_tris[m.name] = region_tris.get(m.name, 0) + tris
    report["mesh_vertex_components"] = {"total": vert_total, "non_finite": vert_bad}
    report["region_meshes"] = {
        "count": len(region_tris),
        "empty": sorted(k for k, v in region_tris.items() if v == 0),
        "triangles": dict(sorted(region_tris.items())),
    }

    # --- bone length CV over the clip ---------------------------------------
    # A bone's length is |child translation| in its parent's frame. If the
    # constraint held, that is constant over time.
    if g.skins:
        joints = g.skins[0].joints
        local = {n: i for i, n in enumerate(joints)}
        parent = {}
        for ci, node in enumerate(g.nodes):
            for ch in node.children or []:
                if ch in local and ci in local:
                    parent[local[ch]] = local[ci]
        # animated translations per node
        trans: dict[int, np.ndarray] = {}
        scale_nodes = []
        for anim in g.animations or []:
            for ch in anim.channels:
                node = ch.target.node
                if node not in local:
                    continue
                s = anim.samplers[ch.sampler]
                if ch.target.path == "translation":
                    trans[local[node]] = read_accessor(g, blob, s.output).astype(np.float64)
                elif ch.target.path == "scale":
                    scale_nodes.append(g.nodes[node].name or str(node))
        cvs = []
        for j, v in trans.items():
            if j not in parent:
                continue
            L = np.linalg.norm(v, axis=1)
            if L.mean() > 1e-9:
                cvs.append(100.0 * L.std() / L.mean())
        if cvs:
            a = np.array(cvs)
            report["bone_length_cv_pct"] = {
                "n_bones": len(a), "mean": round(float(a.mean()), 4),
                "median": round(float(np.median(a)), 4), "max": round(float(a.max()), 4),
                "under_0.01pct": int((a < 0.01).sum()),
            }
        report["animated_scale_nodes"] = sorted(set(scale_nodes))

    print(json.dumps(report, indent=2))

    ok = (report["animation_values"]["non_finite"] == 0
          and report["mesh_vertex_components"]["non_finite"] == 0
          and report["region_meshes"]["count"] == 18
          and not report["region_meshes"]["empty"]
          and list(report["interpolation"]) == ["LINEAR"])
    if args.expect_fps and report.get("keyframe_fps"):
        ok = ok and abs(report["keyframe_fps"] - args.expect_fps) < 0.01
    print("VERDICT:", "PASS" if ok else "FAIL", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
