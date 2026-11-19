#!/usr/bin/env bash
# Зведення: 32 сцени + субтитри/глибиномір (ASS) + звук -> bezodnya_16x9.mp4 (1920x1080, 24 fps)
# Використання: ./make_final.sh RENDER_DIR OUT_DIR RESULT.mp4
# Двопрохідне кодування ~1.4 Мбіт/с, щоб файл був < 100 МБ (ліміт GitHub).
set -euo pipefail
R=$1; O=$2; RES=$3
VF="scale=1920:1080:flags=lanczos,noise=alls=5:allf=t,ass=$O/overlay.ass"
ffmpeg -y -loglevel error -i "$O/mix_raw.wav" -af "loudnorm=I=-14:TP=-1.5:LRA=11" -ar 48000 "$O/mix.wav"
ffmpeg -y -loglevel error -f concat -safe 0 -i "$R/list.txt" -vf "$VF" -c:v libx264 -preset slow \
  -b:v 1400k -maxrate 3000k -bufsize 6000k -pass 1 -passlogfile "$O/x264" -an -f mp4 /dev/null
ffmpeg -y -loglevel error -f concat -safe 0 -i "$R/list.txt" -i "$O/mix.wav" -vf "$VF" -c:v libx264 -preset slow \
  -b:v 1400k -maxrate 3000k -bufsize 6000k -pass 2 -passlogfile "$O/x264" -pix_fmt yuv420p \
  -c:a aac -b:a 192k -shortest -movflags +faststart "$RES"
