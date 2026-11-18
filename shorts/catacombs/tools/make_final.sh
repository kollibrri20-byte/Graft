#!/bin/bash
# frames/ (mixed 720p/540p PNGs) -> render.mp4 1080x1920 -> final.mp4 with voice, captions, sfx, music
set -e
cd "$(dirname "$0")/.."
S=/root/.claude/plugins/synced/dcc9393f-9130-4ab2-a111-4ba3d42d6ba0_d7df1b23-90d5-4b6b-8e75-416b519a8c9e/kylo-3d-shorts/skills/3d-short/scripts
ffmpeg -v error -y -framerate 30 -i frames/f%04d.png -vf "scale=540:960:flags=lanczos,scale=1080:1920:flags=lanczos,unsharp=5:5:0.6" -c:v libx264 -crf 17 -preset medium -pix_fmt yuv420p render.mp4
uv run -q --with pillow --with numpy python $S/assemble.py --video render.mp4 --voice voice.wav --words words.json \
  --sfx render.sfx.json --music music.wav --music-db -16 --out final.mp4
ffprobe -v error -show_entries format=duration:stream=width,height -of compact final.mp4
