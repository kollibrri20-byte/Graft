#!/usr/bin/env python3
"""Збирає відрендерені 3D-шоти (out3d/NNN/*.png, 15 fps) у фільм 1920×1080, 30 fps.

    python3 post.py 1 26            # шоти 1..26 → out/selo3d_001-026.mp4
    python3 post.py 1 26 --scale 0.5

Ефекти: світіння вогнів (bloom), віньєтка, плівкове зерно, перехресні переходи,
затемнення перед розділами, тихий ембієнт (вітер + низький гул) з assemble.py.
"""
import argparse
import os
import subprocess
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from assemble import ambient, estimate_without_voice, load_shots  # noqa: E402

SRC_FPS = 15
FPS = 30
XF = 0.45
DIP = 1.1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("first", type=int)
    ap.add_argument("last", type=int)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    shots = load_shots(os.path.join(ROOT, "shots.txt"))
    st, en, _ = estimate_without_voice(shots)
    st[0] = 0.0
    nums = list(range(a.first, a.last + 1))
    t0 = st[a.first - 1]
    starts = [st[n - 1] - t0 for n in nums]
    ends = [en[n - 1] - t0 for n in nums]
    total = ends[-1] + 0.8
    W, H = int(1920 * a.scale) // 2 * 2, int(1080 * a.scale) // 2 * 2
    out = a.out or os.path.join(ROOT, "out", f"selo3d_{a.first:03d}-{a.last:03d}.mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmpv = out + ".video.mp4"
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                             "-crf", "19", "-pix_fmt", "yuv420p", tmpv], stdin=subprocess.PIPE)
    cache = {}

    def frame(i, t):
        n = nums[i]
        d = os.path.join(ROOT, "out3d", f"{n:03d}")
        files = cache.get(n)
        if files is None:
            files = sorted(f for f in os.listdir(d) if f.endswith(".png")) if os.path.isdir(d) else []
            cache[n] = files
        if not files:
            return np.zeros((H, W, 3), np.float32)
        lead = (DIP if shots[n - 1]["chapter"] else XF) / 2 if i else 0.0
        k = int((t - starts[i] + lead) * SRC_FPS)
        k = min(max(k, 0), len(files) - 1)
        key = (n, k)
        if key in cache:
            return cache[key]
        im = cv2.imread(os.path.join(d, files[k]), cv2.IMREAD_COLOR)[:, :, ::-1]
        im = cv2.resize(im, (W, H), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
        cache[key] = im
        if len(cache) > 40:
            for kk in [x for x in cache if isinstance(x, tuple)][:20]:
                cache.pop(kk)
        return im

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    vign = (1 - 0.38 * np.clip(r - 0.5, 0, None) ** 1.6)[:, :, None]
    rng = np.random.default_rng(3)
    grain = [rng.normal(0, 0.012, (H, W, 1)).astype(np.float32) for _ in range(6)]
    nf = int(total * FPS)
    for fi in range(nf):
        t = fi / FPS
        i = max(j for j in range(len(nums)) if starts[j] - 1e-9 <= t or j == 0)
        img = frame(i, t)
        # перехід у наступний шот
        if i + 1 < len(nums):
            nxt = nums[i + 1]
            x = DIP if shots[nxt - 1]["chapter"] else XF
            b = starts[i + 1]
            if t > b - x / 2:
                w = min(max((t - (b - x / 2)) / x, 0), 1)
                if shots[nxt - 1]["chapter"]:
                    img = img * (1 - w * 2) ** 2 if w < 0.5 else frame(i + 1, t) * ((w - 0.5) * 2) ** 1.5
                else:
                    w = w * w * (3 - 2 * w)
                    img = img * (1 - w) + frame(i + 1, t) * w
        # bloom
        br = np.clip(img - 0.7, 0, None)
        img = img + cv2.GaussianBlur(br, (0, 0), 12 * a.scale + 1) * 0.6 + cv2.GaussianBlur(br, (0, 0), 40 * a.scale + 1) * 0.5
        g = 1.0
        if t < 1.0:
            g = t ** 1.5
        if t > total - 1.2:
            g = min(g, max(total - t, 0) / 1.2) ** 1.5
        img = img * vign * g + grain[fi % 6]
        proc.stdin.write((np.clip(img, 0, 1) * 255).astype(np.uint8).tobytes())
        if fi % 150 == 0:
            print(f"  {fi}/{nf}", flush=True)
    proc.stdin.close()
    proc.wait()
    amb = out + ".amb.wav"
    ambient(total, [starts[i] for i, n in enumerate(nums) if shots[n - 1]["chapter"]], amb)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmpv, "-i", amb, "-filter_complex",
                    "[1:a]volume=-12dB[a]", "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)
    os.remove(tmpv)
    os.remove(amb)
    print("готово:", out)


if __name__ == "__main__":
    main()
