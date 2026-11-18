#!/bin/bash
# Render the frames still missing in [a,b] in chunks of 40 (fresh Blender each chunk keeps memory flat).
cd "$(dirname "$0")/.."
a=$1; b=$2
while true; do
  s=""; for i in $(seq $a $b); do [ -f frames/f$(printf %04d $i).png ] || { s=$i; break; }; done
  [ -z "$s" ] && break
  e=$((s+39)); [ $e -gt $b ] && e=$b
  SCALE=50 SAMPLES=7 tools/blender --background --python build.py -- . frames:$s:$e > logs/m_$s.log 2>&1 || sleep 5
done
echo "range $a-$b done"
