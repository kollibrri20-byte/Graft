"""«Що якби мозок запрацював на 100%» — vertical 3D explainer.

  blender --background --python build.py -- <workdir> [preview|half|full]

Zones far apart in one scene, hard cuts between cameras bound to timeline markers:
  ROOM  — a guy in a bright room (real view)
  BRAIN — glass head on a navy void, a pink brain with glowing neuron clusters (X-ray view)
  CLINIC — MRI scanner + ward bed with a doctor
Rendered with Cycles (CPU) — this machine has no GPU.
Facts: the "10 % of the brain" myth is debunked by imaging (activity across nearly all regions over a day);
a seizure is excessive, synchronous neuronal activity; anti-seizure drugs dampen that excitability.
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_scripts(here):
    import glob
    for c in (os.environ.get("KYLO_SCRIPTS", ""), os.path.join(here, "..", "..", "scripts")):
        if c and os.path.exists(os.path.join(c, "s3d.py")):
            return os.path.abspath(c)
    hits = sorted(glob.glob(os.path.expanduser("~/.claude/plugins/*/*/kylo-3d-shorts/skills/3d-short/scripts")) +
                  glob.glob(os.path.expanduser("~/.claude/plugins/cache/*/kylo-3d-shorts/*/skills/3d-short/scripts")))
    if hits:
        return hits[-1]
    raise SystemExit("set KYLO_SCRIPTS=<plugin>/skills/3d-short/scripts")


SCRIPTS = _find_scripts(HERE)
sys.path.insert(0, SCRIPTS)
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector, noise  # noqa: E402
import s3d  # noqa: E402
import human  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
WORK = os.path.abspath(argv[0])
MODE = argv[1] if len(argv) > 1 else "full"
B = s3d.load_beats(os.path.join(WORK, "beats.json"))
END = B[-1]["fe"] + 30
W = lambda i, word=None, off=0: s3d.when(B, i, word, off)  # noqa: E731
rnd = random.Random(7)
FONT = os.path.join(SCRIPTS, "..", "assets", "fonts", "Montserrat-Variable.ttf")

s3d.new_short(seconds=END / 30, engine="CYCLES", sky=None, sun_elev=40, sun_azim=-25)
sc = bpy.context.scene
sc.frame_end = END
try:
    sc.view_settings.look = "AgX - Punchy"
except TypeError:
    pass
cy = sc.cycles
cy.device = "CPU"
cy.samples = int(os.environ.get("SAMPLES", "48"))
cy.use_denoising = True
cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces = 6, 2, 2, 6
cy.transparent_max_bounces = 8
cy.use_adaptive_sampling = True
sc.render.use_motion_blur = False
sc.render.film_transparent = False

ROOM = Vector((0, 0, 0))
BRAIN = Vector((60, 0, 0))
CLINIC = Vector((-60, 0, 0))


def font_label(lb):
    """Use Montserrat (has Cyrillic) for every label text."""
    try:
        f = bpy.data.fonts.load(FONT, check_existing=True)
    except Exception:
        return
    for o in [lb] + list(lb.children_recursive if hasattr(lb, "children_recursive") else []):
        if o.type == "FONT":
            o.data.font = f


TAGS = []


def tag(text, loc, frame, hold=75, size=0.24, color=(0.03, 0.05, 0.12)):
    """Recorded now, built after the cameras: the plate is glued to the camera live at `frame`, upper third."""
    TAGS.append((text, frame, hold, color))


def build_tag(text, frame, hold, color):
    cam = None
    for m in sorted(sc.timeline_markers, key=lambda m: m.frame):
        if m.frame <= frame + 6 and m.camera:
            cam = m.camera
    sc.frame_set(frame + 6)
    d = cam.data.dof.focus_distance * 0.9
    lb = s3d.label(text, loc=(0, 0, 0), size=0.05 * d)
    font_label(lb)
    for o in lb.children_recursive:
        for sl in getattr(o, "material_slots", []):
            if sl.material and sl.material.name.startswith("lbl_bg"):
                m = sl.material.copy()
                m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*color, 1)
                m.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (*color, 1)
                m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 1.0
                sl.material = m
            elif sl.material and sl.material.name.startswith("lbl_txt"):
                m = sl.material.copy()
                for nd in m.node_tree.nodes:
                    if nd.type == "EMISSION":
                        nd.inputs["Strength"].default_value = 6.0
                sl.material = m
    lb.parent = cam
    lb.location = (0, 0.24 * 50 / cam.data.lens * d, -d)
    lb.rotation_euler = (math.radians(-90), 0, 0)
    s3d.pop_in(lb, frame, dur=8, sfx=None)
    s3d.shrink_out(lb, frame + hold, dur=8)
    return lb


def area(name, loc, target, energy, size=2.0, color=(1, 1, 1)):
    l = bpy.data.lights.new(name, "AREA")
    l.energy = energy
    l.size = size
    l.color = color
    o = bpy.data.objects.new(name, l)
    sc.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


# ================================================================= zone 1: the room
R = ROOM
wall = s3d.mat("RoomWall", (0.86, 0.62, 0.38), rough=0.85, noise=0.15)
s3d.box("Floor", (8, 8, 0.1), R + Vector((0, 2, -0.05)), s3d.tex("wood_floor_deck", tile=1.5, tint=None, fallback=(0.55, 0.36, 0.2)))
s3d.box("BackWall", (8, 0.2, 4), R + Vector((0, 2.2, 2)), wall)
s3d.box("SideWall", (0.2, 6, 4), R + Vector((-2.6, 0, 2)), wall)
win_mat = s3d.mat_emit("WindowSky", (0.65, 0.85, 1.0), 2.5)
s3d.box("Window", (1.4, 0.05, 1.6), R + Vector((1.3, 2.08, 1.9)), win_mat)
for x in (0.58, 2.02):
    s3d.box("WinFrame", (0.08, 0.1, 1.7), R + Vector((x, 2.06, 1.9)), s3d.mat("Frame", (0.95, 0.95, 0.95), rough=0.4))
desk_m = s3d.mat("Desk", (0.35, 0.22, 0.12), rough=0.5)
s3d.box("Desk", (1.6, 0.7, 0.06), R + Vector((-1.15, 1.2, 0.76)), desk_m)
for dx in (-0.7, 0.7):
    s3d.box("DeskLeg", (0.06, 0.6, 0.74), R + Vector((-1.15 + dx, 1.2, 0.37)), desk_m)
s3d.box("Book", (0.3, 0.22, 0.06), R + Vector((-1.4, 1.1, 0.82)), s3d.mat("Book", (0.1, 0.35, 0.7)))
s3d.box("Book2", (0.28, 0.2, 0.05), R + Vector((-1.38, 1.12, 0.875)), s3d.mat("Book2", (0.85, 0.75, 0.15)))
plant_pot = s3d.cylinder("Pot", 0.18, 0.35, R + Vector((1.9, 1.6, 0.175)), mat=s3d.mat("Pot", (0.8, 0.35, 0.2)))
for k in range(6):
    s3d.rock(f"Leaf{k}", 0.22, R + Vector((1.9 + rnd.uniform(-0.15, 0.15), 1.6 + rnd.uniform(-0.1, 0.1), 0.55 + k * 0.08)),
             material=s3d.mat("Leaf", (0.15, 0.55, 0.2)), seed=k, flat=0.4)
room_key = area("RoomKey", R + Vector((1.5, -2.5, 3.2)), R + Vector((0, 1, 1.4)), 600, size=3)
room_fill = area("RoomFill", R + Vector((-2.0, -1.5, 2.0)), R + Vector((0, 1, 1.4)), 180, size=3, color=(0.8, 0.9, 1.0))
room_red = area("RoomRed", R + Vector((0, -1.2, 2.6)), R + Vector((0, 1, 1.3)), 0, size=1.5, color=(1.0, 0.1, 0.05))

guy = human.Human("Guy", loc=R + Vector((0, 1.0, 0)), facing=0, outfit=dict(shirt=(0.05, 0.45, 0.85), pants=(0.15, 0.15, 0.2),
                                                                            shoes=(0.9, 0.9, 0.9), hat=None), seed=0)

# ================================================================= zone 2: X-ray brain on a navy void
Z = BRAIN
void = bpy.data.materials.new("Void")
void.use_nodes = True
nt = void.node_tree
bg = nt.nodes["Principled BSDF"]
bg.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1)
bg.inputs["Emission Color"].default_value = (0.01, 0.03, 0.09, 1)
bg.inputs["Emission Strength"].default_value = 1.0
bg.inputs["Roughness"].default_value = 1.0
bpy.ops.mesh.primitive_uv_sphere_add(radius=9, location=Z)
dome = bpy.context.object
dome.name = "VoidDome"
dome.data.materials.append(void)
for p in dome.data.polygons:
    p.use_smooth = True

# glass head (X-ray look: fresnel rim glow, see-through centre)
glass = bpy.data.materials.new("XrayGlass")
glass.use_nodes = True
n = glass.node_tree.nodes
lk = glass.node_tree.links
n.clear()
out = n.new("ShaderNodeOutputMaterial")
mix = n.new("ShaderNodeMixShader")
tr = n.new("ShaderNodeBsdfTransparent")
em = n.new("ShaderNodeEmission")
em.inputs["Color"].default_value = (0.25, 0.6, 1.0, 1)
em.inputs["Strength"].default_value = 1.4
lw = n.new("ShaderNodeLayerWeight")
lw.inputs["Blend"].default_value = 0.2
lk.new(lw.outputs["Facing"], mix.inputs["Fac"])
lk.new(tr.outputs[0], mix.inputs[1])
lk.new(em.outputs[0], mix.inputs[2])
lk.new(mix.outputs[0], out.inputs["Surface"])
glass.blend_method = "BLEND" if hasattr(glass, "blend_method") else None

HEAD_C = Z + Vector((0, 0, 1.62))


def glass_part(name, loc, scale, sub=4):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=loc, segments=48, ring_count=32)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    o.data.materials.append(glass)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


# one smooth glass silhouette (metaballs -> mesh): skull, jaw, nose, neck, shoulders
mb = bpy.data.metaballs.new("XBody")
mb.resolution = 0.008
mb.render_resolution = 0.006
for c, r, sc_ in ((HEAD_C + Vector((0, 0.005, 0.01)), 0.19, (0.88, 1.05, 1.0)), (HEAD_C + Vector((0, -0.035, -0.09)), 0.12, (0.85, 1.0, 0.9)),
                  (HEAD_C + Vector((0, -0.11, -0.03)), 0.045, (0.55, 0.9, 1.2)), (HEAD_C + Vector((0, 0.01, -0.2)), 0.09, (1, 1, 1.5)),
                  (HEAD_C + Vector((0.12, 0.02, -0.34)), 0.17, (1.3, 0.75, 0.6)), (HEAD_C + Vector((-0.12, 0.02, -0.34)), 0.17, (1.3, 0.75, 0.6))):
    e = mb.elements.new()
    e.co = c - HEAD_C
    e.radius = r
    e.type = "ELLIPSOID"
    e.size_x, e.size_y, e.size_z = sc_
xb = bpy.data.objects.new("XBodyMB", mb)
sc.collection.objects.link(xb)
xb.location = HEAD_C
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
me_x = bpy.data.meshes.new_from_object(xb.evaluated_get(dg))
xo = bpy.data.objects.new("XBody", me_x)
sc.collection.objects.link(xo)
xo.matrix_world = xb.matrix_world
bpy.data.objects.remove(xb)
_bb = [xo.matrix_world @ Vector(v.co) for v in xo.data.vertices]
print("XBODY verts", len(_bb), "zmax-head", max(v.z for v in _bb) - HEAD_C.z if _bb else None,
      "xhalf", max(v.x for v in _bb if v.z > HEAD_C.z) - HEAD_C.x if _bb else None)
xo.data.materials.clear()
xo.data.materials.append(glass)
for p_ in xo.data.polygons:
    p_.use_smooth = True

# brain: two displaced hemispheres with folds
brain_m = s3d.mat("Brain", (0.88, 0.42, 0.45), rough=0.42)
try:
    bsdf = brain_m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Subsurface Weight"].default_value = 0.25
    bsdf.inputs["Subsurface Radius"].default_value = (0.02, 0.006, 0.004)
except Exception:
    pass
BR = HEAD_C + Vector((0, 0.01, 0.025))
BS = Vector((0.06, 0.088, 0.066))     # half-size of one hemisphere


def hemisphere(side):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=6, radius=1.0)
    for v in bm.verts:
        p = v.co.copy()
        # flatten the inner face, round the back, narrower front
        p.x = abs(p.x) ** 0.6 * (1 if p.x >= 0 else -1)
        q = Vector((p.x * BS.x + side * 0.007, p.y * BS.y, p.z * BS.z * (0.85 if p.z < 0 else 1.0)))
        if p.y < 0:
            q.z *= 0.9 - 0.15 * (-p.y)
        # gyri: ridged noise along the surface
        f = noise.noise(Vector((p.x * 2.5 + side * 9, p.y * 2.5, p.z * 2.5)))
        g = 1 - abs(noise.noise(p * 9.0 + Vector((side * 4, 0, 0)) + Vector((f, f, f)) * 0.6))
        q = q * (1 + 0.04 * g * g + 0.012 * f)
        v.co = q + BR
    me = bpy.data.meshes.new(f"Hemi{side}")
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(f"Hemi{side}", me)
    sc.collection.objects.link(o)
    o.data.materials.append(brain_m)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


hemisphere(1)
hemisphere(-1)
# brainstem + cerebellum
s3d.cylinder("Stem", 0.014, 0.06, BR + Vector((0, 0.025, -0.07)), rot=(0.3, 0, 0), mat=brain_m)
cb = glass_part("Cerebellum", BR + Vector((0, 0.065, -0.045)), (0.05, 0.03, 0.022))
cb.data.materials[0] = brain_m

# neurons: N regions of glowing dots on the cortex, each region its own emissive material
REGIONS = []
DIRS = [Vector(d).normalized() for d in [(1, -0.8, 0.3), (-1, -0.8, 0.3), (1, 0, 0.8), (-1, 0, 0.8), (1, 0.8, 0.2), (-1, 0.8, 0.2),
                                          (1, -0.1, -0.5), (-1, -0.1, -0.5), (0.4, -1, -0.1), (-0.4, -1, -0.1), (0.5, 0.9, -0.4), (-0.5, 0.9, -0.4)]]
for ri, d in enumerate(DIRS):
    m = bpy.data.materials.new(f"Neuron{ri}")
    m.use_nodes = True
    nn = m.node_tree.nodes
    nn.clear()
    o_ = nn.new("ShaderNodeOutputMaterial")
    e_ = nn.new("ShaderNodeBsdfPrincipled")
    e_.inputs["Base Color"].default_value = (0.95, 0.55, 0.55, 1)
    e_.inputs["Roughness"].default_value = 0.4
    e_.inputs["Emission Color"].default_value = (1.0, 0.85, 0.35, 1)
    e_.inputs["Emission Strength"].default_value = 0.0
    m.node_tree.links.new(e_.outputs[0], o_.inputs["Surface"])
    bm = bmesh.new()
    pts = 0
    while pts < 60:
        v = Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 1))).normalized()
        if v.dot(d) < 0.78 or (v.x > 0) != (d.x > 0):
            continue
        side = 1 if v.x > 0 else -1
        p = Vector((abs(v.x) ** 0.6 * side * BS.x + side * 0.007, v.y * BS.y, v.z * BS.z * (0.85 if v.z < 0 else 1)))
        p = p * 1.045 + BR
        r = rnd.uniform(0.0012, 0.0024)
        ret = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r)
        bmesh.ops.translate(bm, vec=p, verts=ret["verts"])
        pts += 1
    me = bpy.data.meshes.new(f"Neurons{ri}")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(f"Neurons{ri}", me)
    sc.collection.objects.link(ob)
    ob.data.materials.append(m)
    lt = bpy.data.lights.new(f"NGlow{ri}", "POINT")
    lt.energy = 0
    lt.shadow_soft_size = 0.02
    lt.color = (1.0, 0.8, 0.35)
    lo = bpy.data.objects.new(f"NGlow{ri}", lt)
    sc.collection.objects.link(lo)
    lo.location = BR + Vector((d.x * 0.09, d.y * 0.11, d.z * 0.09))
    REGIONS.append((m, e_, lt))

brain_key = area("BrainKey", Z + Vector((-0.6, -0.9, 2.3)), BR, 25, size=0.8, color=(0.85, 0.9, 1.0))
brain_rim = area("BrainRim", Z + Vector((0.7, 0.8, 1.9)), BR, 35, size=0.8, color=(0.4, 0.6, 1.0))


def neuron(ri, frame, strength, color=None, dur=3):
    m, e_, lt = REGIONS[ri]
    S_, C_ = e_.inputs["Emission Strength"], e_.inputs["Emission Color"]
    strength = 0.0 if strength <= 0.2 else strength
    S_.keyframe_insert("default_value", frame=frame - dur)
    lt.keyframe_insert("energy", frame=frame - dur)
    S_.default_value = strength
    lt.energy = strength * 0.5
    if color:
        C_.keyframe_insert("default_value", frame=frame - dur)
        lt.keyframe_insert("color", frame=frame - dur)
        C_.default_value = (*color, 1)
        lt.color = color
        C_.keyframe_insert("default_value", frame=frame)
        lt.keyframe_insert("color", frame=frame)
    S_.keyframe_insert("default_value", frame=frame)
    lt.keyframe_insert("energy", frame=frame)


def all_neurons(frame, strength, color=None, dur=3):
    for ri in range(len(REGIONS)):
        neuron(ri, frame, strength, color, dur)


# ================================================================= zone 3: clinic (MRI + ward)
C = CLINIC
cl_wall = s3d.mat("ClinicWall", (0.80, 0.90, 0.92), rough=0.8)
s3d.box("CFloor", (14, 8, 0.1), C + Vector((0, 2, -0.05)), s3d.mat("CFloorM", (0.62, 0.68, 0.70), rough=0.35))
s3d.box("CWall", (14, 0.2, 4), C + Vector((0, 3.0, 2)), cl_wall)
white = s3d.mat("MRIWhite", (0.95, 0.95, 0.96), rough=0.25)
MRI = C + Vector((-3, 1.2, 0))
bpy.ops.mesh.primitive_torus_add(major_radius=0.62, minor_radius=0.38, location=MRI + Vector((0, 0, 1.1)),
                                 rotation=(0, math.radians(90), 0), major_segments=64, minor_segments=24)
ring = bpy.context.object
ring.name = "MRIRing"
ring.scale = (1, 1, 1)
ring.data.materials.append(white)
for p in ring.data.polygons:
    p.use_smooth = True
s3d.box("MRIBody", (0.7, 2.0, 2.2), MRI + Vector((0, 0.35, 1.1)), white, bevel=0.15)
bore = s3d.cylinder("MRIBore", 0.36, 0.75, MRI + Vector((0, 0, 1.1)), rot=(0, math.radians(90), 0),
                    mat=s3d.mat("Bore", (0.2, 0.25, 0.3), rough=0.3))
s3d.box("MRIBed", (2.4, 0.6, 0.12), MRI + Vector((-1.5, 0, 0.82)), s3d.mat("BedPad", (0.25, 0.45, 0.7), rough=0.5))
s3d.box("MRIBase", (2.0, 0.5, 0.75), MRI + Vector((-1.6, 0, 0.38)), white)
s3d.box("MRIBlue", (0.05, 0.9, 0.08), MRI + Vector((-0.36, 0, 1.75)), s3d.mat_emit("MRIStripe", (0.2, 0.6, 1.0), 4))
# patient lies on the MRI bed, head into the ring (+X)
pat = human.Human("Patient", loc=MRI + Vector((-1.5, -0.75, 0)), facing=0, outfit=dict(shirt=(0.6, 0.8, 0.9), pants=(0.6, 0.8, 0.9),
                                                                                   shoes=(0.9, 0.9, 0.9), hat=None), seed=0)
pat.lie(40, hip=MRI + Vector((-1.75, 0, 0.98)), head_dir=1, sit=10, dur=16)

WARD = C + Vector((3, 1.2, 0))
s3d.box("Bed", (2.1, 0.95, 0.5), WARD + Vector((0, 0, 0.35)), s3d.mat("Sheet", (0.92, 0.94, 0.96), rough=0.7))
s3d.box("BedFrame", (2.2, 1.0, 0.3), WARD + Vector((0, 0, 0.15)), s3d.mat_steel())
s3d.box("Pillow", (0.45, 0.6, 0.12), WARD + Vector((-0.8, 0, 0.66)), s3d.mat("Pillow", (1, 1, 1), rough=0.8))
s3d.box("Blanket", (1.3, 0.98, 0.08), WARD + Vector((0.35, 0, 0.62)), s3d.mat("Blanket", (0.2, 0.5, 0.75), rough=0.9))
s3d.cylinder("Drip", 0.015, 1.9, WARD + Vector((-1.2, 0.6, 0.95)), mat=s3d.mat_steel())
s3d.box("DripBag", (0.14, 0.04, 0.22), WARD + Vector((-1.2, 0.6, 1.8)), s3d.mat("Bag", (0.85, 0.92, 1.0), rough=0.1))
s3d.box("Monitor", (0.45, 0.25, 0.35), WARD + Vector((-1.45, 0.9, 1.4)), s3d.mat("MonBody", (0.15, 0.15, 0.17)))
s3d.box("MonScreen", (0.38, 0.02, 0.27), WARD + Vector((-1.45, 0.77, 1.4)), s3d.mat_emit("MonScr", (0.05, 0.8, 0.4), 2.5))
pat2 = human.Human("Patient2", loc=WARD + Vector((0, -0.8, 0)), facing=0, outfit=dict(shirt=(0.05, 0.45, 0.85), pants=(0.15, 0.15, 0.2),
                                                                                  shoes=(0.9, 0.9, 0.9), hat=None), seed=0)
pat2.lie(40, hip=WARD + Vector((-0.05, 0, 0.78)), head_dir=-1, sit=10, dur=16)
doc = human.Human("Doctor", loc=WARD + Vector((0.4, -0.95, 0)), facing=-25, outfit=human.SCIENTIST, seed=1)
syr = s3d.cylinder("Syringe", 0.012, 0.14, (0, 0, 0), rot=(math.radians(90), 0, 0), mat=s3d.mat("SyrM", (0.85, 0.95, 1.0), rough=0.1))
syr.parent = doc.arm
syr.parent_type = "BONE"
syr.parent_bone = "hand.R"
syr.location = (0, 0.08, 0)
clinic_key = area("ClinicKey", C + Vector((0, -3, 3.5)), C + Vector((0, 1.2, 1)), 1400, size=6)
clinic_fill = area("ClinicFill", C + Vector((-5, -2, 2)), C + Vector((-3, 1.2, 1)), 300, size=3, color=(0.8, 0.9, 1.0))

# ================================================================= the story, beat by beat
F = {i: (B[i]["fs"], B[i + 1]["fs"] if i + 1 < len(B) else END) for i in range(len(B))}

# beat 0 — the question: the guy thinks, then looks up
guy.pose_at(1, "think")
guy.hold(1, W(0, "мозок"))
guy.pose_at(W(0, "запрацює"), "shrug")
guy.hold(W(0, "запрацює") + 1, F[0][1])

# beat 1 — "10 %": only one region glows
f1 = W(1, "десять")
neuron(0, f1, 9.0)
neuron(0, F[2][0] + 2, 9.0)
tag("10%", BR + Vector((0, -0.13, 0.115)), f1 - 6, hold=F[2][0] - f1 + 4, size=0.04)
s3d.marker("whoosh", F[1][0], prompt="soft cinematic whoosh into a glowing x-ray view", gain=-8)
s3d.marker("ding", f1, prompt="soft electric spark of a single glowing neuron lighting up", gain=-6)

# beat 2 — myth (brain), the scanner, then nearly every region over a day
f_myth = W(2, "міф")
f_scan = W(2, "сканері", -6)
f_day = W(2, "працюють", -6)
neuron(0, f_myth, 0.15, dur=6)
tag("МІФ", BR + Vector((0, -0.13, 0.115)), f_myth, hold=f_scan - f_myth - 4, size=0.04, color=(0.6, 0.05, 0.05))
s3d.marker("thud", f_myth, prompt="deep bass hit, a myth busted, short impact", gain=-6)
s3d.marker("heavy", f_scan, prompt="MRI scanner loud rhythmic knocking and humming", gain=-10, seconds=3)
order = [0, 2, 4, 6, 8, 10, 1, 3, 5, 7, 9, 11]
for k, ri in enumerate(order):
    neuron(ri, f_day + 2 + k * 4, 7.0, color=(1.0, 0.75, 0.3))
s3d.marker("ding", f_day + 4, prompt="rapid sequence of soft electric sparkles, neurons lighting up one after another", gain=-8, seconds=2)

# beat 3 — not all at once: regions take turns
f3 = F[3][0]
all_neurons(f3 + 3, 0.15, dur=3)
for k in range(int((F[3][1] - f3) / 9)):
    fr = f3 + 6 + k * 9
    ri = (k * 5) % len(REGIONS)
    neuron(ri, fr, 9.0, dur=3)
    neuron(ri, fr + 8, 0.15, dur=5)
s3d.marker("ding", f3 + 6, prompt="gentle rhythmic electrical blips, calm brain activity", gain=-10, seconds=4)

# beat 4 — imagine all of them at once
f4 = W(4, "спалахнули", -4)
all_neurons(F[4][0] + 2, 0.15)
all_neurons(f4 + 3, 28.0, color=(1.0, 0.95, 0.8))
s3d.marker("whoosh", F[4][0], prompt="deep cinematic whoosh into an x-ray view", gain=-8)
s3d.marker("heavy", f4, prompt="massive electric surge, crackling high voltage burst, rising", gain=-4, seconds=2.5)

# beat 5 — signals mix, muscles twitch, consciousness fades (room)
f5 = F[5][0]
guy.pose_at(f5, "stand")
guy.act(f5 + 4, "scared", cycles=int((W(5, "свідомість") - f5) / 16) + 1, period=16)
f_fade = W(5, "гасне")
guy.pose_at(f_fade - 6, "sit")
s3d.light_level(room_red, f5 + 2, 0)
for k in range(0, F[5][1] - f5, 8):
    s3d.light_level(room_red, f5 + 4 + k, 250 if k % 16 == 0 else 40, dur=2)
s3d.light_level(room_key, f_fade - 8, 600)
s3d.light_level(room_key, f_fade + 10, 15, dur=14)
s3d.light_level(room_fill, f_fade - 8, 180)
s3d.light_level(room_fill, f_fade + 10, 5, dur=14)
s3d.light_level(room_red, F[5][1] - 2, 0, dur=8)
s3d.marker("crack", f5 + 2, prompt="chaotic electrical static crackling, buzzing interference", gain=-6, seconds=3)
s3d.marker("whoosh", f_fade, prompt="sound fading out into muffled silence, low drone", gain=-6, seconds=2)

# beat 6 — a seizure looks a bit like that: chaotic red flashes in the brain
f6 = F[6][0]
all_neurons(f6 - 1, 2.0, color=(1.0, 0.15, 0.08), dur=1)
for k in range(int((F[6][1] - f6) / 4)):
    fr = f6 + 2 + k * 4
    for ri in range(len(REGIONS)):
        neuron(ri, fr, rnd.choice((2, 6, 18, 30)), dur=2)
tag("ЕПІЛЕПСІЯ", BR + Vector((0, -0.14, -0.1)), W(6, "епілептичного", -4), hold=F[6][1] - W(6, "епілептичного") - 2, size=0.03, color=(0.6, 0.05, 0.05))
s3d.marker("heavy", f6, prompt="tense pulsing electrical storm, distorted crackle", gain=-6, seconds=3)

# beat 7 — doctors and medicine: ward, then the brain calms down in blue
f7 = F[7][0]
f7b = W(7, "гальмують", -6)
doc.pose_at(f7, "stand")
doc.pose_at(f7 + 14, "point")
doc.hold(f7 + 15, f7b)
for k in range(0, f7b - f7, 24):
    s3d.marker("ding", f7 + k, prompt="hospital heart monitor beep", gain=-12) if k == 0 else None
all_neurons(f7b - 2, 10.0, color=(1.0, 0.2, 0.1), dur=2)
for k, ri in enumerate(order):
    neuron(ri, f7b + 6 + k * 3, 1.2, color=(0.3, 0.6, 1.0), dur=10)
s3d.marker("whoosh", f7b, prompt="soothing soft whoosh, calming magical shimmer", gain=-8, seconds=2)

# beat 8 — 100 %, just in turns: brain calm-cycling, then the guy is fine
f8 = F[8][0]
f8b = W(8, "просто", -4)
guy.place(f8 - 1, R + Vector((0, 1.0, 0)), 0)
guy.pose_at(f8, "relieved")
guy.hold(f8 + 1, f8 + 40)
guy.pose_at(f8 + 50, "thumbs_up")
guy.hold(f8 + 51, END)
s3d.light_level(room_key, f8 - 1, 600, dur=1)
s3d.light_level(room_fill, f8 - 1, 180, dur=1)
tag("100%", R + Vector((0, 0.9, 2.15)), W(8, "сто", -4), hold=END, size=0.16)
for k in range(int((END - f8b) / 8)):
    fr = f8b + k * 8
    ri = (k * 7) % len(REGIONS)
    neuron(ri, fr, 8.0, color=(1.0, 0.8, 0.35), dur=3)
    neuron(ri, fr + 7, 1.0, dur=4)
s3d.marker("ding", f8 + 50, prompt="warm positive chime, resolved", gain=-8)

# ================================================================= cameras: hard cuts, slow push-ins
CAMS = []


def shot(name, start, target, frm, lens=50, fstop=4.0, push=0.08, end=None):
    c = bpy.data.cameras.new(name)
    c.lens = lens
    c.clip_start = 0.01
    c.clip_end = 60
    c.dof.use_dof = True
    c.dof.aperture_fstop = fstop
    o = bpy.data.objects.new(name, c)
    sc.collection.objects.link(o)
    t = Vector(target)
    end = end or start + 120
    for fr, k in ((start, 0.0), (end, push)):
        o.location = t + Vector(frm) * (1 - k)
        o.rotation_euler = (t - o.location).to_track_quat("-Z", "Y").to_euler()
        c.dof.focus_distance = (t - o.location).length
        o.keyframe_insert("location", frame=fr)
        o.keyframe_insert("rotation_euler", frame=fr)
        c.dof.keyframe_insert("focus_distance", frame=fr)
    for fc in s3d.fcurves(o) + s3d.fcurves(c):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    m = sc.timeline_markers.new(name, frame=start)
    m.camera = o
    CAMS.append(o)
    if sc.camera is None:
        sc.camera = o
    return o


GUY_HEAD = R + Vector((0, 1.0, 1.45))
shot("CamHook", 1, GUY_HEAD + Vector((0, 0, -0.15)), (0.35, -2.2, 0.15), lens=50, push=0.15, end=F[1][0])
shot("CamTen", F[1][0], BR, (0.3, -0.55, 0.12), lens=50, fstop=8, push=0.12, end=F[2][0])
shot("CamMyth", F[2][0], BR, (-0.35, -0.55, 0.05), lens=50, fstop=8, push=0.1, end=f_scan)
shot("CamMRI", f_scan, MRI + Vector((-1.0, 0, 1.0)), (-1.6, -3.2, 0.7), lens=35, fstop=5.6, push=0.1, end=f_day)
shot("CamDay", f_day, BR, (0.6, -0.12, 0.12), lens=50, fstop=8, push=0.1, end=F[3][0])
shot("CamTurns", F[3][0], BR, (0.35, -0.5, 0.3), lens=50, fstop=8, push=0.12, end=F[4][0])
cam_all = shot("CamAll", F[4][0], BR, (-0.2, -0.75, 0.08), lens=50, fstop=8, push=0.25, end=F[5][0])
shot("CamTwitch", F[5][0], R + Vector((0, 1.0, 1.15)), (0.0, -3.4, 0.25), lens=40, push=0.1, end=F[6][0])
shot("CamSeizure", F[6][0], BR + Vector((0, 0, -0.03)), (0.55, -0.5, 0.02), lens=50, fstop=8, push=0.12, end=F[7][0])
shot("CamWard", F[7][0], WARD + Vector((-0.2, 0, 0.9)), (0.9, -2.8, 0.9), lens=35, fstop=4, push=0.1, end=f7b)
shot("CamCalm", f7b, BR, (-0.3, -0.55, 0.15), lens=50, fstop=8, push=0.1, end=f8)
shot("CamBrainEnd", f8, BR, (-0.5, -0.45, 0.15), lens=50, fstop=8, push=0.1, end=f8 + 45)
shot("CamEnd", f8 + 45, R + Vector((0, 1.0, 1.35)), (0.3, -3.0, 0.2), lens=45, push=0.1, end=END)
for t_ in TAGS:
    build_tag(*t_)
# a small camera shake on the surge
for f, dx in ((f4 + 1, 0), (f4 + 3, 0.006), (f4 + 5, -0.005), (f4 + 7, 0.003), (f4 + 10, 0)):
    sc.frame_set(f)
    cam_all.location.x = cam_all.matrix_world.to_translation().x + dx
    cam_all.keyframe_insert("location", index=0, frame=f)

# ================================================================= output
if MODE == "preview":
    s3d.qa_gate(abort=False)
    out = os.path.join(WORK, "preview")
    os.makedirs(out, exist_ok=True)
    frames = sorted(set(int(x) for x in os.environ.get("FRAMES", "").split(",") if x) or
                    [60, f1 + 10, f_myth + 10, f_scan + 20, f_day + 50, F[3][0] + 40, f4 + 10, W(5, "м'язи"),
                     f_fade + 20, F[6][0] + 30, F[7][0] + 30, f7b + 40, f8 + 20, END - 10])
    sc.cycles.samples = int(os.environ.get("SAMPLES", "16"))
    for fr in frames:
        s3d.preview_still(os.path.join(out, f"f{fr:04d}.png"), frame=fr, scale=int(os.environ.get("SCALE", "30")))
    s3d.export_markers(os.path.join(WORK, "render.sfx.json"))
else:
    s3d.render_mp4(os.path.join(WORK, "render.mp4"), scale=int(os.environ.get("SCALE", "50" if MODE == "half" else "100")))
