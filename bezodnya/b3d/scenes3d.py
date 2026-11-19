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
    lamp_piv.location = o + Vector((0.05, 0.4, 0.92))
    wire = prim("cyl", (0, 0, -0.18), (0.004, 0.004, 0.18), material=mat("wire", (0.02, 0.02, 0.02), 0.5))
    wire.parent = lamp_piv
    bulb = prim("sphere", (0, 0, -0.38), (0.035, 0.035, 0.045), material=emissive("bulb", (1, 0.75, 0.4), 25))
    bulb.parent = lamp_piv
    shade = prim("cone", (0, 0, -0.33), (0.08, 0.08, 0.05), material=mat("shade", (0.15, 0.13, 0.1), 0.4, metal=0.7))
    shade.parent = lamp_piv
    L = light("POINT", (0, 0, 0), 90, (1, 0.72, 0.42), size=0.05)
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
    dive = 0.62 * ctx.dur

    def up(t):
        md.time = t * 0.8
        p = t / ctx.dur
        if t < dive:
            k = ease(smooth(0.05, 0.6, p))
            cam.location = Vector((0, -20 + 15 * k, 22 - 18 * k))
            aim(cam, lerpv((0, 200, 10), (0, 25, -10), k))
        else:
            k = (t - dive) / (ctx.dur - dive)
            cam.location = Vector((0, 5 + 3 * k, 2 - 8 * ease(min(1, k * 3)) - 2 * k))
            aim(cam, (0, 30, -30))
            under = smooth(0.0, 0.08, k)
            bgn.inputs[1].default_value = 1.0
            ramp.color_ramp.elements[0].color = (lerp(1.0, 0.04, under), lerp(0.5, 0.22, under), lerp(0.22, 0.3, under), 1)
            ramp.color_ramp.elements[1].color = (lerp(0.12, 0.0, under), lerp(0.08, 0.05, under), lerp(0.25, 0.1, under), 1)
            water = wnt.nodes.get("UVOL")
            if water is None and under > 0:
                v = wnt.nodes.new("ShaderNodeVolumePrincipled")
                v.name = "UVOL"
                v.inputs["Color"].default_value = (0.2, 0.75, 0.8, 1)
                v.inputs["Anisotropy"].default_value = 0.7
                wnt.links.new(v.outputs[0], wnt.nodes["World Output"].inputs["Volume"])
                water = v
            if water is not None:
                water.inputs["Density"].default_value = 0.06 * under
            sl.data.energy = 4 + 6 * under
            sl.rotation_euler = (math.radians(20), 0, math.radians(172))
            sl.data.color = (0.6 + 0.4 * (1 - under), 0.85, 0.9)
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
    sc = reset((0.08, 0.45, 0.55), 0.03, 0.75, (0.5, 0.9, 0.95), strength=0.9)
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
