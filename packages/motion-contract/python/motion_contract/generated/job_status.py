# GENERATED FILE — do not edit by hand.
# Source of truth: packages/motion-contract/schema/*.schema.json
# Regenerate with: bash scripts/generate-python.sh

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, confloat, conint, constr


class State(Enum):
    """
    "succeeded" and "failed" are terminal. A retried job stays at job_id and moves back to "queued", incrementing retry_count, rather than minting a new id.
    """

    queued = 'queued'
    processing = 'processing'
    succeeded = 'succeeded'
    failed = 'failed'


class Error(BaseModel):
    """
    Required to be null unless state is "failed".
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    code: constr(min_length=1) = Field(
        ...,
        description='Stable machine-readable code, e.g. "no_dancer_found", "clip_too_long", "pipeline_error". Drives which OPEN-DECISIONS.md B1/B2 recovery UI is shown.',
    )
    message: constr(min_length=1) = Field(
        ...,
        description='Human-readable, says what happened — never blame the user, never apologize (DESIGN.md §11).',
    )
    retryable: bool = Field(
        ...,
        description='Whether re-submitting the same clip could plausibly succeed (true for transient GPU/queue errors, false for e.g. "no dancer found").',
    )


class JobStatus(BaseModel):
    """
    Deliberately separate from MotionResult (which only ever describes a finished job). services/motion-api polls/pushes this while a job is queued, processing, or failed; once `state` is "succeeded", the job's MotionResult document is fetched separately by job_id. Keeping these two contracts apart means a MotionResult document is never in a partially-valid state.
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    schema_version: Literal['1.0.0']
    job_id: constr(min_length=1) = Field(
        ...,
        description='Same immutable id that will appear as MotionResult.job_id once the job succeeds.',
    )
    state: State = Field(
        ...,
        description='"succeeded" and "failed" are terminal. A retried job stays at job_id and moves back to "queued", incrementing retry_count, rather than minting a new id.',
    )
    stage_message: str = Field(
        ...,
        description='Plain-language current stage for display, per DESIGN.md §7c — e.g. "Building the body — count 9 of 32". Never a bare percentage or an internal stage enum. Empty string when state is "queued".',
    )
    progress: confloat(ge=0.0, le=1.0) | None = Field(
        ...,
        description='Rough fraction complete, for a progress bar\'s width only. DESIGN.md §7c: display as loose relative time ("about 2 minutes left"), never as false-precision countdown. null when state is "queued" or "failed".',
    )
    error: Error | None = Field(
        ..., description='Required to be null unless state is "failed".'
    )
    retry_count: conint(ge=0) = Field(
        ...,
        description="Number of times this job has been retried. 0 for a job's first attempt.",
    )
