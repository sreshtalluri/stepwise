#!/usr/bin/env bash
# Regenerates python/motion_contract/generated/*.py from schema/*.schema.json.
# Run: bash scripts/generate-python.sh
set -euo pipefail
cd "$(dirname "$0")/.."

HEADER='# GENERATED FILE — do not edit by hand.
# Source of truth: packages/motion-contract/schema/*.schema.json
# Regenerate with: bash scripts/generate-python.sh'

uv run --project python datamodel-codegen \
  --input schema/motion-result.schema.json \
  --input-file-type jsonschema \
  --output python/motion_contract/generated/motion_result.py \
  --output-model-type pydantic_v2.BaseModel \
  --class-name MotionResult \
  --target-python-version 3.11 \
  --disable-timestamp \
  --use-schema-description \
  --collapse-root-models \
  --custom-file-header "$HEADER"

uv run --project python datamodel-codegen \
  --input schema/job-status.schema.json \
  --input-file-type jsonschema \
  --output python/motion_contract/generated/job_status.py \
  --output-model-type pydantic_v2.BaseModel \
  --class-name JobStatus \
  --target-python-version 3.11 \
  --disable-timestamp \
  --use-schema-description \
  --collapse-root-models \
  --custom-file-header "$HEADER"

echo "wrote python/motion_contract/generated/motion_result.py and job_status.py"
