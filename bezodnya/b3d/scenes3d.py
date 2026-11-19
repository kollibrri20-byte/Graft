"""32 сцени "Безодні" у 3D. scene_K(ctx) будує сцену й повертає update(t)."""
import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

from character import Character
from common import (Cockpit, Snow, fish, seabed, sub_white, trieste, water_env, wiggle)
from lib import (aim, camera, ease, emissive, lerp, lerpv, light, loft, mat, obj_from_bm, prim, reset, set_emit,
                 smooth, snow, terrain, tube, update_tube)


def shake(t, amp, seed=0.0):
    return Vector((amp * (math.sin(t * 37 + seed) * 0.6 + math.sin(t * 61 + 2 * seed) * 0.4),
                   0,
                   amp * (math.sin(t * 43 + 1 + seed) * 0.6 + math.sin(t * 71 + seed) * 0.4)))


def use_cam(c):
    bpy.context.scene.camera = c


# ================================================================ батискаф 1960 зсередини
def bathysphere_set(o=Vector((0, 0, 0))):
    steel = mat("b_steel", (0.45, 0.38, 0.28), 0.5, metal=0.45, noise=0.5, noise_scale=5, bump=0.12)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    obj_from_bm("sphere_in", bm, steel, True).location = o
    rv = mat("rivet", (0.45, 0.38, 0.28), 0.35, metal=0.9)
    for ring_a in (0.45, -0.3):
        for k in range(36):
            a = k / 36 * 2 * math.pi
            r = 0.985 * math.cos(ring_a)
            prim("sphere", o + Vector((math.cos(a) * r, math.sin(a) * r, 0.985 * math.sin(ring_a))), (0.018,) * 3,
                 material=rv, segments=8, ring_count=4)
    # ілюмінатор (вікно назовні) — праворуч позаду
    pc = o + Vector((0.55, 0.78, 0.1))
    ring = prim("torus", pc, (1, 1, 1), rot=(math.radians(80), 0, math.radians(35)), material=rv,
                major_radius=0.13, minor_radius=0.03)
    glass = prim("cyl", pc, (0.12, 0.12, 0.02), rot=(math.radians(80), 0, math.radians(35)),
                 material=mat("bwin", (0.01, 0.02, 0.03), 0.02, coat=1.0), vertices=32)
    # лампа на дроті
    lamp_piv = bpy.data.objects.new("lamppiv", None)
    bpy.context.scene.collection.objects.link(lamp_piv)
    lamp_piv.location = o + Vector((0.02, 0.62, 0.78))
    wire = prim("cyl", (0, 0, -0.18), (0.004, 0.004, 0.18), material=mat("wire", (0.02, 0.02, 0.02), 0.5))
    wire.parent = lamp_piv
    bulb = prim("sphere", (0, 0, -0.38), (0.035, 0.035, 0.045), material=emissive("bulb", (1, 0.75, 0.4), 25))
    bulb.parent = lamp_piv
    shade = prim("cone", (0, 0, -0.33), (0.06, 0.06, 0.035), material=mat("shade", (0.45, 0.38, 0.25), 0.35, metal=0.8))
    shade.parent = lamp_piv
    L = light("POINT", (0, 0, 0), 140, (1, 0.7, 0.4), size=0.05)
    L.parent = lamp_piv
    L.location = (0, 0, -0.4)
    fill = light("AREA", o + Vector((0, -0.6, 0.2)), 6, (0.45, 0.55, 0.7), target=o, size=0.6)
    # прилади на стіні
    for k in range(5):
        a = -0.9 + k * 0.32
        g = prim("cyl", o + Vector((math.sin(a) * 0.95, math.cos(a) * 0.95, 0.35 + 0.08 * (k % 2))), (0.045, 0.045, 0.02),
                 rot=(math.pi / 2, 0, -a), material=mat("gauge", (0.85, 0.82, 0.7), 0.3), vertices=20)
    men = []
    for k, (x, y, hair, shirt, yaw) in enumerate(((-0.3, 0.05, (0.05, 0.04, 0.03), (0.32, 0.3, 0.27), 0.35),
                                                  (0.28, 0.12, (0.18, 0.11, 0.06), (0.12, 0.15, 0.22), -0.3))):
        c = Character("Man%d" % k, skin=(0.6, 0.36, 0.25) if k == 0 else (0.62, 0.4, 0.3), hair=hair, shirt=shirt,
                      shirt2=shirt, eyes=(0.3, 0.35, 0.3), loc=o + Vector((x, y, -0.52)), headset=False)
        c.root.rotation_euler = (0, 0, yaw)
        men.append(c)
    return lamp_piv, men, glass


def crack_tree(seed=9):
    r = random.Random(seed)
    segs = []

    def grow(p, a, L, d, t0):
        if d > 4 or L < 0.006:
            return
        q = p + Vector((math.cos(a) * L, math.sin(a) * L))
        segs.append((p, q, t0, d))
        grow(q, a + r.uniform(-0.5, 0.5), L * 0.85, d + 1, t0 + 0.06)
        if r.random() < 0.5:
            grow(q, a + r.choice([-1, 1]) * r.uniform(0.6, 1.1), L * 0.6, d + 1, t0 + 0.08)

    for k in range(7):
        grow(Vector((0, 0)), k / 7 * 6.28 + r.uniform(-0.3, 0.3), 0.045, 0, 0)
    return segs


def crack_window(center, normal_rot, radius=0.3, name="cw"):
    """Товсте скло з тріщинами, що проростають; повертає функцію show(progress)."""
    glass = prim("cyl", center, (radius, radius, 0.03), rot=normal_rot,
                 material=mat(name + "g", (0.05, 0.12, 0.16), 0.03, coat=1.0, trans=0.0), vertices=48)
    ring = prim("torus", center, (1, 1, 1), rot=normal_rot, material=mat(name + "r", (0.3, 0.3, 0.32), 0.35, metal=0.9),
                major_radius=radius * 1.08, minor_radius=radius * 0.12)
    m = emissive(name + "crk", (0.75, 0.9, 1.0), 6)
    rotm = Euler(normal_rot).to_matrix()
    objs = []
    sc = radius / 0.25
    for p, q, t0, d in crack_tree():
        a = center + rotm @ Vector((p.x * sc * 4, p.y * sc * 4, 0.036))
        b = center + rotm @ Vector((q.x * sc * 4, q.y * sc * 4, 0.036))
        ob = tube(name + "c", [a, b], [0.0011 * sc * (1.6 - d * 0.25)] * 2, 5, m)
        ob.hide_render = True
        objs.append((ob, t0))

    def show(prog):
        for ob, t0 in objs:
            ob.hide_render = prog < t0
    return show


def scene_1(ctx):
    sc = reset((0.0, 0.0, 0.0), 0.0)
    lamp, men, _ = bathysphere_set()
    cam = camera((0.02, -0.82, 0.02), (0.0, 0.1, -0.02), lens=26)
    c0 = cam.location.copy()

    def up(t):
        p = t / ctx.dur
        lamp.rotation_euler = (0.06 * math.sin(t * 1.2), 0.08 * math.sin(t * 0.9), 0)
        cam.location = c0 + Vector((0, 0.18 * ease(p), 0))
        for k, m in enumerate(men):
            m.face(blink=1.0 if (t + k * 1.3) % 3.7 < 0.12 else 0.0, brow_in=0.6, frown=0.3,
                   look=(0.15 * math.sin(t * 0.4 + k), 0.05))
            m.pose_head(0.12 * math.sin(t * 0.3 + k * 2) + (0.2 if k == 0 else -0.25), -0.05, 0.03 * k)
    return up


def scene_2(ctx):
    sc = reset((0.0, 0.0, 0.0), 0.0)
    lamp, men, _ = bathysphere_set()
    cam = camera((0.02, -0.7, 0.02), (0.0, 0.1, -0.02), lens=28)
    c0 = cam.location.copy()
    # другий план — крупно вікно з тріщиною (окрема декорація)
    o2 = Vector((50, 0, 0))
    show = crack_window(o2, (math.pi / 2, 0, 0), 0.3)
    light("POINT", o2 + Vector((0.3, -0.5, 0.4)), 40, (1, 0.8, 0.6), size=0.05)
    prim("cube", o2 + Vector((0, 0.06, 0)), (1, 0.02, 1), material=mat("w2", (0.2, 0.17, 0.13), 0.5, metal=0.8, noise=0.5, noise_scale=6, bump=0.3), smooth=False)
    cam2 = camera(o2 + Vector((0.05, -0.62, 0.03)), o2, lens=50)
    hit = ctx.seg(0) + 0.9
    close = ctx.seg(2) - 0.3

    def up(t):
        k = smooth(hit, hit + 0.1, t) * (1 - smooth(hit + 0.1, hit + 2.5, t))
        sw = 0.5 * smooth(hit, hit + 0.2, t) * math.exp(-max(0, t - hit) * 0.6)
        lamp.rotation_euler = (sw * math.sin(t * 3.2), sw * 0.7 * math.cos(t * 2.7), 0)
        cam.location = c0 + shake(t, 0.03 * k)
        scared = smooth(hit, hit + 0.3, t)
        for i, m in enumerate(men):
            m.face(blink=0.0 if scared else (1.0 if (t + i) % 3.3 < 0.12 else 0), brow=0.9 * scared, brow_in=0.3,
                   jaw=0.25 * scared * (1 - smooth(hit + 1.5, hit + 3, t)), look=(0.0, 0.25 * scared))
            m.pose_head((0.2 if i == 0 else -0.25) * (1 - scared), -0.25 * scared + shake(t, 0.02 * k, i).x, 0)
        if t < close:
            use_cam(cam)
        else:
            use_cam(cam2)
            prog = (t - close - 0.2) / 1.6
            show(prog)
            cam2.location = o2 + Vector((0.05, -0.62 + 0.05 * (t - close), 0.03)) + shake(t, 0.006 * smooth(close, close + 0.3, t) * (1 - smooth(close + 1, close + 3, t)))
    return up


# ================================================================ "Трієст" у темряві + ведучий
def scene_3(ctx):
    sc = reset((0.0, 0.0, 0.004), 0.035, 0.7, (0.25, 0.4, 0.45))
    tr, lights = trieste((0, 0, 0), 1.0)
    cam = camera((-14, -14, 1.0), (0, 0, 0.0), lens=35)
    light("AREA", (-8, -10, 6), 900, (0.5, 0.65, 0.8), target=(0, 0, 0), size=4)
    light("AREA", (6, 8, 3), 600, (0.3, 0.5, 0.7), target=(0, 0, 0), size=4)
    cam.data.dof.use_dof = True
    cam.data.dof.focus_object = tr
    cam.data.dof.aperture_fstop = 4
    sn = Snow(cam, 2500, (16, 16, 10), 0.5, (0.5, 0.6, 0.65), 0.01)
    cp = Cockpit(ctx, water=(0.0, 0.03, 0.06), darkness=0.7)
    cut = ctx.seg(3) - 0.15

    def up(t):
        if t < cut:
            use_cam(cam)
            a = -2.4 + 0.5 * t / cut
            cam.location = Vector((math.cos(a) * 17, math.sin(a) * 17, 1.5 - 0.1 * t))
            aim(cam, (0, 0, -0.3))
            sn.update(t)
            tr.location = (0, 0, -0.05 * t)
        else:
            use_cam(cp.cam)
            cp.update(t, push=(t - cut) / (ctx.dur - cut))
    return up


# ================================================================ Гуам, захід сонця, пірнання
def ocean_surface(size=200, res=10, mat_=None, loc=(0, 0, 0), choppy=1.0, scale=1.0):
    bpy.ops.mesh.primitive_plane_add(size=2, location=loc)
    ob = bpy.context.object
    md = ob.modifiers.new("Ocean", "OCEAN")
    md.geometry_mode = "GENERATE"
    md.size = size / 10
    md.spatial_size = int(size / 2)
    md.repeat_x = 2
    md.repeat_y = 2
    md.resolution = res
    md.choppiness = choppy
    md.wave_scale = scale
    md.use_normals = True
    if mat_ is not None:
        ob.data.materials.append(mat_)
    bpy.ops.object.shade_smooth()
    return ob, md


def scene_4(ctx):
    sc = reset((0.9, 0.42, 0.22), 0.0, strength=1.0)
    wnt = sc.world.node_tree
    # небо-градієнт
    tc = wnt.nodes.new("ShaderNodeTexCoord")
    sep = wnt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = wnt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (1.0, 0.5, 0.22, 1)
    ramp.color_ramp.elements[1].position = 0.45
    ramp.color_ramp.elements[1].color = (0.12, 0.08, 0.25, 1)
    wnt.links.new(tc.outputs["Generated"], sep.inputs[0])
    wnt.links.new(sep.outputs["Z"], ramp.inputs[0])
    bgn = wnt.nodes["Background"]
    wnt.links.new(ramp.outputs[0], bgn.inputs[0])
    sea_m = mat("sea", (0.01, 0.06, 0.07), 0.06, coat=0.5)
    sea, md = ocean_surface(400, 12, sea_m, (0, 0, 0), 1.2, 1.5)
    sea.scale = (1, 1, 1)
    sun = prim("sphere", (60, 400, 18), (9, 9, 9), material=emissive("sunm", (1, 0.75, 0.45), 18))
    sl = light("SUN", (0, 0, 10), 4, (1, 0.6, 0.35), rot=(math.radians(85), 0, math.radians(172)))
    # острів
    isl = terrain("island", 120, 60, 0, 5, mat("isl", (0.03, 0.03, 0.05), 0.8), 6.0, (-40, 330, -2),
                  ridge=lambda X, Y: 9 * np.exp(-(X / 35) ** 2 - (Y / 12) ** 2) + 4 * np.exp(-((X - 25) / 12) ** 2 - (Y / 8) ** 2))
    cam = camera((0, -20, 22), (0, 200, 10), lens=30)
    # підводна частина — окремий світ нижче (той самий об'єкт моря видно знизу)
    under_vol = None
    dive = 10 * ctx.dur

    def up(t):
        md.time = t * 0.8
        p = t / ctx.dur
        if t < dive:
            k = ease(p)
            cam.location = Vector((0, -20 + 22 * k, 22 - 19 * k))
            aim(cam, lerpv((0, 200, 10), (0, 120, -6), k))
        else:
            k = ease((t - dive) / (ctx.dur - dive))
            cam.location = Vector((0, 5 + 6 * k, 4 - 3.4 * k))
            aim(cam, lerpv((0, 25, -10), (0, 14, -3), k))
    return up


# ================================================================ Еверест у западині (розріз)
def scene_5(ctx):
    sc = reset((0.0, 0.01, 0.03), 0.012, 0.3, (0.3, 0.6, 0.85))
    rock = mat("rock5", (0.22, 0.2, 0.19), 0.85, noise=0.6, noise_scale=0.8, bump=0.5)
    # западина: V-подібний профіль уздовж Y, глибина 11
    trench = terrain("trench", 70, 140, 0.25, 7, rock, 3.0, (0, 0, -11),
                     ridge=lambda X, Y: 8.5 * np.clip(np.abs(X) / 22, 0, 1) ** 1.3)
    # Еверест: гора від дна (−11) до −2.15
    mnt = terrain("everest", 30, 120, 0.12, 9, rock, 1.5, (0, 6, -11.2),
                  ridge=lambda X, Y: 8.85 * np.exp(-((X / 7.5) ** 2 + (Y / 7.5) ** 2) ** 0.75))
    cap = prim("cone", (0, 6, -2.75), (1.5, 1.5, 0.7), material=mat("snowcap", (0.85, 0.88, 0.92), 0.6, noise=0.3, noise_scale=3, bump=0.4), vertices=24)
    surf = prim("plane", (0, 0, 0), (60, 60, 1), material=mat("surf", (0.5, 0.75, 0.9), 0.1, emit=(0.4, 0.7, 0.9), emit_str=1.2))
    surf.visible_shadow = False
    light("AREA", (-20, -20, -3), 40000, (0.5, 0.75, 1.0), target=(0, 6, -8), size=20)
    sl = light("SUN", (0, 0, 5), 3.5, (0.55, 0.8, 1.0), rot=(math.radians(15), 0, 0))
    cam = camera((0, -16, -1.0), (0, 6, -2.5), lens=28)
    sn = Snow(cam, 1500, (14, 14, 10), 0.6, (0.6, 0.75, 0.85), 0.02)

    def up(t):
        p = ease(t / ctx.dur)
        cam.location = Vector((2 * math.sin(p * 1.5), -16 + 2 * p, lerp(-0.6, -10, p)))
        aim(cam, (0, 6, lerp(-2.2, -9.5, p)))
        sn.update(t)
        # світло тьмяніє з глибиною
        sl.data.energy = lerp(3.5, 1.0, p)
    return up


# ================================================================ бляшанка під тиском
def scene_6(ctx):
    sc = reset((0.0, 0.03, 0.08), 0.03, 0.6, (0.25, 0.5, 0.8))
    alu = mat("alu", (0.75, 0.76, 0.78), 0.22, metal=1.0)
    red = mat("canred", (0.6, 0.02, 0.04), 0.3, metal=0.6)
    root = bpy.data.objects.new("can", None)
    bpy.context.scene.collection.objects.link(root)
    body = prim("cyl", (0, 0, 0), (0.033, 0.033, 0.061), material=alu, vertices=48)
    band = prim("cyl", (0, 0, 0.005), (0.0335, 0.0335, 0.03), material=red, vertices=48)
    for ob in (body, band):
        ob.parent = root
        sub = ob.modifiers.new("S", "SUBSURF")
        sub.levels = 2
        sub.render_levels = 2
    tex = bpy.data.textures.new("crush", "CLOUDS")
    tex.noise_scale = 0.012
    disp = []
    for ob in (body, band):
        d = ob.modifiers.new("D", "DISPLACE")
        d.texture = tex
        d.strength = 0
        d.mid_level = 0.6
        disp.append(d)
    light("SPOT", (0.15, -0.25, 0.4), 30, (0.7, 0.85, 1.0), target=(0, 0, 0), spot=30, blend=0.6, size=0.05)
    light("AREA", (-0.3, 0.1, 0.1), 2, (0.3, 0.6, 1.0), target=(0, 0, 0), size=0.3)
    cam = camera((0.0, -0.36, 0.05), (0, 0, 0), lens=60)
    sn = Snow(cam, 1500, (1.2, 1.2, 1.0), 1.0, (0.7, 0.85, 0.95), 0.0025)
    bub = []
    rng = random.Random(4)
    bm_ = mat("bub6", (0.9, 0.97, 1.0), 0.05, emit=(0.6, 0.8, 1.0), emit_str=0.8)
    for i in range(40):
        b = prim("sphere", (0, 0, 0), (rng.uniform(0.002, 0.006),) * 3, material=bm_, segments=10, ring_count=6)
        b.hide_render = True
        bub.append((b, Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0, 1.5))).normalized() * rng.uniform(0.05, 0.15)))
    crush_t = 0.5 * ctx.dur

    def up(t):
        p = t / ctx.dur
        root.location = (0.003 * math.sin(t), 0, 0.03 - 0.06 * p)
        root.rotation_euler = (0.15 * math.sin(t * 0.5), 0.3 + 0.1 * math.sin(t * 0.3), t * 0.15)
        k = smooth(crush_t, crush_t + 0.35, t)
        for d in disp:
            d.strength = 0.012 * k
        root.scale = (1 - 0.35 * k, 1 - 0.35 * k, 1 - 0.28 * k)
        cam.location = Vector((0, -0.36 + 0.06 * p, 0.03 - 0.06 * p + 0.02))
        aim(cam, root.location)
        sn.update(t)
        for b, v in bub:
            dt = t - crush_t
            b.hide_render = dt < 0 or dt > 3
            if dt >= 0:
                b.location = root.location + v * (1 - math.exp(-dt * 3)) + Vector((0, 0, 0.02 * dt * dt))
    return up


# ================================================================ ведучий: світла немає; вмикаємо прожектори
def scene_7(ctx):
    sc = reset((0.0, 0.004, 0.012), 0.04, 0.7, (0.3, 0.45, 0.55))
    sub, lights = sub_white((0, 0, 0), 1.0)
    for L in lights:
        L.data.energy = 0
    bulbs = [o for o in bpy.data.objects if o.name.startswith("Sub") is False and o.active_material is not None and o.active_material.name.startswith("subbulb")]
    cam = camera((-6, -7, 3.5), (0.5, 0, -0.5), lens=32)
    light("AREA", (-3, -5, 6), 800, (0.4, 0.6, 0.8), target=(0, 0, 0), size=6)
    sn = Snow(cam, 2500, (14, 14, 10), 1.0, (0.6, 0.7, 0.75), 0.018)
    cp = Cockpit(ctx, water=(0.0, 0.02, 0.05), darkness=0.8)
    cut = ctx.seg(3) - 0.1
    on = cut + 1.0
    bm = bpy.data.materials.get("subbulb")

    def up(t):
        if t < cut:
            use_cam(cp.cam)
            cp.update(t, push=t / cut)
            set_emit(bm, 0)
        else:
            use_cam(cam)
            k = smooth(on, on + 0.15, t)
            fl = 1.0 if (t - on) > 0.5 or (t - on) < 0 else (0.3 if int((t - on) * 24) % 3 == 0 else 1.0)
            for L in lights:
                L.data.energy = 1500 * k * fl
            set_emit(bm, 40 * k * fl)
            dt = t - cut
            sub.location = (0.3 * dt, 0, -0.35 * dt)
            cam.location = Vector((-6 + 0.2 * dt, -7, 3.5 - 0.3 * dt))
            aim(cam, sub.location + Vector((1.5, 0, -1.2)))
            sn.update(t)
    return up


# ================================================================ риф
def scene_8(ctx):
    sc = reset((0.03, 0.35, 0.5), 0.03, 0.75, (0.4, 0.85, 0.95), strength=1.0)
    sand = mat("sand8", (0.75, 0.68, 0.5), 0.9, noise=0.3, noise_scale=2, bump=0.3)
    bed = terrain("bed8", 60, 120, 0.4, 3, sand, 4.0, (0, 0, -6))
    sun = light("SUN", (0, 0, 10), 6, (1.0, 0.97, 0.88), rot=(math.radians(12), math.radians(6), 0))
    rng = random.Random(8)
    cols = [(0.9, 0.3, 0.25), (0.95, 0.65, 0.15), (0.6, 0.25, 0.75), (0.95, 0.45, 0.6), (0.25, 0.75, 0.6), (0.9, 0.85, 0.7)]
    for i in range(70):
        x, y = rng.uniform(-14, 14), rng.uniform(-2, 22)
        m = mat("coral%d" % (i % 6), cols[i % 6], 0.7, noise=0.3, noise_scale=30, bump=0.3, sss=0.2)
        base = Vector((x, y, -5.8 + 0.3 * math.sin(x)))
        if i % 3 == 0:
            prim("ico", base, (0.5 + rng.random() * 0.5, 0.5 + rng.random() * 0.5, 0.35 + rng.random() * 0.4),
                 material=m, subdivisions=3)
        else:
            for b in range(5):
                a = rng.uniform(0, 6.28)
                pts = [base]
                d = Vector((math.cos(a) * 0.3, math.sin(a) * 0.3, 1)).normalized()
                for j in range(5):
                    d = (d + Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 0.2))).normalized()
                    pts.append(pts[-1] + d * 0.25)
                tube("cb", pts, [0.07, 0.06, 0.05, 0.045, 0.04, 0.035], 6, m)
    fishes = []
    fc = [(0.95, 0.75, 0.1), (0.2, 0.5, 0.95), (0.95, 0.4, 0.1), (0.9, 0.9, 0.95)]
    for i in range(45):
        f, tl = fish("rf%d" % i, (0, 0, 0), 0.22 + 0.1 * rng.random(), fc[i % 4], 0.38, 0.3)
        fishes.append((f, tl, rng.uniform(0, 6.28), rng.uniform(2, 5), rng.uniform(-3.5, -1), i % 3))
    dolph = []
    for k in range(2):
        def prof(u):
            r = math.sin(math.pi * min(1, (u + 0.03) ** 0.7)) * 0.32
            return (r, r * 1.05, 0)
        d = loft("dolph%d" % k, 20, prof, 2.4, 16, mat("dolph", (0.42, 0.48, 0.55), 0.35, coat=0.4), 1)
        fin = prim("cone", (0.1, 0, 0.32), (0.25, 0.05, 0.25), rot=(0, -0.5, 0), material=bpy.data.materials["dolph"])
        fin.parent = d
        tail = prim("cone", (-1.3, 0, 0), (0.08, 0.45, 0.2), rot=(0, math.pi / 2, 0), material=bpy.data.materials["dolph"])
        tail.parent = d
        dolph.append(d)
    cam = camera((0, -8, -1.5), (0, 10, -4), lens=30)
    sn = Snow(cam, 1200, (14, 14, 10), 0.4, (0.9, 0.97, 1.0), 0.015)

    def up(t):
        p = t / ctx.dur
        cam.location = Vector((0.5 * math.sin(t * 0.2), -8 + 4 * p, -1.5 - 2.0 * ease(p)))
        aim(cam, (0, 10, -4.5))
        for f, tl, ph, r, z, school in fishes:
            a = ph + t * (0.35 + 0.1 * school)
            c = Vector((-3 + 4 * school, 6 + 2 * school, z))
            f.location = c + Vector((math.cos(a) * r, math.sin(a) * r * 0.5, 0.3 * math.sin(a * 2)))
            f.rotation_euler = (0, 0, a + math.pi / 2)
            wiggle(f, tl, t, 9, 0.5, ph)
        for k, d in enumerate(dolph):
            x = -16 + (t * 2.6 + k * 9) % 34
            d.location = (x, 4 + 5 * k, -2.5 + 0.6 * math.sin(t * 1.2 + k))
            d.rotation_euler = (0, 0.12 * math.cos(t * 1.2 + k), 0)
        sn.update(t)
    return up


# ================================================================ спільні істоти
def jellyfish(loc, r, color, strength=3.0, name="jf"):
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    root.location = loc
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=r)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().z < -0.02 * r], context="FACES")
    m = mat(name + "m", color, 0.2, emit=color, emit_str=strength, alpha=0.75)
    bell = obj_from_bm(name + "bell", bm, m, True)
    bell.parent = root
    tents = []
    tm = mat(name + "t", color, 0.3, emit=color, emit_str=strength * 0.6)
    for k in range(6):
        a = k / 6 * 6.28
        pts = [Vector((math.cos(a) * r * 0.7, math.sin(a) * r * 0.7, -0.02 * r - j * r * 0.35)) for j in range(9)]
        tb = tube(name + "tt", pts, [r * 0.03] * 9, 5, tm)
        tb.parent = root
        tents.append((tb, a))
    return root, bell, tents, m


def update_jelly(root, bell, tents, r, t, ph=0.0):
    pul = 1 + 0.12 * math.sin(t * 2.2 + ph)
    bell.scale = (pul, pul, 1 / pul)
    for tb, a in tents:
        pts = [Vector((math.cos(a) * r * 0.7 + 0.15 * r * math.sin(t * 1.5 + j * 0.5 + a) * j / 8,
                       math.sin(a) * r * 0.7, -0.02 * r - j * r * 0.35)) for j in range(9)]
        update_tube(tb, pts, [r * 0.03] * 9, 5)


def whale(loc, L=11.0, name="whale"):
    skin = mat(name + "skin", (0.2, 0.2, 0.22), 0.55, noise=0.5, noise_scale=1.5, bump=0.6)

    def prof(u):
        if u < 0.32:
            h = 0.12
            w = 0.1 * (min(1, u / 0.04) ** 0.5)
        else:
            k = (u - 0.32) / 0.68
            h = 0.12 * (1 - k ** 1.4 * 0.88)
            w = 0.1 * (1 - k ** 1.3 * 0.88)
        return (w * L, h * L, 0)

    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    root.location = loc
    body = loft(name + "b", 30, prof, L, 18, skin, 1)
    body.parent = root
    jaw = prim("cube", (0.25 * L, 0, -0.1 * L), (0.18 * L, 0.035 * L, 0.012 * L), material=skin)
    jaw.parent = root
    for sy in (-1, 1):
        e = prim("sphere", (0.36 * L, sy * 0.095 * L, -0.03 * L), (0.012 * L,) * 3,
                 material=mat("weye", (0.01, 0.01, 0.01), 0.1, coat=1))
        e.parent = root
        fl = prim("sphere", (0.12 * L, sy * 0.1 * L, -0.07 * L), (0.06 * L, 0.01 * L, 0.025 * L), material=skin)
        fl.parent = root
    tp = bpy.data.objects.new(name + "tp", None)
    bpy.context.scene.collection.objects.link(tp)
    tp.parent = root
    tp.location = (-0.48 * L, 0, 0)
    fluke = prim("sphere", (-0.05 * L, 0, 0), (0.06 * L, 0.17 * L, 0.012 * L), material=skin)
    fluke.parent = tp
    return root, tp


def squid(loc, s=1.0, name="sq", color=(0.6, 0.12, 0.08)):
    m = mat(name + "m", color, 0.4, sss=0.2, noise=0.4, noise_scale=6, bump=0.3, coat=0.4)
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    root.location = loc

    def prof(u):
        r = 0.45 * math.sin(math.pi * (0.08 + 0.92 * u) ** 0.9) * (1 - 0.5 * u)
        return (r, r, 0)

    mantle = loft(name + "mant", 20, prof, 3.0, 16, m, 1)
    mantle.parent = root
    mantle.location = (-1.5, 0, 0)
    for sz in (-1, 1):
        fin = prim("sphere", (-2.7, 0, sz * 0.0), (0.35, 0.02, 0.7), rot=(math.pi / 2, 0, 0), material=m)
        fin.parent = root
    head = prim("sphere", (0.15, 0, 0), (0.45, 0.42, 0.42), material=m)
    head.parent = root
    eyes = []
    for sy in (-1, 1):
        e = prim("sphere", (0.2, sy * 0.38, 0.05), (0.2, 0.08, 0.2), material=mat("sqeye", (0.02, 0.02, 0.03), 0.05, coat=1))
        e.parent = root
        eyes.append(e)
    arms = []
    am = mat(name + "arm", (color[0] * 0.9, color[1], color[2]), 0.45, sss=0.2, noise=0.3, noise_scale=10, bump=0.2)
    for k in range(10):
        L = 4.5 if k < 2 else 2.4
        pts = [Vector((0.5 + j * L / 15, 0, 0)) for j in range(16)]
        rad = [0.09 * (1 - j / 16) + 0.015 for j in range(16)]
        tb = tube(name + "a", pts, rad, 7, am)
        tb.parent = root
        arms.append((tb, k, L, rad))
    root.scale = (s, s, s)
    return root, arms


def update_arms(arms, t, spread=0.35, curl=0.0, speed=1.2, target=None):
    for tb, k, L, rad in arms:
        a0 = k / 10 * 2 * math.pi
        dirv = Vector((1, math.cos(a0) * spread, math.sin(a0) * spread)).normalized()
        pts = []
        p = Vector((0.5, 0, 0))
        d = dirv.copy()
        for j in range(16):
            u = j / 15
            wob = Vector((0, math.sin(t * speed + k + u * 4) * 0.35 * u, math.cos(t * speed * 0.8 + k * 1.7 + u * 3) * 0.35 * u))
            d = (dirv + wob + Vector((0, math.cos(a0), math.sin(a0))) * curl * u).normalized()
            pts.append(p.copy())
            p = p + d * (L / 15)
        update_tube(tb, pts, rad, 7)


# ================================================================ 9 сутінкова зона
def scene_9(ctx):
    sc = reset((0.01, 0.07, 0.16), 0.03, 0.7, (0.3, 0.55, 0.85))
    top = light("AREA", (0, 0, 25), 60000, (0.4, 0.65, 1.0), rot=(0, 0, 0), size=40)
    cam = camera((0, -5, 0), (0, 0, 0), lens=40)
    sn = Snow(cam, 1800, (10, 10, 8), 0.7, (0.6, 0.75, 0.9), 0.01, vel=(0, 0, 0.25))
    hf, ht = fish("hatch", (-0.5, 0, -0.1), 1.0, (0.75, 0.78, 0.85), 0.9, 0.95)
    lf, lt = fish("lantern", (0.9, 1.2, 0.5), 0.9, (0.3, 0.35, 0.45), 0.35, 0.6)
    for f, L in ((hf, 1.0), (lf, 0.9)):
        for sy in (-1, 1):
            e = prim("sphere", (L * 0.33, sy * L * 0.09, L * 0.06), (L * 0.11,) * 3,
                     material=mat("bigeye", (0.6, 0.65, 0.7), 0.05, metal=0.9, coat=1))
            e.parent = f
    key = light("SPOT", (-1, -4, 1), 300, (0.6, 0.8, 1.0), target=(0, 0, 0), spot=40, blend=0.7)

    def up(t):
        p = t / ctx.dur
        sc.world.node_tree.nodes["Background"].inputs[1].default_value = lerp(1.0, 0.2, p)
        top.data.energy = lerp(60000, 6000, p)
        sn.update(t)
        turn = ease(smooth(0.3, 0.7, p))
        hf.rotation_euler = (0, 0, lerp(0, -math.pi / 2, turn) + 0.05 * math.sin(t))
        lf.rotation_euler = (0, 0, lerp(math.pi, math.pi * 1.5, turn) + 0.05 * math.sin(t + 1))
        hf.location = (-0.5 + 0.1 * math.sin(t * 0.4), 0, -0.1 + 0.05 * math.sin(t * 0.6))
        wiggle(hf, ht, t, 4, 0.3)
        wiggle(lf, lt, t, 5, 0.3, 1)
        cam.location = Vector((0, -5 + 1.2 * p, 0))
    return up


# ================================================================ 10 біолюмінесценція
def scene_10(ctx):
    sc = reset((0.0, 0.0, 0.004), 0.015, 0.5, (0.3, 0.4, 0.6))
    cam = camera((0, -9, 0), (0, 0, 0), lens=35)
    rng = random.Random(10)
    cols = [(0.2, 0.6, 1.0), (0.2, 1.0, 0.75), (1.0, 0.25, 0.35), (0.6, 0.4, 1.0)]
    jel = []
    for i in range(9):
        r = rng.uniform(0.3, 0.8)
        root, bell, tents, m = jellyfish((rng.uniform(-6, 6), rng.uniform(-2, 6), rng.uniform(-3, 3)), r, cols[i % 4], 4, "j%d" % i)
        jel.append((root, bell, tents, r, m, rng.uniform(0, 6)))
    combs = []
    for i in range(4):
        c = Vector((rng.uniform(-4, 4), rng.uniform(-1, 4), rng.uniform(-2, 2)))
        body = prim("sphere", c, (0.25, 0.25, 0.45), material=mat("comb", (0.7, 0.8, 0.9), 0.1, alpha=0.3, emit=(0.3, 0.4, 0.5), emit_str=0.5))
        rows = []
        for rr in range(8):
            a = rr / 8 * 6.28
            m = emissive("crow%d_%d" % (i, rr), (1, 1, 1), 5)
            for j in range(7):
                z = (j / 6 - 0.5) * 0.8
                rad = 0.25 * math.sqrt(max(0, 1 - (z / 0.45) ** 2)) + 0.01
                prim("sphere", c + Vector((math.cos(a) * rad, math.sin(a) * rad, z)), (0.022,) * 3, material=m, segments=6, ring_count=4)
            rows.append(m)
        combs.append(rows)
    sparks = []
    for i in range(50):
        m = emissive("spk%d" % i, cols[i % 4], 0)
        prim("sphere", (rng.uniform(-8, 8), rng.uniform(-3, 10), rng.uniform(-4, 4)), (0.04,) * 3, material=m, segments=6, ring_count=4)
        sparks.append((m, rng.uniform(0, 3), rng.uniform(0.4, 1.2)))

    def up(t):
        a = t * 0.04
        cam.location = Vector((math.sin(a) * 9, -math.cos(a) * 9, 0.3 * math.sin(t * 0.2)))
        aim(cam, (0, 1, 0))
        on = smooth(0.5, 2.5, t)
        for root, bell, tents, r, m, ph in jel:
            update_jelly(root, bell, tents, r, t, ph)
            root.location.z += 0.004 * math.sin(t + ph)
            set_emit(m, 4 * on * (0.7 + 0.3 * math.sin(t * 2.2 + ph)))
        for rows in combs:
            for k, m in enumerate(rows):
                h = (k / 8 + t * 0.5) % 1
                col = (0.5 + 0.5 * math.sin(h * 6.28), 0.5 + 0.5 * math.sin(h * 6.28 + 2.1), 0.5 + 0.5 * math.sin(h * 6.28 + 4.2))
                for n in m.node_tree.nodes:
                    if n.type == "EMISSION":
                        n.inputs[0].default_value = (*col, 1)
                        n.inputs[1].default_value = 6 * on
        for m, ph, sp in sparks:
            x = (t * sp + ph) % 3.0
            set_emit(m, 40 * math.exp(-((x - 0.3) ** 2) / 0.01) * on)
    return up


# ================================================================ 11 сифонофор
def scene_11(ctx):
    sc = reset((0.0, 0.0, 0.006), 0.015, 0.5, (0.3, 0.4, 0.6))
    cam = camera((0, -7, 0.5), (0, 0, 0), lens=35)
    m = mat("siph", (0.4, 0.7, 1.0), 0.2, emit=(0.35, 0.65, 1.0), emit_str=1.2, alpha=0.8)
    beads = [prim("sphere", (0, 0, 0), (0.14, 0.1, 0.1), material=m, segments=12, ring_count=8) for _ in range(40)]
    tm = mat("sipht", (0.3, 0.5, 1.0), 0.3, emit=(0.3, 0.5, 1.0), emit_str=2)
    hangs = [tube("hang", [Vector((0, 0, 0)), Vector((0, 0, -0.6))], [0.01, 0.005], 5, tm) for _ in range(14)]
    pred = whale((0, 6, 1.5), 9, "pred")[0]
    pred.scale = (1, 0.6, 0.6)
    light("AREA", (0, 10, 4), 300, (0.2, 0.4, 0.7), target=(0, 6, 1), size=6)
    f, ft = fish("photo", (1.5, -1, 1.2), 0.6, (0.12, 0.12, 0.15), 0.35, 0.3)
    leds = []
    for k in range(6):
        lm = emissive("ph%d" % k, (0.4, 0.8, 1), 6)
        o = prim("sphere", (0.2 - k * 0.07, -0.05, -0.09), (0.018,) * 3, material=lm, segments=6, ring_count=4)
        o.parent = f
        leds.append(lm)
    sn = Snow(cam, 1500, (10, 10, 8), 0.3, (0.4, 0.5, 0.6), 0.01)

    def up(t):
        for i, b in enumerate(beads):
            u = i / 39
            b.location = (-6 + 12 * u, 0.3 * math.sin(u * 7 + t * 0.5), -0.5 + 0.8 * math.sin(u * 5 + t * 0.6) + 0.3 * math.sin(u * 13 - t))
            set_emit(m, 1.0 + 0.5 * math.sin(t * 2))
        for k, h in enumerate(hangs):
            b = beads[k * 3 % 40].location
            pts = [Vector(b), Vector(b) + Vector((0.1 * math.sin(t + k), 0, -0.6))]
            update_tube(h, pts, [0.01, 0.005], 5)
        pred.location = (-14 + t * 1.6, 6, 1.5)
        f.location = (1.5 + 0.3 * math.sin(t * 0.3), -1, 1.2)
        f.rotation_euler = (0, 0, math.pi + 0.2 * math.sin(t * 0.3))
        wiggle(f, ft, t, 5, 0.3)
        for k, lm in enumerate(leds):
            set_emit(lm, 8 if math.sin(t * 4 + k) > 0 else 0.5)
        sn.update(t)
        cam.location = Vector((0.6 * math.sin(t * 0.1), -7 + 0.05 * t, 0.5))
        aim(cam, (0, 0, 0))
    return up


# ================================================================ 12 кашалот
def scene_12(ctx):
    sc = reset((0.0, 0.005, 0.015), 0.03, 0.6, (0.3, 0.45, 0.6))
    w, tp = whale((0, 0, 0), 12)
    cam = camera((-2, -13, 0.5), (0, 0, 0), lens=30)
    lamp = light("SPOT", (-6, -9, 2), 6000, (0.85, 0.92, 1.0), target=(2, 0, 0), spot=45, blend=0.6, size=0.2)
    light("AREA", (5, 6, 6), 400, (0.3, 0.45, 0.6), target=(0, 0, 0), size=8)
    sn = Snow(cam, 2500, (16, 16, 10), 0.6, (0.6, 0.7, 0.8), 0.015)

    def up(t):
        p = t / ctx.dur
        w.location = (-5 + 0.9 * t, 0, -0.3 - 0.15 * t)
        w.rotation_euler = (0, 0.06, 0)
        tp.rotation_euler = (0, 0.3 * math.sin(t * 0.9), 0)
        cam.location = Vector((-3 + 0.85 * t, -13, 0.6 - 0.12 * t))
        aim(cam, w.location + Vector((2.5, 0, 0)))
        lamp.location = cam.location + Vector((-3, 3, 1.2))
        aim(lamp, w.location + Vector((3, 0, 0)))
        sn.update(t)
    return up


# ================================================================ 13 На кого? — бій кашалота й кальмара
def scene_13(ctx):
    sc = reset((0.0, 0.004, 0.012), 0.035, 0.6, (0.3, 0.4, 0.55))
    w, tp = whale((0, 0, 0), 12)
    sq, arms = squid((4.2, -0.4, 0.4), 1.4)
    sq.rotation_euler = (0, 0, math.pi)
    for k in range(12):
        prim("torus", (2.2 + (k % 4) * 0.5, -1.15, 0.2 - (k // 4) * 0.35), (1, 1, 1), rot=(math.pi / 2, 0, 0),
             material=mat("scar", (0.45, 0.45, 0.45), 0.6), major_radius=0.09, minor_radius=0.015)
    cam = camera((1, -9, 2), (2, 0, 0), lens=30)
    light("SPOT", (-4, -8, 6), 7000, (0.8, 0.9, 1.0), target=(2, 0, 0), spot=40, blend=0.7)
    light("AREA", (6, 4, 3), 500, (0.4, 0.5, 0.7), target=(2, 0, 0), size=6)
    sn = Snow(cam, 2500, (14, 14, 10), 0.6, (0.6, 0.7, 0.8), 0.015)
    cp = Cockpit(ctx, water=(0.0, 0.03, 0.07), darkness=0.75)
    cut = ctx.seg_end(0) + 0.2

    def up(t):
        if t < cut:
            use_cam(cp.cam)
            cp.update(t, push=t / max(cut, 1), extra_brow=0.4)
            return
        use_cam(cam)
        tt = t - cut
        w.rotation_euler = (0.1 * math.sin(tt * 0.8), 0.05 * math.sin(tt * 0.6), 0.15 * math.sin(tt * 0.5))
        tp.rotation_euler = (0, 0.5 * math.sin(tt * 1.6), 0)
        update_arms(arms, tt * 1.4, spread=0.6, curl=-0.9, speed=1.8)
        sq.location = (4.2 + 0.2 * math.sin(tt), -0.4, 0.4 + 0.2 * math.sin(tt * 1.3))
        cam.location = Vector((1 + 0.15 * tt, -9 + 0.1 * tt, 2)) + shake(tt, 0.05)
        aim(cam, (2.5, 0, 0))
        sn.update(t)
    return up


# ================================================================ 14 гігантський кальмар
def scene_14(ctx):
    sc = reset((0.0, 0.003, 0.01), 0.03, 0.6, (0.4, 0.4, 0.5))
    sq, arms = squid((14, 0, 0), 1.3)
    sq.rotation_euler = (0, 0, math.pi)
    cam = camera((-6, -1.5, 0.4), (0, 0, 0), lens=32)
    light("SPOT", (-7, -4, 3), 9000, (0.9, 0.92, 1.0), target=(2, 0, 0), spot=40, blend=0.8)
    light("AREA", (4, 4, 4), 300, (0.5, 0.3, 0.3), target=(4, 0, 0), size=6)
    sn = Snow(cam, 2000, (12, 12, 8), 0.5, (0.6, 0.65, 0.7), 0.012)

    def up(t):
        p = ease(t / ctx.dur)
        # кальмар іде головою вперед (щупальця попереду), до камери
        sq.location = (lerp(14, 3.0, p), 0, 0.2 * math.sin(t * 0.5))
        sq.rotation_euler = (0, 0, math.pi * 0 + math.pi)
        update_arms(arms, t, spread=lerp(0.15, 0.7, p), curl=0.0, speed=1.0)
        sn.update(t)
    return up


# ================================================================ 15 "Титанік" і вудильник
def titanic(o=Vector((0, 0, 0))):
    rust = mat("rust", (0.32, 0.12, 0.05), 0.85, noise=0.8, noise_scale=1.2, bump=0.8)
    bm = bmesh.new()
    prof = [(-22, -1), (-22, 9), (4, 9.5), (8, 10.5), (9, 10.6), (6.5, 3.5), (3, -1)]
    vs_l = [bm.verts.new((x, -1.8, z)) for x, z in prof]
    vs_r = [bm.verts.new((x, 1.8, z)) for x, z in prof]
    n = len(prof)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((vs_l[i], vs_l[j], vs_r[j], vs_r[i]))
    bm.faces.new(vs_l[::-1])
    bm.faces.new(vs_r)
    # звузити ніс
    for v in bm.verts:
        if v.co.x > 0:
            v.co.y *= max(0.05, 1 - v.co.x / 9.5)
    hull = obj_from_bm("titanic", bm, rust, False)
    bv = hull.modifiers.new("B", "BEVEL")
    bv.width = 0.15
    hull.location = o
    rail_m = mat("rail", (0.2, 0.09, 0.05), 0.8, noise=0.6, noise_scale=3)
    pts = [o + Vector((x, -1.75 * max(0.05, 1 - max(x, 0) / 9.5), 10.0 + 0.06 * max(x, 0))) for x in np.linspace(-20, 8.8, 30)]
    tube("railtop", pts, [0.04] * 30, 5, rail_m)
    for x in np.linspace(-20, 8, 30):
        y = -1.75 * max(0.05, 1 - max(x, 0) / 9.5)
        tube("post", [o + Vector((x, y, 9.4)), o + Vector((x, y, 10.0))], [0.025, 0.025], 4, rail_m)
    for x in np.linspace(-18, 0, 12):
        prim("cyl", o + Vector((x, -1.85, 6.2)), (0.18, 0.18, 0.05), rot=(math.pi / 2, 0, 0), material=mat("hole", (0.01, 0.01, 0.01), 0.9), vertices=12)
    # іржаві "бурульки"
    for i in range(40):
        x = random.uniform(-20, 5)
        prim("cone", o + Vector((x, -1.85 * max(0.05, 1 - max(x, 0) / 9.5), random.uniform(4, 9.4))), (0.08, 0.08, random.uniform(0.2, 0.5)),
             rot=(math.pi, 0, 0), material=rust, vertices=6)
    return hull


def anglerfish(name="ang"):
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    m = mat(name + "m", (0.08, 0.07, 0.07), 0.5, noise=0.5, noise_scale=8, bump=0.5)

    def prof(u):
        r = 0.55 * math.sin(math.pi * (0.15 + 0.85 * u) ** 0.6) * (1 - 0.6 * u)
        return (r * 0.8, r, 0)

    b = loft(name + "b", 16, prof, 1.6, 14, m, 1)
    b.parent = root
    tm = mat("tooth", (0.9, 0.88, 0.8), 0.3)
    for k in range(9):
        a = -0.8 + k * 0.2
        th = prim("cone", (0.8, math.sin(a) * 0.35, -0.05 + 0.1 * (k % 2)), (0.03, 0.03, 0.14), rot=(math.pi if k % 2 else 0, 0, 0), material=tm, vertices=6)
        th.parent = root
    rod = tube("rod", [Vector((0.5, 0, 0.45)), Vector((0.8, 0, 0.9)), Vector((1.2, 0, 0.95)), Vector((1.35, 0, 0.8))], [0.02] * 4, 5, m)
    rod.parent = root
    lm = emissive("lure", (0.5, 1.0, 0.85), 30)
    lure = prim("sphere", (1.37, 0, 0.75), (0.07,) * 3, material=lm)
    lure.parent = root
    L = light("POINT", (0, 0, 0), 25, (0.4, 1.0, 0.8), size=0.05)
    L.parent = root
    L.location = (1.37, 0, 0.72)
    for sy in (-1, 1):
        e = prim("sphere", (0.55, sy * 0.3, 0.2), (0.05,) * 3, material=mat("aeye", (0.4, 0.4, 0.3), 0.1, coat=1))
        e.parent = root
    return root


def scene_15(ctx):
    sc = reset((0.0, 0.006, 0.012), 0.035, 0.6, (0.35, 0.45, 0.5))
    seabed(loc=(0, 0, -1.2), amp=0.3)
    titanic(Vector((0, 4, -1.5)))
    light("SPOT", (-6, -14, 14), 30000, (0.85, 0.92, 1.0), target=(0, 4, 5), spot=45, blend=0.7)
    light("AREA", (10, -6, 6), 800, (0.3, 0.45, 0.6), target=(4, 4, 4), size=10)
    cam = camera((-12, -16, 4), (0, 4, 5), lens=32)
    sn = Snow(cam, 2500, (16, 16, 10), 0.6, (0.6, 0.65, 0.7), 0.015)
    ang = anglerfish()

    def up(t):
        p = t / ctx.dur
        cam.location = Vector((lerp(-14, 2, ease(p)), -16, 4 + 0.5 * math.sin(t * 0.2)))
        aim(cam, (lerp(-6, 6, ease(p)), 4, 5))
        k = smooth(0.45, 1.0, p)
        cf = cam.matrix_world
        ang.location = cf @ Vector((lerp(3, -3, k), -0.3, -4))
        ang.rotation_euler = cam.rotation_euler.copy()
        ang.rotation_euler.rotate_axis("Y", 0)
        ang.rotation_euler = (math.pi / 2, 0, cam.rotation_euler.z + math.pi)
        ang.hide_render = k <= 0
        for ch in ang.children:
            ch.hide_render = k <= 0
        sn.update(t)
    return up


# ================================================================ 16 абісальна рівнина
def scene_16(ctx):
    sc = reset((0.0, 0.005, 0.01), 0.03, 0.6, (0.35, 0.4, 0.45))
    seabed(loc=(0, 0, 0), amp=0.15, size=90)
    rng = random.Random(16)
    cuc = mat("cucumber", (0.75, 0.35, 0.4), 0.3, sss=0.4, alpha=0.85, noise=0.3, noise_scale=10)
    sponge = mat("sponge", (0.85, 0.85, 0.8), 0.2, alpha=0.5, emit=(0.3, 0.3, 0.3), emit_str=0.2)
    objs = []
    for i in range(26):
        x, y = rng.uniform(-6, 6), rng.uniform(2, 60)
        kind = i % 3
        if kind == 0:
            def prof(u):
                r = 0.18 * math.sin(math.pi * (0.05 + 0.9 * u)) + 0.02
                return (r, r * 0.7, 0)
            o = loft("cuc", 12, prof, 0.8, 10, cuc, 1)
            o.location = (x, y, 0.15)
            o.rotation_euler = (0, 0, rng.uniform(0, 6))
        elif kind == 1:
            o = prim("cyl", (x, y, 0.5), (0.18, 0.18, 0.5), material=sponge, vertices=16)
        else:
            o, _ = fish("tri%d" % i, (x, y, 0.55), 0.5, (0.65, 0.65, 0.6), 0.25, 0.3)
            for dx, dy in ((-0.15, 0.08), (-0.15, -0.08), (0.15, 0)):
                tb = tube("leg", [Vector((dx, dy, -0.02)), Vector((dx * 1.3, dy * 1.3, -0.55))], [0.006, 0.004], 4, bpy.data.materials["tri%dm" % i])
                tb.parent = o
        objs.append(o)
    cam = camera((0, -2, 0.9), (0, 10, 0.2), lens=28)
    sp = light("SPOT", (0, 0, 2), 4000, (0.9, 0.95, 1.0), spot=55, blend=0.7)
    sn = Snow(cam, 2000, (12, 12, 8), 0.4, (0.6, 0.65, 0.7), 0.012)

    def up(t):
        cam.location = Vector((0.4 * math.sin(t * 0.15), -2 + 1.3 * t, 0.9 + 0.1 * math.sin(t * 0.3)))
        aim(cam, cam.location + Vector((0, 10, -0.8)))
        sp.location = cam.location + Vector((0, 0.5, 1.2))
        aim(sp, cam.location + Vector((0, 8, -1)))
        sn.update(t)
    return up


# ================================================================ 17 ізопод і туша кита
def scene_17(ctx):
    sc = reset((0.0, 0.005, 0.01), 0.03, 0.6, (0.35, 0.4, 0.45))
    seabed(loc=(0, 0, 0), amp=0.12)
    shell = mat("isopod", (0.62, 0.55, 0.45), 0.4, noise=0.4, noise_scale=20, bump=0.4, coat=0.3)
    iso = bpy.data.objects.new("iso", None)
    bpy.context.scene.collection.objects.link(iso)
    legs = []
    for s_ in range(9):
        u = s_ / 8
        w = 0.17 * math.sin(math.pi * (0.15 + 0.7 * u))
        seg = prim("sphere", (0.25 - u * 0.5, 0, 0.06), (0.04, w, 0.07), material=shell)
        seg.parent = iso
        for sy in (-1, 1):
            lg = tube("lg", [Vector((0.25 - u * 0.5, sy * w * 0.8, 0.03)), Vector((0.25 - u * 0.5, sy * (w + 0.05), -0.04))], [0.006, 0.004], 4, shell)
            lg.parent = iso
            legs.append((lg, u, sy, w))
    for sy in (-1, 1):
        an = tube("ant", [Vector((0.28, sy * 0.04, 0.08)), Vector((0.4, sy * 0.1, 0.12)), Vector((0.5, sy * 0.2, 0.1))], [0.005, 0.004, 0.002], 4, shell)
        an.parent = iso
        e = prim("sphere", (0.27, sy * 0.07, 0.1), (0.015,) * 3, material=mat("isoeye", (0.05, 0.05, 0.05), 0.1, coat=1))
        e.parent = iso
    wc, _ = whale((3.0, 3.0, 0.2), 6, "carcass")
    wc.rotation_euler = (math.pi / 2 * 0.9, 0, 0.4)
    bone = mat("bone", (0.85, 0.82, 0.74), 0.5)
    for k in range(8):
        prim("torus", (1.8 + k * 0.35, 2.4, 0.5), (1, 1, 1), rot=(0, math.pi / 2, 0.4), material=bone, major_radius=0.55, minor_radius=0.04)
    hag = mat("hag", (0.5, 0.35, 0.35), 0.4, sss=0.3)
    hags = [tube("hagf", [Vector((0, 0, 0)) for _ in range(8)], [0.03] * 8, 6, hag) for _ in range(5)]
    cam = camera((-0.8, -1.2, 0.18), (1, 1.5, 0.2), lens=30)
    light("SPOT", (-1, -2, 2), 1500, (0.9, 0.95, 1.0), target=(0.8, 1.2, 0), spot=60, blend=0.7)
    light("AREA", (4, 0, 3), 200, (0.3, 0.4, 0.55), target=(2, 2, 0), size=4)
    sn = Snow(cam, 1500, (8, 8, 6), 0.4, (0.6, 0.65, 0.7), 0.008)

    def up(t):
        p = t / ctx.dur
        iso.location = (lerp(-0.2, 0.9, p), lerp(-0.1, 0.8, p), 0)
        iso.rotation_euler = (0, 0, 0.75)
        for k, h in enumerate(hags):
            base = Vector((2.0 + k * 0.4, 2.2, 0.3))
            pts = [base + Vector((-0.12 * j, 0.1 * math.sin(t * 3 + j * 0.8 + k), 0.05 * math.sin(t * 2 + j))) for j in range(8)]
            update_tube(h, pts, [0.03] * 8, 6)
        sn.update(t)
        cam.location = Vector((-0.8 + 0.3 * p, -1.2 + 0.2 * p, 0.18))
    return up


# ================================================================ 18 "послухайте" — Блуп
def scene_18(ctx):
    sc = reset((0.0, 0.005, 0.015), 0.03, 0.6, (0.3, 0.45, 0.6))
    seabed(loc=(0, 0, -3), amp=0.2)
    dark = mat("hyd", (0.08, 0.09, 0.1), 0.4, metal=0.7)
    for a in range(3):
        an = a / 3 * 6.28
        tube("tri", [Vector((-3, 2, -0.5)), Vector((-3 + math.cos(an) * 0.9, 2 + math.sin(an) * 0.9, -3))], [0.04, 0.04], 6, dark)
    prim("cyl", (-3, 2, -0.2), (0.15, 0.15, 0.4), material=dark, vertices=16)
    red = emissive("redled", (1, 0.1, 0.05), 30)
    prim("sphere", (-3, 2, 0.25), (0.04,) * 3, material=red)
    rings = []
    for k in range(5):
        m = emissive("ring%d" % k, (0.3, 0.7, 1.0), 3)
        r = prim("torus", (8, 30, 0), (1, 1, 1), rot=(math.pi / 2, 0, 0), material=m, major_radius=1.0, minor_radius=0.04)
        rings.append((r, m))
    cam = camera((-5, -4, -1.6), (2, 20, 0), lens=30)
    light("AREA", (-3, -2, 3), 300, (0.4, 0.6, 0.8), target=(-3, 2, -1), size=4)
    sn = Snow(cam, 1800, (12, 12, 8), 0.4, (0.5, 0.6, 0.7), 0.012)
    cp = Cockpit(ctx, water=(0.0, 0.025, 0.06), darkness=0.8)
    cut = ctx.seg_end(0) + 0.3

    def up(t):
        if t < cut:
            use_cam(cp.cam)
            cp.update(t, push=0.3, look=(-0.2, 0.0), extra_brow=0.3)
            return
        use_cam(cam)
        tt = t - cut
        for k, (r, m) in enumerate(rings):
            ph = (tt * 4 + k * 7) % 35
            r.scale = (ph, ph, ph * 0.6)
            set_emit(m, 4 * max(0, 1 - ph / 35))
        set_emit(red, 30 if (tt % 1.5) < 0.2 else 2)
        cam.location = Vector((-5 + 0.1 * tt, -4, -1.6))
        aim(cam, (2, 20, 0))
        sn.update(t)
    return up


# ================================================================ 19 лід Антарктиди
def scene_19(ctx):
    sc = reset((0.02, 0.12, 0.2), 0.03, 0.7, (0.4, 0.7, 0.9))
    ice = mat("ice", (0.6, 0.85, 0.95), 0.15, sss=0.5, emit=(0.3, 0.55, 0.7), emit_str=0.4, noise=0.3, noise_scale=0.5, bump=0.4)
    shelf = terrain("shelf", 80, 120, 1.2, 19, ice, 4.0, (0, 0, 6))
    shelf.rotation_euler = (math.pi, 0, 0)
    top = light("AREA", (0, 0, 3), 30000, (0.6, 0.85, 1.0), rot=(math.pi, 0, 0), size=40)
    top.rotation_euler = (0, 0, 0)
    top.location = (0, 0, 4.5)
    rng = random.Random(19)
    blocks = []
    for i in range(10):
        b = prim("cube", (0, 0, 0), (rng.uniform(0.8, 2.2), rng.uniform(0.6, 1.6), rng.uniform(0.5, 1.4)), material=ice)
        bv = b.modifiers.new("B", "BEVEL")
        bv.width = 0.15
        d = b.modifiers.new("D", "DISPLACE")
        tx = bpy.data.textures.new("ic%d" % i, "CLOUDS")
        tx.noise_scale = 0.6
        d.texture = tx
        d.strength = 0.25
        b.modifiers.new("S", "SUBSURF").levels = 1
        blocks.append((b, rng.uniform(-6, 6), rng.uniform(4, 14), rng.uniform(0, 0.6), rng.uniform(-1, 1)))
    cam = camera((0, -8, 3), (0, 6, 2), lens=28)
    light("AREA", (0, -10, -4), 3000, (0.3, 0.6, 0.9), target=(0, 6, 0), size=10)
    sn = Snow(cam, 700, (14, 14, 10), 0.12, (0.8, 0.9, 1.0), 0.01)

    def up(t):
        p = t / ctx.dur
        for b, x, y, t0, sp in blocks:
            tt = max(0, t - t0 * ctx.dur)
            b.location = (x + sp * tt * 0.4, y, 5 - 0.5 * tt * tt * 0.6 - 0.3 * tt)
            b.rotation_euler = (sp * tt * 0.3, sp * tt * 0.2, 0)
        cam.location = Vector((0, -8 + p, 3 - 9 * ease(p)))
        aim(cam, (0, 8, lerp(2, -6, ease(p))))
        sn.update(t)
    return up


# ================================================================ 20 хадаль: ущелина + ведучий
def scene_20(ctx):
    sc = reset((0.0, 0.002, 0.005), 0.03, 0.5, (0.3, 0.35, 0.4))
    rock = mat("rock20", (0.16, 0.15, 0.14), 0.9, noise=0.6, noise_scale=1.2, bump=0.8)
    for sx in (-1, 1):
        w = terrain("wall", 60, 140, 0.9, 20 + sx, rock, 2.5, (0, 0, 0))
        w.rotation_euler = (0, -sx * math.pi / 2, 0)
        w.location = (sx * 3.6, 0, -25)
    cam = camera((0, -6, 0), (0, 0, -6), lens=26)
    sp = light("SPOT", (0, -5, 0), 9000, (0.9, 0.95, 1.0), spot=80, blend=0.8)
    redl = light("POINT", (0, -5, 0), 0, (1, 0.1, 0.05), size=0.05)
    sn = Snow(cam, 2000, (10, 10, 10), 0.4, (0.6, 0.65, 0.7), 0.012, vel=(0, 0, 0.6))
    cp = Cockpit(ctx, water=(0.0, 0.01, 0.03), darkness=0.9)
    pres = (ctx.seg(2) - 0.2, ctx.seg_end(3) + 0.4)

    def up(t):
        if pres[0] <= t <= pres[1]:
            use_cam(cp.cam)
            cp.update(t, push=(t - pres[0]) / (pres[1] - pres[0]))
            return
        use_cam(cam)
        z = -1.6 * t
        cam.location = Vector((0.3 * math.sin(t * 0.2), -6, z))
        aim(cam, (0, 0, z - 6))
        sp.location = cam.location + Vector((0, 0.3, 0.5))
        aim(sp, (0, 0, z - 8))
        redl.location = cam.location + Vector((0.4, 0.8, -0.3))
        redl.data.energy = 30 if (t % 1.6) < 0.25 else 0
        sn.update(t)
    return up


# ================================================================ 21 риба-равлик
def scene_21(ctx):
    sc = reset((0.0, 0.004, 0.008), 0.03, 0.6, (0.35, 0.4, 0.45))
    seabed(loc=(0, 0, -0.6), amp=0.08)
    pink = mat("snail", (0.95, 0.72, 0.75), 0.25, sss=0.6, alpha=0.6, emit=(0.25, 0.12, 0.13), emit_str=0.3)

    def prof(u):
        r = 0.16 * (1 - u) ** 0.8 * math.sin(math.pi * min(1, 0.15 + u * 1.5)) + 0.008
        return (r * 0.8, r, 0)

    f = loft("snailfish", 22, prof, 1.0, 14, pink, 1)
    org = [prim("sphere", (0.18, 0, -0.02), (0.06, 0.04, 0.045), material=mat("org1", (0.7, 0.2, 0.25), 0.4)),
           prim("sphere", (0.08, 0, -0.04), (0.05, 0.035, 0.035), material=mat("org2", (0.8, 0.5, 0.3), 0.4)),
           prim("sphere", (0.36, 0.06, 0.03), (0.018,) * 3, material=mat("seye", (0.02, 0.02, 0.03), 0.1, coat=1)),
           prim("sphere", (0.36, -0.06, 0.03), (0.018,) * 3, material=bpy.data.materials["seye"])]
    for o in org:
        o.parent = f
    wire = mat("cage", (0.5, 0.5, 0.52), 0.4, metal=0.9)
    cx, cy = 1.2, 0.9
    for a in range(6):
        x = cx - 0.3 + a * 0.12
        tube("cg", [Vector((x, cy - 0.3, -0.55)), Vector((x, cy - 0.3, 0.0))], [0.006] * 2, 4, wire)
    for z in (-0.55, -0.27, 0.0):
        tube("cg", [Vector((cx - 0.3, cy - 0.3, z)), Vector((cx + 0.3, cy - 0.3, z))], [0.006] * 2, 4, wire)
    cam = camera((0, -2.4, 0.2), (0, 0, 0), lens=40)
    light("SPOT", (-1, -2.5, 2), 1500, (0.95, 0.97, 1.0), target=(0, 0, 0), spot=50, blend=0.8)
    light("AREA", (1.5, 1, 1), 60, (0.5, 0.6, 0.8), target=(0, 0, 0), size=2)
    sn = Snow(cam, 1500, (6, 6, 5), 0.4, (0.7, 0.72, 0.75), 0.006)

    def up(t):
        p = ease(t / ctx.dur)
        f.location = (0.1 * math.sin(t * 0.3), 0, 0.05 * math.sin(t * 0.5))
        f.rotation_euler = (0, 0.05 * math.sin(t * 0.7), math.pi * 0.15 + 0.08 * math.sin(t * 0.4))
        cam.location = Vector((0.1 * math.sin(t * 0.2), lerp(-2.4, -1.4, p), 0.2))
        aim(cam, f.location)
        sn.update(t)
    return up


# ================================================================ 22 бокоплави і ксенофіофор
def scene_22(ctx):
    sc = reset((0.0, 0.003, 0.006), 0.03, 0.6, (0.35, 0.38, 0.4))
    seabed(loc=(0, 0, -0.3), amp=0.05)
    bait = prim("sphere", (0, 0, -0.2), (0.3, 0.18, 0.12), material=mat("bait", (0.55, 0.3, 0.25), 0.5, noise=0.5, noise_scale=10, bump=0.4))
    pale = mat("amph", (0.85, 0.8, 0.72), 0.35, sss=0.3)
    rng = random.Random(22)
    amph = []
    for i in range(70):
        def prof(u):
            r = 0.012 * math.sin(math.pi * (0.1 + 0.8 * u)) + 0.002
            return (r, r * 1.3, 0.01 * math.sin(u * 3.14))
        a = loft("am", 8, prof, 0.06, 6, pale, 0)
        amph.append((a, rng.uniform(0, 6.28), rng.uniform(0.1, 0.45), rng.uniform(-0.2, 0.15), rng.uniform(0.6, 1.6)))
    # ксенофіофор — окрема "макро" декорація
    o2 = Vector((40, 0, 0))
    seabed(loc=o2 + Vector((0, 0, -0.1)), amp=0.03, size=10, res=80, seed=5)
    xe = prim("ico", o2 + Vector((0, 0, 0.0)), (0.12, 0.11, 0.08), material=mat("xeno", (0.75, 0.68, 0.55), 0.8, noise=0.6, noise_scale=40, bump=1.0), subdivisions=5)
    tx = bpy.data.textures.new("xen", "CLOUDS")
    tx.noise_scale = 0.03
    d = xe.modifiers.new("D", "DISPLACE")
    d.texture = tx
    d.strength = 0.04
    cam = camera((0, -1.2, 0.35), (0, 0, -0.2), lens=35)
    cam2 = camera(o2 + Vector((0.05, -0.45, 0.15)), o2, lens=50)
    use_cam(cam)
    light("SPOT", (0.3, -1.2, 1.2), 900, (0.95, 0.97, 1.0), target=(0, 0, -0.2), spot=45, blend=0.8)
    light("SPOT", o2 + Vector((-0.4, -0.6, 0.6)), 300, (0.95, 0.95, 1.0), target=o2, spot=45, blend=0.8)
    sn = Snow(cam, 800, (4, 4, 3), 0.3, (0.7, 0.72, 0.75), 0.004)
    cut = 0.55 * ctx.dur

    def up(t):
        if t < cut:
            use_cam(cam)
            for a, ph, r, z, sp in amph:
                ang = ph + t * sp * 2
                rr = r * (1 + 0.2 * math.sin(t * 3 + ph))
                a.location = (math.cos(ang) * rr, math.sin(ang) * rr * 0.6, -0.15 + z * 0.3 + 0.03 * math.sin(t * 5 + ph))
                a.rotation_euler = (0, 0, ang + math.pi / 2)
            sn.update(t)
        else:
            use_cam(cam2)
            k = (t - cut) / (ctx.dur - cut)
            cam2.location = o2 + Vector((0.05, lerp(-0.45, -0.33, k), 0.15))
            aim(cam2, o2)
    return up


# ================================================================ 23 ведучий + палуба 1960
def scene_23(ctx):
    sc = reset((0.75, 0.72, 0.62), 0.0, strength=1.0)
    sea_m = mat("sea23", (0.08, 0.12, 0.13), 0.12, coat=0.4)
    from scenes3d import ocean_surface as _os
    sea, md = _os(300, 10, sea_m, (0, 0, 0), 1.0, 1.0)
    tr, _ = trieste((0, 0, -0.9), 1.0, light_on=False)
    men = []
    for k, x in enumerate((-0.6, 0.6)):
        c = Character("Deck%d" % k, skin=(0.55, 0.36, 0.26), hair=(0.06, 0.05, 0.04), shirt=(0.75, 0.73, 0.68) if k else (0.15, 0.18, 0.25),
                      shirt2=(0.15, 0.15, 0.15), loc=(x, -0.2, 1.75), headset=False)
        c.root.scale = (2.2, 2.2, 2.2)
        legs = prim("cube", (x, -0.2, 1.2), (0.25, 0.12, 0.55), material=mat("pants%d" % k, (0.12, 0.12, 0.13), 0.7), smooth=False)
        men.append(c)
    light("SUN", (0, 0, 10), 3.0, (1.0, 0.92, 0.78), rot=(math.radians(45), 0, math.radians(30)))
    cam = camera((6, -14, 3), (0, 0, 1.5), lens=40)
    cp = Cockpit(ctx, water=(0.0, 0.01, 0.03), darkness=0.85)
    cut = ctx.seg_end(0) + 0.3

    def up(t):
        md.time = t
        if t < cut:
            use_cam(cp.cam)
            cp.update(t, push=t / cut)
            return
        use_cam(cam)
        tt = t - cut
        cam.location = Vector((6 - 0.35 * tt, -14, 3))
        aim(cam, (0, 0, 1.6))
        tr.location = (0, 0, -0.9 + 0.12 * math.sin(t * 0.9))
        tr.rotation_euler = (0.02 * math.sin(t * 0.7), 0, 0)
        for k, m in enumerate(men):
            m.root.location.z = 1.75 + 0.12 * math.sin(t * 0.9)
            m.pose_head(0.3 * math.sin(t * 0.3 + k), 0, 0)
            m.face(blink=1.0 if (t + k) % 3.1 < 0.12 else 0, smile=0.3)
    return up


# ================================================================ 24 розріз "Трієста"
def scene_24(ctx):
    sc = reset((0.0, 0.015, 0.035), 0.025, 0.6, (0.3, 0.5, 0.65))
    tr, _ = trieste((0, 0, 0), 1.0, light_on=False)
    flm = mat("glassfloat", (0.5, 0.6, 0.65), 0.1, alpha=0.25)
    for ch in tr.children:
        if ch.name.startswith("Trfloat"):
            ch.data.materials.clear()
            ch.data.materials.append(flm)
    gas = mat("gas", (0.85, 0.65, 0.15), 0.3, emit=(0.6, 0.4, 0.05), emit_str=0.6)
    for k in range(6):
        prim("cyl", (-5 + k * 2.0, 0, 1.6), (0.75, 0.75, 0.85), rot=(0, math.pi / 2, 0), material=gas, vertices=24)
    arrows = []
    for k in range(14):
        a = k / 14 * 2 * math.pi
        m = emissive("arr%d" % k, (1, 0.25, 0.15), 5)
        d = Vector((math.cos(a), 0, math.sin(a)))
        c = Vector((0, -0.2, -0.9)) + d * 2.0
        shaft = tube("ar", [c, c - d * 0.6], [0.04, 0.04], 6, m)
        head = prim("cone", c - d * 0.75, (0.12, 0.12, 0.18), material=m, vertices=12)
        head.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        arrows.append((shaft, head, m))
    light("AREA", (-6, -10, 6), 3000, (0.7, 0.85, 1.0), target=(0, 0, 0), size=8)
    light("AREA", (6, 8, 2), 1000, (0.4, 0.6, 0.9), target=(0, 0, 0), size=6)
    cam = camera((0, -16, 1), (0, 0, 0.3), lens=32)
    sn = Snow(cam, 1500, (14, 14, 10), 0.4, (0.6, 0.7, 0.8), 0.012, vel=(0, 0, 0.4))

    def up(t):
        p = t / ctx.dur
        a = -0.55 + 0.9 * p
        cam.location = Vector((math.sin(a) * 16, -math.cos(a) * 16, 1.5 - 0.6 * p))
        aim(cam, (0, 0, 0.2))
        for shaft, head, m in arrows:
            set_emit(m, 3 + 3 * math.sin(t * 3))
        sn.update(t)
    return up


# ================================================================ 25 тріснуло зовнішнє вікно
def scene_25(ctx):
    sc = reset((0.0, 0.003, 0.008), 0.03, 0.6, (0.3, 0.4, 0.5))
    hull = mat("hull25", (0.18, 0.18, 0.19), 0.5, metal=0.7, noise=0.5, noise_scale=4, bump=0.3)
    prim("cube", (0, 0.1, 0), (2, 0.05, 2), material=hull, smooth=False)
    for k in range(12):
        a = k / 12 * 6.28
        prim("cyl", (math.cos(a) * 0.43, 0.02, math.sin(a) * 0.43), (0.03, 0.03, 0.04), rot=(math.pi / 2, 0, 0), material=mat("bolt", (0.4, 0.4, 0.42), 0.3, metal=1), vertices=8)
    show = crack_window(Vector((0, 0, 0)), (math.pi / 2, 0, 0), 0.35, "w25")
    lamp = light("SPOT", (0.6, -1.0, 0.8), 600, (0.95, 0.95, 1.0), target=(0, 0, 0), spot=50, blend=0.7)
    cam = camera((0.05, -1.35, 0.1), (0, 0, 0), lens=35)
    c0 = cam.location.copy()
    sn = Snow(cam, 1200, (4, 4, 4), 0.4, (0.6, 0.7, 0.8), 0.006)
    hit = ctx.seg(0) + 0.15 * ctx.dur
    shards = []
    rng = random.Random(25)
    sm = mat("shard", (0.7, 0.85, 0.9), 0.05, emit=(0.4, 0.6, 0.7), emit_str=1)
    for i in range(25):
        s_ = prim("ico", (0, 0, 0), (0.01,) * 3, material=sm, subdivisions=1)
        s_.hide_render = True
        shards.append((s_, Vector((rng.uniform(-1, 1), rng.uniform(-1.2, -0.3), rng.uniform(-1, 1))) * 0.25))

    def up(t):
        k = smooth(hit, hit + 0.1, t) * (1 - smooth(hit + 0.1, hit + 3, t))
        cam.location = c0 + shake(t, 0.03 * k) + Vector((0, 0, 0))
        show((t - hit) / 1.5)
        for s_, v in shards:
            dt = t - hit
            s_.hide_render = dt < 0 or dt > 3
            if dt >= 0:
                s_.location = v * dt + Vector((0, 0, -0.05 * dt * dt))
        sn.vel = Vector((0, 0, 0.3 * smooth(hit + 2, hit + 4, t)))
        sn.update(t)
    return up


# ================================================================ 26 посадка на дно, хмара мулу
def scene_26(ctx):
    sc = reset((0.0, 0.003, 0.006), 0.03, 0.6, (0.35, 0.38, 0.4))
    seabed(loc=(0, 0, -3), amp=0.15, size=60)
    tr, lights = trieste((0, 0, 8), 1.0)
    silt = prim("cube", (0, 0, -2.5), (1, 1, 1), material=None, smooth=False)
    vm = bpy.data.materials.new("silt")
    vm.use_nodes = True
    nt = vm.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    vs = nt.nodes.new("ShaderNodeVolumeScatter")
    vs.inputs["Color"].default_value = (0.55, 0.5, 0.42, 1)
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.5
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 0.0
    nt.links.new(nz.outputs["Fac"], mul.inputs[0])
    nt.links.new(mul.outputs[0], vs.inputs["Density"])
    nt.links.new(vs.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    silt.data.materials.append(vm)
    light("AREA", (-6, -8, 4), 1200, (0.6, 0.7, 0.8), target=(0, 0, 0), size=8)
    cam = camera((-9, -12, 0), (0, 0, 0), lens=30)
    sn = Snow(cam, 1500, (14, 14, 10), 0.4, (0.6, 0.65, 0.7), 0.012)
    land = 0.42 * ctx.dur

    def up(t):
        p = min(1, t / land)
        z = lerp(6, -1.9, ease(p))
        tr.location = (0, 0, z)
        cam.location = Vector((-9, -12, z * 0.5 + 0.5))
        aim(cam, (0, 0, z - 0.5))
        k = smooth(land - 0.2, land + 4, t)
        silt.scale = (1 + 9 * k, 1 + 9 * k, 0.6 + 3 * k)
        silt.location = (0, 0, -2.6 + 1.2 * k)
        mul.inputs[1].default_value = 3.5 * smooth(land - 0.3, land + 0.5, t) * (1 - 0.4 * k)
        sn.update(t)
    return up


# ================================================================ 27 "риба" Пікара: погляд в ілюмінатор + ведучий
def scene_27(ctx):
    sc = reset((0.02, 0.018, 0.012), 0.12, 0.3, (0.55, 0.5, 0.4))
    seabed(loc=(0, 3, -1.2), amp=0.08, size=30)
    shape = loft("flat", 14, lambda u: (0.25 * math.sin(math.pi * (0.1 + 0.9 * u)) + 0.02, 0.06, 0), 1.2, 10,
                 mat("flatfish", (0.6, 0.55, 0.45), 0.6), 1)
    shape.location = (0.2, 3.5, -1.1)
    inner = mat("inner27", (0.05, 0.05, 0.06), 0.5, metal=0.6)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    ring = prim("torus", (0, 0.0, 0), (1, 1, 1), rot=(math.pi / 2, 0, 0), material=mat("brass27", (0.35, 0.28, 0.16), 0.35, metal=1), major_radius=0.25, minor_radius=0.06)
    wall = prim("cube", (0, 0.03, 0), (3, 0.02, 3), material=inner, smooth=False)
    hole = wall.modifiers.new("hole", "BOOLEAN")
    cutter = prim("cyl", (0, 0.03, 0), (0.24, 0.24, 0.2), rot=(math.pi / 2, 0, 0), vertices=40)
    hole.object = cutter
    cutter.hide_render = True
    light("SPOT", (0, 0.5, 1.5), 900, (0.9, 0.9, 0.85), target=(0.2, 3.5, -1.2), spot=40, blend=0.8)
    light("POINT", (0.3, -0.6, 0.3), 3, (1, 0.7, 0.4), size=0.05)
    cam = camera((0.0, -0.6, 0.0), (0, 2, -0.5), lens=30)
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 3.5
    cam.data.dof.aperture_fstop = 1.4
    cp = Cockpit(ctx, water=(0.03, 0.025, 0.015), darkness=0.7)
    pres = ctx.seg(2) - 0.2

    def up(t):
        if t >= pres:
            use_cam(cp.cam)
            cp.update(t, push=(t - pres) / (ctx.dur - pres))
            return
        use_cam(cam)
        cam.location = Vector((0.02 * math.sin(t * 0.5), -0.6 + 0.02 * t, 0.0))
        sc.world.node_tree.nodes["VOL"].inputs["Density"].default_value = 0.12 + 0.08 * t / pres
    return up


# ================================================================ 28 Deepsea Challenger
def scene_28(ctx):
    sc = reset((0.0, 0.002, 0.004), 0.03, 0.6, (0.35, 0.37, 0.4))
    seabed(material=mat("moonbed", (0.42, 0.42, 0.4), 0.95, noise=0.4, noise_scale=2, bump=0.5), loc=(0, 0, -14), amp=0.3, size=80)
    green = mat("dsc", (0.45, 0.75, 0.05), 0.35, coat=0.5)

    def prof(u):
        r = 0.55 * math.sin(math.pi * min(1, 0.06 + u)) ** 0.4
        return (r * 0.7, r, 0)

    dsc = loft("dsc", 20, prof, 7.3, 16, green, 1)
    dsc.rotation_euler = (0, math.pi / 2, 0)
    bulb = emissive("dscb", (1, 0.97, 0.9), 40)
    root = bpy.data.objects.new("dscr", None)
    bpy.context.scene.collection.objects.link(root)
    dsc.parent = root
    boom = prim("cube", (0, 0, -1.8), (1.4, 0.08, 0.08), material=mat("boom", (0.85, 0.85, 0.8), 0.4), smooth=False)
    boom.parent = root
    for sx in (-1.3, 1.3):
        b = prim("sphere", (sx, -0.1, -1.85), (0.1,) * 3, material=bulb)
        b.parent = root
        L = light("SPOT", (0, 0, 0), 5000, (1, 0.97, 0.9), spot=55, blend=0.7)
        L.parent = root
        L.location = (sx, -0.2, -1.9)
        L.rotation_euler = (math.radians(170), 0, 0)
    cam = camera((-4, -9, 0), (0, 0, 0), lens=30)
    sn = Snow(cam, 2000, (14, 14, 12), 0.5, (0.6, 0.65, 0.7), 0.012)

    def up(t):
        p = t / ctx.dur
        z = lerp(4, -9.5, ease(p))
        root.location = (0, 0, z)
        root.rotation_euler = (0, 0, 0.15 * t)
        cam.location = Vector((-5 - 2 * p, -10 - 2 * p, z + 1.0 + 1.5 * p))
        aim(cam, (0, 0, z - 1.5 - 2.0 * p))
        sn.update(t)
    return up


# ================================================================ 29 Limiting Factor + ведучий
def scene_29(ctx):
    sc = reset((0.0, 0.002, 0.004), 0.03, 0.6, (0.35, 0.37, 0.4))
    seabed(material=mat("bed29", (0.38, 0.37, 0.35), 0.95, noise=0.4, noise_scale=2, bump=0.4), loc=(0, 0, -3), amp=0.1, size=60)
    sub, lights = sub_white((0, 0, 4), 1.0)
    bag = prim("plane", (5, 2, -2.95), (0.6, 0.4, 1), material=mat("bag29", (0.9, 0.92, 0.95), 0.3, alpha=0.7))
    cam = camera((-6, -9, 0.5), (0, 0, -1), lens=30)
    light("AREA", (-5, -6, 4), 500, (0.5, 0.6, 0.75), target=(0, 0, -1), size=6)
    sn = Snow(cam, 1800, (14, 14, 10), 0.5, (0.6, 0.65, 0.7), 0.012)
    cp = Cockpit(ctx, water=(0.0, 0.005, 0.015), darkness=0.95)
    pres = (ctx.seg(1) - 0.2, ctx.seg_end(2) + 0.4)

    def up(t):
        if pres[0] <= t <= pres[1]:
            use_cam(cp.cam)
            cp.update(t, push=(t - pres[0]) / (pres[1] - pres[0]), smile=0.0)
            return
        use_cam(cam)
        p = t / ctx.dur
        sub.location = (0, 0, lerp(3, -1.8, ease(min(1, t / (pres[0] + 0.01)))))
        sw = 0.4 * math.sin(t * 0.8)
        if t > pres[1]:
            sw = 0.65
        sub.rotation_euler = (0, 0, sw)
        cam.location = Vector((-6 + 0.2 * t, -9, 0.5 - 0.1 * t))
        aim(cam, sub.location + Vector((1.5, 0.5, -0.5)))
        sn.update(t)
    return up


# ================================================================ 30 пакет на дні
def scene_30(ctx):
    sc = reset((0.0, 0.002, 0.004), 0.03, 0.6, (0.35, 0.37, 0.4))
    seabed(material=mat("bed30", (0.4, 0.38, 0.35), 0.95, noise=0.4, noise_scale=3, bump=0.5), loc=(0, 0, -0.05), amp=0.03, size=20)
    bpy.ops.mesh.primitive_plane_add(size=1.2, location=(0, 0, 0.05))
    bag = bpy.context.object
    bag.scale = (1.0, 0.7, 1)
    sub = bag.modifiers.new("S", "SUBSURF")
    sub.subdivision_type = "SIMPLE"
    sub.levels = 6
    sub.render_levels = 6
    tx = bpy.data.textures.new("bagw", "CLOUDS")
    tx.noise_scale = 0.12
    d = bag.modifiers.new("D", "DISPLACE")
    d.texture = tx
    d.strength = 0.12
    bag.modifiers.new("S2", "SUBSURF").levels = 1
    bag.data.materials.append(mat("bag", (0.92, 0.93, 0.95), 0.25, alpha=0.6, sss=0.2))
    bpy.ops.object.shade_smooth()
    rng = random.Random(30)
    for k, col in enumerate(((0.8, 0.05, 0.1), (0.95, 0.75, 0.05), (0.1, 0.35, 0.9))):
        w = prim("cube", (rng.uniform(-0.8, 0.8), rng.uniform(-0.6, 0.2), 0.03), (0.09, 0.04, 0.01), rot=(0, 0, rng.uniform(0, 3)),
                 material=mat("wr%d" % k, col, 0.15, metal=0.7))
        dd = w.modifiers.new("D", "DISPLACE")
        dd.texture = tx
        dd.strength = 0.02
    light("SPOT", (0.2, -0.5, 3.5), 2500, (1, 1, 1), target=(0, 0, 0), spot=28, blend=0.3)
    cam = camera((0, -2.2, 0.9), (0, 0, 0), lens=35)
    sn = Snow(cam, 1500, (5, 5, 4), 0.5, (0.8, 0.8, 0.82), 0.006, vel=(0, 0, -0.08))

    def up(t):
        p = ease(t / ctx.dur)
        cam.location = Vector((0.1 * math.sin(t * 0.2), lerp(-2.2, -1.3, p), lerp(0.9, 0.6, p)))
        aim(cam, (0, 0, 0))
        sn.update(t)
    return up


# ================================================================ 31 ведучий / Місяць / глобус
def scene_31(ctx):
    sc = reset((0.0, 0.0, 0.0), 0.02, 0.6, (0.3, 0.4, 0.5))
    vol = sc.world.node_tree.nodes["VOL"]
    # Місяць
    o1 = Vector((300, 0, 0))
    terrain("moon", 60, 120, 0.3, 31, mat("moonsurf", (0.5, 0.5, 0.5), 0.95, noise=0.5, noise_scale=1.5, bump=0.6), 3.0, o1)
    earth = prim("sphere", o1 + Vector((8, 60, 14)), (3, 3, 3), material=mat("earth", (0.1, 0.3, 0.8), 0.4, emit=(0.15, 0.35, 0.9), emit_str=1.2, noise=0.6, noise_scale=3))
    astro = prim("cyl", o1 + Vector((0, 4, 1.2)), (0.28, 0.22, 0.55), material=mat("suit", (0.9, 0.9, 0.88), 0.6), vertices=16)
    helm = prim("sphere", o1 + Vector((0, 4, 2.0)), (0.27,) * 3, material=mat("suit2", (0.9, 0.9, 0.88), 0.6))
    visor = prim("sphere", o1 + Vector((0, 3.8, 2.0)), (0.2, 0.1, 0.16), material=mat("visor", (0.8, 0.6, 0.2), 0.05, metal=1))
    for sx in (-0.13, 0.13):
        prim("cyl", o1 + Vector((sx, 4, 0.45)), (0.1, 0.1, 0.35), material=bpy.data.materials["suit"], vertices=12)
    light("AREA", o1 + Vector((-15, -10, 15)), 60000, (1, 0.98, 0.95), target=o1 + Vector((0, 4, 0)), size=4)
    camM = camera(o1 + Vector((1.5, -3, 1.6)), o1 + Vector((0, 4, 1.4)), lens=35)
    # глобус
    o2 = Vector((600, 0, 0))
    gm = bpy.data.materials.new("globe")
    gm.use_nodes = True
    nt = gm.node_tree
    b = nt.nodes["Principled BSDF"]
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 2.5
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.55
    ramp.color_ramp.elements[0].color = (0.01, 0.03, 0.08, 1)
    ramp.color_ramp.elements[1].position = 0.57
    ramp.color_ramp.elements[1].color = (0.2, 0.35, 0.15, 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], b.inputs["Base Color"])
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = 1.2
    r2 = nt.nodes.new("ShaderNodeValToRGB")
    r2.color_ramp.elements[0].position = 0.75
    r2.color_ramp.elements[0].color = (0, 0, 0, 1)
    r2.color_ramp.elements[1].position = 0.78
    r2.color_ramp.elements[1].color = (0.1, 0.45, 0.9, 1)
    nt.links.new(wave.outputs["Fac"], r2.inputs[0])
    nt.links.new(r2.outputs[0], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 1.0
    globe = prim("sphere", o2, (3, 3, 3), material=gm, segments=64, ring_count=32)
    light("AREA", o2 + Vector((-8, -10, 6)), 4000, (1, 1, 1), target=o2, size=6)
    camG = camera(o2 + Vector((0, -9, 0)), o2, lens=35)
    cp = Cockpit(ctx, water=(0.0, 0.005, 0.015), darkness=0.95)
    s1, s2 = ctx.seg(1) - 0.15, ctx.seg(2) - 0.15

    def up(t):
        if t < s1:
            use_cam(cp.cam)
            vol.inputs["Density"].default_value = 0.02
            cp.update(t, push=t / s1)
        elif t < s2:
            use_cam(camM)
            vol.inputs["Density"].default_value = 0.0
            camM.location = o1 + Vector((1.5 - 0.1 * (t - s1), -3, 1.6))
        else:
            use_cam(camG)
            vol.inputs["Density"].default_value = 0.0
            k = (t - s2) / (ctx.dur - s2)
            globe.rotation_euler = (0.3, 0, t * 0.15)
            camG.location = o2 + Vector((0, lerp(-7, -11, ease(k)), 0))
    return up


# ================================================================ 32 фінал: ведучий, нічне море, очі в темряві
def scene_32(ctx):
    sc = reset((0.005, 0.01, 0.03), 0.0, strength=1.0)
    wnt = sc.world.node_tree
    sea_m = mat("sea32", (0.01, 0.02, 0.04), 0.08, coat=0.5)
    from scenes3d import ocean_surface as _os
    sea, md = _os(300, 10, sea_m, (0, 0, 0), 1.0, 1.0)
    moon = prim("sphere", (20, 260, 45), (6, 6, 6), material=emissive("moonm", (0.85, 0.9, 1.0), 8))
    light("AREA", (20, 200, 60), 200000, (0.6, 0.7, 0.9), target=(0, 0, 0), size=30)
    cam = camera((0, -12, 6), (0, 100, 8), lens=32)
    # глибина: очі (окрема темна декорація)
    o2 = Vector((0, 0, -400))
    eyes = []
    for sx in (-0.5, 0.5):
        m = emissive("eye32_%d" % len(eyes), (0.75, 0.9, 0.3), 6)
        e = prim("sphere", o2 + Vector((sx, 10, 0)), (0.16, 0.02, 0.07), material=m)
        pup = prim("sphere", o2 + Vector((sx, 9.98, 0)), (0.025, 0.02, 0.065), material=mat("pup32", (0, 0, 0), 0.5))
        eyes.append((e, m, pup))
    camD = camera(o2 + Vector((0, -2, 0)), o2 + Vector((0, 10, 0)), lens=40)
    snd = snow(1200, (8, 8, 6), (0, 0, -400), 0.01, 0.3, (0.5, 0.6, 0.7))
    cp = Cockpit(ctx, water=(0.0, 0.005, 0.015), darkness=0.9)
    s1 = ctx.seg(1) - 0.2
    s2 = s1 + 0.55 * (ctx.dur - s1)
    eye_t = 0.86 * ctx.dur

    def up(t):
        md.time = t * 0.6
        if t < s1:
            use_cam(cp.cam)
            cp.update(t, push=t / s1, smile=0.15)
        elif t < s2:
            use_cam(cam)
            k = ease((t - s1) / (s2 - s1))
            cam.location = Vector((0, -12 + 6 * k, 6 - 5.6 * k))
            aim(cam, lerpv((0, 100, 8), (0, 40, -4), k))
        else:
            use_cam(camD)
            k = smooth(eye_t, eye_t + 0.8, t)
            for e, m, pup in eyes:
                e.scale = (0.16, 0.02, 0.07 * max(k, 0.02))
                pup.hide_render = k < 0.3
                set_emit(m, 6 * k)
            camD.location = o2 + Vector((0, -2 + 0.15 * (t - s2), 0))
            snd.location = (0.0, 0.03 * t, -400 + 0.02 * t)
    return up
