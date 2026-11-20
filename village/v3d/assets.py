"""Реалістичні асети: фототекстури й моделі Poly Haven (CC0), персонажі Sketchfab (CC-BY),
перенесені анімації Mixamo. Шляхи до завантажених файлів — у ASSETS (див. fetch_assets.sh).

Автори моделей Sketchfab (CC-BY 4.0) перелічені в village/CREDITS.md.
"""
import math
import os
import random
import re

import bpy
from mathutils import Vector

from lib import link, setp

ASSETS = os.environ.get("V3D_ASSETS", "/tmp/claude-0/assets")
SRC_FPS = 30.0


# --------------------------------------------------------------------------
# Текстури
# --------------------------------------------------------------------------
_TEX = {}


def tex_mat(name, folder, scale=1.0, tint=(1, 1, 1), rough_k=1.0, bump=0.6, coords="UV", gloss=None):
    key = (name, folder, scale, tuple(tint))
    if key in _TEX:
        return _TEX[key]
    base = os.path.join(ASSETS, "tex", folder)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (scale, scale, scale)
    nt.links.new(tc.outputs[coords], mp.inputs["Vector"])

    def img(fname, noncolor=False):
        p = os.path.join(base, fname)
        if not os.path.exists(p):
            return None
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(p, check_existing=True)
        if noncolor:
            n.image.colorspace_settings.name = "Non-Color"
        if coords == "Object":
            n.projection = "BOX"
            n.projection_blend = 0.2
        nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        return n
    d = img("diff.jpg")
    if d:
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs["B"].default_value = (*tint, 1)
        nt.links.new(d.outputs["Color"], mix.inputs["A"])
        nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
    r = img("rough.jpg", True)
    if r:
        mr = nt.nodes.new("ShaderNodeMath")
        mr.operation = "MULTIPLY"
        mr.inputs[1].default_value = rough_k
        nt.links.new(r.outputs["Color"], mr.inputs[0])
        nt.links.new(mr.outputs[0], b.inputs["Roughness"])
    nrm = img("nor.jpg", True)
    if nrm:
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = bump
        nt.links.new(nrm.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    _TEX[key] = m
    return m


def TM():
    return dict(
        forest=tex_mat("t_forest", "forest_ground_04", 40, (0.8, 0.85, 0.8)),
        leaves=tex_mat("t_leaves", "forest_leaves_03", 40),
        mud=tex_mat("t_mud", "brown_mud_leaves_01", 30),
        track=tex_mat("t_track", "muddy_tracks", 1.0, coords="Object"),
        plaster=tex_mat("t_plaster", "white_plaster_rough_02", 0.35, (1.0, 0.97, 0.9), coords="Object"),
        plaster_old=tex_mat("t_plaster_old", "worn_mossy_plasterwall", 0.3, coords="Object"),
        thatch=tex_mat("t_thatch", "thatch_roof_angled", 0.4, coords="Object", bump=1.0),
        floor=tex_mat("t_floor", "old_wooden_floor_02", 0.5, coords="Object"),
        planks=tex_mat("t_planks", "wood_planks_grey", 0.8, (0.8, 0.7, 0.6), coords="Object"),
        mosswood=tex_mat("t_mosswood", "moss_wood", 1.5, coords="Object"),
    )


def hdri_world(name="moonlit_golf", strength=0.6, rot=0.0, tint=(1, 1, 1), bg_strength=None):
    sc = bpy.context.scene
    w = bpy.data.worlds.new("w_" + name)
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(os.path.join(ASSETS, "hdri", name + ".hdr"), check_existing=True)
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, rot)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    mix.inputs["B"].default_value = (*tint, 1)
    nt.links.new(env.outputs["Color"], mix.inputs["A"])
    nt.links.new(mix.outputs["Result"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength
    return w


# --------------------------------------------------------------------------
# Моделі з .blend / glTF
# --------------------------------------------------------------------------
def append_blend(path, kinds=("objects", "actions")):
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        for k in kinds:
            setattr(dst, k, list(getattr(src, k)))
    objs = [o for o in dst.objects if o is not None] if "objects" in kinds else []
    for o in objs:
        link(o)
    return objs, (list(dst.actions) if "actions" in kinds else [])


_FIR = {}


def fir_meshes():
    if _FIR:
        return _FIR["m"]
    with bpy.data.libraries.load(os.path.join(ASSETS, "fir_tree_01.blend"), link=False) as (src, dst):
        dst.meshes = [n for n in src.meshes]
    ms = [m for m in dst.meshes if m is not None]
    # висота сирого меша (м)
    hs = []
    for m in ms:
        zs = [v.co.z for v in m.vertices]
        ys = [v.co.y for v in m.vertices]
        hs.append(max(max(zs) - min(zs), max(ys) - min(ys)))
    _FIR["m"] = list(zip(ms, hs))
    return _FIR["m"]


def fir(loc, h, rot=0.0, variant=None, rng=None):
    ms = fir_meshes()
    r = rng or random
    m, mh = ms[variant if variant is not None else r.randrange(len(ms))]
    o = bpy.data.objects.new("fir", m)
    k = h / max(mh, 1e-6)
    o.scale = (k, k, k)
    # glTF Y-up у мешах: якщо висота по Y — повертаємо
    zs = [v.co.z for v in m.vertices[:2000]]
    ys = [v.co.y for v in m.vertices[:2000]]
    upright = (max(ys) - min(ys)) > (max(zs) - min(zs))
    o.rotation_euler = (math.pi / 2 if upright else 0, 0, rot)
    o.location = loc
    return link(o)


def fir_forest(area, n, hmin=12, hmax=24, avoid=None, seed=0, near=None, near_n=0):
    """Справжні ялини (Poly Haven) — n штук у межах area."""
    r = random.Random(seed)
    placed, tries = 0, 0
    while placed < n and tries < n * 30:
        tries += 1
        if near and placed < near_n:
            cx, cy, rad = near
            x, y = cx + r.uniform(-rad, rad), cy + r.uniform(-rad, rad)
        else:
            x, y = r.uniform(area[0], area[1]), r.uniform(area[2], area[3])
        if avoid and avoid(x, y):
            continue
        fir((x, y, -0.2), r.uniform(hmin, hmax), r.uniform(0, 6.28), rng=r)
        placed += 1


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def ph_model(aid, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0):
    objs = import_glb(os.path.join(ASSETS, "ph", aid, aid + ".gltf"))
    root = bpy.data.objects.new(aid, None)
    link(root)
    for o in objs:
        if o.parent is None:
            o.parent = root
    root.location = loc
    root.rotation_euler = rot
    root.scale = (scale, scale, scale)
    return root, objs


# --------------------------------------------------------------------------
# Персонажі
# --------------------------------------------------------------------------
class Human:
    """Персонаж із перенесеними анімаціями (marvin = Андрій, hendrik = селянин)."""

    def __init__(self, who="marvin", name="a", height=1.8, tint=None):
        objs, acts = append_blend(os.path.join(ASSETS, who + ".blend"))
        arms = [o for o in objs if o.type == "ARMATURE"]
        # скелет, на який записані анімації (в ньому є кістки mixamorig:Hips з ключами)
        self.arm = next((o for o in arms if "mixamorig:Hips" in o.data.bones), arms[0])
        keep, drop = [], []
        for o in objs:
            if o.type == "MESH":
                mods = [m for m in o.modifiers if m.type == "ARMATURE"]
                if mods and any(m.object == self.arm for m in mods):
                    keep.append(o)
                else:
                    drop.append(o)
            elif o.type == "ARMATURE" and o != self.arm:
                drop.append(o)
        objs = [o for o in objs if o not in drop]
        for o in drop:
            bpy.data.objects.remove(o, do_unlink=True)
        self.meshes = keep
        self.acts = {re.sub(r"\.\d+$", "", a.name.split("_", 1)[1]).lower(): a for a in acts if "_" in a.name}
        self.root = bpy.data.objects.new(name + "_root", None)
        link(self.root)
        for o in objs:
            if o.parent is None:
                o.parent = self.root
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(c) for o in self.meshes for c in o.bound_box]
        hgt = max(p.z for p in pts) - min(p.z for p in pts)
        self.zoff = -min(p.z for p in pts)
        k = height / max(hgt, 1e-6)
        self.k = k
        self.root.scale = (k, k, k)
        self.arm.animation_data_create()
        self.track = self.arm.animation_data.nla_tracks.new()
        if tint:
            self.tint(tint)

    def tint(self, rgb, match=None):
        """Перефарбовує одяг (множенням) — напр. жилет Марвіна в олівковий."""
        for o in self.meshes:
            for i, m in enumerate(o.data.materials):
                if m is None or (match and match not in m.name.lower()):
                    continue
                m2 = m.copy()
                b = next((n for n in m2.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
                if b is None or not b.inputs["Base Color"].links:
                    continue
                src = b.inputs["Base Color"].links[0].from_socket
                mix = m2.node_tree.nodes.new("ShaderNodeMix")
                mix.data_type = "RGBA"
                mix.blend_type = "MULTIPLY"
                mix.inputs["Factor"].default_value = 1.0
                mix.inputs["B"].default_value = (*rgb, 1)
                m2.node_tree.links.new(src, mix.inputs["A"])
                m2.node_tree.links.new(mix.outputs["Result"], b.inputs["Base Color"])
                o.data.materials[i] = m2

    def play(self, action, f0, f1, speed=1.0, offset=0.0):
        act = self.acts.get(action.lower())
        if act is None:
            return None
        fps = bpy.context.scene.render.fps
        st = self.track.strips.new(f"{action}_{f0}", int(f0), act)
        try:
            if act.slots:
                st.action_slot = act.slots[0]
        except Exception:
            pass
        a0, a1 = act.frame_range
        st.action_frame_start = a0 + offset
        st.action_frame_end = a1
        st.scale = fps / SRC_FPS / speed
        one = max((a1 - a0 - offset) * st.scale, 1e-3)
        st.repeat = max(1.0, (f1 - f0) / one)
        st.extrapolation = "HOLD"
        return st

    def place(self, loc, yaw_deg):
        self.root.location = Vector(loc) + Vector((0, 0, self.zoff * self.k))
        self.root.rotation_euler = (0, 0, math.radians(yaw_deg))

    def path(self, pts, f0, f1, yaw_fix=0.0):
        P = [Vector(p) for p in pts]
        L = [0.0]
        for a, b in zip(P, P[1:]):
            L.append(L[-1] + (b - a).length)
        tot = max(L[-1], 1e-6)
        for f in range(f0, f1 + 1):
            u = (f - f0) / max(f1 - f0, 1)
            d = u * tot
            i = min(max(j for j in range(len(L)) if L[j] <= d + 1e-9), len(P) - 2)
            seg = max(L[i + 1] - L[i], 1e-6)
            self.root.location = P[i].lerp(P[i + 1], (d - L[i]) / seg) + Vector((0, 0, self.zoff * self.k))
            dv = P[i + 1] - P[i]
            self.root.rotation_euler = (0, 0, math.atan2(dv.y, dv.x) - math.pi / 2 + math.radians(yaw_fix))
            self.root.keyframe_insert("location", frame=f)
            self.root.keyframe_insert("rotation_euler", frame=f)

    def bone_world(self, key):
        bpy.context.view_layer.update()
        b = next(b for b in self.arm.pose.bones if b.name.lower().endswith(key.lower()))
        return self.arm.matrix_world @ b.head


class Hanna:
    """Ганна — статична реалістична модель (стоїть / в дверях)."""

    def __init__(self, loc=(0, 0, 0), yaw=180, height=1.6, name="hanna"):
        objs = import_glb(os.path.join(ASSETS, "glb", "bluedress.glb"))
        for o in list(objs):
            if o.type == "MESH" and o.name.lower().startswith("icosphere"):
                bpy.data.objects.remove(o, do_unlink=True)
                objs.remove(o)
        self.meshes = [o for o in objs if o.type == "MESH"]
        self.root = bpy.data.objects.new(name, None)
        link(self.root)
        for o in objs:
            if o.parent is None:
                o.parent = self.root
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(c) for o in self.meshes for c in o.bound_box]
        zmin, zmax = min(p.z for p in pts), max(p.z for p in pts)
        k = height / (zmax - zmin)
        self.root.scale = (k, k, k)
        self.root.location = Vector(loc) + Vector((0, 0, -zmin * k))
        self.root.rotation_euler = (0, 0, math.radians(yaw))
        self.height = height
        # темніша сукня (вовна), як у сценарії
        for o in self.meshes:
            for i, m in enumerate(o.data.materials):
                if m and "dress" in m.name.lower():
                    pass

    def head(self):
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(c) for o in self.meshes for c in o.bound_box]
        cx = sum(p.x for p in pts) / len(pts)
        cy = sum(p.y for p in pts) / len(pts)
        return Vector((cx, cy, max(p.z for p in pts) - 0.12))
