import math, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector
import lib
from lib import *
from assets import *

which = sys.argv[1]
OUT = sys.argv[2]
sc = new_scene((960, 540), samples=16)
mats = M()
tm = TM()
mats.update(wall=tm["plaster"], thatch=tm["thatch"], ground=tm["mud"], road=tm["track"], wood=tm["planks"])
if which == "forest":
    hdri_world("moonlit_golf", 0.5, tint=(0.7, 0.8, 1.0))
    sun((math.radians(55), 0, math.radians(200)), 1.5, color=(0.6, 0.72, 1.0))
    terrain(300, 1.5, 0.5, tm["forest"], subdiv=6, loc=(0, 0, -1.0))
    road_strip([(0.3 * math.sin(y / 9), y) for y in range(-20, 120, 2)], 1.8, tm["leaves"], z=0.05)
    forest(mats, (-60, 60, -10, 160), 500, 14, 26, avoid=lambda x, y: abs(x) < 3.5, seed=4)
    a = Human("marvin", "andr", 1.8, tint=(0.55, 0.75, 0.4))
    a.path([(0, 0, 0.05), (0.2, 6, 0.05)], 1, 36)
    a.play("walk", 1, 36)
    hl = spot_light((0.3, 0.45, 1.25), (math.radians(-80), 0, 0), 800, size_deg=26)
    hl.parent = a.root
    hl.location = Vector((0.3, 0.45, 1.25)) / a.k - Vector((0, 0, a.zoff))
    hl.rotation_euler = (math.radians(80), 0, 0)
    beam((0.3, 0.6, 1.25), (0.4, 14, 0.3), 2.0, k=0.8).parent = None
    cam = camera(lens=35)
    cam_move(cam, 1, 36, (0.6, -3.0, 1.6), (0.6, 2.0, 1.65), (0.1, 6, 1.3), (0.2, 12, 1.4))
    distance_fog(0.05, (0.08, 0.1, 0.15))
    f = 20
else:
    hdri_world("moonlit_golf", 0.5, tint=(0.7, 0.8, 1.0))
    sun((math.radians(55), 0, math.radians(200)), 1.2, color=(0.6, 0.72, 1.0))
    terrain(300, 0.6, 0.6, tm["mud"], subdiv=6, loc=(0, 0, -0.35))
    hut(mats, (0, 4.0, 0), 0, lit=True, door_open=True, shutters=True)
    hn = Hanna((-0.05, 1.05, 0.0), 180)
    v = Human("marvin", "vil", 1.76, tint=(0.75, 0.6, 0.45))
    v.place((-3.2, 0.6, 0), 200)
    v.play("idle", 1, 30, offset=20)
    a = Human("marvin", "andr", 1.8, tint=(0.55, 0.75, 0.4))
    a.path([(2.5, -4, 0), (1.0, -0.6, 0)], 1, 30)
    a.play("walk", 1, 30)
    forest(mats, (-80, 80, 14, 120), 200, 14, 24, seed=2)
    cam = camera(lens=35)
    cam_move(cam, 1, 30, (3.8, -5.2, 1.6), (3.4, -4.6, 1.6), (-0.5, 1.5, 1.3), (-0.5, 1.6, 1.35))
    distance_fog(0.04, (0.08, 0.1, 0.15))
    f = 22
sc.frame_set(f)
sc.render.filepath = OUT
t = time.time(); bpy.ops.render.render(write_still=True); print("frame", round(time.time() - t, 1))
