"""Small helper library for the Clockmaker short (Blender 5.x, Cycles, headless bpy).

Everything that moves is driven procedurally from the frame number by a frame_change_pre handler
(see build.py), so any frame can be rendered on its own and in any order.
"""
from __future__ import annotations

import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "tex")
os.makedirs(TEX, exist_ok=True)
FONT_SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"

# ------------------------------------------------------------------ utils
def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def smoother(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * x * (x * (x * 6 - 15) + 10)


def lerp(a, b, u):
    return a + (b - a) * u


def vlerp(a, b, u):
    return Vector(a).lerp(Vector(b), u)


def ramp(t, t0, t1):
    if t1 <= t0:
        return 1.0 if t >= t1 else 0.0
    return min(max((t - t0) / (t1 - t0), 0.0), 1.0)


COLL = [None]


def link(o, coll=None):
    (coll or COLL[0] or bpy.context.scene.collection).objects.link(o)
    return o


def empty(name, loc=(0, 0, 0), parent=None, rot=(0, 0, 0)):
    o = bpy.data.objects.new(name, None)
    o.empty_display_size = 0.05
    link(o)
    o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    return o


def obj(name, mesh, loc=(0, 0, 0), mat=None, parent=None, rot=(0, 0, 0), scale=(1, 1, 1)):
    o = bpy.data.objects.new(name, mesh)
    link(o)
    o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    o.scale = scale
    if mat is not None:
        if len(o.data.materials) == 0:
            o.data.materials.append(mat)
        else:
            o.material_slots[0].link = "OBJECT"
            o.material_slots[0].material = mat
    return o


def set_mat(o, mat):
    if len(o.data.materials) == 0:
        o.data.materials.append(mat)
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = mat


# ------------------------------------------------------------------ meshes (shared data)
_MESH = {}


def _finish(me, smooth_=True):
    if smooth_:
        try:
            me.shade_smooth()
        except Exception:
            for p in me.polygons:
                p.use_smooth = True
    return me


def m_sphere(seg=32, ring=16):
    k = ("sph", seg, ring)
    if k not in _MESH:
        me = bpy.data.meshes.new("sphere")
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1.0)
        bm.to_mesh(me)
        bm.free()
        _MESH[k] = _finish(me)
    return _MESH[k]


def m_cube(bevel=0.0):
    k = ("cube", bevel)
    if k not in _MESH:
        me = bpy.data.meshes.new("cube")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        if bevel > 0:
            bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2, affect="EDGES", profile=0.5)
        bm.to_mesh(me)
        bm.free()
        _MESH[k] = _finish(me, smooth_=False) if bevel == 0 else me
        if bevel > 0:
            for p in me.polygons:
                p.use_smooth = True
            try:
                me.set_sharp_from_angle(angle=math.radians(40))
            except Exception:
                pass
    return _MESH[k]


def m_cyl(seg=48, r1=1.0, r2=1.0, cap=True):
    """Cylinder/cone of height 1 along Z, centred at origin."""
    k = ("cyl", seg, r1, r2, cap)
    if k not in _MESH:
        me = bpy.data.meshes.new("cyl")
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r1, radius2=r2, depth=1.0)
        bm.to_mesh(me)
        bm.free()
        _finish(me)
        try:
            me.set_sharp_from_angle(angle=math.radians(50))
        except Exception:
            pass
        _MESH[k] = me
    return _MESH[k]


def m_torus(R=1.0, r=0.1, seg=48, rseg=12, a0=0.0, a1=2 * math.pi):
    k = ("tor", R, r, seg, rseg, a0, a1)
    if k in _MESH:
        return _MESH[k]
    closed = abs((a1 - a0) - 2 * math.pi) < 1e-6
    n = seg if closed else seg + 1
    verts, faces = [], []
    for i in range(n):
        a = a0 + (a1 - a0) * i / seg
        for j in range(rseg):
            b = 2 * math.pi * j / rseg
            x = (R + r * math.cos(b)) * math.cos(a)
            y = (R + r * math.cos(b)) * math.sin(a)
            z = r * math.sin(b)
            verts.append((x, y, z))
    for i in range(seg):
        i2 = (i + 1) % n
        for j in range(rseg):
            j2 = (j + 1) % rseg
            faces.append((i * rseg + j, i2 * rseg + j, i2 * rseg + j2, i * rseg + j2))
    if not closed:  # round caps
        for end, ii in ((0, 0), (1, n - 1)):
            c = len(verts)
            a = a0 if end == 0 else a1
            verts.append((R * math.cos(a), R * math.sin(a), 0))
            for j in range(rseg):
                j2 = (j + 1) % rseg
                faces.append((c, ii * rseg + j2, ii * rseg + j) if end == 0 else (c, ii * rseg + j, ii * rseg + j2))
    me = bpy.data.meshes.new("torus")
    me.from_pydata(verts, [], faces)
    me.update()
    _MESH[k] = _finish(me)
    return me


def m_disc(seg=64):
    """Unit disc in the XZ plane facing -Y, UVs mapped from x/z (for dial textures)."""
    k = ("disc", seg)
    if k in _MESH:
        return _MESH[k]
    verts = [(0, 0, 0)] + [(math.cos(2 * math.pi * i / seg), 0, math.sin(2 * math.pi * i / seg)) for i in range(seg)]
    faces = [(0, 1 + (i + 1) % seg, 1 + i) for i in range(seg)]
    me = bpy.data.meshes.new("disc")
    me.from_pydata(verts, [], faces)
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (0.5 + v.x * 0.5, 0.5 + v.z * 0.5)
    for p in me.polygons:
        if p.normal.y > 0:
            p.flip()
    me.update()
    _MESH[k] = me
    return me


def m_plane_uv(nx=1, ny=1):
    """Unit plane in XY (z=0), subdivided, with UVs."""
    k = ("plane", nx, ny)
    if k in _MESH:
        return _MESH[k]
    verts, faces = [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            verts.append((i / nx - 0.5, j / ny - 0.5, 0))
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    me = bpy.data.meshes.new("plane")
    me.from_pydata(verts, [], faces)
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (v.x + 0.5, v.y + 0.5)
    me.update()
    _MESH[k] = me
    return me


def m_prism():
    """Gable roof prism: base 1x1 at z=0, ridge along X at z=1 (y=0)."""
    k = ("prism",)
    if k not in _MESH:
        v = [(-.5, -.5, 0), (.5, -.5, 0), (.5, .5, 0), (-.5, .5, 0), (-.5, 0, 1), (.5, 0, 1)]
        f = [(0, 1, 5, 4), (2, 3, 4, 5), (1, 2, 5), (3, 0, 4), (0, 3, 2, 1)]
        me = bpy.data.meshes.new("prism")
        me.from_pydata(v, [], f)
        me.update()
        _MESH[k] = me
    return _MESH[k]


def sphere(name, loc, r, mat, parent=None, rot=(0, 0, 0)):
    if isinstance(r, (int, float)):
        r = (r, r, r)
    return obj(name, m_sphere(), loc, mat, parent, rot, r)


def box(name, loc, size, mat, parent=None, rot=(0, 0, 0), bevel=0.0):
    return obj(name, m_cube(bevel), loc, mat, parent, rot, size)


def cyl(name, loc, r, h, mat, parent=None, rot=(0, 0, 0), seg=48, r2=None):
    if r2 is None:
        me = m_cyl(seg)
        return obj(name, me, loc, mat, parent, rot, (r, r, h))
    me = m_cyl(seg, 1.0, r2 / r)
    return obj(name, me, loc, mat, parent, rot, (r, r, h))


def torus(name, loc, R, r, mat, parent=None, rot=(0, 0, 0), a0=0.0, a1=2 * math.pi, seg=48):
    return obj(name, m_torus(1.0, r / R, seg, 12, a0, a1), loc, mat, parent, rot, (R, R, R))


def limb(name, parent, length, r0, r1, mat, down=True):
    """Tapered capsule hanging from the parent pivot along -Z (or +Z)."""
    s = -1 if down else 1
    o = cyl(name, (0, 0, s * length / 2), r0, length, mat, parent, r2=r1, seg=24)
    if down:
        o.rotation_euler = (math.pi, 0, 0)
    sphere(name + "_j0", (0, 0, 0), r0, mat, parent)
    sphere(name + "_j1", (0, 0, s * length), r1, mat, parent)
    return o


# ------------------------------------------------------------------ materials
def _bsdf(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def _set(n, key, val):
    if key in n.inputs:
        n.inputs[key].default_value = val


def mat(name, color, rough=0.5, metal=0.0, sss=0.0, coat=0.0, sheen=0.0, emit=None, emit_str=0.0, alpha=1.0,
        transmission=0.0, ior=1.45, spec=0.5):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = _bsdf(m)
    _set(b, "Base Color", (*color, 1))
    _set(b, "Roughness", rough)
    _set(b, "Metallic", metal)
    _set(b, "IOR", ior)
    _set(b, "Specular IOR Level", spec)
    if sss:
        _set(b, "Subsurface Weight", sss)
        _set(b, "Subsurface Radius", (1.0, 0.45, 0.3))
        _set(b, "Subsurface Scale", 0.04)
    if coat:
        _set(b, "Coat Weight", coat)
        _set(b, "Coat Roughness", 0.05)
    if sheen:
        _set(b, "Sheen Weight", sheen)
    if emit:
        _set(b, "Emission Color", (*emit, 1))
        _set(b, "Emission Strength", emit_str)
    if transmission:
        _set(b, "Transmission Weight", transmission)
    if alpha < 1:
        _set(b, "Alpha", alpha)
    return m


def emit(name, color, strength=5.0):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*color, 1)
    e.inputs["Strength"].default_value = strength
    nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def emit_strength_socket(m):
    for n in m.node_tree.nodes:
        if n.type == "EMISSION":
            return n.inputs["Strength"]
        if n.type == "BSDF_PRINCIPLED":
            return n.inputs["Emission Strength"]


def color_socket(m):
    for n in m.node_tree.nodes:
        if n.type == "EMISSION":
            return n.inputs["Color"]
        if n.type == "BSDF_PRINCIPLED":
            return n.inputs["Base Color"]


def noise_mat(name, c1, c2, scale=8.0, rough=0.6, bump=0.3, metal=0.0, kind="noise", detail=6.0, mapping="Object"):
    """Two-colour procedural material (noise / voronoi / wave) with bump. Object-space so it never swims."""
    m = mat(name, c1, rough, metal)
    nt = m.node_tree
    b = _bsdf(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    if kind == "voronoi":
        t = nt.nodes.new("ShaderNodeTexVoronoi")
        t.feature = "DISTANCE_TO_EDGE" if hasattr(t, "feature") else t.feature
        out = t.outputs["Distance"]
    elif kind == "wave":
        t = nt.nodes.new("ShaderNodeTexWave")
        t.inputs["Distortion"].default_value = 4.0
        out = t.outputs["Fac"]
    else:
        t = nt.nodes.new("ShaderNodeTexNoise")
        t.inputs["Detail"].default_value = detail
        out = t.outputs["Fac"]
    t.inputs["Scale"].default_value = scale
    nt.links.new(tc.outputs[mapping], t.inputs["Vector"])
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (*c1, 1)
    cr.color_ramp.elements[1].color = (*c2, 1)
    if kind == "voronoi":
        cr.color_ramp.elements[0].position = 0.0
        cr.color_ramp.elements[1].position = 0.08
    else:
        cr.color_ramp.elements[0].position = 0.3
        cr.color_ramp.elements[1].position = 0.7
    nt.links.new(out, cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], b.inputs["Base Color"])
    if bump:
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        nt.links.new(out, bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def image_mat(name, path, rough=0.5, emit_str=0.0, metal=0.0, alpha=False, emit_color=None):
    m = mat(name, (1, 1, 1), rough, metal)
    nt = m.node_tree
    b = _bsdf(m)
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = bpy.data.images.load(path, check_existing=True)
    tx.image.pack()
    nt.links.new(tx.outputs["Color"], b.inputs["Base Color"])
    if emit_str:
        nt.links.new(tx.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = emit_str
    if alpha:
        nt.links.new(tx.outputs["Alpha"], b.inputs["Alpha"])
    return m


def volume_mat(name, color=(0.6, 0.7, 0.9), density=0.02, anisotropy=0.3, height_falloff=None):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    v = nt.nodes.new("ShaderNodeVolumeScatter")
    v.inputs["Color"].default_value = (*color, 1)
    v.inputs["Anisotropy"].default_value = anisotropy
    if height_falloff:
        z0, z1 = height_falloff  # dense at z0, thin at z1 (world z)
        tc = nt.nodes.new("ShaderNodeNewGeometry")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Position"], sep.inputs[0])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value = z0
        mr.inputs["From Max"].default_value = z1
        mr.inputs["To Min"].default_value = density
        mr.inputs["To Max"].default_value = density * 0.15
        nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], v.inputs["Density"])
        m["density_node"] = mr.name
    else:
        v.inputs["Density"].default_value = density
    nt.links.new(v.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    return m


# ------------------------------------------------------------------ lights / text
def light(name, kind, loc, energy, color=(1, 1, 1), size=0.1, rot=(0, 0, 0), parent=None, spot=None):
    l = bpy.data.lights.new(name, kind)
    l.energy = energy
    l.color = color
    if kind == "AREA":
        l.size = size
    elif kind in ("POINT", "SPOT"):
        l.shadow_soft_size = size
    elif kind == "SUN":
        l.angle = size
    if kind == "SPOT" and spot:
        l.spot_size = spot
        l.spot_blend = 0.6
    o = bpy.data.objects.new(name, l)
    link(o)
    o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    return o


def aim(o, target):
    d = Vector(target) - o.matrix_world.translation if o.parent else Vector(target) - Vector(o.location)
    o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


_FONTS = {}


def font(path=FONT_SERIF):
    if path not in _FONTS:
        _FONTS[path] = bpy.data.fonts.load(path)
    return _FONTS[path]


def text(name, body, loc, size, mat_, parent=None, rot=(math.pi / 2, 0, 0), extrude=0.0, fpath=FONT_SERIF, align="CENTER"):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = font(fpath)
    cu.size = size
    cu.extrude = extrude
    cu.align_x = align
    cu.align_y = "CENTER"
    o = bpy.data.objects.new(name, cu)
    link(o)
    o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    o.data.materials.append(mat_)
    return o


# ------------------------------------------------------------------ point clouds (dust, snow, sparks)
_PTS_NG = {}


def _points_group(radius, m):
    key = (round(radius, 5), m.name)
    if key in _PTS_NG:
        return _PTS_NG[key]
    ng = bpy.data.node_groups.new("Pts", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi = ng.nodes.new("NodeGroupInput")
    go = ng.nodes.new("NodeGroupOutput")
    mp = ng.nodes.new("GeometryNodeMeshToPoints")
    mp.inputs["Radius"].default_value = radius
    rad = ng.nodes.new("GeometryNodeInputNamedAttribute")
    rad.data_type = "FLOAT"
    rad.inputs["Name"].default_value = "size"
    mul = ng.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = radius
    ng.links.new(rad.outputs["Attribute"], mul.inputs[0])
    ng.links.new(mul.outputs[0], mp.inputs["Radius"])
    sm = ng.nodes.new("GeometryNodeSetMaterial")
    sm.inputs["Material"].default_value = m
    ng.links.new(gi.outputs[0], mp.inputs["Mesh"])
    ng.links.new(mp.outputs[0], sm.inputs["Geometry"])
    ng.links.new(sm.outputs[0], go.inputs[0])
    _PTS_NG[key] = ng
    return ng


class Points:
    """N points whose positions are recomputed every frame by a python function."""

    def __init__(self, name, n, radius, m, parent=None):
        self.n = n
        me = bpy.data.meshes.new(name)
        me.vertices.add(n)
        me.attributes.new("size", "FLOAT", "POINT")
        self.me = me
        self.park = (0.0, 0.0, -30.0)
        self.o = obj(name, me, parent=parent)
        mod = self.o.modifiers.new("pts", "NODES")
        mod.node_group = _points_group(radius, m)
        self.hide()

    def set(self, pos, size=None):
        self._hidden = False
        pos = np.asarray(pos, dtype=np.float32).reshape(-1, 3)
        if len(pos) < self.n:
            pad = np.tile(np.array(self.park, np.float32), (self.n - len(pos), 1))
            pos = np.vstack([pos, pad])
            if size is not None:
                size = np.concatenate([np.asarray(size, np.float32), np.zeros(self.n - len(size), np.float32)])
        self.me.vertices.foreach_set("co", pos[: self.n].ravel())
        if size is None:
            size = np.ones(self.n, np.float32)
        self.me.attributes["size"].data.foreach_set("value", np.asarray(size, np.float32)[: self.n])
        self.me.update()

    def hide(self):
        if getattr(self, "_hidden", False):
            return
        self.set(np.tile(np.array(self.park, np.float32), (self.n, 1)), np.zeros(self.n, np.float32))
        self._hidden = True


# ------------------------------------------------------------------ dial textures (PIL)
def dial_png(path, face=(236, 224, 196), ink=(40, 30, 22), ring=(150, 110, 50), roman=True, size=1024, stains=True, seed=0):
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    if os.path.exists(path):
        return path
    rng = np.random.default_rng(seed)
    S = size
    img = Image.new("RGB", (S, S), face)
    if stains:
        n = (rng.random((S // 16, S // 16)) * 255).astype(np.uint8)
        noise = Image.fromarray(n).resize((S, S), Image.BICUBIC).filter(ImageFilter.GaussianBlur(18))
        arr = np.asarray(img).astype(np.float32)
        nn = (np.asarray(noise).astype(np.float32) / 255.0 - 0.5)[..., None]
        yy, xx = np.mgrid[0:S, 0:S]
        r = np.sqrt((xx - S / 2) ** 2 + (yy - S / 2) ** 2) / (S / 2)
        arr = arr * (1 + 0.18 * nn) * (1 - 0.25 * np.clip(r - 0.6, 0, 1)[..., None])
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    c = S / 2
    d.ellipse([S * 0.03, S * 0.03, S * 0.97, S * 0.97], outline=ring, width=int(S * 0.025))
    d.ellipse([S * 0.10, S * 0.10, S * 0.90, S * 0.90], outline=ink, width=int(S * 0.004))
    d.ellipse([S * 0.14, S * 0.14, S * 0.86, S * 0.86], outline=ink, width=int(S * 0.003))
    for k in range(60):
        a = math.radians(k * 6)
        r0, r1 = (0.36, 0.43) if k % 5 == 0 else (0.39, 0.43)
        w = int(S * (0.008 if k % 5 == 0 else 0.003))
        d.line([(c + S * r0 * math.sin(a), c - S * r0 * math.cos(a)), (c + S * r1 * math.sin(a), c - S * r1 * math.cos(a))], fill=ink, width=w)
    fnt = ImageFont.truetype(FONT_SERIF, int(S * 0.075))
    labels = ["XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"] if roman else [str(k if k else 12) for k in range(12)]
    for k, lab in enumerate(labels):
        a = math.radians(k * 30)
        x, y = c + S * 0.29 * math.sin(a), c - S * 0.29 * math.cos(a)
        d.text((x, y), lab, font=fnt, fill=ink, anchor="mm")
    img.save(path)
    return path


def crack_png(path, size=1024, seed=3):
    """White crack lines on black (used as a mask, revealed from the centre outwards)."""
    from PIL import Image, ImageDraw, ImageFilter
    if os.path.exists(path):
        return path
    rng = np.random.default_rng(seed)
    S = size
    img = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(img)
    cx, cy = S * 0.46, S * 0.58

    def branch(x, y, a, length, w, depth):
        steps = int(length / 14)
        for _ in range(steps):
            a += rng.normal(0, 0.25)
            nx, ny = x + 14 * math.cos(a), y + 14 * math.sin(a)
            d.line([(x, y), (nx, ny)], fill=255, width=max(1, int(w)))
            x, y = nx, ny
            w *= 0.985
            if depth < 3 and rng.random() < 0.06:
                branch(x, y, a + rng.choice([-1, 1]) * rng.uniform(0.5, 1.1), length * 0.45, w * 0.7, depth + 1)
    for k in range(9):
        branch(cx, cy, k * 2 * math.pi / 9 + rng.normal(0, 0.2), S * rng.uniform(0.35, 0.6), 6, 0)
    for rr in (0.08, 0.17, 0.3):
        pts = []
        for k in range(40):
            a = 2 * math.pi * k / 39
            r = S * rr * (1 + rng.normal(0, 0.08))
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        for k in range(len(pts) - 1):
            if rng.random() < 0.7:
                d.line([pts[k], pts[k + 1]], fill=200, width=2)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    img.save(path)
    return path


def m_lathe(profile, seg=48, key=None):
    """Closed smooth surface of revolution around Z. profile: [(r, z), ...] from top to bottom."""
    k = ("lathe", key or tuple(profile), seg)
    if k in _MESH:
        return _MESH[k]
    verts, faces = [], []
    n = len(profile)
    for (r, z) in profile:
        for i in range(seg):
            a = 2 * math.pi * i / seg
            verts.append((r * math.cos(a), r * math.sin(a), z))
    for j in range(n - 1):
        for i in range(seg):
            i2 = (i + 1) % seg
            faces.append((j * seg + i, j * seg + i2, (j + 1) * seg + i2, (j + 1) * seg + i))
    top = len(verts)
    verts.append((0, 0, profile[0][1]))
    bot = len(verts)
    verts.append((0, 0, profile[-1][1]))
    for i in range(seg):
        i2 = (i + 1) % seg
        faces.append((top, i2, i))
        faces.append((bot, (n - 1) * seg + i, (n - 1) * seg + i2))
    me = bpy.data.meshes.new("lathe")
    me.from_pydata(verts, [], faces)
    me.update()
    me.validate()
    for p in me.polygons:
        p.use_smooth = True
    _MESH[k] = me
    return me


def lathe(name, loc, profile, m, parent=None, rot=(0, 0, 0), scale=(1, 1, 1), seg=48):
    return obj(name, m_lathe(profile, seg), loc, m, parent, rot, scale)


def bell(top_r, bot_r, h, round_=0.25):
    """Profile of a skirt/coat/cape: rounded top shoulder and rolled hem."""
    pr = []
    for k in range(7):
        u = k / 6
        pr.append((top_r * 0.6 + top_r * 0.4 * math.sin(u * math.pi / 2), 0.04 * h * math.cos(u * math.pi / 2)))
    for k in range(1, 9):
        u = k / 8
        pr.append((top_r + (bot_r - top_r) * (u ** 1.3), -h * u * (1 - round_ * 0.1)))
    for k in range(1, 5):
        a = k / 4 * math.pi / 2
        pr.append((bot_r - h * 0.04 * (1 - math.cos(a)) * 0 + 0.0 - (h * 0.05) * math.sin(a), -h - h * 0.03 * math.sin(a)))
    pr.append((bot_r * 0.6, -h - h * 0.03))
    return pr


def cobble_png(path_col, path_nrm, size=1024, n=90, seed=7):
    """Tileable cobblestone colour + normal map (numpy voronoi, wrap-around)."""
    if os.path.exists(path_col) and os.path.exists(path_nrm):
        return path_col, path_nrm
    from PIL import Image, ImageFilter
    rng = np.random.default_rng(seed)
    S = size
    pts = rng.random((n, 2)) * S
    allp = np.concatenate([pts + np.array([dx, dy]) * S for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    d1 = np.full((S, S), 1e9, np.float32)
    d2 = np.full((S, S), 1e9, np.float32)
    idx = np.zeros((S, S), np.int32)
    for k, (px, py) in enumerate(allp):
        d = np.sqrt((xx - px) ** 2 + (yy - py) ** 2)
        m = d < d1
        d2 = np.where(m, d1, np.minimum(d2, d))
        idx = np.where(m, k % n, idx)
        d1 = np.where(m, d, d1)
    edge = (d2 - d1)
    h = np.clip(edge / 18.0, 0, 1) ** 0.6
    noise = np.asarray(Image.fromarray((rng.random((S // 8, S // 8)) * 255).astype(np.uint8)).resize((S, S), Image.BICUBIC), np.float32) / 255
    h = h * (0.85 + 0.15 * noise)
    tone = rng.uniform(0.75, 1.25, n)[idx]
    base = np.array([0.20, 0.185, 0.17]) * 255
    col = base[None, None, :] * tone[..., None] * (0.55 + 0.45 * h[..., None]) * (0.9 + 0.2 * noise[..., None])
    gap = (edge < 3.0)[..., None]
    col = np.where(gap, np.array([22, 20, 18]), col)
    Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).save(path_col)
    hb = np.asarray(Image.fromarray((h * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
    gx = (np.roll(hb, -1, 1) - np.roll(hb, 1, 1)) * 3.0
    gy = (np.roll(hb, -1, 0) - np.roll(hb, 1, 0)) * 3.0
    nz = np.ones_like(gx)
    nrm = np.stack([-gx, gy, nz], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    Image.fromarray(((nrm * 0.5 + 0.5) * 255).astype(np.uint8)).save(path_nrm)
    return path_col, path_nrm


def cobble_mat(name, scale=0.35):
    pc, pn = cobble_png(os.path.join(TEX, "cobble_col.png"), os.path.join(TEX, "cobble_nrm.png"))
    m = mat(name, (0.2, 0.2, 0.2), 0.42)
    nt = m.node_tree
    b = _bsdf(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (scale, scale, scale)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = bpy.data.images.load(pc, check_existing=True)
    tx.image.pack()
    nt.links.new(mp.outputs["Vector"], tx.inputs["Vector"])
    nt.links.new(tx.outputs["Color"], b.inputs["Base Color"])
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = bpy.data.images.load(pn, check_existing=True)
    tn.image.colorspace_settings.name = "Non-Color"
    tn.image.pack()
    nt.links.new(mp.outputs["Vector"], tn.inputs["Vector"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 1.0
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


_STREAK_NG = {}


def _streak_group(length, radius, m):
    key = (length, radius, m.name)
    if key in _STREAK_NG:
        return _STREAK_NG[key]
    ng = bpy.data.node_groups.new("Streaks", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi = ng.nodes.new("NodeGroupInput")
    go = ng.nodes.new("NodeGroupOutput")
    mp = ng.nodes.new("GeometryNodeMeshToPoints")
    cy_ = ng.nodes.new("GeometryNodeMeshCylinder")
    cy_.inputs["Vertices"].default_value = 5
    cy_.inputs["Radius"].default_value = radius
    cy_.inputs["Depth"].default_value = length
    ip = ng.nodes.new("GeometryNodeInstanceOnPoints")
    rad = ng.nodes.new("GeometryNodeInputNamedAttribute")
    rad.data_type = "FLOAT"
    rad.inputs["Name"].default_value = "size"
    ng.links.new(rad.outputs["Attribute"], ip.inputs["Scale"])
    sm = ng.nodes.new("GeometryNodeSetMaterial")
    sm.inputs["Material"].default_value = m
    ng.links.new(gi.outputs[0], mp.inputs["Mesh"])
    ng.links.new(mp.outputs[0], ip.inputs["Points"])
    ng.links.new(cy_.outputs["Mesh"], ip.inputs["Instance"])
    ng.links.new(ip.outputs[0], sm.inputs["Geometry"])
    ng.links.new(sm.outputs[0], go.inputs[0])
    _STREAK_NG[key] = ng
    return ng


class Streaks(Points):
    def __init__(self, name, n, length, radius, m):
        me = bpy.data.meshes.new(name)
        me.vertices.add(n)
        me.attributes.new("size", "FLOAT", "POINT")
        self.n = n
        self.me = me
        self.park = (0.0, 0.0, -30.0)
        self.o = obj(name, me)
        mod = self.o.modifiers.new("pts", "NODES")
        mod.node_group = _streak_group(length, radius, m)
        self.hide()


def mirror_matrix(c, n):
    """4x4 reflection across the plane through point c with normal n."""
    n = Vector(n).normalized()
    R = Matrix.Identity(4)
    for i in range(3):
        for j in range(3):
            R[i][j] = (1 if i == j else 0) - 2 * n[i] * n[j]
    return Matrix.Translation(Vector(c)) @ R @ Matrix.Translation(-Vector(c))
