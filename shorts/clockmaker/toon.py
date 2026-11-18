"""Stylised (big head, big eyes) characters built from smooth primitives on a pivot hierarchy.

Pivot conventions (character faces -Y when root rotation is 0; character's left = +X):
  pose dict values are (fwd, out, twist) degrees:
  - arm/leg: fwd = swing forward, out = away from the body, twist around the limb
  - elbow: fwd = bend (forearm forward/up); knee: fwd = bend (shin backward)
  - spine/head/neck: fwd = lean/nod forward, out = tilt to character's left, twist = turn to character's left
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

import lib
from lib import sphere, cyl, torus, limb, empty, mat

D = math.radians

ELIAS = dict(
    name="Elias", hip=0.78, torso=0.50, head_r=0.165, neck=0.06, shoulder=0.17, upper=0.26, fore=0.24, thigh=0.38, shin=0.36,
    skin=(0.86, 0.62, 0.50), eye=(0.35, 0.45, 0.55), body_r=(0.20, 0.16), belly=1.08,
    shirt=(0.36, 0.26, 0.18), pants=(0.20, 0.17, 0.15), shoes=(0.12, 0.07, 0.04), hand_r=0.045, limb_r=0.042,
)
LINA = dict(
    name="Lina", hip=0.46, torso=0.36, head_r=0.175, neck=0.035, shoulder=0.12, upper=0.17, fore=0.16, thigh=0.22, shin=0.22,
    skin=(0.95, 0.72, 0.60), eye=(0.80, 0.45, 0.08), body_r=(0.13, 0.10), belly=1.0,
    shirt=(0.72, 0.06, 0.05), pants=(0.12, 0.10, 0.12), shoes=(0.25, 0.10, 0.05), hand_r=0.034, limb_r=0.036,
)
GRANDMA = dict(
    name="Grandma", hip=0.70, torso=0.46, head_r=0.16, neck=0.05, shoulder=0.16, upper=0.25, fore=0.22, thigh=0.36, shin=0.34,
    skin=(0.90, 0.68, 0.58), eye=(0.30, 0.20, 0.12), body_r=(0.19, 0.15), belly=1.05,
    shirt=(0.22, 0.12, 0.20), pants=(0.22, 0.12, 0.20), shoes=(0.10, 0.07, 0.05), hand_r=0.042, limb_r=0.042,
)


def townsman(i):
    import random
    r = random.Random(i)
    coats = [(0.20, 0.25, 0.32), (0.35, 0.22, 0.14), (0.18, 0.28, 0.20), (0.30, 0.28, 0.25), (0.38, 0.16, 0.14)]
    skins = [(0.88, 0.64, 0.52), (0.70, 0.50, 0.38), (0.92, 0.72, 0.62), (0.58, 0.40, 0.30)]
    return dict(
        name=f"Towns{i}", hip=0.86 + r.uniform(-0.05, 0.05), torso=0.52, head_r=0.15, neck=0.05, shoulder=0.18, upper=0.27, fore=0.25,
        thigh=0.42, shin=0.42, skin=skins[i % 4], eye=(0.25, 0.18, 0.1), body_r=(0.21 + r.uniform(0, 0.04), 0.16), belly=1.1,
        shirt=coats[i % 5], pants=(0.15, 0.14, 0.14), shoes=(0.1, 0.07, 0.05), hand_r=0.045, limb_r=0.048,
    )


class Toon:
    def __init__(self, spec, loc=(0, 0, 0), facing=0.0, kind="generic", seed=0):
        self.s = s = spec
        self.kind = kind
        n = s["name"]
        self.root = empty(n + "_root", loc, rot=(0, 0, D(facing)))
        self.mats = {}
        sk = self.mats["skin"] = mat(n + "_skin", s["skin"], 0.5, sss=0.25)
        self.skin_base = tuple(s["skin"])
        shirt = self.mats["shirt"] = mat(n + "_shirt", s["shirt"], 0.85, sheen=0.4)
        pants = mat(n + "_pants", s["pants"], 0.85, sheen=0.3)
        shoes = mat(n + "_shoes", s["shoes"], 0.45, coat=0.3)
        self.P = P = {}
        P["pelvis"] = empty(n + "_pelvis", (0, 0, s["hip"]), self.root)
        P["spine"] = empty(n + "_spine", (0, 0, 0.02), P["pelvis"])
        top = s["torso"]
        P["neck"] = empty(n + "_neck", (0, 0, top), P["spine"])
        P["head"] = empty(n + "_head", (0, 0, s["neck"]), P["neck"])
        bx, by = s["body_r"]
        # torso
        self.torso = sphere(n + "_torso", (0, 0, top * 0.5), (bx, by * s["belly"], top * 0.58), shirt, P["spine"])
        sphere(n + "_hipball", (0, 0, 0.0), (bx * 0.95, by * 0.95, bx * 0.7), pants, P["pelvis"])
        cyl(n + "_neckc", (0, 0, top + s["neck"] * 0.3), s["head_r"] * 0.32, s["neck"] * 1.6, sk, P["spine"])
        # arms
        for side, sx in (("L", 1), ("R", -1)):
            P["arm" + side] = empty(n + "_arm" + side, (sx * s["shoulder"], 0, top * 0.86), P["spine"])
            sphere(n + "_shoulder" + side, (0, 0, 0), s["limb_r"] * 1.35, shirt, P["arm" + side])
            limb(n + "_upper" + side, P["arm" + side], s["upper"], s["limb_r"] * 1.15, s["limb_r"], shirt)
            P["elbow" + side] = empty(n + "_elbow" + side, (0, 0, -s["upper"]), P["arm" + side])
            limb(n + "_fore" + side, P["elbow" + side], s["fore"], s["limb_r"], s["limb_r"] * 0.85, shirt)
            P["hand" + side] = empty(n + "_hand" + side, (0, 0, -s["fore"]), P["elbow" + side])
            sphere(n + "_hand" + side, (0, -0.005, -s["hand_r"] * 0.9), (s["hand_r"] * 0.85, s["hand_r"] * 0.6, s["hand_r"] * 1.15), sk, P["hand" + side])
            sphere(n + "_thumb" + side, (-sx * s["hand_r"] * 0.55, -s["hand_r"] * 0.45, -s["hand_r"] * 0.55), (s["hand_r"] * 0.32, s["hand_r"] * 0.32, s["hand_r"] * 0.55), sk, P["hand" + side])
            # legs
            P["leg" + side] = empty(n + "_leg" + side, (sx * bx * 0.48, 0, 0), P["pelvis"])
            limb(n + "_thigh" + side, P["leg" + side], s["thigh"], s["limb_r"] * 1.35, s["limb_r"] * 1.1, pants)
            P["knee" + side] = empty(n + "_knee" + side, (0, 0, -s["thigh"]), P["leg" + side])
            limb(n + "_shin" + side, P["knee" + side], s["shin"], s["limb_r"] * 1.1, s["limb_r"] * 0.9, pants)
            sphere(n + "_shoe" + side, (0, -0.05, -s["shin"] - 0.01), (s["limb_r"] * 1.35, s["limb_r"] * 2.6, s["limb_r"] * 1.0), shoes, P["knee" + side])
        self._head()
        build = {"elias": self._elias, "lina": self._lina, "grandma": self._grandma}.get(kind, self._generic)
        build(seed)
        self.pose = {}
        self.set_pose({})

    # ------------------------------------------------------------ head + face
    def _head(self):
        s, n, P = self.s, self.s["name"], self.P
        r = s["head_r"]
        H = self.P["head"]
        self.hc = Vector((0, 0, r * 0.92))
        sk = self.mats["skin"]
        self.headmesh = sphere(n + "_skull", self.hc, (r, r * 0.95, r * 1.02), sk, H)
        sphere(n + "_jaw", self.hc + Vector((0, -r * 0.18, -r * 0.42)), (r * 0.78, r * 0.72, r * 0.55), sk, H)
        sphere(n + "_nose", self.hc + Vector((0, -r * 0.98, -r * 0.12)), (r * 0.16, r * 0.15, r * 0.15), sk, H)
        for sx in (1, -1):
            sphere(n + "_ear", self.hc + Vector((sx * r * 0.97, 0.02 * r, -r * 0.05)), (r * 0.12, r * 0.18, r * 0.24), sk, H)
        white = mat(n + "_eyewhite", (0.97, 0.96, 0.94), 0.15, coat=1.0)
        iris = mat(n + "_iris", s["eye"], 0.25, coat=1.0)
        pupil = mat(n + "_pupil", (0.01, 0.01, 0.01), 0.1, coat=1.0)
        hl = lib.emit(n + "_hl", (1, 1, 1), 6.0)
        er = r * 0.26
        self.eyes = []
        for sx in (1, -1):
            e = empty(n + "_eye", self.hc + Vector((sx * r * 0.37, -r * 0.74, r * 0.06)), H)
            sphere(n + "_ew", (0, 0, 0), er, white, e)
            sphere(n + "_ir", (0, -er * 0.80, 0), (er * 0.62, er * 0.32, er * 0.62), iris, e)
            sphere(n + "_pu", (0, -er * 0.97, 0), (er * 0.30, er * 0.18, er * 0.30), pupil, e)
            sphere(n + "_hl", (er * 0.25, -er * 1.08, er * 0.28), er * 0.11, hl, e)
            self.eyes.append(e)
        self.er = er
        # brows
        self.brows = []
        for sx in (1, -1):
            b = empty(n + "_brow", self.hc + Vector((sx * r * 0.38, -r * 0.86, r * 0.40)), H)
            self.brows.append(b)
        # mouths (visibility toggled by scale)
        mm = mat(n + "_mouth", (0.35, 0.06, 0.06), 0.4)
        lip = mat(n + "_lip", tuple(c * 0.75 for c in s["skin"]), 0.5)
        mc = self.hc + Vector((0, -r * 0.88, -r * 0.42))
        self.mouth = {}
        o = torus(n + "_smile", mc + Vector((0, 0, r * 0.12)), r * 0.22, r * 0.035, mm, H, rot=(D(90), 0, 0), a0=D(205), a1=D(335), seg=24)
        self.mouth["smile"] = o
        o = torus(n + "_neutral", mc + Vector((0, 0.0, r * 0.62)), r * 0.65, r * 0.03, mm, H, rot=(D(90), 0, 0), a0=D(252), a1=D(288), seg=16)
        self.mouth["neutral"] = o
        o = torus(n + "_frown", mc + Vector((0, 0.0, -r * 0.16)), r * 0.2, r * 0.032, mm, H, rot=(D(90), 0, 0), a0=D(35), a1=D(145), seg=16)
        self.mouth["frown"] = o
        o = sphere(n + "_open", mc + Vector((0, 0.0, 0)), (r * 0.17, r * 0.08, r * 0.15), mm, H)
        self.mouth["open"] = o
        for k, o in self.mouth.items():
            o["s0"] = tuple(o.scale)

    def _brow_mesh(self, color, w=1.0, thick=1.0):
        r = self.s["head_r"]
        m = mat(self.s["name"] + "_browm", color, 0.8, sheen=0.5)
        for b, sx in zip(self.brows, (1, -1)):
            sphere(self.s["name"] + "_browo", (0, 0, 0), (r * 0.2 * w, r * 0.06 * thick, r * 0.05 * thick), m, b, rot=(0, D(-8 * sx), 0))

    # ------------------------------------------------------------ outfits
    def _elias(self, seed):
        s, n, P, r = self.s, self.s["name"], self.P, self.s["head_r"]
        H = P["head"]
        silver = mat(n + "_hair", (0.80, 0.80, 0.82), 0.6, sheen=0.8)
        self.mats["hair"] = silver
        # fringe of hair around the back of the bald head
        torus(n + "_fringe", self.hc + Vector((0, r * 0.15, r * 0.05)), r * 0.86, r * 0.2, silver, H, rot=(D(-12), 0, 0), a0=D(-20), a1=D(200))
        for sx in (1, -1):
            sphere(n + "_tuft", self.hc + Vector((sx * r * 0.85, r * 0.1, r * 0.25)), (r * 0.22, r * 0.3, r * 0.25), silver, H)
        # long beard + moustache
        sphere(n + "_beard", self.hc + Vector((0, -r * 0.55, -r * 0.95)), (r * 0.72, r * 0.45, r * 0.95), silver, H, rot=(D(-14), 0, 0))
        sphere(n + "_beard2", self.hc + Vector((0, -r * 0.62, -r * 1.65)), (r * 0.45, r * 0.32, r * 0.75), silver, H, rot=(D(-18), 0, 0))
        for sx in (1, -1):
            sphere(n + "_mous", self.hc + Vector((sx * r * 0.2, -r * 0.93, -r * 0.33)), (r * 0.28, r * 0.12, r * 0.1), silver, H, rot=(0, D(sx * 18), 0))
        self.mouth["smile"].location.z -= r * 0.05
        self._brow_mesh((0.86, 0.86, 0.88), w=1.25, thick=1.6)
        # round brass glasses (separate pivot so they can slip)
        brass = mat(n + "_brass", (0.85, 0.62, 0.30), 0.22, metal=1.0)
        import clocks as _c
        lens = _c.thin_glass(n + "_lens")
        g = self.glasses = empty(n + "_glasses", self.hc + Vector((0, -r * 1.0, r * 0.06)), H)
        for sx in (1, -1):
            torus(n + "_rim", (sx * r * 0.37, 0, 0), r * 0.27, r * 0.025, brass, g, rot=(D(90), 0, 0))
            lib.obj(n + "_lensd", lib.m_disc(32), (sx * r * 0.37, -0.002, 0), lens, g, scale=(r * 0.26, 1, r * 0.26))
            cyl(n + "_temple", (sx * r * 0.66, r * 0.4, 0.0), r * 0.015, r * 0.85, brass, g, rot=(D(90), 0, 0), seg=8)
        torus(n + "_bridge", (0, 0, -r * 0.02), r * 0.1, r * 0.02, brass, g, rot=(D(90), 0, 0), a0=D(20), a1=D(160))
        # eyes a bit smaller and kinder
        for e in self.eyes:
            e.scale = (0.85, 0.85, 0.8)
        # apron: front plate + bib + straps
        green = mat(n + "_apron", (0.07, 0.20, 0.12), 0.8, sheen=0.4)
        bx, by = s["body_r"]
        sphere(n + "_apronfront", (0, -by * 0.42, s["torso"] * 0.36), (bx * 0.86, by * 0.68, s["torso"] * 0.55), green, P["spine"])
        lib.lathe(n + "_apronskirt", (0, -0.02, 0.05), lib.bell(bx * 0.98, bx * 1.12, 0.62), green, P["pelvis"], scale=(1, 0.85, 1))
        # pocket with a tiny brass watch chain
        cyl(n + "_chain", (bx * 0.3, -by * 1.08, s["torso"] * 0.3), 0.004, 0.12, brass, P["spine"], rot=(0, D(70), 0), seg=6)

    def _lina(self, seed):
        s, n, P, r = self.s, self.s["name"], self.P, self.s["head_r"]
        H = P["head"]
        hair = mat(n + "_hair", (0.30, 0.15, 0.07), 0.55, sheen=0.6)
        self.mats["hair"] = hair
        sphere(n + "_haircap", self.hc + Vector((0, r * 0.1, r * 0.12)), (r * 1.07, r * 1.02, r * 1.0), hair, H)
        # fringe
        for k, sx in enumerate((-0.45, -0.15, 0.15, 0.45)):
            sphere(n + "_bang", self.hc + Vector((sx * r, -r * 0.82, r * 0.55 - abs(sx) * r * 0.15)), (r * 0.26, r * 0.14, r * 0.2), hair, H, rot=(D(25), 0, D(-sx * 30)))
        # two braids (chains of beads) with yellow ties
        tie = mat(n + "_tie", (0.98, 0.78, 0.10), 0.5)
        self.braids = []
        for sx in (1, -1):
            b = empty(n + "_braid", self.hc + Vector((sx * r * 0.82, r * 0.25, -r * 0.35)), H)
            for k in range(5):
                rr = r * (0.2 - k * 0.018)
                sphere(n + "_bead", (sx * k * r * 0.03, k * r * 0.03, -k * r * 0.27), (rr, rr, rr * 1.25), hair, b)
            sphere(n + "_tieb", (sx * 5 * r * 0.03, 5 * r * 0.03, -5 * r * 0.27 + r * 0.08), r * 0.08, tie, b)
            sphere(n + "_tip", (sx * 5.5 * r * 0.03, 5.5 * r * 0.03, -5.5 * r * 0.27), (r * 0.09, r * 0.09, r * 0.16), hair, b)
            self.braids.append(b)
        self._brow_mesh((0.30, 0.15, 0.07), w=0.9, thick=0.9)
        # blush
        blush = mat(n + "_blush", (0.98, 0.55, 0.50), 0.6, sss=0.3)
        for sx in (1, -1):
            sphere(n + "_cheek", self.hc + Vector((sx * r * 0.52, -r * 0.72, -r * 0.28)), (r * 0.17, r * 0.06, r * 0.11), blush, H)
        # red coat: flared skirt hanging from the waist + collar, yellow scarf
        coat = self.mats["shirt"]
        bx, by = s["body_r"]
        self.skirt = empty(n + "_skirtpiv", (0, 0, 0.06), P["pelvis"])
        lib.lathe(n + "_coat", (0, 0, 0.0), lib.bell(bx * 1.0, bx * 1.65, 0.30), coat, self.skirt, scale=(1, 0.9, 1))
        btn = mat(n + "_btn", (0.15, 0.08, 0.04), 0.3, coat=0.5)
        for k in range(3):
            sphere(n + "_btn", (0, -by * 1.02, s["torso"] * (0.25 + k * 0.17)), 0.012, btn, P["spine"])
        scarf = mat(n + "_scarf", (0.98, 0.76, 0.10), 0.9, sheen=0.8)
        torus(n + "_scarf", (0, 0, s["torso"] + 0.01), r * 0.42, r * 0.14, scarf, P["spine"])
        self.scarf_tail = empty(n + "_scarftail", (bx * 0.35, -by * 0.95, s["torso"] - 0.02), P["spine"])
        sphere(n + "_scarft", (0, -0.01, -0.07), (0.035, 0.018, 0.09), scarf, self.scarf_tail)
        # big eyes
        for e in self.eyes:
            e.scale = (1.12, 1.12, 1.15)
        # tights + boots darker already via pants/shoes

    def _grandma(self, seed):
        s, n, P, r = self.s, self.s["name"], self.P, self.s["head_r"]
        H = P["head"]
        white = mat(n + "_hair", (0.93, 0.92, 0.90), 0.6, sheen=0.7)
        self.mats["hair"] = white
        sphere(n + "_haircap", self.hc + Vector((0, r * 0.12, r * 0.16)), (r * 1.05, r * 1.0, r * 0.95), white, H)
        sphere(n + "_bun", self.hc + Vector((0, r * 0.55, r * 0.85)), r * 0.42, white, H)
        torus(n + "_bunring", self.hc + Vector((0, r * 0.45, r * 0.7)), r * 0.3, r * 0.08, white, H, rot=(D(50), 0, 0))
        for sx in (1, -1):
            sphere(n + "_side", self.hc + Vector((sx * r * 0.62, -r * 0.35, r * 0.5)), (r * 0.42, r * 0.35, r * 0.3), white, H, rot=(0, D(sx * 30), 0))
        self._brow_mesh((0.88, 0.87, 0.85), w=0.95, thick=1.0)
        blush = mat(n + "_blush", (0.95, 0.55, 0.52), 0.6, sss=0.3)
        for sx in (1, -1):
            sphere(n + "_cheek", self.hc + Vector((sx * r * 0.5, -r * 0.72, -r * 0.3)), (r * 0.17, r * 0.06, r * 0.11), blush, H)
        for e in self.eyes:
            e.scale = (0.85, 0.85, 0.82)
        # knitted grey shawl (wave texture bump) over the shoulders
        shawl = lib.noise_mat(n + "_shawl", (0.42, 0.42, 0.44), (0.62, 0.62, 0.64), scale=60, rough=0.95, bump=0.6, kind="wave")
        bx, by = s["body_r"]
        lib.lathe(n + "_shawl", (0, 0.01, s["torso"] + 0.03), lib.bell(r * 0.45, bx * 1.35, s["torso"] * 0.62), shawl, P["spine"], scale=(1, 0.95, 1))
        dress = self.mats["shirt"]
        lib.lathe(n + "_skirt", (0, 0, 0.04), lib.bell(bx * 1.0, bx * 1.4, 0.68), dress, P["pelvis"])

    def _generic(self, seed):
        import random
        rnd = random.Random(seed)
        s, n, P, r = self.s, self.s["name"], self.P, self.s["head_r"]
        H = P["head"]
        hc = [(0.08, 0.05, 0.03), (0.30, 0.18, 0.08), (0.12, 0.10, 0.09), (0.55, 0.42, 0.25)][seed % 4]
        hair = mat(n + "_hair", hc, 0.6, sheen=0.5)
        self.mats["hair"] = hair
        sphere(n + "_haircap", self.hc + Vector((0, r * 0.12, r * 0.14)), (r * 1.04, r * 1.0, r * 0.96), hair, H)
        self._brow_mesh(hc, w=1.0, thick=1.2)
        if seed % 2 == 0:  # flat cap / hat
            hat = mat(n + "_hat", [(0.15, 0.15, 0.17), (0.28, 0.20, 0.12)][seed % 4 // 2], 0.8, sheen=0.4)
            cyl(n + "_hat", self.hc + Vector((0, 0.0, r * 0.82)), r * 0.85, r * 0.45, hat, H, seg=32)
            cyl(n + "_brim", self.hc + Vector((0, 0.0, r * 0.62)), r * 1.35, r * 0.05, hat, H, seg=32)
        if seed % 3 == 1:
            sphere(n + "_mous", self.hc + Vector((0, -r * 0.93, -r * 0.33)), (r * 0.42, r * 0.12, r * 0.1), hair, H)
        bx, by = s["body_r"]
        lib.lathe(n + "_coattail", (0, 0, 0.04), lib.bell(bx * 1.0, bx * 1.18, 0.5), self.mats["shirt"], P["pelvis"], scale=(1, 0.85, 1))
        scarf = mat(n + "_scarf", [(0.55, 0.12, 0.10), (0.15, 0.25, 0.45), (0.5, 0.45, 0.2)][seed % 3], 0.9, sheen=0.6)
        torus(n + "_scarf", (0, 0, s["torso"] + 0.0), r * 0.42, r * 0.13, scarf, P["spine"])

    # ------------------------------------------------------------ posing (called every frame by the handler)
    def set_pose(self, pose, blink=0.0, mouth="neutral", brow=0.0, gaze=(0.0, 0.0), skin=None, mouth_open=1.0):
        """pose: {joint: (fwd, out, twist)} degrees. Missing joints = rest."""
        P = self.P
        for j in ("spine", "neck", "head", "armL", "armR", "elbowL", "elbowR", "legL", "legR", "kneeL", "kneeR", "handL", "handR"):
            f, o, t = pose.get(j, (0, 0, 0))
            if j.startswith("arm") or j.startswith("leg"):
                sx = 1 if j.endswith("L") else -1
                P[j].rotation_euler = (D(-f), D(-o * sx), D(t * sx))
            elif j.startswith("elbow"):
                sx = 1 if j.endswith("L") else -1
                P[j].rotation_euler = (D(-f), D(-o * sx), D(t * sx))
            elif j.startswith("knee"):
                P[j].rotation_euler = (D(f), 0, 0)
            elif j.startswith("hand"):
                sx = 1 if j.endswith("L") else -1
                P[j].rotation_euler = (D(-f), D(-o * sx), D(t * sx))
            else:
                P[j].rotation_euler = (D(f), D(-o), D(t))
        if "pelvis_z" in pose:
            P["pelvis"].location.z = self.s["hip"] + pose["pelvis_z"]
        else:
            P["pelvis"].location.z = self.s["hip"]
        if "pelvis_rot" in pose:
            f, o, t = pose["pelvis_rot"]
            P["pelvis"].rotation_euler = (D(f), D(-o), D(t))
        else:
            P["pelvis"].rotation_euler = (0, 0, 0)
        # eyes: blink (0..1) + gaze (yaw, pitch degrees)
        for e in self.eyes:
            sz = e.get("sz0")
            if sz is None:
                e["sz0"] = tuple(e.scale)
                sz = e["sz0"]
            e.scale = (sz[0], sz[1], sz[2] * max(0.06, 1 - blink))
            e.rotation_euler = (D(-gaze[1]), 0, D(gaze[0]))
        for b, sx in zip(self.brows, (1, -1)):
            b.location.z = self.hc.z + self.s["head_r"] * (0.40 + 0.1 * brow)
            b.rotation_euler = (0, D(sx * 14 * brow * -1 if brow < 0 else -sx * 10 * brow), 0)
        for k, o in self.mouth.items():
            s0 = o["s0"]
            if k == mouth:
                o.scale = (s0[0], s0[1], s0[2] * (mouth_open if k == "open" else 1.0))
            else:
                o.scale = (0, 0, 0)
        if skin is not None:
            lib.color_socket(self.mats["skin"]).default_value = (*skin, 1)
        else:
            lib.color_socket(self.mats["skin"]).default_value = (*self.skin_base, 1)


def blend(a, b, u):
    """Blend two pose dicts."""
    out = {}
    for k in set(a) | set(b):
        va, vb = a.get(k, (0, 0, 0)), b.get(k, (0, 0, 0))
        if isinstance(va, (int, float)) or isinstance(vb, (int, float)):
            va = va if isinstance(va, (int, float)) else 0.0
            vb = vb if isinstance(vb, (int, float)) else 0.0
            out[k] = va + (vb - va) * u
        else:
            out[k] = tuple(x + (y - x) * u for x, y in zip(va, vb))
    return out


def seq(t, keys):
    """keys: [(time, pose), ...] -> smoothly blended pose at t."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, p0), (t1, p1) in zip(keys, keys[1:]):
        if t <= t1:
            return blend(p0, p1, lib.smooth((t - t0) / max(1e-6, t1 - t0)))
    return keys[-1][1]


STAND = {"armL": (0, 6, 0), "armR": (0, 6, 0), "elbowL": (12, 0, 0), "elbowR": (12, 0, 0)}
SIT = {"legL": (85, 5, 0), "legR": (85, 5, 0), "kneeL": (85, 0, 0), "kneeR": (85, 0, 0), "armL": (25, 6, 0), "armR": (25, 6, 0),
       "elbowL": (55, 0, 0), "elbowR": (55, 0, 0)}


def run_cycle(t, period=0.42, amp=1.0):
    ph = 2 * math.pi * t / period
    s = math.sin(ph)
    c = math.cos(ph)
    return {
        "legL": (35 * s * amp, 3, 0), "legR": (-35 * s * amp, 3, 0),
        "kneeL": (40 + 35 * max(0, -c) * amp, 0, 0), "kneeR": (40 + 35 * max(0, c) * amp, 0, 0),
        "armL": (-40 * s * amp, 12, 0), "armR": (40 * s * amp, 12, 0),
        "elbowL": (70, 0, 0), "elbowR": (70, 0, 0),
        "spine": (14, 0, 6 * s), "head": (-8, 0, -4 * s), "pelvis_z": 0.025 * abs(math.sin(ph)) - 0.03,
    }


def walk_cycle(t, period=0.9, amp=1.0):
    ph = 2 * math.pi * t / period
    s = math.sin(ph)
    c = math.cos(ph)
    return {
        "legL": (22 * s * amp, 2, 0), "legR": (-22 * s * amp, 2, 0),
        "kneeL": (8 + 25 * max(0, -c), 0, 0), "kneeR": (8 + 25 * max(0, c), 0, 0),
        "armL": (-18 * s, 7, 0), "armR": (18 * s, 7, 0), "elbowL": (18, 0, 0), "elbowR": (18, 0, 0),
        "spine": (3, 0, 3 * s), "pelvis_z": 0.012 * abs(s) - 0.01,
    }
