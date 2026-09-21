"""The world-vs-local rotation conversion in api.py.

This is the one piece of real math in the HTTP layer, and it shipped wrong:
skel_state's WORLD quaternions were handed to _rest_relative_rotation as
though they were already parent-relative, so every joint below the root was
served its whole chain's accumulated orientation instead of its own bend
(median 125.7 degrees off, measured on the real solo-01 reconstruction).

A synthetic chain is enough to catch that and any conjugate/multiplication-
order slip, and needs no GPU, no Modal token and no reconstruction data.

    python -m pytest services/motion-api/test_api_rotations.py
"""
import math

import pytest

from api import _local_rotations, _quat_conj, _quat_mul, _rest_relative_rotation


def _axis_angle(axis, degrees):
    x, y, z = axis
    n = math.sqrt(x * x + y * y + z * z)
    x, y, z = x / n, y / n, z / n
    h = math.radians(degrees) / 2.0
    s = math.sin(h)
    return (x * s, y * s, z * s, math.cos(h))


def _close(a, b, tol=1e-9):
    """Quaternions are a double cover: q and -q are the same rotation."""
    same = all(abs(u - v) < tol for u, v in zip(a, b))
    flipped = all(abs(u + v) < tol for u, v in zip(a, b))
    return same or flipped


class _Chain:
    """root -> a -> b, plus a second child off the root, as a (J, 8) stand-in
    for one frame of skel_state. Only columns 3:7 (the quaternion) matter."""

    parents = [-1, 0, 1, 0]

    def __init__(self, world_quats):
        self.rows = [[0.0, 0.0, 0.0, *q, 1.0] for q in world_quats]

    def __getitem__(self, idx):
        joint, sl = idx
        return self.rows[joint][sl]


def test_root_local_equals_world():
    """The root has no parent, so its local rotation IS its world rotation."""
    r = _axis_angle((0, 1, 0), 30)
    chain = _Chain([r, r, r, r])
    assert _close(_local_rotations(chain, _Chain.parents)[0], r)


def test_local_is_parent_relative_not_world():
    """The regression that shipped. Child b's world rotation is 90 deg about Y;
    its parent a is already at 60 deg about Y; so b's own bend is 30 deg --
    not the 90 the buggy version served."""
    root = _axis_angle((0, 1, 0), 0)
    a = _axis_angle((0, 1, 0), 60)
    b = _axis_angle((0, 1, 0), 90)
    local = _local_rotations(_Chain([root, a, b, a]), _Chain.parents)
    assert _close(local[1], _axis_angle((0, 1, 0), 60))   # a relative to root
    assert _close(local[2], _axis_angle((0, 1, 0), 30))   # b relative to a
    assert not _close(local[2], b), "serving the world rotation is the bug"


def test_composing_locals_back_up_the_chain_recovers_world():
    """The real invariant: world[j] == world[parent] * local[j] for every
    joint. If that holds, the decomposition is right by construction."""
    worlds = [
        _axis_angle((0, 1, 0), 17),
        _axis_angle((1, 0, 0), 41),
        _axis_angle((0.3, 0.5, -0.8), 123),
        _axis_angle((-1, 2, 0.5), 77),
    ]
    chain = _Chain(worlds)
    local = _local_rotations(chain, _Chain.parents)
    for j, parent in enumerate(_Chain.parents):
        recomposed = local[j] if parent < 0 else _quat_mul(worlds[parent], local[j])
        assert _close(recomposed, worlds[j], tol=1e-9), f"joint {j} does not recompose"


def test_branch_siblings_do_not_inherit_each_other():
    """Joint 3 hangs off the root, not off the a->b chain. Its local rotation
    must not pick up anything from that chain."""
    worlds = [
        _axis_angle((0, 1, 0), 0),
        _axis_angle((0, 1, 0), 90),
        _axis_angle((0, 1, 0), 170),
        _axis_angle((0, 0, 1), 45),
    ]
    local = _local_rotations(_Chain(worlds), _Chain.parents)
    assert _close(local[3], _axis_angle((0, 0, 1), 45))


def test_rest_relative_identity_when_pose_equals_rest():
    """JointHierarchy.rotation_convention: identity == exactly the rest pose."""
    rest = _axis_angle((0.2, -0.7, 0.4), 88)
    assert _close(_rest_relative_rotation(rest, rest), (0.0, 0.0, 0.0, 1.0))


def test_quat_conj_inverts_a_unit_quaternion():
    q = _axis_angle((1, -2, 3), 64)
    assert _close(_quat_mul(q, _quat_conj(q)), (0.0, 0.0, 0.0, 1.0))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
