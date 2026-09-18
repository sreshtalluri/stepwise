# Not part of upstream Fast-SAM-3D-Body -- new for W10.
"""Real-mesh region segmentation for suppressed-body-part masking.

Resolves OPEN-DECISIONS.md E3. THE TRAP (still true): hiding a bone does not
hide its skinned surface -- MHR is a skinned skeleton, so an `absent`/
`uncertain` joint's surface has to be a separately-drawable mesh, not just a
transform you can zero out.

ARCHITECTURE CHOICE (E3): render-time masking, matching what W5 already built
in apps/web/components/Stage3D.tsx (it toggles `mesh.visible` / swaps material
per named `region_<id>` SkinnedMesh, driven by the per-sample `visibility`
field the contract already provides -- see regionVisibility() in
apps/web/lib/motion.ts). That logic needs no changes; it already treats "the
real MHR export" and "W5's stand-in capsule rig" identically as long as both
hand it a skeleton plus N SkinnedMeshes named `region_<id>`. So the only real
work on the export side is STRUCTURAL and ONE-TIME per mesh topology: split
the single mesh pymomentum's `Character.save_gltf_from_skel_states` writes
into 18 region sub-meshes bound to the same skin, once, as a post-process on
the GLB it already produced. The animation (skel_state per frame) is
untouched -- this only edits geometry/skinning, never a keyframe.

Rejected: baking the show/hide *itself* into the export (e.g. per-frame morph
targets zeroing a region's vertices). That would require re-deriving, at
export time, exactly the same observed/uncertain/absent decision the viewer
already makes live from `visibility` -- duplicating DESIGN.md §4's judgment
in two places, and losing the live desaturated-sketchy-outline treatment
(shader-driven, not a static geometry state) that W5 already built and tuned.
Export-time only needs to make masking *possible*; render-time decides it.

WHY A NAME MATCHER, NOT A HARDCODED JOINT-NAME TABLE. The real MHR skeleton
(127 joints, `lod3.fbx`) has never actually been inspected for joint *names*
in this pass -- docs/GATE-REPORT.md's `inspect_pymomentum` only printed the
joint *count* (127, matching mhr_model.pt) before this pass, and no Modal GPU
session ran during it (see the W10 report). Guessing a specific naming
convention (Mixamo names like the contract's OWN reduced 24-joint fixture
uses, vs. Momentum's own `b_`-prefixed sample-asset convention, vs. something
else entirely) and hardcoding it would be exactly the kind of "confident but
unverified" mistake DESIGN.md §7h exists to prevent applied to *code* instead
of a render. So this resolves the mapping from REGIONS' canonical bone names
(shared with apps/web/lib/regions.ts) to whatever names the real skeleton
actually has via a tolerant matcher (several known conventions, several
separator/case styles) plus a structural fallback for the two joints
(`pelvis`, `spine2`) that have exactly one hierarchically-correct answer
regardless of naming. If a region's bone still can't be resolved, this raises
loudly (RegionMappingError) rather than silently mis-masking a body part --
never guess here, because getting this wrong is invisible until someone
notices a limb is masked with the wrong surface.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    id: str
    bone: str  # canonical contract joint name -- must match apps/web/lib/regions.ts
    label: str


# Mirrors apps/web/lib/regions.ts REGIONS exactly (18 entries, same ids/bones).
# No cross-language codegen for this table (unlike packages/motion-contract's
# schema) -- keep the two in sync by hand if either changes.
REGIONS: list[Region] = [
    Region("torso_lower", "pelvis", "hips"),
    Region("torso_upper", "spine2", "torso"),
    Region("neck", "neck", "neck"),
    Region("head", "head", "head"),
    Region("collar_l", "left_collar", "left shoulder"),
    Region("collar_r", "right_collar", "right shoulder"),
    Region("upperarm_l", "left_shoulder", "left upper arm"),
    Region("upperarm_r", "right_shoulder", "right upper arm"),
    Region("forearm_l", "left_elbow", "left forearm"),
    Region("forearm_r", "right_elbow", "right forearm"),
    Region("hand_l", "left_wrist", "left hand"),
    Region("hand_r", "right_wrist", "right hand"),
    Region("thigh_l", "left_hip", "left thigh"),
    Region("thigh_r", "right_hip", "right thigh"),
    Region("shin_l", "left_knee", "left shin"),
    Region("shin_r", "right_knee", "right shin"),
    Region("foot_l", "left_ankle", "left foot"),
    Region("foot_r", "right_ankle", "right foot"),
]


class RegionMappingError(ValueError):
    """A canonical joint could not be confidently resolved against the real
    skeleton's joint names. Raised instead of guessing -- see module docstring."""


def _tokens(name: str) -> list[str]:
    """"LeftForeArm_02" / "b_l_forearm" / "mixamorig:LeftForeArm" -> ["left","fore","arm"]-ish."""
    # Split camelCase boundaries before lowercasing, then split on any run of
    # non-alphanumeric characters (handles ':', '_', '-', '.', digits-as-separators).
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return [t for t in re.split(r"[^a-zA-Z]+", spaced.lower()) if t]


def _joined(tokens: list[str]) -> str:
    return "".join(tokens)


_LEFT_TOKENS = {"l", "left", "lft", "lt"}
_RIGHT_TOKENS = {"r", "right", "rgt", "rt"}

# Every substring any _CATEGORY_MATCHERS predicate looks for, used below so a
# leading "L"/"R" glued directly onto a keyword with no case/separator
# boundary (e.g. "LLowerArm" tokenizes as ["llower","arm"], not ["l","lower",
# "arm"]) is still recognized as a side marker, not just a stray letter.
_SIDE_KEYWORD_FALLBACK = re.compile(
    r"^(l|r)(?=(shoulder|clavicle|collar|upperarm|arm|forearm|lowerarm|elbow|wrist|hand|"
    r"hip|upleg|upperleg|thigh|knee|lowerleg|lowleg|shin|calf|leg|ankle|foot))"
)


def _side(tokens: list[str], joined: str) -> str | None:
    if any(t in _LEFT_TOKENS for t in tokens):
        return "left"
    if any(t in _RIGHT_TOKENS for t in tokens):
        return "right"
    # No-separator fallback: a leading l/r immediately followed by a
    # recognizable keyword, not just any word starting with l/r (which would
    # false-positive on "leg", "root", etc).
    m = _SIDE_KEYWORD_FALLBACK.match(joined)
    if m:
        return "left" if m.group(1) == "l" else "right"
    return None


def _has(joined: str, *subs: str) -> bool:
    return any(s in joined for s in subs)


def _lacks(joined: str, *subs: str) -> bool:
    return not any(s in joined for s in subs)


# Per canonical (unsided) joint, an ORDERED list of predicates on the
# no-separator lowercased joint name. The first predicate with any match
# (across all joints of the right side) wins -- this is what lets "arm" match
# Mixamo's "LeftArm" (upper arm) without also matching "LeftForeArm", and lets
# a rig with a real "wrist" joint prefer it over "hand" (used only as a
# fallback for rigs, like Mixamo, that have no separate wrist bone).
# `collar` is deliberately absent: it's derived structurally (see below),
# because "clavicle"/"collar" naming is inconsistent enough across rigs
# (Mixamo literally calls the clavicle "LeftShoulder") that a keyword guess
# there is more likely to be wrong than "the upper arm's parent joint".
_CATEGORY_MATCHERS: dict[str, list] = {
    "neck": [lambda j: _has(j, "neck")],
    "head": [lambda j: _has(j, "head")],
    "shoulder": [  # the UPPER ARM joint (region canonical `left_shoulder`)
        lambda j: _has(j, "upperarm"),
        # Checked BEFORE a bare "shoulder" match: some rigs (Mixamo) call the
        # CLAVICLE "Shoulder" and the upper arm "Arm" -- "arm" (minus fore/
        # lower-arm) is a more reliable signal for "this is the upper-arm
        # joint" than the word "shoulder" itself turns out to be.
        lambda j: _has(j, "arm") and _lacks(j, "forearm", "lowerarm", "clavicle", "collar"),
        lambda j: _has(j, "shoulder") and _lacks(j, "clavicle", "collar"),
    ],
    "elbow": [
        lambda j: _has(j, "forearm", "lowerarm"),
        lambda j: _has(j, "elbow"),
    ],
    "wrist": [
        lambda j: _has(j, "wrist"),
        lambda j: _has(j, "hand") and _lacks(j, "thumb", "index", "middle", "ring", "pinky", "finger", "tip"),
    ],
    "hip": [
        lambda j: _has(j, "upleg", "upperleg", "thigh"),
        lambda j: _has(j, "hip"),
    ],
    "knee": [
        lambda j: _has(j, "lowerleg", "lowleg", "shin", "calf"),
        lambda j: _has(j, "knee"),
        lambda j: _has(j, "leg") and _lacks(j, "upleg", "upperleg", "thigh", "foot", "toe"),
    ],
    "ankle": [
        lambda j: _has(j, "ankle"),
        lambda j: _has(j, "foot") and _lacks(j, "toe", "ball"),
    ],
}


def resolve_canonical_joints(joint_names: list[str], parent_indices: list[int]) -> dict[str, int]:
    """Maps the canonical names REGIONS reference (all but `spine2`/`*_collar`,
    resolved structurally below) to indices into `joint_names`.

    Structural rules take priority over name-matching where there is exactly
    one hierarchically correct answer regardless of naming convention:
      - `pelvis` is the skeleton root (unique parent_index == -1).
      - `spine2` (torso_upper's bone -- "the joint the upper torso rotates
        from, immediately below the neck") is `neck`'s parent. There is no
        universal name for this joint across rigs (this pipeline's own
        24-joint contract fixture calls it "Spine1"; other rigs call it
        "spine2", "spine3", "chest", "upperChest" depending on how many spine
        joints exist) -- but "the neck's parent" is true by construction.
      - `left_collar`/`right_collar` is the resolved `*_shoulder` joint's
        parent, for the same reason (see `_CATEGORY_MATCHERS` docstring).

    Raises RegionMappingError, naming every unresolved canonical joint, if
    any required joint can't be found -- never returns a partial/guessed
    mapping silently.
    """
    per_joint = [(_tokens(n), n) for n in joint_names]
    per_joint_joined = [_joined(t) for t, _ in per_joint]

    roots = [i for i, p in enumerate(parent_indices) if p < 0]
    if len(roots) != 1:
        raise RegionMappingError(f"expected exactly one root joint (parent_index < 0), found {len(roots)}: {roots}")
    resolved: dict[str, int] = {"pelvis": roots[0]}
    missing: list[str] = []

    def find(canonical: str, category: str, sided: bool) -> None:
        for predicate in _CATEGORY_MATCHERS[category]:
            for i, (tokens, _name) in enumerate(per_joint):
                joined = per_joint_joined[i]
                if not predicate(joined):
                    continue
                if not sided:
                    resolved[canonical] = i
                    return
                side = _side(tokens, joined)
                want_side = "left" if canonical.startswith("left_") else "right"
                if side == want_side:
                    resolved[canonical] = i
                    return
        missing.append(canonical)

    find("neck", "neck", sided=False)
    find("head", "head", sided=False)
    for side in ("left", "right"):
        find(f"{side}_shoulder", "shoulder", sided=True)
        find(f"{side}_elbow", "elbow", sided=True)
        find(f"{side}_wrist", "wrist", sided=True)
        find(f"{side}_hip", "hip", sided=True)
        find(f"{side}_knee", "knee", sided=True)
        find(f"{side}_ankle", "ankle", sided=True)

    if missing:
        raise RegionMappingError(
            "could not confidently match these canonical joints against the real "
            f"skeleton's joint names: {missing}. Real names sampled: {joint_names[:12]}... "
            "Refusing to guess (DESIGN.md §7h's honesty standard applies to this mapping, "
            "not just to rendering) -- extend _CATEGORY_MATCHERS in region_mask.py instead."
        )

    if "neck" not in resolved:
        raise RegionMappingError("neck not resolved; cannot derive spine2 structurally")
    resolved["spine2"] = parent_indices[resolved["neck"]]

    for side in ("left", "right"):
        shoulder_idx = resolved[f"{side}_shoulder"]
        collar_idx = parent_indices[shoulder_idx]
        if collar_idx in resolved.values():
            print(
                f"region_mask: WARNING -- {side}_collar resolved to joint {collar_idx} "
                f"({joint_names[collar_idx]}), already used by another region bone. "
                "This rig likely has no separate clavicle joint; collar_%s's surface "
                "will be folded into whatever region owns that joint instead of getting "
                "its own. Not a wrong-body-part error, just coarser granularity." % side
            )
        resolved[f"{side}_collar"] = collar_idx

    return resolved


def owning_region_by_joint(
    parent_indices: list[int], region_bone_joint: dict[str, int]
) -> list[str | None]:
    """For every joint index, which REGIONS[i].id "owns" it: walk up the parent
    chain (starting at the joint itself) until hitting a joint that IS one of
    the 18 region bones. Every joint reaches one eventually because `pelvis`
    (the root) is always a region bone (`torso_lower`), so the walk always
    terminates. This is how a finger joint ends up owned by `hand_l` (walks
    finger -> ... -> left_hand -> left_wrist, and left_wrist IS hand_l's bone)
    without ever needing to name "hand" as its own joint.
    """
    bone_to_region = {joint_idx: region.id for region in REGIONS for joint_idx in [region_bone_joint.get(region.bone)] if joint_idx is not None}
    n = len(parent_indices)
    owner: list[str | None] = [None] * n
    for start in range(n):
        j = start
        seen = set()
        while j not in bone_to_region:
            if j in seen or j < 0:
                owner[start] = None  # disconnected/cyclic skeleton data -- leave unassigned
                break
            seen.add(j)
            j = parent_indices[j]
        else:
            owner[start] = bone_to_region[j]
    return owner


def assign_vertices_to_regions(joints0: "list[list[int]]", weights0: "list[list[float]]", skin_joint_owner: list[str | None]) -> list[str | None]:
    """Per vertex: the region of its highest-skin-weight joint influence.

    `joints0`/`weights0` are the glTF JOINTS_0/WEIGHTS_0 attributes (already
    resolved from skin-local joint index to the flat skeleton joint index by
    the caller). `skin_joint_owner[j]` is `owning_region_by_joint(...)[j]`.
    """
    out: list[str | None] = []
    for j4, w4 in zip(joints0, weights0):
        best_j, best_w = j4[0], w4[0]
        for j, w in zip(j4[1:], w4[1:]):
            if w > best_w:
                best_j, best_w = j, w
        out.append(skin_joint_owner[best_j] if 0 <= best_j < len(skin_joint_owner) else None)
    return out


# --------------------------------------------------------------------- glTF I/O

_ACCESSOR_DTYPE = {
    5121: ("B", 1),  # UNSIGNED_BYTE
    5123: ("H", 2),  # UNSIGNED_SHORT
    5125: ("I", 4),  # UNSIGNED_INT
    5126: ("f", 4),  # FLOAT
}
_TYPE_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _read_accessor(gltf, blob: bytes, accessor_index: int) -> list:
    """Decodes one accessor into a flat list of per-element tuples (or scalars
    for SCALAR type), independent of numpy so this stays trivially testable."""
    import struct

    acc = gltf.accessors[accessor_index]
    bv = gltf.bufferViews[acc.bufferView]
    fmt_char, comp_size = _ACCESSOR_DTYPE[acc.componentType]
    n_comp = _TYPE_COMPONENTS[acc.type]
    stride = bv.byteStride or (comp_size * n_comp)
    base = (bv.byteOffset or 0) + (acc.byteOffset or 0)
    out = []
    for i in range(acc.count):
        off = base + i * stride
        vals = struct.unpack_from(f"<{n_comp}{fmt_char}", blob, off)
        out.append(vals[0] if n_comp == 1 else list(vals))
    return out


def _append_accessor(gltf, blob: bytearray, values: list, component_type: int, type_: str, target: int | None = None) -> int:
    """Packs `values` (list of scalars, or list of same-length lists) as a new
    buffer region + bufferView + accessor appended to buffer 0. Returns the
    new accessor index. glTF requires 4-byte alignment for bufferViews."""
    import struct

    fmt_char, comp_size = _ACCESSOR_DTYPE[component_type]
    n_comp = _TYPE_COMPONENTS[type_]
    while len(blob) % 4 != 0:
        blob.append(0)
    offset = len(blob)
    for v in values:
        row = v if n_comp > 1 else [v]
        blob.extend(struct.pack(f"<{n_comp}{fmt_char}", *row))
    length = len(blob) - offset

    bv_index = len(gltf.bufferViews)
    import pygltflib as gltflib

    gltf.bufferViews.append(
        gltflib.BufferView(buffer=0, byteOffset=offset, byteLength=length, target=target)
    )
    acc_index = len(gltf.accessors)
    kwargs: dict = dict(bufferView=bv_index, componentType=component_type, count=len(values), type=type_)
    if type_ != "SCALAR":
        cols = list(zip(*values)) if values else [[] for _ in range(n_comp)]
        kwargs["min"] = [min(c) for c in cols] if values else [0.0] * n_comp
        kwargs["max"] = [max(c) for c in cols] if values else [0.0] * n_comp
    gltf.accessors.append(gltflib.Accessor(**kwargs))
    return acc_index


def split_glb_by_region(in_path: str, out_path: str, region_bone_joint: dict[str, int] | None = None) -> dict[str, int]:
    """Rewrites the single-mesh GLB `pymomentum.Character.save_gltf_from_skel_states`
    produces into one whose skinned mesh is split into named `region_<id>`
    sub-meshes bound to the same skin -- the structural change render-time
    masking needs (see module docstring). Animation channels, the skeleton,
    and every node outside the mesh/mesh-node are left untouched.

    `region_bone_joint` maps canonical joint names -> flat skeleton joint
    index; if omitted, it's resolved from the skin's own joint node names via
    `resolve_canonical_joints`.

    Returns {region_id: triangle_count} (0 for a region with no surface --
    e.g. a rig with no separate collar bone) so a caller can sanity-check the
    split before trusting it (measure, don't trust).
    """
    import pygltflib as gltflib

    gltf = gltflib.GLTF2().load(in_path)
    blob = bytearray(gltf.binary_blob())

    if not gltf.skins:
        raise RegionMappingError(f"{in_path}: no skin found -- not a skinned mesh export")
    skin = gltf.skins[0]
    skin_joint_nodes = skin.joints  # node indices, in skin-local order
    joint_names = [gltf.nodes[n].name or f"joint_{n}" for n in skin_joint_nodes]

    # Flat skeleton parent_indices, in the SAME skin-local order as
    # joint_names/skin_joint_nodes, from the glTF node hierarchy.
    node_to_skin_index = {n: i for i, n in enumerate(skin_joint_nodes)}
    parent_indices = [-1] * len(skin_joint_nodes)
    for i, node_idx in enumerate(skin_joint_nodes):
        for candidate_node, node in enumerate(gltf.nodes):
            if node_idx in (node.children or []):
                parent_indices[i] = node_to_skin_index.get(candidate_node, -1)
                break

    if region_bone_joint is None:
        region_bone_joint = resolve_canonical_joints(joint_names, parent_indices)
    owner_by_joint = owning_region_by_joint(parent_indices, region_bone_joint)

    # Find the mesh node pymomentum wrote (the one node with both mesh+skin).
    mesh_node_index = next(i for i, n in enumerate(gltf.nodes) if n.mesh is not None and n.skin is not None)
    mesh_node = gltf.nodes[mesh_node_index]
    mesh = gltf.meshes[mesh_node.mesh]

    region_triangle_counts: dict[str, int] = {r.id: 0 for r in REGIONS}
    new_mesh_indices: list[tuple[str, int]] = []  # (region_id, mesh_index)

    for prim in mesh.primitives:
        positions = _read_accessor(gltf, blob, prim.attributes.POSITION)
        normals = _read_accessor(gltf, blob, prim.attributes.NORMAL) if prim.attributes.NORMAL is not None else None
        joints0 = _read_accessor(gltf, blob, prim.attributes.JOINTS_0)
        weights0 = _read_accessor(gltf, blob, prim.attributes.WEIGHTS_0)
        indices = _read_accessor(gltf, blob, prim.indices)
        # Preserve whatever component types the original export actually used
        # (JOINTS_0 is legally UNSIGNED_BYTE or UNSIGNED_SHORT depending on
        # joint count; indices likewise vary with vertex count) rather than
        # assuming pymomentum's choice matches this module's test fixtures.
        joints_component_type = gltf.accessors[prim.attributes.JOINTS_0].componentType
        index_component_type = gltf.accessors[prim.indices].componentType

        vertex_region = assign_vertices_to_regions(joints0, weights0, owner_by_joint)

        # A face belongs to the region most of its 3 verts belong to (seam
        # verts get duplicated across regions below -- standard for splitting
        # a shared-vertex mesh by material/region).
        faces_by_region: dict[str, list[tuple[int, int, int]]] = {r.id: [] for r in REGIONS}
        for t in range(0, len(indices), 3):
            tri = (indices[t], indices[t + 1], indices[t + 2])
            votes: dict[str, int] = {}
            for v in tri:
                r = vertex_region[v]
                if r is not None:
                    votes[r] = votes.get(r, 0) + 1
            if not votes:
                continue
            winner = max(votes, key=votes.get)
            faces_by_region[winner].append(tri)

        for region in REGIONS:
            tris = faces_by_region[region.id]
            region_triangle_counts[region.id] += len(tris)
            if not tris:
                continue
            used = sorted({v for tri in tris for v in tri})
            remap = {old: new for new, old in enumerate(used)}

            new_positions = [positions[v] for v in used]
            new_normals = [normals[v] for v in used] if normals is not None else None
            new_joints0 = [joints0[v] for v in used]
            new_weights0 = [weights0[v] for v in used]
            new_indices = [remap[v] for tri in tris for v in tri]

            pos_acc = _append_accessor(gltf, blob, new_positions, 5126, "VEC3", gltflib.ARRAY_BUFFER)
            norm_acc = (
                _append_accessor(gltf, blob, new_normals, 5126, "VEC3", gltflib.ARRAY_BUFFER)
                if new_normals is not None
                else None
            )
            joints_acc = _append_accessor(gltf, blob, new_joints0, joints_component_type, "VEC4", gltflib.ARRAY_BUFFER)
            weights_acc = _append_accessor(gltf, blob, new_weights0, 5126, "VEC4", gltflib.ARRAY_BUFFER)
            idx_acc = _append_accessor(gltf, blob, new_indices, index_component_type, "SCALAR", gltflib.ELEMENT_ARRAY_BUFFER)

            attrs = gltflib.Attributes(POSITION=pos_acc, JOINTS_0=joints_acc, WEIGHTS_0=weights_acc)
            if norm_acc is not None:
                attrs.NORMAL = norm_acc
            new_prim = gltflib.Primitive(attributes=attrs, indices=idx_acc, material=prim.material)
            new_mesh = gltflib.Mesh(primitives=[new_prim], name=f"region_{region.id}")
            gltf.meshes.append(new_mesh)
            new_mesh_indices.append((region.id, len(gltf.meshes) - 1))

    # Replace the one pymomentum-authored mesh node with one node per
    # non-empty region, each `name="region_<id>"`, same skin, same parent --
    # exactly the structure Stage3D.tsx already looks for.
    parent_of_mesh_node = next((n for n in gltf.nodes if mesh_node_index in (n.children or [])), None)
    new_node_indices = []
    for region_id, mesh_idx in new_mesh_indices:
        gltf.nodes.append(
            gltflib.Node(mesh=mesh_idx, skin=mesh_node.skin, name=f"region_{region_id}")
        )
        new_node_indices.append(len(gltf.nodes) - 1)

    if parent_of_mesh_node is not None:
        parent_of_mesh_node.children = [c for c in parent_of_mesh_node.children if c != mesh_node_index] + new_node_indices
    else:
        for scene in gltf.scenes:
            if mesh_node_index in scene.nodes:
                scene.nodes = [c for c in scene.nodes if c != mesh_node_index] + new_node_indices
    gltf.nodes[mesh_node_index].mesh = None
    gltf.nodes[mesh_node_index].skin = None

    gltf.set_binary_blob(bytes(blob))
    gltf.save_binary(out_path)
    return region_triangle_counts
