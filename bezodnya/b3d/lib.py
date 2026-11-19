"""Мінімальна бібліотека для процедурних підводних 3D-сцен у Blender (bpy 5.0, EEVEE).

Анімація робиться власним циклом: для кожного кадру викликається update(t), потім render.
"""
import math
import os
import random

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

RES = (960, 540)
FPS = 12


# ---------------------------------------------------------------- сцена
def reset(world_col=(0.0, 0.01, 0.025), density=0.02, anisotropy=0.6, vol_col=(0.3, 0.55, 0.7), samples=6,
          strength=1.0):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.render.resolution_percentage = 100
    sc.eevee.taa_render_samples = samples
    try:
        sc.eevee.volumetric_tile_size = "8"
        sc.eevee.volumetric_samples = 32
        sc.eevee.use_volumetric_shadows = False
        sc.eevee.volumetric_end = 120
    except Exception:
        pass
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 93
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    bg.inputs[0].default_value = (*world_col, 1)
    bg.inputs[1].default_value = strength
    if density > 0:
        v = nt.nodes.new("ShaderNodeVolumePrincipled")
        v.inputs["Color"].default_value = (*vol_col, 1)
        v.inputs["Density"].default_value = density
        v.inputs["Anisotropy"].default_value = anisotropy
        nt.links.new(v.outputs[0], nt.nodes["World Output"].inputs["Volume"])
    return sc


def camera(loc, look_at=None, lens=35, rot=None):
    cd = bpy.data.cameras.new("Cam")
    cd.lens = lens
    cd.clip_start = 0.05
    cd.clip_end = 400
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam.location = loc
    if look_at is not None:
        aim(cam, look_at)
    elif rot is not None:
        cam.rotation_euler = rot
    return cam


def aim(obj, target, roll=0.0):
    d = Vector(target) - obj.location
    q = d.to_track_quat("-Z", "Y")
    obj.rotation_euler = q.to_euler()
    if roll:
        obj.rotation_euler.rotate_axis("Z", roll)


def dof(cam, focus_obj=None, dist=None, fstop=2.8):
    cam.data.dof.use_dof = True
    if focus_obj is not None:
        cam.data.dof.focus_object = focus_obj
    if dist is not None:
        cam.data.dof.focus_distance = dist
    cam.data.dof.aperture_fstop = fstop


def light(kind, loc, energy, color=(1, 1, 1), target=None, size=0.2, spot=45, blend=0.4, rot=None, vol=1.0):
    ld = bpy.data.lights.new("L", kind)
    ld.energy = energy
    ld.color = color
    try:
        ld.shadow_soft_size = size
    except Exception:
        pass
    if kind == "SPOT":
        ld.spot_size = math.radians(spot)
        ld.spot_blend = blend
    if kind == "AREA":
        ld.size = size
    try:
        ld.volume_factor = vol
    except Exception:
        pass
    ob = bpy.data.objects.new("L", ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    if target is not None:
        aim(ob, target)
    elif rot is not None:
        ob.rotation_euler = rot
    return ob


# ---------------------------------------------------------------- матеріали
_mats = {}


def mat(name, color=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, emit=None, emit_str=0.0, alpha=1.0, sss=0.0,
        noise=0.0, noise_scale=8.0, trans=0.0, spec=0.5, coat=0.0, bump=0.0):
    key = (name,)
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit is not None:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = emit_str
    if sss:
        b.inputs["Subsurface Weight"].default_value = sss
        b.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.25)
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    if trans:
        b.inputs["Transmission Weight"].default_value = trans
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            m.blend_method = "BLEND"
    if noise > 0 or bump > 0:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = noise_scale
        nz.inputs["Detail"].default_value = 8
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        if noise > 0:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.inputs["Factor"].default_value = noise
            mix.inputs[6].default_value = (*color, 1)
            mix.inputs[7].default_value = (color[0] * 0.35, color[1] * 0.35, color[2] * 0.35, 1)
            nt.links.new(nz.outputs["Fac"], mix.inputs["Factor"]) if noise >= 1 else None
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].color = (color[0] * (1 - noise), color[1] * (1 - noise), color[2] * (1 - noise), 1)
            ramp.color_ramp.elements[1].color = (*color, 1)
            nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
        if bump > 0:
            bm = nt.nodes.new("ShaderNodeBump")
            bm.inputs["Strength"].default_value = bump
            nt.links.new(nz.outputs["Fac"], bm.inputs["Height"])
            nt.links.new(bm.outputs["Normal"], b.inputs["Normal"])
    _mats[key] = m
    return m


def emissive(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type == "BSDF_PRINCIPLED":
            nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs[0].default_value = (*color, 1)
    e.inputs[1].default_value = strength
    nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def set_emit(m, strength):
    for n in m.node_tree.nodes:
        if n.type == "EMISSION":
            n.inputs[1].default_value = strength
        elif n.type == "BSDF_PRINCIPLED":
            n.inputs["Emission Strength"].default_value = strength


# ---------------------------------------------------------------- геометрія
def obj_from_bm(name, bm, material=None, smooth=True, subsurf=0):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    if material is not None:
        me.materials.append(material)
    if subsurf:
        md = ob.modifiers.new("S", "SUBSURF")
        md.levels = subsurf
        md.render_levels = subsurf
    return ob


def prim(kind, loc=(0, 0, 0), scale=(1, 1, 1), rot=(0, 0, 0), material=None, smooth=True, subsurf=0, **kw):
    fn = {"sphere": bpy.ops.mesh.primitive_uv_sphere_add, "ico": bpy.ops.mesh.primitive_ico_sphere_add,
          "cube": bpy.ops.mesh.primitive_cube_add, "cyl": bpy.ops.mesh.primitive_cylinder_add,
          "cone": bpy.ops.mesh.primitive_cone_add, "plane": bpy.ops.mesh.primitive_plane_add,
          "torus": bpy.ops.mesh.primitive_torus_add}[kind]
    fn(location=loc, rotation=rot, **kw)
    ob = bpy.context.object
    ob.scale = scale
    if smooth and kind not in ("cube", "plane"):
        bpy.ops.object.shade_smooth()
    if material is not None:
        ob.data.materials.append(material)
    if subsurf:
        md = ob.modifiers.new("S", "SUBSURF")
        md.levels = subsurf
        md.render_levels = subsurf
    return ob


def loft(name, n_len, profile, length=1.0, ring=16, material=None, subsurf=1, flat=1.0):
    """Тіло обертання вздовж осі X: profile(u)-> (r_y, r_z, offset_z), u від 0 (ніс, +X) до 1 (хвіст)."""
    bm = bmesh.new()
    rings = []
    for i in range(n_len + 1):
        u = i / n_len
        ry, rz, oz = profile(u)
        x = length * (0.5 - u)
        vs = []
        for j in range(ring):
            a = 2 * math.pi * j / ring
            vs.append(bm.verts.new((x, math.cos(a) * max(ry, 1e-4) * flat, oz + math.sin(a) * max(rz, 1e-4))))
        rings.append(vs)
    for i in range(n_len):
        for j in range(ring):
            a, b = rings[i][j], rings[i][(j + 1) % ring]
            c, d = rings[i + 1][(j + 1) % ring], rings[i + 1][j]
            bm.faces.new((a, b, c, d))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    return obj_from_bm(name, bm, material, True, subsurf)


def tube(name, pts, radii, ring=10, material=None, subsurf=0):
    """Трубка вздовж ламаної pts (список Vector) із радіусами radii."""
    bm = bmesh.new()
    rings = []
    n = len(pts)
    for i in range(n):
        p = Vector(pts[i])
        d = (Vector(pts[min(i + 1, n - 1)]) - Vector(pts[max(i - 1, 0)])).normalized()
        up = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
        s = d.cross(up).normalized()
        u2 = s.cross(d).normalized()
        vs = []
        for j in range(ring):
            a = 2 * math.pi * j / ring
            vs.append(bm.verts.new(p + (s * math.cos(a) + u2 * math.sin(a)) * radii[i]))
        rings.append(vs)
    for i in range(n - 1):
        for j in range(ring):
            bm.faces.new((rings[i][j], rings[i][(j + 1) % ring], rings[i + 1][(j + 1) % ring], rings[i + 1][j]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    return obj_from_bm(name, bm, material, True, subsurf)


def update_tube(ob, pts, radii, ring=10):
    co = []
    n = len(pts)
    for i in range(n):
        p = Vector(pts[i])
        d = (Vector(pts[min(i + 1, n - 1)]) - Vector(pts[max(i - 1, 0)])).normalized()
        up = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
        s = d.cross(up).normalized()
        u2 = s.cross(d).normalized()
        for j in range(ring):
            a = 2 * math.pi * j / ring
            v = p + (s * math.cos(a) + u2 * math.sin(a)) * radii[i]
            co.extend(v)
    ob.data.vertices.foreach_set("co", co)
    ob.data.update()


def terrain(name, size=60, res=160, amp=0.6, seed=1, material=None, scale=6.0, loc=(0, 0, 0), ridge=None):
    """Дно: площина з fbm-рельєфом."""
    rng = np.random.default_rng(seed)
    xs = np.linspace(-size / 2, size / 2, res)
    X, Y = np.meshgrid(xs, xs)
    Z = np.zeros_like(X)
    for k, a in ((1, 1.0), (2.1, 0.5), (4.3, 0.25), (9.1, 0.12), (19, 0.05)):
        ph = rng.uniform(0, 6.28, 4)
        Z += a * (np.sin(X / scale * k + ph[0]) * np.cos(Y / scale * k * 0.8 + ph[1]) +
                  np.sin((X + Y) / scale * k * 0.7 + ph[2]) * 0.5)
    Z *= amp
    if ridge is not None:
        Z += ridge(X, Y)
    bm = bmesh.new()
    vv = [[bm.verts.new((X[i, j], Y[i, j], Z[i, j])) for j in range(res)] for i in range(res)]
    for i in range(res - 1):
        for j in range(res - 1):
            bm.faces.new((vv[i][j], vv[i][j + 1], vv[i + 1][j + 1], vv[i + 1][j]))
    ob = obj_from_bm(name, bm, material, True, 0)
    ob.location = loc
    return ob


def snow(n=1500, box=(14, 14, 8), center=(0, 0, 0), size=0.012, strength=1.5, color=(0.75, 0.85, 0.9), seed=3):
    """Морський сніг: дрібні світні частинки (одна сітка)."""
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    for _ in range(n):
        c = Vector((rng.uniform(-box[0] / 2, box[0] / 2), rng.uniform(-box[1] / 2, box[1] / 2),
                    rng.uniform(-box[2] / 2, box[2] / 2)))
        s = size * rng.uniform(0.5, 1.6)
        r = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=s)
        bmesh.ops.translate(bm, verts=r["verts"], vec=c)
    m = mat("snow", color, 0.8, emit=color, emit_str=strength)
    ob = obj_from_bm("snow", bm, m, False)
    ob.location = center
    return ob


def bubbles(n, box, center, size=0.03, seed=5):
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    for _ in range(n):
        c = Vector((rng.uniform(-box[0] / 2, box[0] / 2), rng.uniform(-box[1] / 2, box[1] / 2),
                    rng.uniform(-box[2] / 2, box[2] / 2)))
        r = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=size * rng.uniform(0.4, 1.4))
        bmesh.ops.translate(bm, verts=r["verts"], vec=c)
    m = mat("bubble", (0.9, 0.97, 1.0), 0.05, emit=(0.6, 0.8, 0.9), emit_str=0.6)
    ob = obj_from_bm("bubbles", bm, m, True)
    ob.location = center
    return ob


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


def lerpv(a, b, t):
    return Vector(a).lerp(Vector(b), t)


def smooth(a, b, x):
    return ease((x - a) / (b - a)) if b != a else float(x >= a)


def render_range(out_dir, prefix, n_frames, update, start=0):
    sc = bpy.context.scene
    os.makedirs(out_dir, exist_ok=True)
    for f in range(start, n_frames):
        path = os.path.join(out_dir, f"{prefix}_{f:05d}.jpg")
        if os.path.exists(path):
            continue
        t = f / FPS
        update(t)
        sc.frame_set(f)  # оновити depsgraph
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
