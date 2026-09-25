#!/bin/sh
# Download the public MotionResults used by segment.py into .cache/ (not committed).
set -e
here=$(dirname "$0")
mkdir -p "$here/.cache"
for j in job_5716ecd319064b329b53df005b736757 job_345b747b1edb406a90e8f0d847b9c518 \
         job_b8223229f23240d39305493bbe628d7d job_a10682e744734f0fb4034149fb4c0569 \
         job_7995c97829a942aba13301fcd14704dd; do
  [ -s "$here/.cache/$j.json" ] || curl -sf --compressed -o "$here/.cache/$j.json" \
    "https://stepwise.sreshta-talluri.workers.dev/api/jobs/$j/result"
done
ls -la "$here/.cache"
