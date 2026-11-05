#!/usr/bin/env bash
# Mux the frame sequence with a ducked music bed + per-scene English voiceover.
set -e
cd "$(dirname "$0")"

# VO start offsets in ms (match the scene timings; chained to avoid overlap).
DELAYS=(250 4250 7750 12250 18750 24250 30750 35500 40250 46700)

INPUTS=(-framerate 30 -i frames/frame_%04d.png -i music.wav)
for i in $(seq -w 1 10); do INPUTS+=(-i "vo/vo_${i}.wav"); done

# Build the audio filter: music ducked, each VO delayed + upmixed to stereo.
FILTER="[1:a]volume=0.30[m];"
MIX="[m]"
idx=2
for d in "${DELAYS[@]}"; do
  FILTER+="[${idx}:a]adelay=${d}:all=1,aformat=channel_layouts=stereo,volume=1.25[a${idx}];"
  MIX+="[a${idx}]"
  idx=$((idx+1))
done
FILTER+="${MIX}amix=inputs=11:normalize=0:dropout_transition=0[mixed];[mixed]alimiter=limit=0.95[aout]"

ffmpeg -y "${INPUTS[@]}" \
  -filter_complex "$FILTER" \
  -map 0:v -map "[aout]" \
  -c:v libx264 -pix_fmt yuv420p -crf 18 -preset medium \
  -c:a aac -b:a 192k -t 52 -movflags +faststart ../brag.mp4

cp frames/frame_0495.png poster_src.png
ffmpeg -y -i poster_src.png -q:v 2 ../brag.jpg
echo "DONE_VO_ASSEMBLE"
