"""Пробний 3D-кадр: нічна вулиця села в тумані (Blender/Cycles)."""
import math, os, random, sys
import bpy
from mathutils import Vector

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/village_test.png"
random.seed(8)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = int(os.environ.get("SAMPLES", "96"))
sc.cycles.use_denoising = True
sc.cycles.volume_bounces = 1
sc.cycles.max_bounces = 4
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.render.resolution_percentage = int(os.environ.get("PCT", "50"))
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"

def mat(name, color, rough=0.9, emit=None, strength=0.0, noise=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1); b.inputs["Roughness"].default_value = rough
    if noise:
        tex = nt.nodes.new("ShaderNodeTexNoise"); tex.inputs["Scale"].default_value = noise
        tex.inputs["Detail"].default_value = 8
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*[c * 0.55 for c in color], 1)
        ramp.color_ramp.elements[1].color = (*color, 1)
        nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"]); nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
        bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.4
        nt.links.new(tex.outputs["Fac"], bump.inputs["Height"]); nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1); b.inputs["Emission Strength"].default_value = strength
    return m

WALL = mat("wall", (0.72, 0.68, 0.6), 0.95, noise=6)
THATCH = mat("thatch", (0.32, 0.24, 0.14), 1.0, noise=40)
WIN = mat("win", (1, 0.6, 0.25), 0.5, emit=(1.0, 0.55, 0.2), strength=18)
WOODM = mat("wood", (0.12, 0.08, 0.05), 0.8, noise=20)
GROUND = mat("ground", (0.09, 0.075, 0.06), 1.0, noise=3)
SHUT = mat("shut", (0.12, 0.22, 0.42), 0.7)
FLAME = mat("flame", (1, 0.6, 0.2), 0.5, emit=(1.0, 0.5, 0.15), strength=60)
PINE = mat("pine", (0.02, 0.04, 0.03), 1.0)

def box(loc, size, m, rot=0):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=(0, 0, rot))
    o = bpy.context.object; o.scale = (size[0] / 2, size[1] / 2, size[2] / 2); o.data.materials.append(m); return o

def hut(x, y, rot, shutters=False):
    w, d, h = 7.0, 5.0, 2.6
    g = []
    g.append(box((0, 0, h / 2), (w, d, h), WALL))
    # стріха: призма, ширша за стіни
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=1, radius2=0.0, depth=1)
    r = bpy.context.object; r.rotation_euler = (0, 0, math.pi / 4)
    bpy.ops.object.transform_apply(rotation=True)
    r.scale = (w * 0.78, d * 0.82, 2.6); r.location = (0, 0, h + 1.2); r.data.materials.append(THATCH); g.append(r)
    for sx in (-1.9, 1.9):
        g.append(box((sx, -d / 2 - 0.02, 1.5), (0.8, 0.06, 0.9), WIN))
        if shutters:
            for ss in (-0.65, 0.65):
                g.append(box((sx + ss, -d / 2 - 0.08, 1.5), (0.45, 0.06, 1.0), SHUT))
        lt = bpy.data.lights.new("wl", "POINT"); lt.energy = 120; lt.color = (1, 0.55, 0.22); lt.shadow_soft_size = 0.3
        lo = bpy.data.objects.new("wl", lt); lo.location = (sx, -d / 2 - 0.6, 1.5); sc.collection.objects.link(lo); g.append(lo)
    g.append(box((0, -d / 2 - 0.03, 1.0), (0.9, 0.06, 2.0), WOODM))
    for o in g:
        o.location = Vector(o.location)
        o.rotation_euler.z += rot
        o.location.rotate(__import__("mathutils").Euler((0, 0, rot)))
        o.location += Vector((x, y, 0))

def lantern_pole(x, y):
    box((x, y, 1.8), (0.12, 0.12, 3.6), WOODM)
    box((x + 0.35, y, 3.55), (0.8, 0.08, 0.08), WOODM)
    box((x + 0.7, y, 3.25), (0.22, 0.22, 0.32), FLAME)
    lt = bpy.data.lights.new("ll", "POINT"); lt.energy = 180; lt.color = (1, 0.6, 0.25); lt.shadow_soft_size = 0.15
    lo = bpy.data.objects.new("ll", lt); lo.location = (x + 0.7, y, 3.1); sc.collection.objects.link(lo)

def pine(x, y, h):
    for i in range(4):
        bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=h * (0.28 - i * 0.05), depth=h * 0.45, location=(x, y, h * (0.3 + i * 0.18)))
        bpy.context.object.data.materials.append(PINE)

# земля й дорога
bpy.ops.mesh.primitive_plane_add(size=400); g = bpy.context.object; g.data.materials.append(GROUND)
for i in range(5):
    y = 8 + i * 12
    hut(-9.5 - random.uniform(0, 1.5), y, math.radians(90 + random.uniform(-6, 6)), shutters=(i == 0))
    hut(9.5 + random.uniform(0, 1.5), y + 5, math.radians(-90 + random.uniform(-6, 6)))
    lantern_pole(-4.2, y + 3) if i % 2 == 0 else lantern_pole(3.8, y + 2)
for i in range(70):
    pine(random.uniform(-60, 60), random.uniform(75, 120), random.uniform(9, 18))
# світ: темно-синє небо + об'ємний туман
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
bg = w.node_tree.nodes["Background"]; bg.inputs["Color"].default_value = (0.01, 0.018, 0.04, 1); bg.inputs["Strength"].default_value = 1.0
vol = w.node_tree.nodes.new("ShaderNodeVolumePrincipled")
vol.inputs["Density"].default_value = 0.018; vol.inputs["Color"].default_value = (0.7, 0.8, 1.0, 1); vol.inputs["Anisotropy"].default_value = 0.3
w.node_tree.links.new(vol.outputs["Volume"], w.node_tree.nodes["World Output"].inputs["Volume"])
# місячне світло
sun = bpy.data.lights.new("moon", "SUN"); sun.energy = 1.2; sun.color = (0.6, 0.72, 1.0); sun.angle = 0.02
so = bpy.data.objects.new("moon", sun); so.rotation_euler = (math.radians(55), 0, math.radians(150)); sc.collection.objects.link(so)

cam = bpy.data.cameras.new("cam"); cam.lens = 30
co = bpy.data.objects.new("cam", cam); sc.collection.objects.link(co); sc.camera = co
co.location = (0.6, -6, 1.6); co.rotation_euler = (math.radians(86), 0, math.radians(-2))
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("saved", OUT)
