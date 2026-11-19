"""Рендер 32 сцен у mp4 (960x540, 24 fps; фінальне масштабування до 1080p робить ffmpeg).

    python render_video.py TIMELINE.json OUT_DIR [--workers 4]
    python render_video.py TIMELINE.json OUT_DIR --preview   # по 2 PNG-кадри з кожної сцени
"""
import json
import os
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image

from gfx import H, W, to_u8
from scenes import SCENE_CLASSES

FPS = 24
EDGE_FADE = 0.35  # с: короткий перехід через темряву між сценами


def render_scene(args):
    idx, dur, out_dir = args
    path = os.path.join(out_dir, f"scene_{idx + 1:02d}.mp4")
    if os.path.exists(path):
        return path
    sc = SCENE_CLASSES[idx](dur)
    n = int(round(dur * FPS))
    tmp = path + ".part.mp4"
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "14",
         "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for f in range(n):
        t = f / FPS
        img = sc.frame(t)
        k = min(1.0, t / EDGE_FADE, (dur - t) / EDGE_FADE)
        if idx in (0,):  # перша сцена виходить із темряви повільніше
            k = min(k, t / 1.2)
        img = img * max(k, 0)
        proc.stdin.write(to_u8(img).tobytes())
    proc.stdin.close()
    proc.wait()
    os.replace(tmp, path)
    print(f"scene {idx + 1:02d} done ({n} frames)", flush=True)
    return path


def main():
    tl = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    durs = [s["dur"] for s in tl["scenes"]]
    if "--preview" in sys.argv:
        only = None
        for a in sys.argv:
            if a.startswith("--only="):
                only = {int(x) for x in a[7:].split(",")}
        for i, d in enumerate(durs):
            if only and i + 1 not in only:
                continue
            sc = SCENE_CLASSES[i](d)
            for u in (0.3, 0.8):
                img = to_u8(sc.frame(d * u))
                Image.fromarray(img).save(os.path.join(out, f"p{i + 1:02d}_{int(u * 100)}.png"))
            print("preview", i + 1, flush=True)
        return
    workers = 4
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    # довгі сцени першими — краще навантаження
    jobs = sorted([(i, d, out) for i, d in enumerate(durs)], key=lambda j: -j[1])
    with Pool(workers) as p:
        list(p.imap_unordered(render_scene, jobs))
    with open(os.path.join(out, "list.txt"), "w") as f:
        for i in range(len(durs)):
            f.write(f"file 'scene_{i + 1:02d}.mp4'\n")


if __name__ == "__main__":
    main()
