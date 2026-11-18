"""The Clockmaker — vertical 3D short (Cycles, headless bpy).

  python build.py preview t1 t2 ...        # stills at those seconds -> preview/
  python build.py shots                     # one still per shot (mid-point) -> preview/
  python build.py render F0 F1 [step]       # frames -> frames/f#####.png
Scale/samples via env: CM_SCALE (default 50 = 540x960), CM_SAMPLES (default 24).
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy
import addon_utils
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector

addon_utils.enable("cycles")
bpy.ops.wm.read_factory_settings(use_empty=True)

import lib
import toon
import clocks
import sets
from lib import smooth, smoother, ramp, lerp, vlerp, empty, sphere, cyl, box, mat, emit
from sets import R, X0, X1, X2

D = math.radians
FPS = 24
LINES = json.load(open(os.path.join(HERE, "lines_raw.json")))
S = [0.0] + [round(l["at"] - 0.25, 2) for l in LINES[1:]]
END = 94.0
S.append(END)
NSH = 36
AT = [l["at"] for l in LINES]


def shot_of(t):
    for i in range(NSH):
        if t < S[i + 1]:
            return i
    return NSH - 1


# ------------------------------------------------------------------ scene setup
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.render.fps = FPS
sc.frame_start = 1
sc.frame_end = int(END * FPS)
sc.render.resolution_x, sc.render.resolution_y = 1080, 1920
sc.render.resolution_percentage = int(os.environ.get("CM_SCALE", "40"))
cy = sc.cycles
cy.samples = int(os.environ.get("CM_SAMPLES", "6"))
cy.use_adaptive_sampling = True
if os.environ.get("CM_THREADS"):
    sc.render.threads_mode = "FIXED"
    sc.render.threads = int(os.environ["CM_THREADS"])
cy.adaptive_threshold = 0.03
cy.use_denoising = True
try:
    cy.denoiser = "OPENIMAGEDENOISE"
except Exception:
    pass
cy.max_bounces = 4
cy.diffuse_bounces = 1
cy.glossy_bounces = 1
cy.transmission_bounces = 2
cy.transparent_max_bounces = 6
cy.volume_bounces = 0
cy.sample_clamp_indirect = 4.0
cy.caustics_reflective = False
cy.caustics_refractive = False
cy.volume_step_rate = 4.0
sc.render.use_persistent_data = True
sc.render.motion_blur_shutter = 0.5
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Punchy"
sc.render.film_transparent = False

sets.world()
sets.town()
sets.shop()
sets.room()
sets.void()
_sd = Vector((0.75, 0.25, -0.62)).normalized()
R["sun"].rotation_euler = _sd.to_track_quat("-Z", "Y").to_euler()
if os.environ.get('CM_NOVOL'):
    for o in bpy.data.objects:
        if o.name.startswith(('townfog','shazebox','rhazebox','sdoorfogbox')):
            o.hide_render = True

# ------------------------------------------------------------------ characters
elias = toon.Toon(toon.ELIAS, (X0 - 0.7, 2.95, -0.24), 0, "elias")
linaS = toon.Toon(dict(toon.LINA, name="LinaS"), (X0 + 3.6, 1.45, 0), -90, "lina")
linaT = toon.Toon(dict(toon.LINA, name="LinaT"), (0.8, 15.0, 0), 180, "lina")
linaR = toon.Toon(dict(toon.LINA, name="LinaR"), (X1 - 3.8, 1.85, 0), 90, "lina")
granny = toon.Toon(toon.GRANDMA, (0, 0, 0), 0, "grandma")
granny.root.parent = R["rock"]
granny.root.location = (0, 0.05, -0.27)
towns = []
for k, (x, y, fa) in enumerate(((2.15, 11.0, 75), (1.55, 12.35, 95), (2.35, 13.7, 110))):
    tm = toon.Toon(toon.townsman(k), (x, y, 0), fa, "generic", seed=k)
    towns.append(tm)
taras2 = toon.Toon(dict(toon.townsman(0), name="Taras2"), (0.6, 22.0, 0), 0, "generic", seed=0)

# 30 reflected in Lina's eye (shot 18): mirrored glowing text in front of her face
num30 = lib.text("num30", "30", (0, 10, -30), 0.3, emit("num30m", (1.0, 0.75, 0.3), 14.0), None, rot=(0, 0, 0))
num30.hide_render = True

# hero alarm clocks held by Lina (town / room) and her own clock at the end
def olena_clock(name, crack=False):
    return clocks.Clock(name, (0, 0, -50), 0, "alarm", 0.065, dial="silver", label="ОЛЕНА",
                        label_mat=emit(name + "_lab", (1.0, 0.12, 0.06), 6.0), body=clocks.mats()["silver"], seconds=True, glass=True,
                        counter="1:00", crack=crack)


olT = olena_clock("olenaT")
olR = olena_clock("olenaR", crack=True)
olR.root.location = (X1, 0, -50)
olS = R["olena_shop"]
olR_glow = lib.light("olRglow", "POINT", (0, 0, 0), 0, (1.0, 0.7, 0.3), size=0.03, parent=olR.root)
olR_glow.location = (0, -0.04, 0)
blue_lab = emit("lina_lab", (0.25, 0.55, 1.0), 7.0)
linaClock = clocks.Clock("linaclock", (0, 0, -50), 0, "alarm", 0.065, dial="silver", label="ЛІНА", label_mat=blue_lab,
                         body=clocks.mats()["silver"], seconds=True, glass=True, crack=True)
linaClock.crack_val.outputs[0].default_value = 1.5
lc_glow = lib.light("lcglow", "POINT", (0, -0.08, 0.0), 0, (0.3, 0.55, 1.0), size=0.03, parent=linaClock.root)

# hero hand for the top-down palm shot (33) – placed in the morning lot
HAND = {}


def hero_hand():
    skin = mat("hh_skin", toon.LINA["skin"], 0.5, sss=0.3)
    coat = linaT.mats["shirt"]
    root = empty("hh_root", (6.35, 11.5, 0.92), rot=(0, 0, D(90)))
    palm = sphere("hh_palm", (0, 0, 0), (0.045, 0.055, 0.016), skin, root)
    cyl("hh_cuff", (0, 0.085, 0.0), 0.04, 0.06, coat, root, rot=(D(90), 0, 0))
    cyl("hh_wrist", (0, 0.06, 0.0), 0.028, 0.04, skin, root, rot=(D(90), 0, 0))
    fingers = []
    for k, (fx, ln) in enumerate(((-0.03, 0.03), (-0.01, 0.036), (0.01, 0.034), (0.03, 0.028))):
        p1 = empty("hh_f1", (fx, -0.05, 0.0), root)
        sphere("hh_s1", (0, -ln * 0.5, 0), (0.0095, ln * 0.6, 0.0095), skin, p1)
        p2 = empty("hh_f2", (0, -ln, 0), p1)
        sphere("hh_s2", (0, -ln * 0.4, 0), (0.0088, ln * 0.5, 0.0088), skin, p2)
        fingers.append((p1, p2))
    th = empty("hh_t1", (-0.045, -0.01, 0.0), root, rot=(0, 0, D(-40)))
    sphere("hh_ts", (0, -0.02, 0), (0.011, 0.026, 0.011), skin, th)
    HAND.update(root=root, fingers=fingers, thumb=th)


hero_hand()


# ------------------------------------------------------------------ the note (shot 32)
def note_png(path):
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    if os.path.exists(path):
        return path
    W, H = 840, 600
    r = np.random.default_rng(4)
    base = np.ones((H, W, 3)) * np.array([226, 208, 168])
    n = np.asarray(Image.fromarray((r.random((H // 10, W // 10)) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)) / 255.0
    yy, xx = np.mgrid[0:H, 0:W]
    edge = np.minimum(np.minimum(xx, W - xx), np.minimum(yy, H - yy)) / 60.0
    base = base * (0.88 + 0.16 * n[..., None]) * (0.75 + 0.25 * np.clip(edge, 0, 1)[..., None])
    img = Image.fromarray(base.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf", 64)
    ink = (52, 30, 18)
    d.text((W / 2, H * 0.36), "Час не можна вкрасти.", font=f, fill=ink, anchor="mm")
    d.text((W / 2, H * 0.58), "Його можна лише", font=f, fill=ink, anchor="mm")
    d.text((W / 2, H * 0.76), "подарувати.", font=f, fill=ink, anchor="mm")
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    img.save(path)
    return path


def make_note():
    me = lib.m_plane_uv(14, 10).copy()
    o = lib.obj("note", me, (5.75, 11.55, 0.026), lib.image_mat("notem", note_png(os.path.join(lib.TEX, "note.png")), rough=0.8),
                rot=(0, 0, D(8)), scale=(0.21, 0.15, 1))
    o.shape_key_add(name="Basis")
    k = o.shape_key_add(name="lift")
    for v, kv in zip(me.vertices, k.data):
        x, y = v.co.x + 0.5, v.co.y + 0.5
        w = max(0.0, (x - 0.55) / 0.45) * max(0.0, (y - 0.45) / 0.55)
        kv.co = v.co + Vector((-0.05 * w * w, -0.04 * w * w, 0.07 * w * w))
    return o, k


NOTE, NOTE_KEY = make_note()

# golden wave over the rooftops (shot 29)
ringm = emit("ringm", (1.0, 0.72, 0.3), 0.0)
RING = lib.obj("wavering", lib.m_torus(1.0, 0.012, 96, 8), (0, 26, 7.0), ringm, scale=(0.01, 0.01, 25))

# end clock: its own glowing dial
_endd = lib.image_mat("enddial", os.path.join(lib.TEX, "dial_blue.png"), rough=0.4, emit_str=0.0)
lib.set_mat(R["endclock"].dial, _endd)
R["enddial_mat"] = _endd

# ------------------------------------------------------------------ dissolve shader for Taras2
DISSOLVE = []


def add_dissolve(m):
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    src = out.inputs["Surface"].links[0].from_socket
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 9.0
    nz.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    val = nt.nodes.new("ShaderNodeValue")
    val.outputs[0].default_value = 0.0
    sub = nt.nodes.new("ShaderNodeMath"); sub.operation = "SUBTRACT"
    nt.links.new(nz.outputs["Fac"], sub.inputs[0]); nt.links.new(val.outputs[0], sub.inputs[1])
    alive = nt.nodes.new("ShaderNodeMath"); alive.operation = "GREATER_THAN"; alive.inputs[1].default_value = 0.0
    nt.links.new(sub.outputs[0], alive.inputs[0])
    edge = nt.nodes.new("ShaderNodeMapRange")
    edge.inputs["From Min"].default_value = 0.0
    edge.inputs["From Max"].default_value = 0.03
    edge.inputs["To Min"].default_value = 1.0
    edge.inputs["To Max"].default_value = 0.0
    nt.links.new(sub.outputs[0], edge.inputs["Value"])
    gate = nt.nodes.new("ShaderNodeMath"); gate.operation = "GREATER_THAN"; gate.inputs[1].default_value = 0.001
    nt.links.new(val.outputs[0], gate.inputs[0])
    em_s = nt.nodes.new("ShaderNodeMath"); em_s.operation = "MULTIPLY"
    nt.links.new(edge.outputs[0], em_s.inputs[0]); nt.links.new(gate.outputs[0], em_s.inputs[1])
    em_s2 = nt.nodes.new("ShaderNodeMath"); em_s2.operation = "MULTIPLY"; em_s2.inputs[1].default_value = 6.0
    nt.links.new(em_s.outputs[0], em_s2.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 0.7, 0.25, 1)
    nt.links.new(em_s2.outputs[0], em.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(src, add.inputs[0]); nt.links.new(em.outputs[0], add.inputs[1])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(alive.outputs[0], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(add.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    DISSOLVE.append(val)


_seen = set()
for o in bpy.data.objects:
    if o.name.startswith("Taras2") and o.type in ("MESH", "FONT"):
        for slot in o.material_slots:
            if slot.material and slot.material.name not in _seen:
                _seen.add(slot.material.name)
                add_dissolve(slot.material)

# ------------------------------------------------------------------ point systems
rng = np.random.default_rng(42)
P_shopdust = lib.Points("shopdust", 450, 0.0035, emit("dustw", (1.0, 0.7, 0.4), 2.5))
P_dissolve = lib.Points("dissolve", 2200, 0.006, emit("dustg", (1.0, 0.7, 0.25), 9.0))
P_snow = lib.Points("snow", 700, 0.007, mat("snowp", (0.95, 0.97, 1.0), 0.6, emit=(0.6, 0.7, 0.9), emit_str=0.6))
P_roomdust = lib.Points("roomdust", 380, 0.0028, emit("dustr", (1.0, 0.75, 0.4), 4.0))
P_sparks = lib.Points("sparks", 220, 0.0016, emit("sparkm", (1.0, 0.75, 0.3), 25.0))
P_morning = lib.Points("mdust", 900, 0.0035, emit("dustm", (1.0, 0.78, 0.4), 6.0))
P_shards = lib.Points("shards", 90, 0.0012, mat("shardm", (0.9, 0.95, 1.0), 0.05, emit=(0.7, 0.85, 1.0), emit_str=3.0))
P_endmotes = lib.Points("endmotes", 160, 0.004, emit("endmote", (0.4, 0.65, 1.0), 6.0))

SD = dict(base=np.column_stack([rng.uniform(X0 - 2.8, X0 + 2.8, 450), rng.uniform(0.5, 5.6, 450), rng.uniform(0.3, 3.2, 450)]),
          ph=rng.uniform(0, 6.28, (450, 3)), sz=rng.uniform(0.4, 1.3, 450))
RD = dict(base=np.column_stack([rng.uniform(X1 - 2.5, X1 + 2.5, 380), rng.uniform(1.0, 4.8, 380), rng.uniform(0.3, 2.5, 380)]),
          ph=rng.uniform(0, 6.28, (380, 3)), sz=rng.uniform(0.4, 1.4, 380))
MD = dict(r=rng.uniform(0.2, 2.4, 900), a=rng.uniform(0, 6.28, 900), z=rng.uniform(0.05, 3.5, 900), w=rng.uniform(0.15, 0.6, 900),
          sz=rng.uniform(0.4, 1.3, 900))
SN = dict(v=np.column_stack([rng.uniform(1.5, 4.5, 700), rng.uniform(-0.9, 0.9, 700), rng.uniform(-0.6, 0.8, 700)]),
          t0=rng.uniform(0.0, 1.4, 700), sz=rng.uniform(0.5, 1.4, 700), p0=np.column_stack([np.zeros(700), rng.uniform(-0.4, 0.4, 700), rng.uniform(0.2, 2.0, 700)]))
SP = dict(a=rng.uniform(0, 6.28, 220), r=rng.uniform(0.06, 0.2, 220), w=rng.uniform(-8, 8, 220), z=rng.uniform(-0.08, 0.08, 220),
          life=rng.uniform(0.3, 0.9, 220), off=rng.uniform(0, 1, 220))
SH = dict(v=rng.normal(0, 1, (90, 3)), sz=rng.uniform(0.5, 1.5, 90))
EM = dict(p=np.column_stack([rng.uniform(-1.2, 1.2, 160), rng.uniform(-0.6, 0.8, 160), rng.uniform(-0.6, 2.4, 160)]), ph=rng.uniform(0, 6.28, (160, 3)))

# sample points on Taras2 for the dissolve
bpy.context.view_layer.update()
_pts = []
for o in bpy.data.objects:
    if o.name.startswith("Taras2") and o.type == "MESH":
        mw = o.matrix_world
        vs = [mw @ v.co for v in o.data.vertices]
        _pts += vs
_pts = np.array([tuple(v) for v in _pts])
sel = rng.choice(len(_pts), 2200, replace=len(_pts) < 2200)
DS = dict(p0=_pts[sel], rel=rng.uniform(0.25, 0.75, 2200), v=np.column_stack([rng.uniform(0.6, 2.2, 2200), rng.uniform(-0.4, 0.6, 2200), rng.uniform(0.1, 0.9, 2200)]),
          ph=rng.uniform(0, 6.28, (2200, 3)), sz=rng.uniform(0.5, 1.4, 2200))
DIS_T0, DIS_T1 = AT[8] + 0.05, AT[8] + 1.6

# ------------------------------------------------------------------ camera
cam_data = bpy.data.cameras.new("Cam")
cam_data.clip_start = 0.01
cam_data.clip_end = 500
cam_data.sensor_width = 36
cam_data.dof.use_dof = True
CAM = bpy.data.objects.new("Cam", cam_data)
lib.link(CAM)
sc.camera = CAM


def C(loc, look, lens=35, f=2.8, focus=None, roll=0.0):
    return dict(loc=Vector(loc), look=Vector(look), lens=lens, f=f, focus=focus, roll=roll)


def wobble(t, amp, freq=1.0, seed=0):
    return Vector((amp * math.sin(t * 1.3 * freq + seed) + amp * 0.5 * math.sin(t * 2.9 * freq + seed * 2),
                   amp * 0.6 * math.sin(t * 1.1 * freq + seed * 3),
                   amp * math.sin(t * 1.7 * freq + seed * 5) + amp * 0.4 * math.sin(t * 3.3 * freq + seed)))


def shake(t, amp):
    return Vector((amp * (math.sin(t * 31) + 0.6 * math.sin(t * 53 + 1)), amp * 0.5 * math.sin(t * 41 + 2), amp * (math.sin(t * 37 + 3) + 0.5 * math.sin(t * 61))))


def head_world(ch):
    return ch.P["head"].matrix_world @ ch.hc


def clock_world(c):
    return c.root.matrix_world.translation.copy()


# ------------------------------------------------------------------ hold-clock helpers
HOLD = {"armL": (52, -14, 0), "armR": (52, -14, 0), "elbowL": (72, 0, 0), "elbowR": (72, 0, 0), "handL": (10, 0, 0), "handR": (10, 0, 0)}


def attach_between_hands(c, ch, face_to=None, fwd=0.035, up=0.0, local_dir=None):
    bpy.context.view_layer.update()
    hl = ch.P["handL"].matrix_world.translation
    hr = ch.P["handR"].matrix_world.translation
    mid = (hl + hr) / 2
    rootm = ch.root.matrix_world
    fdir = (rootm.to_3x3() @ Vector((0, -1, 0))).normalized()
    pos = mid + fdir * fwd + Vector((0, 0, up - 0.03))
    if local_dir is not None:
        face_to = pos + rootm.to_3x3() @ Vector(local_dir)
    d = Vector(face_to) - pos
    q = d.to_track_quat("-Y", "Z")
    c.root.matrix_world = Matrix.Translation(pos) @ q.to_matrix().to_4x4()


def place_clock(c, pos, face_to, roll=0.0):
    d = Vector(face_to) - Vector(pos)
    q = d.to_track_quat("-Y", "Z")
    m = Matrix.Translation(Vector(pos)) @ q.to_matrix().to_4x4() @ Matrix.Rotation(roll, 4, "Y")
    c.root.matrix_world = m


# ------------------------------------------------------------------ countdown
CD = [(0.0, 60.0), (37.45, 60.0), (42.73, 30.0), (50.25, 10.0), (60.0, 1.0)]
TICK_T = AT[26] + 0.85  # "цок"


def remaining(t):
    if t <= CD[0][0]:
        return CD[0][1]
    for (t0, v0), (t1, v1) in zip(CD, CD[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return 1.0


def set_countdown(c, t, tremble=0.0):
    if t >= TICK_T:
        dt = t - TICK_T
        s = 6.0 + math.floor(dt * 2) * 6 * 1.0 + 6 * smooth((dt * 2) % 1 * 4)
        c.set(0, 30 + dt * 4, s)
        if c.counter:
            c.counter.data.body = ""
        return
    rem = remaining(t)
    tick = math.ceil(rem)
    sec_ang = (tick % 60) * 6.0
    min_ang = 30.0 * min(1.0, rem / 60.0) + tremble * math.sin(t * 47) * 2.0
    c.set(0, min_ang, sec_ang)
    if c.counter:
        c.counter.data.body = f"{int(tick) // 60}:{int(tick) % 60:02d}"


# ------------------------------------------------------------------ per-set animation
def anim_shop(t):
    i = shot_of(t)
    # Elias
    blink = 1.0 if (t % 3.7) < 0.12 else 0.0
    base = dict(toon.SIT)
    base.update({"armL": (62, -4, 0), "armR": (62, -4, 0), "elbowL": (45, 0, 0), "elbowR": (45, 0, 0)})
    work = dict(base, head=(30, 0, 0), spine=(14, 0, 0))
    look = dict(base, head=(-4, 0, 0), spine=(6, 0, 0))
    if t < S[1] + 0.4:
        p = work
        gz = (0, -15)
    elif t < S[2]:
        u = ramp(t, S[1] + 0.4, S[1] + 1.6)
        p = toon.blend(work, look, smoother(u))
        gz = (0, -15 + 15 * u)
    elif t < S[11]:
        p = dict(look, head=(6, 0, 18))
        gz = (12, 0)
    else:
        u = ramp(t, S[11] + 0.2, S[11] + 1.2)
        p = toon.blend(dict(look, head=(6, 0, 18)), dict(look, head=(-8, 0, 26), spine=(2, 0, 0), armL=(40, 0, 0), armR=(40, 0, 0)), smooth(u))
        gz = (14, 3)
    pale = ramp(t, S[11] + 0.3, S[11] + 1.5) if t >= S[11] else 0.0
    sk = tuple(lerp(a, b, pale) for a, b in zip(toon.ELIAS["skin"], (0.78, 0.80, 0.82)))
    elias.set_pose(p, blink=blink if pale < 0.5 else 0.0, mouth="open" if pale > 0.3 else "smile", mouth_open=0.6, brow=pale * 1.2,
                   gaze=gz, skin=sk)
    elias.glasses.location.z = elias.hc.z + elias.s["head_r"] * 0.06 - 0.016 * smooth(ramp(t, S[11] + 0.6, S[11] + 1.3))
    # Lina in the shop
    ch = linaS
    if t < S[9] + 1.6:
        ch.root.location = (X0 + 3.62, 1.45, 0)
        ch.root.rotation_euler = (0, 0, D(-90))
        ch.set_pose(toon.STAND, mouth="neutral", gaze=(0, 0))
    elif t < S[10]:
        u = ramp(t, S[9] + 1.6, S[10])
        pos = vlerp((X0 + 3.62, 1.45, 0), (X0 + 2.2, 1.7, 0), u)
        ch.root.location = pos
        ch.root.rotation_euler = (0, 0, D(-90))
        ch.set_pose(toon.walk_cycle(t), mouth="neutral")
    elif t < S[14]:
        ch.root.location = (X0 + 1.4, 3.2, 0)
        ch.root.rotation_euler = (0, 0, D(180))
        bl = 1.0 if (t % 2.9) < 0.1 else 0.0
        ch.set_pose(dict(toon.STAND, head=(-24, 0, 6), armL=(8, 10, 0), armR=(8, 10, 0)), blink=bl, mouth="smile", gaze=(4, 14), brow=0.5)
        if t > S[12]:
            ch.root.location = (X0 + 0.55, 4.3, 0)
            ch.set_pose(dict(toon.STAND, head=(-10, 0, 0)), mouth="neutral", gaze=(0, 0), brow=-0.6)
    else:
        lt = t - S[14]
        pos0 = Vector((X0 + 0.2, 5.12, 0))
        reach = dict(toon.STAND, armL=(88, -10, 0), armR=(88, -10, 0), elbowL=(10, 0, 0), elbowR=(10, 0, 0), spine=(10, 0, 0), head=(5, 0, 0))
        if lt < 0.55:
            u = smooth(lt / 0.45)
            ch.root.location = pos0
            ch.root.rotation_euler = (0, 0, D(180))
            ch.set_pose(toon.blend(toon.STAND, reach, u), mouth="open", mouth_open=0.7, brow=-0.5)
            place_clock(olS, olS.home, olS.home + Vector((0, -1, 0)))
        else:
            u = ramp(lt, 0.55, 1.3)
            ang = 180 - 180 * smoother(u)
            run = ramp(lt, 1.15, 1.5)
            pose = toon.blend(toon.blend(reach, HOLD, smooth(ramp(lt, 0.55, 0.85))), toon.blend(HOLD, dict(toon.run_cycle(lt), **{k: v for k, v in HOLD.items()}), 1.0), run)
            ch.root.rotation_euler = (0, 0, D(ang))
            ch.root.location = pos0 + Vector((0.4, -1.4, 0)) * (max(0.0, lt - 1.2) / 1.25) ** 1.2
            ch.set_pose(pose, mouth="open", mouth_open=0.8, brow=-0.8)
            ch.skirt.scale = (1 + 0.25 * math.sin(math.pi * u), 1 + 0.25 * math.sin(math.pi * u), 1 - 0.1 * math.sin(math.pi * u))
            ch.skirt.rotation_euler = (0, 0, D(-25 * math.sin(math.pi * u)))
            for b, sx in zip(ch.braids, (1, -1)):
                b.rotation_euler = (D(-30 * math.sin(math.pi * u)), D(sx * 40 * math.sin(math.pi * u)), 0)
            attach_between_hands(olS, ch, fwd=0.03, local_dir=(0.0, -1.0, 0.4))
            return
    ch.skirt.scale = (1, 1, 1)
    ch.skirt.rotation_euler = (0, 0, 0)
    for b in ch.braids:
        b.rotation_euler = (0, 0, 0)
    place_clock(olS, olS.home, olS.home + Vector((0, -1, 0)))


def anim_town(t):
    i = shot_of(t)
    # townspeople at the window
    for k, tm in enumerate(towns):
        laugh = 1.0 if t < S[4] + 0.6 else 0.0
        ph = t * 9 + k * 1.7
        bob = math.sin(ph)
        if laugh:
            p = dict(toon.STAND, spine=(-6 + 5 * bob, 0, 0), head=(-18 + 8 * bob, 0, 0))
            if k == 1:
                p.update(armR=(80, 18, 0), elbowR=(8, 0, 0))
            if k == 2:
                p.update(armL=(20, 10, 0), elbowL=(110, 0, 0), spine=(16 + 6 * bob, 0, 0))
            tm.set_pose(p, mouth="open", mouth_open=0.8 + 0.5 * abs(bob), brow=0.4, blink=0.6)
        else:
            u = ramp(t, S[4] + 0.6, S[4] + 1.1)
            p = dict(toon.STAND, head=(0, 0, 0))
            if k == 1:
                p.update(armR=(80 * (1 - u), 18, 0))
            pale = ramp(t, S[4] + 0.7, S[4] + 1.5) if k == 0 else 0.0
            sk = tuple(lerp(a, b, pale) for a, b in zip(toon.townsman(k)["skin"], (0.80, 0.82, 0.84)))
            tm.set_pose(p, mouth="open" if k == 0 else "neutral", mouth_open=0.5, brow=1.2 * pale if k == 0 else 0.3, skin=sk)
    for k, tm in enumerate(towns):
        tm.root.location.z = 0 if t < S[29] else -40
    # Taras2 on the street, dissolving
    u = ramp(t, DIS_T0, DIS_T1)
    for v in DISSOLVE:
        v.outputs[0].default_value = lerp(0.18, 0.82, u) if u > 0 else 0.0
    taras2.root.location = (0.6, 22.0, 0) if t < DIS_T1 + 0.3 else (0.6, 22.0, -40)
    taras2.set_pose(dict(toon.STAND, head=(-6, 0, 0), armL=(18, 14, 0), armR=(18, 14, 0), elbowL=(30, 0, 0), elbowR=(30, 0, 0)),
                    mouth="open", mouth_open=0.4, brow=1.0, gaze=(0, 5))
    # Lina running (16-18) and in the morning lot (31-33)
    ch = linaT
    if S[15] <= t < S[18]:
        lt = t - S[15]
        y = 15.0 + lt * 3.4
        x = 0.8 - 0.25 * lt
        ch.root.location = (x, y, 0)
        ch.root.rotation_euler = (0, 0, D(180))
        pose = dict(toon.run_cycle(t, 0.38), **HOLD)
        pose["spine"] = (18, 0, 4 * math.sin(t * 16.5))
        ch.set_pose(pose, mouth="open", mouth_open=0.7, brow=-0.6, blink=0.0, gaze=(0, -6))
        ch.skirt.rotation_euler = (D(14), 0, 0)
        for b, sx in zip(ch.braids, (1, -1)):
            b.rotation_euler = (D(-35 + 10 * math.sin(t * 16.5)), D(sx * 12), 0)
        attach_between_hands(olT, ch, fwd=0.04, local_dir=(0.35, -1.0, 0.45))
        set_countdown(olT, t)
        return
    ch.skirt.rotation_euler = (0, 0, 0)
    for b in ch.braids:
        b.rotation_euler = (0, 0, 0)
    if t >= S[30] and t < S[33]:
        ch.root.location = (6.75, 12.0, 0.02)
        ch.root.rotation_euler = (0, 0, D(-100))
        bl = 1.0 if (t % 3.1) < 0.12 else 0.0
        pose = dict(toon.STAND, head=(18, 0, -10), armR=(40, -10, 0), elbowR=(80, 0, 0), armL=(4, 8, 0))
        ch.set_pose(pose, blink=bl, mouth="neutral", gaze=(-5, -12), brow=0.3)
        olT.root.location = (0, 0, -50)
    else:
        ch.root.location = (0, -80, -50)
        olT.root.location = (0, 0, -50)


def anim_room(t):
    i = shot_of(t)
    rock_amp = 4.0 if t < S[21] else 1.0
    R["rock"].rotation_euler = (D(rock_amp * math.sin(t * 1.6)), 0, 0) if not (S[24] <= t < S[26]) else (D(rock_amp * math.sin(S[24] * 1.6)), 0, 0)
    # door
    if t < S[18] + 0.15:
        dr = 0.0
    else:
        u = ramp(t, S[18] + 0.15, S[18] + 0.45)
        dr = -112 * smooth(u) + 6 * math.sin(max(0, t - S[18] - 0.45) * 14) * math.exp(-max(0, t - S[18] - 0.45) * 4)
    R["room_door"].rotation_euler = (0, 0, D(dr))
    # grandma
    gp = dict(toon.SIT, armL=(40, -6, 0), armR=(40, -6, 0), elbowL=(55, 0, 0), elbowR=(55, 0, 0), spine=(-6, 0, 0), head=(4, 0, 0))
    turn = smooth(ramp(t, S[19] + 0.6, S[19] + 2.4))
    gp["head"] = (4 - 6 * turn, 0, -32 * turn)
    gz = (-20 * turn, 0)
    mouth = "neutral"
    hug = smooth(ramp(t, S[21] + 0.1, S[21] + 1.0))
    if t >= S[21]:
        gp = toon.blend(gp, dict(toon.SIT, spine=(10, 0, -12), head=(10, -10, -30), armL=(60, -30, 0), armR=(70, -10, -20), elbowL=(80, 0, 0), elbowR=(85, 0, 0)), hug)
        gz = (-10, -10)
    smile = ramp(t, S[27] + 0.6, S[27] + 1.6)
    grey = 1.0 - smile if t < S[27] + 1.6 else 0.0
    grey = grey * ramp(t, S[19], S[20])
    if t >= S[24] and t < S[27]:
        grey = 1.0
    sk = tuple(lerp(a, b, grey * 0.55) for a, b in zip(toon.GRANDMA["skin"], (0.72, 0.74, 0.78)))
    bl = 1.0 if ((t % 4.1) < 0.13 and not (S[24] <= t < S[26])) else 0.0
    if t >= S[24] and t < S[27] + 0.6:
        bl = 0.85  # eyes closed in the hug / freeze
    granny.set_pose(gp, blink=bl, mouth="smile" if smile > 0.4 else mouth, gaze=gz, brow=0.6 * (1 - smile) if t > S[19] else 0, skin=sk)
    # Lina
    ch = linaR
    if t < S[18]:
        ch.root.location = (X1 - 3.8, 1.85, 0)
        ch.set_pose(toon.STAND)
        attach_between_hands(olR, ch, fwd=0.04, local_dir=(0.85, -0.55, 0.35))
        set_countdown(olR, t)
        return
    if t < S[19] + 1.8:
        lt = t - S[18]
        u = smooth(ramp(lt, 0.25, 3.3))
        pos = vlerp((X1 - 3.7, 1.85, 0), (X1 - 0.55, 3.05, 0), u)
        ch.root.location = pos
        ch.root.rotation_euler = (0, 0, D(lerp(90, 118, u)))
        run = 1.0 - ramp(lt, 2.6, 3.4)
        pose = toon.blend(dict(toon.STAND, **HOLD), dict(toon.run_cycle(t, 0.38), **HOLD), run)
        ch.set_pose(pose, mouth="open", mouth_open=0.7, brow=-0.6)
    else:
        ch.root.location = (X1 - 0.55, 3.05, 0)
        ch.root.rotation_euler = (0, 0, D(118))
        p = dict(toon.STAND, **HOLD)
        p["head"] = (8, 0, 0)
        hugp = dict(toon.STAND, spine=(28, 0, 0), head=(10, 0, -25), armL=(70, -22, 0), armR=(70, -22, 0), elbowL=(78, 0, 0), elbowR=(78, 0, 0),
                    handL=(20, 0, 0), handR=(20, 0, 0), legL=(10, 0, 0), kneeL=(10, 0, 0))
        hug = smooth(ramp(t, S[21] + 0.1, S[21] + 1.0))
        ch.set_pose(toon.blend(p, hugp, hug), mouth="frown" if t < S[27] else "smile", brow=-0.7 if t < S[27] else 0.3,
                    blink=0.9 if (S[21] + 1 < t < S[27] + 0.8) else 0.0)
        ch.root.location = vlerp((X1 - 0.55, 3.05, 0), (X1 - 0.33, 3.2, 0), hug)
    gr = head_world(granny)
    attach_between_hands(olR, ch, fwd=0.04, local_dir=(0.85, -0.55, 0.35))
    set_countdown(olR, t, tremble=1.0)
    # glow, crack, ripple
    glow = 0.0
    if t >= S[21]:
        glow = 1.2 * smooth(ramp(t, S[21] + 0.5, S[22] + 1.5))
    if t >= S[23] + 2.0:
        glow *= 0.4
    olR_glow.data.energy = glow
    lib.emit_strength_socket(olR.label_mat).default_value = 6.0 + glow * 2
    R["hug_light"].data.energy = 220 * smooth(ramp(t, S[21] + 0.3, S[21] + 2.0)) * (1 - 0.6 * ramp(t, S[23], S[23] + 1.0))
    cr = smooth(ramp(t, AT[23] + 0.25, AT[23] + 2.0)) * 1.2 if t >= AT[23] else 0.0
    olR.crack_val.outputs[0].default_value = cr
    rp = ramp(t, TICK_T, TICK_T + 1.6)
    R["ripple"].scale = (0.02 + 6 * rp,) * 3
    R["ripple"].location = clock_world(olR)
    sv = R["ripple_mat"].node_tree.nodes["strength"]
    sv.outputs[0].default_value = (30.0 * (1 - rp) * (1 if rp > 0 else 0))
    if t > S[27]:
        R["hug_light"].data.energy = 160 * smooth(ramp(t, TICK_T, TICK_T + 1.0))


def anim_morning_hand(t):
    if not (S[32] <= t < S[35]):
        HAND["root"].location = (6.35, 11.5, -40)
        linaClock.root.location = (0, 0, -50)
        return
    HAND["root"].location = (6.35, 11.5, 0.92)
    open_ = smooth(ramp(t, S[32] + 0.3, S[32] + 1.6)) if t < S[33] else 1.0
    for k, (p1, p2) in enumerate(HAND["fingers"]):
        c = 1 - open_
        p1.rotation_euler = (D(-75 * c - 5), 0, 0)
        p2.rotation_euler = (D(-80 * c - 5), 0, 0)
    HAND["thumb"].rotation_euler = (D(-40 * (1 - open_)), 0, D(-40 + 25 * (1 - open_)))
    bpy.context.view_layer.update()
    m = HAND["root"].matrix_world
    pos = m @ Vector((0, -0.005, 0.016 + 0.05))
    # dial faces up (toward the top-down camera); in the macro shots it faces the camera
    place_clock(linaClock, pos, pos + Vector((0, 0, 1)), 0)
    linaClock.root.matrix_world = Matrix.Translation(pos) @ Euler((D(-90), 0, 0)).to_matrix().to_4x4()
    # hands: frozen until shot 35, then backwards
    if t < S[34]:
        linaClock.set(0, 0, 6)
    else:
        dt = t - S[34]
        s = 6 - (math.floor(dt * 2) + smooth((dt * 2) % 1 * 4)) * 6
        linaClock.set(-dt * 2, -dt * 10, s)
    lc_glow.data.energy = 0.6 if t >= S[33] else 0.2
    lib.emit_strength_socket(blue_lab).default_value = 3.0 + 6.0 * smooth(ramp(t, S[33], S[33] + 1.2))


# ------------------------------------------------------------------ cameras per shot
def cam(i, t):
    t0, t1 = S[i], S[i + 1]
    u = (t - t0) / (t1 - t0)
    lt = t - t0
    e = smooth(u)
    if i == 0:   # aerial descent over the foggy town toward the glowing shop window
        return C(vlerp((-6, -42, 34), (1.5, -4, 6.5), smoother(u)), vlerp((3, 20, 0), (4.0, 11.6, 1.6), e), 26, 8)
    if i == 1:   # Elias lifts his head
        return C(vlerp((X0 - 0.62, 1.55, 1.32), (X0 - 0.66, 1.92, 1.31), e), (X0 - 0.7, 2.95, 1.30), 50, 2.0)
    if i == 2:   # pan across the shelves
        return C(vlerp((X0 - 2.2, 3.9, 1.75), (X0 + 2.0, 3.9, 1.65), e), vlerp((X0 - 1.9, 5.8, 1.7), (X0 + 2.3, 5.8, 1.55), e), 32, 2.8)
    if i == 3:   # townspeople laughing outside
        return C(vlerp((3.55, 15.9, 1.55), (3.45, 15.4, 1.5), e), (1.9, 12.2, 1.45), 32, 2.8)
    if i == 4:   # laughter freezes, snap toward the clock in the window
        sn = smooth(ramp(u, 0.62, 0.8))
        a = C((3.45, 15.3, 1.5), (1.9, 12.0, 1.55), 40, 2.8)
        b = C((2.0, 13.0, 1.6), (4.06, 11.0, 1.8), 50, 2.8)
        return C(vlerp(a["loc"], b["loc"], sn), vlerp(a["look"], b["look"], sn), lerp(40, 50, sn), 2.8)
    if i == 5:   # macro of a dial: engraved golden name
        c = R["heroes"]["ostap"]
        p = clock_world(c)
        return C(p + Vector((0.07 - 0.05 * e, -0.36 + 0.06 * e, 0.02)), p + Vector((0, 0, -0.025)), 85, 2.8)
    if i == 6:   # montage of named dials
        keys = ["marta", "ivan", "sofia", "ostap"]
        k = min(3, int(u * 4))
        c = R["heroes"][keys[k]]
        p = clock_world(c)
        uu = u * 4 - k
        return C(p + Vector((0.05 * (1 if k % 2 else -1) * (1 - uu), -0.3 + 0.04 * uu, 0.02)), p + Vector((0, 0, -0.02)), 85, 2.8)
    if i == 7:   # extreme close-up: hand ticks to zero
        p = clock_world(R["heroes"]["taras"])
        return C(p + Vector((0.035, -0.19, 0.06)), p + Vector((0.0, 0, 0.035)), 100, 2.8)
    if i == 8:   # man dissolves into golden dust
        return C(vlerp((0.0, 18.4, 1.35), (0.15, 18.9, 1.35), e), (0.75, 22.0, 1.2), 40, 4.0)
    if i == 9:   # door opens, Lina silhouette in fog
        return C(vlerp((X0 + 0.6, 2.7, 1.0), (X0 + 0.8, 2.55, 1.0), e), (X0 + 3.1, 1.45, 1.0), 30, 4.0)
    if i == 10:  # Lina looking up, eyes reflect clocks
        return C(vlerp((X0 + 1.42, 4.12, 0.96), (X0 + 1.42, 4.0, 0.97), e), (X0 + 1.4, 3.2, 1.1), 50, 2.8)
    if i == 11:  # Elias pales
        return C(vlerp((X0 - 0.55, 2.02, 1.36), (X0 - 0.6, 2.18, 1.34), e), (X0 - 0.68, 2.95, 1.33), 55, 2.0)
    if i == 12:  # slow dolly to the small silver clock
        p = olS.home
        return C(vlerp(p + Vector((-0.55, -1.2, 0.3)), p + Vector((-0.08, -0.38, 0.06)), smoother(u)), p + Vector((0, 0, 0.0)), 50, 2.8)
    if i == 13:  # macro: minute hand trembling at 1
        p = olS.home
        return C(p + Vector((0.012, -0.26 + 0.02 * e, 0.012)), p + Vector((0.0, 0, 0.0)), 85, 4.0)
    if i == 14:  # Lina grabs it and spins
        return C(vlerp((X0 + 1.35, 3.45, 1.05), (X0 + 1.3, 3.25, 1.0), e), vlerp((X0 + 0.25, 4.85, 0.8), (X0 + 0.4, 4.3, 0.75), e), 30, 4.0)
    if i == 15:  # tracking behind Lina running through the foggy street
        p = linaT.root.location.copy()
        return C(p + Vector((0.35, -2.5, 1.05)) + wobble(t, 0.03, 3), p + Vector((0, 3, 0.65)), 32, 4.0)
    if i == 16:  # the clock in her hands, spinning hands, sparks
        p = clock_world(olT)
        r = linaT.root.matrix_world.to_3x3()
        return C(p + r @ Vector((0.18, -0.36, 0.1)) + wobble(t, 0.01, 4), p, 50, 2.8)
    if i == 17:  # 30 reflected in her eye
        eye = linaT.eyes[1].matrix_world.translation
        r = linaT.root.matrix_world.to_3x3()
        loc = eye + r @ Vector((-0.03, -0.22, 0.01)) + wobble(t, 0.002, 6)
        return C(loc, eye, 85, 4.0, focus=(loc - eye).length - 0.05)
    if i == 18:  # door bursts open, snow rushes in (low angle)
        return C((X1 - 1.6, 3.4, 0.22), vlerp((X1 - 3.0, 1.85, 1.15), (X1 - 2.6, 2.0, 1.0), e), 22, 5.0)
    if i == 19:  # grandma in the rocking chair by the window
        g = head_world(granny)
        return C(vlerp((X1 - 0.75, 1.75, 1.05), (X1 - 0.55, 2.15, 1.05), e), g + Vector((0, 0, -0.15)), 40, 2.8)
    if i == 20:  # dial 0:10, camera shake
        p = clock_world(olR)
        r = olR.root.matrix_world.to_3x3()
        return C(p + r @ Vector((0.02, -0.3, 0.03)) + shake(t, 0.003 + 0.006 * u), p, 70, 2.8)
    if i == 21:  # the hug, warm golden light
        return C(vlerp((X1 + 0.85, 2.0, 1.2), (X1 + 0.7, 2.2, 1.15), e), (X1 - 0.05, 3.35, 0.95), 32, 2.8)
    if i == 22:  # small hands squeezing the clock
        p = clock_world(olR)
        r = olR.root.matrix_world.to_3x3()
        return C(p + r @ (Vector((0.08, -0.26, 0.07)) * (1 - 0.15 * e)), p, 60, 2.8)
    if i == 23:  # glass crack, super slow
        p = clock_world(olR)
        r = olR.root.matrix_world.to_3x3()
        return C(p + r @ Vector((0.03, -0.2 + 0.03 * e, 0.02)), p + r @ Vector((-0.006, 0, 0.0)), 100, 4.0)
    if i == 24:  # hand frozen at 1, dust frozen
        p = clock_world(olR)
        r = olR.root.matrix_world.to_3x3()
        return C(p + r @ Vector((0.03, -0.19 + 0.01 * e, 0.02)), p + r @ Vector((0.004, 0, 0.004)), 85, 4.0)
    if i == 25:  # wide, still
        return C((X1 - 1.9, 0.9, 1.5), (X1 - 0.1, 3.4, 0.9), 26, 5.6)
    if i == 26:  # macro tick -> ripple of golden light, pull back
        p = clock_world(olR)
        r = olR.root.matrix_world.to_3x3()
        pb = smoother(ramp(t, TICK_T - 0.1, TICK_T + 1.0))
        a = p + r @ Vector((0.0, -0.2, 0.02))
        b = Vector((X1 - 1.7, 1.2, 1.4))
        return C(vlerp(a, b, pb), vlerp(p, Vector((X1 - 0.1, 3.3, 1.0)), pb), lerp(85, 26, pb), lerp(4, 5.6, pb))
    if i == 27:  # hands go forward, grandma smiles
        g = head_world(granny)
        return C(vlerp((X1 + 0.15, 2.35, 1.2), (X1 + 0.1, 2.55, 1.18), e), g + Vector((-0.12, 0, -0.12)), 38, 2.8)
    if i == 28:  # every clock in town turns forward: wave of light over the roofs
        return C(vlerp((-11, 6, 15), (-9, 10, 13), e), (3, 40, 5), 26, 8)
    if i == 29:  # morning, empty lot
        return C(vlerp((-2.8, 11.6, 1.7), (-2.0, 11.8, 1.7), e), (8.0, 12.0, 1.9), 24, 8)
    if i == 30:  # golden dust, Lina alone
        return C(vlerp((3.0, 11.0, 1.05), (3.4, 11.2, 1.0), e), (6.7, 12.0, 0.85), 35, 4.0)
    if i == 31:  # the note
        p = Vector((5.75, 11.55, 0.03))
        return C(p + Vector((-0.05, -0.38 + 0.06 * e, 0.34 - 0.04 * e)), p, 50, 2.8)
    if i == 32:  # top-down: palm opens
        p = HAND["root"].matrix_world.translation
        return C(p + Vector((0.0, -0.001, 0.62 - 0.06 * e)), p, 50, 2.8, roll=0)
    if i == 33:  # macro: name LINA glowing blue
        p = clock_world(linaClock)
        return C(p + Vector((0.03, -0.07, 0.2 - 0.03 * e)), p + Vector((0, 0, 0)), 85, 4.0)
    if i == 34:  # hands turn backwards, cut to black
        p = clock_world(linaClock)
        return C(p + Vector((-0.02, -0.05, 0.19 - 0.04 * e)), p, 85, 4.0)
    if i == 35:  # black screen, a single glowing clock
        return C((X2, -2.6 + 0.3 * e, 1.25), (X2, 0, 1.15), 50, 4.0)


def cam_dial_roll(i):
    return 0.0


# ------------------------------------------------------------------ environment per time
def env(t):
    w = R["world"].node_tree
    morning = t >= S[29]
    grad = w.nodes["skygrad"].color_ramp
    if morning:
        grad.elements[0].color = (0.95, 0.75, 0.55, 1)
        grad.elements[1].color = (0.30, 0.50, 0.85, 1)
        w.nodes["stars"].inputs[1].default_value = 0.0
        w.nodes["bg"].inputs["Strength"].default_value = 1.6
        R["moonlight"].data.energy = 0.0
        R["sun"].data.energy = 4.5
        for L in R["lamps"]:
            L.data.energy = 0.0
        lib.emit_strength_socket(R["lamp_mat"]).default_value = 0.2
        for m in R["win_mats"]:
            m.node_tree.nodes["base"].outputs[0].default_value = 0.0
        vs = next(n for n in R["town_fog"].node_tree.nodes if n.bl_idname == "ShaderNodeVolumeScatter")
        vs.inputs["Density"].default_value = 0.012
        vs.inputs["Color"].default_value = (1.0, 0.9, 0.75, 1)
        R["shop_ext"].scale = (0.0, 0.0, 0.0)
        R["shop_ext"].location = (0, 0, -60)
        R["tower_glow"].data.energy = 0
    else:
        grad.elements[0].color = (0.035, 0.05, 0.10, 1)
        grad.elements[1].color = (0.004, 0.007, 0.02, 1)
        w.nodes["stars"].inputs[1].default_value = 0.6
        w.nodes["bg"].inputs["Strength"].default_value = 1.0
        R["moonlight"].data.energy = 0.35
        R["sun"].data.energy = 0.0
        fl = 1.0
        for k, L in enumerate(R["lamps"]):
            f = 1.0 + 0.12 * math.sin(t * 13 + k * 2.1) * math.sin(t * 7.3 + k)
            if S[15] <= t < S[17]:
                f *= 0.75 + 0.25 * (math.sin(t * 23 + k * 5) > -0.6)
            L.data.energy = 90 * f
        lib.emit_strength_socket(R["lamp_mat"]).default_value = 14.0
        for m in R["win_mats"]:
            m.node_tree.nodes["base"].outputs[0].default_value = 3.5 if m.name == "win_lit" else 0.0
        vs = next(n for n in R["town_fog"].node_tree.nodes if n.bl_idname == "ShaderNodeVolumeScatter")
        vs.inputs["Density"].default_value = 0.03
        vs.inputs["Color"].default_value = (0.60, 0.68, 0.85, 1)
        R["shop_ext"].scale = (1, 1, 1)
        R["shop_ext"].location = (0, 0, 0)
        R["tower_glow"].data.energy = 60 + 400 * ramp(t, S[28], S[28] + 1.2)
    # golden wave over the roofs (shot 29)
    wv = (t - S[28]) * 38.0 if t >= S[28] else -100.0
    for m in R["win_mats"]:
        m.node_tree.nodes["wave"].outputs[0].default_value = wv
    # shop candle flicker
    f = 1.0 + 0.18 * math.sin(t * 17) * math.sin(t * 5.3) + 0.08 * math.sin(t * 41)
    R["candle"].data.energy = 22 * f
    R["flame"].scale = (0.012 * (1 + 0.1 * math.sin(t * 23)), 0.012, 0.03 * f)
    for k, L in enumerate(R.get("candles2", [])):
        L.data.energy = 10 * (1.0 + 0.15 * math.sin(t * 15 + k * 3))
    R["oillamp"].data.energy = 45 * (1.0 + 0.06 * math.sin(t * 11))
    # shop door + bell
    if t < S[9] + 0.25:
        dr = 0.0
    else:
        dr = 95 * smooth(ramp(t, S[9] + 0.25, S[9] + 1.0))
    R["shop_door"].rotation_euler = (0, 0, D(dr))
    bt = t - (S[9] + 0.3)
    R["shop_bell"].rotation_euler = (D(25 * math.sin(bt * 22) * math.exp(-bt * 2.5)) if bt > 0 else 0, 0, 0)
    # note corner lifted by the wind
    NOTE_KEY.value = 0.35 + 0.35 * math.sin(t * 2.3) * math.sin(t * 0.9 + 1) if t >= S[31] else 0.0
    # wave ring
    if S[28] <= t < S[29]:
        rr = (t - S[28]) * 38.0
        RING.scale = (rr, rr, 25)
        lib.emit_strength_socket(ringm).default_value = 30.0 * (1 - ramp(t, S[28] + 1.2, S[29]))
    else:
        RING.scale = (0.01, 0.01, 25)
        lib.emit_strength_socket(ringm).default_value = 0.0
    # end card light
    a = smooth(ramp(t, S[35] + 0.25, S[35] + 1.6))
    lib.emit_strength_socket(R["enddial_mat"]).default_value = 1.2 * a
    R["endlight"].data.energy = 600 * a
    R["endrim"].data.energy = 60 * a


def clocks_tick(t, st="SHOP"):
    if st == "VOID":
        ec = R["endclock"]
        tk = math.floor(t) + smooth((t % 1) * 5)
        ec.set(-20, -t * 0.5, -tk * 6)
        return
    if st == "TOWN":
        tc = R["tower_clock"]
        if t < S[28]:
            tc.set(120 - t * 2, 300 - t * 30, 0)
        else:
            dt = t - S[28]
            tc.set(120 - S[28] * 2 + dt * 20, 300 - S[28] * 30 + dt * 240, 0)
        return
    if st == "ROOM":
        return
    # all shelf clocks run backwards in sync
    for c in R["shelf_clocks"]:
        mn = getattr(c, "phase", 0) - t * 90.0
        c.set(mn / 12.0, mn, 0)
    for c in R["pendulums"]:
        c.pend.rotation_euler = (0, D(9 * math.sin(t * 3.1)), 0)
    for k, (gp, w) in enumerate(R["gears"]):
        gp.rotation_euler = (0, 0, -t * w)
    # hero clocks with names: ticking backwards
    for key, c in R["heroes"].items():
        tk = math.floor(t * 1.0) + smooth((t * 1.0) % 1 * 5)
        c.set(-30 - t * 0.5 + c.phase / 12, c.phase - t * 6, (c.phase * 7 - tk * 6))
    tar = R["heroes"]["taras"]
    st = S[7]
    if t >= st - 0.2:
        n = 7 - min(7, math.floor((t - st - 0.05) / 0.25) + smooth(((t - st - 0.05) / 0.25) % 1 * 4)) if t > st + 0.05 else 7
        if t >= st + 1.8:
            n = 0
        tar.set(0, 0, n * 6.0)
    # grandma's clock in the shop
    set_countdown(olS, t, tremble=1.0 if S[13] <= t < S[14] else 0.0)
    for c in (olS, olT, olR):
        lib.emit_strength_socket(c.label_mat).default_value = 6.0 + 3.0 * (0.5 + 0.5 * math.sin(t * 7.5)) if t < S[24] else 6.0
    # tower clock: backwards until the wave, then forward
    tc = R["tower_clock"]
    if t < S[28]:
        tc.set(120 - t * 2, 300 - t * 30, 0)
    else:
        dt = t - S[28]
        tc.set(120 - S[28] * 2 + dt * 20, 300 - S[28] * 30 + dt * 240, 0)
    # end clock
    ec = R["endclock"]
    tk = math.floor(t) + smooth((t % 1) * 5)
    ec.set(-20, -t * 0.5, -tk * 6)


def particles(t):
    # shop dust (always drifting in candle light)
    if SET_OF_SHOT[shot_of(t)] == "SHOP":
        b, ph = SD["base"], SD["ph"]
        pos = b + 0.06 * np.sin(t * np.array([0.21, 0.17, 0.13]) + ph)
        P_shopdust.set(pos, SD["sz"])
    else:
        P_shopdust.hide()
    # dissolve
    if DIS_T0 - 0.1 < t < DIS_T1 + 2.6:
        u = ramp(t, DIS_T0, DIS_T1)
        val = lerp(0.18, 0.82, u)
        rel_t = DIS_T0 + (DS["rel"] - 0.18) / 0.64 * (DIS_T1 - DIS_T0)
        dt = np.clip(t - rel_t, 0, None)
        on = dt > 0
        p = DS["p0"] + DS["v"] * (dt[:, None] ** 1.25) * 0.9 + 0.05 * np.sin(dt[:, None] * 3 + DS["ph"]) * (dt[:, None] > 0)
        sz = DS["sz"] * on * np.clip(1.4 - dt / 2.2, 0, 1)
        sz = np.where(on, sz, 0.0)
        P_dissolve.set(p, sz)
    else:
        P_dissolve.hide()
    # snow through the room door
    if S[18] <= t < S[22]:
        lt = t - S[18] - 0.15
        dt = np.clip(lt - SN["t0"], 0, None)
        on = (lt > SN["t0"]).astype(float)
        door = np.array([X1 - 3.4, 1.85, 0.0])
        drag = 1 - np.exp(-dt * 1.4)
        p = door + SN["p0"] + SN["v"] * drag[:, None] / 1.4 + np.column_stack([np.zeros(700), np.zeros(700), -0.25 * dt])
        p[:, 2] = np.maximum(p[:, 2], 0.01)
        P_snow.set(p, SN["sz"] * on)
    else:
        P_snow.hide()
    # room dust (frozen during shots 25-26)
    tt = t
    if S[24] <= t < S[26]:
        tt = S[24]
    elif t >= S[26]:
        tt = t - (S[26] - S[24])
    pos = RD["base"] + 0.07 * np.sin(tt * np.array([0.25, 0.19, 0.15]) + RD["ph"])
    if S[18] <= t < S[29]:
        P_roomdust.set(pos, RD["sz"] * (1.6 if S[24] <= t < S[27] else 1.0))
    else:
        P_roomdust.hide()
    # sparks around Lina's clock (shot 17)
    if S[16] <= t < S[17]:
        c = clock_world(olT)
        ph = (t * 1.6 + SP["off"]) % 1.0
        a = SP["a"] + SP["w"] * t
        r = SP["r"] * (0.4 + ph)
        p = np.column_stack([c.x + r * np.cos(a), c.y + r * np.sin(a) - ph * 0.15, c.z + SP["z"] + ph * 0.1])
        P_sparks.set(p, (1 - ph) * 1.2)
    else:
        P_sparks.hide()
    # glass shards (shot 24-25: drifting very slowly, frozen in 25)
    if S[23] <= t < S[26]:
        tt = min(t, S[24]) - (AT[23] + 0.3)
        c = clock_world(olR)
        rm = olR.root.matrix_world.to_3x3()
        fwd = rm @ Vector((0, -1, 0))
        d = max(0.0, tt)
        p = np.array(c + fwd * 0.012) + (SH["v"] * 0.012 + np.array(fwd) * 0.02) * d * 0.6
        P_shards.set(p, SH["sz"] * (d > 0))
    else:
        P_shards.hide()
    # morning golden dust swirling in the lot
    if t >= S[29] and t < S[35]:
        a = MD["a"] + MD["w"] * t
        p = np.column_stack([7.3 + MD["r"] * np.cos(a) * 0.9, 12.0 + MD["r"] * np.sin(a) * 0.8, MD["z"] + 0.1 * np.sin(t * 0.7 + MD["a"])])
        P_morning.set(p, MD["sz"])
    else:
        P_morning.hide()
    # end card motes
    if t >= S[35]:
        a = smooth(ramp(t, S[35] + 0.3, S[35] + 2.0))
        p = np.array([X2, 0, 0]) + EM["p"] + 0.05 * np.sin(t * 0.4 + EM["ph"])
        P_endmotes.set(p, np.ones(160) * a)
    else:
        P_endmotes.hide()


EXPOSURE = {0: 0.9, 3: 0.3, 4: 0.3, 8: 0.4, 15: 0.5, 16: 0.3, 17: 0.3, 28: 0.7, 29: 0.0, 30: 0.2, 31: 0.2, 32: 0.0, 33: 0.0, 34: 0.0, 35: 0.3}
MBLUR = set()

# shelf position memory for grandma's clock
olS.home = olS.root.matrix_world.translation.copy() if False else Vector(olS.root.location)


def update(scene, *_):
    t = (scene.frame_current - 1 + scene.frame_subframe) / FPS
    i = shot_of(t)
    st = SET_OF_SHOT[i]
    env(t)
    clocks_tick(t, st)
    if st == "SHOP":
        anim_shop(t)
    if st == "TOWN":
        anim_town(t)
        anim_morning_hand(t)
    if st == "ROOM":
        anim_room(t)
    bpy.context.view_layer.update()
    particles(t)
    c = cam(i, t)
    if i == 17:
        eye = linaT.eyes[1].matrix_world.translation
        back = (c["loc"] - eye).normalized()
        pos = c["loc"] + back * 0.07 + Vector((0, 0, 0.0))
        q = (eye - pos).to_track_quat("Z", "Y")
        num30.matrix_world = Matrix.Translation(pos) @ q.to_matrix().to_4x4() @ Matrix.Diagonal((-1, 1, 1, 1))
        num30.hide_render = False
    else:
        num30.hide_render = True
    CAM.location = c["loc"]
    d = c["look"] - c["loc"]
    q = d.to_track_quat("-Z", "Y")
    CAM.rotation_euler = (q @ Quaternion((0, 0, 1), c["roll"])).to_euler()
    cam_data.lens = c["lens"]
    cam_data.dof.aperture_fstop = c["f"]
    cam_data.dof.focus_distance = c["focus"] or d.length
    scene.view_settings.exposure = EXPOSURE.get(i, 0.0)


bpy.app.handlers.frame_change_pre.clear()
bpy.app.handlers.frame_change_pre.append(update)


# ------------------------------------------------------------------ CLI
def frame_of(t):
    return int(round(t * FPS)) + 1


SET_OF_SHOT = {}
for _i in range(NSH):
    SET_OF_SHOT[_i] = ("SHOP" if _i in (1, 2, 5, 6, 7, 9, 10, 11, 12, 13, 14) else
                       "ROOM" if 18 <= _i <= 27 else "VOID" if _i == 35 else "TOWN")
SETS = {"TOWN": [], "SHOP": [], "ROOM": [], "VOID": []}
_POINTSET = {"shopdust": "SHOP", "dissolve": "TOWN", "snow": "ROOM", "roomdust": "ROOM", "sparks": "TOWN", "mdust": "TOWN",
             "shards": "ROOM", "endmotes": "VOID"}


def classify():
    bpy.context.view_layer.update()
    for o in bpy.data.objects:
        if o.type in ("EMPTY", "CAMERA"):
            continue
        if o.name in _POINTSET:
            SETS[_POINTSET[o.name]].append(o)
            continue
        x = o.matrix_world.translation.x
        k = "TOWN" if x < 50 else "SHOP" if x < 150 else "ROOM" if x < 250 else "VOID"
        SETS[k].append(o)
    for nm in ("olenaT", "linaclock", "hh_root"):
        pass


_ACTIVE = [None]


def activate(setname):
    if _ACTIVE[0] == setname:
        return
    for k, objs in SETS.items():
        for o in objs:
            if os.environ.get("CM_NOVOL") and o.name.startswith(("townfog", "shazebox", "rhazebox", "sdoorfogbox")):
                o.hide_render = True
                continue
            o.hide_render = (k != setname)
    _ACTIVE[0] = setname


def render_frame(f, path):
    t = (f - 1) / FPS
    i = shot_of(t)
    if not SETS["TOWN"]:
        classify()
    activate(SET_OF_SHOT[i])
    sc.render.use_motion_blur = i in MBLUR
    sc.frame_set(f)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    mode = args[0] if args else "shots"
    os.makedirs(os.path.join(HERE, "preview"), exist_ok=True)
    if mode == "preview":
        for a in args[1:]:
            t = float(a)
            p = os.path.join(HERE, "preview", f"t{t:06.2f}.png")
            t0 = time.time()
            render_frame(frame_of(t), p)
            print("PREVIEW", p, f"{time.time() - t0:.1f}s")
    elif mode == "shots":
        which = [int(x) for x in args[1:]] or list(range(NSH))
        for i in which:
            t = S[i] + (S[i + 1] - S[i]) * 0.6
            p = os.path.join(HERE, "preview", f"shot{i + 1:02d}.png")
            t0 = time.time()
            render_frame(frame_of(t), p)
            print("SHOT", i + 1, p, f"{time.time() - t0:.1f}s")
    elif mode == "render":
        f0, f1 = int(args[1]), int(args[2])
        step = int(args[3]) if len(args) > 3 else 1
        os.makedirs(os.path.join(HERE, "frames"), exist_ok=True)
        for f in range(f0, f1 + 1, step):
            p = os.path.join(HERE, "frames", f"f{f:05d}.png")
            if os.path.exists(p):
                continue
            t0 = time.time()
            render_frame(f, p)
            print("FRAME", f, f"{time.time() - t0:.1f}s", flush=True)
    elif mode == "save":
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "clockmaker.blend"))
