#!/bin/bash
# odd frames (12 fps) -> motion-interpolated 24 fps -> 1080x1920 -> sound, captions -> final.mp4
set -e
cd "$(dirname "$0")"
S=/root/.claude/plugins/synced/dcc9393f-9130-4ab2-a111-4ba3d42d6ba0_d7df1b23-90d5-4b6b-8e75-416b519a8c9e/kylo-3d-shorts/skills/3d-short/scripts
T=$(mktemp -d)
END=${END:-1243}
k=1
for i in $(seq 1 2 $END); do ln -s "$PWD/frames_half/f$(printf %04d $i).png" "$T/o$(printf %04d $k).png"; k=$((k+1)); done
ffmpeg -v error -y -framerate 12 -i "$T/o%04d.png" \
  -vf "minterpolate=fps=24:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,scale=1080:1920:flags=lanczos,unsharp=5:5:0.6" \
  -c:v libx264 -crf 16 -preset medium -pix_fmt yuv420p render.mp4
uv run -q --with pillow --with numpy python $S/assemble.py --video render.mp4 --voice voice.wav --words words.json \
  --sfx render.sfx.json --sfx-lib sfx --music music.wav --music-db -16 --style explainer --out final.mp4
