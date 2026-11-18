"""Сонний параліч — vertical 3D short (stylised little people, night bedroom, X-ray, three cultures, Fuseli, 1 in 13).

  blender --background --python build.py -- <workdir> [preview|half|full]
  (or with the bpy module: python build.py -- <workdir> [preview|half|full])
<workdir> must contain beats.json. Output: render.mp4 + render.sfx.json, or preview/f####.png stills.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_scripts(here):
    import glob
    for c in (os.environ.get("KYLO_SCRIPTS", ""), os.path.join(here, "..", "..", "scripts"), os.path.join(here, "scripts")):
        if c and os.path.exists(os.path.join(c, "s3d.py")):
            return os.path.abspath(c)
    pats = ("~/.claude/plugins/cache/*/kylo-3d-shorts/*/skills/3d-short/scripts",
            "~/.claude/plugins/synced/*/kylo-3d-shorts/skills/3d-short/scripts")
    for p in pats:
        hits = sorted(glob.glob(os.path.expanduser(p)))
        if hits:
            return hits[-1]
    raise SystemExit("set KYLO_SCRIPTS=<plugin>/skills/3d-short/scripts")


sys.path.insert(0, _find_scripts(HERE))
import bpy  # noqa: E402
from mathutils import Euler, Vector  # noqa: E402
import s3d  # noqa: E402
import human  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["."]
WORK = os.path.abspath(argv[0])
MODE = argv[1] if len(argv) > 1 else "full"
B = s3d.load_beats(os.path.join(WORK, "beats.json"))
END = B[-1]["fe"] + 45
W = lambda i, word=None, off=0: s3d.when(B, i, word, off)  # noqa: E731
BS = lambda i: B[i]["fs"]  # noqa: E731

s3d.new_short(seconds=END / 30, sky=None)
sc = bpy.context.scene
sc.frame_end = END
if hasattr(sc.render, "motion_blur_position"):
    sc.render.motion_blur_position = "START"
for n in ("Sun", "Fill"):
    o = bpy.data.objects.get(n)
    if o:
        bpy.data.objects.remove(o, do_unlink=True)
s3d.sky_world(top=(0.004, 0.006, 0.014), horizon=(0.01, 0.014, 0.03), strength=1.0)
sc.view_settings.exposure = -0.2
sc.eevee.use_raytracing = os.environ.get("RT", "0") == "1"
if hasattr(sc.eevee, "use_fast_gi"):
    sc.eevee.use_fast_gi = False

CAMS = []


def light(name, kind, loc, energy, size=1.0, color=(1, 1, 1), aim=None, spot=None):
    d = bpy.data.lights.new(name, kind)
    d.energy = energy
    d.color = color
    if kind == "AREA":
        d.size = size
    if kind == "SPOT" and spot:
        d.spot_size = math.radians(spot)
        d.spot_blend = 0.4
    if kind in ("POINT", "SPOT"):
        d.shadow_soft_size = size
    o = bpy.data.objects.new(name, d)
    sc.collection.objects.link(o)
    o.location = loc
    if aim is not None:
        o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


def shot(name, start, keys, lens=35, fstop=4.0):
    """Hard-cut camera bound to a timeline marker. keys = [(frame, target, offset)], linear/eased moves between."""
    c = bpy.data.cameras.new(name)
    c.lens = lens
    c.clip_start = 0.02
    c.clip_end = 200
    c.dof.use_dof = True
    c.dof.aperture_fstop = fstop
    o = bpy.data.objects.new(name, c)
    sc.collection.objects.link(o)
    for fr, target, off in keys:
        t = Vector(target)
        o.location = t + Vector(off)
        o.rotation_euler = (t - o.location).to_track_quat("-Z", "Y").to_euler()
        c.dof.focus_distance = (t - o.location).length
        o.keyframe_insert("location", frame=fr)
        o.keyframe_insert("rotation_euler", frame=fr)
        c.dof.keyframe_insert("focus_distance", frame=fr)
    for fc in s3d.fcurves(o) + s3d.fcurves(c):
        for k in fc.keyframe_points:
            k.interpolation = "SINE"
            k.easing = "EASE_IN_OUT"
    m = sc.timeline_markers.new(name, frame=start)
    m.camera = o
    CAMS.append(o)
    return o


def H(name, scale=1.0, **kw):
    h = human.Human(name, **kw)
    h.arm.scale = (scale,) * 3
    return h


def recolor(person, mat, eye_mat=None, keep=()):
    for p in person.parts:
        if any(k in p.name for k in keep):
            continue
        p.data.materials.clear()
        p.data.materials.append(eye_mat if (eye_mat and "pupil" in p.name) else mat)


def eyes(person):
    return [p for p in person.parts if p.get("blink")]


def eyes_keys(person, keys):
    """keys = [(frame, z_scale)] — 0.08 closed, 1 open, 1.3 wide. Replaces the automatic blinks."""
    for e in eyes(person):
        e.animation_data_clear()
        for fr, s in keys:
            e.scale = (1, 1, s)
            e.keyframe_insert("scale", frame=fr)


def blinks(f0, f1, step=70):
    out, f = [], f0
    while f + 5 < f1:
        out += [(f, 1.0), (f + 2, 0.08), (f + 4, 1.0)]
        f += step
    return out


def place_lying(person, frame, hip, rot_deg):
    """Root of a lying person so that its hips sit at `hip` with rotation rot_deg (XYZ euler degrees)."""
    q = Euler([math.radians(a) for a in rot_deg]).to_quaternion()
    person.arm.rotation_euler = q.to_euler("XYZ", person.arm.rotation_euler)
    person.arm.location = Vector(hip) - q @ Vector((0, 0, 0.94)) * person.arm.scale.x
    s3d._key(person.arm, frame, loc=True, rot=True)


human.POSES.update({
    "lie_flat": {"upper_arm": (0, 9, 0), "forearm": (6, 0, 0), "hand": (0, 0, 0), "thigh": (0, 3, 0), "shin": (0, 0, 0), "head": (-4, 0, 0)},
    "lie_tense": {"upper_arm": (0, 11, 0), "forearm": (10, 0, 0), "hand": (14, 0, 0), "thigh": (0, 3, 0), "shin": (0, 0, 0), "head": (-10, 0, 0)},
    "sit_bed": {"thigh": (88, 4, 0), "shin": (0, 0, 0), "foot": (-10, 0, 0), "upper_arm": (14, 12, 0), "forearm": (30, 0, 0), "spine": (6, 0, 0), "head": (6, 0, 0)},
    "sit_relief": {"thigh": (88, 4, 0), "shin": (0, 0, 0), "foot": (-10, 0, 0), "upper_arm": (8, 24, 0), "forearm": (25, 0, 0), "spine": (-6, 0, 0), "head": (-14, 0, 0)},
    "lurk": {"spine": (14, 0, 0), "neck": (10, 0, 0), "head": (16, 0, 0), "upper_arm": (6, 6, 0), "forearm": (10, 0, 0), "hand": (10, 0, 0)},
    "lurk_reach": {"spine": (20, 0, 0), "neck": (12, 0, 0), "head": (18, 0, 0), "upper_arm.R": (55, 8, 0), "forearm.R": (12, 0, 0),
                   "upper_arm.L": (10, 6, 0), "forearm.L": (10, 0, 0)},
    "perch": {"spine": (30, 0, 0), "head": (10, 0, 0), "thigh": (95, 18, 0), "shin": (-140, 0, 0), "foot": (40, 0, 0),
              "upper_arm": (60, 18, 0), "forearm": (70, 0, 0)},
    "faint": {"upper_arm.R": (0, 10, 0), "forearm.R": (4, 0, 0), "upper_arm.L": (-40, 70, 0), "forearm.L": (5, 0, 0),
              "thigh": (6, 3, 0), "shin": (-10, 0, 0), "head": (-45, 0, -15), "spine": (-8, 0, 0)},
})

# ================================================================= materials
WALL = s3d.mat("Wall", (0.16, 0.18, 0.25), rough=0.9, noise=0.25, noise_scale=6)
FLOOR = s3d.mat("Floor", (0.30, 0.20, 0.13), rough=0.6, noise=0.5, noise_scale=14)
WOOD = s3d.mat("BedWood", (0.32, 0.20, 0.12), rough=0.5, noise=0.3)
SHEET = s3d.mat("Sheet", (0.80, 0.82, 0.86), rough=0.9, noise=0.15, noise_scale=12)
BLANKET = s3d.mat("Blanket", (0.20, 0.28, 0.50), rough=0.95, noise=0.35, noise_scale=10)
SHADOW = s3d.mat_emit("Shadow", (0.0, 0.0, 0.0), 0.0)
GLOW_EYE = s3d.mat_emit("ShadowEyes", (1.0, 0.85, 0.75), 4.0)
PJ = dict(shirt=(0.36, 0.46, 0.66), pants=(0.28, 0.30, 0.38), shoes=(0.75, 0.62, 0.52), hat=None)
SHADOW_FIT = dict(shirt=(0.01, 0.01, 0.01), pants=(0.01, 0.01, 0.01), shoes=(0.01, 0.01, 0.01), hat=None)

# ================================================================= ZONE A: the bedroom (x = 0)
room = s3d.hollow_box("Room", (4.0, 4.0, 2.8), wall=0.08, loc=(0, 2.0, 1.32), mat=WALL)
floor = s3d.box("FloorBoards", (3.84, 3.9, 0.02), (0, 2.0, 0.0), FLOOR, bevel=0)
# window on the left wall: cold moonlight
WIN = Vector((-1.91, 2.0, 1.55))
pane_m = s3d.mat_emit("MoonPane", (0.55, 0.68, 1.0), 2.2)
pane = s3d.box("WindowPane", (0.02, 1.0, 1.15), WIN, pane_m, bevel=0)
frame_m = s3d.mat("WinFrame", (0.75, 0.75, 0.78), rough=0.5)
for dy, dz, sx in ((0, 0.6, (0.06, 1.12, 0.06)), (0, -0.6, (0.06, 1.12, 0.06)), (0, 0, (0.05, 1.0, 0.04)),
                   (0.53, 0, (0.06, 0.06, 1.26)), (-0.53, 0, (0.06, 0.06, 1.26)), (0, 0, (0.05, 0.04, 1.15))):
    s3d.box("WinBar", sx, WIN + Vector((0.02, dy, dz)), frame_m, bevel=0.005)
curtain_m = s3d.mat("Curtain", (0.22, 0.12, 0.20), rough=0.95, noise=0.4, noise_scale=20)
for dy in (-0.72, 0.72):
    s3d.box("Curtain", (0.06, 0.32, 1.7), WIN + Vector((0.06, dy, -0.05)), curtain_m, bevel=0.03)
moon = light("MoonKey", "AREA", (-1.6, 2.0, 1.7), 160, 1.0, (0.55, 0.66, 1.0), aim=(0.4, 2.9, 0.6))
moon2 = light("MoonCorner", "AREA", (-0.8, 1.2, 2.5), 40, 1.5, (0.45, 0.55, 1.0), aim=(-1.5, 3.7, 1.4))
fill = light("NightFill", "AREA", (0.6, -1.5, 2.2), 14, 3.0, (0.5, 0.6, 1.0), aim=(0.2, 2.8, 0.8))
# bed along +Y, headboard at the back wall
BX, HIPY, MT = 0.35, 2.75, 0.55
bed = [s3d.box("BedFrame", (1.15, 2.15, 0.33), (BX, 2.65, 0.165), WOOD, bevel=0.02),
       s3d.box("Headboard", (1.15, 0.08, 0.95), (BX, 3.76, 0.47), WOOD, bevel=0.02),
       s3d.box("Mattress", (1.05, 2.05, 0.22), (BX, 2.65, 0.44), SHEET, bevel=0.06),
       s3d.box("Pillow", (0.62, 0.38, 0.1), (BX, 3.48, 0.57), SHEET, bevel=0.06),
       s3d.box("Blanket", (1.12, 1.0, 0.36), (BX, 2.0, 0.64), BLANKET, bevel=0.09)]
stand = s3d.box("Nightstand", (0.45, 0.4, 0.5), (1.25, 3.55, 0.25), WOOD, bevel=0.02)
clock_m = s3d.mat_emit("ClockDigits", (1.0, 0.2, 0.12), 3.0)
clock = s3d.box("Clock", (0.2, 0.08, 0.1), (1.25, 3.5, 0.55), s3d.mat("ClockBody", (0.05, 0.05, 0.05)), bevel=0.01)
s3d.box("ClockFace", (0.15, 0.01, 0.05), (1.25, 3.455, 0.555), clock_m, bevel=0)
wardrobe = s3d.box("Wardrobe", (0.6, 0.9, 2.0), (-1.6, 0.7, 1.0), WOOD, bevel=0.02)
s3d.box("Rug", (1.4, 1.0, 0.012), (-0.6, 1.6, 0.01), s3d.mat("Rug", (0.35, 0.10, 0.10), rough=1, noise=0.5, noise_scale=30), bevel=0)

# the sleeper (head +Y, face up)
guy = human.Human("Sleeper", loc=(0, 0, 0), facing=0, outfit=PJ, seed=2)
for p in guy.parts:
    if "_shoe" in p.name or "_sole" in p.name:
        p.hide_render = True
HIP = (BX, HIPY, MT + 0.11)
LIE = (-90, 0, 0)
place_lying(guy, 1, HIP, LIE)
guy.pose_at(1, "lie_flat")
guy.hold(1, W(1, "руки", -2))
f_open = W(1, "розплющуєш")
# hands try to move but only tremble
f_hand = W(1, "руки")
for k in range(16):
    guy.pose_at(f_hand + k * 3, "lie_tense" if k % 2 else "lie_flat", blend=("lie_tense", 0.5) if k % 2 == 0 else None)
guy.pose_at(f_hand + 50, "lie_tense")
guy.hold(f_hand + 50, BS(9) - 1)
# morning: he sits up and breathes out
f_up = W(9, "кількох", -6)
place_lying(guy, BS(9), HIP, LIE)
guy.pose_at(BS(9), "lie_tense")
n = 8
q0 = Euler([math.radians(a) for a in LIE]).to_quaternion()
q1 = Euler((0, 0, 0)).to_quaternion()
sit_hip = Vector((BX, HIPY - 0.05, MT + 0.1))
for k in range(1, n + 1):
    t = k / n
    te = t * t * (3 - 2 * t)
    q = q0.slerp(q1, te)
    guy.arm.rotation_euler = q.to_euler("XYZ", guy.arm.rotation_euler)
    guy.arm.location = Vector(HIP).lerp(sit_hip, te) - q @ Vector((0, 0, 0.94))
    fr = f_up + int(round(22 * t))
    s3d._key(guy.arm, fr, loc=True, rot=True)
    guy.pose_at(fr, "lie_flat", blend=("sit_bed", te))
guy.pose_at(W(9, "минає", -4), "sit_relief")
guy.hold(W(9, "минає", -4), END)
eyes_keys(guy, [(1, 0.08), (f_open - 1, 0.08), (f_open + 3, 1.0), (W(2, "кутку", -1), 1.0), (W(2, "кутку", 3), 1.35),
                (BS(3) - 1, 1.35), (BS(9), 0.08), (f_up - 1, 0.08), (f_up + 3, 1.0)] + blinks(f_up + 30, END, 60))
s3d.marker("tick", 2, prompt="quiet clock ticking in a silent dark bedroom at night", gain=-10, seconds=10)
s3d.marker("gasp", f_open, prompt="sharp frightened inhale, eyes snapping open in the dark", gain=-6)

# the dark figure in the corner
fig = human.Human("Figure", loc=(-1.45, 3.55, 0), facing=55, outfit=SHADOW_FIT, seed=3)
fig.arm.scale = (1.05, 1.05, 1.18)
recolor(fig, SHADOW, GLOW_EYE)
for p in fig.parts:
    if "_eye" in p.name:
        p.hide_render = True
fig.pose_at(1, "lurk")
fig.hold(1, W(5, "домальовує"))
fig.hide_until(W(2, "кутку", -3))
f_dream = W(5, "домальовує")
fig.place(f_dream, (-1.45, 3.55, 0), 55)
fig.pose_at(f_dream, "lurk")
fig.place(f_dream + 55, (-0.75, 3.35, 0), 45)
fig.pose_at(f_dream + 55, "lurk_reach")
fig.hold(f_dream + 55, BS(6))
fig.hide_from(BS(6))
s3d.marker("whoosh", W(2, "кутку"), prompt="low eerie breathy whoosh, a dark presence appears in a dark room", gain=-3)
s3d.marker("drone", W(5, "домальовує"), prompt="creeping low horror drone swelling, distorted whispers", gain=-6, seconds=4)

# the creature on the chest
imp = H("Imp", loc=(BX, HIPY + 0.32, MT + 0.02), facing=0, outfit=SHADOW_FIT, seed=5, scale=0.42)
recolor(imp, SHADOW, GLOW_EYE)
for p in imp.parts:
    if "_eye" in p.name:
        p.hide_render = True
imp.pose_at(1, "perch")
imp.hold(1, BS(3))
f_chest = W(2, "груди")
s3d.slide_in(imp.arm, f_chest - 2, offset=(0, 0, 0.7), dur=10, sfx="thud", prompt="heavy soft thump on a mattress, something lands on a chest")
imp.hide_from(BS(3))
fig_ret = W(5, "домальовує")  # the imp comes back with the dream
imp.place(fig_ret + 20, (BX, HIPY + 0.32, MT + 0.02), 0)
imp.pose_at(fig_ret + 20, "perch")
imp.hold(fig_ret + 20, BS(6))
for x in [imp.arm] + list(imp.arm.children_recursive):
    if x.get("s3d_always_hidden"):
        continue
    x.hide_render = True
    x.keyframe_insert("hide_render", frame=fig_ret + 19)
    x.hide_render = False
    x.keyframe_insert("hide_render", frame=fig_ret + 20)
    x.hide_render = True
    x.keyframe_insert("hide_render", frame=BS(6))
s3d.marker("pressure", f_chest + 6, prompt="deep muffled heartbeat with heavy pressure, tense", gain=-4, seconds=3)

# dream light: purple glow swells over the bed when the brain "paints the dream" into the room
dream = light("DreamGlow", "POINT", (BX, 3.2, 1.3), 0, 0.6, (0.65, 0.25, 1.0))
dream.data.keyframe_insert("energy", frame=f_dream - 2)
dream.data.energy = 140
dream.data.keyframe_insert("energy", frame=f_dream + 30)
dream.data.keyframe_insert("energy", frame=BS(6) - 1)
dream.data.energy = 0
dream.data.keyframe_insert("energy", frame=BS(6))

# dawn (beat 9): warm window, warm key, cool off
for ob, col_n, col_d, e_n, e_d in ((moon, (0.55, 0.66, 1.0), (1.0, 0.72, 0.45), 160, 380),
                                   (moon2, (0.45, 0.55, 1.0), (1.0, 0.8, 0.6), 40, 120),
                                   (fill, (0.5, 0.6, 1.0), (1.0, 0.85, 0.7), 14, 50)):
    ob.data.color = col_n
    ob.data.energy = e_n
    ob.data.keyframe_insert("color", frame=BS(9) - 1)
    ob.data.keyframe_insert("energy", frame=BS(9) - 1)
    ob.data.color = col_d
    ob.data.energy = e_d
    ob.data.keyframe_insert("color", frame=BS(9))
    ob.data.keyframe_insert("energy", frame=BS(9))
pe = next(nd for nd in pane_m.node_tree.nodes if nd.type == "EMISSION")
for fr, col, st in ((BS(9) - 1, (0.55, 0.68, 1.0), 2.2), (BS(9), (1.0, 0.75, 0.45), 6.0)):
    pe.inputs["Color"].default_value = (*col, 1)
    pe.inputs["Strength"].default_value = st
    pe.inputs["Color"].keyframe_insert("default_value", frame=fr)
    pe.inputs["Strength"].keyframe_insert("default_value", frame=fr)
s3d.marker("birds", BS(9) + 4, prompt="soft early morning birdsong through a window, calm", gain=-8, seconds=6)
s3d.marker("exhale", W(9, "минає"), prompt="long relieved exhale of a person sitting up in bed", gain=-4)

# ================================================================= ZONE B: X-ray (x = 40)
XR = Vector((40, 0, 0))
bpy.ops.mesh.primitive_uv_sphere_add(radius=6.0, location=XR + Vector((0, 0, 1.0)), segments=48, ring_count=24)
void = bpy.context.active_object
void.name = "XrayVoid"
void.data.materials.append(s3d.mat_emit("Void", (0.008, 0.022, 0.07), 1.0))
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.flip_normals()
bpy.ops.object.mode_set(mode="OBJECT")


def mat_glass(name="XrayGlass", col=(0.18, 0.55, 1.0), strength=2.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 2.0
    nt.links.new(lw.outputs["Facing"], pw.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*col, 1)
    em.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    add.inputs[1].default_value = 0.04
    nt.links.new(pw.outputs[0], add.inputs[0])
    nt.links.new(add.outputs[0], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND"), ("use_backface_culling", True)):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    return m


GLASS = mat_glass()
MUSCLE = s3d.mat_emit("Muscle", (1.0, 0.16, 0.10), 2.2)
xr = human.Human("Xray", loc=(0, 0, 0), facing=0, outfit=PJ, seed=2)
XHIP = XR + Vector((0, 0.2, 0.6))
place_lying(xr, 1, XHIP, LIE)
xr.pose_at(1, "lie_flat")
xr.hold(1, END)
LIMBS = ("upperarm", "forearm", "thigh", "shin", "hand", "thumb")
for p in xr.parts:
    p.data.materials.clear()
    nm = p.name.split("_", 1)[1].split(".")[0]
    if nm in LIMBS:
        p.data.materials.append(MUSCLE)
        p.scale = p.scale * 0.8 if nm in ("hand", "thumb") else p.scale
    elif nm in ("torso", "head", "neck", "pelvis"):
        p.data.materials.append(GLASS)
    else:
        p.hide_render = True
# limb glass skins (slightly bigger copies of the limbs around the red muscle)
for p in list(xr.parts):
    nm = p.name.split("_", 1)[1].split(".")[0]
    if nm in ("upperarm", "forearm", "thigh", "shin"):
        c = p.copy()
        c.data = p.data.copy()
        c.data.materials.clear()
        c.data.materials.append(GLASS)
        sc.collection.objects.link(c)
        c.scale = c.scale * 1.0
        p.scale = p.scale * 0.72
bpy.context.view_layer.update()
sc.frame_set(1)
hb = xr.arm.pose.bones["head"]
HEADW = xr.arm.matrix_world @ ((hb.head + hb.tail) / 2)
NECKW = xr.arm.matrix_world @ xr.arm.pose.bones["neck"].head
BRAIN_M = s3d.mat_emit("Brain", (1.0, 0.45, 0.65), 3.0)
bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=HEADW + Vector((0, 0.03, 0.01)), segments=32, ring_count=16)
brain = bpy.context.active_object
brain.name = "Brain"
brain.scale = (0.08, 0.095, 0.07)
d = brain.modifiers.new("Folds", "DISPLACE")
tx = bpy.data.textures.new("BrainFolds", "CLOUDS")
tx.noise_scale = 0.25
d.texture = tx
d.strength = 0.25
sub = brain.modifiers.new("Sub", "SUBSURF")
sub.levels = sub.render_levels = 2
bpy.ops.object.shade_smooth()
brain.data.materials.append(BRAIN_M)
# spinal cord: brain -> hips
CORD_M = s3d.mat_emit("Cord", (1.0, 0.8, 0.5), 2.0)
cord = s3d.cylinder("SpinalCord", 0.012, (NECKW - XHIP).length + 0.12, (NECKW + XHIP) / 2 + Vector((0, 0.02, 0.0)),
                    rot=(math.radians(90), 0, 0), mat=CORD_M, verts=12)
# the "switch": a cyan ring at the neck that blocks signals during REM sleep
LOCK_M = s3d.mat_emit("Lock", (0.25, 0.95, 1.0), 6.0)
bpy.ops.mesh.primitive_torus_add(major_radius=0.075, minor_radius=0.012, location=NECKW + Vector((0, -0.02, 0)), rotation=(math.radians(90), 0, 0))
lock = bpy.context.active_object
lock.name = "Lock"
lock.data.materials.append(LOCK_M)
f_off = W(3, "вимикає")
s3d.pop_in(lock, f_off, dur=10, sfx="zap", prompt="electric power-down click with a soft descending hum")
# muscles go dark when the brain switches them off
mem = next(nd for nd in MUSCLE.node_tree.nodes if nd.type == "EMISSION")
for fr, col, st in ((f_off + 4, (1.0, 0.16, 0.10), 2.2), (f_off + 22, (0.10, 0.18, 0.35), 0.6)):
    mem.inputs["Color"].default_value = (*col, 1)
    mem.inputs["Strength"].default_value = st
    mem.inputs["Color"].keyframe_insert("default_value", frame=fr)
    mem.inputs["Strength"].keyframe_insert("default_value", frame=fr)
# brain: dreaming pink -> awake gold on "свідомість"
bem = next(nd for nd in BRAIN_M.node_tree.nodes if nd.type == "EMISSION")
f_aw = W(4, "свідомість")
for fr, col, st in ((f_aw - 1, (1.0, 0.45, 0.65), 3.0), (f_aw + 8, (1.0, 0.85, 0.3), 9.0)):
    bem.inputs["Color"].default_value = (*col, 1)
    bem.inputs["Strength"].default_value = st
    bem.inputs["Color"].keyframe_insert("default_value", frame=fr)
    bem.inputs["Strength"].keyframe_insert("default_value", frame=fr)
s3d.marker("shimmer", f_aw, prompt="bright magical shimmer rising, mind waking up", gain=-5)
# signals: glowing pulses run from the brain down the cord; after the lock they stop at the ring
SIG_M = s3d.mat_emit("Signal", (1.0, 0.95, 0.6), 12.0)
for k, f0 in enumerate(range(BS(3) + 4, BS(5), 26)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.022, location=HEADW, segments=12, ring_count=8)
    s = bpy.context.active_object
    s.name = f"Signal{k}"
    s.data.materials.append(SIG_M)
    blocked = f0 > f_off
    end = NECKW if blocked else XHIP
    dur = 10 if blocked else 22
    s.location = HEADW
    s.keyframe_insert("location", frame=f0)
    s.location = end
    s.keyframe_insert("location", frame=f0 + dur)
    s3d._hide_before(s, f0)
    s3d.hide_at(s, f0 + dur + (4 if blocked else 1))
    if blocked and k % 2 == 0:
        s3d.marker("blip", f0 + dur, prompt="tiny electric blip bouncing off a barrier", gain=-10)
light("XKey", "AREA", XR + Vector((1.2, -0.6, 2.4)), 40, 1.5, (0.8, 0.9, 1.0), aim=XHIP)

# ================================================================= ZONE C: three cultures (x = 80)
CU = Vector((80, 0, 0))
CULT = [("ЯПОНІЯ", "канашібарі", (0.78, 0.68, 0.50), (0.85, 0.20, 0.18)),
        ("КАНАДА", "Стара Відьма", (0.42, 0.26, 0.15), (0.20, 0.42, 0.22)),
        ("УКРАЇНА", "домовик душить", (0.88, 0.88, 0.84), (0.20, 0.35, 0.75))]
DIO = []
floor2 = s3d.box("CultFloor", (12, 6, 0.1), CU + Vector((0, 2, -0.05)), s3d.mat("Stage", (0.05, 0.05, 0.07), rough=0.7), bevel=0)
for i, (country, word, wall_c, bl_c) in enumerate(CULT):
    c = CU + Vector(((i - 1) * 2.6, 0, 0))
    wm = s3d.mat(f"DioWall{i}", wall_c, rough=0.9, noise=0.3, noise_scale=8)
    s3d.box(f"DioBack{i}", (2.0, 0.08, 1.9), c + Vector((0, 1.9, 0.95)), wm, bevel=0.01)
    s3d.box(f"DioSide{i}", (0.08, 1.4, 1.9), c + Vector((-1.0, 1.2, 0.95)), wm, bevel=0.01)
    s3d.box(f"DioFloor{i}", (2.0, 1.5, 0.06), c + Vector((0, 1.2, 0.03)), FLOOR, bevel=0)
    if i == 0:   # shoji grid
        for gx in (-0.6, -0.2, 0.2, 0.6):
            s3d.box("Shoji", (0.03, 0.02, 1.8), c + Vector((gx, 1.85, 0.95)), WOOD, bevel=0)
        for gz in (0.5, 1.0, 1.5):
            s3d.box("Shoji", (1.95, 0.02, 0.03), c + Vector((0, 1.85, gz)), WOOD, bevel=0)
    if i == 1:   # log cabin
        for gz in range(6):
            s3d.cylinder("Log", 0.15, 2.0, c + Vector((0, 1.82, 0.15 + gz * 0.3)), rot=(0, math.radians(90), 0), mat=WOOD, verts=16)
    if i == 2:   # whitewashed hata with a blue trim and a rushnyk
        s3d.box("Trim", (2.0, 0.02, 0.12), c + Vector((0, 1.85, 0.12)), s3d.mat("BlueTrim", (0.12, 0.25, 0.65)), bevel=0)
        s3d.box("Rushnyk", (0.5, 0.02, 0.18), c + Vector((0.4, 1.84, 1.45)), s3d.mat("Rushnyk", (0.9, 0.9, 0.86)), bevel=0)
        s3d.box("RushnykRed", (0.5, 0.025, 0.04), c + Vector((0.4, 1.84, 1.4)), s3d.mat("RushRed", (0.75, 0.05, 0.05)), bevel=0)
    s = 0.55
    mt = 0.2 + 0.12
    s3d.box(f"DioBed{i}", (0.65, 1.3, 0.2), c + Vector((0.1, 1.15, 0.1 + 0.06)), WOOD if i != 0 else s3d.mat("Futon", (0.85, 0.85, 0.8)), bevel=0.02)
    s3d.box(f"DioBlanket{i}", (0.68, 0.62, 0.12), c + Vector((0.1, 0.82, 0.33)), s3d.mat(f"DioBl{i}", bl_c, rough=0.95, noise=0.3), bevel=0.04)
    sl = H(f"Sleeper{i}", loc=(0, 0, 0), facing=0, outfit=dict(PJ, shirt=bl_c), seed=i, scale=s)
    sl_hip = c + Vector((0.1, 1.15 + 0.15, mt + 0.06))
    place_lying(sl, 1, sl_hip, LIE)
    sl.pose_at(1, "lie_tense")
    eyes_keys(sl, [(1, 1.3)])
    im = H(f"Imp{i}", loc=c + Vector((0.1, 1.15 + 0.15 + 0.18, mt - 0.02)), facing=0, outfit=SHADOW_FIT, seed=5, scale=0.24)
    recolor(im, SHADOW, GLOW_EYE)
    for p in im.parts:
        if "_eye" in p.name:
            p.hide_render = True
    im.pose_at(1, "perch")
    light(f"DioLight{i}", "AREA", c + Vector((0.5, 0.0, 2.3)), 70, 1.2, (0.6, 0.7, 1.0), aim=c + Vector((0, 1.2, 0.3)))
    DIO.append(c)
    f_lab = W(6, ("Японії", "Канаді", "нас")[i])
    t1 = s3d.label(country, loc=c + Vector((0, -0.05, 2.2)), size=0.2)
    t2 = s3d.label(word, loc=c + Vector((0, -0.05, 1.95)), size=0.14, bg=False)
    s3d.pop_in(t1, f_lab, dur=8, sfx="pop")
    s3d.pop_in(t2, f_lab + 3, dur=8, sfx=None)
s3d.marker("chime", W(6, "домовик"), prompt="three soft bell chimes in a row", gain=-8)

# ================================================================= ZONE D: Fuseli's painting in a gallery (x = 120)
GA = Vector((120, 0, 0))
gwall = s3d.box("GalleryWall", (8, 0.1, 6), GA + Vector((0, 1.0, 1.5)), s3d.mat("GalWall", (0.12, 0.20, 0.20), rough=0.9, noise=0.2), bevel=0)
s3d.box("GalleryFloor", (8, 5, 0.1), GA + Vector((0, -1.0, -1.05)), s3d.mat("GalFloor", (0.25, 0.16, 0.10), rough=0.4, noise=0.4, noise_scale=12), bevel=0)
PW, PH = 1.9, 1.53
PC = GA + Vector((0, 0.9, 1.5))
gold = s3d.mat("Gold", (0.85, 0.62, 0.25), rough=0.3, metal=1.0, noise=0.2)
for dx, dz, sz in ((0, PH / 2 + 0.06, (PW + 0.24, 0.12, 0.12)), (0, -PH / 2 - 0.06, (PW + 0.24, 0.12, 0.12)),
                   (PW / 2 + 0.06, 0, (0.12, 0.12, PH + 0.24)), (-PW / 2 - 0.06, 0, (0.12, 0.12, PH + 0.24))):
    s3d.box("Frame", sz, PC + Vector((dx, -0.06, dz)), gold, bevel=0.02)
# the scene inside the frame (a shallow box behind the wall opening)
INS = PC + Vector((0, 0.9, 0))
cut = s3d.box("PaintingHole", (PW, 1.0, PH), PC + Vector((0, 0.1, 0)), bevel=0)
cut.hide_render = True
cut.display_type = "WIRE"
cut["s3d_always_hidden"] = 1
bm_ = gwall.modifiers.new("Hole", "BOOLEAN")
bm_.operation, bm_.object = "DIFFERENCE", cut
s3d.box("PaintBack", (PW + 0.4, 0.05, PH + 0.4), PC + Vector((0, 1.6, 0)), s3d.mat("Drape", (0.55, 0.10, 0.06), rough=0.9, noise=0.5, noise_scale=5), bevel=0)
for k in range(5):
    s3d.cylinder("Fold", 0.08, PH + 0.3, PC + Vector((-0.8 + k * 0.4, 1.52, 0)), mat=bpy.data.materials["Drape"], verts=16)
s3d.box("PaintFloor", (PW + 0.4, 1.6, 0.05), PC + Vector((0, 0.8, -PH / 2)), s3d.mat("PaintFloor", (0.10, 0.06, 0.04)), bevel=0)
pbed = s3d.box("PaintBed", (1.25, 0.7, 0.42), PC + Vector((-0.2, 0.75, -PH / 2 + 0.21)), s3d.mat("PaintSheet", (0.92, 0.88, 0.80), rough=0.9), bevel=0.06)
woman = H("Dreamer", loc=(0, 0, 0), facing=0, outfit=dict(shirt=(0.95, 0.93, 0.88), pants=(0.95, 0.93, 0.88), shoes=(0.85, 0.7, 0.6), hat=None), seed=2, scale=0.58)
WH = PC + Vector((0.1, 0.75, -PH / 2 + 0.42 + 0.07))
place_lying(woman, 1, WH, (-90, 0, -90))
woman.pose_at(1, "faint")
eyes_keys(woman, [(1, 0.08)])
dem = H("Incubus", loc=WH + Vector((0.2, -0.02, -0.2)), facing=0, outfit=dict(shirt=(0.08, 0.06, 0.05), pants=(0.08, 0.06, 0.05), shoes=(0.05, 0.04, 0.03), hat=None), seed=3, scale=0.3)
recolor(dem, s3d.mat("ImpSkin", (0.10, 0.08, 0.06), rough=0.8), GLOW_EYE)
dem.pose_at(1, "perch")
light("PaintIn", "AREA", PC + Vector((-0.4, 0.5, 0.65)), 90, 0.8, (1.0, 0.8, 0.6), aim=WH)
light("PaintKey", "SPOT", PC + Vector((0.8, -0.3, 1.4)), 600, 0.2, (1.0, 0.85, 0.65), aim=WH, spot=55)
light("GalSpot", "SPOT", PC + Vector((0, -1.6, 2.6)), 700, 0.3, (1.0, 0.9, 0.75), aim=PC, spot=42)
plaque = s3d.label("Генрі Фюзелі · «Нічний кошмар»", loc=PC + Vector((0, -0.25, PH / 2 + 0.13)), size=0.08)
yr = s3d.label("1781", loc=PC + Vector((0, -0.25, PH / 2 + 0.36)), size=0.2)
s3d.pop_in(yr, W(7, "1781"), dur=8, sfx="pop")
s3d.pop_in(plaque, W(7, "Фюзелі"), dur=8, sfx=None)
s3d.marker("brush", W(7, "намалював"), prompt="soft oil paint brush strokes on canvas", gain=-8)

# ================================================================= ZONE E: 1 in 13 (x = 160)
CR = Vector((160, 0, 0))
s3d.box("CrowdFloor", (10, 8, 0.1), CR + Vector((0, 3, -0.05)), s3d.mat("CrowdFloor", (0.04, 0.04, 0.05), rough=0.6), bevel=0)
ROWS = [(5, 0.0, 0.0), (4, 0.7, 0.3), (4, 1.4, 0.6)]
crowd = []
pal = [(0.75, 0.2, 0.15), (0.2, 0.45, 0.7), (0.3, 0.55, 0.3), (0.85, 0.65, 0.2), (0.55, 0.3, 0.6), (0.9, 0.9, 0.9), (0.25, 0.25, 0.3)]
k = 0
for n_, y, z in ROWS:
    if z > 0:
        s3d.box("Riser", (n_ * 0.62 + 0.4, 0.7, z), CR + Vector((0, y + 0.95, z / 2)), s3d.mat("Riser", (0.06, 0.06, 0.08)), bevel=0.02)
    for j in range(n_):
        x = (j - (n_ - 1) / 2) * 0.62
        p = human.Human(f"P{k}", loc=CR + Vector((x, y + 0.95, z)), facing=0,
                        outfit=dict(shirt=pal[k % len(pal)], pants=(0.15, 0.17, 0.25), shoes=(0.1, 0.08, 0.06), hat=None), seed=k)
        p.pose_at(1, "stand")
        p.hold(1, END)
        crowd.append(p)
        k += 1
ONE = crowd[7]
crowd_l = light("CrowdFill", "AREA", CR + Vector((0, -2.5, 3.0)), 220, 4.0, (0.6, 0.7, 1.0), aim=CR + Vector((0, 1.5, 1.0)))
f_one = W(8, "тринадцятою")
spot = light("OneSpot", "SPOT", ONE.arm.location + Vector((0, -0.6, 3.2)), 0, 0.1, (1.0, 0.88, 0.6), aim=ONE.arm.location + Vector((0, 0, 1.0)), spot=22)
spot.data.keyframe_insert("energy", frame=f_one - 1)
spot.data.energy = 1500
spot.data.keyframe_insert("energy", frame=f_one + 1)
crowd_l.data.keyframe_insert("energy", frame=f_one - 1)
crowd_l.data.energy = 45
crowd_l.data.keyframe_insert("energy", frame=f_one + 6)
ONE.pose_at(f_one + 4, "stand")
ONE.pose_at(f_one + 14, "scared")
ONE.hold(f_one + 14, END)
t13 = s3d.label("1 з 13", loc=CR + Vector((0, 0.2, 2.75)), size=0.26)
s3d.pop_in(t13, f_one + 6, dur=8, sfx=None)
s3d.marker("spotlight", f_one, prompt="heavy theatre spotlight switching on with a clunk", gain=-3)

# ================================================================= cameras (hard cuts)
HEAD = Vector((BX, HIPY + 0.73, MT + 0.2))
CHEST = Vector((BX, HIPY + 0.35, MT + 0.3))
FIGH = Vector((-1.45, 3.55, 1.7))
shot("CamWide", 1, [(1, (0.0, 2.9, 0.9), (0.9, -3.4, 1.9)), (BS(1), (0.1, 2.9, 0.85), (0.75, -2.7, 1.55))], lens=30, fstop=5.6)
shot("CamFace", BS(1), [(BS(1), HEAD, (0.12, -0.95, 0.75)), (BS(2), HEAD, (0.1, -0.78, 0.6))], lens=45, fstop=2.8)
f_cor = W(2, "кутку", -3)
shot("CamCorner", f_cor, [(f_cor, (-1.0, 3.3, 1.25), (1.9, -2.9, 0.15)), (W(2, "груди", -4), (-1.05, 3.3, 1.25), (1.65, -2.45, 0.12))], lens=32, fstop=4.0)
f_ch = W(2, "груди", -4)
shot("CamChest", f_ch, [(f_ch, CHEST + Vector((0, 0.15, 0.05)), (0.35, -1.25, 0.55)), (BS(3), CHEST + Vector((0, 0.15, 0.05)), (0.3, -1.05, 0.45))], lens=40, fstop=2.8)
shot("CamXray", BS(3), [(BS(3), XHIP + Vector((0, 0.15, 0)), (0.6, -1.5, 2.2)), (BS(4), XHIP + Vector((0, 0.25, 0)), (0.5, -1.25, 1.9))], lens=32, fstop=8)
shot("CamBrain", BS(4), [(BS(4), HEADW + Vector((0, -0.15, 0)), (0.55, -0.55, 0.6)), (BS(5), HEADW + Vector((0, -0.15, 0)), (0.45, -0.45, 0.48))], lens=40, fstop=8)
shot("CamDream", BS(5), [(BS(5), (-0.4, 3.0, 1.05), (1.6, -2.6, 0.5)), (BS(6), (-0.3, 3.1, 1.0), (1.2, -1.9, 0.35))], lens=30, fstop=4.0)
D0, D1, D2 = [c + Vector((0, 1.1, 0.75)) for c in DIO]
shot("CamCult", BS(6), [(BS(6), D0, (0.25, -2.9, 0.9)), (W(6, "Канаді", -14), D0, (0.2, -2.6, 0.8)), (W(6, "Канаді", -2), D1, (0.2, -2.6, 0.8)),
                        (W(6, "нас", -14), D1, (0.15, -2.4, 0.8)), (W(6, "нас", -2), D2, (0.15, -2.6, 0.8)), (W(6, "домовик", 6), D2, (0.1, -2.3, 0.7)),
                        (BS(7) - 1, CU + Vector((0, 1.1, 0.9)), (0, -6.8, 1.6))], lens=35, fstop=5.6)
shot("CamPainting", BS(7), [(BS(7), PC + Vector((0, 0, 0.2)), (0.0, -5.2, 0.2)), (BS(8), PC + Vector((0, 0, 0.1)), (0.0, -3.8, 0.1))], lens=40, fstop=5.6)
shot("CamCrowd", BS(8), [(BS(8), CR + Vector((0, 1.6, 1.3)), (0, -6.2, 1.2)), (f_one, CR + Vector((0, 1.6, 1.35)), (0, -5.6, 1.1)),
                         (BS(9), ONE.arm.location + Vector((0, 0, 1.4)), (0, -3.8, 0.6))], lens=35, fstop=5.6)
shot("CamDawn", BS(9), [(BS(9), (0.2, 2.9, 0.9), (0.6, -2.8, 1.5)), (END, (0.25, 2.9, 0.95), (0.5, -2.2, 1.25))], lens=30, fstop=5.6)
sc.camera = CAMS[0]

QA = []
if MODE == "preview":
    s3d.qa_gate(QA, abort=False)
    out = os.path.join(WORK, "preview")
    os.makedirs(out, exist_ok=True)
    frames = sorted(set(int(x) for x in os.environ.get("FRAMES", "").split(",") if x) or
                    [60, W(1, "руки", 10), W(2, "кутку", 12), W(2, "груди", 14), W(3, "вимикає", 30), W(4, "свідомість", 20),
                     W(5, "кімнату"), W(6, "Японії", 12), W(6, "нас", 14), W(7, "Фюзелі", 10), W(8, "тринадцятою", 20), W(9, "минає", 20)])
    scale = int(os.environ.get("PSCALE", "30"))
    for fr in frames:
        s3d.preview_still(os.path.join(out, f"f{fr:04d}.png"), frame=fr, scale=scale, samples=int(os.environ.get("PSAMPLES", "8")))
    s3d.export_markers(os.path.join(WORK, "render.sfx.json"))
elif MODE == "frames":
    # PNG sequence (every STEP-th frame) for slow CPU-only machines; ffmpeg turns it back into 30 fps
    s3d.qa_gate(QA)
    s3d.export_markers(os.path.join(WORK, "render.sfx.json"))
    sc.eevee.taa_render_samples = int(os.environ.get("SAMPLES", "8"))
    sc.render.resolution_percentage = int(os.environ.get("RSCALE", "50"))
    sc.frame_step = int(os.environ.get("STEP", "2"))
    sc.frame_start = int(os.environ.get("FSTART", "1"))
    sc.frame_end = int(os.environ.get("FEND", str(END)))
    sc.render.image_settings.file_format = "PNG"
    sc.render.use_overwrite = False
    sc.render.use_placeholder = True
    sc.render.filepath = os.path.join(WORK, "frames", "f")
    bpy.ops.render.render(animation=True)
else:
    if MODE == "half":
        sc.eevee.taa_render_samples = int(os.environ.get("SAMPLES", "12"))
    s3d.render_mp4(os.path.join(WORK, "render.mp4"), scale=50 if MODE == "half" else 100, qa=QA)
