"""Zombie-ant short: Ophiocordyceps fungus takes over a carpenter ant (realistic macro explainer look).

Everything is procedural (no downloaded assets). Rendered with Cycles on CPU.

  python build.py -- . preview      # stills at key moments -> preview/f####.png
  python build.py -- . half         # 540x960 PNG frames -> frames_half/ + render_half.mp4
  python build.py -- . full         # 1080x1920 PNG frames -> frames_full/ + render.mp4
Optional 4th arg "a:b" renders only frames a..b (resumable; existing PNGs are skipped).
Units: 1 unit = 1 cm in the story (an ant is ~1.6 units long).
"""
import json
import math
import os
import random
import re
import subprocess
import sys

import bpy
import bmesh
from mathutils import Euler, Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
PROJ = os.path.abspath(argv[0] if argv else os.path.dirname(os.path.abspath(__file__)))
MODE = argv[1] if len(argv) > 1 else "preview"
RANGE = argv[2] if len(argv) > 2 else None
FPS = 24
FK = 30.0 / FPS  # per-frame rates below were tuned at 30 fps
B = json.load(open(os.path.join(PROJ, "beats.json")))
END = int(math.ceil((B[-1]["e"] + 1.6) * FPS))
random.seed(7)
SFX = []
TAU = math.tau


# ------------------------------------------------------------------ basics
def when(i, word=None, off=0):
    b = B[i]
    if word:
        w = word.lower()
        for x in b["words"]:
            if x["w"].lower().strip(".,!?—").startswith(w):
                return int(round(x["s"] * FPS)) + 1 + off
        print(f"WARNING: word {word!r} not in beat {i}")
    return int(round(b["s"] * FPS)) + 1 + off


def cue(kind, frame, prompt=None, gain=0.0, seconds=None):
    m = {"sfx": kind, "frame": int(frame), "t": round(int(frame) / FPS, 3)}
    if prompt:
        m["prompt"] = prompt
    if gain:
        m["gain"] = gain
    if seconds:
        m["seconds"] = seconds
    SFX.append(m)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.use_scripts_auto_execute = True
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, END
    sc.render.resolution_x, sc.render.resolution_y = 1080, 1920
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.03
    sc.cycles.max_bounces = 3
    sc.cycles.diffuse_bounces = 1
    sc.cycles.glossy_bounces = 1
    sc.cycles.transmission_bounces = 1
    sc.cycles.transparent_max_bounces = 16
    sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 1.0
    sc.render.use_persistent_data = True
    sc.view_settings.view_transform = "AgX"
    for look in ("AgX - Punchy", "Punchy", "AgX - Medium High Contrast"):
        try:
            sc.view_settings.look = look
            break
        except Exception:
            pass
    sc.view_settings.exposure = 0.5
    # world: humid jungle light, green from above
    w = bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.03, 0.06, 0.02, 1)
    ramp.color_ramp.elements[1].position = 0.85
    ramp.color_ramp.elements[1].color = (0.55, 0.75, 0.35, 1)
    mapr = nt.nodes.new("ShaderNodeMapRange")
    mapr.inputs["From Min"].default_value = -1
    mapr.inputs["From Max"].default_value = 1
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], mapr.inputs["Value"])
    nt.links.new(mapr.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.5
    nt.links.new(bg.outputs[0], out.inputs[0])
    # sun through the canopy
    sd = bpy.data.lights.new("Sun", "SUN")
    sd.energy = 5.0
    sd.color = (1.0, 0.93, 0.78)
    sd.angle = math.radians(4)
    so = bpy.data.objects.new("Sun", sd)
    so.rotation_euler = (math.radians(38), math.radians(12), math.radians(-30))
    link(so)


def link(o, coll=None):
    (coll or bpy.context.scene.collection).objects.link(o)
    return o


def upd():
    bpy.context.view_layer.update()


def wmat(o):
    """World matrix from the transform channels (no depsgraph update needed)."""
    m = o.matrix_basis.copy()
    if o.parent:
        m = wmat(o.parent) @ o.matrix_parent_inverse @ m
    return m


def parent_keep(child, par):
    mw = wmat(child)
    child.parent = par
    child.matrix_parent_inverse = wmat(par).inverted()
    child.matrix_basis = child.matrix_parent_inverse.inverted() @ wmat(par).inverted() @ mw


def empty(name, loc=(0, 0, 0)):
    o = bpy.data.objects.new(name, None)
    o.location = loc
    o.empty_display_size = 0.2
    return link(o)


def set_interp(kind):
    bpy.context.preferences.edit.keyframe_new_interpolation_type = kind


def key(o, path, f, val=None, index=-1):
    if val is not None:
        if index >= 0:
            getattr(o, path)[index] = val
        else:
            setattr(o, path, val)
    o.keyframe_insert(path, frame=f, index=index)


def keyprop(o, prop, f, val):
    o[prop] = val
    o.keyframe_insert(f'["{prop}"]', frame=f)


# ------------------------------------------------------------------ materials
def principled(name, rgb, rough=0.5, metal=0.0, coat=0.0, emit=None, estr=0.0, sss=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*rgb, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    p.inputs["Coat Weight"].default_value = coat
    if emit:
        p.inputs["Emission Color"].default_value = (*emit, 1)
        p.inputs["Emission Strength"].default_value = estr
    if sss:
        p.inputs["Subsurface Weight"].default_value = sss
    return m


def bsdf(m):
    return m.node_tree.nodes["Principled BSDF"]


def noisy(name, c1, c2, scale=8.0, rough=0.8, bump=0.3, detail=6.0):
    m = principled(name, c1, rough)
    nt = m.node_tree
    p = bsdf(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = detail
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*c1, 1)
    ramp.color_ramp.elements[1].color = (*c2, 1)
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[1].position = 0.65
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    if bump:
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], p.inputs["Normal"])
    return m


def leaf_mat(name, rgb, trans=0.35, rough=0.45, vein_dark=0.75):
    """Leaf: principled + translucency (glows when backlit) + darker veins pattern."""
    m = principled(name, rgb, rough, sss=0.0)
    nt = m.node_tree
    p = bsdf(m)
    out = nt.nodes["Material Output"]
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
    tr.inputs["Color"].default_value = (rgb[0] * 1.2, rgb[1] * 1.3, rgb[2] * 0.6, 1)
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = trans
    nt.links.new(p.outputs[0], mix.inputs[1])
    nt.links.new(tr.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    # subtle vein/colour variation
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.inputs["Scale"].default_value = 3.0
    wv.inputs["Distortion"].default_value = 2.0
    wv.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["UV"], wv.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 6
    nt.links.new(tc.outputs["UV"], nz.inputs["Vector"])
    mixc = nt.nodes.new("ShaderNodeMix")
    mixc.data_type = "RGBA"
    mixc.inputs["Factor"].default_value = 0.25
    mixc.inputs["A"].default_value = (*rgb, 1)
    mixc.inputs["B"].default_value = (rgb[0] * vein_dark, rgb[1] * vein_dark * 1.1, rgb[2] * 0.6, 1)
    nt.links.new(wv.outputs["Fac"], mixc.inputs["Factor"])
    nt.links.new(mixc.outputs["Result"], p.inputs["Base Color"])
    return m


def glass_mat(name, rgb=(0.25, 0.6, 1.0), strength=3.0, alpha=0.06):
    """X-ray skin: emissive fresnel rim, transparent middle."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 1.6
    nt.links.new(lw.outputs["Facing"], pw.inputs[0])
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    add.inputs[1].default_value = alpha
    nt.links.new(pw.outputs[0], add.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1)
    em.inputs["Strength"].default_value = strength
    trn = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(add.outputs[0], mix.inputs[0])
    nt.links.new(trn.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


def emit_mat(name, rgb, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def emit_node(m):
    return next(n for n in m.node_tree.nodes if n.type == "EMISSION")


# ------------------------------------------------------------------ geometry helpers
def _mesh_obj(name, bm, loc, mat, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    o.location = loc
    return link(o)


def sphere(name, loc, radii, mat, seg=32, ring=16):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * radii[0], v.co.y * radii[1], v.co.z * radii[2]))
    return _mesh_obj(name, bm, loc, mat)


def tube(name, p0, p1, r0, r1, mat, verts=12):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, radius1=r0, radius2=r1,
                          depth=d.length)
    q = Vector((0, 0, 1)).rotation_difference(d)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=q.to_matrix())
    return _mesh_obj(name, bm, (p0 + p1) / 2, mat)


def curve_obj(name, pts, radius, mat, radii=None, res=6, grow=True):
    cd = bpy.data.curves.new(name, "CURVE")
    cd.dimensions = "3D"
    cd.bevel_depth = radius
    cd.bevel_resolution = 3
    cd.resolution_u = res
    cd.use_fill_caps = True
    sp = cd.splines.new("POLY" if len(pts) < 3 else "NURBS")
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1)
        if radii:
            sp.points[i].radius = radii[i]
    if sp.type == "NURBS":
        sp.use_endpoint_u = True
        sp.order_u = min(4, len(pts))
    if grow:
        cd.bevel_factor_mapping_end = "SPLINE"
    o = bpy.data.objects.new(name, cd)
    o.data.materials.append(mat)
    return link(o)


def grow_curve(o, f0, f1):
    cd = o.data
    cd.bevel_factor_end = 0.0
    cd.keyframe_insert("bevel_factor_end", frame=f0)
    cd.bevel_factor_end = 1.0
    cd.keyframe_insert("bevel_factor_end", frame=f1)


def look_at(o, target, roll=0.0):
    d = Vector(target) - o.location
    q = d.to_track_quat("-Z", "Y")
    o.rotation_mode = "XYZ"
    o.rotation_euler = q.to_euler()
    if roll:
        o.rotation_euler.rotate_axis("Z", roll)


def orient(fwd, up):
    """Euler for an object whose local +X looks along fwd and local +Z along up."""
    f = Vector(fwd).normalized()
    u = Vector(up).normalized()
    left = u.cross(f).normalized()
    u = f.cross(left).normalized()
    m = Matrix((f, left, u)).transposed()
    return m.to_euler()


def leaf_mesh(name, L, W, droop=0.15, curl=-0.06, nu=24, nv=8, tip=0.9, mat=None):
    """Leaf lying along local +X from the stalk at the origin."""
    verts, faces, uvs = [], [], []
    for i in range(nu + 1):
        u = i / nu
        w = W / 2 * (math.sin(math.pi * u ** tip) ** 0.8) + 0.02
        for j in range(nv + 1):
            v = j / nv * 2 - 1
            x = u * L
            y = v * w
            z = leaf_z(x, y, L, droop, curl)
            verts.append((x, y, z))
            uvs.append((u, (v + 1) / 2))
    for i in range(nu):
        for j in range(nv):
            a = i * (nv + 1) + j
            faces.append((a, a + nv + 1, a + nv + 2, a + 1))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new()
    for poly in me.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = uvs[me.loops[li].vertex_index]
    for poly in me.polygons:
        poly.use_smooth = True
    o = bpy.data.objects.new(name, me)
    if mat:
        me.materials.append(mat)
    link(o)
    sol = o.modifiers.new("thick", "SOLIDIFY")
    sol.thickness = 0.05
    sol.offset = 0
    return o


def leaf_z(x, y, L, droop, curl):
    return -droop * (x / L) ** 2 * L + curl * y * y


# ------------------------------------------------------------------ the ant
LEGS = [  # attach x, femur knee (dx, y, z), foot (dx, y), phase group
    (0.26, (0.36, 0.30, 0.50), (0.52, 0.56)),
    (0.12, (0.08, 0.36, 0.48), (0.06, 0.64)),
    (-0.02, (-0.20, 0.36, 0.48), (-0.44, 0.62)),
]


class Ant:
    """Procedural carpenter ant. Root origin at the feet, forward +X, up +Z, ~1.6 units long."""

    def __init__(self, name, mats, xray=False, phase=0.0, walk=0.0):
        self.name = name
        self.root = empty(name)
        self.root["walk"] = 0.0
        self.root["ph"] = phase
        self.root["splay"] = 0.0
        self._walk = walk
        body, dark, eye = mats["body"], mats["dark"], mats["eye"]
        self.mats = mats
        self.parts = []
        # thorax (mesosoma) - slightly arched
        th = sphere(name + "_thorax", (0.12, 0, 0.34), (0.30, 0.13, 0.14), body)
        th.rotation_euler = (0, math.radians(-8), 0)
        self.thorax = th
        parent_keep(th, self.root)
        prop = sphere(name + "_propod", (-0.08, 0, 0.36), (0.1, 0.1, 0.1), body)
        parent_keep(prop, th)
        pet = sphere(name + "_petiole", (-0.2, 0, 0.36), (0.05, 0.06, 0.1), body)
        parent_keep(pet, th)
        ga = sphere(name + "_gaster", (-0.58, 0, 0.36), (0.40, 0.30, 0.28), body)
        ga.rotation_euler = (0, math.radians(10), 0)
        self.gaster = ga
        parent_keep(ga, th)
        # head on a neck pivot
        self.neck = empty(name + "_neck", (0.42, 0, 0.36))
        parent_keep(self.neck, th)
        hd = sphere(name + "_head", (0.6, 0, 0.37), (0.21, 0.2, 0.17), body)
        parent_keep(hd, self.neck)
        self.head = hd
        for s in (1, -1):
            e = sphere(name + f"_eye{s}", (0.64, 0.16 * s, 0.43), (0.05, 0.035, 0.04), eye)
            parent_keep(e, hd)
            # mandible on a pivot
            mp = empty(name + f"_mandp{s}", (0.76, 0.08 * s, 0.31))
            parent_keep(mp, hd)
            md = tube(name + f"_mand{s}", (0.76, 0.08 * s, 0.31), (0.92, 0.0 * s, 0.27), 0.045, 0.012, dark, 8)
            parent_keep(md, mp)
            mp.rotation_euler = (0, 0, math.radians(18) * s)
            setattr(self, f"mand{s}", mp)
            # antenna: scape then funiculus, with idle sway
            ap = empty(name + f"_antp{s}", (0.74, 0.1 * s, 0.44))
            parent_keep(ap, hd)
            a1 = tube(name + f"_scape{s}", (0.74, 0.1 * s, 0.44), (0.82, 0.32 * s, 0.68), 0.022, 0.018, dark, 8)
            a2 = tube(name + f"_funi{s}", (0.82, 0.32 * s, 0.68), (1.18, 0.42 * s, 0.52), 0.018, 0.026, dark, 8)
            parent_keep(a1, ap)
            parent_keep(a2, ap)
            if not xray:
                self._drive(ap, "rotation_euler", 2, f"{0.18*s}*sin(frame*0.13+{1.3 if s > 0 else 0.2})")
                self._drive(ap, "rotation_euler", 1, f"0.12*sin(frame*0.17+{0.5 if s > 0 else 2.1})")
        # legs
        self.hips = []
        self.leg_segments = []
        for li, (ax, knee, foot) in enumerate(LEGS):
            for s in (1, -1):
                hp = empty(name + f"_hip{li}{s}", (ax, 0.07 * s, 0.27))
                parent_keep(hp, th)
                p0 = Vector((ax, 0.07 * s, 0.27))
                p1 = Vector((ax + knee[0] * 0.5, knee[1] * s * 0.8, knee[2] * 0.9))
                p2 = Vector((ax + foot[0] * 0.85, foot[1] * s * 0.95, 0.06))
                p3 = Vector((ax + foot[0] * 1.0, foot[1] * s * 1.15, 0.0))
                segs = [tube(name + f"_coxa{li}{s}", p0, p0 + (p1 - p0) * 0.25, 0.04, 0.035, body, 10),
                        tube(name + f"_femur{li}{s}", p0 + (p1 - p0) * 0.2, p1, 0.035, 0.028, body, 10),
                        tube(name + f"_tibia{li}{s}", p1, p2, 0.026, 0.018, dark, 10),
                        tube(name + f"_tarsus{li}{s}", p2, p3, 0.016, 0.01, dark, 8)]
                kn = sphere(name + f"_knee{li}{s}", p1, (0.03, 0.03, 0.03), dark, 12, 6)
                segs.append(kn)
                for sg in segs:
                    parent_keep(sg, hp)
                self.leg_segments.append((p0, p1, p2, p3, hp, s))
                ph = 0.0 if (li % 2 == 0) == (s > 0) else math.pi
                if not xray:
                    self._drive(hp, "rotation_euler", 2,
                                f"w*0.42*sin(frame*{0.85*FK:.4f}+{ph:.3f}+p)" + ("" if s > 0 else ""))
                    self._drive(hp, "rotation_euler", 0,
                                f"{s}*(w*0.28*max(0,cos(frame*{0.85*FK:.4f}+{ph:.3f}+p))+sp*0.55)")
                self.hips.append(hp)
        upd()
        self.rest = {o.name: o.matrix_world.copy() for o in self.all_objects()}
        self.root["walk"] = self._walk

    def world(self, obj, pt):
        """Current world position of a point given in rest (ant) coordinates, carried by obj."""
        return obj.matrix_world @ (self.rest[obj.name].inverted() @ Vector(pt))

    def _drive(self, o, path, idx, expr):
        fc = o.driver_add(path, idx)
        d = fc.driver
        d.type = "SCRIPTED"
        for vn, prop in (("w", "walk"), ("p", "ph"), ("sp", "splay")):
            if re.search(r"\b%s\b" % vn, expr):
                v = d.variables.new()
                v.name = vn
                v.targets[0].id = self.root
                v.targets[0].data_path = f'["{prop}"]'
        d.expression = expr

    def all_objects(self):
        out = []

        def rec(o):
            out.append(o)
            for c in o.children:
                rec(c)
        rec(self.root)
        return out


def ant_mats(prefix, xray=False):
    if xray:
        g = glass_mat(prefix + "_glass")
        return {"body": g, "dark": g, "eye": g}
    body = principled(prefix + "_body", (0.05, 0.022, 0.012), 0.33, coat=0.25)
    dark = principled(prefix + "_dark", (0.05, 0.022, 0.012), 0.35, coat=0.3)
    eye = principled(prefix + "_eye", (0.01, 0.01, 0.01), 0.08, coat=1.0)
    return {"body": body, "dark": dark, "eye": eye}


def bake_path(o, f0, f1, fn, step=1):
    """Key location+rotation every `step` frames from fn(frame) -> (loc, euler)."""
    for f in range(f0, f1 + 1, step):
        loc, rot = fn(f)
        o.location = loc
        o.rotation_euler = rot
        o.keyframe_insert("location", frame=f)
        o.keyframe_insert("rotation_euler", frame=f)


# ------------------------------------------------------------------ world: jungle floor
def ground():
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=160, y_subdivisions=160, size=180, location=(0, 10, 0))
    g = bpy.context.active_object
    g.name = "Ground"
    vg = g.vertex_groups.new(name="disp")
    for v in g.data.vertices:
        x, y = v.co.x, v.co.y + 10
        d_trail = abs(y)
        d_plant = math.hypot(x - 4, y - 1.5)
        wgt = min(1.0, max(0.0, (d_trail - 1.6) / 3.0)) * min(1.0, max(0.0, (d_plant - 4.5) / 3.0))
        vg.add([v.index], wgt, "REPLACE")
    tex = bpy.data.textures.new("gnoise", "CLOUDS")
    tex.noise_scale = 3.0
    md = g.modifiers.new("disp", "DISPLACE")
    md.texture = tex
    md.strength = 0.9
    md.mid_level = 0.5
    md.vertex_group = "disp"
    g.data.materials.append(noisy("Soil", (0.045, 0.026, 0.014), (0.11, 0.065, 0.035), scale=1.6, bump=0.5))
    bpy.ops.object.shade_smooth()
    return g


_BVH = []


def ground_z(x, y):
    if not _BVH:
        from mathutils.bvhtree import BVHTree
        g = bpy.data.objects["Ground"]
        dg = bpy.context.evaluated_depsgraph_get()
        _BVH.append((BVHTree.FromObject(g, dg), g.matrix_world.copy()))
    t, mw = _BVH[0]
    loc, *_ = t.ray_cast(mw.inverted() @ Vector((x, y, 30)), Vector((0, 0, -1)))
    return (mw @ loc).z if loc else 0.0


def litter():
    cols = [(0.32, 0.17, 0.06), (0.42, 0.26, 0.08), (0.22, 0.12, 0.05), (0.5, 0.32, 0.12),
            (0.28, 0.2, 0.07), (0.18, 0.1, 0.05)]
    mats = [leaf_mat(f"Litter{i}", c, trans=0.1, rough=0.7) for i, c in enumerate(cols)]
    bases = []
    for i in range(8):
        o = leaf_mesh(f"LitterBase{i}", random.uniform(2.5, 4.5), random.uniform(1.2, 2.2),
                      droop=random.uniform(-0.1, 0.1), curl=random.uniform(0.04, 0.15), nu=10, nv=4,
                      mat=mats[i % len(mats)])
        o.hide_render = True
        o.hide_viewport = True
        bases.append(o)
    n = 0
    tries = 0
    while n < 520 and tries < 5000:
        tries += 1
        x = random.uniform(-60, 60)
        y = random.uniform(-25, 70)
        if abs(y) < 1.4 and -60 < x < 60:
            continue
        if math.hypot(x - 4, y - 1.5) < 3.8:
            continue
        b = random.choice(bases)
        o = bpy.data.objects.new(f"Litter{n}", b.data)
        o.modifiers.new("thick", "SOLIDIFY").thickness = 0.04
        o.location = (x, y, ground_z(x, y) + random.uniform(0.02, 0.1))
        o.rotation_euler = (random.uniform(-0.25, 0.25), random.uniform(-0.25, 0.25), random.uniform(0, TAU))
        s = random.uniform(0.6, 1.4)
        o.scale = (s, s, s)
        o.data.materials.clear() if False else None
        link(o)
        o.material_slots[0].link = "OBJECT"
        o.material_slots[0].material = random.choice(mats)
        n += 1
    twig = noisy("Twig", (0.09, 0.06, 0.035), (0.2, 0.13, 0.07), scale=12, rough=0.85)
    for i in range(45):
        x = random.uniform(-40, 40)
        y = random.uniform(2.2, 50) * random.choice([1, 1, -0.4])
        if abs(y) < 2:
            continue
        a = random.uniform(0, TAU)
        L = random.uniform(2, 8)
        p0 = Vector((x, y, ground_z(x, y) + 0.12))
        p1 = p0 + Vector((math.cos(a) * L, math.sin(a) * L, random.uniform(0, 0.4)))
        link_none = tube(f"Twig{i}", p0, p1, random.uniform(0.08, 0.2), random.uniform(0.04, 0.1), twig, 8)


def plant(name, base, height, leaves, mat_stem, mat_leaf, bend=(0, 0)):
    """Stem (curve) with leaves at the top part. leaves: list of (height_frac, yaw, L, W, droop)."""
    bx, by, bz = base
    pts = [(bx + bend[0] * (t ** 2), by + bend[1] * (t ** 2), bz + height * t) for t in (0, 0.33, 0.66, 1.0)]
    st = curve_obj(name + "_stem", pts, 0.32 * max(1, height / 14), mat_stem, radii=[1.1, 1.0, 0.85, 0.7], grow=False)
    objs = [st]
    for k, (hf, yaw, L, W, droop) in enumerate(leaves):
        t = hf
        p = (bx + bend[0] * t * t, by + bend[1] * t * t, bz + height * t)
        lf = leaf_mesh(f"{name}_leaf{k}", L, W, droop=droop, curl=-0.05, mat=mat_leaf)
        lf.location = p
        lf.rotation_euler = (0, math.radians(-8), yaw)
        # little petiole
        objs.append(lf)
    return objs


def jungle(mat_stem, leaf_mats):
    rng = random.Random(3)
    spots = []
    for i in range(70):
        for _ in range(50):
            x = rng.uniform(-70, 70)
            y = rng.uniform(12, 90) if rng.random() < 0.8 else rng.uniform(-40, -18)
            if all(math.hypot(x - a, y - b) > 6 for a, b in spots) and math.hypot(x + 14, y - 22) > 12 \
                    and not (-8 < x < 24 and y < 16):
                break
        spots.append((x, y))
        h = rng.uniform(8, 40)
        lv = []
        for k in range(rng.randint(3, 7)):
            lv.append((rng.uniform(0.45, 1.0), rng.uniform(0, TAU), rng.uniform(8, 22), rng.uniform(4, 9),
                       rng.uniform(0.1, 0.35)))
        plant(f"BG{i}", (x, y, 0), h, lv, mat_stem, rng.choice(leaf_mats), bend=(rng.uniform(-3, 3), rng.uniform(-3, 3)))
    # big tree trunks far away
    bark = noisy("Bark", (0.12, 0.09, 0.06), (0.3, 0.24, 0.16), scale=0.6, bump=0.8)
    for i in range(9):
        x = rng.uniform(-90, 90)
        y = rng.uniform(60, 120)
        tube(f"Trunk{i}", (x, y, -1), (x + rng.uniform(-6, 6), y, 160), rng.uniform(4, 9), rng.uniform(3, 6), bark, 24)
    # glowing canopy gaps far behind (become bokeh)
    sky = emit_mat("CanopyGap", (0.85, 0.95, 0.6), 2.5)
    for i in range(26):
        x = rng.uniform(-110, 110)
        z = rng.uniform(20, 120)
        o = sphere(f"Gap{i}", (x, 160, z), (rng.uniform(3, 9),) * 3, sky, 16, 8)
        o.visible_shadow = False
    # back wall of dark green foliage so the world never shows a seam
    wall = noisy("Foliage", (0.02, 0.07, 0.02), (0.08, 0.2, 0.05), scale=0.05, bump=0)
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 170, 60))
    o = bpy.context.active_object
    o.scale = (500, 260, 1)
    o.rotation_euler = (math.radians(90), 0, 0)
    o.data.materials.append(wall)
    o.name = "FoliageWall"


# ------------------------------------------------------------------ build
def build():
    reset()
    sc = bpy.context.scene
    ground()
    litter()
    stem_mat = principled("Stem", (0.12, 0.25, 0.06), 0.5)
    leaf_mats = [leaf_mat("LeafA", (0.08, 0.28, 0.04)), leaf_mat("LeafB", (0.13, 0.33, 0.05)),
                 leaf_mat("LeafC", (0.05, 0.2, 0.035)), leaf_mat("LeafD", (0.2, 0.36, 0.07))]
    jungle(stem_mat, leaf_mats)

    # --- hero plant: stem at (6, 3), the big leaf reaches back over the trail (local +X -> world -Y)
    SX, SY, TOP = 6.0, 3.0, 14.0
    L, W, DROOP = 12.0, 5.2, 0.12
    curve_obj("HeroStem", [(SX, SY, 0), (SX, SY, 5), (SX, SY + 0.1, 10), (SX, SY - 0.2, TOP + 0.2)], 0.36,
              stem_mat, radii=[1.0, 0.95, 0.85, 0.7], grow=False)
    hero_leaf_mat = leaf_mat("HeroLeaf", (0.1, 0.3, 0.045))
    leaf = leaf_mesh("HeroLeaf", L, W, droop=DROOP, curl=-0.03, nu=40, nv=14, mat=hero_leaf_mat)
    leaf.location = (SX, SY - 0.2, TOP)
    leaf.rotation_euler = (0, 0, math.radians(-90))
    for k, (hf, yaw, l2, w2) in enumerate([(0.55, 0.9, 9, 4), (0.75, 2.6, 10, 4.5), (0.4, -2.2, 8, 3.6)]):
        lf = leaf_mesh(f"HeroLeaf{k}", l2, w2, droop=0.25, curl=-0.05, mat=leaf_mats[k % 4])
        lf.location = (SX, SY, TOP * hf)
        lf.rotation_euler = (0, math.radians(-12), yaw)

    def leaf_under(lx, ly):
        """World point on the underside of the hero leaf at leaf-local (lx along leaf, ly across)."""
        z = TOP + leaf_z(lx, ly, L, DROOP, -0.03) - 0.025
        return Vector((SX + ly, SY - 0.2 - lx, z))

    # midrib on the underside
    rib = [leaf_under(lx, 0) + Vector((0, 0, -0.045)) for lx in [0.0, 2, 4, 6, 8, 10, 11.6]]
    curve_obj("Midrib", [tuple(p) for p in rib], 0.075, principled("Rib", (0.16, 0.34, 0.08), 0.5),
              radii=[1.3, 1.1, 1.0, 0.9, 0.7, 0.5, 0.3], grow=False)
    for k in range(7):  # side veins
        lx = 1.2 + k * 1.45
        for s in (1, -1):
            a = leaf_under(lx, 0)
            pts = [leaf_under(lx + t * 1.2, s * t * 2.2) + Vector((0, 0, -0.02)) for t in (0, 0.5, 1)]
            curve_obj(f"Vein{k}{s}", [tuple(p) for p in pts], 0.025, principled("Vein", (0.14, 0.3, 0.07), 0.5),
                      grow=False)

    # --- trail ants
    v = 2.6  # units per second
    t_leave = when(4, "кидає") / FPS
    HX0 = 1.0
    trail_mats = ant_mats("Trail")
    template = None
    trail = []
    for k in range(-18, 18):
        if k == 0:
            continue
        a = Ant(f"T{k}", trail_mats, phase=random.uniform(0, TAU), walk=1.0)
        yoff = random.uniform(-0.35, 0.35)
        x0 = HX0 + 3.3 * k + random.uniform(-0.5, 0.5)
        speed = v * random.uniform(0.92, 1.08)
        wob = random.uniform(0, TAU)

        def fn(f, x0=x0, yoff=yoff, speed=speed, wob=wob):
            t = f / FPS
            x = x0 + speed * (t - t_leave)
            x = (x + 59.4) % 118.8 - 59.4
            y = yoff + 0.25 * math.sin(t * 1.3 + wob)
            dy = 0.25 * 1.3 * math.cos(t * 1.3 + wob)
            return (x, y, 0.0), (0, 0, math.atan2(dy, speed))
        bake_path(a.root, 1, END, fn, 1)
        trail.append(a)

    # --- hero ant
    hero_m = ant_mats("Hero")
    hero = Ant("Hero", hero_m, walk=1.0, phase=0.4)
    R = hero.root
    f_leave = when(4, "кидає")
    f_turn_end = f_leave + 22
    stem_base = Vector((SX - 0.15, SY - 0.75, 0.0))
    f_b5 = when(5)
    f_climb_end = when(5, "спускається") - 1
    f_down = when(5, "спускається")
    f_b6 = when(6)
    f_bite = when(6, "вчіплюється")
    f_die = when(7, "помирає")
    f_sprout = when(7, "проростає")
    # 1) along the trail until "кидає", then a stop, twitch and turn to the plant
    turn_dir = (stem_base - Vector((HX0 + 0.3, 0, 0))).normalized()
    yaw_turn = math.atan2(turn_dir.y, turn_dir.x)

    def hero_fn(f):
        t = f / FPS
        if f <= f_leave:
            x = HX0 + v * (t - t_leave)
            return (x, 0.05 * math.sin(t * 1.1), 0), (0, 0, 0)
        if f <= f_turn_end:
            k = (f - f_leave) / (f_turn_end - f_leave)
            k = k * k * (3 - 2 * k)
            jit = 0.25 * math.sin(f * 1.7) * (1 - k) if f < f_leave + 12 else 0
            return (HX0 + 0.3 * k, 0, 0), (0, 0, yaw_turn * k + jit)
        # walk to the stem
        p0 = Vector((HX0 + 0.3, 0, 0))
        dist = (stem_base - p0).length
        tt = (f - f_turn_end) / FPS
        s = min(dist, tt * v * 0.9)
        p = p0 + turn_dir * s
        return tuple(p), (0, 0, yaw_turn)
    bake_path(R, 1, f_b5 - 1, hero_fn, 1)
    keyprop(R, "walk", f_leave - 2, 1.0)
    keyprop(R, "walk", f_leave + 3, 0.0)
    keyprop(R, "walk", f_turn_end - 6, 0.0)
    keyprop(R, "walk", f_turn_end + 2, 1.0)

    # 2) climb the stem (front face, towards the camera at -Y)
    stem_face = Vector((SX, SY - 0.36, 0))
    rot_climb = orient((0, 0, 1), (0, -1, 0))

    def climb_fn(f):
        t = (f - f_b5) / FPS
        z = 0.6 + 2.3 * t
        wob = 0.05 * math.sin(t * 5)
        return (stem_face.x + wob, stem_face.y, z), rot_climb
    bake_path(R, f_b5, f_climb_end, climb_fn, 1)

    # 3) under the leaf: walk along the midrib (upside down), then turn to face the vein
    rot_under = orient((0, -1, 0), (0, 0, -1))
    LX_BITE = 5.0
    side = 0.62

    def under_fn(f):
        t = (f - f_down) / FPS
        lx = min(LX_BITE - 0.3, 1.6 + 1.9 * t)
        p = leaf_under(lx, side)
        return tuple(p), rot_under
    f_under_end = f_b6 - 1
    bake_path(R, f_down, f_under_end, under_fn, 1)
    # beat 6: turn towards the vein (head over the midrib)
    p_bite = leaf_under(LX_BITE, 0.8)
    rot_bite = orient((-1, 0, 0), (0, 0, -1))

    def turn_fn(f):
        k = min(1, (f - f_b6) / 14)
        k = k * k * (3 - 2 * k)
        pa = leaf_under(LX_BITE - 0.3, side)
        p = pa.lerp(p_bite, k)
        ra = Vector(rot_under)
        rb = Vector(rot_bite)
        # shortest yaw blend
        q = rot_under.to_quaternion().slerp(rot_bite.to_quaternion(), k)
        return tuple(p), q.to_euler()
    bake_path(R, f_b6, END, turn_fn, 1)
    keyprop(R, "walk", f_b6 + 12, 1.0)
    keyprop(R, "walk", f_bite - 6, 0.25)
    keyprop(R, "walk", f_bite, 0.0)
    # bite: thorax tips forward, head pitches down onto the vein, mandibles snap shut
    th, nk = hero.thorax, hero.neck
    for o, ang in ((th, -8), (nk, 0)):
        key(o, "rotation_euler", f_bite - 4, math.radians(ang), 1)
    key(th, "rotation_euler", f_bite + 3, math.radians(10), 1)
    key(nk, "rotation_euler", f_bite + 3, math.radians(34), 1)
    for s in (1, -1):
        mp = getattr(hero, f"mand{s}")
        key(mp, "rotation_euler", f_bite - 2, math.radians(42) * s, 2)
        key(mp, "rotation_euler", f_bite + 2, math.radians(-6) * s, 2)
    # clamp shudder
    set_interp("LINEAR")
    for i, f in enumerate(range(f_bite + 3, f_bite + 22, 2)):
        key(th, "rotation_euler", f, math.radians(10 + (1.8 if i % 2 else -1.8)), 1)
    key(th, "rotation_euler", f_bite + 24, math.radians(10), 1)
    set_interp("BEZIER")
    # dying: legs slowly splay away from the leaf, body colour fades to dusty grey-brown
    keyprop(R, "splay", f_die - 2, 0.0)
    keyprop(R, "splay", f_die + 40, 0.9)
    for m, c in ((hero_m["body"], (0.09, 0.07, 0.05)), (hero_m["dark"], (0.1, 0.08, 0.06))):
        p = bsdf(m)
        p.inputs["Base Color"].keyframe_insert("default_value", frame=f_die)
        p.inputs["Roughness"].keyframe_insert("default_value", frame=f_die)
        p.inputs["Base Color"].default_value = (*c, 1)
        p.inputs["Roughness"].default_value = 0.75
        p.inputs["Base Color"].keyframe_insert("default_value", frame=f_die + 45)
        p.inputs["Roughness"].keyframe_insert("default_value", frame=f_die + 45)

    ul = bpy.data.lights.new("UnderLeaf", "AREA")
    ul.energy = 260
    ul.size = 5
    ul.color = (0.85, 1.0, 0.75)
    ulo = bpy.data.objects.new("UnderLeaf", ul)
    ulo.location = leaf_under(4.5, 1.0) + Vector((2.5, -2.5, -4.5))
    look_at(ulo, leaf_under(4.5, 0.5))
    link(ulo)
    # white mycelium tufts at the joints (appear after death)
    myc = principled("Mycelium", (0.85, 0.82, 0.72), 0.9, sss=0.3)
    sc.frame_set(END)
    upd()
    tufts = []
    for (p0, p1, p2, p3, hp, s) in hero.leg_segments:
        for pt in (p0, p1):
            tufts.append(hero.world(hp, pt))
    for pt in [(-0.2, 0, 0.42), (0.42, 0, 0.4), (-0.5, 0.1, 0.55)]:
        tufts.append(hero.world(th, pt))
    for i, w in enumerate(tufts):
        o = sphere(f"Tuft{i}", w, (0.04, 0.04, 0.04), myc, 12, 8)
        d = o.modifiers.new("d", "DISPLACE")
        tx = bpy.data.textures.new(f"tuft{i}", "CLOUDS")
        tx.noise_scale = 0.03
        d.texture = tx
        d.strength = 0.04
        f0 = f_die + 20 + i * 2
        key(o, "scale", f0, (0, 0, 0))
        key(o, "scale", f0 + 25, (1, 1, 1))
    # the stalk: from the back of the head, down (the ant hangs upside down)
    head_back = hero.head.matrix_world @ Vector((0.0, 0, 0))  # placeholder, recomputed below
    hw = hero.head.matrix_world
    # head object data is in world coords at build time, so use its bounding box centre
    hc = sum((hw @ Vector(c) for c in hero.head.bound_box), Vector()) / 8
    start = hc + Vector((0.12, 0, -0.08))
    stalk_pts = [start + (p - start) * 0.72 for p in
                 [start, start + Vector((0.08, -0.05, -0.6)), start + Vector((0.3, -0.15, -1.3)),
                  start + Vector((0.35, -0.3, -2.0)), start + Vector((0.2, -0.4, -2.8)),
                  start + Vector((0.05, -0.45, -3.4))]]
    stalk_mat = noisy("Stalk", (0.35, 0.26, 0.15), (0.6, 0.5, 0.33), scale=30, rough=0.7, bump=0.4)
    stalk = curve_obj("Stalk", [tuple(p) for p in stalk_pts], 0.045, stalk_mat,
                      radii=[1.3, 1.1, 1.0, 0.9, 0.75, 0.45])
    grow_curve(stalk, f_sprout, f_sprout + 75)
    bulb_pos = stalk_pts[3] + Vector((0.0, 0.0, 0.0))
    bulb = sphere("Ascoma", bulb_pos, (0.14, 0.14, 0.18), noisy("AscomaM", (0.45, 0.3, 0.16), (0.7, 0.55, 0.3),
                                                                 scale=60, bump=0.8), 24, 12)
    f_bulb = f_sprout + 60
    key(bulb, "scale", f_bulb, (0, 0, 0))
    key(bulb, "scale", f_bulb + 18, (1, 1, 1))
    cue("grow", f_sprout, "slow creepy organic stretching growth, creaking fungus sprouting", seconds=3.5)

    # spores raining down
    spore_m = emit_mat("SporeGlow", (1.0, 0.95, 0.75), 6.0)
    f_rain = when(8, "сиплються") - 6
    rng = random.Random(11)
    me = None
    for i in range(110):
        f0 = f_rain + rng.randint(0, 80)
        dur = rng.randint(70, 130)
        p0 = bulb_pos + Vector((rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), rng.uniform(-0.2, 0.1)))
        p1 = Vector((p0.x + rng.uniform(-3, 3), p0.y + rng.uniform(-3, 3), rng.uniform(0.05, 0.3)))
        o = sphere(f"Spore{i}", p0, (0.03, 0.03, 0.03), spore_m, 8, 4)
        o.visible_shadow = False
        key(o, "scale", f0 - 1, (0, 0, 0))
        key(o, "scale", f0, (1, 1, 1))
        key(o, "location", f0, p0)
        set_interp("LINEAR")
        mid = p0.lerp(p1, 0.5) + Vector((rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), 0))
        key(o, "location", f0 + dur // 2, mid)
        key(o, "location", f0 + dur, p1)
        set_interp("BEZIER")
    cue("spores", f_rain, "soft puff of dust, sparkling spores drifting down, magical shimmer", seconds=3)

    # --- spore landing on the hero during beat 1
    f_spore = when(1, "спора")
    sp = sphere("SporeHero", (0, 0, 0), (0.07, 0.07, 0.09), emit_mat("SporeHeroM", (1.0, 0.95, 0.7), 14), 12, 8)
    sp.parent = R
    sp.matrix_parent_inverse = Matrix()
    # gaster data is in root-local world coords (built at origin) -> local = ant coords
    land = Vector((-0.45, 0.04, 0.66))
    key(sp, "location", 1, land + Vector((-0.4, 0.2, 5)))
    key(sp, "location", f_spore - 18, land + Vector((-0.4, 0.2, 5)))
    key(sp, "location", f_spore + 14, land)
    key(sp, "scale", f_spore - 19, (0, 0, 0))
    key(sp, "scale", f_spore - 18, (1, 1, 1))
    key(sp, "scale", f_b5 - 1, (1, 1, 1))
    key(sp, "scale", f_b5, (0, 0, 0))
    cue("spore_land", f_spore + 14, "tiny soft magical pop, a dust speck landing", seconds=1.0)
    cue("skitter", when(1), "tiny insect legs skittering on dry leaves, ants marching", seconds=4, gain=-4)

    # ------------------------------------------------------------ teaser: an old zombie ant on another plant
    TX, TY = -14.0, 22.0
    curve_obj("TeaserStem", [(TX, TY, 0), (TX, TY, 6), (TX + 0.2, TY, 13)], 0.3, stem_mat, grow=False)
    tl = leaf_mesh("TeaserLeaf", 11, 4.8, droop=0.1, curl=-0.03, mat=leaf_mats[1])
    tl.location = (TX, TY, 13)
    tl.rotation_euler = (0, 0, math.radians(-90))
    tm = ant_mats("Teaser")
    for m, c in ((tm["body"], (0.09, 0.07, 0.05)), (tm["dark"], (0.1, 0.08, 0.06))):
        bsdf(m).inputs["Base Color"].default_value = (*c, 1)
        bsdf(m).inputs["Roughness"].default_value = 0.75
    ta = Ant("Teaser", tm, walk=0.0)
    ta.root["splay"] = 0.9
    ta.root.location = (TX + 0.75, TY - 0.2 - 4.0, 13 + leaf_z(4.0, 0.75, 11, 0.1, -0.03) - 0.03)
    ta.root.rotation_euler = orient((-1, 0, 0), (0, 0, -1))
    ta.thorax.rotation_euler[1] = math.radians(10)
    ta.neck.rotation_euler[1] = math.radians(34)
    upd()
    hw = ta.head.matrix_world
    hc = sum((hw @ Vector(c) for c in ta.head.bound_box), Vector()) / 8
    st0 = hc + Vector((0.12, 0, -0.08))
    tpts = [st0 + (p - stalk_pts[0]) for p in stalk_pts]
    curve_obj("TeaserStalk", [tuple(p) for p in tpts], 0.045, stalk_mat, radii=[1.3, 1.1, 1.0, 0.9, 0.75, 0.45],
              grow=False)
    sphere("TeaserAscoma", tpts[3], (0.14, 0.14, 0.18), bpy.data.materials["AscomaM"], 24, 12)
    for i, w in enumerate([hc + Vector((0, 0.2, 0.1)), hc + Vector((0.5, 0.1, 0.1)), hc + Vector((0.9, -0.3, 0.2))]):
        sphere(f"TTuft{i}", w, (0.045, 0.045, 0.045), myc, 12, 8)

    # ------------------------------------------------------------ X-ray zone
    XO = Vector((0, 600, 50))
    void = sphere("Void", XO, (40, 40, 40), emit_mat("VoidM", (0.004, 0.012, 0.03), 1.0), 32, 16)
    void.visible_shadow = False
    xm = ant_mats("X", xray=True)
    xa = Ant("XAnt", xm, xray=True)
    xr = xa.root
    # muscles (wet red) - big head muscles for the jaws, thorax bundles, leg muscles
    mus = principled("Muscle", (0.55, 0.035, 0.03), 0.3, emit=(0.6, 0.05, 0.03), estr=0.25, sss=0.2)
    muscles = []
    mspec = []  # (centre, axis unit, half length, radius)
    for s in (1, -1):
        muscles.append(sphere(f"MHead{s}", (0.56, 0.08 * s, 0.37), (0.14, 0.08, 0.1), mus))
        mspec.append((Vector((0.56, 0.08 * s, 0.37)), Vector((1, 0, 0)), 0.14, 0.09))
        for k, (x, z) in enumerate([(0.24, 0.36), (0.08, 0.34), (-0.04, 0.34)]):
            muscles.append(sphere(f"MTh{k}{s}", (x, 0.05 * s, z), (0.1, 0.05, 0.08), mus))
            mspec.append((Vector((x, 0.05 * s, z)), Vector((1, 0, 0)), 0.1, 0.065))
    for (p0, p1, p2, p3, hp, s) in xa.leg_segments:
        for a_, b_, r_ in ((p0 + (p1 - p0) * 0.15, p1 - (p1 - p0) * 0.08, 0.02), (p1 + (p2 - p1) * 0.08, p2 - (p2 - p1) * 0.15, 0.013)):
            muscles.append(tube(f"MLeg{len(muscles)}", a_, b_, r_, r_ * 0.8, mus, 8))
            mspec.append(((a_ + b_) / 2, (b_ - a_).normalized(), (b_ - a_).length / 2, r_ * 1.3))
    gut = principled("Gut", (0.35, 0.12, 0.05), 0.35, emit=(0.3, 0.08, 0.02), estr=0.15)
    sphere("Crop", (-0.6, 0, 0.36), (0.2, 0.13, 0.12), gut)
    brain = principled("Brain", (0.8, 0.55, 0.6), 0.4, emit=(0.6, 0.3, 0.35), estr=0.3)
    sphere("Brain", (0.6, 0, 0.42), (0.07, 0.09, 0.05), brain)
    for o in muscles:
        parent_keep(o, xr)
    for nm in ("Crop", "Brain"):
        parent_keep(bpy.data.objects[nm], xr)

    hy_m = emit_mat("Hypha", (0.75, 1.0, 0.25), 7.0)
    E = Vector((-0.47, 0.04, 0.61))
    sp2 = sphere("SporeX", E + Vector((0, 0, 0.035)), (0.045, 0.045, 0.055), emit_mat("SporeXM", (1, 0.95, 0.7), 9), 12, 8)
    parent_keep(sp2, xr)
    rng = random.Random(5)
    f_b2 = when(2)
    f_through = when(2, "проростає")
    f_inside = when(2, "всередину")
    f_b3 = when(3)
    f_spread = when(3, "розростається")
    f_wrap = when(3, "обплітає")
    f_ctrl = when(3, "контроль")
    hyphae = []

    def wiggle(a, b, n=10, amp=0.035, seed=0):
        r = random.Random(seed)
        a, b = Vector(a), Vector(b)
        pts = []
        for i in range(n + 1):
            t = i / n
            p = a.lerp(b, t)
            if 0 < i < n:
                p += Vector((r.uniform(-amp, amp), r.uniform(-amp, amp), r.uniform(-amp, amp)))
            pts.append(tuple(p))
        return pts

    def hypha(pts, f0, f1, r=0.007):
        o = curve_obj(f"Hy{len(hyphae)}", pts, r, hy_m)
        grow_curve(o, f0, f1)
        o.parent = xr
        hyphae.append(o)
        return o

    # germ tube through the shell
    hypha(wiggle(E, (-0.48, 0.02, 0.36), 6, 0.01, 1), f_through, f_inside + 10, 0.02)
    # gaster fill
    for i in range(14):
        a = Vector((-0.48, 0.02, 0.36))
        b = Vector((-0.56 + rng.uniform(-0.28, 0.3), rng.uniform(-0.2, 0.2), 0.34 + rng.uniform(-0.17, 0.17)))
        hypha(wiggle(a, b, 8, 0.03, 10 + i), f_inside + rng.randint(0, 15), f_spread + rng.randint(10, 40), 0.012)
    # trunk lines to thorax and head
    trunk = [(-0.48, 0.02, 0.36), (-0.2, 0, 0.36), (0.1, 0, 0.34), (0.42, 0, 0.36), (0.6, 0, 0.36)]
    for k in range(3):
        pts = []
        for j in range(len(trunk) - 1):
            seg = wiggle(trunk[j], trunk[j + 1], 5, 0.025, 30 + j + 7 * k)
            pts += seg[:-1]
        pts.append(trunk[-1])
        hypha(pts, f_spread, f_spread + 45 + k * 6, 0.016)
    # branches into every muscle
    for i, mo in enumerate(muscles):
        c = sum((mo.matrix_world @ Vector(v) for v in mo.bound_box), Vector()) / 8
        c = xr.matrix_world.inverted() @ c
        src = Vector(min(trunk, key=lambda q: (Vector(q) - c).length))
        f0 = f_spread + 15 + rng.randint(0, 25)
        hypha(wiggle(src, c, 8, 0.03, 100 + i), f0, f0 + 30, 0.011)
    # wrapping the muscles: spirals around every bundle
    for i, (c, ax, hl, rad) in enumerate(mspec):
        u = ax.orthogonal().normalized()
        w2 = ax.cross(u).normalized()
        pts = []
        n = 48
        turns = 4.0 if hl > 0.08 else 3.0
        for j in range(n + 1):
            t = j / n
            ang = t * turns * TAU + i
            along = (t * 2 - 1) * hl * 0.85
            rr = rad * math.sqrt(max(0.15, 1 - (along / hl) ** 2)) if hl > 0.08 else rad
            pts.append(tuple(c + ax * along + (u * math.cos(ang) + w2 * math.sin(ang)) * rr))
        f0 = f_wrap + rng.randint(0, 20)
        hypha(pts, f0, f0 + 40, 0.008)
    # muscles get infected: they turn a sickly orange at "контроль"
    for nm, val in (("Base Color", (0.55, 0.035, 0.03, 1)), ("Emission Color", (0.6, 0.05, 0.03, 1))):
        inp = bsdf(mus).inputs[nm]
        inp.default_value = val
        inp.keyframe_insert("default_value", frame=f_ctrl - 4)
    bsdf(mus).inputs["Base Color"].default_value = (0.6, 0.3, 0.05, 1)
    bsdf(mus).inputs["Emission Color"].default_value = (0.7, 0.45, 0.05, 1)
    for nm in ("Base Color", "Emission Color"):
        bsdf(mus).inputs[nm].keyframe_insert("default_value", frame=f_ctrl + 20)
    # x-ray ant twitches when the fungus takes over
    xr.location = XO
    set_interp("LINEAR")
    key(xr, "rotation_euler", f_ctrl - 2, (0, 0, 0))
    for j, f in enumerate(range(f_ctrl, f_ctrl + 24, 3)):
        key(xr, "rotation_euler", f, (math.radians(rng.uniform(-4, 4)), math.radians(rng.uniform(-3, 3)),
                                      math.radians(rng.uniform(-5, 5))))
    key(xr, "rotation_euler", f_ctrl + 27, (0, 0, 0))
    set_interp("BEZIER")
    for o in hyphae:
        o.matrix_parent_inverse = Matrix()
    xl = bpy.data.lights.new("XKey", "POINT")
    xl.energy = 120
    xl.color = (0.8, 0.9, 1.0)
    xlo = bpy.data.objects.new("XKey", xl)
    xlo.location = XO + Vector((0.5, -3, 3))
    link(xlo)
    cue("whoosh", f_b2, "deep cinematic whoosh into darkness, x-ray transition", seconds=1.2)
    cue("sprout", f_through, "wet organic creaking, tiny tendril pushing through a shell", seconds=2.5)
    cue("spread", f_spread, "eerie squelching fungal growth spreading, organic crackle", seconds=4)
    cue("twitch", f_ctrl, "insect body twitching, dry clicking spasm", seconds=1.2)

    # ------------------------------------------------------------ fossil zone
    FO = Vector((600, 0, 0))
    bpy.ops.mesh.primitive_cube_add(size=1, location=FO + Vector((0, 0, 0.3)))
    slab = bpy.context.active_object
    slab.name = "Slab"
    slab.scale = (20, 13, 0.6)
    bpy.ops.object.transform_apply(scale=True)
    slab.modifiers.new("bev", "BEVEL").width = 0.25
    slab.data.materials.append(noisy("Stone", (0.1, 0.085, 0.065), (0.2, 0.17, 0.13), scale=1.4, bump=0.6))
    tbl = principled("Table", (0.05, 0.035, 0.025), 0.6)
    bpy.ops.mesh.primitive_plane_add(size=80, location=FO + Vector((0, 0, -0.3)))
    bpy.context.active_object.data.materials.append(noisy("Dark", (0.03, 0.025, 0.02), (0.07, 0.05, 0.035),
                                                          scale=0.5, bump=0.2))
    imp = noisy("Imprint", (0.035, 0.025, 0.015), (0.07, 0.05, 0.03), scale=6, bump=0.8)
    fl = leaf_mesh("FossilLeaf", 11, 5.2, droop=0.0, curl=0.0, nu=30, nv=10, mat=imp)
    fl.modifiers["thick"].thickness = 0.02
    fl.location = FO + Vector((-5.5, -0.3, 0.62))
    fl.rotation_euler = (0, 0, math.radians(8))
    upd()
    fm = fl.matrix_world
    curve_obj("FossilRib", [tuple(fm @ Vector((x, 0, 0.02))) for x in (0, 3, 6, 9, 10.8)], 0.06,
              noisy("RibStone", (0.12, 0.09, 0.06), (0.2, 0.16, 0.1), scale=10), grow=False)
    scar = principled("Scar", (0.03, 0.02, 0.015), 0.9)
    sc_pt = fm @ Vector((5.0, 0, 0.03))
    for s in (1, -1):
        o = sphere(f"Scar{s}", sc_pt + fm.to_3x3() @ Vector((0, 0.2 * s, 0)), (0.14, 0.09, 0.03), scar, 16, 8)
        o.rotation_euler = fl.rotation_euler
    tube("ScarLine", sc_pt + fm.to_3x3() @ Vector((0, 0.2, 0)), sc_pt + fm.to_3x3() @ Vector((0, -0.2, 0)),
         0.03, 0.03, scar, 8)
    dome = sphere("FossilDome", FO, (45, 45, 45), emit_mat("DomeM", (0.0, 0.0, 0.0), 0.0), 32, 16)
    dome.visible_shadow = False
    fla = bpy.data.lights.new("FossilKey", "AREA")
    fla.energy = 1800
    fla.size = 6
    fla.color = (1.0, 0.85, 0.65)
    flo = bpy.data.objects.new("FossilKey", fla)
    flo.location = FO + Vector((-16, -4, 4))
    look_at(flo, FO)
    link(flo)
    cue("stone", when(9, "сліди"), "heavy stone slab set down, dusty thud, deep cinematic boom", seconds=2.5)

    # ------------------------------------------------------------ cameras (hard cuts)
    cams = []

    def cam(name, frame, loc, target, lens=50, fstop=2.8, focus=None, end=None):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = fstop
        o = bpy.data.objects.new(name, cd)
        link(o)
        o.location = loc
        look_at(o, target)
        ft = empty(name + "_focus", focus if focus is not None else target)
        cd.dof.focus_object = ft
        m = sc.timeline_markers.new(name, frame=frame)
        m.camera = o
        cams.append((frame, o))
        set_interp("LINEAR")
        if end:  # slow push-in: (frame_end, loc_end, target_end)
            fe, le, te = end
            o.keyframe_insert("location", frame=frame)
            o.keyframe_insert("rotation_euler", frame=frame)
            o.location = le
            look_at(o, te)
            o.keyframe_insert("location", frame=fe)
            o.keyframe_insert("rotation_euler", frame=fe)
            ft.keyframe_insert("location", frame=frame)
            ft.location = te
            ft.keyframe_insert("location", frame=fe)
        set_interp("BEZIER")
        return o

    # S0 teaser: the zombie ant hanging under a leaf
    tant = ta.root.location
    f1 = when(0, "перетворює")
    cam("S0_teaser", 1, tant + Vector((3.0, -4.4, -2.0)), tant + Vector((-0.4, -0.3, -1.35)), lens=45, fstop=2.8,
        focus=tant + Vector((-0.4, -0.2, -0.8)),
        end=(f1, tant + Vector((2.5, -3.7, -1.8)), tant + Vector((-0.4, -0.3, -1.3))))
    # S1 wide trail + the plant
    f2 = when(1)
    cam("S1_trail", f1, (-3.5, -9.5, 2.6), (1.5, 0.5, 0.9), lens=32, fstop=4.0, focus=(0, 0, 0.3),
        end=(f2, (-2.8, -8.0, 2.2), (1.5, 0.5, 0.8)))
    # S2 tracking the hero, spore falls on it
    hx = lambda f: HX0 + v * (f / FPS - t_leave)
    f3 = when(2)
    cam("S2_track", f2, (hx(f2) + 1.7, -3.9, 1.7), (hx(f2) - 0.2, 0, 0.3), lens=50, fstop=2.8,
        end=(f3, (hx(f3) + 1.4, -3.3, 1.45), (hx(f3) - 0.2, 0, 0.3)))
    # S3 x-ray close on the spore
    E_w = XO + E
    cam("S3_xclose", f3, E_w + Vector((0.6, -1.6, 0.55)), E_w + Vector((0, 0, -0.08)), lens=70, fstop=8,
        end=(when(3), E_w + Vector((0.4, -1.2, 0.4)), E_w + Vector((0.03, 0, -0.1))))
    # S4 x-ray whole ant profile
    f5 = when(4)
    cam("S4_xfull", when(3), XO + Vector((2.7, -2.7, 2.0)), XO + Vector((-0.05, 0, 0.3)), lens=55, fstop=11,
        end=(f5, XO + Vector((2.2, -2.2, 1.65)), XO + Vector((-0.05, 0, 0.3))))
    # S5 hero leaves the colony
    cam("S5_leave", f5, (HX0 - 0.5, -4.8, 1.8), (HX0 + 1.4, 1.0, 0.35), lens=45, fstop=2.8,
        focus=(HX0 + 0.4, 0, 0.3), end=(f_b5, (HX0 - 0.2, -3.9, 0.9), (HX0 + 1.6, 1.2, 0.35)))
    # S6 climbing the stem
    cam("S6_climb", f_b5, (SX + 1.0, SY - 4.0, 1.4), (SX, SY - 0.36, 2.0), lens=55, fstop=2.8,
        focus=(SX, SY - 0.4, 1.6), end=(f_down, (SX + 0.8, SY - 3.4, 3.2), (SX, SY - 0.36, 3.8)))
    # S7 under the leaf
    u1 = leaf_under(1.8, side)
    u2 = leaf_under(LX_BITE, side)
    cam("S7_under", f_down, u1 + Vector((2.6, -1.2, -2.0)), u1 + Vector((0, -0.4, -0.2)), lens=45, fstop=2.8,
        end=(f_b6, u2 + Vector((2.4, 0.6, -1.9)), u2 + Vector((0, 0, -0.2))))
    # S8 bite close-up (side view of the head on the vein)
    hb = leaf_under(LX_BITE, 0.1)
    cam("S8_bite", f_b6, hb + Vector((-1.6, -3.0, -1.1)), hb + Vector((0.35, 0, -0.3)), lens=60, fstop=3.5,
        focus=hb + Vector((0.05, 0, -0.25)),
        end=(f_die, hb + Vector((-1.3, -2.5, -0.95)), hb + Vector((0.3, 0, -0.3))))
    # S9 death + stalk (wider, from below)
    cam("S9_stalk", f_die, hb + Vector((3.0, -5.0, -2.2)), hb + Vector((0.5, -0.3, -1.4)), lens=45, fstop=4,
        focus=hb + Vector((0.6, -0.3, -1.0)), end=(when(8), hb + Vector((2.6, -4.3, -2.0)), hb + Vector((0.5, -0.3, -1.45))))
    # S10 spores raining onto the trail below
    cam("S10_rain", when(8), (SX + 9, SY - 13, 1.4), (SX + 0.5, -1.5, 7.0), lens=26, fstop=5.6,
        focus=(SX + 0.6, -1.2, 9.5), end=(when(9), (SX + 8, SY - 11.5, 1.6), (SX + 0.5, -1.5, 7.3)))
    # S11 fossil
    cam("S11_fossil", when(9), FO + Vector((-1.5, -6.5, 13)), FO + Vector((-0.6, 0, 0.6)), lens=35, fstop=5.6,
        end=(END, sc_pt + Vector((0.4, -2.0, 3.2)), sc_pt))
    sc.camera = cams[0][1]

    # extra sound
    cue("ambience", 1, "humid tropical rainforest ambience, insects buzzing, distant exotic birds", seconds=22,
        gain=-8)
    cue("ambience2", when(4), "humid tropical rainforest ambience, cicadas, dripping water", seconds=22, gain=-8)
    cue("hit", f_leave, "ominous low cinematic hit, dark drone swell", seconds=2.5)
    cue("skitter2", f_b5, "tiny insect legs climbing a plant stem, scratchy", seconds=3, gain=-4)
    cue("bite", f_bite + 2, "sharp crunchy bite into a leaf, tiny mandibles snapping shut", seconds=1.0)
    cue("death", f_die, "faint eerie low tone fading out, last breath", seconds=2.5, gain=-3)
    cue("whoosh", when(3), "deep cinematic whoosh, x-ray transition", seconds=1.2, gain=-4)
    cue("whoosh", f5, "short whoosh transition", seconds=1.0, gain=-6)
    return hero


def stills():
    fs = [10, when(0, "перетворює") + 20, when(1, "спора") + 16, when(2, "всередину") + 10,
          when(3, "обплітає") + 30, when(3, "контроль") + 6, when(4, "кидає") + 30, when(5) + 30,
          when(5, "спускається") + 20, when(6, "вчіплюється") + 10, when(7, "помирає") + 30,
          when(7, "проростає") + 50,
          when(8, "сиплються") + 40, when(9) + 40, END - 5]
    return fs


def main():
    build()
    sc = bpy.context.scene
    with open(os.path.join(PROJ, "render.sfx.json"), "w") as f:
        json.dump(sorted(SFX, key=lambda m: m["frame"]), f, indent=1, ensure_ascii=False)
    if MODE == "save":
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(PROJ, "scene.blend"))
        return
    if MODE == "preview":
        out = os.path.join(PROJ, "preview")
        os.makedirs(out, exist_ok=True)
        sc.render.resolution_percentage = int(os.environ.get("PREVIEW_PCT", "40"))
        sc.cycles.samples = int(os.environ.get("PREVIEW_SAMPLES", "24"))
        sc.render.image_settings.file_format = "PNG"
        only = os.environ.get("ONLY")
        frames = [int(x) for x in only.split(",")] if only else stills()
        for fr in frames:
            sc.frame_set(fr)
            sc.render.filepath = os.path.join(out, f"f{fr:04d}.png")
            bpy.ops.render.render(write_still=True)
            print("still", fr)
        return
    half = MODE == "half"
    sc.render.resolution_percentage = {"half": 50, "mid": 67, "full": 100}[MODE]
    sc.cycles.samples = int(os.environ.get("SAMPLES", "20" if half else "40"))
    out = os.path.join(PROJ, "frames_" + MODE)
    os.makedirs(out, exist_ok=True)
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.compression = 30
    sc.render.use_overwrite = False
    sc.render.use_placeholder = True
    sc.render.filepath = os.path.join(out, "f")
    if RANGE:
        a, b = RANGE.split(":")
        sc.frame_start, sc.frame_end = int(a), int(b)
    sc.frame_step = int(os.environ.get("STEP", "1"))
    bpy.ops.render.render(animation=True)


main()
