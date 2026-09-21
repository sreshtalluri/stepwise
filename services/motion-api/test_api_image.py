"""Does api.py still import from only the files api_image actually ships?

This suite exists because of one defect found in the third integration pass,
and it guards the exact class rather than the one instance:

  `deployment`'s api_image excludes `vendor/**` (1.9 GB of Fast-SAM-3D-Body
  that a CPU web container must never carry). `grounding-wiring` gave
  `motion_result` a module-level import that reaches into `vendor/`. api.py
  imports motion_result at module level. Composed: `modal deploy` succeeds,
  the image builds, and then every request to the ASGI app dies inside
  `web()` with ModuleNotFoundError.

Git raised no conflict -- the two branches touched different files -- and no
existing test could have caught it, because every suite runs from a checkout
where `vendor/` is simply there on disk. So the check has to be an import
performed against a tree built to api_image's own rules, in a subprocess with
a clean sys.modules.

If this fails, the fix is a mount in api_image (modal_app.py), not a relaxation
here: the whole point is that api.py stays deployable without the CV tree.
"""
from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent


def _api_image_extra_files() -> list[tuple[Path, str]]:
    """`(local_path, remote_path)` for every `add_local_file` on api_image.

    Parsed out of modal_app.py's source rather than imported, because importing
    modal_app pulls in the modal client and builds Image objects whose mount
    list is not introspectable. A blunt AST walk is enough: we only need the
    string literals, and a mount this test does not understand shows up as a
    missing file, i.e. a failure, not a false pass.
    """
    tree = ast.parse((HERE / "modal_app.py").read_text())
    out: list[tuple[Path, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "api_image" for t in node.targets)):
            continue
        for call in ast.walk(node.value):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "add_local_file" and len(call.args) == 2):
                continue
            remote = call.args[1]
            if not isinstance(remote, ast.Constant):
                continue
            # The local arg is an os.path.join of literals rooted at
            # MOTION_API_DIR; collect the literal parts and join them.
            parts = [n.value for n in ast.walk(call.args[0])
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            out.append((HERE.joinpath(*parts), remote.value))
    return out


def _build_image_tree(dest: Path) -> Path:
    """Reproduce api_image's file layout: the three add_local_dir mounts with
    their ignore rules, plus every add_local_file."""
    def ignore_pyc(_dir, names):
        return [n for n in names if n == "__pycache__" or n.endswith(".pyc")]

    shutil.copytree(HERE, dest / "app/services/motion-api",
                    ignore=lambda d, n: ignore_pyc(d, n) + [x for x in n if x in ("vendor", ".venv")])
    mc = REPO_ROOT / "packages/motion-contract"
    shutil.copytree(mc / "python", dest / "app/packages/motion-contract/python",
                    ignore=lambda d, n: ignore_pyc(d, n) + [x for x in n if x == ".venv"])
    shutil.copytree(mc / "schema", dest / "app/packages/motion-contract/schema")

    for local, remote in _api_image_extra_files():
        target = dest / remote.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local, target)
    return dest / "app/services/motion-api"


def test_api_imports_with_only_what_api_image_ships():
    with tempfile.TemporaryDirectory() as tmp:
        app_dir = _build_image_tree(Path(tmp))
        assert not (app_dir / "vendor/fast-sam-3d-body/sam_3d_body").exists(), \
            "the CV tree must stay out of the API image -- that is the point"
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, sys.argv[1]); import api", str(app_dir)],
            capture_output=True, text=True, env={**os.environ, "PYTHONPATH": ""})
    assert proc.returncode == 0, (
        "api.py does not import from what api_image ships -- the deployed ASGI app "
        "would 500 on every request while `modal deploy` reported success.\n"
        f"{proc.stderr}")


def test_skeleton_constraints_is_mounted_despite_the_vendor_exclusion():
    """The specific instance, named, so a failure reads as itself.

    Narrower than the test above on purpose: that one tells you something is
    unshippable, this one tells you which mount went missing.
    """
    remotes = [r for _, r in _api_image_extra_files()]
    assert any(r.endswith("/skeleton_constraints.py") for r in remotes), (
        "api_image ignores vendor/**, but world_placement_probe (reached from "
        "motion_result, reached from api) imports skeleton_constraints from it"
    )
