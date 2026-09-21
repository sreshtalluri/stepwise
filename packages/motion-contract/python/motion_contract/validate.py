from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schema"
_MOTION_RESULT_SCHEMA = json.loads((_SCHEMA_DIR / "motion-result.schema.json").read_text())
_JOB_STATUS_SCHEMA = json.loads((_SCHEMA_DIR / "job-status.schema.json").read_text())


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]


def _format_errors(errors: list[jsonschema.ValidationError]) -> list[str]:
    return [f"{'/'.join(str(p) for p in e.path) or '/'} {e.message}" for e in errors]


def _check_invariants(doc: dict[str, Any]) -> list[str]:
    """Invariants JSON Schema can't express: cross-field array-length parity,
    monotonic sample_times_s, joint index consistency, and the
    absent-implies-a-suppression-reason honesty rule."""
    errors: list[str] = []
    sample_times = doc["sample_times_s"]
    n = len(sample_times)

    for i in range(1, n):
        if not (sample_times[i] > sample_times[i - 1]):
            errors.append(
                f"sample_times_s must be strictly increasing: index {i} ({sample_times[i]}) "
                f"<= index {i - 1} ({sample_times[i - 1]})"
            )

    joints_def = doc["joint_hierarchy"]["joints"]
    for i, j in enumerate(joints_def):
        if j["index"] != i:
            errors.append(f"joint_hierarchy.joints[{i}].index must equal {i}, got {j['index']}")
    joint_count = len(joints_def)

    for pi, person in enumerate(doc["persons"]):
        if len(person["root_trajectory"]) != n:
            errors.append(
                f"persons[{pi}].root_trajectory length {len(person['root_trajectory'])} != sample_times_s length {n}"
            )
        if len(person["samples"]) != n:
            errors.append(f"persons[{pi}].samples length {len(person['samples'])} != sample_times_s length {n}")
        if len(person["crop_rects"]["hands"]) != n:
            errors.append(
                f"persons[{pi}].crop_rects.hands length {len(person['crop_rects']['hands'])} != sample_times_s length {n}"
            )
        if len(person["crop_rects"]["feet"]) != n:
            errors.append(
                f"persons[{pi}].crop_rects.feet length {len(person['crop_rects']['feet'])} != sample_times_s length {n}"
            )
        for si, sample in enumerate(person["samples"]):
            if len(sample["joints"]) != joint_count:
                errors.append(
                    f"persons[{pi}].samples[{si}].joints length {len(sample['joints'])} "
                    f"!= joint_hierarchy.joints length {joint_count}"
                )
            for ji, joint in enumerate(sample["joints"]):
                if joint["visibility"] == "absent" and joint["provenance"]["suppressed"] is None:
                    errors.append(
                        f'persons[{pi}].samples[{si}].joints[{ji}] has visibility "absent" but '
                        f"provenance.suppressed is null — an absent joint must carry a suppression reason"
                    )

    grounding = doc["grounding"]
    if grounding["status"] == "none" and grounding["floor_plane"] is not None:
        errors.append('grounding.status is "none" but floor_plane is not null — DESIGN.md §10 forbids a floor when grounding failed')
    if grounding["status"] == "grounded" and grounding["floor_plane"] is None:
        errors.append('grounding.status is "grounded" but floor_plane is null')

    # A proposed grid that disagrees with the timeline it is laid over is worse
    # than no proposal: the count strip would run out of counts, or show counts
    # past the end of the dance, with nothing anywhere saying why. Same formula
    # as `normalizeStructure` in packages/navigation/src/core.ts, against
    # sample_times_s rather than source_video.duration_s.
    pc = doc.get("proposed_counts")
    if pc:
        end_s = doc["sample_times_s"][n - 1]
        expected = max(1, int((end_s - pc["count_one_s"]) // pc["seconds_per_count"]) + 1)
        if pc["count_total"] != expected:
            errors.append(
                f"proposed_counts.count_total is {pc['count_total']} but the grid over "
                f"sample_times_s gives {expected} — a proposal must be sized against "
                f"the authoritative timeline"
            )

    return errors


def validate_motion_result(doc: dict[str, Any]) -> ValidationResult:
    schema_errors = list(jsonschema.Draft202012Validator(_MOTION_RESULT_SCHEMA).iter_errors(doc))
    if schema_errors:
        return ValidationResult(valid=False, errors=_format_errors(schema_errors))
    invariant_errors = _check_invariants(doc)
    return ValidationResult(valid=len(invariant_errors) == 0, errors=invariant_errors)


def validate_job_status(doc: dict[str, Any]) -> ValidationResult:
    schema_errors = list(jsonschema.Draft202012Validator(_JOB_STATUS_SCHEMA).iter_errors(doc))
    return ValidationResult(valid=len(schema_errors) == 0, errors=_format_errors(schema_errors))
