#!/usr/bin/env bash
# Збирає 3D-кадри (12 fps) у фінальне відео 1920x1080 24 fps з субтитрами, глибиноміром і звуком.
# ./assemble3d.sh R3D_DIR DATA_DIR OUT.mp4
set -euo pipefail
R=$1; D=$2; OUT=$3
SEQ=$R/seq; rm -rf "$SEQ"; mkdir -p "$SEQ"
n=0
for k in $(seq -w 1 32); do
  for f in "$R"/s$k/f_*.jpg; do
    n=$((n+1)); ln -s "$f" "$SEQ/$(printf %06d $n).jpg"
  done
done
echo "frames: $n"
VF="scale=1920:1080:flags=lanczos,unsharp=5:5:0.5,fps=24,noise=alls=4:allf=t,vignette=angle=PI/5,fade=t=in:st=0:d=1.2,ass=$D/overlay.ass"
ffmpeg -y -loglevel error -framerate 12 -i "$SEQ/%06d.jpg" -vf "$VF" -c:v libx264 -preset slow \
  -b:v 1500k -maxrate 3500k -bufsize 7000k -pass 1 -passlogfile "$R/x264" -an -f mp4 /dev/null
ffmpeg -y -loglevel error -framerate 12 -i "$SEQ/%06d.jpg" -i "$D/mix.wav" -vf "$VF" -c:v libx264 -preset slow \
  -b:v 1500k -maxrate 3500k -bufsize 7000k -pass 2 -passlogfile "$R/x264" -pix_fmt yuv420p \
  -c:a aac -b:a 192k -shortest -movflags +faststart "$OUT"
# Фінальна заставка (лайк / підписка / дзвоник) у кінці
if [ -f "$D/../endcard/endcard.mp4" ] || [ -n "${ENDCARD:-}" ]; then
  EC=${ENDCARD:-$D/../endcard/endcard.mp4}
  printf "file '%s'\nfile '%s'\n" "$OUT" "$EC" > "$R/endlist.txt"
  ffmpeg -y -loglevel error -f concat -safe 0 -i "$R/endlist.txt" -c copy -movflags +faststart "${OUT%.mp4}_end.mp4"
  mv "${OUT%.mp4}_end.mp4" "$OUT"
fi
