"""Рендер однієї 3D-сцени: python run_scene.py K OUT_DIR [--preview] [--samples N]
Кадри: OUT_DIR/sKK/f_00000.jpg (12 fps)."""
import importlib
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402

import lib  # noqa: E402
from common import Ctx  # noqa: E402

k = int(sys.argv[1])
out = sys.argv[2]
preview = "--preview" in sys.argv
samples = int(sys.argv[sys.argv.index("--samples") + 1]) if "--samples" in sys.argv else 6
mod = importlib.import_module("scenes3d")
ctx = Ctx(k)
fn = getattr(mod, f"scene_{k}")
update = fn(ctx)
bpy.context.scene.eevee.taa_render_samples = samples
n = int(round(ctx.dur * lib.FPS))
d = os.path.join(out, f"s{k:02d}")
os.makedirs(d, exist_ok=True)
if preview:
    for u in (0.15, 0.5, 0.85):
        f = int(n * u)
        update(f / lib.FPS)
        bpy.context.scene.frame_set(f)
        bpy.context.scene.render.filepath = os.path.join(out, f"prev_{k:02d}_{int(u * 100)}.jpg")
        bpy.ops.render.render(write_still=True)
else:
    lib.render_range(d, "f", n, update)
    open(os.path.join(d, "DONE"), "w").write(str(n))
