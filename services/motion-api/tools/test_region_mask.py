# Not part of upstream Fast-SAM-3D-Body -- new for W10.
"""Runnable self-check for region_mask.py.

No GPU, pymomentum, or Modal needed -- these test the joint-name matcher
against several real-world naming conventions (since the actual MHR
skeleton's joint names have never been inspected in this repo, only its
joint *count*, per docs/GATE-REPORT.md) and the GLB-splitting mechanics
against a synthetic skinned GLB built with pygltflib, standing in for what
pymomentum's `Character.save_gltf_from_skel_states` produces (single skinned
mesh + skeleton). This is the honest ceiling of what could be verified
without a Modal GPU session this pass -- see the W10 report for exactly what
still needs running against the real `lod3.fbx` output.

Run: python3 test_region_mask.py
"""
from __future__ import annotations

from region_mask import (
    REGIONS,
    RegionMappingError,
    owning_region_by_joint,
    resolve_canonical_joints,
    split_glb_by_region,
)

CANONICAL_REQUIRED = [
    "pelvis", "spine2", "neck", "head",
    "left_collar", "right_collar", "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow", "left_wrist", "right_wrist",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle",
]


def _build(names_and_parents: list[tuple[str, str | None]]) -> tuple[list[str], list[int]]:
    """[(name, parent_name_or_None), ...] -> (names, parent_indices)."""
    names = [n for n, _ in names_and_parents]
    index = {n: i for i, n in enumerate(names)}
    parents = [index[p] if p is not None else -1 for _, p in names_and_parents]
    return names, parents


# --- Convention A: Mixamo (this repo's own 24-joint contract fixture uses
# this for its stand-in glb_node_name values) -- notably, the clavicle is
# literally named "*Shoulder" and there is no separate wrist bone.
MIXAMO = [
    ("Hips", None), ("Spine", "Hips"), ("Spine1", "Spine"), ("Spine2", "Spine1"),
    ("Neck", "Spine2"), ("Head", "Neck"),
    ("LeftShoulder", "Spine2"), ("LeftArm", "LeftShoulder"), ("LeftForeArm", "LeftArm"), ("LeftHand", "LeftForeArm"),
    ("RightShoulder", "Spine2"), ("RightArm", "RightShoulder"), ("RightForeArm", "RightArm"), ("RightHand", "RightForeArm"),
    ("LeftUpLeg", "Hips"), ("LeftLeg", "LeftUpLeg"), ("LeftFoot", "LeftLeg"), ("LeftToeBase", "LeftFoot"),
    ("RightUpLeg", "Hips"), ("RightLeg", "RightUpLeg"), ("RightFoot", "RightLeg"), ("RightToeBase", "RightFoot"),
]

# --- Convention B: Momentum-style b_-prefixed, snake_case, WITH a distinct
# clavicle and wrist joint (plausibly closer to the real MHR asset).
MOMENTUM = [
    ("b_root", None), ("b_spine0", "b_root"), ("b_spine1", "b_spine0"),
    ("b_neck", "b_spine1"), ("b_head", "b_neck"),
    ("b_l_clavicle", "b_spine1"), ("b_l_upperarm", "b_l_clavicle"), ("b_l_forearm", "b_l_upperarm"),
    ("b_l_wrist", "b_l_forearm"), ("b_l_hand", "b_l_wrist"),
    ("b_r_clavicle", "b_spine1"), ("b_r_upperarm", "b_r_clavicle"), ("b_r_forearm", "b_r_upperarm"),
    ("b_r_wrist", "b_r_forearm"), ("b_r_hand", "b_r_wrist"),
    ("b_l_upleg", "b_root"), ("b_l_lowleg", "b_l_upleg"), ("b_l_foot", "b_l_lowleg"), ("b_l_toes", "b_l_foot"),
    ("b_r_upleg", "b_root"), ("b_r_lowleg", "b_r_upleg"), ("b_r_foot", "b_r_lowleg"), ("b_r_toes", "b_r_foot"),
]

# --- Convention C: Unity-humanoid-ish, terse single-letter side prefix, no
# separate clavicle.
UNITY_ISH = [
    ("Hips", None), ("Spine", "Hips"), ("Chest", "Spine"), ("Neck", "Chest"), ("Head", "Neck"),
    ("LUpperArm", "Chest"), ("LLowerArm", "LUpperArm"), ("LHand", "LLowerArm"),
    ("RUpperArm", "Chest"), ("RLowerArm", "RUpperArm"), ("RHand", "RLowerArm"),
    ("LUpLeg", "Hips"), ("LLowLeg", "LUpLeg"), ("LFoot", "LLowLeg"),
    ("RUpLeg", "Hips"), ("RLowLeg", "RUpLeg"), ("RFoot", "RLowLeg"),
]


# --- Convention D: the REAL MHR skeleton (facebook/sam-3d-body-dinov3's
# bundled mhr_model.pt), captured 2026-09-18 by running
# `modal_app.py::inspect_mhr_region_mapping` for real against the actual
# gated weights. `l_`/`r_` prefixed, and critically: the forearm bone is
# named "lowarm" (no "er"), which the original elbow matcher (checking only
# "forearm"/"lowerarm") did not catch -- it raised RegionMappingError rather
# than guess, per the honesty standard, and got fixed here instead of papered
# over. Trimmed to the joints region_mask.py actually needs; the real
# skeleton has 127 total (fingers, twist-correction joints, face) omitted.
REAL_MHR = [
    ("body_world", None), ("root", "body_world"),
    ("c_spine0", "root"), ("c_spine1", "c_spine0"), ("c_spine2", "c_spine1"), ("c_spine3", "c_spine2"),
    ("c_neck", "c_spine3"), ("c_head", "c_neck"),
    ("l_clavicle", "c_spine3"), ("l_uparm", "l_clavicle"), ("l_lowarm", "l_uparm"),
    ("l_wrist_twist", "l_lowarm"), ("l_wrist", "l_lowarm"),
    ("r_clavicle", "c_spine3"), ("r_uparm", "r_clavicle"), ("r_lowarm", "r_uparm"),
    ("r_wrist_twist", "r_lowarm"), ("r_wrist", "r_lowarm"),
    ("l_upleg", "root"), ("l_lowleg", "l_upleg"), ("l_foot", "l_lowleg"), ("l_ball", "l_foot"),
    ("r_upleg", "root"), ("r_lowleg", "r_upleg"), ("r_foot", "r_lowleg"), ("r_ball", "r_foot"),
]


def test_real_mhr_skeleton_resolves_every_canonical_joint():
    names, parents = _build(REAL_MHR)
    resolved = _check_all_resolved(names, parents, "real-mhr")
    assert names[resolved["left_elbow"]] == "l_lowarm"
    assert names[resolved["right_elbow"]] == "r_lowarm"
    assert names[resolved["left_knee"]] == "l_lowleg"
    assert names[resolved["left_shoulder"]] == "l_uparm"
    assert names[resolved["left_collar"]] == "l_clavicle"
    assert names[resolved["pelvis"]] == "body_world"
    # Real bug caught against real data: "l_wrist_twist" is a corrective
    # rotation-distribution bone, not the wrist -- it must lose to "l_wrist".
    assert names[resolved["left_wrist"]] == "l_wrist"
    assert names[resolved["right_wrist"]] == "r_wrist"


def _check_all_resolved(names, parents, label):
    resolved = resolve_canonical_joints(names, parents)
    for c in CANONICAL_REQUIRED:
        assert c in resolved, f"{label}: {c} not resolved"
    return resolved


def test_mixamo_convention_resolves_every_canonical_joint():
    names, parents = _build(MIXAMO)
    resolved = _check_all_resolved(names, parents, "mixamo")
    assert names[resolved["left_shoulder"]] == "LeftArm"
    assert names[resolved["left_elbow"]] == "LeftForeArm"
    assert names[resolved["left_wrist"]] == "LeftHand"  # no separate wrist bone -> hand fallback
    assert names[resolved["left_collar"]] == "LeftShoulder"  # structural, not keyword
    assert names[resolved["spine2"]] == "Spine2"
    assert names[resolved["pelvis"]] == "Hips"


def test_momentum_convention_resolves_every_canonical_joint():
    names, parents = _build(MOMENTUM)
    resolved = _check_all_resolved(names, parents, "momentum")
    assert names[resolved["left_shoulder"]] == "b_l_upperarm"
    assert names[resolved["left_collar"]] == "b_l_clavicle"
    assert names[resolved["left_wrist"]] == "b_l_wrist"  # real wrist bone preferred over hand
    assert names[resolved["right_ankle"]] == "b_r_foot"


def test_unity_ish_convention_resolves_every_canonical_joint():
    names, parents = _build(UNITY_ISH)
    resolved = _check_all_resolved(names, parents, "unity_ish")
    assert names[resolved["left_shoulder"]] == "LUpperArm"
    assert names[resolved["left_elbow"]] == "LLowerArm"
    assert names[resolved["left_knee"]] == "LLowLeg"


def test_missing_required_joint_raises_instead_of_guessing():
    # No head joint at all -- must raise, not silently point somewhere wrong.
    names, parents = _build([n for n in MIXAMO if n[0] != "Head"])
    try:
        resolve_canonical_joints(names, parents)
        raise AssertionError("expected RegionMappingError")
    except RegionMappingError as e:
        assert "head" in str(e)


def test_owning_region_assigns_descendants_past_unmapped_joints():
    # A finger joint (LeftHandIndex1) two levels below LeftHand, which is
    # itself not a region bone -- must still resolve to hand_l by walking up
    # to LeftForeArm... no: LeftHand IS resolved as left_wrist (hand_l's bone)
    # in the Mixamo convention (no separate wrist), so the finger should be
    # owned by hand_l, and a toe should be owned by foot_l.
    extended = MIXAMO + [("LeftHandIndex1", "LeftHand"), ("LeftHandIndex2", "LeftHandIndex1")]
    names, parents = _build(extended)
    resolved = resolve_canonical_joints(names, parents)
    owner = owning_region_by_joint(parents, resolved)
    idx = {n: i for i, n in enumerate(names)}
    assert owner[idx["LeftHandIndex2"]] == "hand_l"
    assert owner[idx["LeftToeBase"]] == "foot_l"
    assert owner[idx["Spine1"]] == "torso_lower"  # between pelvis and spine2
    assert owner[idx["Hips"]] == "torso_lower"
    assert owner[idx["Head"]] == "head"


def test_every_region_bone_maps_to_a_distinct_or_intentionally_shared_joint():
    # Sanity: every REGIONS entry's `bone` name is one this module actually
    # resolves (catches a REGIONS/region_mask.py drift early).
    names, parents = _build(MOMENTUM)
    resolved = resolve_canonical_joints(names, parents)
    for region in REGIONS:
        assert region.bone in resolved, f"REGIONS entry {region.id} references unresolved bone {region.bone}"


# --------------------------------------------------------- GLB split, end to end

def _build_synthetic_skinned_glb(path: str) -> None:
    """A tiny but real skinned GLB: 5-joint chain (pelvis-spine2-neck-head,
    plus one arm bone off spine2) and a mesh whose vertices are weighted
    toward different joints along that chain, so the split has real work to
    do and a real answer to check. Standing in for pymomentum's export
    (single mesh, one skin, N joints) without needing pymomentum installed.
    """
    import struct

    import pygltflib as g

    joint_names = ["Hips", "Spine2", "Neck", "Head", "LeftArm"]
    parents = [-1, 0, 1, 2, 1]

    # 10 vertices: 2 per joint influence, forming 8 triangles along a line so
    # every joint has real surface. Positions are irrelevant to the test.
    positions = [[float(i), 0.0, 0.0] for i in range(10)]
    joints0 = [[i // 2, 0, 0, 0] for i in range(10)]  # vtx pair i -> joint i//2
    weights0 = [[1.0, 0.0, 0.0, 0.0] for _ in range(10)]
    indices = []
    for i in range(0, 8, 2):
        indices += [i, i + 1, i + 2]
        indices += [i + 1, i + 3, i + 2]

    gltf = g.GLTF2()
    blob = bytearray()

    def add(values, comp_type, type_, target=None):
        fmt = {5126: "f", 5121: "B", 5123: "H"}[comp_type]
        size = {5126: 4, 5121: 1, 5123: 2}[comp_type]
        ncomp = {"VEC3": 3, "VEC4": 4, "SCALAR": 1, "MAT4": 16}[type_]
        while len(blob) % 4 != 0:
            blob.append(0)
        offset = len(blob)
        for v in values:
            row = v if ncomp > 1 else [v]
            blob.extend(struct.pack(f"<{ncomp}{fmt}", *row))
        bv = g.BufferView(buffer=0, byteOffset=offset, byteLength=len(blob) - offset, target=target)
        gltf.bufferViews.append(bv)
        acc = g.Accessor(bufferView=len(gltf.bufferViews) - 1, componentType=comp_type, count=len(values), type=type_)
        if ncomp > 1:
            cols = list(zip(*values))
            acc.min = [min(c) for c in cols]
            acc.max = [max(c) for c in cols]
        gltf.accessors.append(acc)
        return len(gltf.accessors) - 1

    pos_acc = add(positions, 5126, "VEC3", g.ARRAY_BUFFER)
    joints_acc = add(joints0, 5121, "VEC4", g.ARRAY_BUFFER)
    weights_acc = add(weights0, 5126, "VEC4", g.ARRAY_BUFFER)
    idx_acc = add(indices, 5123, "SCALAR", g.ELEMENT_ARRAY_BUFFER)

    prim = g.Primitive(attributes=g.Attributes(POSITION=pos_acc, JOINTS_0=joints_acc, WEIGHTS_0=weights_acc), indices=idx_acc)
    gltf.meshes.append(g.Mesh(primitives=[prim]))

    joint_node_indices = list(range(len(joint_names)))
    for i, name in enumerate(joint_names):
        gltf.nodes.append(g.Node(name=name))
    for i, p in enumerate(parents):
        if p >= 0:
            gltf.nodes[p].children = (gltf.nodes[p].children or []) + [i]

    ibm_acc = add([[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] for _ in joint_names], 5126, "MAT4")
    gltf.skins.append(g.Skin(joints=joint_node_indices, inverseBindMatrices=ibm_acc))

    mesh_node = g.Node(mesh=0, skin=0, name="mhr_body")
    gltf.nodes.append(mesh_node)
    mesh_node_index = len(gltf.nodes) - 1

    gltf.scenes.append(g.Scene(nodes=[0, mesh_node_index]))  # root joint (Hips) + mesh node, both top-level
    gltf.scene = 0
    gltf.buffers.append(g.Buffer(byteLength=len(blob)))
    gltf.set_binary_blob(bytes(blob))
    gltf.save_binary(path)


def test_split_glb_by_region_produces_named_region_meshes():
    import os
    import tempfile

    import pygltflib as g

    with tempfile.TemporaryDirectory() as d:
        in_path = os.path.join(d, "in.glb")
        out_path = os.path.join(d, "out.glb")
        _build_synthetic_skinned_glb(in_path)

        # This synthetic rig is deliberately minimal (5 joints, not all 18
        # canonical bones) to keep the test's geometry simple -- pass the
        # mapping explicitly rather than exercising resolve_canonical_joints
        # here too (that's covered above, against realistic full skeletons).
        # Joints 0-4 are the real synthetic skeleton; everything this rig
        # doesn't actually have gets a unique out-of-range placeholder index
        # so it can't collide with (and silently steal ownership of) a real
        # joint's region bone in the walk-up lookup table.
        region_bone_joint = {
            "pelvis": 0, "spine2": 1, "neck": 2, "head": 3, "left_shoulder": 4,
            "left_collar": 100, "right_collar": 101, "right_shoulder": 102,
            "left_elbow": 103, "right_elbow": 104, "left_wrist": 105, "right_wrist": 106,
            "left_hip": 107, "right_hip": 108, "left_knee": 109, "right_knee": 110,
            "left_ankle": 111, "right_ankle": 112,
        }
        counts = split_glb_by_region(in_path, out_path, region_bone_joint)
        # This synthetic rig only has 3 of the 18 canonical bones with real
        # geometry on them (torso_lower via Hips, torso_upper via Spine2,
        # neck via Neck, head via Head, upperarm_l via LeftArm) -- the rest
        # legitimately have zero triangles, which is fine; the test is that
        # nothing crashes and geometry lands where expected.
        assert counts["head"] > 0
        assert counts["neck"] > 0
        assert counts["torso_upper"] > 0
        assert counts["torso_lower"] > 0
        assert counts["upperarm_l"] > 0
        assert counts["thigh_l"] == 0  # no leg joints in this synthetic rig

        result = g.GLTF2().load(out_path)
        region_node_names = {n.name for n in result.nodes if n.name and n.name.startswith("region_")}
        assert "region_head" in region_node_names
        assert "region_neck" in region_node_names
        assert "region_upperarm_l" in region_node_names
        # Every region node must carry its own mesh and the ORIGINAL skin.
        for n in result.nodes:
            if n.name and n.name.startswith("region_"):
                assert n.mesh is not None
                assert n.skin == 0
        # Total triangles preserved (nothing dropped, nothing duplicated at
        # the top level -- vertex duplication at seams is expected and fine,
        # but triangle *count* must be conserved exactly).
        assert sum(counts.values()) == 8


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok: {t.__name__}")
    print(f"\n{len(tests)} tests passed")
