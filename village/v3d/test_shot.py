import math, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from lib import *

OUT = sys.argv[1]
sc = new_scene((960, 540), samples=int(os.environ.get("SAMPLES", "12")))
mats = M()
world(sky=(0.008, 0.014, 0.03), fog=0.022, fog_col=(0.6, 0.7, 0.9))
sun((math.radians(60), 0, math.radians(160)), 1.2)
terrain(300, 1.2, 0.6, mats["ground"], subdiv=6)
road_strip([(0, -10), (0, 20), (0.5, 50), (1, 90)], 5.5, mats["road"])
for i in range(5):
    y = 6 + i * 11
    hut(mats, (-9.5, y, 0), math.radians(90), lit=True, door_open=(i < 3), shutters=(i == 1))
    hut(mats, (9.5, y + 5, 0), math.radians(-90), lit=True, door_open=(i < 3))
    lantern_pole(mats, (-4.0 if i % 2 else 3.8, y + 2, 0), shadow=(i == 0))
forest(mats, (-80, 80, 70, 140), 160, seed=3)
church(mats, (4, 80, 0), 1.0)
# жителі біля дверей
vill = []
for i, (x, y, k) in enumerate([(-6.0, 6, "woman"), (-6.0, 17, "old"), (6.2, 11, "man"), (6.2, 22, "woman"), (-5.5, 28, "child")]):
    p = Person(mats, k, f"v{i}", 1.8 if k != "child" else 1.25)
    p.place((x, y, 0), 90 if x < 0 else -90)
    vill.append(p)
a = Person(mats, "andriy", "andr", 1.8)
F0, F1 = 1, 36
walk_path(a, [(0.3, 2, 0), (0.3, 9, 0)], F0, F1, gait="walk")
for i, p in enumerate(vill):
    stand(p, F0, F1, look=(0, 0))
cam = camera(lens=32)
cam_move(cam, F0, F1, (2.6, 1.0, 1.5), (2.2, 4.0, 1.6), (0.3, 7, 1.3), (0.3, 10, 1.4), shake=0.01)
for f in (18,):
    sc.frame_set(f)
    sc.render.filepath = OUT + f"_{f:02d}.png"
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print("frame", f, round(time.time() - t, 1))
