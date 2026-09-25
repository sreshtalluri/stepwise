#!/bin/sh
# Build the test set in $DANCE_GATE_DATA (default ./.data, gitignored). No video is ever committed.
#
#   1. positives: our lessons' source videos. Their job ids are NOT in this public repo (a job id is the
#      lesson link): put them one per line in $DATA/jobs.txt, with "walkin" after the one whose clip
#      opens with a walk-in (it also becomes a hard negative, cut to its first 4.4 s).
#   2. positives: the eval clips from the stepwise-eval Modal Volume (needs `modal` logged in).
#   3. Wikimedia Commons clips (every file there is CC/PD; manifest.json records source and licence),
#      then the label fixes in relabel.py and the no-video-stream check in quarantine.py.
#   4. hard cases derived from (1): a dancer's frame frozen for 12 s over the original music (negative),
#      and lessons with the audio stripped (positive: a muted dance must still pass).
set -e
here=$(cd "$(dirname "$0")" && pwd)
DATA=${DANCE_GATE_DATA:-$here/.data}
export DANCE_GATE_DATA=$DATA
PY=${PY:-python}
mkdir -p "$DATA/clips/pos" "$DATA/clips/neg" "$DATA/clips/amb"
cd "$DATA/clips"

[ -s "$DATA/jobs.txt" ] || { echo "put lesson job ids in $DATA/jobs.txt first"; exit 1; }
while read -r j role; do
  [ -n "$j" ] || continue
  [ -s pos/$j.mp4 ] || curl -sfL -o pos/$j.mp4 "https://stepwise.sreshta-talluri.workers.dev/api/jobs/$j/video"
  if [ "$role" = walkin ] && [ ! -s neg/synth_walkin.mp4 ]; then
    ffmpeg -v error -y -i pos/$j.mp4 -t 4.4 -c:v libx264 -c:a aac neg/synth_walkin.mp4
  fi
done < "$DATA/jobs.txt"

for f in group-synced-01 solo-07 solo-02 solo-01; do
  [ -s pos/eval_$f.mp4 ] || modal volume get stepwise-eval /$f.mp4 pos/eval_$f.mp4 >/dev/null
done

$PY "$here/fetch_commons.py"
$PY "$here/relabel.py"
$PY "$here/quarantine.py"

n=0
for j in $(cut -d' ' -f1 "$DATA/jobs.txt"); do
  n=$((n + 1))
  short=$(echo "$j" | cut -c5-8)
  if [ $n -le 3 ]; then  # frozen frame at 6 s over the clip's own music
    [ -s neg/synth_still_music_$short.mp4 ] || ffmpeg -v error -y -ss 6 -i pos/$j.mp4 -t 12 \
      -vf "select=eq(n\,0),loop=400:1:0,setpts=N/30/TB" -r 30 -c:v libx264 -c:a aac -shortest neg/synth_still_music_$short.mp4
  elif [ $n -le 5 ]; then
    [ -s pos/synth_muted_$short.mp4 ] || ffmpeg -v error -y -i pos/$j.mp4 -an -c:v copy pos/synth_muted_$short.mp4
  fi
done
ls pos neg amb | grep -c mp4
