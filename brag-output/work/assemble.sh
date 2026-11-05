#!/usr/bin/env bash
# Assemble the rendered PNG frames + music into brag.mp4, then bake a poster
# frame as frame 0 so platform thumbnails show a settled frame.
set -e
cd "$(dirname "$0")"

FRAMES="frames"
OUT="../brag.mp4"
POSTER="../brag.jpg"

# 1) frames -> h264 mp4 with the music bed (shortest stops at 20s)
ffmpeg -y -framerate 30 -i "$FRAMES/frame_%04d.png" -i music.wav \
  -c:v libx264 -pix_fmt yuv420p -crf 18 -preset medium \
  -c:a aac -b:a 192k -shortest -movflags +faststart "$OUT"

# 2) poster: a settled frame from the verdict scene (~16.5s -> frame 495)
cp "$FRAMES/frame_0495.png" poster_src.png
ffmpeg -y -i poster_src.png -q:v 2 "$POSTER"

echo "DONE_ASSEMBLE"
ls -la "$OUT" "$POSTER"
