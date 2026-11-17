"""
Ashfall Camp — real 3D version (Blender / Cycles), vertical 9:16.

Run with the bpy module (or `blender --background --python build.py -- ...`):
    python build.py preview 1.0 10.5 17 20.7      # stills -> out3d/preview/
    python build.py render                        # frames -> out3d/frames/
Environment: RES (default 720) = output width; SAMPLES (default 32).
"""
import math
import os
import random
import sys

import bpy  # noqa: I001  (bpy must be imported before bmesh/mathutils)
import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "out3d")
FPS = 24
DUR = 24.0
NF = int(FPS * DUR)
RES_W = int(os.environ.get("RES", "720"))
SAMPLES = int(os.environ.get("SAMPLES", "32"))

TENT = Vector((-0.45, 420.0, 0.0))
FIRE = Vector((1.25, 418.8, 0.0))
FOG_COL = (0.10, 0.022, 0.014)
FOG_D = 650.0

R = random.Random(7)


def fr(t):
    return 1 + int(round(t * FPS))


# ---------------------------------------------------------------- scene setup
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.03
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 1
    sc.cycles.transmission_bounces = 3
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.volume_bounces = 0
    sc.cycles.sample_clamp_indirect = 4.0
    sc.cycles.blur_glossy = 1.0
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.render.resolution_x = RES_W
    sc.render.resolution_y = RES_W * 16 // 9
    sc.render.resolution_percentage = 100
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, NF
    sc.render.use_persistent_data = True
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = 0.6
    sc.render.use_motion_blur = False
    return sc


def node_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    return m, nt, out


_FOG = None


def fog_group():
    """Distance haze: mixes the shader toward a dark-red emission with distance."""
    global _FOG
    if _FOG:
        return _FOG
    g = bpy.data.node_groups.new("Fog", "ShaderNodeTree")
    g.interface.new_socket("Shader", in_out="INPUT", socket_type="NodeSocketShader")
    g.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    gi = g.nodes.new("NodeGroupInput")
    go = g.nodes.new("NodeGroupOutput")
    cam = g.nodes.new("ShaderNodeCameraData")
    div = g.nodes.new("ShaderNodeMath"); div.operation = "DIVIDE"; div.inputs[1].default_value = -FOG_D
    ex = g.nodes.new("ShaderNodeMath"); ex.operation = "EXPONENT"
    inv = g.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    mul = g.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = 0.85
    em = g.nodes.new("ShaderNodeEmission"); em.inputs[0].default_value = (*FOG_COL, 1); em.inputs[1].default_value = 1.0
    mix = g.nodes.new("ShaderNodeMixShader")
    lp = g.nodes.new("ShaderNodeLightPath")
    camray = g.nodes.new("ShaderNodeMath"); camray.operation = "MULTIPLY"
    L = g.links
    L.new(cam.outputs["View Distance"], div.inputs[0])
    L.new(div.outputs[0], ex.inputs[0])
    L.new(ex.outputs[0], inv.inputs[1])
    L.new(inv.outputs[0], mul.inputs[0])
    L.new(mul.outputs[0], camray.inputs[0])
    L.new(lp.outputs["Is Camera Ray"], camray.inputs[1])
    L.new(camray.outputs[0], mix.inputs[0])
    L.new(gi.outputs[0], mix.inputs[1])
    L.new(em.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], go.inputs[0])
    _FOG = g
    return g


def finish(nt, out, shader_socket, fog=True):
    if fog:
        f = nt.nodes.new("ShaderNodeGroup")
        f.node_tree = fog_group()
        nt.links.new(shader_socket, f.inputs[0])
        nt.links.new(f.outputs[0], out.inputs["Surface"])
    else:
        nt.links.new(shader_socket, out.inputs["Surface"])


def mat_diffuse(name, col, rough=0.9, noise=0.0, noise_scale=2.0, col2=None, fog=True, emit=None):
    m, nt, out = node_mat(name)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Roughness"].default_value = rough
    if noise > 0:
        tx = nt.nodes.new("ShaderNodeTexNoise")
        tx.inputs["Scale"].default_value = noise_scale
        tx.inputs["Detail"].default_value = 6
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*col, 1)
        ramp.color_ramp.elements[1].color = (*(col2 or [c * (1 + noise) for c in col]), 1)
        nt.links.new(tx.outputs["Fac"], ramp.inputs[0])
        nt.links.new(ramp.outputs[0], b.inputs["Base Color"])
    else:
        b.inputs["Base Color"].default_value = (*col, 1)
    if emit:
        b.inputs["Emission Color"].default_value = (*emit[0], 1)
        b.inputs["Emission Strength"].default_value = emit[1]
    finish(nt, out, b.outputs[0], fog)
    return m


def mat_emit(name, col, strength, fog=True):
    m, nt, out = node_mat(name)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs[0].default_value = (*col, 1)
    e.inputs[1].default_value = strength
    finish(nt, out, e.outputs[0], fog)
    return m, e


def link_obj(ob, coll=None):
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


def mesh_from_bm(name, bm, mat=None, coll=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if mat:
        me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    return link_obj(ob, coll)


def bm_box(bm, c, s, rot_z=0.0, rot_x=0.0):
    r = bmesh.ops.create_cube(bm, size=1.0)
    vs = r["verts"]
    from mathutils import Matrix
    M = (Matrix.Translation(c) @ Matrix.Rotation(rot_z, 4, "Z") @ Matrix.Rotation(rot_x, 4, "X")
         @ Matrix.Diagonal((*s, 1.0)))
    bmesh.ops.transform(bm, matrix=M, verts=vs)


def coll(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


# ---------------------------------------------------------------- world / sky
def build_world():
    w = bpy.data.worlds.new("Sky")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = "EASE"
    cr.elements[0].position = 0.0
    cr.elements[0].color = (0.55, 0.12, 0.035, 1)
    cr.elements[1].position = 0.75
    cr.elements[1].color = (0.008, 0.0015, 0.002, 1)
    e = cr.elements.new(0.12); e.color = (0.30, 0.045, 0.02, 1)
    e = cr.elements.new(0.35); e.color = (0.09, 0.012, 0.008, 1)
    clamp = nt.nodes.new("ShaderNodeMath"); clamp.operation = "MAXIMUM"; clamp.inputs[1].default_value = 0.0
    nt.links.new(sep.outputs["Z"], clamp.inputs[0])
    nt.links.new(clamp.outputs[0], ramp.inputs[0])
    # clouds: noise on direction, strongest a little above the horizon
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.2
    noise.inputs["Detail"].default_value = 8
    noise.inputs["Roughness"].default_value = 0.6
    mp = nt.nodes.new("ShaderNodeMapping")
    nt.links.new(tc.outputs["Generated"], mp.inputs[0])
    nt.links.new(mp.outputs[0], noise.inputs["Vector"])
    # slow drift
    mp.inputs["Location"].default_value = (0, 0, 0)
    mp.inputs["Location"].keyframe_insert("default_value", frame=1)
    mp.inputs["Location"].default_value = (0.25, 0.08, 0)
    mp.inputs["Location"].keyframe_insert("default_value", frame=NF)
    cramp = nt.nodes.new("ShaderNodeValToRGB")
    cramp.color_ramp.elements[0].position = 0.45
    cramp.color_ramp.elements[1].position = 0.72
    nt.links.new(noise.outputs["Fac"], cramp.inputs[0])
    cloud_col = nt.nodes.new("ShaderNodeMix"); cloud_col.data_type = "RGBA"
    cloud_col.inputs["B"].default_value = (0.012, 0.003, 0.003, 1)
    nt.links.new(ramp.outputs[0], cloud_col.inputs["A"])
    nt.links.new(cramp.outputs[0], cloud_col.inputs["Factor"])
    # lightning: brighten whole sky (cool), keyed
    flash = nt.nodes.new("ShaderNodeMix"); flash.data_type = "RGBA"; flash.blend_type = "ADD"
    flash.inputs["B"].default_value = (0.30, 0.30, 0.48, 1)
    nt.links.new(cloud_col.outputs[2], flash.inputs["A"])
    mulc = nt.nodes.new("ShaderNodeMath"); mulc.operation = "MULTIPLY_ADD"
    nt.links.new(cramp.outputs[0], mulc.inputs[0])
    mulc.inputs[1].default_value = 0.9
    mulc.inputs[2].default_value = 0.12
    fl = nt.nodes.new("ShaderNodeValue"); fl.name = "FLASH"
    fl.outputs[0].default_value = 0.0
    m2 = nt.nodes.new("ShaderNodeMath"); m2.operation = "MULTIPLY"
    nt.links.new(mulc.outputs[0], m2.inputs[0])
    nt.links.new(fl.outputs[0], m2.inputs[1])
    nt.links.new(m2.outputs[0], flash.inputs["Factor"])
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs[1].default_value = 1.0
    nt.links.new(flash.outputs[2], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    return fl


STRIKES = [(4.4, 0.45, True), (18.7, 0.5, False), (20.6, 1.0, True), (22.55, 0.55, False)]


def flash_value(t):
    e = 0.0
    for t0, a, _ in STRIKES:
        for dt, aa in ((0.0, 1.0), (0.085, 0.55), (0.22, 0.9), (0.40, 0.35)):
            x = t - (t0 + dt)
            if x >= 0:
                e += a * aa * math.exp(-x / 0.075)
    return min(e, 1.3)


def key_flash(val_node, sun, bolts):
    for f in range(1, NF + 1):
        t = (f - 1) / FPS
        v = flash_value(t)
        val_node.outputs[0].default_value = v
        val_node.outputs[0].keyframe_insert("default_value", frame=f)
        sun.data.energy = 6.0 * v
        sun.data.keyframe_insert("energy", frame=f)
        for (t0, emit_node) in bolts:
            x = t - t0
            on = 0.0
            for dt, aa in ((0.0, 1.0), (0.085, 0.55), (0.22, 0.9)):
                if x - dt >= 0:
                    on += aa * math.exp(-(x - dt) / 0.06)
            emit_node.inputs[1].default_value = 60.0 * min(on, 1.2)
            emit_node.inputs[1].keyframe_insert("default_value", frame=f)
            ob = BOLT_OBJ[id(emit_node)]
            ob.hide_render = on < 0.02
            ob.keyframe_insert("hide_render", frame=f)


def build_bolt(name, start, end, seed):
    rr = random.Random(seed)

    def mid(p0, p1, disp, depth, out):
        if depth == 0:
            out.append(p0)
            return
        m = (p0 + p1) / 2 + Vector((rr.gauss(0, disp), rr.gauss(0, disp * 0.3), rr.gauss(0, disp * 0.2)))
        mid(p0, m, disp * 0.55, depth - 1, out)
        mid(m, p1, disp * 0.55, depth - 1, out)

    m, em = mat_emit(name + "_m", (0.8, 0.82, 1.0), 0.0, fog=False)
    cd = bpy.data.curves.new(name, "CURVE")
    cd.dimensions = "3D"
    cd.bevel_depth = 0.9
    main = []
    mid(start, end, (end - start).length * 0.08, 7, main)
    main.append(end)
    branches = [main]
    for _ in range(4):
        k = rr.randint(len(main) // 6, len(main) // 2)
        p0 = main[k]
        p1 = p0 + Vector((rr.uniform(-1, 1) * 120, rr.uniform(-30, 30), -rr.uniform(80, 180)))
        b = []
        mid(p0, p1, 25, 5, b)
        b.append(p1)
        branches.append(b)
    for pts in branches:
        sp = cd.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            sp.points[i].co = (*p, 1)
    ob = bpy.data.objects.new(name, cd)
    cd.materials.append(m)
    link_obj(ob)
    ob.visible_shadow = False
    BOLT_OBJ[id(em)] = ob
    return em


BOLT_OBJ = {}


# ---------------------------------------------------------------- city & ruins
def build_city(c):
    bm = bmesh.new()
    rr = random.Random(11)
    for ring, (y0, y1, hmax) in enumerate([(1150, 1350, 420), (1600, 2000, 330)]):
        x = -1700.0
        while x < 1700:
            w = rr.uniform(25, 90)
            d = rr.uniform(25, 70)
            h = rr.uniform(60, hmax) * (0.4 + 0.6 * rr.random() ** 0.6)
            y = rr.uniform(y0, y1)
            kind = rr.random()
            if kind < 0.5:
                bm_box(bm, Vector((x, y, h / 2)), (w, d, h))
                if rr.random() < 0.7:  # broken, tilted top chunk
                    hh = rr.uniform(10, 40)
                    bm_box(bm, Vector((x + rr.uniform(-5, 5), y, h + hh / 2 - 6)), (w * rr.uniform(0.4, 0.8), d * 0.8, hh),
                           rot_z=rr.uniform(-0.2, 0.2), rot_x=rr.uniform(-0.25, 0.25))
            else:  # skeleton: lower block + columns
                hb = h * rr.uniform(0.45, 0.7)
                bm_box(bm, Vector((x, y, hb / 2)), (w, d, hb))
                for k in range(int(w / 9) + 1):
                    ch = rr.uniform(0.3, 1.0) * (h - hb)
                    bm_box(bm, Vector((x - w / 2 + k * 9, y - d / 2, hb + ch / 2)), (1.6, 1.6, ch))
                for k in range(int((h - hb) / 10)):
                    bm_box(bm, Vector((x - w * 0.1, y - d / 2, hb + k * 10)), (w * rr.uniform(0.3, 0.9), 1.2, 1.2))
            x += w + rr.uniform(3, 25)
    m, nt, out = node_mat("city")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.03, 0.02, 0.02, 1)
    b.inputs["Roughness"].default_value = 1.0
    # sparse burning windows
    tc = nt.nodes.new("ShaderNodeTexCoord")
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.inputs["Scale"].default_value = 0.25
    brick.inputs["Mortar Size"].default_value = 0.35
    brick.inputs["Color1"].default_value = (1, 1, 1, 1)
    brick.inputs["Color2"].default_value = (0, 0, 0, 1)
    brick.inputs["Mortar"].default_value = (0, 0, 0, 1)
    nt.links.new(tc.outputs["Object"], brick.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.6
    nz.inputs["Detail"].default_value = 0
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    th = nt.nodes.new("ShaderNodeMath"); th.operation = "GREATER_THAN"; th.inputs[1].default_value = 0.74
    nt.links.new(nz.outputs["Fac"], th.inputs[0])
    mu = nt.nodes.new("ShaderNodeMath"); mu.operation = "MULTIPLY"
    nt.links.new(brick.outputs["Fac"], mu.inputs[0])
    nt.links.new(th.outputs[0], mu.inputs[1])
    mu2 = nt.nodes.new("ShaderNodeMath"); mu2.operation = "MULTIPLY"; mu2.inputs[1].default_value = 3.0
    nt.links.new(mu.outputs[0], mu2.inputs[0])
    b.inputs["Emission Color"].default_value = (1.0, 0.32, 0.06, 1)
    nt.links.new(mu2.outputs[0], b.inputs["Emission Strength"])
    finish(nt, out, b.outputs[0])
    ob = mesh_from_bm("City", bm, m, c)
    # fires at the foot of the city: big emissive blobs + lights
    fm, _ = mat_emit("cityfire", (1.0, 0.28, 0.05), 25.0)
    for i in range(14):
        p = Vector((rr.uniform(-1400, 1400), rr.uniform(1100, 1300), 0))
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=rr.uniform(8, 22), location=p)
        o = bpy.context.object
        o.scale.z = 0.5
        o.data.materials.append(fm)
        for col in o.users_collection:
            col.objects.unlink(o)
        c.objects.link(o)
    return ob


def build_ruins(c):
    rr = random.Random(21)
    bm = bmesh.new()
    rub = bmesh.new()
    y = 20.0
    while y < 315:
        x = rr.uniform(-160, -120)
        while x < 160:
            w = rr.uniform(8, 22)
            d = rr.uniform(6, 16)
            floors = rr.randint(2, 9)
            if abs(x) < 6 and rr.random() < 0.5:
                x += w
                continue
            rz = rr.uniform(-0.15, 0.15)
            for fl in range(floors):
                z = fl * 3.3
                keep = 1.0 - fl / floors * rr.uniform(0.3, 1.0)
                # slab (sometimes broken and tilted)
                if rr.random() < keep:
                    tilt = rr.uniform(-0.35, 0.35) if rr.random() < 0.25 else 0.0
                    bm_box(bm, Vector((x, y, z + 3.2)), (w * rr.uniform(0.5, 1.0), d, 0.3), rot_z=rz, rot_x=tilt)
                # columns
                for cx in (-0.5, -0.17, 0.17, 0.5):
                    for cy in (-0.5, 0.5):
                        if rr.random() < keep:
                            bm_box(bm, Vector((x + cx * w, y + cy * d, z + 1.65)), (0.5, 0.5, 3.3), rot_z=rz)
                # facade pieces with gaps (windows)
                for k in range(int(w / 2.6)):
                    if rr.random() < keep * 0.6:
                        bm_box(bm, Vector((x - w / 2 + (k + 0.5) * 2.6, y - d / 2, z + 0.6)), (2.0, 0.3, 1.2), rot_z=rz)
                        bm_box(bm, Vector((x - w / 2 + (k + 0.5) * 2.6, y - d / 2, z + 3.0)), (2.6, 0.3, 0.6), rot_z=rz)
            # rubble heap
            for _ in range(rr.randint(6, 18)):
                s = rr.uniform(0.6, 2.4)
                bm_box(rub, Vector((x + rr.gauss(0, w / 2), y + rr.gauss(0, d / 2), s * 0.3)), (s, s * rr.uniform(0.5, 1.2), s * 0.6),
                       rot_z=rr.uniform(0, 3), rot_x=rr.uniform(-0.6, 0.6))
            x += w + rr.uniform(4, 18)
        y += rr.uniform(14, 24)
    concrete = mat_diffuse("concrete", (0.11, 0.09, 0.08), noise=0.8, noise_scale=0.6, col2=(0.035, 0.03, 0.028))
    mesh_from_bm("Ruins", bm, concrete, c)
    mesh_from_bm("Rubble", rub, mat_diffuse("rubble", (0.07, 0.06, 0.055), noise=0.6, noise_scale=1.5), c)
    # burnt cars and small fires among the ruins
    fm, _ = mat_emit("ruinfire", (1.0, 0.35, 0.07), 18.0)
    for i in range(16):
        p = Vector((rr.uniform(-90, 90), rr.uniform(40, 300), 0.3))
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=rr.uniform(0.6, 1.4), location=p)
        o = bpy.context.object
        o.scale.z = 0.8
        o.data.materials.append(fm)
        bpy.ops.object.light_add(type="POINT", location=p + Vector((0, 0, 1.5)))
        L = bpy.context.object
        L.data.energy = rr.uniform(3000, 9000)
        L.data.color = (1.0, 0.4, 0.12)
        L.data.shadow_soft_size = 1.0


# ---------------------------------------------------------------- trees
def make_pine_proto(name, seed, mat_trunk, mat_leaf, dead=False):
    rr = random.Random(seed)
    bm = bmesh.new()
    if dead:
        def br(p, d, ln, r, depth):
            q = p + d * ln
            v = q - p
            c = (p + q) / 2
            from mathutils import Matrix
            res = bmesh.ops.create_cone(bm, cap_ends=True, segments=5, radius1=r, radius2=r * 0.6, depth=ln)
            rot = v.to_track_quat("Z", "Y").to_matrix().to_4x4()
            bmesh.ops.transform(bm, matrix=Matrix.Translation(c) @ rot, verts=res["verts"])
            if depth:
                for _ in range(2):
                    nd = (d + Vector((rr.uniform(-0.8, 0.8), rr.uniform(-0.8, 0.8), rr.uniform(-0.1, 0.4)))).normalized()
                    br(q, nd, ln * 0.62, r * 0.6, depth - 1)
        br(Vector((0, 0, 0)), Vector((0, 0, 1)), 4.5, 0.25, 4)
        me = mesh_from_bm(name, bm, mat_trunk)
        return me
    from mathutils import Matrix
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.25, radius2=0.08, depth=10)
    bmesh.ops.translate(bm, vec=(0, 0, 5), verts=res["verts"])
    leaf_bm = bmesh.new()
    tiers = rr.randint(6, 9)
    for i in range(tiers):
        u = i / tiers
        r = 2.4 * (1 - u) ** 0.9 + 0.25
        z = 1.8 + u * 8.0
        res = bmesh.ops.create_cone(leaf_bm, cap_ends=True, segments=rr.randint(7, 10), radius1=r, radius2=0.05, depth=r * 1.25)
        for v in res["verts"]:
            if v.co.z < 0:
                v.co.x *= rr.uniform(0.8, 1.2)
                v.co.y *= rr.uniform(0.8, 1.2)
                v.co.z += rr.uniform(-0.25, 0.1)
        bmesh.ops.rotate(leaf_bm, verts=res["verts"], cent=(0, 0, 0), matrix=Matrix.Rotation(rr.uniform(0, 6.28), 3, "Z"))
        bmesh.ops.translate(leaf_bm, vec=(0, 0, z + r * 0.6), verts=res["verts"])
    me1 = mesh_from_bm(name, bm, mat_trunk)
    me2 = mesh_from_bm(name + "_leaf", leaf_bm, mat_leaf)
    # join
    bpy.ops.object.select_all(action="DESELECT")
    me1.select_set(True)
    me2.select_set(True)
    bpy.context.view_layer.objects.active = me1
    bpy.ops.object.join()
    return me1


def build_forest(c):
    protos_c = bpy.data.collections.new("TreeProtos")
    bpy.context.scene.collection.children.link(protos_c)
    trunk = mat_diffuse("bark", (0.03, 0.02, 0.015))
    leaf = mat_diffuse("needles", (0.03, 0.045, 0.028), noise=0.8, noise_scale=3.0)
    deadm = mat_diffuse("deadwood", (0.05, 0.04, 0.035))
    protos = []
    for i in range(4):
        o = make_pine_proto(f"Pine{i}", 100 + i, trunk, leaf)
        protos.append(o)
    dead = [make_pine_proto(f"Dead{i}", 200 + i, deadm, deadm, dead=True) for i in range(2)]
    for o in protos + dead:
        for cc in o.users_collection:
            cc.objects.unlink(o)
        protos_c.objects.link(o)
    protos_c.hide_render = False
    bpy.context.view_layer.layer_collection.children["TreeProtos"].exclude = True
    pcs = []
    for i, o in enumerate(protos + dead):
        cc = bpy.data.collections.new(f"P{i}")
        cc.objects.link(o)
        pcs.append(cc)
    rr = random.Random(31)

    def inst(p, sc, rz, k):
        e = bpy.data.objects.new("tree", None)
        e.instance_type = "COLLECTION"
        e.instance_collection = pcs[k]
        e.location = p
        e.scale = (sc, sc, sc)
        e.rotation_euler.z = rz
        c.objects.link(e)

    def clear(x, y):
        # keep the camera corridor (descent) and the clearing open
        if 380 < y < 450 and abs(x) < 9.0 + max(0.0, (y - 420) * 0.3):
            return True
        return False

    # dead transition trees
    for _ in range(250):
        x, y = rr.uniform(-160, 160), rr.uniform(300, 335)
        inst(Vector((x, y, 0)), rr.uniform(1.0, 2.5), rr.uniform(0, 6.3), 4 + rr.randint(0, 1))
    n = 0
    y = 322.0
    while y < 760:
        span = 170 if y < 450 else 260
        x = -span + rr.uniform(0, 2)
        step = 2.4 if y < 450 else 3.6
        while x < span:
            px, py = x + rr.uniform(-1, 1), y + rr.uniform(-1, 1)
            if not clear(px, py):
                k = rr.randint(0, 3) if rr.random() > 0.04 else 4 + rr.randint(0, 1)
                inst(Vector((px, py, 0)), rr.uniform(1.1, 2.3), rr.uniform(0, 6.3), k)
                n += 1
            x += rr.uniform(step * 0.6, step * 1.4)
        y += step * rr.uniform(0.8, 1.2)
    print("trees:", n)


# ---------------------------------------------------------------- ground
def build_ground():
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 900, 0))
    g = bpy.context.object
    g.name = "Ground"
    g.scale = (5000, 3000, 1)
    m, nt, out = node_mat("ground")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Roughness"].default_value = 1.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 0.05; nz.inputs["Detail"].default_value = 10
    nz2 = nt.nodes.new("ShaderNodeTexNoise"); nz2.inputs["Scale"].default_value = 3.0; nz2.inputs["Detail"].default_value = 8
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(tc.outputs["Object"], nz2.inputs["Vector"])
    # world-space y via Geometry position
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sy = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sy.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 300
    mr.inputs["From Max"].default_value = 335
    nt.links.new(sy.outputs["Y"], mr.inputs["Value"])
    ash = nt.nodes.new("ShaderNodeValToRGB")
    ash.color_ramp.elements[0].color = (0.05, 0.04, 0.038, 1)
    ash.color_ramp.elements[1].color = (0.16, 0.15, 0.145, 1)
    ash.color_ramp.elements[0].position = 0.4
    ash.color_ramp.elements[1].position = 0.7
    nt.links.new(nz.outputs["Fac"], ash.inputs[0])
    forest = nt.nodes.new("ShaderNodeValToRGB")
    forest.color_ramp.elements[0].color = (0.018, 0.014, 0.008, 1)
    forest.color_ramp.elements[1].color = (0.06, 0.042, 0.025, 1)
    nt.links.new(nz2.outputs["Fac"], forest.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    nt.links.new(mr.outputs[0], mix.inputs["Factor"])
    nt.links.new(ash.outputs[0], mix.inputs["A"])
    nt.links.new(forest.outputs[0], mix.inputs["B"])
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.6
    nt.links.new(nz2.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs[0], b.inputs["Normal"])
    finish(nt, out, b.outputs[0])
    g.data.materials.append(m)
    # grass + fallen needles patch around the camp (hair particles)
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0.4, 421.0, 0.002))
    p = bpy.context.object
    p.name = "GrassPatch"
    p.scale = (14, 9, 1)
    bpy.ops.object.transform_apply(scale=True)
    p.data.materials.append(m)
    ps = p.modifiers.new("grass", "PARTICLE_SYSTEM").particle_system.settings
    ps.type = "HAIR"
    ps.count = 0
    ps.hair_length = 0.12
    ps.use_advanced_hair = True
    ps.use_rotations = True
    ps.rotation_mode = "NOR"
    ps.normal_factor = 0.25
    ps.factor_random = 0.08
    ps.length_random = 0.7
    ps.root_radius = 0.6
    ps.tip_radius = 0.0
    ps.radius_scale = 0.012
    ps.render_type = "PATH"
    ps.display_step = 3
    ps.render_step = 3
    gm = mat_diffuse("grass", (0.03, 0.028, 0.012), rough=0.8)
    p.data.materials.append(gm)
    ps.material = 2
    # exclude grass under tent / fire with a vertex-group-free trick: density texture
    tex = bpy.data.textures.new("grassmask", "BLEND")
    tex.progression = "SPHERICAL"
    return g


# ---------------------------------------------------------------- tent + person
def build_tent():
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0), plane_no=(0, 0, 1), clear_inner=True)
    for v in bm.verts:
        v.co.x *= 1.2
        v.co.y *= 1.0
        v.co.z = 1.35 * (max(v.co.z, 0)) ** 0.8
        # slight sag between poles
        ang = math.atan2(v.co.y, v.co.x)
        v.co.z *= 1 - 0.04 * (math.cos(4 * ang) * 0.5 + 0.5) * (1 - v.co.z / 1.35)
    m, nt, out = node_mat("tentfabric")
    dif = nt.nodes.new("ShaderNodeBsdfDiffuse"); dif.inputs[0].default_value = (0.55, 0.16, 0.03, 1)
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent"); tr.inputs[0].default_value = (1.0, 0.42, 0.10, 1)
    mix = nt.nodes.new("ShaderNodeMixShader"); mix.inputs[0].default_value = 0.8
    nt.links.new(dif.outputs[0], mix.inputs[1])
    nt.links.new(tr.outputs[0], mix.inputs[2])
    finish(nt, out, mix.outputs[0])
    tent = mesh_from_bm("Tent", bm, m)
    tent.location = TENT
    bpy.ops.object.select_all(action="DESELECT")
    tent.select_set(True)
    bpy.context.view_layer.objects.active = tent
    bpy.ops.object.shade_smooth()
    # door zipper arch (dark thin tube) on the camera side
    cd = bpy.data.curves.new("zip", "CURVE"); cd.dimensions = "3D"; cd.bevel_depth = 0.008
    sp = cd.splines.new("POLY")
    pts = []
    for i in range(25):
        a = math.pi * i / 24
        x = -0.5 * math.cos(a)
        z = 0.05 + 0.95 * math.sin(a)
        rr_ = 1 - (x / 1.2) ** 2 - (min(1, z / 1.35) ** (1 / 0.8)) ** 2
        y = -math.sqrt(max(rr_, 0.0)) - 0.012
        pts.append((x + TENT.x, y + TENT.y, z))
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1)
    zo = bpy.data.objects.new("Zip", cd)
    cd.materials.append(mat_diffuse("zip", (0.03, 0.02, 0.015)))
    link_obj(zo)
    # guy lines
    lm = mat_diffuse("rope", (0.25, 0.2, 0.15))
    for sx in (-1, 1):
        cd = bpy.data.curves.new("guy", "CURVE"); cd.dimensions = "3D"; cd.bevel_depth = 0.004
        sp = cd.splines.new("POLY"); sp.points.add(1)
        sp.points[0].co = (TENT.x + sx * 0.95, TENT.y - 0.2, 1.0, 1)
        sp.points[1].co = (TENT.x + sx * 1.9, TENT.y - 0.6, 0.0, 1)
        o = bpy.data.objects.new("Guy", cd); cd.materials.append(lm); link_obj(o)
    # flashlight inside, hanging at the back: casts the person's shadow onto the front wall
    bpy.ops.object.light_add(type="POINT", location=(TENT.x + 0.05, TENT.y + 0.6, 0.78))
    L = bpy.context.object
    L.name = "Flashlight"
    L.data.energy = 90
    L.data.color = (1.0, 0.82, 0.6)
    L.data.shadow_soft_size = 0.03
    return tent


def build_person():
    """Seated person in profile facing the fire (+X); returns the parts to animate."""
    mat = mat_diffuse("person", (0.05, 0.04, 0.035))
    root = bpy.data.objects.new("PersonRoot", None)
    root.location = (TENT.x - 0.22, TENT.y - 0.3, 0.0)
    link_obj(root)

    def part(kind, loc, scale, rot=(0, 0, 0), parent=root):
        if kind == "s":
            bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=1, location=loc)
        else:
            bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=1, depth=1, location=loc)
        o = bpy.context.object
        o.scale = scale
        o.rotation_euler = rot
        o.data.materials.append(mat)
        o.parent = parent
        return o

    part("s", (0, 0, 0.30), (0.17, 0.13, 0.28), (0, -0.22, 0))             # torso
    part("s", (-0.03, 0, 0.12), (0.16, 0.15, 0.1))                          # hips
    for sy in (-0.08, 0.08):
        part("c", (0.15, sy, 0.24), (0.06, 0.06, 0.36), (0, 1.0, 0))       # thighs (knees up)
        part("c", (0.33, sy, 0.14), (0.055, 0.055, 0.3), (0, -0.45, 0))    # shins
    neck = bpy.data.objects.new("Neck", None); neck.parent = root; neck.location = (0.06, 0, 0.58); link_obj(neck)
    part("s", (0.03, 0, 0.11), (0.1, 0.095, 0.11), parent=neck)              # head
    part("s", (0.11, 0, 0.1), (0.03, 0.02, 0.025), parent=neck)              # nose
    part("s", (0.01, 0, 0.18), (0.095, 0.09, 0.07), parent=neck)             # beanie
    part("s", (-0.01, 0, 0.255), (0.03, 0.03, 0.03), parent=neck)            # pompom
    sh = bpy.data.objects.new("Shoulder", None); sh.parent = root; sh.location = (0.06, -0.12, 0.5); link_obj(sh)
    part("c", (0, 0, -0.13), (0.045, 0.045, 0.26), parent=sh)                # upper arm
    el = bpy.data.objects.new("Elbow", None); el.parent = sh; el.location = (0, 0, -0.26); link_obj(el)
    part("c", (0, 0, 0.12), (0.04, 0.04, 0.24), parent=el)                   # forearm
    hand = bpy.data.objects.new("Hand", None); hand.parent = el; hand.location = (0, 0, 0.25); link_obj(hand)
    part("c", (0.03, 0, 0.0), (0.04, 0.04, 0.09), parent=hand)               # mug
    part("s", (0.0, 0, 0.0), (0.035, 0.03, 0.03), parent=hand)               # fist
    # second arm resting
    sh2 = bpy.data.objects.new("Shoulder2", None); sh2.parent = root; sh2.location = (0.06, 0.12, 0.5); link_obj(sh2)
    part("c", (0, 0, -0.13), (0.045, 0.045, 0.26), parent=sh2)
    sh2.rotation_euler = (0, -0.9, 0)
    return root, neck, sh, el, hand


def animate_person(root, neck, sh, el, hand):
    # rest: arm forward-down, forearm up, mug in front of chest; sip: mug to mouth
    rest = dict(sh=(0, -0.55, 0), el=(0, -2.2, 0), hand=(0, 0.9, 0), neck=(0, 0.05, 0))
    sip = dict(sh=(0, -1.25, 0), el=(0, -2.35, 0), hand=(0, 1.9, 0), neck=(0, -0.2, 0))

    def key(pose, t):
        f = fr(t)
        for o, k in ((sh, "sh"), (el, "el"), (hand, "hand"), (neck, "neck")):
            o.rotation_euler = pose[k]
            o.keyframe_insert("rotation_euler", frame=f)

    key(rest, 0.0)
    key(rest, 20.15)
    key(sip, 20.9)
    key(sip, 21.95)
    key(rest, 22.8)
    key(rest, 24.0)
    # breathing
    for f in range(1, NF + 1, 12):
        t = (f - 1) / FPS
        root.location.z = 0.006 * math.sin(t * 1.5)
        root.keyframe_insert("location", index=2, frame=f)


# ---------------------------------------------------------------- campfire
def build_fire():
    rr = random.Random(41)
    wood = mat_diffuse("logs", (0.04, 0.022, 0.012), emit=((1.0, 0.25, 0.03), 0.6))
    for ang in (0.3, 1.9, 3.5, 5.0):
        bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.05, depth=0.7,
                                            location=FIRE + Vector((0, 0, 0.12)), rotation=(1.15, 0, ang))
        bpy.context.object.data.materials.append(wood)
    stone = mat_diffuse("stone", (0.09, 0.085, 0.08), noise=0.5, noise_scale=8)
    for i in range(11):
        a = 2 * math.pi * i / 11
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=rr.uniform(0.08, 0.12),
                                              location=FIRE + Vector((0.42 * math.cos(a), 0.42 * math.sin(a), 0.04)))
        o = bpy.context.object
        o.scale = (1.2, 1.0, 0.7)
        o.data.materials.append(stone)
    # embers bed
    em, _ = mat_emit("embers", (1.0, 0.3, 0.04), 8.0)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.28, location=FIRE + Vector((0, 0, 0.0)))
    o = bpy.context.object
    o.scale.z = 0.12
    o.data.materials.append(em)
    # flames: displaced cones with an animated noise texture
    m, nt, out = node_mat("flame")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (1.0, 0.75, 0.25, 1)
    ramp.color_ramp.elements[1].color = (1.0, 0.12, 0.01, 1)
    nt.links.new(sep.outputs["Z"], ramp.inputs[0])
    e = nt.nodes.new("ShaderNodeEmission"); e.inputs[1].default_value = 5.0
    nt.links.new(ramp.outputs[0], e.inputs[0])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    a = nt.nodes.new("ShaderNodeMapRange")
    a.inputs["From Min"].default_value = 0.35
    a.inputs["From Max"].default_value = 1.0
    nt.links.new(sep.outputs["Z"], a.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(a.outputs[0], mix.inputs[0])
    nt.links.new(e.outputs[0], mix.inputs[1])
    nt.links.new(tr.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    m.surface_render_method = "BLENDED" if hasattr(m, "surface_render_method") else None
    tex = bpy.data.textures.new("flamenoise", "CLOUDS")
    tex.noise_scale = 0.12
    drv = bpy.data.objects.new("FlameTexDriver", None)
    link_obj(drv)
    drv.location = (0, 0, 0)
    drv.keyframe_insert("location", frame=1)
    drv.location = (0.3, 0.2, -18.0)
    drv.keyframe_insert("location", frame=NF)
    for fc in drv.animation_data.action.fcurves if hasattr(drv.animation_data.action, "fcurves") else []:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    for i, (dx, dy, r, h) in enumerate([(0, 0, 0.17, 0.75), (0.1, 0.05, 0.11, 0.55), (-0.1, -0.03, 0.12, 0.6),
                                        (0.04, -0.09, 0.09, 0.45), (-0.05, 0.08, 0.1, 0.5)]):
        bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=r, radius2=0.0, depth=h,
                                        location=FIRE + Vector((dx, dy, 0.1 + h / 2)))
        o = bpy.context.object
        o.name = f"Flame{i}"
        sub = o.modifiers.new("sub", "SUBSURF"); sub.levels = 2; sub.render_levels = 3
        d = o.modifiers.new("disp", "DISPLACE")
        d.texture = tex
        d.texture_coords = "OBJECT"
        d.texture_coords_object = drv
        d.strength = 0.14
        d.mid_level = 0.5
        o.data.materials.append(m)
        o.visible_shadow = False
    # fire light with flicker
    bpy.ops.object.light_add(type="POINT", location=FIRE + Vector((0, 0, 0.45)))
    L = bpy.context.object
    L.name = "FireLight"
    L.data.color = (1.0, 0.45, 0.13)
    L.data.shadow_soft_size = 0.2
    for f in range(1, NF + 1, 2):
        t = (f - 1) / FPS
        fl = (0.86 + 0.07 * math.sin(13.1 * t) + 0.05 * math.sin(29.3 * t + 1.3)
              + 0.04 * math.sin(7.7 * t + 0.4) + 0.03 * math.sin(41.0 * t + 2.2))
        L.data.energy = 420 * fl
        L.data.keyframe_insert("energy", frame=f)
    # embers rising
    bpy.ops.mesh.primitive_circle_add(radius=0.2, fill_type="NGON", location=FIRE + Vector((0, 0, 0.3)))
    emitter = bpy.context.object
    emitter.name = "EmberEmitter"
    emitter.hide_render = True
    psys = emitter.modifiers.new("embers", "PARTICLE_SYSTEM").particle_system
    s = psys.settings
    s.count = 900
    s.frame_start = 1
    s.frame_end = NF
    s.lifetime = 50
    s.lifetime_random = 0.5
    s.normal_factor = 1.0
    s.factor_random = 0.6
    s.brownian_factor = 0.6
    s.effector_weights.gravity = -0.06
    s.render_type = "OBJECT"
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.006, location=(0, 0, -50))
    spark = bpy.context.object
    spark.name = "Spark"
    sm, _ = mat_emit("spark", (1.0, 0.45, 0.1), 30.0)
    spark.data.materials.append(sm)
    s.instance_object = spark
    s.particle_size = 1.0
    s.size_random = 0.6
    return L


# ---------------------------------------------------------------- ash
def build_ash(cam):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    box = bpy.context.object
    box.name = "AshVolume"
    box.scale = (60, 70, 40)
    box.parent = cam
    box.matrix_parent_inverse = cam.matrix_world.inverted()
    box.location = cam.location + Vector((0, 30, 0))
    box.hide_render = True
    box.display_type = "WIRE"
    psys = box.modifiers.new("ash", "PARTICLE_SYSTEM").particle_system
    s = psys.settings
    s.count = int(os.environ.get("ASH", "35000"))
    s.frame_start = -60
    s.frame_end = NF
    s.lifetime = 110
    s.emit_from = "VOLUME"
    s.distribution = "RAND"
    s.normal_factor = 0.0
    s.object_align_factor = (0, 0, -0.4)
    s.factor_random = 0.15
    s.brownian_factor = 0.35
    s.effector_weights.gravity = 0.0
    s.render_type = "OBJECT"
    s.use_rotations = True
    s.rotation_mode = "NONE"
    s.phase_factor_random = 2.0
    s.angular_velocity_mode = "RAND"
    s.angular_velocity_factor = 2.0
    bpy.ops.mesh.primitive_plane_add(size=0.025, location=(0, 0, -60))
    flake = bpy.context.object
    flake.name = "AshFlake"
    am = mat_diffuse("ash", (0.55, 0.52, 0.5), emit=((0.5, 0.25, 0.18), 0.4))
    flake.data.materials.append(am)
    s.instance_object = flake
    s.particle_size = 1.0
    s.size_random = 0.7
    return box


# ---------------------------------------------------------------- camera
KT = [0.0, 8.0, 12.5, 15.5, 24.0]
CAM = dict(y=[0.0, 250.0, 385.0, 409.0, 414.0], z=[40.0, 34.0, 30.0, 0.70, 0.62],
           x=[-8.0, 3.0, -1.0, 0.25, 0.35], pitch=[-2.0, -6.6, -5.5, 7.4, 7.4])


def pchip(ts, vs, t):
    import numpy as np
    from scipy.interpolate import PchipInterpolator
    return float(PchipInterpolator(ts, vs)(t))


def build_camera():
    cd = bpy.data.cameras.new("Cam")
    cd.sensor_fit = "VERTICAL"
    cd.angle_y = math.radians(60)
    cd.clip_start = 0.05
    cd.clip_end = 6000
    cam = bpy.data.objects.new("Cam", cd)
    link_obj(cam)
    bpy.context.scene.camera = cam
    try:
        import numpy as np  # noqa
        from scipy.interpolate import PchipInterpolator
        fs = {k: PchipInterpolator(KT, v) for k, v in CAM.items()}
        ev = lambda k, t: float(fs[k](t))
    except Exception:
        ev = None
    for f in range(1, NF + 1):
        t = (f - 1) / FPS
        g = min(max((t - 13.0) / 3.0, 0), 1)
        x = ev("x", t) + 0.02 * math.sin(0.7 * t) * g
        z = ev("z", t) + 0.006 * math.sin(1.1 * t + 1) * g
        cam.location = (x, ev("y", t), z)
        cam.rotation_euler = (math.radians(90 + ev("pitch", t)) + 0.0015 * math.sin(0.45 * t), 0.002 * math.sin(0.3 * t) * g, 0)
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    return cam


# ---------------------------------------------------------------- smoke plumes (camera-facing cards)
def build_plumes(cam):
    m, nt, out = node_mat("smoke")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    nt.links.new(tc.outputs["Generated"], mp.inputs[0])
    mp.inputs["Location"].default_value = (0, 0, 0)
    mp.inputs["Location"].keyframe_insert("default_value", frame=1)
    mp.inputs["Location"].default_value = (0.0, -1.6, 0)
    mp.inputs["Location"].keyframe_insert("default_value", frame=NF)
    mp.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 3.5; nz.inputs["Detail"].default_value = 8
    nt.links.new(mp.outputs[0], nz.inputs["Vector"])
    grad = nt.nodes.new("ShaderNodeTexGradient"); grad.gradient_type = "QUADRATIC_SPHERE"
    mp2 = nt.nodes.new("ShaderNodeMapping")
    mp2.inputs["Location"].default_value = (-0.5, -0.5, 0)
    nt.links.new(tc.outputs["Generated"], mp2.inputs[0])
    mp2.inputs["Scale"].default_value = (2.0, 1.15, 1)
    nt.links.new(mp2.outputs[0], grad.inputs[0])
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
    nt.links.new(nz.outputs["Fac"], mul.inputs[0])
    nt.links.new(grad.outputs["Fac"], mul.inputs[1])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.12
    ramp.color_ramp.elements[1].position = 0.45
    nt.links.new(mul.outputs[0], ramp.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs[0].default_value = (0.05, 0.02, 0.018, 1); em.inputs[1].default_value = 1
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(ramp.outputs[0], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    rr = random.Random(51)
    for (x, y, base, w) in [(-950, 1250, 100, 260), (-420, 1250, 160, 330), (-60, 1250, 80, 220), (380, 1250, 140, 300),
                            (820, 1250, 200, 320), (60, 190, 0, 50), (-70, 240, 0, 60), (35, 120, 0, 36)]:
        bpy.ops.mesh.primitive_plane_add(size=1, location=(x, y, base + w * 1.6))
        o = bpy.context.object
        o.scale = (w, 1, w * 3.2)
        o.rotation_euler = (math.pi / 2, 0, 0)
        bpy.ops.object.transform_apply(rotation=True, scale=True)
        o.data.materials.append(m)
        o.visible_shadow = False
        c = o.constraints.new("TRACK_TO")
        c.target = cam
        c.track_axis = "TRACK_NEGATIVE_Y"
        c.up_axis = "UP_Z"
        c.use_target_z = False
        # only rotate about Z: lock with a limit
        lim = o.constraints.new("LIMIT_ROTATION")
        lim.use_limit_x = True
        lim.use_limit_y = True


# ---------------------------------------------------------------- lights
def build_lights():
    # red horizon key from behind the city, low
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(84), 0, math.radians(180)))
    s = bpy.context.object
    s.data.energy = 1.6
    s.data.color = (1.0, 0.32, 0.15)
    s.data.angle = math.radians(8)
    # lightning sun (keyed)
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(35), math.radians(10), math.radians(200)))
    f = bpy.context.object
    f.data.color = (0.75, 0.8, 1.0)
    f.data.energy = 0.0
    f.data.angle = math.radians(25)
    return f


def build():
    sc = reset()
    flash_node = build_world()
    cam = build_camera()
    build_ground()
    c_city = coll("City")
    build_city(c_city)
    c_r = coll("Ruins")
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children["Ruins"]
    build_ruins(c_r)
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection
    c_f = coll("Forest")
    build_forest(c_f)
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection
    build_tent()
    p = build_person()
    animate_person(*p)
    build_fire()
    build_ash(cam)
    build_plumes(cam)
    fsun = build_lights()
    b1 = build_bolt("Bolt1", Vector((-520, 1500, 900)), Vector((-470, 1450, 60)), 5)
    b2 = build_bolt("Bolt2", Vector((150, 1000, 700)), Vector((120, 980, 30)), 7)
    key_flash(flash_node, fsun, [(4.4, b1), (20.6, b2)])
    return sc


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    mode = args[0] if args else "preview"
    sc = build()
    os.makedirs(OUT, exist_ok=True)
    if mode == "save":
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "ashfall_camp.blend"))
        return
    if mode == "preview":
        d = os.path.join(OUT, "preview")
        os.makedirs(d, exist_ok=True)
        times = [float(a) for a in args[1:]] or [1.0, 6.0, 11.0, 14.0, 17.0, 20.7, 21.4]
        # particles need the frames before: step through
        last = 1
        for t in sorted(times):
            f = fr(t)
            for k in range(last, f + 1, 4):
                sc.frame_set(k)
            sc.frame_set(f)
            last = f
            sc.render.filepath = os.path.join(d, f"f{f:04d}.png")
            bpy.ops.render.render(write_still=True)
            print("PREVIEW", t, sc.render.filepath, flush=True)
        return
    if mode == "render":
        start = int(args[1]) if len(args) > 1 else 1
        sc.frame_start = start
        sc.render.filepath = os.path.join(OUT, "frames", "f")
        bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
