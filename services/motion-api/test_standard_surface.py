"""Standard body surface (docs/legal/body-shape-decision.md, option b).

Runs the real `_export_clip_gltf` over a synthetic npz whose every frame
carries an estimated `shape_params`, with pymomentum, the region split and R2
swapped for recorders, and checks the three promises:

  * the GLB is written from lod3's own character -- no shape applied,
  * the export manifest carries no shape vector,
  * the materialised MotionResult validates and says `default_assumed`.
"""
import gzip
import io
import json
import sys
import types
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
sys.path.insert(0, str(HERE.parents[1] / "packages" / "motion-contract" / "python"))

import modal_app  # noqa: E402
from test_world_placement_wiring import _synth_npz  # noqa: E402


def test_export_applies_and_keeps_no_body_shape(tmp_path, monkeypatch):
    import region_mask
    import retention

    npz, _, _ = _synth_npz(n_frames=40)
    data = dict(np.load(io.BytesIO(npz), allow_pickle=True))
    for frame in data["per_frame"]:
        for person in frame.values():
            person["shape_params"] = np.full(45, 0.7, dtype=np.float32)  # a real-looking estimate
    np.savez(tmp_path / "clip.npz", **data)

    lod3 = object()
    saved = []

    class Character:
        @staticmethod
        def load_fbx(path):
            assert path.endswith("lod3.fbx")
            return lod3

        @staticmethod
        def save_gltf_from_skel_states(path, character, fps, skel_states):
            saved.append(character)
            Path(path).write_bytes(b"glb")

    geometry = types.ModuleType("pymomentum.geometry")
    geometry.Character = Character
    pkg = types.ModuleType("pymomentum")
    pkg.geometry = geometry
    monkeypatch.setitem(sys.modules, "pymomentum", pkg)
    monkeypatch.setitem(sys.modules, "pymomentum.geometry", geometry)
    monkeypatch.setattr(modal_app, "RESULTS_DIR", str(tmp_path))
    monkeypatch.setattr(modal_app, "results", types.SimpleNamespace(reload=lambda: None, commit=lambda: None))
    monkeypatch.setattr(modal_app, "_rewrite_interpolation_linear",
                        lambda p: {"n_rewritten": 0, "n_samplers": 0, "interpolation": "LINEAR"})
    monkeypatch.setattr(modal_app, "_publish_to_r2", lambda *a, **k: [])
    monkeypatch.setattr(region_mask, "split_glb_by_region", lambda i, o: {"torso": 1})
    monkeypatch.setattr(retention, "is_removed", lambda vol, clip_id, reload=False: False)

    out = modal_app._export_clip_gltf("clip", "job_clip")

    assert saved == [lod3], "the GLB must be written from lod3's own (standard) character"
    manifest = json.loads((tmp_path / "clip.export-manifest.json").read_text())
    assert "shape_params" not in manifest and "0.7" not in json.dumps(manifest)
    assert out["motion_result_materialised"]
    doc = json.loads(gzip.decompress((tmp_path / "clip.motion-result.json.gz").read_bytes()))
    from motion_contract import validate_motion_result
    assert validate_motion_result(doc).valid
    assert [p["shape_params"] for p in doc["persons"]] == [{"source": "default_assumed"}]
