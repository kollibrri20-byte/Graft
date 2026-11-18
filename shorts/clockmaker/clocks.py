"""Clocks: shelf clocks, mantel clocks, pendulum clocks and the hero alarm clocks (grandma / Lina)."""
from __future__ import annotations

import math
import os

import bpy
from mathutils import Vector

import lib
from lib import empty, sphere, cyl, torus, box, obj, mat, emit

D = math.radians
_M = {}


def mats():
    if _M:
        return _M
    _M["brass"] = mat("brass", (0.80, 0.55, 0.24), 0.25, metal=1.0)
    _M["brass_dark"] = mat("brass_dark", (0.45, 0.30, 0.12), 0.35, metal=1.0)
    _M["silver"] = mat("silver", (0.82, 0.83, 0.86), 0.18, metal=1.0)
    _M["wood"] = lib.noise_mat("clockwood", (0.20, 0.09, 0.04), (0.34, 0.17, 0.07), scale=14, rough=0.35, bump=0.05, kind="wave")
    _M["wood2"] = lib.noise_mat("clockwood2", (0.10, 0.05, 0.03), (0.22, 0.12, 0.06), scale=10, rough=0.3, bump=0.05, kind="wave")
    _M["wood3"] = lib.noise_mat("clockwood3", (0.32, 0.20, 0.10), (0.45, 0.30, 0.16), scale=12, rough=0.4, bump=0.05, kind="wave")
    _M["hands"] = mat("hands", (0.03, 0.03, 0.05), 0.3, metal=0.8)
    _M["hands_gold"] = mat("hands_gold", (0.9, 0.65, 0.25), 0.2, metal=1.0)
    _M["sec"] = mat("sechand", (0.6, 0.05, 0.03), 0.3, metal=0.5)
    _M["glass"] = thin_glass("clockglass")
    for k, args in {
        "cream": dict(face=(236, 224, 196), ink=(40, 30, 22), ring=(150, 110, 50), seed=1),
        "ivory": dict(face=(244, 238, 222), ink=(30, 26, 22), ring=(120, 90, 40), seed=2),
        "dark": dict(face=(40, 34, 30), ink=(220, 190, 120), ring=(170, 130, 60), seed=3),
        "silver": dict(face=(214, 216, 222), ink=(26, 28, 36), ring=(140, 140, 150), seed=4),
        "blue": dict(face=(28, 40, 70), ink=(225, 210, 160), ring=(170, 140, 70), seed=5),
    }.items():
        p = lib.dial_png(os.path.join(lib.TEX, f"dial_{k}.png"), **args)
        _M["dial_" + k] = lib.image_mat("dial_" + k, p, rough=0.45)
    return _M


class Clock:
    """A clock whose dial faces -Y of its root. Hands rotate about local Y (positive = clockwise from the front)."""

    def __init__(self, name, loc, rz=0.0, style="round", r=0.1, dial="cream", label=None, label_mat=None, parent=None,
                 glass=False, seconds=False, body=None, crack=False, counter=None):
        M = mats()
        self.name = name
        self.r = r
        self.root = empty(name, loc, parent, rot=(0, 0, D(rz)))
        R = self.root
        bm = body or M["brass"]
        self.dial = obj(name + "_dial", lib.m_disc(64), (0, 0, 0), M["dial_" + dial] if isinstance(dial, str) else dial, R, scale=(r, 1, r))
        if style == "round":
            cyl(name + "_body", (0, r * 0.32, 0), r * 1.1, r * 0.6, M["wood2"] if bm is None else bm, R, rot=(D(90), 0, 0))
            torus(name + "_bezel", (0, -r * 0.03, 0), r * 1.05, r * 0.08, M["brass"], R, rot=(D(90), 0, 0))
        elif style == "mantel":
            box(name + "_case", (0, r * 0.62, -r * 0.35), (r * 2.6, r * 1.2, r * 2.9), bm, R, bevel=0.0)
            cyl(name + "_dome", (0, r * 0.62, r * 0.95), r * 1.3, r * 1.2, bm, R, rot=(D(90), 0, 0))
            torus(name + "_bezel", (0, -r * 0.03, 0), r * 1.05, r * 0.07, M["brass"], R, rot=(D(90), 0, 0))
            for sx in (1, -1):
                sphere(name + "_foot", (sx * r * 1.1, r * 0.62, -r * 1.85), (r * 0.18, r * 0.18, r * 0.1), M["brass"], R)
            sphere(name + "_finial", (0, r * 0.62, r * 2.3), r * 0.14, M["brass"], R)
        elif style == "square":
            box(name + "_case", (0, r * 0.4, 0), (r * 2.5, r * 0.75, r * 2.5), bm, R)
            torus(name + "_bezel", (0, -r * 0.03, 0), r * 1.05, r * 0.06, M["brass"], R, rot=(D(90), 0, 0))
        elif style == "alarm":
            cyl(name + "_body", (0, r * 0.37, 0), r * 1.12, r * 0.65, bm, R, rot=(D(90), 0, 0), seg=64)
            torus(name + "_bezel", (0, -r * 0.03, 0), r * 1.08, r * 0.09, bm, R, rot=(D(90), 0, 0), seg=64)
            for sx in (1, -1):
                a = D(38)
                c = Vector((sx * math.sin(a) * r * 1.2, r * 0.3, math.cos(a) * r * 1.2))
                b = sphere(name + "_bell", c, (r * 0.42, r * 0.42, r * 0.42), bm, R)
                b.rotation_euler = (0, D(sx * 38), 0)
                sphere(name + "_leg", (sx * r * 0.75, r * 0.3, -r * 1.12), (r * 0.15, r * 0.15, r * 0.2), bm, R)
            torus(name + "_handle", (0, r * 0.3, r * 1.3), r * 0.42, r * 0.06, bm, R, rot=(0, 0, 0), a0=0, a1=math.pi)
            self.handle = None
            sphere(name + "_knob", (0, r * 0.3, r * 1.62), r * 0.1, bm, R)
        elif style == "pendulum":
            box(name + "_case", (0, r * 0.7, -r * 4.2), (r * 2.8, r * 1.4, r * 11.0), bm, R)
            box(name + "_hood", (0, r * 0.7, r * 0.2), (r * 3.2, r * 1.6, r * 3.0), bm, R)
            cyl(name + "_arch", (0, r * 0.7, r * 1.6), r * 1.5, r * 1.5, bm, R, rot=(D(90), 0, 0))
            torus(name + "_bezel", (0, -r * 0.03, 0), r * 1.05, r * 0.07, M["brass"], R, rot=(D(90), 0, 0))
            box(name + "_window", (0, -0.002, -r * 4.3), (r * 1.7, r * 0.02, r * 5.5), mat(name + "_wd", (0.02, 0.015, 0.01), 0.2), R)
            self.pend = empty(name + "_pend", (0, -0.01, -r * 1.8), R)
            box(name + "_rod", (0, 0, -r * 2.0), (r * 0.06, r * 0.02, r * 4.0), M["brass"], self.pend)
            cyl(name + "_bob", (0, 0, -r * 4.1), r * 0.55, r * 0.08, M["brass"], self.pend, rot=(D(90), 0, 0))
        # hands
        hm = M["hands_gold"] if dial in ("dark", "blue") else M["hands"]
        self.h = empty(name + "_hp", (0, -r * 0.012, 0), R)
        self.m = empty(name + "_mp", (0, -r * 0.022, 0), R)
        box(name + "_hh", (0, 0, r * 0.22), (r * 0.075, r * 0.012, r * 0.52), hm, self.h)
        sphere(name + "_hht", (0, 0, r * 0.46), (r * 0.07, r * 0.012, r * 0.09), hm, self.h)
        box(name + "_mh", (0, 0, r * 0.33), (r * 0.05, r * 0.012, r * 0.78), hm, self.m)
        self.s = None
        if seconds:
            self.s = empty(name + "_sp", (0, -r * 0.03, 0), R)
            box(name + "_sh", (0, 0, r * 0.3), (r * 0.018, r * 0.01, r * 1.0), M["sec"], self.s)
        sphere(name + "_cap", (0, -r * 0.035, 0), (r * 0.06, r * 0.03, r * 0.06), M["brass"], R)
        self.label = None
        if label:
            lm = label_mat or emit(name + "_lab", (1.0, 0.72, 0.25), 3.0)
            self.label_mat = lm
            self.label = lib.text(name + "_label", label, (0, -r * 0.006, -r * 0.33), r * 0.17, lm, R)
        self.counter = None
        if counter:
            cm = emit(name + "_cnt", (1.0, 0.15, 0.08), 4.0)
            self.counter_mat = cm
            self.counter = lib.text(name + "_counter", counter, (0, -r * 0.006, r * 0.33), r * 0.2, cm, R)
        self.glass = None
        if glass:
            self.glass = obj(name + "_glass", lib.m_disc(64), (0, -r * 0.06, 0), M["glass"], R, scale=(r * 1.02, 1, r * 1.02))
        self.crack = None
        if crack:
            self.crack_mat, self.crack_val = crack_material(name)
            self.crack = obj(name + "_crack", lib.m_disc(64), (0, -r * 0.065, 0), self.crack_mat, R, scale=(r * 1.02, 1, r * 1.02))
        self.angles = (0.0, 0.0, 0.0)

    def set(self, hour_deg, minute_deg, sec_deg=0.0):
        self.h.rotation_euler = (0, D(hour_deg), 0)
        self.m.rotation_euler = (0, D(minute_deg), 0)
        if self.s:
            self.s.rotation_euler = (0, D(sec_deg), 0)

    def world_center(self):
        return self.root.matrix_world.translation.copy()


def thin_glass(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.12
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = 0.03
    mix = nt.nodes.new("ShaderNodeMixShader")
    mr = nt.nodes.new("ShaderNodeMath"); mr.operation = "ADD"; mr.inputs[1].default_value = 0.06
    nt.links.new(lw.outputs["Fresnel"], mr.inputs[0])
    nt.links.new(mr.outputs[0], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(gl.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def crack_material(name):
    """Transparent disc showing glowing crack lines, revealed radially by the 'reveal' value (0..1.2)."""
    p = lib.crack_png(os.path.join(lib.TEX, "crack.png"))
    m = bpy.data.materials.new(name + "_crackm")
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    out = nt.nodes["Material Output"]
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = bpy.data.images.load(p, check_existing=True)
    tx.image.pack()
    tx.image.colorspace_settings.name = "Non-Color"
    uv = nt.nodes.new("ShaderNodeUVMap")
    nt.links.new(uv.outputs["UV"], tx.inputs["Vector"])
    # radial distance from the impact point (0.46, 0.42 in uv; image y is flipped)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs[0])
    dx = nt.nodes.new("ShaderNodeMath"); dx.operation = "SUBTRACT"; dx.inputs[1].default_value = 0.46
    dy = nt.nodes.new("ShaderNodeMath"); dy.operation = "SUBTRACT"; dy.inputs[1].default_value = 0.42
    nt.links.new(sep.outputs["X"], dx.inputs[0]); nt.links.new(sep.outputs["Y"], dy.inputs[0])
    vx = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(dx.outputs[0], vx.inputs[0]); nt.links.new(dy.outputs[0], vx.inputs[1])
    ln = nt.nodes.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"
    nt.links.new(vx.outputs[0], ln.inputs[0])
    val = nt.nodes.new("ShaderNodeValue"); val.name = "reveal"; val.outputs[0].default_value = 0.0
    lt = nt.nodes.new("ShaderNodeMath"); lt.operation = "LESS_THAN"
    nt.links.new(ln.outputs["Value"], lt.inputs[0]); nt.links.new(val.outputs[0], lt.inputs[1])
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
    nt.links.new(tx.outputs["Color"], mul.inputs[0]); nt.links.new(lt.outputs[0], mul.inputs[1])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.85, 0.95, 1.0, 1)
    em.inputs["Strength"].default_value = 1.2
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = 0.1
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(em.outputs[0], add.inputs[0]); nt.links.new(gl.outputs[0], add.inputs[1])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(mul.outputs[0], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(add.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    try:
        m.surface_render_method = "BLENDED"
    except Exception:
        pass
    return m, val
