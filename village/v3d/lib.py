"""3D-бібліотека для «Села, якого немає на жодній карті» (Blender / EEVEE)."""
import math
import random

import bpy
from mathutils import Euler, Vector

FPS = 15


def setp(obj, name, value):
    try:
        setattr(obj, name, value)
    except (AttributeError, TypeError, ValueError):
        pass


# --------------------------------------------------------------------------
# Сцена
# --------------------------------------------------------------------------
def new_scene(res=(960, 540), samples=12):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.fps = FPS
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "AgX"
    setp(sc.view_settings, "look", "AgX - Medium High Contrast")
    sc.view_settings.exposure = 1.6
    ee = sc.eevee
    setp(ee, "taa_render_samples", samples)
    setp(ee, "volumetric_tile_size", "4")
    setp(ee, "volumetric_samples", 64)
    setp(ee, "volumetric_start", 0.5)
    setp(ee, "volumetric_end", 160)
    setp(ee, "use_volumetric_shadows", False)
    setp(ee, "volumetric_ray_depth", 1)
    setp(ee, "use_gtao", True)
    setp(ee, "use_bloom", True)
    setp(ee, "shadow_ray_count", 1)
    setp(ee, "shadow_step_count", 4)
    setp(ee, "use_shadow_jitter_viewport", False)
    return sc


def world(sky=(0.006, 0.01, 0.022), strength=1.0, fog=0.02, fog_col=(0.65, 0.75, 0.95), aniso=0.3):
    sc = bpy.context.scene
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    bg.inputs["Color"].default_value = (*sky, 1)
    bg.inputs["Strength"].default_value = strength
    if fog > 0:
        vol = nt.nodes.new("ShaderNodeVolumePrincipled")
        vol.inputs["Density"].default_value = fog
        vol.inputs["Color"].default_value = (*fog_col, 1)
        vol.inputs["Anisotropy"].default_value = aniso
        nt.links.new(vol.outputs["Volume"], nt.nodes["World Output"].inputs["Volume"])
    return w


def fog_box(center, size, density, color=(0.7, 0.8, 1.0), noise_scale=0.08):
    """Локальний неоднорідний туман (клуби) у кубі."""
    bpy.ops.mesh.primitive_cube_add(location=center)
    o = bpy.context.object
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    m = bpy.data.materials.new("fogbox")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (*color, 1)
    vol.inputs["Anisotropy"].default_value = 0.35
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = noise_scale * 10
    tex.inputs["Detail"].default_value = 3
    coord = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(coord.outputs["Object"], tex.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = 0.4
    ramp.inputs["From Max"].default_value = 0.75
    ramp.inputs["To Min"].default_value = 0.0
    ramp.inputs["To Max"].default_value = density
    nt.links.new(tex.outputs["Fac"], ramp.inputs["Value"])
    nt.links.new(ramp.outputs["Result"], vol.inputs["Density"])
    nt.links.new(vol.outputs["Volume"], nt.nodes["Material Output"].inputs["Volume"])
    o.data.materials.append(m)
    setp(o, "visible_shadow", False)
    return o


# --------------------------------------------------------------------------
# Матеріали
# --------------------------------------------------------------------------
_MATS = {}


def mat(name, color, rough=0.85, noise=None, bump=0.3, emit=None, strength=0.0, metal=0.0,
        sss=0.0, noise_dark=0.55, stripes=None, alpha=1.0):
    key = (name, tuple(color), rough, noise, emit, strength)
    if key in _MATS:
        return _MATS[key]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if sss:
        setp(b.inputs["Subsurface Weight"], "default_value", sss)
        b.inputs["Subsurface Radius"].default_value = (1.0, 0.4, 0.25)
    if noise:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = noise
        tex.inputs["Detail"].default_value = 8
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*[c * noise_dark for c in color], 1)
        ramp.color_ramp.elements[1].color = (*color, 1)
        nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
        if bump:
            bp = nt.nodes.new("ShaderNodeBump")
            bp.inputs["Strength"].default_value = bump
            nt.links.new(tex.outputs["Fac"], bp.inputs["Height"])
            nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    if stripes:  # вишивка: червоні смуги
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.inputs["Scale"].default_value = stripes
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.82
        ramp.color_ramp.elements[0].color = (*color, 1)
        ramp.color_ramp.elements[1].position = 0.86
        ramp.color_ramp.elements[1].color = (0.45, 0.05, 0.04, 1)
        nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    _MATS[key] = m
    return m


def M():
    """Набір матеріалів сцени."""
    return dict(
        wall=mat("wall", (0.75, 0.71, 0.63), 0.95, noise=5, bump=0.15),
        thatch=mat("thatch", (0.30, 0.22, 0.12), 1.0, noise=60, bump=0.8, noise_dark=0.35),
        wood=mat("wood", (0.16, 0.10, 0.06), 0.8, noise=25, bump=0.3),
        wood_light=mat("woodl", (0.38, 0.27, 0.16), 0.75, noise=30, bump=0.2),
        ground=mat("ground", (0.11, 0.09, 0.07), 1.0, noise=1.5, bump=0.5, noise_dark=0.5),
        road=mat("road", (0.17, 0.15, 0.13), 1.0, noise=2.5, bump=0.4),
        grass=mat("grass", (0.05, 0.08, 0.04), 1.0, noise=8, bump=0.6),
        pine=mat("pine", (0.025, 0.045, 0.03), 1.0, noise=30, bump=0.5),
        bark=mat("bark", (0.07, 0.05, 0.04), 1.0, noise=12, bump=0.8),
        win=mat("win", (1.0, 0.6, 0.25), 0.5, emit=(1.0, 0.52, 0.2), strength=14),
        win_off=mat("winoff", (0.02, 0.025, 0.03), 0.2),
        flame=mat("flame", (1, 0.6, 0.2), 0.5, emit=(1.0, 0.5, 0.15), strength=50),
        candle_wax=mat("wax", (0.85, 0.78, 0.6), 0.6, sss=0.5),
        shutter=mat("shutter", (0.10, 0.20, 0.42), 0.7, noise=20, bump=0.1),
        skin=mat("skin", (0.62, 0.44, 0.34), 0.55, sss=0.25),
        skin_old=mat("skin_old", (0.6, 0.45, 0.38), 0.65, noise=80, bump=0.25, sss=0.2, noise_dark=0.8),
        jacket=mat("jacket", (0.09, 0.12, 0.05), 0.9, noise=40, bump=0.15),
        hoodie=mat("hoodie", (0.22, 0.22, 0.22), 0.95, noise=60, bump=0.1),
        jeans=mat("jeans", (0.05, 0.06, 0.09), 0.9, noise=50, bump=0.1),
        hair=mat("hair", (0.04, 0.025, 0.015), 0.6, noise=90, bump=0.3),
        boots=mat("boots", (0.03, 0.025, 0.02), 0.5),
        dress=mat("dress", (0.05, 0.035, 0.03), 0.95, noise=40, bump=0.1),
        shawl=mat("shawl", (0.32, 0.32, 0.33), 1.0, noise=120, bump=0.5),
        scarf=mat("scarf", (0.82, 0.8, 0.74), 0.9, stripes=6),
        linen=mat("linen", (0.62, 0.58, 0.5), 0.95, noise=60, bump=0.1),
        villager=mat("vill", (0.18, 0.15, 0.12), 0.95, noise=40, bump=0.1),
        villager2=mat("vill2", (0.32, 0.27, 0.2), 0.95, noise=40, bump=0.1),
        metal=mat("metal", (0.05, 0.05, 0.05), 0.4, metal=1.0),
        car=mat("car", (0.03, 0.04, 0.05), 0.25, metal=0.6),
        car_old=mat("car_old", (0.35, 0.33, 0.25), 0.35, metal=0.4),
        glass=mat("glass", (0.02, 0.03, 0.04), 0.05, metal=0.2),
        earth=mat("earth", (0.08, 0.05, 0.035), 1.0, noise=12, bump=1.0),
        cloth_red=mat("red", (0.45, 0.04, 0.03), 0.9),
        cloth_white=mat("white", (0.85, 0.83, 0.78), 0.9),
        paper=mat("paper", (0.75, 0.7, 0.6), 0.9, noise=20, bump=0.05),
        clay=mat("clay", (0.35, 0.18, 0.1), 0.7, noise=20, bump=0.1),
        borscht=mat("borscht", (0.45, 0.06, 0.05), 0.3),
        bread=mat("bread", (0.5, 0.28, 0.1), 0.7, noise=30, bump=0.6),
        plaster_in=mat("plaster", (0.6, 0.56, 0.48), 0.95, noise=4, bump=0.2),
        floor=mat("floor", (0.12, 0.08, 0.05), 0.8, noise=6, bump=0.2),
        photo=mat("photo", (0.4, 0.4, 0.38), 0.3, noise=8, bump=0.0, noise_dark=0.2),
        dash_glow=mat("dash", (0.3, 0.5, 1.0), 0.4, emit=(0.35, 0.55, 1.0), strength=6),
        phone_glow=mat("phone", (0.5, 0.6, 0.8), 0.3, emit=(0.55, 0.65, 0.85), strength=5),
        red_light=mat("redl", (1, 0.1, 0.05), 0.4, emit=(1, 0.08, 0.03), strength=30),
        head_light=mat("headl", (1, 0.95, 0.85), 0.3, emit=(1, 0.95, 0.85), strength=40),
    )


# --------------------------------------------------------------------------
# Примітиви
# --------------------------------------------------------------------------
def link(o):
    if o.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(o)
    return o


def box(loc, size, m, rot=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    o.data.materials.append(m)
    if bevel:
        bpy.ops.object.transform_apply(scale=True)
        mod = o.modifiers.new("b", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    return o


def cyl(loc, r, depth, m, rot=(0, 0, 0), verts=16):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.object
    o.data.materials.append(m)
    bpy.ops.object.shade_smooth()
    return o


def sphere(loc, r, m, scale=(1, 1, 1), segs=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=segs // 2, radius=r, location=loc)
    o = bpy.context.object
    o.scale = scale
    o.data.materials.append(m)
    bpy.ops.object.shade_smooth()
    return o


def cone(loc, r1, r2, depth, m, rot=(0, 0, 0), verts=12):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=depth, location=loc, rotation=rot)
    o = bpy.context.object
    o.data.materials.append(m)
    bpy.ops.object.shade_smooth()
    return o


def point_light(loc, energy, color=(1, 0.55, 0.22), radius=0.15, shadow=True, name="pl"):
    lt = bpy.data.lights.new(name, "POINT")
    lt.energy = energy
    lt.color = color
    lt.shadow_soft_size = radius
    setp(lt, "use_shadow", shadow)
    o = bpy.data.objects.new(name, lt)
    o.location = loc
    return link(o)


def spot_light(loc, rot, energy, color=(0.92, 0.95, 1.0), size_deg=28, blend=0.4, radius=0.05, name="spot"):
    lt = bpy.data.lights.new(name, "SPOT")
    lt.energy = energy
    lt.color = color
    lt.spot_size = math.radians(size_deg)
    lt.spot_blend = blend
    lt.shadow_soft_size = radius
    o = bpy.data.objects.new(name, lt)
    o.location = loc
    o.rotation_euler = rot
    return link(o)


def sun(rot, energy, color=(0.6, 0.72, 1.0), angle=0.02):
    lt = bpy.data.lights.new("sun", "SUN")
    lt.energy = energy
    lt.color = color
    lt.angle = angle
    o = bpy.data.objects.new("sun", lt)
    o.rotation_euler = rot
    return link(o)


def moon_disc(direction, dist=400, r=9, k=6):
    m = mat("moon", (0.9, 0.93, 1.0), 1.0, emit=(0.85, 0.9, 1.0), strength=k)
    d = Vector(direction).normalized()
    o = sphere(tuple(d * dist), r, m, segs=24)
    setp(o, "visible_shadow", False)
    return o


def look_at(obj, target, roll=0.0):
    d = Vector(target) - obj.location
    q = d.to_track_quat("-Z", "Y")
    obj.rotation_euler = q.to_euler()
    if roll:
        obj.rotation_euler.rotate_axis("Z", math.radians(roll))


# --------------------------------------------------------------------------
# Ландшафт
# --------------------------------------------------------------------------
def terrain(size=400, height=6.0, scale=0.6, m=None, loc=(0, 0, 0), subdiv=7, seed=1):
    bpy.ops.mesh.primitive_plane_add(size=size, location=loc)
    o = bpy.context.object
    mod = o.modifiers.new("sub", "SUBSURF")
    mod.subdivision_type = "SIMPLE"
    mod.levels = mod.render_levels = subdiv
    tex = bpy.data.textures.new("terr%d" % seed, "CLOUDS")
    tex.noise_scale = scale * size / 10
    tex.noise_depth = 3
    d = o.modifiers.new("disp", "DISPLACE")
    d.texture = tex
    d.strength = height
    d.mid_level = 0.5
    if m:
        o.data.materials.append(m)
    bpy.ops.object.shade_smooth()
    return o


_PINE = {}


def pine_mesh(mats, variant=0):
    if variant in _PINE:
        return _PINE[variant]
    random.seed(100 + variant)
    parts = []
    tiers = 7
    for i in range(tiers):
        t = i / tiers
        r = 0.42 * (1 - t) + 0.06
        parts.append(cone((0, 0, 0.18 + t * 0.78), r, 0.0, 0.32, mats["pine"], verts=9,
                          rot=(random.uniform(-0.05, 0.05), random.uniform(-0.05, 0.05), random.uniform(0, 6))))
    parts.append(cyl((0, 0, 0.25), 0.035, 0.5, mats["bark"], verts=8))
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    o = bpy.context.object
    o.name = "pine_src%d" % variant
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    me = o.data
    bpy.data.objects.remove(o)
    _PINE[variant] = me
    return me


def forest(mats, area, n, hmin=10, hmax=22, avoid=None, seed=0, ground_fn=None):
    """area = (xmin, xmax, ymin, ymax); avoid(x, y) -> True щоб пропустити."""
    r = random.Random(seed)
    meshes = [pine_mesh(mats, v) for v in range(3)]
    placed = 0
    tries = 0
    while placed < n and tries < n * 20:
        tries += 1
        x, y = r.uniform(area[0], area[1]), r.uniform(area[2], area[3])
        if avoid and avoid(x, y):
            continue
        h = r.uniform(hmin, hmax)
        o = bpy.data.objects.new("pine", meshes[r.randrange(3)])
        z = ground_fn(x, y) if ground_fn else 0
        o.location = (x, y, z - 0.3)
        w = h * r.uniform(0.34, 0.44)
        o.scale = (w, w, h)
        o.rotation_euler = (r.uniform(-0.03, 0.03), r.uniform(-0.03, 0.03), r.uniform(0, 6.28))
        link(o)
        placed += 1


def trunk_row(mats, xs, y, h=26, seed=0):
    r = random.Random(seed)
    for x in xs:
        o = cyl((x, y + r.uniform(-1, 1), h / 2), r.uniform(0.25, 0.45), h, mats["bark"], verts=12)
        o.rotation_euler = (r.uniform(-0.03, 0.03), r.uniform(-0.03, 0.03), 0)


def road_strip(points, width, m, z=0.02):
    """Дорога як стрічка вздовж ламаної [(x,y),...]."""
    import bmesh
    me = bpy.data.meshes.new("road")
    bm = bmesh.new()
    left, right = [], []
    for i, (x, y) in enumerate(points):
        a = Vector(points[min(i + 1, len(points) - 1)]) - Vector(points[max(i - 1, 0)])
        a = Vector((a.x, a.y)).normalized()
        n = Vector((-a.y, a.x))
        w = width(i / (len(points) - 1)) if callable(width) else width
        left.append(bm.verts.new((x + n.x * w / 2, y + n.y * w / 2, z)))
        right.append(bm.verts.new((x - n.x * w / 2, y - n.y * w / 2, z)))
    for i in range(len(points) - 1):
        bm.faces.new((left[i], right[i], right[i + 1], left[i + 1]))
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("road", me)
    o.data.materials.append(m)
    return link(o)


# --------------------------------------------------------------------------
# Село
# --------------------------------------------------------------------------
def hut(mats, loc, rot_z, lit=True, door_open=False, shutters=False, win_k=1.0, lights=True, scale=1.0):
    w, d, h = 7.0 * scale, 5.0 * scale, 2.6 * scale
    objs = []
    objs.append(box((0, 0, h / 2), (w, d, h), mats["wall"], bevel=0.08))
    # стріха
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=1, radius2=0.0, depth=1)
    r = bpy.context.object
    r.rotation_euler = (0, 0, math.pi / 4)
    bpy.ops.object.transform_apply(rotation=True)
    r.scale = (w * 0.8, d * 0.86, 2.7 * scale)
    r.location = (0, 0, h + 1.25 * scale)
    r.data.materials.append(mats["thatch"])
    objs.append(r)
    # призьба
    objs.append(box((0, -d / 2 - 0.15, 0.2), (w + 0.2, 0.35, 0.4), mats["wall"]))
    wm = mats["win"] if lit else mats["win_off"]
    for sx in (-1.9 * scale, 1.9 * scale):
        objs.append(box((sx, -d / 2 - 0.02, 1.45 * scale), (0.8 * scale, 0.06, 0.9 * scale), wm))
        objs.append(box((sx, -d / 2 - 0.06, 1.45 * scale), (0.05, 0.04, 0.9 * scale), mats["wood"]))
        objs.append(box((sx, -d / 2 - 0.06, 1.48 * scale), (0.8 * scale, 0.04, 0.05), mats["wood"]))
        if shutters:
            for ss in (-0.65 * scale, 0.65 * scale):
                objs.append(box((sx + ss, -d / 2 - 0.08, 1.45 * scale), (0.45 * scale, 0.06, 1.0 * scale), mats["shutter"]))
        if lit and lights:
            objs.append(point_light((sx, -d / 2 - 0.7, 1.45 * scale), 90 * win_k, shadow=False))
    if door_open and lit:
        objs.append(box((0, -d / 2 - 0.01, 1.0 * scale), (0.9 * scale, 0.04, 2.0 * scale), mats["win"]))
        objs.append(box((0.5 * scale, -d / 2 + 0.45, 1.0 * scale), (0.06, 0.9 * scale, 2.0 * scale), mats["wood"]))
        if lights:
            objs.append(point_light((0, -d / 2 - 1.0, 1.3 * scale), 160 * win_k, shadow=True, radius=0.4))
    else:
        objs.append(box((0, -d / 2 - 0.03, 1.0 * scale), (0.9 * scale, 0.06, 2.0 * scale), mats["wood"]))
    eu = Euler((0, 0, rot_z))
    for o in objs:
        o.location.rotate(eu)
        o.location += Vector(loc)
        o.rotation_euler.z += rot_z
    return objs


def church(mats, loc, s=1.0):
    x, y, z = loc
    box((x, y, 4 * s), (7 * s, 9 * s, 8 * s), mats["wood"])
    box((x, y, 10 * s), (4 * s, 4 * s, 4 * s), mats["wood"])
    sphere((x, y, 13 * s), 2.2 * s, mats["wood"], scale=(1, 1, 1.25))
    cone((x, y, 16 * s), 0.6 * s, 0, 2 * s, mats["wood"])
    box((x, y, 17.6 * s), (0.12 * s, 0.12 * s, 2.0 * s), mats["metal"])
    box((x, y, 18.0 * s), (0.9 * s, 0.1 * s, 0.1 * s), mats["metal"])
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=1, radius2=0, depth=1)
    r = bpy.context.object
    r.rotation_euler = (0, 0, math.pi / 4)
    bpy.ops.object.transform_apply(rotation=True)
    r.scale = (5.5 * s, 7 * s, 3 * s)
    r.location = (x, y, 9.5 * s)
    r.data.materials.append(mats["thatch"])


def lantern_pole(mats, loc, k=1.0, lit=True, shadow=False):
    x, y, z = loc
    cyl((x, y, z + 1.8), 0.06, 3.6, mats["wood"], verts=8)
    box((x + 0.35, y, z + 3.55), (0.8, 0.08, 0.08), mats["wood"])
    box((x + 0.7, y, z + 3.25), (0.26, 0.26, 0.36), mats["flame"] if lit else mats["metal"])
    box((x + 0.7, y, z + 3.47), (0.34, 0.34, 0.06), mats["metal"])
    if lit:
        return point_light((x + 0.7, y, z + 3.05), 220 * k, shadow=shadow, radius=0.1)


def hand_lantern(mats, parent, offset=(0, 0, 0), k=1.0):
    o = box(offset, (0.14, 0.14, 0.2), mats["flame"])
    o.parent = parent
    l = point_light(offset, 45 * k, shadow=False, radius=0.06)
    l.parent = parent
    return o, l


def well(mats, loc):
    x, y, z = loc
    box((x, y, z + 0.5), (1.2, 1.2, 1.0), mats["wood"])
    cyl((x + 1.2, y, z + 2.0), 0.1, 4.0, mats["wood"], verts=8)
    o = cyl((x + 1.2, y, z + 4.0), 0.07, 8.5, mats["wood"], rot=(0, math.radians(62), 0), verts=8)
    cyl((x - 0.45, y, z + 3.2), 0.015, 3.8, mats["metal"], verts=6)
    box((x - 0.45, y, z + 1.3), (0.35, 0.35, 0.4), mats["wood"])


def fence(mats, a, b, h=1.1, seed=0):
    r = random.Random(seed)
    a, b = Vector(a), Vector(b)
    n = int((b - a).length / 0.25)
    for i in range(n):
        p = a.lerp(b, i / max(n - 1, 1))
        o = cyl((p.x, p.y, h / 2), 0.03, h * r.uniform(0.85, 1.1), mats["wood"], verts=5)
        o.rotation_euler = (r.uniform(-0.06, 0.06), r.uniform(-0.06, 0.06), 0)
    d = b - a
    ang = math.atan2(d.y, d.x)
    for zz in (0.35, 0.8):
        box(((a.x + b.x) / 2, (a.y + b.y) / 2, zz), (d.length, 0.05, 0.05), mats["wood"], rot=(0, 0, ang))


def grave_cross(mats, loc, h=1.6, tilt=0.0, rot=0.0, m=None, towel=False):
    m = m or mats["wood"]
    x, y, z = loc
    objs = [box((0, 0, h / 2), (0.1, 0.1, h), m),
            box((0, 0, h * 0.75), (h * 0.55, 0.08, 0.09), m),
            box((0, 0, h * 0.38), (h * 0.35, 0.08, 0.08), m, rot=(0, math.radians(-18), 0))]
    if towel:
        objs.append(box((h * 0.25, -0.05, h * 0.55), (0.14, 0.02, 0.55), mats["scarf"]))
        objs.append(box((h * 0.25, -0.06, h * 0.32), (0.14, 0.02, 0.06), mats["cloth_red"]))
    eu = Euler((tilt, 0, rot))
    for o in objs:
        o.location.rotate(eu)
        o.location += Vector(loc)
        o.rotation_euler = (o.rotation_euler.x + tilt, o.rotation_euler.y, o.rotation_euler.z + rot)
    return objs


# --------------------------------------------------------------------------
# Персонажі (ієрархія «кісток»-порожніх об'єктів + гладкі частини тіла)
# --------------------------------------------------------------------------
class Person:
    def __init__(self, mats, kind="andriy", name="p", h=1.8):
        self.kind = kind
        self.h = h
        s = h / 1.8
        self.s = s
        self.root = self._empty(name + "_root", (0, 0, 0))
        self.hips = self._empty(name + "_hips", (0, 0, 0.98 * s), self.root)
        self.chest = self._empty(name + "_chest", (0, 0, 0.32 * s), self.hips)
        self.neck = self._empty(name + "_neck", (0, 0, 0.3 * s), self.chest)
        self.head = self._empty(name + "_head", (0, 0, 0.1 * s), self.neck)
        J = {}
        for side, sx in (("l", 1), ("r", -1)):
            sh = self._empty(f"{name}_sh{side}", (sx * 0.19 * s, 0, 0.26 * s), self.chest)
            el = self._empty(f"{name}_el{side}", (0, 0, -0.29 * s), sh)
            wr = self._empty(f"{name}_wr{side}", (0, 0, -0.26 * s), el)
            hp = self._empty(f"{name}_hp{side}", (sx * 0.1 * s, 0, -0.02 * s), self.hips)
            kn = self._empty(f"{name}_kn{side}", (0, 0, -0.46 * s), hp)
            an = self._empty(f"{name}_an{side}", (0, 0, -0.44 * s), kn)
            J[side] = dict(sh=sh, el=el, wr=wr, hp=hp, kn=kn, an=an)
        self.J = J
        self._body(mats)

    def _empty(self, name, loc, parent=None):
        o = bpy.data.objects.new(name, None)
        o.empty_display_size = 0.05
        o.location = loc
        if parent:
            o.parent = parent
        return link(o)

    def _part(self, obj, parent):
        obj.parent = parent
        obj.matrix_parent_inverse.identity()
        return obj

    def _limb(self, parent, length, r0, r1, m):
        bpy.ops.mesh.primitive_cone_add(vertices=14, radius1=r1, radius2=r0, depth=length, location=(0, 0, -length / 2))
        o = bpy.context.object
        o.data.materials.append(m)
        bpy.ops.object.shade_smooth()
        mod = o.modifiers.new("sub", "SUBSURF")
        mod.levels = mod.render_levels = 1
        o.location = (0, 0, -length / 2)
        return self._part(o, parent)

    def _blob(self, parent, loc, r, scale, m, segs=20):
        o = sphere(loc, r, m, scale=scale, segs=segs)
        o.location = loc
        return self._part(o, parent)

    def _body(self, mats):
        s, k = self.s, self.kind
        fem = k in ("hanna", "woman")
        old = k in ("hanna", "old")
        child = k == "child"
        if k == "andriy":
            top, sleeve, legs, skin = mats["jacket"], mats["jacket"], mats["jeans"], mats["skin"]
        elif k == "hanna":
            top, sleeve, legs, skin = mats["shawl"], mats["dress"], mats["dress"], mats["skin_old"]
        elif k == "woman":
            top, sleeve, legs, skin = mats["villager2"], mats["villager2"], mats["dress"], mats["skin"]
        elif k == "child":
            top, sleeve, legs, skin = mats["linen"], mats["linen"], mats["linen"], mats["skin"]
        else:
            top, sleeve, legs, skin = mats["linen"] if k == "man" else mats["villager"], mats["villager"], mats["villager"], mats["skin_old"] if old else mats["skin"]
        # тулуб: таз + довгий торс (куртка/сорочка) + комір, що ховає шию
        self._blob(self.hips, (0, 0, 0.06 * s), 0.19 * s, (1.0, 0.75, 0.85), legs)
        self._blob(self.chest, (0, 0, 0.06 * s), 0.215 * s, (1.0 if not fem else 0.95, 0.72, 1.55), top)
        self._blob(self.hips, (0, 0, 0.16 * s), 0.2 * s, (1.02, 0.76, 0.75), top)
        self._blob(self.chest, (0, 0, 0.27 * s), 0.11 * s, (1.25, 1.1, 0.55), top, segs=14)
        self._blob(self.neck, (0, 0, 0.02 * s), 0.062 * s, (1, 1, 1.4), skin, segs=12)
        # голова
        hr = 0.11 * s * (1.12 if child else 1.0)
        self._blob(self.head, (0, 0, hr), hr, (0.86, 0.95, 1.08), skin)
        self._blob(self.head, (0, -hr * 0.9, hr * 0.92), hr * 0.16, (0.8, 1.1, 1.3), skin, segs=10)  # ніс
        for ex in (-0.38, 0.38):
            self._blob(self.head, (ex * hr, -hr * 0.82, hr * 1.12), hr * 0.08, (1.2, 0.6, 0.7), mats["hair"], segs=10)
        if k == "andriy":
            self._blob(self.head, (0, 0.02 * s, hr * 1.35), hr * 0.98, (0.9, 0.98, 0.62), mats["hair"])
            self._blob(self.head, (0, -hr * 0.35, hr * 0.45), hr * 0.62, (1.2, 0.9, 0.7), mats["hair"], segs=14)  # щетина
            self._blob(self.chest, (0, -0.02 * s, 0.33 * s), 0.12 * s, (1.3, 1.1, 0.5), mats["hoodie"])  # капюшон
        elif fem:
            # хустка
            self._blob(self.head, (0, 0.03 * s, hr * 1.1), hr * 1.18, (0.95, 1.02, 1.05), mats["scarf"])
            self._blob(self.head, (0, 0.06 * s, hr * 0.1), hr * 0.9, (1.0, 0.8, 0.8), mats["scarf"])
        elif k == "old":
            self._blob(self.head, (0, 0, hr * 1.55), hr * 1.1, (1.0, 1.05, 0.35), mats["villager"])
        else:
            self._blob(self.head, (0, 0.02 * s, hr * 1.35), hr * 0.98, (0.92, 1.0, 0.6), mats["hair"])
        # спідниця для жінок
        if fem:
            bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.38 * s, radius2=0.18 * s, depth=0.95 * s, location=(0, 0, -0.45 * s))
            o = bpy.context.object
            o.data.materials.append(mats["dress"])
            bpy.ops.object.shade_smooth()
            self._part(o, self.hips)
            o.location = (0, 0, -0.42 * s)
        for side in ("l", "r"):
            J = self.J[side]
            self._limb(J["sh"], 0.31 * s, 0.075 * s, 0.065 * s, sleeve)
            self._limb(J["el"], 0.28 * s, 0.066 * s, 0.052 * s, sleeve)
            self._blob(J["el"], (0, 0, 0), 0.068 * s, (1, 1, 1), sleeve, segs=10)
            self._blob(J["wr"], (0, -0.01 * s, -0.07 * s), 0.05 * s, (0.7, 0.45, 1.3), skin, segs=12)
            if not fem:
                self._limb(J["hp"], 0.5 * s, 0.1 * s, 0.078 * s, legs)
                self._limb(J["kn"], 0.46 * s, 0.078 * s, 0.06 * s, legs)
                self._blob(J["kn"], (0, 0, 0), 0.08 * s, (1, 1, 1), legs, segs=10)
                self._blob(J["hp"], (0, 0, 0), 0.1 * s, (1, 1, 1), legs, segs=10)
            self._blob(J["an"], (0, -0.06 * s, -0.03 * s), 0.06 * s, (0.75, 1.8, 0.55), mats["boots"], segs=12)
            self._blob(J["sh"], (0, 0, 0), 0.085 * s, (1, 1, 1), sleeve, segs=12)
        if k == "andriy":  # камера на ремені
            cam = box((0.1 * s, -0.16 * s, -0.05 * s), (0.13 * s, 0.07 * s, 0.09 * s), mats["metal"])
            self._part(cam, self.chest)
            cam.location = (0.1 * s, -0.17 * s, -0.04 * s)

    # ---- пози й анімація
    def place(self, loc, yaw_deg):
        self.root.location = loc
        self.root.rotation_euler = (0, 0, math.radians(yaw_deg))

    def key_all(self, f):
        for o in [self.root, self.hips, self.chest, self.neck, self.head] + [j for d in self.J.values() for j in d.values()]:
            o.keyframe_insert("rotation_euler", frame=f)
        self.root.keyframe_insert("location", frame=f)
        self.hips.keyframe_insert("location", frame=f)

    def pose(self, f, phase=0.0, gait="stand", look=(0, 0), arms=None, breathe=True):
        s = self.s
        J = self.J
        sw = {"stand": 0.0, "walk": 0.45, "run": 0.95, "slow": 0.22}.get(gait, 0)
        p = phase * 2 * math.pi
        for side, sg in (("l", 1), ("r", -1)):
            a = math.sin(p + (0 if side == "l" else math.pi))
            J[side]["hp"].rotation_euler = (sw * a * 0.8, 0, 0)
            J[side]["kn"].rotation_euler = (-max(0, -math.cos(p + (0 if side == "l" else math.pi))) * sw * 1.3 - 0.05, 0, 0)
            J[side]["an"].rotation_euler = (0.1 * sw * a, 0, 0)
            J[side]["sh"].rotation_euler = (-sw * a * 0.7, sg * 0.08, 0)
            J[side]["el"].rotation_euler = (-0.25 - sw * 0.9 * (0.6 + 0.4 * a), 0, 0)
        bob = abs(math.sin(p)) * 0.04 * sw * s
        self.hips.location = (0, 0, 0.98 * s + bob - (0.05 * s if gait == "run" else 0))
        lean = {"run": 0.28, "walk": 0.06}.get(gait, 0.0)
        br = 0.012 * math.sin(f * 0.35) if breathe else 0
        self.chest.rotation_euler = (lean + br, 0, 0.12 * sw * math.sin(p))
        self.head.rotation_euler = (math.radians(look[1]), 0, math.radians(look[0]))
        if arms:
            arms(self, f)
        self.key_all(f)

    def kneel(self, f, t=1.0):
        s = self.s
        J = self.J
        for side in ("l", "r"):
            J[side]["hp"].rotation_euler = (1.4 * t if side == "l" else 0.2 * t, 0, 0)
            J[side]["kn"].rotation_euler = (-1.5 * t if side == "l" else -1.7 * t, 0, 0)
            J[side]["sh"].rotation_euler = (-0.2, 0, 0)
            J[side]["el"].rotation_euler = (-0.3, 0, 0)
        self.hips.location = (0, 0, 0.98 * s - 0.48 * s * t)
        self.chest.rotation_euler = (0.25 * t, 0, 0)
        self.head.rotation_euler = (0.2 * t, 0, 0)
        self.key_all(f)


def arm_raise(side="r", up=1.4, el=0.4):
    def fn(p, f):
        p.J[side]["sh"].rotation_euler = (-up, 0, 0)
        p.J[side]["el"].rotation_euler = (-el, 0, 0)
    return fn


def arm_hold(side="r"):
    """Рука зігнута вперед (тримає ліхтарик/свічку/лампу)."""
    def fn(p, f):
        p.J[side]["sh"].rotation_euler = (-0.55, 0, 0)
        p.J[side]["el"].rotation_euler = (-1.0, 0, 0)
    return fn


def walk_path(person, pts, f0, f1, gait="walk", stride=1.4, look=(0, 0), arms=None, step=1):
    """Веде персонажа по ламаній pts [(x,y,z)] з кадру f0 до f1."""
    P = [Vector(p) for p in pts]
    L = [0.0]
    for a, b in zip(P, P[1:]):
        L.append(L[-1] + (b - a).length)
    tot = max(L[-1], 1e-6)
    s = person.s
    for f in range(f0, f1 + 1, step):
        u = (f - f0) / max(f1 - f0, 1)
        d = u * tot
        i = max(j for j in range(len(L)) if L[j] <= d + 1e-9)
        i = min(i, len(P) - 2)
        seg = max(L[i + 1] - L[i], 1e-6)
        pos = P[i].lerp(P[i + 1], (d - L[i]) / seg)
        dirv = P[i + 1] - P[i]
        yaw = math.atan2(dirv.y, dirv.x) - math.pi / 2 if dirv.length > 1e-6 else person.root.rotation_euler.z
        person.root.location = pos
        person.root.rotation_euler = (0, 0, yaw)
        phase = d / (stride * s)
        person.pose(f, phase, gait if tot > 0.05 else "stand", look, arms)


def stand(person, f0, f1, look=(0, 0), arms=None, step=2, sway=True):
    for f in range(f0, f1 + 1, step):
        lk = (look[0] + (2 * math.sin(f * 0.07) if sway else 0), look[1])
        person.pose(f, 0, "stand", lk, arms)


# --------------------------------------------------------------------------
# Камера
# --------------------------------------------------------------------------
def camera(lens=35, dof=None, fstop=2.8):
    cam = bpy.data.cameras.new("cam")
    cam.lens = lens
    cam.clip_start = 0.05
    cam.clip_end = 2000
    if dof:
        cam.dof.use_dof = True
        cam.dof.focus_distance = dof
        cam.dof.aperture_fstop = fstop
    o = bpy.data.objects.new("cam", cam)
    link(o)
    bpy.context.scene.camera = o
    return o


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def cam_move(cam, f0, f1, p0, p1, t0, t1, roll0=0.0, roll1=0.0, shake=0.0, lens0=None, lens1=None, seed=0):
    r = random.Random(seed)
    ph = [r.uniform(0, 6.28) for _ in range(6)]
    for f in range(f0, f1 + 1):
        u = 0.25 * ((f - f0) / max(f1 - f0, 1)) + 0.75 * ease((f - f0) / max(f1 - f0, 1))
        p = Vector(p0).lerp(Vector(p1), u)
        t = Vector(t0).lerp(Vector(t1), u)
        if shake:
            p += Vector((math.sin(f * 0.9 + ph[0]) + 0.5 * math.sin(f * 2.3 + ph[1]),
                         math.sin(f * 0.7 + ph[2]) * 0.5,
                         math.sin(f * 1.1 + ph[3]) + 0.5 * math.sin(f * 2.9 + ph[4]))) * shake
        cam.location = p
        look_at(cam, t, roll0 + (roll1 - roll0) * u)
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
        if lens0 is not None:
            cam.data.lens = lens0 + (lens1 - lens0) * u
            cam.data.keyframe_insert("lens", frame=f)


def flicker(light, f0, f1, base, amount=0.25, seed=0, speed=1.0):
    r = random.Random(seed)
    for f in range(f0, f1 + 1):
        light.data.energy = base * (1 + amount * (0.6 * math.sin(f * 1.7 * speed + r.random()) + 0.4 * r.uniform(-1, 1)))
        light.data.keyframe_insert("energy", frame=f)


# --------------------------------------------------------------------------
# Дешевий туман у матеріалах (без шуму об'ємів): колір → туман за відстанню до камери
# --------------------------------------------------------------------------
def distance_fog(density=0.03, color=(0.05, 0.07, 0.11), strength=1.0, height_falloff=0.0):
    for m in bpy.data.materials:
        if not m.use_nodes or m.get("fogged"):
            continue
        nt = m.node_tree
        out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
        if out is None or not out.inputs["Surface"].links:
            continue
        src = out.inputs["Surface"].links[0].from_socket
        camd = nt.nodes.new("ShaderNodeCameraData")
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = -density
        nt.links.new(camd.outputs["View Distance"], mul.inputs[0])
        ex = nt.nodes.new("ShaderNodeMath")
        ex.operation = "EXPONENT"
        nt.links.new(mul.outputs[0], ex.inputs[0])
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        nt.links.new(ex.outputs[0], inv.inputs[1])
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*color, 1)
        em.inputs["Strength"].default_value = strength
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(inv.outputs[0], mix.inputs["Fac"])
        nt.links.new(src, mix.inputs[1])
        nt.links.new(em.outputs["Emission"], mix.inputs[2])
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
        m["fogged"] = 1


# --------------------------------------------------------------------------
# Світловий промінь у тумані (фейковий об'єм: напівпрозорий конус, що світиться)
# --------------------------------------------------------------------------
def beam(origin, target, radius, color=(0.9, 0.95, 1.0), k=1.5, length=None, name="beam"):
    o_ = Vector(origin)
    d = Vector(target) - o_
    L = length or d.length
    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=radius, radius2=0.03, depth=L, end_fill_type="NOTHING")
    o = bpy.context.object
    o.name = name
    m = bpy.data.materials.new(name + "_m")
    m.use_nodes = True
    setp(m, "surface_render_method", "BLENDED")
    setp(m, "blend_method", "BLEND")
    setp(m, "use_backface_culling", False)
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    # z=1 біля джерела (верх конуса), z=0 на кінці; м'якшаємо краї за кутом огляду
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 2.2
    nt.links.new(sep.outputs["Z"], pw.inputs[0])
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.6
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    nt.links.new(lw.outputs["Facing"], inv.inputs[1])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    nt.links.new(pw.outputs[0], mul.inputs[0])
    nt.links.new(inv.outputs[0], mul.inputs[1])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 3.0
    mul2 = nt.nodes.new("ShaderNodeMath")
    mul2.operation = "MULTIPLY"
    nt.links.new(mul.outputs[0], mul2.inputs[0])
    nt.links.new(nz.outputs["Fac"], mul2.inputs[1])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    mk = nt.nodes.new("ShaderNodeMath")
    mk.operation = "MULTIPLY"
    mk.inputs[1].default_value = k
    nt.links.new(mul2.outputs[0], mk.inputs[0])
    nt.links.new(mk.outputs[0], em.inputs["Strength"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(tr.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    m["fogged"] = 1
    o.data.materials.append(m)
    setp(o, "visible_shadow", False)
    # орієнтуємо: вершина конуса (radius2) у джерелі
    o.location = o_ + d.normalized() * (L / 2)
    o.rotation_euler = (-d).to_track_quat("Z", "Y").to_euler()
    return o


def hatchback(mats, loc, yaw, m=None, lights=True, tail=True, lit_k=1.0, old=False):
    m = m or (mats["car_old"] if old else mats["car"])
    parts = []
    parts.append(box((0, 0, 0.62), (1.75, 3.9, 0.7), m, bevel=0.12))
    parts.append(box((0, -0.25, 1.18), (1.6, 2.2, 0.55), m, bevel=0.12))
    for sx in (-0.8, 0.8):
        parts.append(box((sx, -0.25, 1.18), (0.04, 2.0, 0.42), mats["glass"]))
    parts.append(box((0, 0.88, 1.15), (1.5, 0.05, 0.45), mats["glass"], rot=(math.radians(-30), 0, 0)))
    parts.append(box((0, -1.37, 1.15), (1.5, 0.05, 0.42), mats["glass"], rot=(math.radians(25), 0, 0)))
    for sx in (-0.82, 0.82):
        for sy in (-1.25, 1.25):
            parts.append(cyl((sx, sy, 0.33), 0.33, 0.24, mats["boots"], rot=(0, math.radians(90), 0), verts=20))
    if lights:
        for sx in (-0.6, 0.6):
            parts.append(box((sx, 1.96, 0.72), (0.3, 0.04, 0.14), mats["head_light"]))
    if tail:
        for sx in (-0.65, 0.65):
            parts.append(box((sx, -1.96, 0.78), (0.25, 0.04, 0.12), mats["red_light"]))
    eu = Euler((0, 0, yaw))
    for p in parts:
        p.location.rotate(eu)
        p.location += Vector(loc)
        p.rotation_euler.z += yaw
    return parts


def headlights(loc, yaw, k=1.0, length=28):
    out = []
    eu = Euler((0, 0, yaw))
    for sx in (-0.6, 0.6):
        o = Vector((sx, 2.0, 0.72))
        o.rotate(eu)
        o += Vector(loc)
        fwd = Vector((0, 1, -0.06))
        fwd.rotate(eu)
        rot = (fwd * -1).to_track_quat("Z", "Y").to_euler()
        out.append(spot_light(o, rot, 900 * k, color=(1, 0.95, 0.85), size_deg=40, blend=0.5))
        out.append(beam(o, o + fwd * length, 2.4, (1, 0.95, 0.85), 0.6 * k))
    return out
