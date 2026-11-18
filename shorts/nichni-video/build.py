"""«Нічні відео» — vertical 3D horror short (Blender / bpy, Cycles CPU).

  python build.py -- <project dir> preview [frame ...]   # stills -> preview/f#####.png
  python build.py -- <project dir> render [step_scale]   # PNG sequence -> frames/ (resumable)
  python build.py -- <project dir> blend                 # save scene.blend

One bedroom set, two copies of the same man (A sleeps, B is the double), ~30 shots, each its own
camera bound to a timeline marker (hard cuts). Timing comes from beats.json (voice).
shots.json tells post.py which look each shot gets (phone footage, camcorder night-vision, story).
"""
import json
import math
import os
import shutil
import sys

import bpy
from mathutils import Euler, Matrix, Vector


def _find_scripts():
    for p in (os.environ.get("KYLO_SCRIPTS", ""),
              "/root/.claude/plugins/synced/dcc9393f-9130-4ab2-a111-4ba3d42d6ba0_d7df1b23-90d5-4b6b-8e75-416b519a8c9e/kylo-3d-shorts/skills/3d-short/scripts"):
        if p and os.path.exists(os.path.join(p, "s3d.py")):
            return p
    raise SystemExit("set KYLO_SCRIPTS to the 3d-short scripts folder")


sys.path.insert(0, _find_scripts())
import s3d  # noqa: E402
import human  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
PROJ = os.path.abspath(ARGS[0] if ARGS else os.path.dirname(os.path.abspath(__file__)))
MODE = ARGS[1] if len(ARGS) > 1 else "preview"
FPS = 24
RES = (540, 960)
B = s3d.load_beats(os.path.join(PROJ, "beats.json"))
END = int(round((B[-1]["e"] + 1.6) * FPS))


def W(i, word=None, off=0):
    return s3d.when(B, i, word, off)


# ---------------------------------------------------------------- scene
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 20
sc.cycles.use_adaptive_sampling = True
sc.cycles.adaptive_threshold = 0.06
sc.cycles.use_denoising = True
sc.cycles.denoiser = "OPENIMAGEDENOISE"
sc.cycles.max_bounces = 4
sc.cycles.diffuse_bounces = 2
sc.cycles.glossy_bounces = 1
sc.cycles.transmission_bounces = 2
sc.cycles.transparent_max_bounces = 4
sc.cycles.caustics_reflective = False
sc.cycles.caustics_refractive = False
sc.cycles.blur_glossy = 1.0
sc.render.use_persistent_data = True
sc.render.resolution_x, sc.render.resolution_y = RES
sc.render.resolution_percentage = 100
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, END
sc.render.use_motion_blur = False
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.view_settings.exposure = 0.0

world = bpy.data.worlds.new("World")
world.use_nodes = True
sc.world = world
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.05, 0.06, 0.09, 1)

CONST = []          # datablocks whose fcurves become CONSTANT (light states)


def key(idb, path, frame, value, index=-1):
    if path.startswith("node_tree."):
        idb, path = idb.node_tree, path[len("node_tree."):]
    if "." in path:
        parent, attr = path.rsplit(".", 1)
        obj = idb.path_resolve(parent)
    else:
        obj, attr = idb, path
    if index < 0:
        setattr(obj, attr, value)
    else:
        getattr(obj, attr)[index] = value
    idb.keyframe_insert(path, frame=frame, index=index)
    if idb not in CONST:
        CONST.append(idb)


def vis(objs, frame, on):
    for o in (objs if isinstance(objs, (list, tuple)) else [objs]):
        for x in [o] + list(o.children_recursive):
            x.hide_render = not on
            x.keyframe_insert("hide_render", frame=frame)


# ---------------------------------------------------------------- materials
def M(name, rgb, rough=0.6, metal=0.0, noise=0.0, ns=8.0):
    return s3d.mat(name, rgb, rough=rough, metal=metal, noise=noise, noise_scale=ns)


def emit_mat(name, rgb, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs[0])
    return m, em


def wallpaper():
    m = bpy.data.materials.new("Wallpaper")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.85
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = 9.0
    wave.inputs["Distortion"].default_value = 0.4
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nt.links.new(sep.outputs["X"], comb.inputs["X"])
    nt.links.new(sep.outputs["Y"], comb.inputs["Y"])
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    nt.links.new(sep.outputs["X"], add.inputs[0])
    nt.links.new(sep.outputs["Y"], add.inputs[1])
    nt.links.new(add.outputs[0], comb.inputs["X"])
    nt.links.new(comb.outputs[0], wave.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.30, 0.32, 0.30, 1)
    ramp.color_ramp.elements[1].color = (0.37, 0.39, 0.36, 1)
    nt.links.new(wave.outputs["Fac"], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], b.inputs["Base Color"])
    return m


def planks():
    m = bpy.data.materials.new("Floor")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.55
    tc = nt.nodes.new("ShaderNodeTexCoord")
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.004
    br.inputs["Brick Width"].default_value = 1.2
    br.inputs["Row Height"].default_value = 0.14
    br.inputs["Color1"].default_value = (0.24, 0.14, 0.08, 1)
    br.inputs["Color2"].default_value = (0.17, 0.10, 0.06, 1)
    br.inputs["Mortar"].default_value = (0.05, 0.03, 0.02, 1)
    br.offset = 0.37
    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 30
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 0.35
    nt.links.new(br.outputs["Color"], mix.inputs[6])
    nt.links.new(nz.outputs["Color"], mix.inputs[7])
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    return m


WALL = wallpaper()
FLOOR = planks()
CEIL = M("Ceiling", (0.55, 0.55, 0.53), 0.9)
WOOD_D = M("DarkWood", (0.13, 0.07, 0.04), 0.5, noise=0.5, ns=20)
WOOD_M = M("MidWood", (0.30, 0.18, 0.10), 0.55, noise=0.5, ns=14)
LINEN = M("Linen", (0.62, 0.62, 0.60), 0.9, noise=0.2, ns=40)
BLANKET = M("Blanket", (0.20, 0.25, 0.33), 0.95, noise=0.35, ns=25)
PILLOW = M("Pillow", (0.70, 0.70, 0.68), 0.9, noise=0.15, ns=30)
BLACK = M("BlackPlastic", (0.02, 0.02, 0.022), 0.35)
METAL = M("Brass", (0.55, 0.45, 0.25), 0.3, metal=1.0)
DOORM = M("DoorPaint", (0.48, 0.47, 0.44), 0.6, noise=0.15, ns=10)
CURT = M("Curtain", (0.22, 0.10, 0.10), 0.95, noise=0.3, ns=12)
HALLW = M("HallWall", (0.20, 0.20, 0.19), 0.9, noise=0.2)

# ---------------------------------------------------------------- room (x: -2..2, y: -2.25..2.25, h 2.6)
RH = 2.6
s3d.box("Floor", (4.0, 4.5, 0.1), (0, 0, -0.05), FLOOR, bevel=0)
s3d.box("Ceiling", (4.2, 4.7, 0.1), (0, 0, RH + 0.05), CEIL, bevel=0)
s3d.box("WallBack", (4.2, 0.12, RH), (0, 2.31, RH / 2), WALL, bevel=0)
s3d.box("WallLeft", (0.12, 4.7, RH), (-2.06, 0, RH / 2), WALL, bevel=0)
# front wall with the door opening x 0.68..1.53, z 0..2.05
DX0, DX1, DH = 0.68, 1.53, 2.05
s3d.box("WallFrontL", (DX0 + 2.12, 0.12, RH), ((-2.12 + DX0) / 2, -2.31, RH / 2), WALL, bevel=0)
s3d.box("WallFrontR", (2.12 - DX1, 0.12, RH), ((DX1 + 2.12) / 2, -2.31, RH / 2), WALL, bevel=0)
s3d.box("WallFrontTop", (DX1 - DX0, 0.12, RH - DH), ((DX0 + DX1) / 2, -2.31, (RH + DH) / 2), WALL, bevel=0)
# right wall with the window opening y 0.2..1.4, z 0.9..2.05
WY0, WY1, WZ0, WZ1 = 0.15, 1.45, 0.9, 2.05
s3d.box("WallRightA", (0.12, 2.25 + WY0 + 0.1, RH), (2.06, (-2.35 + WY0) / 2, RH / 2), WALL, bevel=0)
s3d.box("WallRightB", (0.12, 2.35 - WY1, RH), (2.06, (WY1 + 2.35) / 2, RH / 2), WALL, bevel=0)
s3d.box("WallRightLow", (0.12, WY1 - WY0, WZ0), (2.06, (WY0 + WY1) / 2, WZ0 / 2), WALL, bevel=0)
s3d.box("WallRightTop", (0.12, WY1 - WY0, RH - WZ1), (2.06, (WY0 + WY1) / 2, (RH + WZ1) / 2), WALL, bevel=0)
# skirting
for nm, sz, lc in (("SkBack", (4, 0.02, 0.09), (0, 2.24, 0.045)), ("SkLeft", (0.02, 4.5, 0.09), (-1.99, 0, 0.045))):
    s3d.box(nm, sz, lc, CEIL, bevel=0.003)
# window frame + glass + outside sky panel
WIN = M("WindowFrame", (0.75, 0.74, 0.70), 0.5)
wy, wz = (WY0 + WY1) / 2, (WZ0 + WZ1) / 2
for nm, sz, lc in (("WinSill", (0.22, WY1 - WY0 + 0.1, 0.04), (1.96, wy, WZ0 - 0.02)),
                   ("WinMullV", (0.05, 0.04, WZ1 - WZ0), (2.05, wy, wz)),
                   ("WinMullH", (0.05, WY1 - WY0, 0.04), (2.05, wy, wz + 0.15)),
                   ("WinF1", (0.06, 0.05, WZ1 - WZ0), (2.05, WY0 + 0.025, wz)),
                   ("WinF2", (0.06, 0.05, WZ1 - WZ0), (2.05, WY1 - 0.025, wz)),
                   ("WinF3", (0.06, WY1 - WY0, 0.05), (2.05, wy, WZ1 - 0.025)),
                   ("WinF4", (0.06, WY1 - WY0, 0.05), (2.05, wy, WZ0 + 0.025))):
    s3d.box(nm, sz, lc, WIN, bevel=0.005)
SKY_M, SKY_E = emit_mat("SkyPanel", (0.10, 0.16, 0.32), 0.25)
sky = s3d.box("SkyPanel", (0.02, 3.0, 2.4), (3.2, wy, wz), SKY_M, bevel=0)
sky.visible_shadow = False
# a far rooftop silhouette outside the window
s3d.box("Rooftops", (0.1, 4.0, 1.0), (3.0, wy + 0.4, 0.95), M("Silhouette", (0.01, 0.01, 0.012), 1.0), bevel=0).visible_shadow = False
# curtains: wavy panels at both sides of the window
for k, yy in enumerate((WY0 - 0.12, WY1 + 0.12)):
    c = s3d.box(f"Curtain{k}", (0.03, 0.42, 2.25), (1.93, yy, 1.18), CURT, bevel=0)
    sub = c.modifiers.new("Sub", "SUBSURF")
    sub.levels = sub.render_levels = 3
    sub.subdivision_type = "SIMPLE"
    d = c.modifiers.new("Wave", "WAVE")
    d.use_x, d.use_y = False, True
    d.height, d.width, d.narrowness = 0.03, 0.12, 1.0
    d.speed = 0
    d.use_normal = True
    d.time_offset = -1000
s3d.cylinder("CurtainRod", 0.012, 2.0, (1.92, wy, 2.35), rot=(math.radians(90), 0, 0), mat=METAL, verts=12)

# ---------------------------------------------------------------- bed
s3d.box("BedFrame", (1.62, 2.18, 0.30), (0, 1.16, 0.20), WOOD_D, bevel=0.02)
for lx in (-0.76, 0.76):
    for ly in (0.12, 2.18):
        s3d.box(f"BedLeg{lx}{ly}", (0.07, 0.07, 0.08), (lx, ly, 0.04), WOOD_D, bevel=0.005)
s3d.box("Mattress", (1.50, 2.06, 0.20), (0, 1.17, 0.45), LINEN, bevel=0.06)
s3d.box("Headboard", (1.66, 0.07, 1.05), (0, 2.22, 0.53), WOOD_D, bevel=0.02)
pillow = s3d.box("Pillow", (0.66, 0.40, 0.12), (0, 1.97, 0.61), PILLOW, bevel=0.05)
pillow.modifiers["Bevel"].segments = 6
s3d.box("Pillow2", (0.60, 0.36, 0.10), (0.45, 2.02, 0.60), PILLOW, bevel=0.045)


def blanket_mesh(name, thrown=False):
    import numpy as np
    nx, ny = 56, 70
    xs = np.linspace(-0.86, 0.86, nx)
    y0, y1 = (0.06, 0.78) if thrown else (0.06, 1.62)
    ys = np.linspace(y0, y1, ny)
    verts, faces = [], []
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            ax = abs(x)
            base = 0.575
            if not thrown:
                torso = 0.20 * s(y, 0.95, 1.15) * (1 - s(y, 1.50, 1.64))
                legs = 0.15 * s(y, 0.35, 0.55) * (1 - s(y, 0.95, 1.10))
                feet = 0.24 * s(y, 0.10, 0.22) * (1 - s(y, 0.30, 0.46))
                h = max(torso, legs, feet)
                width = 0.30 if y > 1.0 else 0.24
                bump = h * math.exp(-(x / width) ** 4)
            else:
                roll = math.exp(-((y - 0.45) / 0.18) ** 2) * 0.16 + 0.05 * math.sin(x * 9 + y * 4) ** 2
                bump = roll
            fold = 0.008 * math.sin(x * 23 + y * 7) + 0.006 * math.sin(y * 31 - x * 5)
            z = base + bump + fold
            xx = x
            if ax > 0.74:
                k = (ax - 0.74) / 0.12
                z = base + bump * (1 - k) - 0.30 * k
                xx = math.copysign(0.74 + 0.07 * k, x)
            verts.append((xx, y, z))
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            faces.append((a, a + 1, a + nx + 1, a + nx))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    ob.data.materials.append(BLANKET)
    so = ob.modifiers.new("Thick", "SOLIDIFY")
    so.thickness = 0.03
    so.offset = 1
    sb = ob.modifiers.new("Sub", "SUBSURF")
    sb.levels = sb.render_levels = 1
    if not thrown:   # breathing: chest region rises and falls (driver on a shape key)
        ob.shape_key_add(name="Basis")
        kb = ob.shape_key_add(name="Breath")
        for v, kv in zip(me.vertices, kb.data):
            y = v.co.y
            w = s(y, 1.05, 1.25) * (1 - s(y, 1.45, 1.62)) * math.exp(-(v.co.x / 0.3) ** 2)
            kv.co = v.co + Vector((0, 0, 0.022 * w))
        dr = kb.driver_add("value").driver
        dr.type = "SCRIPTED"
        dr.expression = "0.5 + 0.5 * sin(frame * 6.2832 / 100)"
    return ob


def s(x, a, b):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


blanket = blanket_mesh("Blanket")
blanket_thrown = blanket_mesh("BlanketThrown", thrown=True)

# ---------------------------------------------------------------- furniture
s3d.box("Nightstand", (0.46, 0.40, 0.54), (1.12, 1.98, 0.27), WOOD_M, bevel=0.012)
s3d.box("NSDrawer", (0.40, 0.01, 0.16), (1.12, 1.775, 0.38), WOOD_D, bevel=0.004)
s3d.cylinder("NSKnob", 0.012, 0.02, (1.12, 1.765, 0.38), rot=(math.radians(90), 0, 0), mat=METAL, verts=12)
s3d.cylinder("LampBase", 0.055, 0.04, (1.24, 2.07, 0.56), mat=METAL, verts=24)
s3d.cylinder("LampStem", 0.01, 0.26, (1.24, 2.07, 0.70), mat=METAL, verts=10)
LAMP_M, LAMP_E = emit_mat("LampShade", (1.0, 0.62, 0.30), 0.0)
shade = s3d.cylinder("LampShade", 0.11, 0.17, (1.24, 2.07, 0.86), mat=LAMP_M, verts=32)
# wardrobe (left wall, near the front)
WX, WYc = -1.70, -1.15
s3d.box("Wardrobe", (0.56, 1.10, 2.05), (WX, WYc, 1.025), WOOD_M, bevel=0.012)
s3d.box("WardrobeGap", (0.01, 0.006, 1.95), (WX + 0.282, WYc, 1.03), WOOD_D, bevel=0)
for yy in (WYc - 0.06, WYc + 0.06):
    s3d.cylinder(f"WHandle{yy}", 0.008, 0.16, (WX + 0.30, yy, 1.05), mat=METAL, verts=10)
s3d.box("WardrobeTop", (0.6, 1.14, 0.04), (WX, WYc, 2.07), WOOD_D, bevel=0.008)
# desk + chair + laptop (front wall, left of the door)
s3d.box("DeskTop", (1.0, 0.52, 0.04), (-0.40, -1.98, 0.75), WOOD_M, bevel=0.008)
for lx in (-0.86, 0.06):
    for ly in (-2.20, -1.76):
        s3d.box(f"DeskLeg{lx}{ly}", (0.04, 0.04, 0.73), (lx, ly, 0.365), WOOD_D, bevel=0.004)
s3d.box("ChairSeat", (0.44, 0.42, 0.04), (-0.40, -1.30, 0.46), WOOD_D, bevel=0.01)
s3d.box("ChairBack", (0.44, 0.04, 0.48), (-0.40, -1.09, 0.72), WOOD_D, bevel=0.01)
for lx in (-0.60, -0.20):
    for ly in (-1.49, -1.11):
        s3d.box(f"ChairLeg{lx}{ly}", (0.03, 0.03, 0.44), (lx, ly, 0.22), WOOD_D, bevel=0.003)
s3d.box("LaptopBase", (0.34, 0.24, 0.016), (-0.40, -1.86, 0.778), M("Alu", (0.35, 0.36, 0.38), 0.35, metal=0.8), bevel=0.004)
lid = s3d.box("LaptopLid", (0.34, 0.012, 0.23), (-0.40, -1.98, 0.90), M("Alu2", (0.35, 0.36, 0.38), 0.35, metal=0.8), bevel=0.004)
lid.rotation_euler = (math.radians(12), 0, 0)
LAP_M, LAP_E = emit_mat("LaptopScreen", (0.55, 0.70, 0.85), 0.0)
lscr = s3d.box("LaptopScreen", (0.31, 0.002, 0.20), (-0.40, -1.971, 0.902), LAP_M, bevel=0)
lscr.rotation_euler = (math.radians(12), 0, 0)
# rug
s3d.box("Rug", (1.6, 1.1, 0.01), (0.15, -0.55, 0.005), M("Rug", (0.25, 0.08, 0.07), 0.95, noise=0.6, ns=6), bevel=0)
# picture frame above the bed
s3d.box("Picture", (0.55, 0.03, 0.40), (-0.2, 2.24, 1.70), WOOD_D, bevel=0.01)
s3d.box("PictureIn", (0.47, 0.01, 0.32), (-0.2, 2.22, 1.70), M("Painting", (0.18, 0.20, 0.17), 0.8, noise=0.9, ns=5), bevel=0)

# ---------------------------------------------------------------- door with two locks (hinged at x = DX0)
hinge = bpy.data.objects.new("DoorHinge", None)
sc.collection.objects.link(hinge)
hinge.location = (DX0, -2.27, 0)
door = s3d.box("Door", (DX1 - DX0 - 0.01, 0.045, DH - 0.01), ((DX0 + DX1) / 2, -2.27, DH / 2), DOORM, bevel=0.006)
for k, zz in enumerate((0.55, 1.45)):
    s3d.box(f"DoorPanel{k}", (0.6, 0.006, 0.7), ((DX0 + DX1) / 2, -2.245, zz), M(f"DoorPanelM{k}", (0.42, 0.41, 0.39), 0.6), bevel=0.01)
handle = s3d.cylinder("DoorHandle", 0.012, 0.13, (DX1 - 0.12, -2.21, 1.0), rot=(0, math.radians(90), 0), mat=METAL, verts=12)
LOCKS = []
for k, zz in enumerate((1.18, 1.36)):
    rose = s3d.cylinder(f"LockRose{k}", 0.028, 0.012, (DX1 - 0.11, -2.242, zz), rot=(math.radians(90), 0, 0), mat=METAL, verts=24)
    knob = s3d.box(f"LockTurn{k}", (0.016, 0.022, 0.05), (DX1 - 0.11, -2.226, zz), METAL, bevel=0.004)
    LOCKS.append(knob)
for o in [x for x in bpy.data.objects if x.name.startswith(("Door", "LockRose", "LockTurn")) and x.name != "DoorHinge"]:
    mw = o.matrix_world.copy()
    o.parent = hinge
    o.matrix_world = mw
# frame trim
for nm, sz, lc in (("TrimL", (0.06, 0.03, DH + 0.06), (DX0 - 0.03, -2.235, DH / 2)),
                   ("TrimR", (0.06, 0.03, DH + 0.06), (DX1 + 0.03, -2.235, DH / 2)),
                   ("TrimT", (DX1 - DX0 + 0.12, 0.03, 0.06), ((DX0 + DX1) / 2, -2.235, DH + 0.03))):
    s3d.box(nm, sz, lc, CEIL, bevel=0.004)
# hallway behind the door (only seen in the last shots)
s3d.box("HallFloor", (2.6, 3.0, 0.1), (1.1, -3.85, -0.05), FLOOR, bevel=0)
s3d.box("HallCeil", (2.6, 3.0, 0.1), (1.1, -3.85, RH + 0.05), CEIL, bevel=0)
s3d.box("HallWallL", (0.1, 3.0, RH), (-0.2, -3.85, RH / 2), HALLW, bevel=0)
s3d.box("HallWallR", (0.1, 3.0, RH), (2.4, -3.85, RH / 2), HALLW, bevel=0)
s3d.box("HallWallEnd", (2.6, 0.1, RH), (1.1, -5.4, RH / 2), HALLW, bevel=0)
s3d.box("HallFrame", (0.4, 0.04, 0.5), (2.34, -3.4, 1.6), WOOD_D, bevel=0.01).rotation_euler = (0, 0, math.radians(90))

# ---------------------------------------------------------------- phones + camcorder
PH_M, PH_E = emit_mat("PhoneScreen", (0.75, 0.82, 1.0), 0.0)


def phone(name, loc, rot):
    body = s3d.box(name, (0.074, 0.152, 0.009), loc, BLACK, bevel=0.004)
    scr = s3d.box(name + "_screen", (0.066, 0.142, 0.001), (loc[0], loc[1], loc[2] + 0.005), PH_M, bevel=0)
    scr.parent = body
    scr.matrix_parent_inverse = body.matrix_world.inverted()
    body.rotation_euler = rot
    return body


phone_ns = phone("PhoneNS", (1.02, 1.90, 0.545), (0, 0, math.radians(20)))
NS_M, NS_E = emit_mat("PhoneNSScreen", (0.75, 0.82, 1.0), 0.0)
phone_ns.children[0].data.materials[0] = NS_M

cc = bpy.data.objects.new("Camcorder", None)
sc.collection.objects.link(cc)
CAMC = Vector((WX + 0.05, WYc - 0.12, 2.09))
cc_parts = [
    s3d.box("CC_body", (0.22, 0.10, 0.12), (0, 0, 0.065), M("CCBody", (0.08, 0.08, 0.085), 0.45), bevel=0.012),
    s3d.cylinder("CC_lens", 0.035, 0.08, (0.14, 0, 0.075), rot=(0, math.radians(90), 0), mat=BLACK, verts=24),
    s3d.cylinder("CC_glass", 0.026, 0.005, (0.181, 0, 0.075), rot=(0, math.radians(90), 0),
                 mat=M("Glass", (0.02, 0.03, 0.05), 0.05, metal=0.5), verts=24),
    s3d.box("CC_screen", (0.07, 0.008, 0.05), (0.0, 0.056, 0.08), BLACK, bevel=0.003),
    s3d.box("CC_strap", (0.14, 0.02, 0.03), (-0.01, -0.055, 0.07), M("Strap", (0.03, 0.03, 0.03), 0.9), bevel=0.008),
]
LED_M, LED_E = emit_mat("LED", (1.0, 0.05, 0.03), 0.0)
cc_parts.append(s3d.cylinder("CC_led", 0.006, 0.006, (0.09, 0, 0.13), mat=LED_M, verts=12))
for p in cc_parts:
    p.parent = cc
cc.location = CAMC
TARGET_BED = Vector((0.35, 1.2, 0.7))
d = TARGET_BED - CAMC
cc.rotation_euler = (0, math.atan2(-d.z, d.xy.length) * 0.6, math.atan2(d.y, d.x))

# ---------------------------------------------------------------- lights
def area(name, loc, rot, size, color, energy=0.0, shape="RECTANGLE", sy=None):
    L = bpy.data.lights.new(name, "AREA")
    L.shape = shape
    L.size = size
    if sy:
        L.size_y = sy
    L.color = color
    L.energy = energy
    o = bpy.data.objects.new(name, L)
    sc.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    return o


def point(name, loc, color, energy=0.0, radius=0.05):
    L = bpy.data.lights.new(name, "POINT")
    L.color = color
    L.energy = energy
    L.shadow_soft_size = radius
    o = bpy.data.objects.new(name, L)
    sc.collection.objects.link(o)
    o.location = loc
    return o


def spot(name, loc, aim, color, energy=0.0, angle=70):
    L = bpy.data.lights.new(name, "SPOT")
    L.color = color
    L.energy = energy
    L.spot_size = math.radians(angle)
    L.spot_blend = 0.6
    L.shadow_soft_size = 0.03
    o = bpy.data.objects.new(name, L)
    sc.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


moon = area("Moon", (2.7, wy, 1.75), (0, math.radians(75), 0), 1.0, (0.55, 0.68, 1.0), sy=1.2)
sunL = area("SunWin", (2.6, wy + 0.2, 2.2), (0, math.radians(62), math.radians(-12)), 1.2, (1.0, 0.80, 0.58), sy=1.2)
fill = area("Fill", (0.0, -1.6, 2.5), (math.radians(35), 0, 0), 2.0, (0.75, 0.82, 1.0))
lampL = point("LampLight", (1.24, 2.07, 0.86), (1.0, 0.62, 0.32), radius=0.08)
ir = spot("IR", CAMC + Vector((0.2, 0.15, 0.08)), TARGET_BED, (1.0, 1.0, 1.0), angle=95)
lapL = area("LaptopLight", (-0.40, -1.90, 0.95), (math.radians(78), 0, 0), 0.3, (0.60, 0.75, 1.0), sy=0.2)
hallL = point("HallLight", (1.1, -4.6, 2.3), (1.0, 0.75, 0.5), radius=0.2)
facefill = point("FaceKick", (0, 0, 0), (0.7, 0.8, 1.0), radius=0.2)
phL = point("PhoneLight", (0, 0, 0), (0.75, 0.85, 1.0), radius=0.06)
nsL = point("PhoneNSLight", (1.02, 1.88, 0.62), (0.75, 0.85, 1.0), radius=0.03)

MODES = {  # light energies per look
    "night": dict(moon=80, sun=0, fill=3, lamp=0, ir=0, lap=0, hall=0, world=0.015, sky=0.20),
    "phone": dict(moon=110, sun=0, fill=8, lamp=0, ir=0, lap=0, hall=0, world=0.03, sky=0.22),
    "morning": dict(moon=0, sun=320, fill=8, lamp=0, ir=0, lap=0, hall=0, world=0.10, sky=1.6),
    "evening": dict(moon=45, sun=0, fill=10, lamp=70, ir=0, lap=0, hall=0, world=0.02, sky=0.10),
    "cam": dict(moon=30, sun=0, fill=0, lamp=0, ir=260, lap=0, hall=0, world=0.01, sky=0.15),
    "laptop": dict(moon=0, sun=110, fill=2, lamp=0, ir=0, lap=14, hall=0, world=0.04, sky=0.45),
    "dawn": dict(moon=0, sun=0, fill=6, lamp=0, ir=0, lap=0, hall=0, world=0.05, sky=0.9),
    "hall": dict(moon=55, sun=0, fill=0, lamp=0, ir=0, lap=0, hall=6, world=0.01, sky=0.20),
}
LOBJ = dict(moon=moon, sun=sunL, fill=fill, lamp=lampL, ir=ir, lap=lapL, hall=hallL)


def set_mode(f, mode, **over):
    v = dict(MODES[mode])
    v.update(over)
    for k, o in LOBJ.items():
        key(o.data, "energy", f, float(v[k]))
    key(world, 'node_tree.nodes["Background"].inputs[1].default_value', f, v["world"])
    key(world, 'node_tree.nodes["Background"].inputs[0].default_value', f,
        (0.30, 0.25, 0.20, 1) if mode == "morning" else (0.05, 0.06, 0.09, 1))
    key(SKY_M, 'node_tree.nodes["Emission"].inputs[1].default_value', f, v["sky"])
    key(SKY_M, 'node_tree.nodes["Emission"].inputs[0].default_value', f,
        (1.0, 0.86, 0.68, 1) if mode == "morning" else (0.55, 0.62, 0.72, 1) if mode == "laptop" else
        (0.22, 0.30, 0.55, 1) if mode == "dawn" else (0.10, 0.16, 0.32, 1))
    key(LAMP_M, 'node_tree.nodes["Emission"].inputs[1].default_value', f, 6.0 if v["lamp"] else 0.0)
    key(LAP_M, 'node_tree.nodes["Emission"].inputs[1].default_value', f, 3.0 if v["lap"] else 0.0)
    key(facefill.data, "energy", f, float(over.get("kick", 0.0)))


def phone_light(f, on, strength=4.0, light=2.5):
    key(PH_M, 'node_tree.nodes["Emission"].inputs[1].default_value', f, strength if on else 0.0)
    key(phL.data, "energy", f, light if on else 0.0)


def ns_light(f, on):
    key(NS_M, 'node_tree.nodes["Emission"].inputs[1].default_value', f, 1.6 if on else 0.0)
    key(nsL.data, "energy", f, 0.8 if on else 0.0)


# ---------------------------------------------------------------- the two men
SLEEP = {"upper_arm": (2, 8, 0), "forearm": (12, 0, 0), "hand": (0, 0, 0), "thigh": (0, 2, 0), "shin": (-3, 0, 0),
         "foot": (-10, 0, 0), "head": (14, 0, -10), "neck": (4, 0, 0)}
PJ = dict(shirt=(0.30, 0.31, 0.33), pants=(0.10, 0.11, 0.15), shoes=(0.70, 0.50, 0.40), hat=None)
SKIN = (0.80, 0.60, 0.50)
HAIR = (0.10, 0.07, 0.05)


def make_man(name):
    h = human.Human(name, loc=(0, 0, 0), facing=0, outfit=PJ, skin=SKIN, hair=HAIR, seed=2)
    bpy.context.view_layer.update()
    return h


def attach(h, obj, bone):
    bpy.context.view_layer.update()
    mw = obj.matrix_world.copy()
    obj.parent = h.arm
    obj.parent_type = "BONE"
    obj.parent_bone = bone
    bpy.context.view_layer.update()
    obj.matrix_world = mw


HC = Vector((0, 0.005, 1.675))
A = make_man("A")
B_ = make_man("B")
# A: closed eyes = dark lash lines; real eyes hidden until the very end
A_eyes = [p for p in A.parts if p.get("blink")]
A_hidden = [p for p in A.parts if p.name.split(".")[0] in ("A_hand", "A_thumb", "A_shoe", "A_sole", "A_forearm")]
for e in A_eyes:
    e.animation_data_clear()
    e.scale = (1, 1, 1)
lash_m = M("Lash", (0.06, 0.03, 0.025), 0.6)
A_lashes = []
for sx in (1, -1):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=1, location=(sx * 0.042, -0.112, 1.692))
    lo = bpy.context.active_object
    lo.name = f"A_lash{sx}"
    lo.scale = (0.022, 0.006, 0.0042)
    lo.rotation_euler = (0, math.radians(-8 * sx), 0)
    lo.data.materials.append(lash_m)
    attach(A, lo, "head")
    A_lashes.append(lo)
# B: the grin (hidden until he smiles), glowing pupils for the night-vision shots
grin_pts = []
for k in range(15):
    x = -0.056 + 0.112 * k / 14
    grin_pts.append((x, -0.113 + 2.6 * x * x, 1.609 + 3.6 * x * x))
cu = bpy.data.curves.new("Grin", "CURVE")
cu.dimensions = "3D"
cu.bevel_depth = 0.0042
cu.bevel_resolution = 3
sp = cu.splines.new("POLY")
sp.points.add(len(grin_pts) - 1)
for p_, c in zip(sp.points, grin_pts):
    p_.co = (*c, 1)
grin = bpy.data.objects.new("B_grin", cu)
sc.collection.objects.link(grin)
grin.data.materials.append(M("GrinM", (0.08, 0.01, 0.01), 0.4))
teeth = s3d.box("B_teeth", (0.07, 0.004, 0.009), (0, -0.113, 1.6145), M("Teeth", (0.85, 0.82, 0.72), 0.3), bevel=0.002)
attach(B_, grin, "head")
attach(B_, teeth, "head")
B_mouth = next(p for p in B_.parts if p.name.startswith("B_mouth"))
PUP = bpy.data.materials["B_pupil"]
pb_ = next(n for n in PUP.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
PUP_E = pb_.inputs["Emission Strength"]
pb_.inputs["Emission Color"].default_value = (0.9, 1.0, 0.9, 1)


def pupils_glow(f, on):
    key(PUP, 'node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value', f, 6.0 if on else 0.0)


# phone in B's right hand (built at the rest pose, then parented to the hand bone)
bpy.context.view_layer.update()
hb = B_.arm.pose.bones["hand.R"]
hm = B_.arm.matrix_world @ hb.matrix
hpos = hm @ Vector((0, 0.07, -0.035))
phone_h = phone("PhoneHand", tuple(hpos), (0, 0, 0))
bpy.context.view_layer.update()
phone_h.matrix_world = Matrix.Translation(hpos) @ (hm.to_3x3() @ Matrix.Rotation(math.radians(90), 3, "X")).to_4x4()
attach(B_, phone_h, "hand.R")
phL.location = phone_h.matrix_world @ Vector((0, 0, 0.06))
attach(B_, phL, "hand.R")


def snap(h, f):
    """Hold the current rig state at f-1 so the next state is a hard cut, not a slide."""
    s3d._key(h.arm, f - 1, loc=True, rot=True)
    for b in h.arm.pose.bones:
        b.keyframe_insert("rotation_euler", frame=f - 1)


def set_state(h, f, loc, rot_deg, pose, cut=True):
    if cut:
        snap(h, f)
    h.arm.location = loc
    h.arm.rotation_euler = tuple(math.radians(a) for a in rot_deg)
    s3d._key(h.arm, f, loc=True, rot=True)
    h.pose_at(f, pose)


HIP = Vector((0, 0, 0.94))
A_LOC = Vector((0, 0.30, 0.67))
LIE_ROT = (-90, 0, 0)
set_state(A, 1, A_LOC, LIE_ROT, SLEEP, cut=False)

POSE = {
    "sit_phone": {"thigh": (86, 7, 0), "shin": (-82, 0, 0), "foot": (-6, 0, 0), "upper_arm": (28, -14, 0), "forearm": (78, 0, 0),
                  "hand": (10, 0, 0), "head": (26, 0, 0), "spine": (10, 0, 0)},
    "sit_laptop": {"thigh": (86, 7, 0), "shin": (-84, 0, 0), "upper_arm": (24, -6, 0), "forearm": (58, 0, 0),
                   "head": (16, 0, 0), "spine": (12, 0, 0)},
    "sit_bed": {"thigh": (90, 6, 0), "shin": (0, 0, 0), "upper_arm": (14, 6, 0), "forearm": (20, 0, 0), "head": (6, 0, 0)},
    "edge": {"thigh": (86, 7, 0), "shin": (-82, 0, 0), "upper_arm": (8, 10, 0), "forearm": (20, 0, 0), "head": (8, 0, 0)},
    "reach": {"spine": (38, 0, 0), "upper_arm.R": (62, 4, 0), "forearm.R": (8, 0, 0), "upper_arm.L": (10, 6, 0),
              "forearm.L": (20, 0, 0), "head": (10, 0, 0), "thigh": (14, 2, 0), "shin": (-14, 0, 0)},
    "film": {"upper_arm.R": (62, -16, 0), "forearm.R": (48, 0, 0), "hand.R": (0, 0, 0), "upper_arm.L": (40, -22, 0),
             "forearm.L": (70, 0, 0), "spine": (12, 0, 0), "head": (24, 0, 0)},
    "lock": {"upper_arm.R": (64, -6, 0), "forearm.R": (40, 0, 0), "head": (6, 0, 0), "spine": (4, 0, 0)},
    "lift": {"upper_arm": (160, 8, 0), "forearm": (15, 0, 0), "head": (-22, 0, 0), "spine": (-4, 0, 0)},
    "stand_phone": {"upper_arm.R": (6, 4, 0), "forearm.R": (24, 0, 0), "head": (2, 0, 0)},
    "selfie": {"upper_arm.R": (78, 14, 0), "forearm.R": (12, 0, 0), "head": (6, 0, 4), "spine": (2, 0, 0)},
}
for k, v in POSE.items():
    human.POSES[k] = v

# ---------------------------------------------------------------- shots
SHOTS = []
OBJS = {"A": A.arm, "B": B_.arm}


def shot(name, f0, loc, target, lens=35, fx="clean", mode="night", move=None, shake=0.0, fstop=None, roll=0.0, **light):
    cam_d = bpy.data.cameras.new("C_" + name)
    cam_d.lens = lens
    cam_d.sensor_width = 24
    cam_d.clip_start = 0.02
    co = bpy.data.objects.new("C_" + name, cam_d)
    sc.collection.objects.link(co)

    def aim(l, t):
        q = (Vector(t) - Vector(l)).to_track_quat("-Z", "Y")
        e = q.to_euler()
        e.rotate_axis("Z", math.radians(roll))
        return e

    co.location = loc
    co.rotation_euler = aim(loc, target)
    if fstop:
        cam_d.dof.use_dof = True
        cam_d.dof.focus_distance = (Vector(target) - Vector(loc)).length
        cam_d.dof.aperture_fstop = fstop
    co.keyframe_insert("location", frame=f0)
    co.keyframe_insert("rotation_euler", frame=f0)
    if move:
        f1, l1, t1 = move[0], move[1], move[2]
        co.location = l1
        co.rotation_euler = aim(l1, t1)
        co.keyframe_insert("location", frame=f1)
        co.keyframe_insert("rotation_euler", frame=f1)
        if len(move) > 3:
            cam_d.lens = move[3]
            cam_d.keyframe_insert("lens", frame=f1)
            cam_d.lens = lens
            cam_d.keyframe_insert("lens", frame=f0)
        for fc in s3d.fcurves(co):
            for kp in fc.keyframe_points:
                kp.interpolation = "SINE"
                kp.easing = "EASE_IN_OUT"
    if shake:
        for fc in s3d.fcurves(co):
            if fc.data_path == "rotation_euler":
                n = fc.modifiers.new("NOISE")
                n.scale = 14
                n.strength = shake
                n.phase = 3 + fc.array_index * 17 + f0
            if fc.data_path == "location":
                n = fc.modifiers.new("NOISE")
                n.scale = 20
                n.strength = shake * 0.25
                n.phase = 11 + fc.array_index * 7 + f0
    m = sc.timeline_markers.new(name, frame=f0)
    m.camera = co
    set_mode(f0, mode, **light)
    SHOTS.append({"name": name, "f0": f0, "fx": fx, "mode": mode})
    return co


# bed states
def vis_man(h, f, on, skip=()):
    for x in [h.arm] + [p for p in h.parts if p not in skip]:
        x.hide_render = not on
        x.keyframe_insert("hide_render", frame=f)


def bed(f, sleeper):
    vis_man(A, f, sleeper, skip=list(A_eyes) + A_hidden)
    vis(A_lashes, f, sleeper)
    vis(blanket, f, sleeper)
    vis(blanket_thrown, f, not sleeper)


def show_b(f, on):
    vis_man(B_, f, on, skip=[B_mouth] if not on else [])
    if not on:
        vis([B_mouth], f, False)


# initial visibility
for o in (grin, teeth):
    vis(o, 1, False)
vis(phone_h, 1, True)
vis(phone_ns, 1, False)
vis(phone_ns, W(3), True)
vis(phone_h, W(7), False)
vis(cc, 1, False)
vis(A_eyes, 1, False)
vis(A_hidden, 1, False)
vis(A_lashes, 1, True)
key(hinge, "rotation_euler", 1, 0.0, index=2)
pupils_glow(1, False)
phone_light(1, False)
ns_light(1, False)
for k in LOCKS:
    key(k, "rotation_euler", 1, 0.0, index=1)

SEAT_BED = Vector((0.60, 0.92, 0.555))       # hips when sitting on the right edge of the bed
CHAIR = Vector((-0.40, -1.24, 0.50))           # hips on the desk chair
FACE_B_SIT = SEAT_BED + Vector((0.05, 0, 0.62))

# ---- beat 0: morning, he sits on the edge of the bed with the phone
f = W(0)
bed(f, False)
show_b(f, True)
set_state(B_, f, SEAT_BED - HIP, (0, 0, 90), "sit_phone")
B_.hold(f + 1, W(2) - 1)
phone_light(f, True)
shot("m_wide", f, (1.75, -0.55, 1.35), (0.72, 0.95, 0.92), lens=30, mode="morning", move=(W(0, "пам'ятаю", -7), (1.55, -0.2, 1.3), (0.72, 0.95, 0.92)), fstop=4)
f2 = W(0, "пам'ятаю", -6)
shot("m_face", f2, (1.62, 0.55, 1.22), (0.75, 0.95, 1.12), lens=50, mode="morning", move=(W(1) - 1, (1.5, 0.62, 1.2), (0.75, 0.95, 1.12)), fstop=2.2)
# ---- beat 1: phone footage from the door
f = W(1)
bed(f, True)
show_b(f, False)
phone_light(f, False)
shot("p_door", f, (1.05, -1.95, 1.48), (0.05, 1.6, 0.55), lens=17, fx="phone", mode="phone", shake=0.006)
SHOTS[-1]["timer"] = 0
# ---- beat 2: morning, over the shoulder, deletes it
f = W(2)
bed(f, False)
show_b(f, True)
phone_light(f, True)
shot("m_ots", f, (0.28, 1.25, 1.48), (1.0, 0.82, 0.95), lens=40, mode="morning",
     move=(W(3) - 1, (0.36, 1.2, 1.42), (1.0, 0.82, 0.95)), fstop=2.8)
fd = W(2, "Видалив")
phone_light(fd, True, strength=9)
phone_light(fd + 4, True, strength=4)
phone_light(fd + 14, False)
s3d.marker("tap", fd, prompt="phone tap")
# ---- beat 3: next morning the phone on the nightstand lights up; then footage from mid-room
f = W(3)
show_b(f, False)
shot("m_ns", f, (1.45, 1.32, 0.92), (1.04, 1.92, 0.56), lens=45, mode="morning", fstop=2.0,
     move=(W(3, "Камера") - 1, (1.38, 1.42, 0.86), (1.04, 1.92, 0.56)))
ns_light(f + 10, True)
s3d.marker("buzz", f + 10, prompt="phone buzz")
s3d.marker("buzz", f + 26, prompt="phone buzz")
f = W(3, "Камера")
ns_light(f, False)
bed(f, True)
shot("p_mid", f, (0.25, -0.55, 1.42), (0.0, 1.75, 0.6), lens=19, fx="phone", mode="phone", shake=0.006)
SHOTS[-1]["timer"] = 0
# ---- beat 4: beside the bed
f = W(4)
shot("p_bed", f, (0.95, 0.95, 1.30), (0.02, 1.88, 0.66), lens=20, fx="phone", mode="phone", shake=0.008)
SHOTS[-1]["timer"] = 0
# ---- beat 5-6: right over the face, breathing that isn't his
f = W(5)
shot("p_face", f, (0.05, 1.62, 1.12), (0.0, 1.98, 0.66), lens=24, fx="phone", mode="phone", shake=0.012, roll=8)
SHOTS[-1]["timer"] = 0
s3d.marker("hit", W(5, "Не", 0), prompt="low hit")
f = W(6, "А")
shot("p_face2", f, (0.02, 1.80, 0.98), (0.0, 1.99, 0.66), lens=26, fx="phone", mode="phone", shake=0.03, roll=-6)
SHOTS[-1]["timer"] = 21
# ---- beat 7: evening, lives alone, two locks
f = W(7)
bed(f, False)
show_b(f, True)
set_state(B_, f, (0.35, 0.05, 0), (0, 0, 0), "stand")
B_.walk(f + 2, W(7, "Двері") + 2, to=(1.25, -1.72), face_end=0)
shot("e_wide", f, (-1.0, 1.75, 1.75), (0.95, -1.6, 1.0), lens=26, mode="evening", fstop=4,
     move=(W(7, "Двері") - 1, (-0.85, 1.55, 1.7), (1.05, -1.8, 1.0)))
f = W(7, "Двері")
set_state(B_, f, (1.25, -1.72, 0), (0, 0, 0), "lock")
B_.hold(f + 1, W(8) - 1)
shot("e_locks", f, (1.62, -1.55, 1.42), (1.42, -2.24, 1.25), lens=40, mode="evening", fstop=2.5,
     move=(W(7, "Ніхто") - 1, (1.58, -1.65, 1.38), (1.42, -2.24, 1.25)))
for k, wd in enumerate(("два", "замки")):
    fk = W(7, wd, 2)
    key(LOCKS[k], "rotation_euler", fk, 0.0, index=1)
    key(LOCKS[k], "rotation_euler", fk + 4, math.radians(90), index=1)
    s3d.marker("lock", fk + 3, prompt="deadbolt lock click")
f = W(7, "Ніхто")
shot("e_door", f, (0.55, -0.3, 1.5), (1.1, -2.25, 1.15), lens=30, mode="evening", fstop=3.5,
     move=(W(8) - 1, (0.75, -0.9, 1.4), (1.1, -2.25, 1.15)))
# ---- beat 8: one night he puts the old camcorder on the wardrobe
f = W(8)
set_state(B_, f, (-1.05, -1.25, 0), (0, 0, -90), "stand")
B_.pose_at(W(8, "поставив", -8), "lift")
B_.hold(W(8, "поставив", -6), W(8, "камеру", 6))
B_.pose_at(W(8, "камеру", 14), "stand")
shot("n_ward", f, (0.75, 0.55, 1.45), (-1.45, -1.25, 1.75), lens=28, mode="evening", fstop=4,
     move=(W(8, "ввімкнув") - 1, (0.55, 0.35, 1.5), (-1.5, -1.25, 1.85)))
vis(cc, f, False)
vis(cc, W(8, "поставив", -2), True)
s3d.marker("place", W(8, "камеру", 0), prompt="plastic camcorder set down on wood")
f = W(8, "ввімкнув")
show_b(f, False)
shot("n_cc", f, (-1.05, -0.62, 2.22), (CAMC.x + 0.1, CAMC.y, CAMC.z + 0.08), lens=55, mode="evening", fstop=2.8, kick=10.0,
     move=(W(9) - 1, (-1.22, -0.83, 2.2), (CAMC.x + 0.1, CAMC.y, CAMC.z + 0.08)))
fl = W(8, "запис", 4)
key(LED_M, 'node_tree.nodes["Emission"].inputs[1].default_value', 1, 0.0)
key(LED_M, 'node_tree.nodes["Emission"].inputs[1].default_value', fl, 12.0)
s3d.marker("beep", fl, prompt="camcorder record beep")
# ---- beats 9-15: the camcorder tape (night vision)
CC_EYE = CAMC + Vector((0.34, 0.06, 0.10))
f = W(9)
bed(f, True)
shot("c_rew", f, tuple(CC_EYE), (0.3, 1.15, 0.65), lens=15, fx="rew", mode="cam")
f = W(10)
shot("c_wide", f, tuple(CC_EYE), (0.35, 1.15, 0.75), lens=15, fx="cam", mode="cam")
SHOTS[-1]["clock"] = 3 * 3600 + 0 * 60 + 2
# B separates from A: starts exactly in A's place and sits up
fsit = W(10, "сідаю", -4)
set_state(B_, fsit - 1, A_LOC, LIE_ROT, SLEEP)
show_b(fsit - 1, True)
pupils_glow(fsit - 1, True)
hip_w = A_LOC + Euler([math.radians(a) for a in LIE_ROT]).to_matrix() @ HIP
q0 = Euler([math.radians(a) for a in LIE_ROT]).to_quaternion()
q1 = Euler((0, 0, 0)).to_quaternion()
for k in range(1, 7):
    t = k / 6
    te = t * t * (3 - 2 * t)
    q = q0.slerp(q1, te)
    fr = fsit + int(round(26 * t))
    B_.arm.rotation_euler = q.to_euler("XYZ", B_.arm.rotation_euler)
    B_.arm.location = hip_w - q.to_matrix() @ HIP
    s3d._key(B_.arm, fr, loc=True, rot=True)
    B_.pose_at(fr, SLEEP, blend=("sit_bed", te))
s3d.marker("sheets", fsit, prompt="bed sheets rustle")
f = W(10, "Очі")
shot("c_eyes", f, tuple(CC_EYE), tuple(hip_w + Vector((0, 0, 0.72))), lens=95, fx="cam", mode="cam")
SHOTS[-1]["clock"] = 3 * 3600 + 0 * 60 + 9
f = W(10, "встаю", -2)
shot("c_wide2", f, tuple(CC_EYE), (0.35, 1.15, 0.75), lens=15, fx="cam", mode="cam")
SHOTS[-1]["clock"] = 3 * 3600 + 0 * 60 + 12
# swing legs over the right edge, stand up, take the phone, start filming
fs = f + 2
snap(B_, fs)
B_.arm.rotation_euler = (0, 0, math.radians(90))
B_.arm.location = Vector((0.55, 1.20, 0.56)) - HIP
s3d._key(B_.arm, fs + 14, loc=True, rot=True)
B_.pose_at(fs + 14, "edge")
B_.arm.location = Vector((1.02, 1.30, 0))
s3d._key(B_.arm, fs + 30, loc=True, rot=True)
B_.pose_at(fs + 30, "stand")
s3d.marker("creak", fs + 16, prompt="old bed creak")
ft = W(10, "беру", -6)
B_.turn(ft, 180, dur=8)
B_.pose_at(ft + 8, "reach")
fg = W(10, "телефон", 2)
B_.pose_at(fg, "reach")
vis(phone_ns, fg, False)
vis(phone_h, fg, True)
B_.pose_at(fg + 10, "stand_phone")
B_.turn(fg + 8, 270, dur=10)
fc = W(10, "вмикаю", 2)
B_.pose_at(fc, "film")
phone_light(fc + 6, True, strength=6, light=3.0)
s3d.marker("camstart", fc + 6, prompt="phone camera start sound")
B_.hold(fc + 1, W(14, "повертає", -2))
f = W(12)
shot("c_bed", f, tuple(CC_EYE), (0.15, 1.75, 0.68), lens=48, fx="cam", mode="cam")
SHOTS[-1]["clock"] = 3 * 3600 + 0 * 60 + 31
s3d.marker("hit", f + 2, prompt="deep boom")
f = W(13)
shot("c_wide3", f, tuple(CC_EYE), (0.45, 1.25, 0.95), lens=15, fx="cam", mode="cam", move=(W(14) - 1, tuple(CC_EYE), (0.55, 1.25, 1.0), 22))
SHOTS[-1]["clock"] = 3 * 3600 + 0 * 60 + 35
# he turns his head to the wardrobe, right into the lens, and smiles
f = W(14)
HEAD_B = Vector((1.02, 1.30, 1.70))
shot("c_med", f, tuple(CC_EYE), tuple(HEAD_B + Vector((0, 0, -0.25))), lens=36, fx="cam", mode="cam")
SHOTS[-1]["clock"] = 3 * 3600 + 0 * 60 + 42
fh = W(14, "повертає")
turned = dict(POSE["film"])
turned.update({"head": (-8, 0, 48), "neck": (0, 0, 12), "spine": (6, 0, 10)})
B_.pose_at(fh, "film")
B_.pose_at(fh + 40, turned)
B_.hold(fh + 41, W(16) - 1, breathe=False)
f = W(14, "Прямо")
shot("c_close", f, tuple(CC_EYE), tuple(HEAD_B), lens=110, fx="cam", mode="cam")
SHOTS[-1]["clock"] = 3 * 3600 + 0 * 60 + 47
fsm = W(14, "Посміхається")
vis([B_mouth], fsm, False)
vis([grin, teeth], fsm, True)
s3d.marker("sting", fsm, prompt="creepy string sting")
f = W(15)
shot("c_xclose", f, tuple(CC_EYE), tuple(HEAD_B + Vector((0, 0, -0.03))), lens=190, fx="glitch", mode="cam")
SHOTS[-1]["clock"] = 3 * 3600 + 0 * 60 + 53
# ---- beats 16-17: morning, trembling in front of the laptop (and the bed is not empty)
f = W(16)
show_b(f, True)
pupils_glow(f, False)
vis([grin, teeth], f, False)
vis([B_mouth], f, True)
phone_light(f, False)
vis(phone_h, f, False)
vis(phone_ns, f, True)
set_state(B_, f, CHAIR - HIP, (0, 0, 0), "sit_laptop")
B_.hold(f + 1, W(18) - 1)
shot("l_front", f, (0.05, -1.90, 1.12), (-0.40, -1.33, 1.15), lens=28, mode="laptop", fstop=2.4,
     move=(W(16, "Руки") - 1, (0.0, -1.86, 1.13), (-0.40, -1.33, 1.17)))
f = W(16, "Руки")
shot("l_hands", f, (0.05, -1.50, 1.42), (-0.40, -1.55, 0.85), lens=45, mode="laptop", fstop=2.0, shake=0.004)
for k in range(0, 40, 2):   # trembling forearms
    B_.pose_at(f + k, dict(POSE["sit_laptop"], forearm=(58 + (2.5 if k % 4 else -2.5), 0, 0), hand=((3 if k % 4 else -3), 0, 0)))
B_.pose_at(f + 42, "sit_laptop")
f = W(16, "Треба")
shot("l_face", f, (-0.02, -1.90, 1.25), (-0.40, -1.34, 1.22), lens=40, mode="laptop", fstop=2.0,
     move=(W(17, "не", 0), (-0.12, -1.80, 1.25), (-0.40, -1.34, 1.22)))
s3d.marker("hit", W(17, "не", 0), prompt="low boom")
f = W(17, "не", 0)
shot("l_bed", f, (-0.85, -1.62, 1.32), (0.0, 1.85, 0.66), lens=50, mode="laptop", fstop=2.0)
# ---- beat 18: flashback — standing in the middle of the room with the phone
f = W(18)
set_state(B_, f, (0.12, -0.35, 0), (0, 0, 0), "stand_phone")
B_.hold(f + 1, W(19) - 1, breathe=False)
pupils_glow(f, False)
vis(phone_h, f, True)
vis(phone_ns, f, False)
shot("f_low", f, (0.2, -1.65, 0.55), (0.12, -0.35, 1.35), lens=22, fx="flash", mode="dawn", fstop=3,
     move=(W(18, "З") - 1, (0.18, -1.35, 0.6), (0.12, -0.35, 1.4)))
f = W(18, "З")
shot("f_hand", f, (0.35, -1.05, 0.95), (-0.10, -0.38, 0.84), lens=40, fx="flash", mode="dawn", fstop=2.0, kick=3.0)
# ---- beat 19: through the open door from the hallway
f = W(19)
show_b(f, False)
key(hinge, "rotation_euler", f - 1, 0.0, index=2)
key(hinge, "rotation_euler", f, math.radians(100), index=2)
shot("h_door", f, (1.0, -4.4, 1.5), (0.2, 1.6, 0.62), lens=30, mode="hall", fstop=4,
     move=(W(20) - 1, (1.0, -3.9, 1.48), (0.2, 1.6, 0.62)))
# ---- beat 20: his own video: selfie in the hallway, the bedroom door ajar behind him
f = W(20)
show_b(f, True)
set_state(B_, f, (1.0, -3.15, 0), (0, 0, 180), "selfie")
B_.hold(f + 1, W(21) - 1, breathe=True)
vis(phone_h, f, False)
FACE_SELF = Vector((1.0, -3.15, 1.68))
shot("s_selfie", f, (0.92, -2.62, 1.66), tuple(FACE_SELF + Vector((0.02, 0, -0.04))), lens=24, fx="selfie", mode="hall",
     shake=0.01, kick=6.0)
SHOTS[-1]["timer"] = 0
vis([B_mouth], W(20, "поки"), False)
vis([grin, teeth], W(20, "поки"), True)
# ---- beat 21: his turn tomorrow — the sleeper opens his eyes
f = W(21)
show_b(f, False)
shot("a_face", f, (0.10, 1.48, 1.22), (0.0, 1.96, 0.74), lens=45, mode="night", kick=2.5,
     move=(END, (0.06, 1.62, 1.10), (0.0, 1.96, 0.74)))
fo = W(21, "знімати", 4)
vis(A_eyes, fo, True)
vis(A_lashes, fo, False)
for e in A_eyes:
    e.scale = (1.15, 1.15, 1.25)
s3d.marker("sting2", fo, prompt="horror sting eyes open")
SHOTS.append({"name": "black", "f0": fo + 20, "fx": "black", "mode": "night"})

# face kick light position per shot (constant)
KICK_AT = {"n_cc": (-1.1, -0.75, 2.35), "f_hand": (0.3, -0.9, 1.0), "s_selfie": (0.9, -2.75, 1.62), "a_face": (0.4, 1.6, 1.3)}
for s_ in SHOTS:
    if s_["name"] in KICK_AT:
        facefill.location = KICK_AT[s_["name"]]
        facefill.keyframe_insert("location", frame=s_["f0"])
        CONST.append(facefill) if facefill not in CONST else None

def aim_cam_at(name, obj, frame, offset=(0, 0, 0)):
    co = bpy.data.objects["C_" + name]
    sc.frame_set(frame)
    t = obj.matrix_world.translation + Vector(offset)
    co.rotation_euler = (t - co.location).to_track_quat("-Z", "Y").to_euler()
    co.keyframe_insert("rotation_euler", frame=frame)
    co.data.dof.focus_distance = (t - co.location).length
    sc.frame_set(1)


for s_ in SHOTS:
    if s_["name"] == "f_hand":
        aim_cam_at("f_hand", phone_h, s_["f0"] + 5)
    if s_["name"] == "l_hands":
        aim_cam_at("l_hands", phone_h, s_["f0"] + 5, offset=(0.08, -0.05, 0))

# constant interpolation for all state switches
for idb in CONST:
    ad = idb.animation_data
    if not ad or not ad.action:
        continue
    act = ad.action
    curves = getattr(act, "fcurves", None)
    if curves is None:
        curves = [c for layer in act.layers for strip in layer.strips for bag in strip.channelbags for c in bag.fcurves]
    for fc in curves:
        if idb in LOCKS and fc.data_path == "rotation_euler":
            continue
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"

# shots.json for post (frame ranges, looks)
SHOTS.sort(key=lambda x: x["f0"])
for i, s_ in enumerate(SHOTS):
    s_["f1"] = (SHOTS[i + 1]["f0"] - 1) if i + 1 < len(SHOTS) else END
json.dump({"fps": FPS, "end": END, "res": RES, "shots": SHOTS}, open(os.path.join(PROJ, "shots.json"), "w"), indent=1)
s3d.export_markers(os.path.join(PROJ, "render.sfx.json"))
print("BUILD OK: frames", END, "shots", len(SHOTS))


# ---------------------------------------------------------------- outputs
def render_frame(f, path, samples=None):
    sc.frame_set(f)
    if samples:
        sc.cycles.samples = samples
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


if MODE == "preview":
    out = os.path.join(PROJ, "preview")
    os.makedirs(out, exist_ok=True)
    frames = [int(x) for x in ARGS[2:]] or [s_["f0"] + 12 for s_ in SHOTS if s_["fx"] != "black"]
    sc.render.resolution_percentage = int(os.environ.get("PREVIEW_PCT", "50"))
    for fr in frames:
        render_frame(fr, os.path.join(out, f"f{fr:05d}.png"), samples=int(os.environ.get("PREVIEW_SPP", "12")))
elif MODE == "blend":
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(PROJ, "scene.blend"))
elif MODE == "render":
    import time
    out = os.path.join(PROJ, "frames")
    os.makedirs(out, exist_ok=True)
    sc.render.resolution_percentage = int(os.environ.get("RENDER_PCT", "80"))
    sc.cycles.samples = int(os.environ.get("RENDER_SPP", "8"))
    lo = int(os.environ.get("F0", "1"))
    hi = int(os.environ.get("F1", str(END)))
    step_of = {"phone": 2, "cam": 2, "rew": 3, "glitch": 3, "selfie": 2, "black": 0}
    last = None
    for s_ in SHOTS:
        st = step_of.get(s_["fx"], 1)
        for fr in range(max(lo, s_["f0"]), min(hi, s_["f1"]) + 1):
            p = os.path.join(out, f"{fr:05d}.png")
            if os.path.exists(p):
                last = p
                continue
            if st == 0:
                continue          # black: post makes it
            if st > 1 and (fr - s_["f0"]) % st and last and os.path.exists(last):
                shutil.copyfile(last, p)
            else:
                t = time.time()
                render_frame(fr, p)
                print(f"frame {fr}/{hi} {time.time() - t:.1f}s", flush=True)
            last = p
