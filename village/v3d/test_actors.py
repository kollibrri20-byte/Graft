import math, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from lib import *
from actors import Actor, scan_head

OUT = sys.argv[1]
sc = new_scene((960, 540), samples=int(os.environ.get("S","32")))
mats = M()
world(sky=(0.012, 0.018, 0.035), fog=0.0)
sun((math.radians(55), 0, math.radians(200)), 0.8, color=(0.5, 0.65, 1.0))
terrain(200, 0.8, 0.6, mats["ground"], subdiv=6)
hut(mats, (0, 8, 0), 0, lit=True, door_open=False, shutters=True)
a = Actor(mats, "andriy", "andr")
a.path([(1.5, -2, 0), (0.6, 4.2, 0)], 1, 30)
a.play("Walk", 1, 30)
h = Actor(mats, "hanna", "hanna")
h.place((-1.2, 5.0, 0.0), 180)
h.play("idle", 1, 30)
v = Actor(mats, "man", "vil")
v.place((-3.0, 5.0, 0), 160)
v.play("Idle", 1, 30, offset=10)
sc.eevee.volumetric_tile_size = os.environ.get("TILE","2")
setp(sc.eevee, "volumetric_samples", int(os.environ.get("VS","64")))
for o in bpy.data.objects:
    if o.type == "LIGHT" and o.data.type == "POINT": o.data.energy *= 0.6

distance_fog(0.07, (0.02, 0.03, 0.055))
cam = camera(lens=35)
cam_move(cam, 1, 30, (4.5, -1.5, 1.5), (4.0, -0.5, 1.5), (0.5, 4.5, 1.2), (0.4, 5.0, 1.3))
sc.frame_set(20)
sc.render.filepath = OUT + "_a.png"
t = time.time(); bpy.ops.render.render(write_still=True); print("frame", round(time.time() - t, 1))
