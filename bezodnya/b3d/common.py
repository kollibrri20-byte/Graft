"""Спільні "актори" і декорації для 3D-сцен."""
import json
import math
import os
import random

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Vector

from character import Character
from lib import (aim, camera, ease, emissive, lerp, lerpv, light, loft, mat, obj_from_bm, prim, set_emit, smooth,
                 snow, terrain, tube, update_tube)

DATA = os.environ.get("BEZ_DATA", "")


class Ctx:
    def __init__(self, scene_no):
        tl = json.load(open(os.path.join(DATA, "timeline.json")))
        self.sc = tl["scenes"][scene_no - 1]
        self.start = self.sc["start"]
        self.dur = self.sc["dur"]
        segs = json.load(open(os.path.join(DATA, "segments.json")))
        self.segs = [dict(s, ls=s["start"] - self.start, le=s["end"] - self.start) for s in segs if s["scene"] == scene_no]
        self.lips = json.load(open(os.path.join(DATA, "lips.json")))
        self.no = scene_no

    def seg(self, i):
        return self.segs[i]["ls"]

    def seg_end(self, i):
        return self.segs[i]["le"]

    def lip(self, t_local):
        i = int(round((self.start + t_local) * 24))
        L = self.lips
        i = max(0, min(i, len(L["open"]) - 1))
        return L["open"][i], L["wide"][i], L["round"][i]

    def mood(self, t_local):
        m = "calm"
        for s in self.segs:
            if s["ls"] - 0.3 <= t_local:
                m = s["mood"]
        return m


# ---------------------------------------------------------------- ведучий у кабіні батискафа
class Cockpit:
    """Ведучий у тісній кабіні: ілюмінатор за плечем, монітори, тепле світло екранів."""

    def __init__(self, ctx, origin=(100, 0, 0), water=(0.02, 0.12, 0.2), darkness=0.0, cam_side=1):
        self.ctx = ctx
        o = Vector(origin)
        self.o = o
        self.host = Character("Host", loc=o)
        hull = mat("hull", (0.11, 0.12, 0.13), 0.55, metal=0.6, noise=0.4, noise_scale=2, bump=0.03)
        # стіни — внутрішня поверхня сфери
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.25)
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        w = obj_from_bm("hullwall", bm, hull, True)
        w.location = o + Vector((0, 0.35, 0.2))
        # ребра жорсткості
        for a in (-0.6, 0.0, 0.6):
            r = prim("torus", o + Vector((0, 0.35, 0.2)), (1, 1, 1), rot=(0, math.pi / 2, a), material=hull,
                     major_radius=1.2, minor_radius=0.03)
        # ілюмінатор позаду праворуч
        pc = o + Vector((0.42 * cam_side, 0.95, 0.5))
        ring = prim("torus", pc, (1, 1, 1), rot=(math.pi / 2 - 0.25, 0, 0.35 * cam_side),
                    material=mat("brass", (0.5, 0.38, 0.2), 0.3, metal=1.0), major_radius=0.2, minor_radius=0.035)
        self.glass_m = emissive("portglass", water, 1.6 * (1 - darkness) + 0.05)
        glass = prim("cyl", pc, (0.19, 0.19, 0.01), rot=(math.pi / 2 - 0.25, 0, 0.35 * cam_side),
                     material=self.glass_m, vertices=40)
        self.port_fish = []
        # монітори
        for k, (dx, col) in enumerate(((-0.55, (0.2, 0.9, 0.7)), (0.62, (1.0, 0.55, 0.15)))):
            mon = prim("cube", o + Vector((dx, -0.05, 0.3)), (0.16, 0.012, 0.11), rot=(0.25, 0, -dx * 0.9),
                       material=mat("monframe", (0.03, 0.03, 0.03), 0.4), smooth=False)
            scr = emissive("scr%d" % k, col, 2.5)
            s = prim("cube", o + Vector((dx * 0.995, -0.064, 0.3)), (0.145, 0.002, 0.095), rot=(0.25, 0, -dx * 0.9),
                     material=scr, smooth=False)
        # пульт і лампочки
        prim("cube", o + Vector((0, -0.32, -0.02)), (0.45, 0.12, 0.03), rot=(0.4, 0, 0),
             material=mat("desk", (0.06, 0.06, 0.07), 0.5, metal=0.4), smooth=False)
        self.leds = []
        for i in range(12):
            m = emissive("led%d" % i, [(1, 0.2, 0.1), (0.2, 1, 0.3), (1, 0.7, 0.1)][i % 3], 4)
            led = prim("sphere", o + Vector((-0.3 + i * 0.055, -0.36, 0.0)), (0.008,) * 3, material=m, segments=8,
                       ring_count=4)
            self.leds.append(m)
        # світло
        self.key = light("AREA", o + Vector((-0.55, -0.55, 0.55)), 14, (1.0, 0.78, 0.55), target=o + Vector((0, 0, 0.38)), size=0.5)
        self.fill = light("AREA", o + Vector((0.6, -0.5, 0.3)), 5, (1.0, 0.6, 0.3), target=o + Vector((0, 0, 0.38)), size=0.4)
        self.rim = light("AREA", o + Vector((0.45 * cam_side, 0.75, 0.6)), 22, (0.35, 0.65, 1.0),
                         target=o + Vector((0, 0, 0.4)), size=0.35)
        self.cam = camera(o + Vector((0.1 * cam_side, -0.95, 0.40)), o + Vector((0, 0, 0.37)), lens=42)
        self.cam.data.dof.use_dof = True
        self.cam.data.dof.focus_object = self.host.head
        self.cam.data.dof.aperture_fstop = 2.0
        self.cam0 = self.cam.location.copy()
        self.rng = random.Random(ctx.no)
        self.blinks = []
        t = 0.6
        while t < ctx.dur + 2:
            self.blinks.append(t)
            t += self.rng.uniform(2.2, 4.8)
        self.prev_open = 0.0
        self.emph = 0.0

    def update(self, t, push=0.0, look=(0.0, 0.0), extra_brow=0.0, smile=0.0):
        op, wd, rn = self.ctx.lip(t)
        mood = self.ctx.mood(t)
        # наголоси: різкий ріст відкритості -> кивок і брови
        d = max(0.0, op - self.prev_open)
        self.prev_open = op
        self.emph = max(self.emph * 0.8, d * 2.2)
        blink = 0.0
        for b in self.blinks:
            dt = t - b
            if -0.09 < dt < 0.17:
                blink = max(blink, 1 - abs(dt - 0.04) / 0.13)
        brow = 0.15 + 0.6 * self.emph + extra_brow
        brow_in = 0.0
        frown = 0.0
        if mood == "soft":
            brow_in, frown, brow = 0.5, 0.15, brow * 0.6
        elif mood == "tense":
            brow_in, brow = 0.35, brow + 0.2
        self.host.face(jaw=op * 0.95, wide=wd * 0.6 * op, round_=rn * 0.8 * op, smile=smile, frown=frown,
                       blink=min(1, blink), brow=min(1.2, brow), brow_in=brow_in, look=look)
        yaw = 0.06 * math.sin(t * 0.37) + 0.03 * math.sin(t * 1.1 + 1)
        pitch = -0.03 + 0.05 * math.sin(t * 0.53) + 0.07 * self.emph - 0.03 * op
        roll = 0.03 * math.sin(t * 0.29 + 2)
        self.host.pose_head(yaw, pitch, roll)
        self.host.root.rotation_euler = (0, 0, 0.02 * math.sin(t * 0.21))
        # камера: повільний наїзд + легке "дихання" руки оператора
        c = self.cam0.copy()
        c.y += 0.12 * push
        c.x += 0.008 * math.sin(t * 0.7)
        c.z += 0.006 * math.sin(t * 0.9 + 1)
        self.cam.location = c
        for i, m in enumerate(self.leds):
            set_emit(m, 4 if (math.sin(t * (1.3 + i * 0.37) + i) > -0.2) else 0.3)


# ---------------------------------------------------------------- середовище
def water_env(sc, col=(0.0, 0.02, 0.05), vol=(0.2, 0.5, 0.65), density=0.03):
    w = sc.world
    nt = w.node_tree
    nt.nodes["Background"].inputs[0].default_value = (*col, 1)
    for n in nt.nodes:
        if n.type == "PRINCIPLED_VOLUME":
            n.inputs["Color"].default_value = (*vol, 1)
            n.inputs["Density"].default_value = density


class Snow:
    """Морський сніг навколо камери, повільно дрейфує."""

    def __init__(self, cam_ref, n=1800, box=(10, 10, 7), strength=1.2, color=(0.7, 0.8, 0.85), size=0.012, vel=(0, 0, 0.05)):
        self.ob = snow(n, box, (0, 0, 0), size, strength, color)
        self.cam = cam_ref
        self.box = Vector(box)
        self.vel = Vector(vel)

    def update(self, t):
        c = self.cam.location
        off = self.vel * t
        # частинки "прив'язані" до світу, але обгортаються навколо камери
        p = Vector(((off.x - c.x) % self.box.x, (off.y - c.y) % self.box.y, (off.z - c.z) % self.box.z))
        self.ob.location = c + p - self.box / 2


# ---------------------------------------------------------------- апарати
def trieste(loc=(0, 0, 0), s=1.0, light_on=True, name="Tr"):
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    root.location = loc
    grey = mat("tr_grey", (0.42, 0.44, 0.45), 0.55, metal=0.3, noise=0.35, noise_scale=3, bump=0.1)
    dark = mat("tr_dark", (0.12, 0.12, 0.13), 0.5, metal=0.6, noise=0.3, noise_scale=5, bump=0.2)

    def prof(u):
        r = 1.0 * (min(1, (u / 0.12)) ** 0.5) * (min(1, ((1 - u) / 0.1)) ** 0.45)
        return (r * 1.05, r, 0)

    fl = loft(name + "float", 30, prof, 15.0, 24, grey, 1)
    fl.parent = root
    fl.location = (0, 0, 1.6)
    k = prim("cube", (0, 0, 0.7), (6.5, 0.6, 0.3), material=dark, smooth=False)
    k.parent = root
    tower = prim("cube", (0.6, 0, 2.8), (0.8, 0.45, 0.45), material=dark, smooth=False)
    tower.parent = root
    shaft = prim("cyl", (0, 0, 0.2), (0.3, 0.3, 0.6), material=dark, vertices=20)
    shaft.parent = root
    sph = prim("sphere", (0, 0, -0.9), (1.08,) * 3, material=mat("tr_sphere", (0.18, 0.19, 0.2), 0.35, metal=0.8, noise=0.3, noise_scale=8, bump=0.2))
    sph.parent = root
    win = prim("cyl", (0, -1.04, -0.9), (0.12, 0.12, 0.06), rot=(math.pi / 2, 0, 0),
               material=mat("tr_win", (0.05, 0.1, 0.12), 0.05, metal=0.0), vertices=20)
    win.parent = root
    lights = []
    for sx in (-1.6, 1.6):
        bulb = prim("sphere", (sx, -0.6, 0.45), (0.12,) * 3, material=emissive("trbulb", (1, 0.95, 0.8), 30 if light_on else 0))
        bulb.parent = root
        L = light("SPOT", (0, 0, 0), 900 if light_on else 0, (1, 0.93, 0.8), spot=32, blend=0.6, size=0.1)
        L.parent = root
        L.location = (sx, -0.7, 0.4)
        L.rotation_euler = (math.radians(160), 0, 0)
        lights.append(L)
    root.scale = (s, s, s)
    return root, lights


def sub_white(loc=(0, 0, 0), s=1.0, name="Sub", lights_on=1.0):
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    root.location = loc
    white = mat("sub_white", (0.85, 0.86, 0.87), 0.3, coat=0.5, noise=0.08, noise_scale=4)
    orange = mat("sub_orange", (0.8, 0.25, 0.03), 0.4)

    def prof(u):
        r = (math.sin(math.pi * min(1, u * 1.1)) ** 0.6) * 0.9 + 0.05
        return (r * 0.8, r * 0.75, 0)

    body = loft(name + "b", 24, prof, 4.2, 24, white, 1)
    body.parent = root
    skid = prim("cube", (0, 0, -0.75), (1.8, 0.65, 0.12), material=orange, smooth=False)
    skid.parent = root
    dome = prim("sphere", (1.75, 0, 0.0), (0.42, 0.55, 0.5), material=mat("dome", (0.02, 0.05, 0.07), 0.05, coat=1))
    dome.parent = root
    for sy in (-0.75, 0.75):
        th = prim("cyl", (-1.9, sy, 0.1), (0.18, 0.18, 0.3), rot=(0, math.pi / 2, 0), material=orange, vertices=16)
        th.parent = root
    lights = []
    bmat = bpy.data.materials.get("subbulb") or emissive("subbulb", (1, 0.97, 0.9), 40 * lights_on)
    for sy in (-0.45, 0.45):
        b = prim("sphere", (2.0, sy, -0.45), (0.08,) * 3, material=bmat)
        b.parent = root
        L = light("SPOT", (0, 0, 0), 1500 * lights_on, (1, 0.96, 0.9), spot=40, blend=0.5, size=0.1)
        L.parent = root
        L.location = (2.1, sy, -0.45)
        L.rotation_euler = (0, math.radians(-115), 0)
        lights.append(L)
    root.scale = (s, s, s)
    return root, lights


def fish(name, loc, L=0.3, color=(0.6, 0.6, 0.65), depth=0.32, metal=0.4, eye=True, emit=None):
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    root.location = loc
    m = mat(name + "m", color, 0.3, metal=metal, noise=0.2, noise_scale=20) if emit is None else \
        mat(name + "m", color, 0.3, metal=metal, emit=emit, emit_str=1.5)

    def prof(u):
        r = math.sin(math.pi * min(1, (u + 0.02) ** 0.75)) * 0.5
        return (r * 0.35, r * depth * 2, 0)

    b = loft(name + "b", 16, prof, L, 12, m, 1)
    b.parent = root
    tail_piv = bpy.data.objects.new(name + "tp", None)
    bpy.context.scene.collection.objects.link(tail_piv)
    tail_piv.parent = root
    tail_piv.location = (-L * 0.45, 0, 0)
    tail = prim("cone", (-L * 0.1, 0, 0), (L * 0.18, L * 0.02, L * 0.12), rot=(0, math.pi / 2, 0), material=m, vertices=12)
    tail.parent = tail_piv
    if eye:
        for sy in (-1, 1):
            e = prim("sphere", (L * 0.33, sy * L * 0.07, L * 0.03), (L * 0.05,) * 3,
                     material=mat("fisheye", (0.02, 0.02, 0.02), 0.05, coat=1), segments=12, ring_count=6)
            e.parent = root
    return root, tail_piv


def wiggle(root, tail, t, speed=6, amp=0.4, ph=0.0):
    tail.rotation_euler = (0, 0, amp * math.sin(t * speed + ph))


def seabed(material=None, size=80, amp=0.35, seed=2, loc=(0, 0, 0), res=150, ridge=None):
    m = material or mat("sand", (0.32, 0.29, 0.24), 0.95, noise=0.5, noise_scale=3, bump=0.4)
    return terrain("bed", size, res, amp, seed, m, 5.0, loc, ridge)
