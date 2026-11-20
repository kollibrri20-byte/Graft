#!/usr/bin/env python3
"""Рендер 3D-шотів: python3 render.py 1 2 3 [--still] [--res 960x540] [--samples 16]

Кадри → ../out3d/NNN/0001.png …  Готові шоти (з файлом DONE) пропускаються.
"""
import argparse
import inspect
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import bpy  # noqa: E402
import lib  # noqa: E402
import shots  # noqa: E402
from assemble import estimate_without_voice, load_shots  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "out3d")
TAIL = 8  # запас кадрів на перехресні переходи


def durations():
    sh = load_shots(os.path.join(os.path.dirname(HERE), "shots.txt"))
    st, en, _ = estimate_without_voice(sh)
    st[0] = 0.0
    return {s["num"]: e - a for s, a, e in zip(sh, st, en)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nums", nargs="+", type=int)
    ap.add_argument("--still", action="store_true")
    ap.add_argument("--res", default="960x540")
    ap.add_argument("--samples", type=int, default=8)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    res = tuple(int(x) for x in a.res.split("x"))
    D = durations()
    for n in a.nums:
        d = os.path.join(OUT, f"{n:03d}")
        if not a.still and not a.force and os.path.exists(os.path.join(d, "DONE")):
            print(f"[{n:03d}] вже готовий")
            continue
        F = int(round(D[n] * lib.FPS)) + TAIL
        t0 = time.time()
        sc = lib.new_scene(res, a.samples)
        mats = lib.M()
        tm = shots.TM()
        mats.update(wall=tm["plaster"], thatch=tm["thatch"], ground=tm["mud"], road=tm["track"],
                    wood=tm["planks"], grass=tm["forest"], floor=tm["floor"], plaster_in=tm["plaster_old"])
        fn = shots.SHOTS[n]
        kw = {"n": n} if "n" in inspect.signature(fn).parameters else {}
        fn(mats, F, **kw)
        sc.frame_start, sc.frame_end = 1, F
        os.makedirs(d, exist_ok=True)
        if a.still:
            sc.frame_set(F // 2)
            sc.render.filepath = os.path.join(OUT, "stills", f"{n:03d}.png")
            bpy.ops.render.render(write_still=True)
        else:
            sc.render.filepath = os.path.join(d, "")
            bpy.ops.render.render(animation=True)
            open(os.path.join(d, "DONE"), "w").write(f"{F}\n")
        print(f"[{n:03d}] {F} кадрів, {time.time() - t0:.0f} с", flush=True)
        lib._MATS.clear()
        lib._PINE.clear()
        import assets
        assets._TEX.clear()


if __name__ == "__main__":
    main()
