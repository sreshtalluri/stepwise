"""One-off: give every stored lesson the standard body surface.

    python3 restandardize_bodies.py                 # dry run: what it would do, every GLB checked in memory
    python3 restandardize_bodies.py --apply         # do it
    python3 restandardize_bodies.py --apply --only <clip_id> [--only ...]
    python3 restandardize_bodies.py --copy-test <clip_id>   # the whole path on a throwaway copy, then deleted

docs/legal/body-shape-decision.md, option (b): from 2026-09-18 (`8f4ae48`) to
2026-09-25 export baked each dancer's estimated MHR shape into the GLB's rest
mesh. The export no longer does; this brings the lessons already stored into
line. Nothing else about a lesson changes: the skeleton (the dancer's limb
lengths), the animation, the counts the owner set and every other field of the
MotionResult stay exactly as served.

Two routes, chosen per lesson:

  * **npz gone** (the sweeper reaps it once the MotionResult is materialised;
    true of every lesson with owner-set counts) -> **swap the surface in the
    stored GLB.** Each GLB's POSITION and NORMAL accessors -- the region
    meshes and the orphaned pre-split mesh the region split leaves in the
    binary chunk -- are overwritten in place with the standard body's, from a
    reference GLB (`--reference`, the lod3 body exported by the same
    pymomentum + region split). Every other byte is kept, which is what makes
    this safe: animation, skin, inverse bind matrices, node TRS, joints,
    weights and indices are checked byte-identical, and the swap refuses any
    GLB whose topology does not match the reference. Then the MotionResult
    gets the new versioned GLB names and `shape_params: default_assumed`,
    and is republished through `storage.publish_motion_result`, the path the
    owner's count-1 edit uses. `proposed_counts` is not touched.
  * **npz present** -> the normal CPU export (`export_clip_gltf`, from THIS
    checkout, in an ephemeral Modal app: no GPU). A re-export rebuilds
    `proposed_counts` from the detector, so a stored MotionResult's
    `proposed_counts` is put back afterwards and republished the same way.

Superseded GLB and MotionResult versions are pruned after the grace period,
with `modal_app._prune_old_versions`. Lessons with a tombstone (removed, and
so also quarantined ones) are skipped, and the quarantine Volume is never
opened. Needs a Modal token; R2 credentials come from ~/.stepwise-secrets/r2.env.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
sys.path.insert(0, str(HERE.parents[1] / "packages" / "motion-contract" / "python"))

SURFACE = ("POSITION", "NORMAL")
_COMP = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


class Mismatch(ValueError):
    """This GLB is not the reference body's topology; the swap refuses it."""


# --- the swap: pure bytes in, bytes out -------------------------------------

def _load(data: bytes):
    import pygltflib
    return pygltflib.GLTF2.load_from_bytes(data)


def _span(g, i: int) -> tuple[int, int]:
    a = g.accessors[i]
    bv = g.bufferViews[a.bufferView]
    size = _COMP[a.componentType] * _NCOMP[a.type]
    if bv.byteStride not in (None, size):
        raise Mismatch(f"accessor {i} is interleaved (stride {bv.byteStride}); not handled")
    return (bv.byteOffset or 0) + (a.byteOffset or 0), a.count * size


def _mesh_accessors(g) -> dict:
    """(mesh name, primitive, attribute) -> accessor index, for every mesh --
    including the pre-split one the region split leaves unreferenced but still
    in the binary chunk. Keyed by name because the accessor numbering shifts
    with the number of animation channels."""
    out = {}
    for mi, m in enumerate(g.meshes):
        for pi, p in enumerate(m.primitives):
            for attr in (*SURFACE, "JOINTS_0", "WEIGHTS_0"):
                if getattr(p.attributes, attr) is not None:
                    out[(m.name or f"#{mi}", pi, attr)] = getattr(p.attributes, attr)
            out[(m.name or f"#{mi}", pi, "indices")] = p.indices
    return out


def standardize_glb(old: bytes, ref: bytes) -> bytes:
    """`old` with its rest-mesh surface replaced by `ref`'s. Raises Mismatch
    unless every non-surface mesh accessor and the inverse bind matrices are
    byte-identical between the two."""
    go, gr = _load(old), _load(ref)
    ao, ar = _mesh_accessors(go), _mesh_accessors(gr)
    if set(ao) != set(ar):
        raise Mismatch(f"mesh layout differs: {sorted(set(ao) ^ set(ar))[:4]}")
    blob = bytearray(go.binary_blob())
    rblob = gr.binary_blob()

    def same(i, j):
        (oo, on), (ro, rn) = _span(go, i), _span(gr, j)
        return on == rn and blob[oo:oo + on] == rblob[ro:ro + rn]

    ibm_o, ibm_r = go.skins[0].inverseBindMatrices, gr.skins[0].inverseBindMatrices
    if len(go.skins) != 1 or not same(ibm_o, ibm_r):
        raise Mismatch("inverse bind matrices differ: not the reference skeleton")
    for key, i in ao.items():
        j = ar[key]
        a, b = go.accessors[i], gr.accessors[j]
        if (a.componentType, a.type, a.count) != (b.componentType, b.type, b.count):
            raise Mismatch(f"{key}: {a.type}x{a.count} vs {b.type}x{b.count}")
        if key[2] in SURFACE:
            (oo, n), (ro, _) = _span(go, i), _span(gr, j)
            blob[oo:oo + n] = rblob[ro:ro + n]
            a.min, a.max = b.min, b.max
        elif not same(i, j):
            raise Mismatch(f"{key} differs from the reference: different topology or skinning")
    go.set_binary_blob(bytes(blob))
    out = go.save_to_bytes()
    return b"".join(out) if isinstance(out, list) else out


def verify_glb(old: bytes, new: bytes, ref: bytes) -> dict:
    """Everything the swap promises, re-read from the bytes that will ship."""
    import modal_app
    go, gn, gr = _load(old), _load(new), _load(ref)
    bo, bn, br = go.binary_blob(), gn.binary_blob(), gr.binary_blob()
    assert len(bo) == len(bn), "binary chunk changed size"
    mask = np.zeros(len(bo), dtype=bool)
    an, ar = _mesh_accessors(gn), _mesh_accessors(gr)
    for key, i in an.items():
        if key[2] in SURFACE:
            s, n = _span(gn, i)
            mask[s:s + n] = True
            rs, rn = _span(gr, ar[key])
            assert bn[s:s + n] == br[rs:rs + rn], f"{key} is not the standard surface"
    diff = np.frombuffer(bo, np.uint8) != np.frombuffer(bn, np.uint8)
    assert not (diff & ~mask).any(), "a byte outside the surface accessors changed"
    # Skeleton and motion: node TRS, skin, animation all as before.
    assert [n.to_dict() for n in gn.nodes] == [n.to_dict() for n in go.nodes]
    assert [s.to_dict() for s in gn.skins] == [s.to_dict() for s in go.skins]
    assert [a.to_dict() for a in gn.animations] == [a.to_dict() for a in go.animations]
    assert [m.name for m in gn.meshes] == [m.name for m in go.meshes]
    # The export's own last check: every sampler LINEAR, the binary chunk
    # untouched by the rewrite, no non-finite float anywhere in it. Raises if not.
    with tempfile.NamedTemporaryFile(suffix=".glb") as f:
        f.write(new)
        f.flush()
        assert modal_app._rewrite_interpolation_linear(f.name)["n_rewritten"] == 0
    pos_key = next(k for k in an if k[2] == "POSITION" and not str(k[0]).startswith("region_"))
    s, n = _span(go, _mesh_accessors(go)[pos_key])
    p_old = np.frombuffer(bo, np.float32, n // 4, s).reshape(-1, 3)
    p_new = np.frombuffer(bn, np.float32, n // 4, s).reshape(-1, 3)
    move = np.linalg.norm(p_old.astype(np.float64) - p_new, axis=1) * 100.0  # metres -> cm
    return {"surface_moved_cm_mean": round(float(move.mean()), 3),
            "surface_moved_cm_max": round(float(move.max()), 3),
            "zero_norm_rotations": zero_rotations(new)}


def zero_rotations(data: bytes) -> int:
    g = _load(data)
    blob = g.binary_blob()
    n = 0
    for anim in g.animations:
        for ch in anim.channels:
            if ch.target.path == "rotation":
                s, size = _span(g, anim.samplers[ch.sampler].output)
                q = np.frombuffer(blob, np.float32, size // 4, s).reshape(-1, 4)
                n += int((np.linalg.norm(q, axis=1) < 1e-6).sum())
    return n


def reference_glb(single_mesh_standard_glb: str) -> bytes:
    """The standard body, region-split exactly as export does it, from a GLB
    pymomentum wrote with lod3's own (unshaped) character."""
    from region_mask import split_glb_by_region
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "ref.glb")
        split_glb_by_region(single_mesh_standard_glb, out)
        return Path(out).read_bytes()


# --- the stores -------------------------------------------------------------

def _read(vol, path: str) -> bytes | None:
    buf = io.BytesIO()
    try:
        vol.read_file_into_fileobj(path, buf)
    except FileNotFoundError:
        return None
    return buf.getvalue()


def _write(vol, files: dict) -> None:
    with tempfile.TemporaryDirectory() as d:
        with vol.batch_upload(force=True) as batch:
            for i, (path, data) in enumerate(files.items()):
                local = os.path.join(d, str(i))
                Path(local).write_bytes(data)
                batch.put_file(local, path)


def stored_doc(results, clip_id: str) -> dict | None:
    """The MotionResult as served: R2's latest copy first, then the Volume's
    (api.py `_stored_doc`)."""
    import storage
    raw = None
    if storage.enabled():
        try:
            raw = storage.client().get_object(Bucket=storage.bucket(),
                                              Key=storage.motion_result_key(clip_id))["Body"].read()
        except Exception:  # noqa: BLE001
            raw = None
    raw = raw or _read(results, f"/{clip_id}.motion-result.json.gz")
    return json.loads(gzip.decompress(raw)) if raw else None


def plan(results) -> list[dict]:
    """Every lesson with an export manifest, what route it takes, or why not."""
    import retention
    names = [e.path.lstrip("/") for e in results.listdir("/")]
    have = set(names)
    lessons = []
    for m in sorted(n for n in names if n.endswith(".export-manifest.json")):
        clip_id = m[: -len(".export-manifest.json")]
        row = {"clip_id": clip_id}
        if f"{clip_id}.removed.json" in have or retention.is_removed(results, clip_id):
            row["route"] = "skip: removed" + (" (quarantined)" if retention.is_quarantined(results, clip_id) else "")
        elif f"{clip_id}.npz" in have:
            # An owner eval clip (no job-meta: never uploaded through the API)
            # whose surface was never shaped is left alone: re-exporting it
            # would materialise a MotionResult and let the sweeper reap the npz
            # the GATE measurements rerun from.
            shaped = "shape_params" in json.loads(_read(results, f"/{m}"))
            row["route"] = ("reexport" if shaped or f"job_{clip_id}.job-meta.json" in have
                            else "skip: eval clip, surface already standard, npz kept")
        elif f"{clip_id}.motion-result.json.gz" in have:
            row["route"] = "swap"
        else:
            row["route"] = "skip: no npz and no stored MotionResult"
        lessons.append(row)
    return lessons


def swap_lesson(results, clip_id: str, ref: bytes, apply: bool) -> dict:
    """The npz-gone route. Returns what it did (or would do) and the checks."""
    import retention
    import storage
    from motion_contract import validate_motion_result

    doc = stored_doc(results, clip_id)
    manifest = json.loads(_read(results, f"/{clip_id}.export-manifest.json"))
    new_doc = copy.deepcopy(doc)
    new_glbs, checks = {}, {}
    for p in new_doc["persons"]:
        old_name = p["animation"]["glb_asset_id"]
        old = _read(results, f"/{old_name}")
        if old is None and storage.enabled():
            old = storage.client().get_object(Bucket=storage.bucket(), Key=storage.glb_key(old_name))["Body"].read()
        new = standardize_glb(old, ref)
        checks[old_name] = verify_glb(old, new, ref)
        name = storage.versioned_name(f"{clip_id}_track{p['track_id']}.glb", new)
        new_glbs[name] = new
        p["animation"]["glb_asset_id"] = name
        p["shape_params"] = {"source": "default_assumed"}
        manifest["glb_paths"][str(p["track_id"])] = name
    manifest.pop("shape_params", None)
    check = validate_motion_result(new_doc)
    assert check.valid, check.errors[:5]
    assert new_doc.get("proposed_counts") == doc.get("proposed_counts")
    out = {"clip_id": clip_id, "job_id": doc["job_id"], "glbs": checks, "new_glbs": sorted(new_glbs)}
    if not apply:
        return out

    retention.ensure_not_removed(results, clip_id)
    gz = gzip.compress(json.dumps(new_doc, separators=(",", ":")).encode(), 6)
    _write(results, {**{f"/{n}": b for n, b in new_glbs.items()},
                     f"/{clip_id}.export-manifest.json": json.dumps(manifest).encode(),
                     f"/{clip_id}.motion-result.json.gz": gz})
    written = []
    if storage.enabled():
        for n, b in new_glbs.items():
            written.append(storage.put_bytes(storage.glb_key(n), b, "model/gltf-binary"))
        written += storage.publish_motion_result(clip_id, gz, new_doc["job_id"])  # latest pointer last
    if retention.is_removed(results, clip_id):  # a takedown landed meanwhile: take it all back
        for n in [*new_glbs, f"{clip_id}.motion-result.json.gz"]:
            retention.remove_if_present(results, f"/{n}")
        for k in written:
            storage.delete(k)
        raise retention.Removed(clip_id)
    out.update(glb_names=sorted(new_glbs), r2_published=written, motion_result_materialised=True)
    return out


def reexport_lesson(results, clip_id: str, job_id: str) -> dict:
    """The npz-present route: this checkout's export, CPU only, with any stored
    `proposed_counts` (owner picks included) put back afterwards."""
    import modal_app
    import storage
    from motion_contract import validate_motion_result

    before = stored_doc(results, clip_id)
    with modal_app.app.run():
        out = modal_app.export_clip_gltf.remote(clip_id, job_id)
    doc = stored_doc(results, clip_id)
    assert doc is not None, f"{clip_id}: export did not materialise a MotionResult"
    if before and before.get("proposed_counts") and doc.get("proposed_counts") != before["proposed_counts"]:
        doc["proposed_counts"] = before["proposed_counts"]
        assert validate_motion_result(doc).valid
        gz = gzip.compress(json.dumps(doc, separators=(",", ":")).encode(), 6)
        _write(results, {f"/{clip_id}.motion-result.json.gz": gz})
        published = storage.publish_motion_result(clip_id, gz, doc["job_id"]) if storage.enabled() else []
        out = dict(out, r2_published=published, counts_restored=True)
    return out


def copy_lesson(results, src: str) -> str:
    """A throwaway copy of lesson `src` under a new clip id, on the Volume only
    (as a lesson whose R2 publish failed would be: api.py falls back to the
    Volume). Same bytes, ids rewritten. Returns the new clip id."""
    tmp = f"stdtest-{src[:8]}"
    names = [e.path.lstrip("/") for e in results.listdir("/")
             if e.path.lstrip("/").startswith((src, f"job_{src}"))]
    files = {}
    for n in names:
        if n.endswith((".npz", ".glb", ".count-one-labels.json", ".last-access.json")):
            continue
        data = _read(results, f"/{n}")
        if n.endswith(".gz"):
            data = gzip.compress(gzip.decompress(data).replace(src.encode(), tmp.encode()), 6)
        elif n.endswith(".json"):
            data = data.replace(src.encode(), tmp.encode())
        files["/" + n.replace(src, tmp)] = data
    doc = json.loads(gzip.decompress(files[f"/{tmp}.motion-result.json.gz"])) \
        if f"/{tmp}.motion-result.json.gz" in files else None
    for p in (doc or {}).get("persons", []):  # the GLBs the copied document names, same bytes
        name = p["animation"]["glb_asset_id"]
        files[f"/{name}"] = _read(results, "/" + name.replace(tmp, src))
    _write(results, files)
    if f"{src}.npz" in names:
        results.copy_files([f"/{src}.npz"], f"/{tmp}.npz")
    return tmp


def delete_lesson_bytes(results, clip_id: str) -> list[str]:
    """Every Volume file and R2 key of a throwaway copy. Only ever called on
    ids copy_lesson made."""
    import storage
    assert clip_id.startswith("stdtest-")
    gone = [e.path.lstrip("/") for e in results.listdir("/")
            if e.path.lstrip("/").startswith((clip_id, f"job_{clip_id}"))]
    for n in gone:
        results.remove_file(f"/{n}")
    if storage.enabled():
        for k in storage.clip_keys(clip_id):
            storage.delete(k)
            gone.append(k)
    return gone


def prune(clip_id: str, out: dict) -> None:
    import modal_app
    modal_app.OLD_VERSION_GRACE_S = 0  # the caller already waited it out once for every lesson
    modal_app._prune_old_versions(clip_id, out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--copy-test", metavar="CLIP_ID",
                    help="copy this lesson to a throwaway id and run the whole path on the copy (implies --apply)")
    ap.add_argument("--delete-copy", metavar="CLIP_ID", help="delete a throwaway copy (stdtest-*) everywhere")
    ap.add_argument("--reference", default=None,
                    help="a single-mesh GLB exported from lod3's unshaped character "
                         "(default: the stored GLB of the first lesson whose manifest never had a shape vector)")
    args = ap.parse_args()

    from audit_removed import _load_env
    _load_env("r2.env")
    import modal
    import storage
    results = modal.Volume.from_name("stepwise-results")

    if args.delete_copy:
        print("deleted", delete_lesson_bytes(results, args.delete_copy))
        return 0
    if args.copy_test:
        tmp = copy_lesson(results, args.copy_test)
        print(f"copied {args.copy_test} -> {tmp}")
        args.apply, args.only = True, [tmp]
    rows = plan(results)
    if args.only:
        rows = [r for r in rows if r["clip_id"] in args.only]
    ref_src = args.reference
    if ref_src is None:
        ref_src = os.path.join(tempfile.mkdtemp(), "standard.glb")
        Path(ref_src).write_bytes(_read(results, "/" + _standard_source(results)))
    ref = reference_glb(ref_src)
    print(f"R2 {'on' if storage.enabled() else 'OFF'}; reference surface from {ref_src}; "
          f"{'APPLYING' if args.apply else 'dry run'}\n")

    done = []
    for r in rows:
        clip_id, route = r["clip_id"], r["route"]
        if route.startswith("skip"):
            print(f"{clip_id}  {route}")
            continue
        if route == "swap":
            out = swap_lesson(results, clip_id, ref, args.apply)
            print(f"{clip_id}  swap  {out['job_id']}")
            for name, c in out["glbs"].items():
                print(f"    {name}: surface moved mean {c['surface_moved_cm_mean']} cm, max "
                      f"{c['surface_moved_cm_max']} cm; zero-norm rotations {c['zero_norm_rotations']}")
            print(f"    -> {', '.join(out['new_glbs'])}")
        else:
            print(f"{clip_id}  reexport (CPU export_clip_gltf, stored proposed_counts kept)")
            if not args.apply:
                continue
            out = reexport_lesson(results, clip_id, f"job_{clip_id}")
            print(f"    -> {out.get('glb_names')}")
        if args.apply:
            done.append((clip_id, out))

    if done:
        import modal_app
        print(f"\nwaiting {modal_app.OLD_VERSION_GRACE_S}s before pruning superseded versions...")
        time.sleep(modal_app.OLD_VERSION_GRACE_S)
        for clip_id, out in done:
            prune(clip_id, out)
    return 0


def _standard_source(results) -> str:
    """A stored single-mesh GLB from a manifest that never carried a shape
    vector: pymomentum's export of lod3's own character."""
    for e in results.listdir("/"):
        n = e.path.lstrip("/")
        if n.endswith(".export-manifest.json"):
            m = json.loads(_read(results, f"/{n}"))
            if "shape_params" not in m and m.get("glb_paths"):
                name = next(iter(m["glb_paths"].values()))
                data = _read(results, f"/{name}")
                if data and len(_load(data).meshes) == 1:
                    return name
    raise SystemExit("no unshaped single-mesh GLB to take the standard surface from; pass --reference")


if __name__ == "__main__":
    sys.exit(main())
