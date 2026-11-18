"""Sets for «Крамниця дзеркал»: TOWN (x≈0, rainy night), SHOP (x≈100, mirror shop), HOME (x≈200, doorway + hallway),
VOID (x≈300, end card), WALL (x≈400, people trapped behind glass)."""
from __future__ import annotations

import math
import os
import random

import bpy
import numpy as np
from mathutils import Matrix, Vector

import lib
from lib import box, cyl, sphere, torus, empty, obj, mat, emit, light, text

D = math.radians
R = {}


def coll(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


# ------------------------------------------------------------------ materials
_M = {}


def M():
    if _M:
        return _M
    _M["gold"] = mat("gold", (0.85, 0.60, 0.22), 0.28, metal=1.0)
    _M["gold_dark"] = mat("gold_dark", (0.45, 0.30, 0.10), 0.4, metal=1.0)
    _M["silver"] = mat("silverm", (0.85, 0.86, 0.9), 0.2, metal=1.0)
    _M["mirror"] = mirror_mat("mirror")
    _M["black_cloth"] = lib.noise_mat("blackcloth", (0.015, 0.015, 0.018), (0.04, 0.04, 0.045), scale=30, rough=0.9, bump=0.3, kind="wave")
    return _M


def mirror_mat(name):
    """Antique mirror: metallic, a bit of dust in the roughness, and glowing silver cracks revealed by a
    distance wave (value 'crackwave', origin set per frame) -> shot 26 chain reaction."""
    p = lib.crack_png(os.path.join(lib.TEX, "crack.png"))
    m = mat(name, (0.86, 0.88, 0.92), 0.03, metal=1.0)
    nt = m.node_tree
    b = lib._bsdf(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.45
    mr.inputs["From Max"].default_value = 0.75
    mr.inputs["To Min"].default_value = 0.02
    mr.inputs["To Max"].default_value = 0.16
    nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    # cracks
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = bpy.data.images.load(p, check_existing=True)
    tx.image.colorspace_settings.name = "Non-Color"
    tx.image.pack()
    uv = nt.nodes.new("ShaderNodeUVMap")
    nt.links.new(uv.outputs["UV"], tx.inputs["Vector"])
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    org = nt.nodes.new("ShaderNodeCombineXYZ"); org.name = "crackorigin"
    dist = nt.nodes.new("ShaderNodeVectorMath"); dist.operation = "DISTANCE"
    nt.links.new(oi.outputs["Location"], dist.inputs[0]); nt.links.new(org.outputs[0], dist.inputs[1])
    wave = nt.nodes.new("ShaderNodeValue"); wave.name = "crackwave"; wave.outputs[0].default_value = -10.0
    lt = nt.nodes.new("ShaderNodeMath"); lt.operation = "LESS_THAN"
    nt.links.new(dist.outputs["Value"], lt.inputs[0]); nt.links.new(wave.outputs[0], lt.inputs[1])
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
    nt.links.new(tx.outputs["Color"], mul.inputs[0]); nt.links.new(lt.outputs[0], mul.inputs[1])
    glow = nt.nodes.new("ShaderNodeValue"); glow.name = "crackglow"; glow.outputs[0].default_value = 8.0
    mul2 = nt.nodes.new("ShaderNodeMath"); mul2.operation = "MULTIPLY"
    nt.links.new(mul.outputs[0], mul2.inputs[0]); nt.links.new(glow.outputs[0], mul2.inputs[1])
    b.inputs["Emission Color"].default_value = (0.8, 0.88, 1.0, 1)
    nt.links.new(mul2.outputs[0], b.inputs["Emission Strength"])
    return m


def glass_window_mat(name):
    """'Glass' of a magic mirror: mostly transparent with a fresnel silver sheen, animated radial ripples
    (values 'rip_t', 'rip_amp', ripple centre in UV 'rip_u','rip_v') and an optional fog patch."""
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    uv = nt.nodes.new("ShaderNodeUVMap")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs[0])
    cu = nt.nodes.new("ShaderNodeValue"); cu.name = "rip_u"; cu.outputs[0].default_value = 0.5
    cv = nt.nodes.new("ShaderNodeValue"); cv.name = "rip_v"; cv.outputs[0].default_value = 0.5
    dx = nt.nodes.new("ShaderNodeMath"); dx.operation = "SUBTRACT"
    dy = nt.nodes.new("ShaderNodeMath"); dy.operation = "SUBTRACT"
    nt.links.new(sep.outputs["X"], dx.inputs[0]); nt.links.new(cu.outputs[0], dx.inputs[1])
    nt.links.new(sep.outputs["Y"], dy.inputs[0]); nt.links.new(cv.outputs[0], dy.inputs[1])
    asp = nt.nodes.new("ShaderNodeValue"); asp.name = "aspect"; asp.outputs[0].default_value = 2.0
    dy2 = nt.nodes.new("ShaderNodeMath"); dy2.operation = "MULTIPLY"
    nt.links.new(dy.outputs[0], dy2.inputs[0]); nt.links.new(asp.outputs[0], dy2.inputs[1])
    cmb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(dx.outputs[0], cmb.inputs[0]); nt.links.new(dy2.outputs[0], cmb.inputs[1])
    ln = nt.nodes.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"
    nt.links.new(cmb.outputs[0], ln.inputs[0])
    rt = nt.nodes.new("ShaderNodeValue"); rt.name = "rip_t"; rt.outputs[0].default_value = 0.0
    k1 = nt.nodes.new("ShaderNodeMath"); k1.operation = "MULTIPLY"; k1.inputs[1].default_value = 60.0
    nt.links.new(ln.outputs["Value"], k1.inputs[0])
    k2 = nt.nodes.new("ShaderNodeMath"); k2.operation = "MULTIPLY"; k2.inputs[1].default_value = 25.0
    nt.links.new(rt.outputs[0], k2.inputs[0])
    ph = nt.nodes.new("ShaderNodeMath"); ph.operation = "SUBTRACT"
    nt.links.new(k1.outputs[0], ph.inputs[0]); nt.links.new(k2.outputs[0], ph.inputs[1])
    sn = nt.nodes.new("ShaderNodeMath"); sn.operation = "SINE"
    nt.links.new(ph.outputs[0], sn.inputs[0])
    dec = nt.nodes.new("ShaderNodeMath"); dec.operation = "MULTIPLY"; dec.inputs[1].default_value = -6.0
    nt.links.new(ln.outputs["Value"], dec.inputs[0])
    ex = nt.nodes.new("ShaderNodeMath"); ex.operation = "EXPONENT"
    nt.links.new(dec.outputs[0], ex.inputs[0])
    amp = nt.nodes.new("ShaderNodeValue"); amp.name = "rip_amp"; amp.outputs[0].default_value = 0.0
    h1 = nt.nodes.new("ShaderNodeMath"); h1.operation = "MULTIPLY"
    nt.links.new(sn.outputs[0], h1.inputs[0]); nt.links.new(ex.outputs[0], h1.inputs[1])
    h2 = nt.nodes.new("ShaderNodeMath"); h2.operation = "MULTIPLY"
    nt.links.new(h1.outputs[0], h2.inputs[0]); nt.links.new(amp.outputs[0], h2.inputs[1])
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 1.0; bump.inputs["Distance"].default_value = 0.02
    nt.links.new(h2.outputs[0], bump.inputs["Height"])
    lw = nt.nodes.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.15
    nt.links.new(bump.outputs["Normal"], lw.inputs["Normal"])
    gl = nt.nodes.new("ShaderNodeBsdfGlossy"); gl.inputs["Roughness"].default_value = 0.02
    gl.inputs["Color"].default_value = (0.85, 0.9, 1.0, 1)
    nt.links.new(bump.outputs["Normal"], gl.inputs["Normal"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    fr = nt.nodes.new("ShaderNodeMath"); fr.operation = "ADD"; fr.inputs[1].default_value = 0.07
    nt.links.new(lw.outputs["Fresnel"], fr.inputs[0])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fr.outputs[0], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(gl.outputs[0], mix.inputs[2])
    # breath fog patch (value 'fog', centre 'fog_u','fog_v')
    fu = nt.nodes.new("ShaderNodeValue"); fu.name = "fog_u"; fu.outputs[0].default_value = 0.5
    fv = nt.nodes.new("ShaderNodeValue"); fv.name = "fog_v"; fv.outputs[0].default_value = 0.5
    fdx = nt.nodes.new("ShaderNodeMath"); fdx.operation = "SUBTRACT"
    fdy = nt.nodes.new("ShaderNodeMath"); fdy.operation = "SUBTRACT"
    nt.links.new(sep.outputs["X"], fdx.inputs[0]); nt.links.new(fu.outputs[0], fdx.inputs[1])
    nt.links.new(sep.outputs["Y"], fdy.inputs[0]); nt.links.new(fv.outputs[0], fdy.inputs[1])
    fdy2 = nt.nodes.new("ShaderNodeMath"); fdy2.operation = "MULTIPLY"
    nt.links.new(fdy.outputs[0], fdy2.inputs[0]); nt.links.new(asp.outputs[0], fdy2.inputs[1])
    fc = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(fdx.outputs[0], fc.inputs[0]); nt.links.new(fdy2.outputs[0], fc.inputs[1])
    fl = nt.nodes.new("ShaderNodeVectorMath"); fl.operation = "LENGTH"
    nt.links.new(fc.outputs[0], fl.inputs[0])
    fmr = nt.nodes.new("ShaderNodeMapRange")
    fmr.inputs["From Min"].default_value = 0.05
    fmr.inputs["From Max"].default_value = 0.22
    fmr.inputs["To Min"].default_value = 1.0
    fmr.inputs["To Max"].default_value = 0.0
    nt.links.new(fl.outputs["Value"], fmr.inputs["Value"])
    fog = nt.nodes.new("ShaderNodeValue"); fog.name = "fog"; fog.outputs[0].default_value = 0.0
    fm = nt.nodes.new("ShaderNodeMath"); fm.operation = "MULTIPLY"
    nt.links.new(fmr.outputs[0], fm.inputs[0]); nt.links.new(fog.outputs[0], fm.inputs[1])
    df = nt.nodes.new("ShaderNodeBsdfDiffuse"); df.inputs["Color"].default_value = (0.75, 0.8, 0.85, 1)
    mix2 = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fm.outputs[0], mix2.inputs["Fac"])
    nt.links.new(mix.outputs[0], mix2.inputs[1]); nt.links.new(df.outputs[0], mix2.inputs[2])
    # whole-surface silver glow (for the 'stepping out of glowing mirrors' shot)
    gv = nt.nodes.new("ShaderNodeValue"); gv.name = "glow"; gv.outputs[0].default_value = 0.0
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (0.8, 0.88, 1.0, 1)
    nt.links.new(gv.outputs[0], em.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(mix2.outputs[0], add.inputs[0]); nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def frame_rect(name, center, rz, w, h, thick=0.07, parent=None, m=None):
    """Gilded rectangular frame in the XZ plane of a local pivot (glass faces -Y)."""
    m = m or M()["gold"]
    piv = empty(name, center, parent, rot=(0, 0, D(rz)))
    for sx in (-1, 1):
        box(name + "_fv", (sx * (w / 2 + thick / 2), 0, 0), (thick, thick * 0.9, h + 2 * thick), m, piv, bevel=0.0)
    for sz in (-1, 1):
        box(name + "_fh", (0, 0, sz * (h / 2 + thick / 2)), (w + 2 * thick, thick * 0.9, thick), m, piv)
    # ornaments
    for sx in (-1, 1):
        for sz in (-1, 1):
            sphere(name + "_orn", (sx * (w / 2 + thick / 2), -thick * 0.4, sz * (h / 2 + thick / 2)), thick * 0.75, m, piv)
    sphere(name + "_crest", (0, -thick * 0.3, h / 2 + thick * 1.3), (thick * 1.6, thick * 0.6, thick * 1.0), m, piv)
    return piv


def plane_xz(name, center_local, w, h, m, parent):
    """UV plane in the XZ plane facing -Y (child of a pivot)."""
    o = obj(name, lib.m_plane_uv(1, 1), center_local, m, parent, rot=(D(90), 0, 0), scale=(w, h, 1))
    return o


def real_mirror(name, center, rz, w, h, parent=None, oval=False):
    piv = frame_rect(name, center, rz, w, h, thick=0.06 if w < 0.8 else 0.08, parent=parent)
    plane_xz(name + "_glass", (0, -0.005, 0), w, h, M()["mirror"], piv)
    box(name + "_back", (0, 0.03, 0), (w, 0.04, h), mat(name + "_bk", (0.05, 0.03, 0.02), 0.8), piv)
    R.setdefault("mirrors", []).append(piv)
    return piv


class MagicMirror:
    """A 'mirror' that is actually a window into a reflected copy of the set (collection instance with a
    reflection matrix). Characters placed behind it act as independent reflections."""

    def __init__(self, name, center, rz, w, h, collection=None, glass_coll=None, tunnel=None):
        self.c = Vector(center)
        self.rz = rz
        self.w, self.h = w, h
        n = Vector((math.sin(D(rz)), -math.cos(D(rz)), 0))  # glass faces -Y local -> world normal
        self.n = n
        self.M = lib.mirror_matrix(self.c, n)
        self.frame = frame_rect(name, center, rz, w, h, thick=0.09)
        prev = lib.COLL[0]
        lib.COLL[0] = glass_coll
        self.glass_mat = glass_window_mat(name + "_glassm")
        self.glass_mat.node_tree.nodes["aspect"].outputs[0].default_value = h / w
        self.glass = plane_xz(name + "_glass", (0, -0.004, 0), w, h, self.glass_mat, empty(name + "_gp", center, None, rot=(0, 0, D(rz))))
        lib.COLL[0] = prev
        # the 'reflected room': a tunnel behind the glass, exactly the size of the opening
        piv = empty(name + "_tun", center, None, rot=(0, 0, D(rz)))
        self.tunnel = piv
        depth = tunnel.get("depth", 2.4) if tunnel else 2.4
        wm = tunnel.get("wall") if tunnel else None
        wm = wm or mat(name + "_tw", (0.06, 0.06, 0.07), 0.8)
        fm = tunnel.get("floor") if tunnel else None
        fm = fm or wm
        hw, hh = w / 2 + 0.01, h / 2 + 0.01
        zc = 0.0
        if tunnel and tunnel.get("size"):  # wall-mounted: a whole reflected room (the wall hides the rest)
            tw, zb, zt = tunnel["size"]
            hw = tw / 2
            zc = (zb + zt) / 2
            hh = (zt - zb) / 2
        box(name + "_tl", (-hw - 0.02, depth / 2, zc), (0.04, depth, 2 * hh), wm, piv)
        box(name + "_tr", (hw + 0.02, depth / 2, zc), (0.04, depth, 2 * hh), wm, piv)
        box(name + "_tt", (0, depth / 2, zc + hh + 0.02), (2 * hw + 0.08, depth, 0.04), wm, piv)
        box(name + "_tb", (0, depth / 2, zc - hh - 0.02), (2 * hw + 0.08, depth, 0.04), fm, piv)
        box(name + "_tback", (0, depth, zc), (2 * hw, 0.04, 2 * hh), wm, piv)
        if tunnel and tunnel.get("frames"):
            r = random.Random(len(name))
            for k in range(3):
                frame_rect(name + "_tf", (r.uniform(-0.25, 0.25) * w, depth - 0.05, r.uniform(-0.2, 0.3) * h), 180, w * 0.25, h * 0.2, 0.025,
                           parent=piv, m=M()["gold_dark"])
        lc = tunnel.get("light", (1.0, 0.6, 0.3)) if tunnel else (1.0, 0.6, 0.3)
        le = tunnel.get("energy", 25) if tunnel else 25
        self.tlight = light(name + "_tlight", "POINT", (w * 0.3, depth * 0.45, h * 0.3), le, lc, size=0.05, parent=piv)
        light(name + "_tfill", "POINT", (-w * 0.3, 0.35, 0.0), le * 0.6, (0.75, 0.8, 1.0), size=0.2, parent=piv)
        self.inst = None

    def reflect_point(self, p):
        return self.M @ Vector(p)

    def reflect_facing(self, deg):
        f = Vector((math.sin(D(deg)), -math.cos(D(deg)), 0))
        fr = f - 2 * f.dot(self.n) * self.n
        return math.degrees(math.atan2(fr.x, -fr.y))

    def node(self, k):
        return self.glass_mat.node_tree.nodes[k].outputs[0]


# ------------------------------------------------------------------ world
def world():
    w = bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_WORLD":
            nt.nodes.remove(n)
    out = next(n for n in nt.nodes if n.type == "OUTPUT_WORLD")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    grad = nt.nodes.new("ShaderNodeValToRGB")
    grad.color_ramp.elements[0].color = (0.04, 0.05, 0.07, 1)
    grad.color_ramp.elements[1].position = 0.6
    grad.color_ramp.elements[1].color = (0.008, 0.01, 0.016, 1)
    nt.links.new(sep.outputs["Z"], grad.inputs["Fac"])
    bg = nt.nodes.new("ShaderNodeBackground"); bg.name = "bg"
    nt.links.new(grad.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    R["world"] = w


# ------------------------------------------------------------------ TOWN (rain)
PLASTER = [(0.40, 0.38, 0.36), (0.34, 0.33, 0.34), (0.30, 0.34, 0.36), (0.42, 0.36, 0.30), (0.33, 0.30, 0.34), (0.38, 0.38, 0.33)]


def house(x_face, side, yc, w, d, h, rng, Mt):
    cx = x_face + side * d / 2
    pl = Mt["plaster"][rng.randrange(len(Mt["plaster"]))]
    box("house", (cx, yc, h / 2), (d, w, h), pl)
    obj("roof", lib.m_prism(), (cx, yc, h - 0.02), Mt["roof"], scale=(d + 0.4, w + 0.35, w * 0.55))
    for z in [z for z in (2.9, 5.6, 8.3) if z < h - 0.4]:
        box("beam", (x_face - side * 0.06, yc, z), (0.12, w + 0.02, 0.16), Mt["timber"])
    floors = [z for z in (1.6, 4.25, 6.9) if z < h - 1.0]
    cols = [yc - w * 0.25, yc + w * 0.25] if w > 3.6 else [yc]
    for fz in floors:
        for yy in cols:
            if fz < 2 and abs(yy - cols[0]) < 0.01 and len(cols) > 1:
                box("door", (x_face - side * 0.03, yy, 1.05), (0.08, 1.0, 2.1), Mt["door"])
                continue
            lit = rng.random() < 0.4
            box("win", (x_face - side * 0.035, yy, fz + 0.15), (0.05, 0.8, 1.15), Mt["win_lit" if lit else "win_dark"])
            box("sill", (x_face - side * 0.08, yy, fz - 0.47), (0.16, 0.95, 0.07), Mt["timber"])
            for sy in (-1, 1):
                box("shutter", (x_face - side * 0.06, yy + sy * 0.62, fz + 0.15), (0.05, 0.4, 1.2), Mt["shutter"])


def town():
    rng = random.Random(21)
    Mt = {
        "plaster": [lib.noise_mat(f"plaster{i}", c, tuple(x * 0.8 for x in c), scale=3, rough=0.6, bump=0.15) for i, c in enumerate(PLASTER)],
        "roof": lib.noise_mat("rooftiles", (0.12, 0.10, 0.10), (0.20, 0.16, 0.15), scale=9, rough=0.35, bump=0.4, kind="wave"),
        "timber": mat("timber", (0.07, 0.05, 0.04), 0.5),
        "shutter": mat("shutter", (0.10, 0.14, 0.16), 0.6),
        "door": mat("door", (0.12, 0.07, 0.04), 0.5),
        "win_lit": mat("win_lit", (0.9, 0.6, 0.3), 0.1, emit=(1.0, 0.62, 0.3), emit_str=2.5),
        "win_dark": mat("win_dark", (0.03, 0.03, 0.04), 0.05),
    }
    R["win_lit"] = Mt["win_lit"]
    cob = lib.cobble_mat("cobble", 0.33)
    lib._bsdf(cob).inputs["Roughness"].default_value = 0.12
    box("street", (0, 20, -0.05), (30, 100, 0.1), cob)
    # puddles with rain ripples
    pud = mat("puddle", (0.02, 0.02, 0.025), 0.02)
    nt = pud.node_tree
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.noise_dimensions = "4D"; nz.inputs["Scale"].default_value = 40; nz.name = "rain_noise"
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    bp = nt.nodes.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.15
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], lib._bsdf(pud).inputs["Normal"])
    R["puddle"] = pud
    for k in range(18):
        cyl("puddle", (rng.uniform(-2.8, 2.8), rng.uniform(-6, 50), 0.003), rng.uniform(0.5, 1.4), 0.004, pud, seg=24).scale.y *= rng.uniform(0.5, 1.6)
    for side in (1, -1):
        y = -14.0
        while y < 52:
            w = rng.uniform(4.2, 5.8)
            if side == 1 and y < 14 and y + w > 10:
                if y < 10:
                    w = 10 - y
                    if w < 2.5:
                        y = 14.0
                        continue
                else:
                    y = 14.0
                    continue
            if side == -1 and y < 30 and y + w > 26:
                if y < 26:
                    w = 26 - y
                    if w < 2.5:
                        y = 30.0
                        continue
                else:
                    y = 30.0
                    continue
            house(4.0 * side, side, y + w / 2, w, 7.0, rng.uniform(6.0, 9.0), rng, Mt)
            y += w
    # the mirror shop facade (right side, y 10..14): silver glowing window
    wood = mat("shopwood", (0.03, 0.03, 0.035), 0.4)
    box("shopbody", (7.7, 12, 2.6), (7.2, 4.0, 5.2), wood)
    obj("shoproof", lib.m_prism(), (7.7, 12, 5.18), Mt["roof"], scale=(7.6, 4.4, 2.2))
    win = mat("shopwin", (0.6, 0.65, 0.75), 0.05, emit=(0.75, 0.82, 1.0), emit_str=3.0)
    R["shop_win"] = win
    box("shopwin", (4.05, 11.4, 1.6), (0.04, 2.4, 2.0), win)
    for k in range(5):  # mirror silhouettes in the window
        frame_rect("winframe", (4.0, 10.6 + k * 0.42, 1.7 + 0.25 * math.sin(k * 1.7)), 90, 0.25, 0.42, 0.03, m=M()["gold_dark"])
    box("shopdoor", (4.05, 13.4, 1.1), (0.08, 0.9, 2.2), Mt["door"])
    signm = mat("sign", (0.04, 0.04, 0.05), 0.4)
    box("signboard", (3.1, 12.8, 3.2), (0.06, 1.5, 0.6), signm)
    box("signarm", (3.4, 12.8, 3.6), (1.3, 0.05, 0.05), Mt["timber"])
    text("signtext", "ДЗЕРКАЛА", (3.06, 12.8, 3.2), 0.18, emit("signsilver", (0.8, 0.86, 1.0), 2.5), rot=(D(90), 0, D(-90)))
    light("shopglow", "AREA", (3.2, 11.4, 1.7), 220, (0.7, 0.8, 1.0), size=2.2, rot=(0, D(-90), 0))
    # Tim's house (left side, gap y 26..30): warm open doorway
    home = mat("homeplaster", (0.45, 0.38, 0.30), 0.6)
    box("home", (-7.5, 28, 3.5), (7.0, 4.0, 7.0), home)
    obj("homeroof", lib.m_prism(), (-7.5, 28, 6.98), Mt["roof"], scale=(7.4, 4.4, 2.2))
    box("homedoorglow", (-4.02, 28, 1.1), (0.04, 1.0, 2.15), emit("homedoor", (1.0, 0.65, 0.3), 4.0))
    light("homedoorl", "AREA", (-3.6, 28, 1.3), 120, (1.0, 0.65, 0.3), size=1.0, rot=(0, D(90), 0))
    # street lamps
    iron = mat("iron", (0.03, 0.03, 0.035), 0.3, metal=0.8)
    lampm = emit("lampglass", (1.0, 0.65, 0.32), 12.0)
    R["lamp_mat"] = lampm
    R["lamps"] = []
    for side in (1, -1):
        for y in range(-6, 52, 9):
            yy = y + (4.5 if side < 0 else 0)
            x = side * 3.2
            cyl("pole", (x, yy, 1.5), 0.05, 3.0, iron)
            box("lantern", (x, yy, 3.15), (0.24, 0.24, 0.34), lampm)
            obj("lampcap", lib.m_prism(), (x, yy, 3.32), iron, scale=(0.32, 0.32, 0.18))
            R["lamps"].append(light("lamp", "POINT", (x, yy, 3.0), 80, (1.0, 0.62, 0.3), size=0.12))
    moon = light("moonlight", "SUN", (0, 0, 30), 0.25, (0.6, 0.7, 1.0), size=0.02)
    moon.rotation_euler = (D(55), 0, D(195))
    fogm = lib.volume_mat("townfog", (0.62, 0.68, 0.8), density=0.028, anisotropy=0.45)
    box("townfog", (0, 20, 4), (28, 90, 8), fogm)


# ------------------------------------------------------------------ SHOP interior (mirrors)
X0 = 100.0


def shop():
    rng = random.Random(4)
    x0 = X0
    C = coll("SHOPC")
    G = coll("SHOPGLASS")
    lib.COLL[0] = C
    floor = lib.noise_mat("planks", (0.10, 0.06, 0.04), (0.20, 0.12, 0.07), scale=3, rough=0.4, bump=0.2, kind="wave")
    wall = lib.noise_mat("shopwall", (0.07, 0.07, 0.08), (0.12, 0.11, 0.12), scale=4, rough=0.8, bump=0.15)
    box("sfloor", (x0, 4, -0.05), (4.4, 8.4, 0.1), floor)
    box("sceil", (x0, 4, 3.25), (4.4, 8.4, 0.1), wall)
    box("sback", (x0, 8.05, 1.6), (4.4, 0.1, 3.3), wall)
    box("swl", (x0 - 2.05, 4, 1.6), (0.1, 8.4, 3.3), wall)
    box("swr", (x0 + 2.05, 4, 1.6), (0.1, 8.4, 3.3), wall)
    # front wall with door (x 99.6..100.4)
    box("sf1", (x0 - 1.2, -0.05, 1.6), (1.6, 0.1, 3.3), wall)
    box("sf2", (x0 + 1.2, -0.05, 1.6), (1.6, 0.1, 3.3), wall)
    box("sf3", (x0, -0.05, 2.75), (0.8, 0.1, 1.1), wall)
    lib.COLL[0] = G  # door + outside are not part of the reflected world
    hinge = empty("sdoorhinge", (x0 - 0.4, -0.02, 0))
    dm = mat("sdoor", (0.08, 0.05, 0.03), 0.5)
    box("sdoor", (0.4, 0, 1.1), (0.8, 0.06, 2.2), dm, hinge)
    box("sdoorwin", (0.4, 0.035, 1.6), (0.4, 0.01, 0.5), emit("sdoorwin", (0.3, 0.42, 0.7), 1.2), hinge)
    R["shop_door"] = hinge
    bellp = empty("sbell", (x0 + 0.3, 0.1, 2.15))
    lib.lathe("sbellcup", (0, 0, -0.03), [(0.01, 0.0), (0.03, -0.01), (0.04, -0.05), (0.05, -0.075), (0.035, -0.075)], M()["gold"], bellp)
    R["shop_bell"] = bellp
    light("sdoorback", "AREA", (x0, -1.6, 1.5), 700, (0.5, 0.62, 1.0), size=1.5, rot=(D(-90), 0, 0))
    box("sdoorout", (x0, -3.0, 1.7), (4, 0.1, 4), emit("snight2", (0.07, 0.10, 0.18), 1.0))
    fo = lib.volume_mat("sdoorfog", (0.6, 0.7, 0.9), density=0.3, anisotropy=0.5)
    box("sdoorfogbox", (x0, -1.0, 1.5), (2.4, 1.8, 3.0), fo)
    lib.COLL[0] = C
    # mirrors on the walls (real reflective)
    for side in (-1, 1):
        y = 1.0
        while y < 7.4:
            w = rng.uniform(0.35, 0.65)
            h = rng.uniform(0.5, 1.1)
            z = rng.uniform(1.0, 2.2)
            if side == -1 and 6.2 < y < 7.9:  # leave the corner for the tall mirror
                y += w + 0.1
                continue
            real_mirror("wm", (x0 + side * 1.97, y + w / 2, z), -90 * side, w, h)
            if rng.random() < 0.6:
                w2 = rng.uniform(0.25, 0.4)
                real_mirror("wm", (x0 + side * 1.97, y + w / 2 + rng.uniform(-0.05, 0.05), z + h / 2 + 0.45 + rng.uniform(0, 0.2)), -90 * side, w2, w2 * 1.3)
            y += w + rng.uniform(0.15, 0.3)
    for k in range(5):
        w = rng.uniform(0.4, 0.6)
        real_mirror("bm", (x0 - 0.9 + k * 0.45 + rng.uniform(-0.05, 0.05), 7.97, rng.uniform(1.6, 2.5)), 0, w * 0.7, w)
    # counter + candles
    wood = lib.noise_mat("counter", (0.10, 0.05, 0.03), (0.18, 0.09, 0.05), scale=6, rough=0.35, bump=0.1, kind="wave")
    box("counter", (x0 + 0.9, 6.4, 0.5), (2.0, 0.6, 1.0), wood)
    box("countertop", (x0 + 0.9, 6.4, 1.02), (2.1, 0.7, 0.05), wood)
    wax = mat("wax", (0.95, 0.88, 0.70), 0.4, sss=0.5)
    R["candles"] = []
    for k, (cx, cy, cz) in enumerate(((x0 + 0.2, 6.25, 1.05), (x0 + 1.7, 6.3, 1.05), (x0 - 1.7, 2.0, 1.4), (x0 + 1.7, 4.2, 1.3), (x0 - 1.7, 5.0, 1.3))):
        cyl("candle", (cx, cy, cz + 0.07), 0.022, 0.14, wax, seg=16)
        fl = sphere("flame", (cx, cy, cz + 0.17), (0.011, 0.011, 0.028), emit("flame", (1.0, 0.55, 0.15), 30.0))
        L = light("candlel", "POINT", (cx, cy, cz + 0.22), 16, (1.0, 0.55, 0.22), size=0.02)
        R["candles"].append((L, fl))
        if k >= 2:
            box("bracket", (cx + (0.08 if cx < x0 else -0.08), cy, cz - 0.01), (0.18, 0.06, 0.02), M()["gold_dark"])
    # mirror being polished on the counter + wrapped mirrors
    real_mirror("polish", (x0 + 1.0, 6.25, 1.32), -15, 0.35, 0.45)
    paper = lib.noise_mat("paper", (0.55, 0.42, 0.28), (0.62, 0.50, 0.34), scale=20, rough=0.9, bump=0.2)
    R["paper"] = paper
    for k in range(3):
        box("wrapped", (x0 + 1.6, 3.0 + k * 0.25, 0.45), (0.06, 0.5, 0.9), paper, rot=(0, D(-8), 0))
    # stool (Tim grabs it)
    stool = empty("stool", (x0 + 0.8, 4.6, 0))
    for sx in (-1, 1):
        for sy in (-1, 1):
            box("stoolleg", (sx * 0.12, sy * 0.12, 0.22), (0.04, 0.04, 0.44), wood, stool, rot=(D(sy * 5), D(-sx * 5), 0))
    cyl("stoolseat", (0, 0, 0.46), 0.18, 0.04, wood, stool, seg=24)
    R["stool"] = stool
    light("sfill", "AREA", (x0, 1.0, 3.0), 120, (1.0, 0.7, 0.45), size=2.5, rot=(D(30), 0, 0))
    light("sfill2", "AREA", (x0, 5.0, 3.1), 90, (1.0, 0.68, 0.42), size=2.5, rot=(0, 0, 0))
    light("smoon", "AREA", (x0 + 1.9, 3.5, 2.8), 40, (0.6, 0.7, 1.0), size=1.5, rot=(0, D(-60), 0))
    hz = lib.volume_mat("shaze", (0.85, 0.85, 0.9), density=0.018, anisotropy=0.35)
    box("shazebox", (x0, 4.0, 1.6), (3.9, 7.9, 3.2), hz)
    lib.COLL[0] = None
    # the tall old mirror in the back-left corner (magic: window into the reflected shop)
    tall = MagicMirror("tall", (x0 - 1.05, 6.6, 1.15), 15, 0.85, 1.9, C, G,
                       tunnel=dict(wall=wall, floor=floor, frames=True, energy=30, depth=1.35))
    R["tall"] = tall
    cloth = lib.lathe("cloth", (0, 0, 0), [(0.02, 0.0), (0.4, -0.05), (0.5, -0.6), (0.55, -1.2), (0.5, -1.3)], M()["black_cloth"], None)
    cloth.parent = tall.frame
    cloth.location = (0.2, -0.08, 0.6)
    cloth.rotation_euler = (D(5), D(-25), 0)
    cloth.scale = (0.85, 0.25, 1.0)
    R["cloth"] = cloth
    box("tallstand", (x0 - 1.05, 6.6, 0.1), (0.9, 0.3, 0.2), M()["gold_dark"], rot=(0, 0, D(15)))
    # small standing mirror with a lagging reflection (shot 4)
    lag = MagicMirror("lag", (x0 + 1.2, 2.6, 1.45), -60, 0.45, 0.6, C, G, tunnel=dict(wall=wall, frames=True, energy=20, depth=1.6))
    R["lag"] = lag
    cyl("lagstand", (x0 + 1.2, 2.6, 0.55), 0.03, 1.1, M()["gold_dark"], seg=12)
    cyl("lagbase", (x0 + 1.2, 2.6, 0.02), 0.2, 0.04, M()["gold_dark"], seg=24)


# ------------------------------------------------------------------ HOME (doorway + hallway)
X1 = 200.0


def home():
    x1 = X1
    C = coll("HOMEC")
    G = coll("HOMEGLASS")
    lib.COLL[0] = C
    floor = lib.noise_mat("hplanks", (0.30, 0.18, 0.10), (0.42, 0.27, 0.15), scale=3, rough=0.45, bump=0.2, kind="wave")
    wallp = lib.noise_mat("hwall", (0.62, 0.50, 0.36), (0.70, 0.58, 0.42), scale=40, rough=0.8, bump=0.1, kind="wave")
    # hallway: x 199..201, y 0..5 ; front door at y=0 opening to the rainy porch (y<0)
    box("hfloor", (x1, 2.5, -0.05), (2.4, 5.2, 0.1), floor)
    box("hceil", (x1, 2.5, 2.65), (2.4, 5.2, 0.1), wallp)
    # left wall with an opening for the small mirror (y 2.19..2.61, z 1.14..1.76)
    box("hwl1", (x1 - 1.05, 1.07, 1.3), (0.1, 2.24, 2.7), wallp)
    box("hwl2", (x1 - 1.05, 3.83, 1.3), (0.1, 2.44, 2.7), wallp)
    box("hwl3", (x1 - 1.05, 2.4, 0.57), (0.1, 0.42, 1.14), wallp)
    box("hwl4", (x1 - 1.05, 2.4, 2.2), (0.1, 0.42, 0.88), wallp)
    box("hwr", (x1 + 1.05, 2.5, 1.3), (0.1, 5.2, 2.7), wallp)
    box("hback", (x1, 5.05, 1.3), (2.2, 0.1, 2.7), wallp)
    box("hf1", (x1 - 0.75, -0.05, 1.3), (0.6, 0.1, 2.7), wallp)
    box("hf2", (x1 + 0.75, -0.05, 1.3), (0.6, 0.1, 2.7), wallp)
    box("hf3", (x1, -0.05, 2.45), (0.9, 0.1, 0.4), wallp)
    tim_ = mat("htrim", (0.35, 0.22, 0.12), 0.5)
    box("hskirting", (x1 - 0.99, 2.5, 0.06), (0.03, 5.0, 0.12), tim_)
    box("hskirting", (x1 + 0.99, 2.5, 0.06), (0.03, 5.0, 0.12), tim_)
    # coat rack, rug, lamp
    rug = lib.noise_mat("hrug", (0.45, 0.12, 0.08), (0.7, 0.45, 0.18), scale=8, rough=0.95, bump=0.2, kind="wave")
    box("hrug", (x1, 2.0, 0.005), (1.1, 2.2, 0.01), rug)
    for k in range(3):
        sphere("hook", (x1 + 0.98, 1.3 + k * 0.3, 1.7), 0.025, M()["gold_dark"])
    box("coat", (x1 + 0.92, 1.6, 1.25), (0.12, 0.5, 0.9), mat("hcoat", (0.2, 0.25, 0.35), 0.8))
    lampm = emit("hlampm", (1.0, 0.7, 0.4), 6.0)
    sphere("hlamp", (x1, 2.6, 2.45), 0.12, lampm)
    R["home_lamp"] = light("hlampl", "POINT", (x1, 2.6, 2.3), 90, (1.0, 0.68, 0.38), size=0.2)
    light("hkitchen", "AREA", (x1, 4.6, 1.5), 200, (1.0, 0.65, 0.32), size=1.5, rot=(D(90), 0, 0))
    lib.COLL[0] = G
    # porch outside (rain), door open
    hinge = empty("hdoorhinge", (x1 - 0.45, 0.0, 0), rot=(0, 0, D(-100)))
    box("hdoor", (0.45, 0, 1.08), (0.9, 0.06, 2.15), mat("hdoorm", (0.35, 0.12, 0.08), 0.5), hinge)
    box("hporch", (x1, -1.5, -0.05), (4, 3, 0.1), lib.cobble_mat("cobble2", 0.33))
    box("hfacade", (x1 - 1.3, -0.12, 1.5), (1.6, 0.1, 3.0), mat("hfac", (0.42, 0.36, 0.28), 0.6))
    box("hfacade2", (x1 + 1.3, -0.12, 1.5), (1.6, 0.1, 3.0), mat("hfac", (0.42, 0.36, 0.28), 0.6))
    box("hnight", (x1, -6, 2), (12, 0.1, 6), emit("hnightm", (0.04, 0.06, 0.1), 1.0))
    light("hporchl", "AREA", (x1, -2.5, 2.5), 80, (0.5, 0.6, 0.9), size=2.0, rot=(D(-50), 0, 0))
    light("hporchkey", "AREA", (x1 + 0.6, -1.2, 1.9), 220, (1.0, 0.75, 0.5), size=0.8, rot=(D(-60), 0, D(30)))
    lib.COLL[0] = None
    # small hallway mirror on the left wall (magic)
    hm = MagicMirror("hallmirror", (x1 - 0.98, 2.4, 1.45), 90, 0.42, 0.62, C, G,
                     tunnel=dict(wall=wallp, floor=floor, energy=60, depth=2.2, size=(3.0, -1.45, 1.15)))
    R["hallmirror"] = hm


# ------------------------------------------------------------------ VOID (end card)
X2 = 300.0


def void():
    x2 = X2
    C = coll("VOIDC")
    lib.COLL[0] = C
    black = mat("void", (0, 0, 0), 1.0, spec=0.0)
    sphere("voidsphere", (x2, 0, 1), 12, black)
    R["voidkey"] = light("voidkey", "SPOT", (x2 - 0.6, -1.4, 2.3), 0, (0.7, 0.8, 1.0), size=0.2, spot=D(45))
    lib.aim(R["voidkey"], (x2, 0, 1.4))
    R["voidface"] = light("voidface", "AREA", (x2 + 0.3, -1.0, 1.4), 0, (0.8, 0.85, 1.0), size=0.5)
    lib.aim(R["voidface"], (x2, -0.3, 1.2))
    lib.COLL[0] = None
    vm = MagicMirror("voidmirror", (x2, 0.0, 1.35), 0, 0.5, 0.75, C, None, tunnel=dict(wall=black, energy=15, depth=1.6))
    R["voidmirror"] = vm


# ------------------------------------------------------------------ WALL (people trapped behind glass)
X3 = 400.0


def wall():
    x3 = X3
    wallm = mat("darkwall", (0.03, 0.03, 0.035), 0.6)
    R["wallcells"] = []
    for k in range(6):
        cx = x3 - 1.5 + (k % 3) * 1.5
        cz = 1.5 + (k // 3) * 1.6
        fr = frame_rect("wf", (cx, 0, cz), 0, 1.0, 1.3, thick=0.09)
        gm = glass_window_mat(f"wallglass{k}")
        gm.node_tree.nodes["aspect"].outputs[0].default_value = 1.3
        g = plane_xz(f"wallglass{k}", (0, -0.004, 0), 1.0, 1.3, gm, fr)
        # cold silvery box behind
        cm = mat(f"cell{k}", (0.35, 0.38, 0.45), 0.6)
        box("cellback", (cx, 0.9, cz), (1.0, 0.05, 1.3), cm)
        box("cellside", (cx - 0.52, 0.45, cz), (0.05, 0.9, 1.3), cm)
        box("cellside", (cx + 0.52, 0.45, cz), (0.05, 0.9, 1.3), cm)
        box("cellfl", (cx, 0.45, cz - 0.67), (1.0, 0.9, 0.05), cm)
        box("celltop", (cx, 0.45, cz + 0.67), (1.0, 0.9, 0.05), cm)
        light("celllight", "AREA", (cx, 0.5, cz + 0.6), 25, (0.7, 0.8, 1.0), size=0.8, rot=(0, 0, 0))
        R["wallcells"].append(dict(c=Vector((cx, 0, cz)), glass=gm))
    box("wallbg", (x3, 1.0, 2.4), (5.5, 0.05, 5), wallm)
    light("wallkey", "AREA", (x3, -2.5, 3.0), 80, (1.0, 0.7, 0.4), size=3.0, rot=(D(60), 0, 0))
