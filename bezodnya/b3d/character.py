"""Стилізований 3D-персонаж (голова з відкритим ротом, повіки, брови, волосся, тулуб) з
шейп-кі для лікпсинку: open / wide / round / smile / frown.

Голова дивиться в -Y. Одиниці — метри (голова ~0.24 м заввишки).
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

from lib import mat, obj_from_bm, prim, tube

R = 0.105  # базовий радіус голови


def _head_shape(v):
    x, y, z = v
    # видовжити, звузити підборіддя, сплощити потилицю
    z2 = z * 1.18
    k = 1.0
    if z < 0:
        k = 1 - 0.30 * (-z / R) ** 1.6       # підборіддя вужче
    x2 = x * 0.86 * k
    y2 = y * (0.95 if y < 0 else 0.98) * (k * 0.5 + 0.5)
    # щоки трохи вперед, очні западини
    if y < 0:
        ez = z - 0.18 * R
        for sx in (-1, 1):
            d = ((x - sx * 0.36 * R) ** 2 + ez ** 2) / (0.22 * R) ** 2
            y2 += 0.10 * R * math.exp(-d)  # западина
        y2 -= 0.06 * R * math.exp(-((z + 0.35 * R) ** 2 + x ** 2) / (0.35 * R) ** 2)  # губи/рот вперед
    return Vector((x2, y2, z2))


class Character:
    def __init__(self, name="Host", skin=(0.56, 0.30, 0.19), hair=(0.035, 0.022, 0.015), shirt=(0.05, 0.09, 0.2),
                 shirt2=(0.75, 0.22, 0.03), eyes=(0.25, 0.45, 0.55), loc=(0, 0, 0), headset=True,
                 hair_style="short", beard=False, collar=True):
        self.name = name
        self.root = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(self.root)
        self.root.location = loc
        self.m_skin = mat(name + "skin", skin, 0.48, sss=0.08, noise=0.12, noise_scale=60, bump=0.05)
        self.m_lip = mat(name + "lip", (skin[0] * 0.85, skin[1] * 0.45, skin[2] * 0.45), 0.4, sss=0.2)
        self.m_hair = mat(name + "hair", hair, 0.55, noise=0.4, noise_scale=120, bump=0.3)
        self.m_shirt = mat(name + "shirt", shirt, 0.7, noise=0.1, noise_scale=40, bump=0.08)
        self.m_shirt2 = mat(name + "shirt2", shirt2, 0.7, noise=0.1, noise_scale=40, bump=0.08)
        self.m_white = mat(name + "eyewhite", (0.92, 0.9, 0.88), 0.15)
        self.m_iris = mat(name + "iris", eyes, 0.2, noise=0.5, noise_scale=300)
        self.m_dark = mat(name + "pupil", (0.01, 0.01, 0.01), 0.1)
        self.m_mouth = mat(name + "mouthin", (0.18, 0.04, 0.05), 0.6)
        self.m_teeth = mat(name + "teeth", (0.9, 0.88, 0.82), 0.25)
        self.m_tongue = mat(name + "tongue", (0.55, 0.18, 0.18), 0.5, sss=0.2)
        self._body(shirt, collar)
        self.head_pivot = bpy.data.objects.new(name + "_headpivot", None)
        bpy.context.scene.collection.objects.link(self.head_pivot)
        self.head_pivot.parent = self.root
        self.head_pivot.location = (0, 0, 0.245)  # основа шиї
        self._head()
        self._eyes()
        self._hair(hair_style, beard)
        if headset:
            self._headset()
        self.blink_v = 0.0

    # ---------------------------------------------------------- тулуб
    def _body(self, shirt, collar):
        def prof(u):
            # u: 0 — плечі (верх), 1 — низ грудей; loft іде вздовж X, повернемо вертикально
            w = 0.21 - 0.03 * u + 0.02 * math.sin(u * 3.14)
            d = 0.11 + 0.01 * math.sin(u * 3.14)
            return (w, d, 0)

        from lib import loft
        torso = loft(self.name + "_torso", 10, prof, 0.42, 20, self.m_shirt, 2)
        torso.rotation_euler = (0, math.radians(90), math.radians(90))
        torso.parent = self.root
        torso.location = (0, 0.0, 0.0)
        # плечі — сфери-округлення
        for sx in (-1, 1):
            sh = prim("sphere", (sx * 0.16, 0.0, 0.165), (0.085, 0.09, 0.055), material=self.m_shirt)
            sh.parent = self.root
            arm = prim("cyl", (sx * 0.24, 0.01, -0.02), (0.065, 0.065, 0.2), material=self.m_shirt, vertices=20)
            arm.rotation_euler = (0, sx * math.radians(8), 0)
            arm.parent = self.root
        # темна вставка/комір
        band = prim("cube", (0, -0.112, 0.02), (0.2, 0.01, 0.025), material=self.m_shirt2, smooth=False)
        band.parent = self.root
        if collar:
            col = prim("torus", (0, 0, 0.215), (1, 0.9, 0.6), material=self.m_shirt2, major_radius=0.07,
                       minor_radius=0.022)
            col.parent = self.root
        neck = prim("cyl", (0, 0.005, 0.25), (0.05, 0.046, 0.06), material=self.m_skin, vertices=24)
        neck.parent = self.root
        # нашивка на грудях
        patch = prim("cyl", (0.1, -0.118, 0.1), (0.028, 0.028, 0.003), material=mat("patch", (0.9, 0.85, 0.3), 0.6),
                     rot=(math.radians(90), 0, 0), vertices=24)
        patch.parent = self.root

    # ---------------------------------------------------------- голова
    def _head(self):
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=48, radius=R)
        # повернути, щоб полюси були вгорі/внизу (вже так) — шви на потилиці
        for v in bm.verts:
            v.co = _head_shape(v.co)
        # проріз рота
        mz = -0.40 * R * 1.18
        dele = []
        for f in bm.faces:
            c = f.calc_center_median()
            if c.y < 0 and (c.x / (0.30 * R)) ** 2 + ((c.z - mz) / (0.028 * R)) ** 2 < 1:
                dele.append(f)
        bmesh.ops.delete(bm, geom=dele, context="FACES")
        # матеріали: губи
        me = bpy.data.meshes.new(self.name + "_head")
        bm.to_mesh(me)
        bm.free()
        head = bpy.data.objects.new(self.name + "_head", me)
        bpy.context.scene.collection.objects.link(head)
        me.materials.append(self.m_skin)
        me.materials.append(self.m_lip)
        for p in me.polygons:
            p.use_smooth = True
            c = p.center
            if c.y < -0.5 * R and (c.x / (0.31 * R)) ** 2 + ((c.z - mz) / (0.075 * R)) ** 2 < 1:
                p.material_index = 1
        head.parent = self.head_pivot
        head.location = (0, 0, 0.13)
        self.head = head
        self.mz = mz
        # шейп-кі
        co = np.array([v.co[:] for v in me.vertices])
        head.shape_key_add(name="Basis")

        def add_key(name, fn):
            k = head.shape_key_add(name=name, from_mix=False)
            new = np.array([fn(Vector(c)) for c in co])
            k.data.foreach_set("co", new.ravel())
            k.value = 0
            return k

        piv = Vector((0, 0.25 * R, -0.05 * R))

        def k_open(c):
            if c.z < mz + 0.005 * R and c.y < 0.55 * R:
                # нижня щелепа обертається вниз
                w = min(1, max(0, (mz + 0.02 * R - c.z) / (0.05 * R)))
                w *= min(1, max(0, (0.55 * R - c.y) / (0.4 * R)))
                ang = math.radians(16) * w
                d = c - piv
                rot = Matrix.Rotation(ang, 3, "X")
                return piv + rot @ d
            if c.z >= mz and c.y < -0.3 * R:
                w = math.exp(-((c.z - mz) / (0.07 * R)) ** 2) * math.exp(-(c.x / (0.35 * R)) ** 2)
                return c + Vector((0, 0, 0.012 * R * w))
            return c

        def k_wide(c):
            if c.y < -0.2 * R:
                w = math.exp(-((c.z - mz) / (0.18 * R)) ** 2) * min(1, abs(c.x) / (0.3 * R))
                w *= math.exp(-max(0, abs(c.x) - 0.35 * R) / (0.1 * R))
                return c + Vector((math.copysign(0.07 * R * w, c.x), 0.01 * R * w, 0.01 * R * w))
            return c

        def k_round(c):
            if c.y < -0.2 * R:
                w = math.exp(-((c.z - mz) / (0.16 * R)) ** 2) * math.exp(-(c.x / (0.4 * R)) ** 2)
                return c + Vector((-c.x * 0.35 * w, -0.08 * R * w, 0))
            return c

        def k_smile(c):
            if c.y < -0.2 * R:
                w = math.exp(-((c.z - mz) / (0.2 * R)) ** 2) * min(1, abs(c.x) / (0.28 * R))
                w *= math.exp(-max(0, abs(c.x) - 0.36 * R) / (0.12 * R))
                return c + Vector((math.copysign(0.04 * R * w, c.x), 0.01 * R * w, 0.06 * R * w))
            return c

        def k_frown(c):
            if c.y < -0.2 * R:
                w = math.exp(-((c.z - mz) / (0.2 * R)) ** 2) * min(1, abs(c.x) / (0.28 * R))
                return c + Vector((0, 0, -0.05 * R * w))
            return c

        self.k_open = add_key("open", k_open)
        self.k_wide = add_key("wide", k_wide)
        self.k_round = add_key("round", k_round)
        self.k_smile = add_key("smile", k_smile)
        self.k_frown = add_key("frown", k_frown)
        sub = head.modifiers.new("S", "SUBSURF")
        sub.levels = 1
        sub.render_levels = 2
        # порожнина рота, зуби, язик (діти щелепи)
        hz = 0.13
        cav = prim("sphere", (0, -0.42 * R, hz + mz - 0.02 * R), (0.25 * R, 0.3 * R, 0.13 * R), material=self.m_mouth)
        cav.parent = self.head_pivot
        self.teeth_up = prim("cube", (0, -0.80 * R, hz + mz + 0.035 * R), (0.2 * R, 0.05 * R, 0.035 * R),
                             material=self.m_teeth, subsurf=2)
        self.teeth_up.parent = self.head_pivot
        self.jaw = bpy.data.objects.new(self.name + "_jaw", None)
        bpy.context.scene.collection.objects.link(self.jaw)
        self.jaw.parent = self.head_pivot
        self.jaw.location = (0, piv.y, hz + piv.z)
        tl = prim("cube", (0, -0.76 * R - piv.y, mz - 0.04 * R - piv.z), (0.18 * R, 0.05 * R, 0.03 * R),
                  material=self.m_teeth, subsurf=2)
        tl.parent = self.jaw
        tg = prim("sphere", (0, -0.5 * R - piv.y, mz - 0.08 * R - piv.z), (0.2 * R, 0.3 * R, 0.07 * R),
                  material=self.m_tongue)
        tg.parent = self.jaw
        # ніс
        nose = prim("sphere", (0, -0.97 * R, hz + 0.0 * R), (0.11 * R, 0.13 * R, 0.17 * R), material=self.m_skin,
                    subsurf=1)
        nose.parent = self.head_pivot
        tip = prim("sphere", (0, -1.07 * R, hz - 0.1 * R), (0.1 * R, 0.09 * R, 0.08 * R), material=self.m_skin)
        tip.parent = self.head_pivot
        # вуха
        for sx in (-1, 1):
            ear = prim("sphere", (sx * 0.86 * R, 0.05 * R, hz + 0.05 * R), (0.06 * R, 0.16 * R, 0.24 * R),
                       material=self.m_skin)
            ear.rotation_euler = (0, 0, sx * math.radians(-20))
            ear.parent = self.head_pivot

    # ---------------------------------------------------------- очі
    def _eyes(self):
        hz = 0.13
        self.eyes, self.lids_up, self.lids_lo, self.brows = [], [], [], []
        for sx in (-1, 1):
            c = Vector((sx * 0.36 * R, -0.70 * R, hz + 0.20 * R))
            piv = bpy.data.objects.new("eyepiv", None)
            bpy.context.scene.collection.objects.link(piv)
            piv.parent = self.head_pivot
            piv.location = c
            ball = prim("sphere", (0, 0, 0), (0.17 * R,) * 3, material=self.m_white, segments=32, ring_count=16)
            ball.parent = piv
            iris = prim("sphere", (0, -0.12 * R, 0), (0.095 * R, 0.06 * R, 0.095 * R), material=self.m_iris,
                        segments=32, ring_count=16)
            iris.parent = piv
            pup = prim("sphere", (0, -0.163 * R, 0), (0.045 * R, 0.02 * R, 0.045 * R), material=self.m_dark,
                       segments=24, ring_count=12)
            pup.parent = piv
            hl = prim("sphere", (0.03 * R, -0.17 * R, 0.035 * R), (0.016 * R,) * 3,
                      material=mat("eyehl", (1, 1, 1), 0.1, emit=(1, 1, 1), emit_str=3.0), segments=12, ring_count=6)
            hl.parent = piv
            self.eyes.append(piv)
            # повіки — півсфери шкіри
            for up, store in ((True, self.lids_up), (False, self.lids_lo)):
                lp = bpy.data.objects.new("lidpiv", None)
                bpy.context.scene.collection.objects.link(lp)
                lp.parent = self.head_pivot
                lp.location = c
                bm = bmesh.new()
                bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=0.19 * R)
                dele = [f for f in bm.faces if (f.calc_center_median().z < 0) == up]
                bmesh.ops.delete(bm, geom=dele, context="FACES")
                lid = obj_from_bm("lid", bm, self.m_skin, True)
                lid.parent = lp
                store.append(lp)
            # брова
            pts = [Vector((sx * (0.2 + 0.06 * i) * R, -0.86 * R + 0.02 * R * i * i * 0.2, hz + (0.40 + 0.03 * math.sin(i * 0.8)) * R))
                   for i in range(6)]
            br = tube("brow", pts, [0.025 * R, 0.035 * R, 0.035 * R, 0.033 * R, 0.028 * R, 0.018 * R], 8, self.m_hair)
            bp = bpy.data.objects.new("browpiv", None)
            bpy.context.scene.collection.objects.link(bp)
            bp.parent = self.head_pivot
            br.parent = bp
            self.brows.append((bp, sx))

    # ---------------------------------------------------------- волосся
    def _hair(self, style, beard):
        hz = 0.13
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=32, radius=R * 1.06)
        rng = np.random.default_rng(len(self.name))
        dele = []
        for v in bm.verts:
            v.co = _head_shape(v.co / 1.06) * 1.07
        for f in bm.faces:
            c = f.calc_center_median()
            # залишити шапку: верх і потилицю, відкрити лоб і обличчя
            front = c.y < -0.25 * R and c.z < 0.70 * R
            low = c.z < (0.05 * R if c.y > 0.2 * R else 0.25 * R)
            side_ear = abs(c.x) > 0.75 * R and c.z < 0.35 * R and c.y < 0.3 * R
            if front or low or side_ear:
                dele.append(f)
        bmesh.ops.delete(bm, geom=dele, context="FACES")
        for v in bm.verts:
            n = v.co.normalized()
            v.co += n * (0.07 * R + 0.035 * R * rng.random()) * (1 if v.co.z > 0.3 * R else 0.55)
        hair = obj_from_bm("hair", bm, self.m_hair, True, 2)
        sol = hair.modifiers.new("T", "SOLIDIFY")
        sol.thickness = 0.02 * R
        hair.modifiers.move(1, 0)
        hair.parent = self.head_pivot
        hair.location = (0, 0, hz)
        if beard:
            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=32, radius=R * 1.02)
            dele = []
            for v in bm.verts:
                v.co = _head_shape(v.co / 1.02) * 1.03
            for f in bm.faces:
                c = f.calc_center_median()
                if not (c.z < -0.05 * R and c.y < 0.35 * R) or (abs(c.x) < 0.3 * R and abs(c.z - self.mz) < 0.12 * R):
                    dele.append(f)
            bmesh.ops.delete(bm, geom=dele, context="FACES")
            bd = obj_from_bm("beard", bm, self.m_hair, True, 1)
            bd.parent = self.head_pivot
            bd.location = (0, 0, hz)

    def _headset(self):
        hz = 0.13
        m = mat("headset", (0.05, 0.05, 0.06), 0.35, metal=0.3)
        pts = [Vector((math.cos(a) * 0.98 * R * 1.12, 0.05 * R, hz + math.sin(a) * 1.18 * R * 1.1)) for a in np.linspace(0.05, math.pi - 0.05, 24)]
        band = tube("band", pts, [0.012] * 24, 8, m)
        band.parent = self.head_pivot
        for sx in (-1, 1):
            cup = prim("cyl", (sx * 0.98 * R, 0.05 * R, hz + 0.05 * R), (0.32 * R, 0.32 * R, 0.1 * R),
                       rot=(0, math.radians(90), 0), material=m, vertices=24)
            cup.parent = self.head_pivot
        boom = [Vector((-0.98 * R, 0.0, hz)), Vector((-0.9 * R, -0.5 * R, hz - 0.35 * R)),
                Vector((-0.55 * R, -0.95 * R, hz - 0.5 * R)), Vector((-0.3 * R, -1.08 * R, hz - 0.52 * R))]
        b = tube("boom", boom, [0.004, 0.004, 0.004, 0.004], 6, m)
        b.parent = self.head_pivot
        mic = prim("sphere", (-0.28 * R, -1.1 * R, hz - 0.52 * R), (0.06 * R,) * 3, material=m)
        mic.parent = self.head_pivot

    # ---------------------------------------------------------- анімація
    def face(self, jaw=0.0, wide=0.0, round_=0.0, smile=0.0, frown=0.0, blink=0.0, brow=0.0, brow_in=0.0,
             look=(0.0, 0.0)):
        self.k_open.value = jaw
        self.jaw.rotation_euler = (math.radians(16) * jaw, 0, 0)
        self.k_wide.value = wide
        self.k_round.value = round_
        self.k_smile.value = smile
        self.k_frown.value = frown
        for e in self.eyes:
            e.rotation_euler = (look[1], 0, look[0])
        # повіки: верхня опускається до закриття
        for lp in self.lids_up:
            lp.rotation_euler = (math.radians(lerp_(-28, 72, blink)) + look[1] * 0.5, 0, 0)
        for lp in self.lids_lo:
            lp.rotation_euler = (math.radians(lerp_(18, -8, blink)), 0, 0)
        for bp, sx in self.brows:
            bp.location = (sx * -0.01 * R * brow_in, 0, 0.06 * R * brow - 0.02 * R * brow_in)
            bp.rotation_euler = (0, sx * math.radians(10) * brow_in, 0)

    def pose_head(self, yaw=0.0, pitch=0.0, roll=0.0):
        self.head_pivot.rotation_euler = (pitch, roll, yaw)


def lerp_(a, b, t):
    return a + (b - a) * t
