#!/bin/sh
# Every measurement in docs/research/dance-gate.md, from a test set built by fetch.sh.
#   sh run.sh           per-method scores (cached in $DANCE_GATE_DATA/cache), then the tables
#   sh run.sh gate      the recommended gate end to end, without and with --pose
# Needs: ffmpeg, and pip install torch torchvision transformers onnxruntime rtmlib opencv-python-headless
#        librosa soundfile beat-this==1.1.0 nudenet num2words pillow numpy
set -e
here=$(cd "$(dirname "$0")" && pwd)
export DANCE_GATE_DATA=${DANCE_GATE_DATA:-$here/.data}
PY=${PY:-python}
cd "$here"
clips="$DANCE_GATE_DATA/clips/pos/*.mp4 $DANCE_GATE_DATA/clips/neg/*.mp4 $DANCE_GATE_DATA/clips/amb/*.mp4"
if [ "$1" = gate ]; then
  $PY gate.py $clips | grep '^{' > "$DANCE_GATE_DATA/gate.jsonl"
  $PY score_gate.py "$DANCE_GATE_DATA/gate.jsonl"
  $PY gate.py --pose $clips | grep '^{' > "$DANCE_GATE_DATA/gate_pose.jsonl"
  $PY score_gate.py "$DANCE_GATE_DATA/gate_pose.jsonl"
  exit
fi
$PY extract_a.py $clips
for m in kinetics xclip clip smolvlm falconsai nudenet; do $PY extract_bcd.py $m $clips; done
$PY evaluate.py
$PY combos.py
