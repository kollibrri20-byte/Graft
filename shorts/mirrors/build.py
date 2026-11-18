"""«Крамниця дзеркал» — vertical 3D short (Cycles, headless bpy). Same CLI as the clockmaker build:
  python build.py shots [i ...] | preview t ... | render F0 F1 [step]
"""
from __future__ import annotations

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
import sets
from lib import smooth, smoother, ramp, lerp, vlerp, empty, sphere, cyl, box, mat, emit
from sets import R, X0, X1, X2, X3

D = math.radians
FPS = 24
SLOTS = [0, 2, 5, 7, 10, 12, 15, 17, 20, 22, 25, 27, 30, 32, 35, 37, 40, 42, 45, 47, 50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80,
         82, 85, 87]
S = [float(x) for x in SLOTS]
END = 92.8
S.append(END)
NSH = 36


def shot_of(t):
    for i in range(NSH):
        if t < S[i + 1]:
            return i
    return NSH - 1


SET_OF_SHOT = {}
for _i in range(NSH):
    SET_OF_SHOT[_i] = ("TOWN" if _i in (0, 5, 18, 28) else "WALL" if _i in (16, 17) else "HOME" if 29 <= _i <= 34 else
                       "VOID" if _i == 35 else "SHOP")

# ------------------------------------------------------------------ scene
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.render.fps = FPS
sc.frame_start = 1
sc.frame_end = int(END * FPS)
sc.render.resolution_x, sc.render.resolution_y = 1080, 1920
sc.render.resolution_percentage = int(os.environ.get("CM_SCALE", "30"))
cy = sc.cycles
cy.samples = int(os.environ.get("CM_SAMPLES", "4"))
cy.use_adaptive_sampling = True
cy.adaptive_threshold = 0.04
if os.environ.get("CM_THREADS"):
    sc.render.threads_mode = "FIXED"
    sc.render.threads = int(os.environ["CM_THREADS"])
cy.use_denoising = True
cy.max_bounces = 5
cy.diffuse_bounces = 1
cy.glossy_bounces = 3
cy.transmission_bounces = 2
cy.transparent_max_bounces = 8
cy.volume_bounces = 0
cy.sample_clamp_indirect = 4.0
cy.caustics_reflective = False
cy.caustics_refractive = False
cy.volume_step_rate = 4.0
sc.render.use_persistent_data = True
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Punchy"

sets.world()
sets.town()
sets.shop()
sets.home()
sets.void()
sets.wall()
TALL, LAG, HALL, VM = R["tall"], R["lag"], R["hallmirror"], R["voidmirror"]
_pk = bpy.data.objects["hporchkey"]
lib.aim(_pk, (X1, 0.3, 1.45))


# ------------------------------------------------------------------ characters
def mk(spec, kind, name, loc=(0, 0, -50), facing=0, seed=0):
    return toon.Toon(dict(spec, name=name), loc, facing, kind, seed=seed)


veyl = mk(toon.VEYL, "veyl", "Veyl")
timS = mk(toon.TIM, "tim", "TimS")
timR = mk(toon.TIM, "tim", "TimR")
timT = mk(toon.TIM, "tim", "TimT")
timH = mk(toon.TIM, "tim", "TimH")
timHR = mk(toon.TIM, "tim", "TimHR")
timV = mk(toon.TIM, "tim", "TimV")
timVR = mk(toon.TIM, "tim", "TimVR")
woman = mk(dict(toon.townsman(1), shirt=(0.25, 0.30, 0.48)), "woman", "Woman", seed=1)
womanR = mk(dict(toon.townsman(1), shirt=(0.25, 0.30, 0.48)), "woman", "WomanR", seed=1)
mother = mk(toon.MOTHER, "mother", "Mother")
motherR = mk(toon.MOTHER, "mother", "MotherR")
cust = [mk(toon.townsman(k), "generic", f"Cust{k}", seed=k) for k in (2, 3)]
custT = mk(toon.townsman(4), "generic", "CustT", seed=4)
walkers = [mk(toon.townsman(k), "generic", f"Walk{k}", seed=k) for k in (0, 1, 5, 6)]
emergers = [mk(toon.townsman(k), "generic", f"Emer{k}", seed=k) for k in (7, 8, 9)]
wallpeople = [mk(toon.townsman(k), "generic", f"WallP{k}", seed=k) for k in range(6)]

# Veyl has no reflection
for o in bpy.data.objects:
    if o.name.startswith("Veyl"):
        o.visible_glossy = False


def objs_of(prefix):
    return [o for o in bpy.data.objects if o.name.startswith(prefix) and o.type == "MESH"]


def place(ch, pos, facing):
    ch.root.location = Vector(pos)
    ch.root.rotation_euler = (0, 0, D(facing))


def park(ch):
    ch.root.location = (ch.root.location.x if abs(ch.root.location.z) < 40 else ch.root.location.x, -60, -50)


def mirror_pose(p):
    out = {}
    for k, v in p.items():
        if isinstance(v, (int, float)):
            out[k] = v
            continue
        if k.endswith("L"):
            out[k[:-1] + "R"] = v
        elif k.endswith("R") and k[:-1] + "L" in ("armL", "elbowL", "legL", "kneeL", "handL"):
            out[k[:-1] + "L"] = v
        elif k in ("spine", "neck", "head", "pelvis_rot"):
            out[k] = (v[0], -v[1], -v[2])
        else:
            out[k] = v
    return out


# ------------------------------------------------------------------ props
paper_png = os.path.join(lib.TEX, "note_mirror.png")


def make_note_png(path):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    if os.path.exists(path):
        return path
    W, H = 600, 760
    rng = np.random.default_rng(3)
    base = np.ones((H, W, 3)) * np.array([232, 226, 210])
    n = np.asarray(Image.fromarray((rng.random((H // 12, W // 12)) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)) / 255.0
    base *= (0.85 + 0.2 * n[..., None])
    img = Image.fromarray(base.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    for k in range(9):  # crumples
        x0, y0 = rng.integers(0, W), rng.integers(0, H)
        d.line([(x0, y0), (x0 + rng.integers(-200, 200), y0 + rng.integers(-200, 200))], fill=(200, 194, 178), width=3)
    f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 92)
    d.text((W / 2, H * 0.36), "Я СПРАВЖНІЙ.", font=f, fill=(25, 20, 35), anchor="mm")
    f2 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 130)
    d.text((W / 2, H * 0.66), "ТІКАЙ", font=f2, fill=(160, 15, 15), anchor="mm")
    img = img.transpose(Image.FLIP_LEFT_RIGHT).filter(ImageFilter.GaussianBlur(0.7))  # written from the other side
    img.save(path)
    return path


note = lib.obj("note", lib.m_plane_uv(6, 8).copy(), (0, 0, -50), lib.image_mat("notem", make_note_png(paper_png), rough=0.85),
               scale=(0.16, 0.2, 1))
note_basis = note.shape_key_add(name="Basis")
nk = note.shape_key_add(name="crumple")
_r = np.random.default_rng(5)
for v, kv in zip(note.data.vertices, nk.data):
    kv.co = v.co + Vector((0, 0, _r.normal(0, 0.03)))
nk.value = 0.5

wrapped = [box(f"wrapcarry{k}", (0, 0, -50), (0.5, 0.06, 0.7), R["paper"]) for k in range(3)]

# shards of the tall mirror
SH_N = 130
FACE_PNG = [os.path.join(lib.TEX, f"face{k}.png") for k in range(4)]
shards = []
_rs = np.random.default_rng(11)
for k in range(SH_N):
    me = bpy.data.meshes.new("shard")
    sz = _rs.uniform(0.04, 0.13) if k >= 12 else _rs.uniform(0.09, 0.14)
    pts = [(_rs.uniform(-1, 1) * sz, 0, _rs.uniform(-1, 1) * sz) for _ in range(3)]
    if k < 12:
        pts = [(-sz, 0, -sz * 0.8), (sz * 1.1, 0, -sz * 0.6), (_rs.uniform(-0.3, 0.3) * sz, 0, sz * 1.1)]
    me.from_pydata(pts, [], [(0, 2, 1)])
    uv = me.uv_layers.new(name="UVMap")
    for li, vi in enumerate(me.polygons[0].vertices):
        p = pts[vi]
        uv.data[li].uv = (0.5 + p[0] / (2.4 * sz), 0.5 + p[2] / (2.4 * sz))
    me.update()
    o = lib.obj(f"shard{k}", me, (0, 0, -50), sets.M()["mirror"])
    shards.append(o)
SHARD = dict(u=_rs.uniform(-0.45, 0.45, SH_N), v=_rs.uniform(-0.95, 0.95, SH_N), sp=_rs.uniform(0.3, 1.3, SH_N),
             side=_rs.normal(0, 0.45, (SH_N, 3)), rot=_rs.normal(0, 1.2, (SH_N, 3)), r0=_rs.uniform(0, 6.28, (SH_N, 3)))
for k in range(12):
    SHARD["u"][k] = _rs.uniform(-0.25, 0.25)
    SHARD["v"][k] = _rs.uniform(-0.3, 0.5)
    SHARD["sp"][k] = _rs.uniform(0.22, 0.32)
    SHARD["rot"][k] *= 0.25

impact_light = lib.light("impact", "POINT", (0, 0, -50), 0, (0.8, 0.88, 1.0), size=0.3)
burst_lights = [lib.light(f"burst{k}", "POINT", (0, 0, -50), 0, (0.8, 0.88, 1.0), size=0.2) for k in range(4)]

# ------------------------------------------------------------------ dissolve (Veyl) + silver blend (emergers)
DISSOLVE = []


def add_dissolve(m, color=(0.8, 0.88, 1.0)):
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    if not out.inputs["Surface"].links:
        return
    src = out.inputs["Surface"].links[0].from_socket
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 9.0; nz.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    val = nt.nodes.new("ShaderNodeValue"); val.outputs[0].default_value = 0.0
    sub = nt.nodes.new("ShaderNodeMath"); sub.operation = "SUBTRACT"
    nt.links.new(nz.outputs["Fac"], sub.inputs[0]); nt.links.new(val.outputs[0], sub.inputs[1])
    alive = nt.nodes.new("ShaderNodeMath"); alive.operation = "GREATER_THAN"; alive.inputs[1].default_value = 0.0
    nt.links.new(sub.outputs[0], alive.inputs[0])
    edge = nt.nodes.new("ShaderNodeMapRange")
    edge.inputs["From Min"].default_value = 0.0; edge.inputs["From Max"].default_value = 0.03
    edge.inputs["To Min"].default_value = 1.0; edge.inputs["To Max"].default_value = 0.0
    nt.links.new(sub.outputs[0], edge.inputs["Value"])
    gate = nt.nodes.new("ShaderNodeMath"); gate.operation = "GREATER_THAN"; gate.inputs[1].default_value = 0.001
    nt.links.new(val.outputs[0], gate.inputs[0])
    e1 = nt.nodes.new("ShaderNodeMath"); e1.operation = "MULTIPLY"
    nt.links.new(edge.outputs[0], e1.inputs[0]); nt.links.new(gate.outputs[0], e1.inputs[1])
    e2 = nt.nodes.new("ShaderNodeMath"); e2.operation = "MULTIPLY"; e2.inputs[1].default_value = 8.0
    nt.links.new(e1.outputs[0], e2.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*color, 1)
    nt.links.new(e2.outputs[0], em.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(src, add.inputs[0]); nt.links.new(em.outputs[0], add.inputs[1])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(alive.outputs[0], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(add.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    DISSOLVE.append(val)


def char_mats(prefix):
    ms = []
    for o in bpy.data.objects:
        if o.name.startswith(prefix) and o.type in ("MESH", "FONT"):
            for s_ in o.material_slots:
                if s_.material and s_.material not in ms:
                    ms.append(s_.material)
    return ms


for m in char_mats("Veyl"):
    add_dissolve(m)

SILVER = []
for e in emergers:
    pre = e.s["name"]
    for m in char_mats(pre):
        b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if b:
            SILVER.append((b, tuple(b.inputs["Base Color"].default_value), b.inputs["Metallic"].default_value, b.inputs["Roughness"].default_value))


def set_silver(f):
    for b, col, met, rough in SILVER:
        b.inputs["Base Color"].default_value = tuple(lerp(c, s_, f) for c, s_ in zip(col, (0.85, 0.87, 0.92, 1.0)))
        b.inputs["Metallic"].default_value = lerp(met, 1.0, f)
        b.inputs["Roughness"].default_value = lerp(rough, 0.08, f)


# ------------------------------------------------------------------ particles
rng = np.random.default_rng(42)
rain_m = mat("rainm", (0.8, 0.85, 0.95), 0.1, emit=(0.7, 0.78, 0.9), emit_str=0.8)
P_rain = lib.Streaks("rain", 2200, 0.22, 0.0022, rain_m)
P_drops = lib.Points("drops", 160, 0.004, mat("dropm", (0.85, 0.9, 1.0), 0.05, emit=(0.6, 0.7, 0.9), emit_str=0.5))
P_dust = lib.Points("shopdust", 400, 0.003, emit("dustw", (1.0, 0.75, 0.45), 2.5))
P_silver = lib.Points("silverdust", 2000, 0.005, emit("dusts", (0.8, 0.88, 1.0), 9.0))
P_drip = lib.Points("drip", 400, 0.006, mat("dripm", (0.9, 0.92, 0.96), 0.05, metal=1.0, emit=(0.6, 0.7, 0.9), emit_str=0.4))
P_void = lib.Points("voidmotes", 140, 0.003, emit("voidm", (0.7, 0.8, 1.0), 5.0))
RN = dict(p=rng.random((2200, 3)), sp=rng.uniform(7, 9, 2200))
SD = dict(base=np.column_stack([rng.uniform(X0 - 1.9, X0 + 1.9, 400), rng.uniform(0.3, 7.8, 400), rng.uniform(0.2, 3.1, 400)]),
          ph=rng.uniform(0, 6.28, (400, 3)), sz=rng.uniform(0.4, 1.3, 400))
DR = dict(v=rng.normal(0, 1, (160, 3)), sz=rng.uniform(0.5, 1.3, 160))
VM_P = dict(p=np.column_stack([rng.uniform(-1.2, 1.2, 140), rng.uniform(-1, 0.5, 140), rng.uniform(0.3, 2.4, 140)]), ph=rng.uniform(0, 6.28, (140, 3)))

# ------------------------------------------------------------------ camera
cam_data = bpy.data.cameras.new("Cam")
cam_data.clip_start = 0.01
cam_data.clip_end = 500
cam_data.dof.use_dof = True
CAM = bpy.data.objects.new("Cam", cam_data)
lib.link(CAM)
sc.camera = CAM


def C(loc, look, lens=35, f=2.8, focus=None):
    return dict(loc=Vector(loc), look=Vector(look), lens=lens, f=f, focus=focus)


def wobble(t, amp, freq=1.0, seed=0):
    return Vector((amp * math.sin(t * 1.3 * freq + seed), amp * 0.6 * math.sin(t * 1.1 * freq + seed * 3), amp * math.sin(t * 1.7 * freq + seed * 5)))


def head_world(ch):
    return ch.P["head"].matrix_world @ ch.hc


def hand_world(ch, side):
    return ch.P["hand" + side].matrix_world.translation.copy()


# ------------------------------------------------------------------ geometry helpers for the tall mirror
TC = TALL.c
TN = TALL.n
TP = Vector((TN.y * -1, TN.x, 0)).normalized()  # along the glass, to the right as seen from the front
TIM_POS = Vector((TC.x, TC.y, 0)) + TN * 1.05
TIM_FACE = math.degrees(math.atan2(-TN.x, TN.y))  # facing the mirror
VEYL_BEHIND = TIM_POS + TN * 0.95
STOOL_POS = TIM_POS - TP * 0.55
IMPACT_T = 53.55


def glass_uv(mm, p):
    """world point -> (u, v) on a magic mirror's glass"""
    local = Matrix.Rotation(-D(mm.rz), 4, "Z") @ (Vector(p) - mm.c)
    return 0.5 + local.x / mm.w, 0.5 + local.z / mm.h


HOLD_STOOL = {"armL": (75, -18, 0), "armR": (75, -18, 0), "elbowL": (35, 0, 0), "elbowR": (35, 0, 0)}


def stand_idle(t, k=0):
    b = math.sin(t * 1.4 + k)
    return dict(toon.STAND, spine=(1 + b, 0, 0), head=(0, 0, 3 * math.sin(t * 0.5 + k)))


# ------------------------------------------------------------------ shop animation
def shard_tau(t):
    if t < IMPACT_T:
        return -1.0
    a = min(t, S[22]) - IMPACT_T                       # real speed until the slow-motion shot
    b = max(0.0, min(t, S[24]) - S[22]) * 0.12         # super slow
    c = max(0.0, t - S[26]) * 0.25                     # resume after the freeze + cracks
    return a + b + c


def anim_shop(t):
    i = shot_of(t)
    # ---- Veyl
    bl = 1.0 if (t % 5.3) < 0.1 else 0.0
    if t < S[13]:
        place(veyl, (X0 + 0.9, 6.95, 0), 0)
        ph = t * 3.0
        pol = dict(toon.STAND, spine=(10, 0, 0), head=(14, 0, -6), armR=(55 + 8 * math.sin(ph), -10 + 10 * math.cos(ph), 0), elbowR=(60, 0, 0),
                   armL=(40, -6, 0), elbowL=(70, 0, 0))
        veyl.set_pose(pol, blink=bl, mouth="neutral", gaze=(0, -10), glow=1.2)
        veyl.set_fingers(1.0, 3)
    elif t < S[19]:
        u = smooth(ramp(t, S[13] + 0.3, S[13] + 1.6))
        pos = vlerp((X0 + 0.9, 6.95, 0), VEYL_BEHIND, u)
        place(veyl, pos, lerp(0, TIM_FACE, u) if u < 1 else TIM_FACE)
        lean = smooth(ramp(t, S[15], S[15] + 1.2))
        p = dict(toon.STAND, spine=(6 + 18 * lean, 0, 0), head=(10 + 8 * lean, 0, 0), neck=(10 * lean, 0, 0), armL=(10, 4, 0), armR=(10, 4, 0))
        veyl.set_pose(p, blink=bl, mouth="smile", smile_w=0.8, gaze=(0, -12), glow=3.0 + 4 * lean, brow=-0.6)
        veyl.set_fingers(1.0, 2)
    elif t < S[27]:
        place(veyl, VEYL_BEHIND, TIM_FACE)
        reach = smooth(ramp(t, S[19] + 0.2, S[19] + 2.4))
        p = dict(toon.STAND, spine=(14, 0, 0), head=(8, 0, 0), armR=(90 * reach, -6, 0), elbowR=(5, 0, 0), handR=(10 * reach, 0, 0))
        if t >= S[20]:
            p = dict(toon.STAND, spine=(-8, 0, 0), head=(-6, 0, 0), armR=(30, 20, 0), armL=(30, 20, 0), elbowL=(40, 0, 0), elbowR=(40, 0, 0))
        veyl.set_pose(p, mouth="smile" if t < S[20] else "open", smile_w=0.85, mouth_open=1.3, gaze=(0, -5), glow=6.0, brow=-0.8 if t < S[25] else 1.4)
        veyl.set_fingers(1.0 + 0.9 * reach * (t < S[20]), 6, 10)
    else:
        place(veyl, VEYL_BEHIND, TIM_FACE)
        p = dict(toon.STAND, spine=(-12, 0, 0), head=(-22, 0, 0), armR=(110, 30, 0), armL=(110, 30, 0), elbowL=(30, 0, 0), elbowR=(30, 0, 0))
        veyl.set_pose(p, mouth="open", mouth_open=1.6, glow=8.0, brow=1.5)
    du = ramp(t, S[27] + 0.4, S[27] + 2.0)
    for v in DISSOLVE:
        v.outputs[0].default_value = lerp(0.18, 0.84, du) if du > 0 else 0.0
    if t > S[27] + 2.4:
        veyl.root.location.z = -50

    # ---- woman + lagging reflection (shot 4)
    wpos = LAG.c + LAG.n * 0.62
    wpos.z = 0
    wface = math.degrees(math.atan2(-LAG.n.x, LAG.n.y))

    def wpose(tt):
        u = smooth(ramp(tt, S[3] + 0.3, S[3] + 1.0)) * (1 - smooth(ramp(tt, S[3] + 2.0, S[3] + 2.6)))
        tilt = 12 * math.sin(max(0, tt - S[3] - 0.6) * 4) * u
        return dict(toon.STAND, armR=(150 * u, 25, 0), elbowR=(80 * u, 0, 0), head=(-4, 0, 4 * u)), tilt, u
    if S[3] - 0.5 <= t < S[4]:
        place(woman, wpos, wface)
        p, tilt, u = wpose(t)
        woman.set_pose(p, mouth="smile", gaze=(0, 0))
        woman.hat.rotation_euler = (0, D(tilt), 0)
        place(womanR, LAG.reflect_point(wpos), LAG.reflect_facing(wface))
        p2, tilt2, u2 = wpose(t - 1.0)
        womanR.set_pose(mirror_pose(p2), mouth="smile")
        womanR.hat.rotation_euler = (0, D(-tilt2), 0)
    else:
        woman.root.location.z = -50
        womanR.root.location.z = -50

    # ---- customers carrying wrapped mirrors out (shot 5)
    for k, c in enumerate(cust):
        if S[4] - 0.3 <= t < S[5]:
            lt = t - S[4]
            pos = Vector((X0 - 0.35 + 0.7 * k, 3.6 + k * 0.8 - lt * 1.2, 0))
            place(c, pos, 0)
            p = dict(toon.walk_cycle(t + k * 0.3), **HOLD_STOOL)
            p["head"] = (-15 + 6 * math.sin(t * 9 + k), 0, 20 * (1 if k else -1))
            c.set_pose(p, mouth="open", mouth_open=0.9 + 0.4 * abs(math.sin(t * 9 + k)), brow=0.4, blink=0.6)
            bpy.context.view_layer.update()
            mid = (hand_world(c, "L") + hand_world(c, "R")) / 2
            wrapped[k].location = mid + Vector((0, -0.18, 0.05))
            wrapped[k].rotation_euler = (0, 0, 0)
        else:
            c.root.location.z = -50
            wrapped[k].location = (0, 0, -50)

    # ---- Tim in the shop
    ch = timS
    if t < S[6]:
        ch.root.location.z = -50
    elif t < S[7]:
        lt = t - S[6]
        pos = vlerp((X0, -0.5, 0), (X0 + 0.1, 0.9, 0), smooth(ramp(lt, 0.3, 1.6)))
        place(ch, pos, 180)
        run = 1 - ramp(lt, 1.2, 1.8)
        ch.set_pose(toon.blend(stand_idle(t), toon.run_cycle(t, 0.36), run), mouth="open", mouth_open=0.7, brow=0.3)
        ch.hood.rotation_euler = (D(-110), 0, 0)  # hood up
        ch.hood.location.z = ch.s["torso"] + 0.12
    elif t < S[8]:
        lt = t - S[7]
        place(ch, (X0 + 0.15, 1.3, 0), 180 + 25 * math.sin(lt * 1.2))
        shake_ = math.sin(lt * 30) * (1 - smooth(ramp(lt, 0.2, 1.0)))
        hoodback = smooth(ramp(lt, 0.15, 0.7))
        ch.set_pose(dict(toon.STAND, head=(-14 + 6 * shake_, 0, 20 * shake_ + 25 * math.sin(lt * 1.3)), armL=(130 * (1 - hoodback) + 10, 20, 0),
                         armR=(130 * (1 - hoodback) + 10, 20, 0), elbowL=(90, 0, 0), elbowR=(90, 0, 0)),
                    mouth="open" if lt > 1.0 else "neutral", mouth_open=0.5, brow=0.8, gaze=(10 * math.sin(lt), 12))
        ch.hood.rotation_euler = (D(-110 * (1 - hoodback)), 0, 0)
        ch.hood.location.z = ch.s["torso"] + 0.02 + 0.1 * (1 - hoodback)
    elif t < S[20]:
        ch.hood.rotation_euler = (0, 0, 0)
        ch.hood.location.z = ch.s["torso"] + 0.02
        if t < S[9]:
            u = smooth(ramp(t, S[8], S[9]))
            place(ch, vlerp((X0 + 0.15, 1.3, 0), TIM_POS, u), lerp(180, TIM_FACE + 360 if TIM_FACE < 0 else TIM_FACE, u))
            ch.set_pose(dict(toon.walk_cycle(t), head=(-6, 0, 0)), mouth="neutral", gaze=(0, 5))
        else:
            place(ch, TIM_POS, TIM_FACE)
            wave = smooth(ramp(t, S[9] + 0.2, S[9] + 0.6)) * (1 - smooth(ramp(t, S[10] - 0.4, S[10])))
            p = dict(stand_idle(t), armR=(10 + 150 * wave, 20, 0), elbowR=(20 + 30 * wave * (0.5 + 0.5 * math.sin(t * 14)), 0, 0))
            scared = smooth(ramp(t, S[13], S[13] + 0.6))
            if t >= S[10]:
                p = dict(stand_idle(t), head=(-4, 0, 0), armL=(10, 8, 0), armR=(10, 8, 0), spine=(-6 * scared, 0, 0))
            if t >= S[13]:
                p = dict(toon.STAND, head=(-14, 0, 25 * smooth(ramp(t, S[13] + 0.6, S[13] + 1.4))), spine=(-8, 0, 0), armL=(25, 20, 0),
                         armR=(25, 20, 0), elbowL=(70, 0, 0), elbowR=(70, 0, 0))
            ch.set_pose(p, mouth="smile" if t < S[10] else "open", mouth_open=0.6, brow=0.2 if t < S[10] else 1.2,
                        blink=1.0 if (t % 3.3) < 0.1 else 0.0, gaze=(0, 3))
    elif t < S[22]:
        lt = t - S[20]
        # grab the stool, spin, then swing into the mirror
        spin = smoother(ramp(lt, 0.4, 1.6))
        swing = smoother(ramp(t, IMPACT_T - 0.5, IMPACT_T))
        place(ch, TIM_POS + (TN * 0.15 * swing), TIM_FACE + 360 * spin)
        reach = smooth(ramp(lt, 0.0, 0.35))
        p = dict(toon.STAND, spine=(10 + 25 * swing, 0, -20 * (1 - spin) * reach), armL=(80 + 70 * (1 - swing) * spin, -15, 0),
                 armR=(80 + 70 * (1 - swing) * spin, -15, 0), elbowL=(25, 0, 0), elbowR=(25, 0, 0), legL=(20 * swing, 0, 0), kneeL=(15, 0, 0))
        ch.set_pose(p, mouth="open", mouth_open=1.0, brow=-0.9)
        ch.skirt.scale = (1 + 0.3 * math.sin(math.pi * spin), 1 + 0.3 * math.sin(math.pi * spin), 1 - 0.12 * math.sin(math.pi * spin))
        bpy.context.view_layer.update()
        if lt > 0.3:
            mid = (hand_world(ch, "L") + hand_world(ch, "R")) / 2
            R["stool"].location = mid + Vector((0, 0, -0.25))
            R["stool"].rotation_euler = (D(-70 * swing), 0, ch.root.rotation_euler.z)
        else:
            R["stool"].location = STOOL_POS
            R["stool"].rotation_euler = (0, 0, 0)
        return
    else:
        place(ch, TIM_POS + TN * 0.15, TIM_FACE)
        p = dict(toon.STAND, spine=(-10, 0, 0), head=(-12, 0, 0), armL=(70, 30, 0), armR=(70, 30, 0), elbowL=(110, 0, 0), elbowR=(110, 0, 0))
        if t >= S[26]:
            p = dict(toon.STAND, head=(-6, 0, 10), armL=(20, 10, 0), armR=(20, 10, 0))
        ch.set_pose(p, mouth="open", mouth_open=0.8, brow=1.4, blink=0.0)
        R["stool"].location = TIM_POS + TN * 0.6 + Vector((0, 0, 0))
        R["stool"].rotation_euler = (D(80), D(10), 0)
    ch.skirt.scale = (1, 1, 1)
    if t < S[20]:
        R["stool"].location = STOOL_POS
        R["stool"].rotation_euler = (0, 0, 0)


def anim_reflection(t):
    """TimR behind the tall mirror: stands still while Tim waves, knocks, shows the note."""
    if not (S[9] <= t < IMPACT_T + 0.05):
        timR.root.location.z = -50
        note.location = (0, 0, -50)
        TALL.node("rip_amp").default_value = 0.0
        return
    place(timR, TALL.reflect_point(TIM_POS), TALL.reflect_facing(TIM_FACE))
    p = dict(toon.STAND, head=(4, 0, 0))
    knock = 0.0
    if t >= S[10]:
        lt = t - S[10]
        kk = (lt * 3.2) % 1.0 if lt < 1.4 else 0.0
        knock = math.sin(kk * math.pi) if lt < 1.4 else 0.0
        p = dict(toon.STAND, armR=(95, 10, 0), elbowR=(60 - 30 * knock, 0, 0), handR=(-30, 0, 0), head=(2, 0, 0))
    if t >= S[11]:
        p = dict(toon.STAND, armR=(100, 18, 0), armL=(100, 18, 0), elbowR=(35, 0, 0), elbowL=(35, 0, 0), handL=(-50, 0, 0), handR=(-50, 0, 0))
    timR.set_pose(p, mouth="frown", brow=1.3 if t >= S[10] else -0.2, gaze=(0, 0), blink=0.0)
    # move TimR right up to the glass for knocking / note
    close = smooth(ramp(t, S[10] - 0.3, S[10] + 0.2))
    tp = TALL.reflect_point(TIM_POS)
    timR.root.location = vlerp(tp, Vector((TC.x, TC.y, 0)) - TN * 0.32, close)
    bpy.context.view_layer.update()
    # ripples from the knuckles
    if S[10] <= t < S[11] + 0.6:
        hp = hand_world(timR, "R")
        u, v = glass_uv(TALL, hp)
        TALL.node("rip_u").default_value = u
        TALL.node("rip_v").default_value = v
        lt = t - S[10]
        TALL.node("rip_t").default_value = (lt * 3.2) % 1.0 * 1.2
        TALL.node("rip_amp").default_value = 0.6 * (lt < 1.6)
    else:
        TALL.node("rip_amp").default_value = 0.0
    if t >= S[11]:
        mid = (hand_world(timR, "L") + hand_world(timR, "R")) / 2
        pos = Vector((mid.x, mid.y, mid.z)) - TALL.n * 0.0
        pos = pos + TALL.n * ((Vector(TC) - pos).dot(TALL.n) - 0.012)  # flat against the glass (inside)
        q = TALL.n.to_track_quat("Z", "Y")
        note.matrix_world = Matrix.Translation(pos) @ q.to_matrix().to_4x4() @ Matrix.Rotation(D(1.5 * math.sin(t * 23)), 4, "Z")
        note.scale = (0.16, 0.2, 1)
    else:
        note.location = (0, 0, -50)


def anim_tall_glass(t):
    g = TALL.glass
    if t < IMPACT_T:
        g.scale = (TALL.w, TALL.h, 1)
        TALL.node("glow").default_value = 0.0
    else:
        g.scale = (0, 0, 0)
    # cloth slides half off in shot 9
    R["cloth"].location = (0.2, -0.08, 0.6)
    fl = smooth(ramp(t, S[8] + 0.2, S[8] + 1.6))
    R["cloth"].location = Vector((0.2 + 0.25 * fl, -0.08, 0.6 - 0.35 * fl))
    R["cloth"].rotation_euler = (D(5), D(-25 - 20 * fl), 0)
    # impact flash
    fi = math.exp(-max(0, t - IMPACT_T) * 9) if t >= IMPACT_T else 0.0
    impact_light.location = TC - TN * 0.2
    impact_light.data.energy = 900 * fi


def anim_shards(t):
    tau = shard_tau(t)
    if tau < 0 or t >= S[29]:
        for o in shards:
            o.location = (0, 0, -50)
        return
    rot0 = Matrix.Rotation(D(TALL.rz), 4, "Z")
    for k, o in enumerate(shards):
        base = TC + TP * (SHARD["u"][k] * TALL.w) + Vector((0, 0, SHARD["v"][k] * TALL.h * 0.5))
        vel = TN * SHARD["sp"][k] * 1.4 + Vector(SHARD["side"][k]) * 0.5 + Vector((0, 0, 0.25))
        if k < 12:  # face shards drift toward where the macro camera looks
            vel = TN * SHARD["sp"][k] * 1.3 + Vector(SHARD["side"][k]) * 0.15 + Vector((0, 0, 0.2))
        g = Vector((0, 0, -0.6 * tau * tau)) if t >= S[26] else Vector((0, 0, -0.05 * tau * tau))
        o.location = base + vel * tau + g
        rr = Vector(SHARD["r0"][k]) + Vector(SHARD["rot"][k]) * tau * 3
        if k < 12:
            o.matrix_world = Matrix.Translation(o.location) @ rot0 @ Euler((rr.x * 0.15, rr.y * 0.15, rr.z * 0.15)).to_matrix().to_4x4()
        else:
            o.rotation_euler = (rr.x, rr.y, rr.z)


def anim_cracks(t):
    m = sets.M()["mirror"].node_tree
    org = m.nodes["crackorigin"]
    org.inputs[0].default_value, org.inputs[1].default_value, org.inputs[2].default_value = TC.x, TC.y, TC.z
    if t >= S[25] + 0.2:
        m.nodes["crackwave"].outputs[0].default_value = (t - S[25] - 0.2) * 4.0
    else:
        m.nodes["crackwave"].outputs[0].default_value = -10.0
    m.nodes["crackglow"].outputs[0].default_value = 10.0 * (1 + 0.6 * math.sin(t * 13)) if t < S[27] + 1 else 4.0
    pts = [Vector((X0 - 1.9, 3.0, 1.6)), Vector((X0 + 1.9, 2.5, 1.8)), Vector((X0, 7.9, 2.0)), Vector((X0 + 1.9, 6.0, 1.5))]
    for k, L in enumerate(burst_lights):
        L.location = pts[k]
        d_ = (pts[k] - TC).length
        tt = t - (S[25] + 0.2 + d_ / 4.0)
        L.data.energy = 300 * math.exp(-tt * 3) if (tt > 0 and S[25] <= t < S[27]) else 0.0
    # mirrors glow for the people stepping out
    gl = smooth(ramp(t, S[26] - 0.2, S[26] + 0.4)) * (1 - smooth(ramp(t, S[27], S[27] + 1.0)))
    lib.emit_strength_socket(sets.M()["mirror"]).default_value = 0.0 if False else lib.emit_strength_socket(sets.M()["mirror"]).default_value


def anim_emergers(t):
    if not (S[26] - 0.1 <= t < S[28]):
        for e in emergers:
            e.root.location.z = -50
        set_silver(0.0)
        return
    lt = t - S[26]
    for k, e in enumerate(emergers):
        x = X0 - 0.9 + k * 0.85
        y = 8.25 - min(lt, 2.4) * 0.55
        place(e, (x, y, 0), 0)
        e.set_pose(dict(toon.walk_cycle(t + k * 0.2, 1.2), head=(-12, 0, 0), armL=(30, 25, 0), armR=(30, 25, 0)), mouth="open", mouth_open=0.7,
                   brow=1.0, blink=0.0)
    set_silver(1.0 - 0.75 * smooth(ramp(t, S[26] + 0.5, S[27] + 2.0)))


# ------------------------------------------------------------------ town
def anim_town(t):
    # customer turning to camera (shot 6)
    if S[5] - 0.2 <= t < S[6]:
        lt = t - S[5]
        turn = smooth(ramp(lt, 0.6, 1.4))
        place(custT, (0.9, 13.3 + min(lt, 0.8) * 0.6, 0), lerp(180, 345, turn))
        p = toon.blend(toon.walk_cycle(t), dict(toon.STAND, head=(-4, 0, -15)), ramp(lt, 0.6, 1.0))
        custT.set_pose(p, mouth="smile", smile_w=1.0 + 1.0 * turn, glow=4.0 * smooth(ramp(lt, 1.6, 2.2)), gaze=(0, 0))
    else:
        custT.root.location.z = -50
    # townspeople walking in perfect sync (shot 19) / hugging (shot 29)
    for k, w in enumerate(walkers):
        if S[18] - 0.2 <= t < S[19]:
            lt = t - S[18]
            place(w, (-1.8 + k * 1.2, 22.5 - lt * 1.1, 0), 0)
            w.set_pose(dict(toon.walk_cycle(t, 1.0), head=(0, 0, 0)), mouth="neutral", glow=5.0, blink=0.0, gaze=(0, 0))
        elif S[28] - 0.2 <= t < S[29]:
            pair, side = divmod(k, 2)
            base = Vector((-2.0 if pair == 0 else 2.0, 19.0 + pair * 3.0, 0))
            place(w, base + Vector((0, 0.32 if side else -0.32, 0)), 180 if side else 0)
            w.set_pose(dict(toon.STAND, armL=(80, -30, 0), armR=(80, -30, 0), elbowL=(60, 0, 0), elbowR=(60, 0, 0), spine=(8, 0, 0), head=(6, 0, 15)),
                       mouth="smile", blink=0.9)
        else:
            w.root.location.z = -50
    # Tim running home (shot 29)
    if S[28] <= t < S[29]:
        lt = t - S[28]
        place(timT, (0.3, 14.0 + lt * 3.8, 0), 180)
        timT.set_pose(dict(toon.run_cycle(t, 0.36), head=(-6, 0, 0)), mouth="open", mouth_open=0.6, brow=0.2)
        timT.hood.rotation_euler = (0, 0, 0)
    else:
        timT.root.location.z = -50


# ------------------------------------------------------------------ home
HUG_POS_M = Vector((X1 - 0.15, 1.85, 0))
HUG_POS_T = Vector((X1 - 0.15, 1.55, 0))


def anim_home(t):
    m, ch = mother, timH
    hugM = dict(toon.STAND, armL=(70, -28, 0), armR=(70, -28, 0), elbowL=(70, 0, 0), elbowR=(70, 0, 0), spine=(14, 0, 0), head=(14, 0, 10))
    hugT = dict(toon.STAND, armL=(70, -20, 0), armR=(70, -20, 0), elbowL=(60, 0, 0), elbowR=(60, 0, 0), head=(-8, 0, -10), spine=(4, 0, 0))
    if t < S[31]:
        # doorway
        lt = t - S[29]
        place(m, (X1, 0.3, 0), 0)
        run = 1 - smooth(ramp(lt, 0.9, 1.4))
        tp = vlerp((X1 + 0.05, -2.6, 0), (X1 + 0.02, 0.0, 0), smooth(ramp(lt, 0.0, 1.3)))
        place(ch, tp, 180)
        hug = smooth(ramp(lt, 1.0, 1.6)) if t < S[30] else 1.0
        ch.set_pose(toon.blend(toon.run_cycle(t, 0.36), hugT, 1 - run), mouth="smile" if hug > 0.5 else "open", mouth_open=0.5, blink=0.9 * hug)
        stroke = math.sin(t * 2.5) if t >= S[30] else 0
        pm = toon.blend(dict(toon.STAND, armL=(40, -5, 0), armR=(40, -5, 0), elbowL=(40, 0, 0), elbowR=(40, 0, 0)), hugM, hug)
        if t >= S[30]:
            pm["armR"] = (120 + 10 * stroke, -20, 0)
            pm["elbowR"] = (70 + 15 * stroke, 0, 0)
        m.set_pose(pm, mouth="smile", blink=0.5 if t >= S[30] else 0, gaze=(0, -15), brow=0.3)
        motherR.root.location.z = -50
        timHR.root.location.z = -50
        return
    # hallway: hugging in front of the small mirror
    place(m, HUG_POS_M, 0)
    place(ch, HUG_POS_T, 180)
    stroke = math.sin(t * 2.5)
    pm = dict(hugM, armR=(115 + 8 * stroke, -20, 0), elbowR=(70 + 10 * stroke, 0, 0))
    wide = smooth(ramp(t, S[34] + 0.4, S[34] + 1.4))
    m.set_pose(pm, mouth="smile", smile_w=1.0 + 0.9 * wide, glow=5.0 * wide, blink=0.0 if t >= S[34] else 0.4, gaze=(0, -12), brow=-0.3 * wide)
    ch.set_pose(hugT, mouth="neutral", blink=0.0 if t >= S[31] + 0.6 else 0.9, gaze=(-25, 0) if t >= S[31] + 0.6 else (0, 0))
    # reflections
    place(timHR, HALL.reflect_point(HUG_POS_T), HALL.reflect_facing(180))
    timHR.set_pose(mirror_pose(hugT), mouth="neutral", blink=0.0 if t >= S[31] + 0.6 else 0.9, gaze=(25, 0) if t >= S[31] + 0.6 else (0, 0))
    if t < S[32]:
        place(motherR, HALL.reflect_point(HUG_POS_M), HALL.reflect_facing(0))
        motherR.set_pose(mirror_pose(pm), mouth="smile", gaze=(0, -12))
        HALL.node("rip_amp").default_value = 0.0
    else:
        gp = HALL.c - HALL.n * 0.48
        place(motherR, (gp.x, gp.y + 0.05, 0), 90)
        lt = t - S[32]
        knock = math.sin(((lt * 3.0) % 1.0) * math.pi) if t >= S[33] else 0.0
        motherR.set_pose(dict(toon.STAND, armL=(92, 18, 0), armR=(92, 18, 0), elbowL=(25, 0, 0), elbowR=(25 + 35 * knock, 0, 0), handL=(-60, 0, 0),
                              handR=(-60, 0, 0), spine=(4, 0, 0), head=(0, 0, 0)),
                         mouth="open", mouth_open=0.9, brow=1.5, gaze=(0, 0), blink=0.0)
        bpy.context.view_layer.update()
        if t >= S[33]:
            hp = hand_world(motherR, "R")
            u, v = glass_uv(HALL, hp)
            HALL.node("rip_u").default_value = u
            HALL.node("rip_v").default_value = v
            HALL.node("rip_t").default_value = (lt * 3.0) % 1.0 * 1.2
            HALL.node("rip_amp").default_value = 0.5
        else:
            HALL.node("rip_amp").default_value = 0.0


# ------------------------------------------------------------------ void + wall
def anim_void(t):
    a = smooth(ramp(t, S[35] + 0.2, S[35] + 1.5))
    R["voidkey"].data.energy = 250 * a
    R["voidface"].data.energy = 40 * a
    place(timV, (X2, -0.62, 0), 180)
    place(timVR, VM.reflect_point((X2, -0.62, 0)), VM.reflect_facing(180))
    bt = t - S[35]
    b1 = 1.0 if 2.0 < bt < 2.12 or 3.4 < bt < 3.52 else 0.0
    b2 = 1.0 if 2.55 < bt < 2.67 or 3.95 < bt < 4.07 else 0.0
    timV.set_pose(dict(toon.STAND, head=(-4, 0, 0)), blink=b1, mouth="neutral")
    timVR.set_pose(dict(toon.STAND, head=(-4, 0, 0)), blink=b2, mouth="smile", smile_w=1.3, glow=1.5 * a)


def anim_wall(t):
    for k, w in enumerate(wallpeople):
        cell = R["wallcells"][k]
        c = cell["c"]
        head_h = w.s["hip"] + 0.02 + w.s["torso"] + w.s["neck"] + w.hc.z
        place(w, (c.x, 0.3, c.z + 0.1 - head_h), 0)
        sh = math.sin(t * 6 + k * 1.3)
        w.set_pose(dict(toon.STAND, armL=(105, 32, 0), armR=(105, 32, 0), elbowL=(30, 0, 0), elbowR=(30, 0, 0), handL=(-55, 0, 0), handR=(-55, 0, 0),
                        head=(-4 + 4 * sh, 0, 5 * math.sin(t * 2 + k)), spine=(6, 0, 0)),
                   mouth="open", mouth_open=1.1 + 0.4 * abs(sh), brow=1.4, blink=0.0, gaze=(0, 0))
        gm = cell["glass"].node_tree.nodes
        gm["fog"].outputs[0].default_value = 0.55 * (0.5 + 0.5 * math.sin(t * 3 + k))
        gm["fog_u"].outputs[0].default_value = 0.5
        gm["fog_v"].outputs[0].default_value = 0.44


# ------------------------------------------------------------------ cameras
def cam(i, t):
    t0, t1 = S[i], S[i + 1]
    u = (t - t0) / (t1 - t0)
    e = smooth(u)
    if i == 0:
        return C(vlerp((-5, -36, 28), (1.2, 4.0, 4.0), smoother(u)), vlerp((3, 20, 0), (4.05, 11.4, 1.7), e), 26, 8)
    if i == 1:
        h = Vector((X0 + 0.9, 6.95, 1.95))
        return C(vlerp(h + Vector((-0.35, -1.05, -0.2)), h + Vector((-0.2, -0.75, -0.15)), e), h + Vector((0, 0, -0.12)), 40, 2.8)
    if i == 2:
        return C(vlerp((X0 + 0.9, 1.5, 1.65), (X0 + 0.9, 6.2, 1.6), e), vlerp((X0 - 2.0, 2.5, 1.6), (X0 - 2.0, 7.0, 1.6), e), 30, 2.8)
    if i == 3:
        wpos = LAG.c + LAG.n * 0.62
        wpos.z = 0
        side = Vector((-LAG.n.y, LAG.n.x, 0))
        loc = wpos + LAG.n * 1.55 + side * 0.42 + Vector((0, 0, 1.6))
        return C(loc, LAG.c + Vector((0, 0, 0.05)), 45, 2.8)
    if i == 4:
        return C((X0 + 0.85, 3.5, 1.6), vlerp((X0 - 0.1, 1.2, 1.2), (X0 - 0.05, 0.5, 1.2), e), 28, 4.0)
    if i == 5:
        h = head_world(custT)
        return C(vlerp((0.4, 12.0, 1.75), (0.45, 12.4, 1.72), e), h + Vector((0, 0, -0.05)), 50, 2.8)
    if i == 6:
        return C((X0 + 0.5, 3.0, 1.0), (X0, -0.2, 1.1), 30, 4.0)
    if i == 7:
        h = head_world(timS)
        return C(vlerp((X0 + 0.9, 2.6, 1.0), (X0 + 0.8, 2.35, 1.0), e), h + Vector((0, 0, -0.2)), 32, 4.0)
    if i == 8:
        p = TC
        return C(vlerp(p + TN * 3.3 + Vector((0.2, 0, 0.35)), p + TN * 1.6 + Vector((0.1, 0, 0.15)), smoother(u)), p, 30, 4.0)
    if i in (9, 10):
        loc = TIM_POS + TN * 1.1 + TP * 0.5 + Vector((0, 0, 1.35))
        return C(loc + wobble(t, 0.01), TC + Vector((0, 0, -0.25)), 38, 4.0)
    if i == 11:
        loc = TIM_POS + TN * 0.8 + TP * 0.35 + Vector((0, 0, 1.25))
        return C(loc, TC + Vector((0, 0, -0.35)), 45, 4.0)
    if i == 12:
        np_ = note.matrix_world.translation if note.location.z > -40 else TC
        return C(np_ + TN * (0.55 - 0.06 * e) + Vector((0.01, 0, 0.01)), np_, 55, 4.0)
    if i == 13:
        h = head_world(timS)
        loc = TC + TN * 0.35 - TP * 0.25 + Vector((0, 0, 1.05 - TC.z + 0.1))
        loc.z = 1.0
        return C(loc + wobble(t, 0.008), h + TN * 0.6 + Vector((0, 0, 0.45)), 30, 4.0)
    if i == 14:
        return C((X0 + 1.6, 5.2, 1.7), (X0 - 1.4, 6.6, 1.2), 24, 5.6)
    if i == 15:
        h = head_world(veyl)
        fwd = veyl.root.matrix_world.to_3x3() @ Vector((0, -1, 0))
        return C(h + fwd * (0.6 - 0.1 * e) + Vector((0.05, 0, -0.04)), h + Vector((0, 0, 0.0)), 55, 2.8)
    if i == 16:
        k = [0, 4, 2][min(2, int(u * 3))]
        c = R["wallcells"][k]["c"]
        uu = u * 3 - int(u * 3)
        return C(c + Vector((0.12 * (1 - uu) - 0.06, -1.35 + 0.2 * uu, 0.05)), c + Vector((0, 0.2, 0.0)), 40, 2.8)
    if i == 17:
        k = 1 if u < 0.5 else 3
        c = R["wallcells"][k]["c"]
        return C(c + Vector((0.04, -0.75 + 0.1 * e, 0.12)), c + Vector((0, 0.3, 0.12)), 50, 2.8)
    if i == 18:
        return C((0.2, 16.0, 0.75), (0.0, 21.0, 1.6), 30, 4.0)
    if i == 19:
        hr = hand_world(veyl, "R")
        fwd = veyl.root.matrix_world.to_3x3() @ Vector((0, -1, 0))
        return C(hr + fwd * 0.55 + Vector((0.05, 0, -0.35)), hr + Vector((0, 0, 0.05)), 26, 4.0)
    if i == 20:
        return C(TIM_POS + TN * 1.6 - TP * 0.6 + Vector((0, 0, 0.9)), TIM_POS + Vector((0, 0, 0.6)), 28, 4.0)
    if i == 21:
        return C(TC + TN * 1.9 + TP * 0.9 + Vector((0, 0, -0.1)), TC + Vector((0, 0, -0.2)), 30, 5.6)
    if i == 22:
        return C(vlerp(TC + TN * 1.0 + TP * 1.1 + Vector((0, 0, 0.25)), TC + TN * 0.9 + TP * 0.9 + Vector((0, 0, 0.2)), e), TC + TN * 0.45, 32, 5.6)
    if i == 23:
        p = shards[0].matrix_world.translation
        return C(p + TN * 0.3 + TP * 0.07 + Vector((0, 0, 0.03)), p, 50, 2.8)
    if i == 24:
        return C((X0 + 0.4, 2.2, 1.6), (X0 - 0.7, 6.6, 1.1), 24, 8)
    if i == 25:
        return C(vlerp((X0 + 1.3, 1.0, 1.4), (X0 + 1.0, 1.6, 1.4), e), (X0 - 0.4, 6.0, 1.5), 22, 8)
    if i == 26:
        return C((X0 + 0.95, 4.3, 1.3), (X0 + 0.1, 8.0, 1.3), 26, 5.6)
    if i == 27:
        h = head_world(veyl) if veyl.root.location.z > -40 else VEYL_BEHIND + Vector((0, 0, 1.9))
        fwd = Vector((math.sin(D(TIM_FACE)), -math.cos(D(TIM_FACE)), 0))
        return C(VEYL_BEHIND + fwd * 1.5 + Vector((0.3, 0, 1.55)), VEYL_BEHIND + Vector((0, 0, 1.55)), 32, 4.0)
    if i == 28:
        p = timT.root.location.copy() if timT.root.location.z > -40 else Vector((0.3, 14, 0))
        return C(p + Vector((0.4, -2.4, 1.0)) + wobble(t, 0.03, 3), p + Vector((0, 3, 0.6)), 30, 4.0)
    if i == 29:
        return C((X1 + 0.35, -2.7, 1.15), (X1, 0.1, 1.0), 32, 4.0)
    if i == 30:
        h = head_world(mother)
        return C(vlerp((X1 + 0.32, -0.75, 1.35), (X1 + 0.3, -0.6, 1.35), e), h + Vector((0, 0, -0.03)), 50, 2.8)
    if i in (31, 32):
        ref = Vector((HALL.c.x - 0.83, 1.7, 1.35))
        d_ = (HALL.c - ref).normalized()
        dist = lerp(1.7, 1.15, smoother(u)) if i == 31 else 1.0
        if i == 32:
            d_ = (HALL.c - Vector((HALL.c.x - 0.5, 2.45, 1.45))).normalized()
        return C(HALL.c + d_ * dist + Vector((0, 0, 0.05)), HALL.c + Vector((0, 0, -0.03)), 40 if i == 31 else 45, 4.0)
    if i == 33:
        hp = hand_world(motherR, "R")
        return C(Vector((X1 - 0.5, hp.y - 0.12, hp.z + 0.04)), Vector((HALL.c.x, hp.y, hp.z)), 50, 2.8)
    if i == 34:
        h = head_world(mother)
        return C(h + Vector((0.5, -0.5, 0.15)), h + Vector((0, 0, -0.02)), 60, 2.8)
    if i == 35:
        return C((X2 + 0.35, -1.55, 1.42), (X2, 0.0, 1.32), 40, 4.0)


EXPOSURE = {0: 0.8, 5: 0.5, 18: 0.5, 28: 0.6, 16: 0.2, 17: 0.2, 35: 0.3, 29: 0.5, 30: 0.6}
for _i in range(NSH):
    if SET_OF_SHOT[_i] == "SHOP":
        EXPOSURE.setdefault(_i, 0.9)

# ------------------------------------------------------------------ particles per frame
def particles(t, st, camloc):
    i = shot_of(t)
    # rain: around the camera in the town, outside the door in shots 7 and 30-31
    rain_box = None
    if st == "TOWN":
        rain_box = (camloc + Vector((-5, -2, -3)), Vector((10, 14, 9)))
    elif i == 6:
        rain_box = (Vector((X0 - 2, -4.0, 0)), Vector((4, 3.6, 3.2)))
    elif i in (29, 30):
        rain_box = (Vector((X1 - 2, -4.0, 0)), Vector((4, 3.8, 3.2)))
    if rain_box:
        o, s = rain_box
        p = RN["p"].copy()
        p[:, 2] = (p[:, 2] - t * RN["sp"] / s.z) % 1.0
        pos = np.array(o) + p * np.array(s)
        near = np.linalg.norm(pos - np.array(camloc), axis=1) < 1.3
        P_rain.set(pos, np.where(near, 0.0, 1.0))
    else:
        P_rain.hide()
    # water drops shaken off Tim's raincoat (shot 8)
    if S[7] <= t < S[7] + 1.4:
        h = head_world(timS)
        lt = t - S[7]
        p = np.array(h) + DR["v"] * np.array([0.4, 0.4, 0.2]) * lt * 2 + np.array([0, 0, -0.6]) * lt * lt * 3
        P_drops.set(p, DR["sz"])
    else:
        P_drops.hide()
    if st == "SHOP":
        pos = SD["base"] + 0.06 * np.sin(t * np.array([0.21, 0.17, 0.13]) + SD["ph"])
        if S[24] <= t < S[25]:
            pos = SD["base"] + 0.06 * np.sin(S[24] * np.array([0.21, 0.17, 0.13]) + SD["ph"])
        P_dust.set(pos, SD["sz"])
    else:
        P_dust.hide()
    # Veyl silver dust
    if S[27] <= t < S[28]:
        if not hasattr(particles, "vp"):
            bpy.context.view_layer.update()
            vs = []
            for o in objs_of("Veyl"):
                mw = o.matrix_world
                vs += [tuple(mw @ v.co) for v in list(o.data.vertices)[::3]]
            vs = np.array(vs)
            r_ = np.random.default_rng(1)
            particles.vp = vs[r_.choice(len(vs), 2000)]
            particles.rel = r_.uniform(0.18, 0.84, 2000)
            particles.v = np.column_stack([r_.uniform(-0.3, 0.3, 2000), r_.uniform(-0.3, 0.3, 2000), r_.uniform(0.2, 1.0, 2000)]) + np.array(TN) * 0.6
        d0 = S[27] + 0.4
        rel = d0 + (particles.rel - 0.18) / 0.66 * 1.6
        dt = np.clip(t - rel, 0, None)
        p = particles.vp + particles.v * dt[:, None] ** 1.2
        P_silver.set(p, np.where(dt > 0, np.clip(1.3 - dt / 2.0, 0, 1), 0))
    else:
        P_silver.hide()
    # dripping liquid silver from the emergers (shot 27)
    if S[26] <= t < S[27]:
        r_ = np.random.default_rng(int(t * 24))
        bpy.context.view_layer.update()
        pts = []
        for k, e in enumerate(emergers):
            base = e.root.matrix_world.translation
            n = 130
            ph = (np.arange(n) / n + t * 0.8) % 1.0
            xs = np.random.default_rng(k).uniform(-0.18, 0.18, n)
            ys = np.random.default_rng(k + 9).uniform(-0.1, 0.1, n)
            zs = np.random.default_rng(k + 19).uniform(0.6, 1.7, n) * (1 - ph) ** 0.5
            pts.append(np.column_stack([base.x + xs, base.y + ys, zs]))
        P_drip.set(np.vstack(pts)[:400])
    else:
        P_drip.hide()
    if st == "VOID":
        a = smooth(ramp(t, S[35] + 0.5, S[35] + 2.0))
        P_void.set(np.array([X2, 0, 0]) + VM_P["p"] + 0.05 * np.sin(t * 0.4 + VM_P["ph"]), np.ones(140) * a)
    else:
        P_void.hide()
    R["puddle"].node_tree.nodes["rain_noise"].inputs["W"].default_value = t * 2.0


def env(t, st):
    for k, (L, fl) in enumerate(R["candles"]):
        f = 1.0 + 0.18 * math.sin(t * 17 + k) * math.sin(t * 5.3 + k * 2) + (0.5 * math.sin(t * 40) if S[13] <= t < S[13] + 1.0 else 0)
        L.data.energy = 16 * f
        fl.scale = (0.011, 0.011, 0.028 * f)
    bri = 1.0 + 1.5 * smooth(ramp(t, S[28] + 0.5, S[29])) if t >= S[28] else 1.0
    for k, L in enumerate(R["lamps"]):
        L.data.energy = 80 * bri * (1.0 + 0.1 * math.sin(t * 13 + k))
    lib.emit_strength_socket(R["lamp_mat"]).default_value = 12.0 * bri
    # shop door: bursts open (shot 7), customers leave (shot 5)
    if S[4] + 0.6 <= t < S[5]:
        dr = 80 * smooth(ramp(t, S[4] + 0.6, S[4] + 1.1)) * (1 - smooth(ramp(t, S[5] - 0.4, S[5])))
    elif S[6] <= t < S[8]:
        dr = 105 * smooth(ramp(t, S[6] + 0.1, S[6] + 0.35)) - 8 * math.sin(max(0, t - S[6] - 0.35) * 12) * math.exp(-max(0, t - S[6] - 0.35) * 3)
    else:
        dr = 0
    R["shop_door"].rotation_euler = (0, 0, D(-dr))
    for tb in (S[4] + 0.6, S[6] + 0.1):
        bt = t - tb
        if 0 < bt < 3:
            R["shop_bell"].rotation_euler = (D(25 * math.sin(bt * 22) * math.exp(-bt * 2.5)), 0, 0)
            break
    else:
        R["shop_bell"].rotation_euler = (0, 0, 0)


_ACTIVE = [None]
SETS = {"TOWN": [], "SHOP": [], "HOME": [], "VOID": [], "WALL": []}
_POINTSET = {"rain": None, "drops": "SHOP", "shopdust": "SHOP", "silverdust": "SHOP", "drip": "SHOP", "voidmotes": "VOID"}


def classify():
    bpy.context.view_layer.update()
    for o in bpy.data.objects:
        if o.type == "CAMERA":
            continue
        if o.type == "EMPTY" and o.instance_type != "COLLECTION":
            continue
        if o.name in _POINTSET:
            if _POINTSET[o.name]:
                SETS[_POINTSET[o.name]].append(o)
            continue
        x = o.get("set_x", o.matrix_world.translation.x)
        if o.name.startswith(("TimS", "TimR", "Veyl", "Woman", "Cust2", "Cust3", "Emer", "note", "shard", "wrapcarry", "impact", "burst")):
            k = "SHOP"
        elif o.name.startswith(("TimH", "Mother")):
            k = "HOME"
        elif o.name.startswith(("TimV",)):
            k = "VOID"
        elif o.name.startswith("WallP"):
            k = "WALL"
        elif o.name.startswith(("TimT", "CustT", "Walk")):
            k = "TOWN"
        else:
            k = "TOWN" if x < 50 else "SHOP" if x < 150 else "HOME" if x < 250 else "VOID" if x < 350 else "WALL"
        SETS[k].append(o)


def lib_active(name):
    return _ACTIVE[0] == name


def activate(setname):
    if _ACTIVE[0] == setname:
        return
    for k, objs in SETS.items():
        for o in objs:
            o.hide_render = (k != setname)
    _ACTIVE[0] = setname


def update(scene, *_):
    t = (scene.frame_current - 1 + scene.frame_subframe) / FPS
    i = shot_of(t)
    st = SET_OF_SHOT[i]
    env(t, st)
    if st == "SHOP":
        anim_shop(t)
        anim_reflection(t)
        anim_tall_glass(t)
        anim_shards(t)
        anim_cracks(t)
        anim_emergers(t)
        if S[3] - 0.5 <= t < S[4]:
            pass
    elif st == "TOWN":
        anim_town(t)
    elif st == "HOME":
        anim_home(t)
    elif st == "VOID":
        anim_void(t)
    elif st == "WALL":
        anim_wall(t)
    bpy.context.view_layer.update()
    c = cam(i, t)
    particles(t, st, c["loc"])
    CAM.location = c["loc"]
    d = c["look"] - c["loc"]
    CAM.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cam_data.lens = c["lens"]
    cam_data.dof.aperture_fstop = c["f"]
    cam_data.dof.focus_distance = c["focus"] or d.length
    scene.view_settings.exposure = EXPOSURE.get(i, 0.0)


bpy.app.handlers.frame_change_pre.clear()
bpy.app.handlers.frame_change_pre.append(update)


def frame_of(t):
    return int(round(t * FPS)) + 1


def bake_faces():
    """Portraits of the trapped people for the face shards (rendered once, cached in tex/)."""
    if all(os.path.exists(p) for p in FACE_PNG):
        return
    classify()
    activate("WALL")
    old = (sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage)
    sc.render.resolution_x = sc.render.resolution_y = 320
    sc.render.resolution_percentage = 100
    for k in range(4):
        sc.frame_set(frame_of(S[17] + 0.3 * k))
        c = R["wallcells"][k]["c"]
        CAM.location = c + Vector((0.0, -0.55, 0.1))
        d = (c + Vector((0, 0.3, 0.1))) - CAM.location
        CAM.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        cam_data.lens = 50
        cam_data.dof.focus_distance = d.length
        sc.render.filepath = FACE_PNG[k]
        bpy.ops.render.render(write_still=True)
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = old
    _ACTIVE[0] = None


def assign_face_mats():
    for k in range(12):
        m = lib.image_mat(f"facem{k}", FACE_PNG[k % 4], rough=0.15, emit_str=0.6, metal=0.3)
        lib.set_mat(shards[k], m)


def render_frame(f, path):
    if not SETS["TOWN"]:
        bake_faces()
        assign_face_mats()
        classify()
    t = (f - 1) / FPS
    i = shot_of(t)
    activate(SET_OF_SHOT[i])
    sc.frame_set(f)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    args = sys.argv[1:]
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
            print("SHOT", i + 1, p, f"{time.time() - t0:.1f}s", flush=True)
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
