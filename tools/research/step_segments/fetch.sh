#!/bin/sh
# Download the public MotionResults (and, with --video, the source videos) used by the
# research scripts into .cache/ (not committed). Lesson ids are NOT in this repo: a job id is
# the lesson's link and the repo is public. Put one job id per line in .data/jobs.txt
# (git-ignored), optionally followed by a short name: "job_<id> bhangra".
set -e
here=$(dirname "$0")
list="$here/.data/jobs.txt"
[ -s "$list" ] || { echo "missing $list (one job id per line)"; exit 1; }
mkdir -p "$here/.cache"
while read -r j name; do
  [ -n "$j" ] || continue
  out="$here/.cache/${name:-$j}"
  [ -s "$out.json" ] || curl -sf --compressed -o "$out.json" \
    "https://stepwise.sreshta-talluri.workers.dev/api/jobs/$j/result"
  if [ "$1" = "--video" ] && [ ! -s "$out.mp4" ]; then
    curl -sfL -o "$out.mp4" "https://stepwise.sreshta-talluri.workers.dev/api/jobs/$j/video"
  fi
done < "$list"
ls -la "$here/.cache"
