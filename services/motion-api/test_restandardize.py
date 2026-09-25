"""restandardize_bodies.standardize_glb: the surface swap that re-exports a
stored lesson whose npz is gone. It must replace the rest-mesh surface and
nothing else, and refuse a GLB that is not the reference body's topology."""
import sys
from pathlib import Path

import numpy as np
import pygltflib
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))

from modal_app import _rewrite_interpolation_linear  # noqa: E402
from region_mask import split_glb_by_region  # noqa: E402
from restandardize_bodies import Mismatch, standardize_glb, verify_glb  # noqa: E402
from test_region_mask import _build_synthetic_skinned_glb  # noqa: E402

JOINTS = {"pelvis": 0, "spine2": 1, "neck": 2, "head": 3, "left_shoulder": 4,
          **{k: 100 + i for i, k in enumerate(
              ["left_collar", "right_collar", "right_shoulder", "left_elbow", "right_elbow", "left_wrist",
               "right_wrist", "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"])}}


def _exported(tmp_path, name, nudge=None, index_edit=False) -> bytes:
    """The synthetic body through the export's two GLB passes, optionally with
    its rest surface moved (a 'shaped' export) or its triangles changed."""
    raw = tmp_path / f"{name}.raw.glb"
    _build_synthetic_skinned_glb(str(raw), with_animation=True)
    g = pygltflib.GLTF2().load(str(raw))
    blob = bytearray(g.binary_blob())
    prim = g.meshes[0].primitives[0]
    if nudge is not None:
        a = g.accessors[prim.attributes.POSITION]
        off = g.bufferViews[a.bufferView].byteOffset
        pos = np.frombuffer(bytes(blob[off:off + a.count * 12]), np.float32).reshape(-1, 3) + nudge
        blob[off:off + a.count * 12] = pos.astype(np.float32).tobytes()
    if index_edit:
        a = g.accessors[prim.indices]
        off = g.bufferViews[a.bufferView].byteOffset
        blob[off:off + 4] = blob[off + 2:off + 4] + blob[off:off + 2]  # swap two corners
    g.set_binary_blob(bytes(blob))
    g.save_binary(str(raw))
    out = tmp_path / f"{name}.glb"
    split_glb_by_region(str(raw), str(out), JOINTS)
    _rewrite_interpolation_linear(str(out))
    return out.read_bytes()


def test_swap_replaces_the_surface_and_nothing_else(tmp_path):
    ref = _exported(tmp_path, "ref")
    shaped = _exported(tmp_path, "shaped", nudge=np.array([0.0, 0.01, 0.02], np.float32))
    new = standardize_glb(shaped, ref)
    report = verify_glb(shaped, new, ref)  # raises on any byte outside the surface
    assert report["surface_moved_cm_mean"] == pytest.approx(np.hypot(1, 2), abs=1e-3)
    assert report["zero_norm_rotations"] == 0
    assert standardize_glb(new, ref) == new, "idempotent: a standard body stays as it is"


def test_swap_refuses_a_different_topology(tmp_path):
    ref = _exported(tmp_path, "ref")
    other = _exported(tmp_path, "other", index_edit=True)
    with pytest.raises(Mismatch):
        standardize_glb(other, ref)
