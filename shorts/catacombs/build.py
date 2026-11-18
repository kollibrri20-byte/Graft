"""Паризькі катакомби — cutaway short timed to the voiceover through beats.json.

  blender --background --python build.py -- <workdir> [preview|half|full|still:<frame>]
Beats (script.txt):
 0 Під вулицями Парижа лежать кістки понад шести мільйонів людей.   street + Eiffel vista -> down to the bone heap
 1 Коли міські кладовища переповнилися,                              cemetery: coffins stack up until it bursts
 2 останки перенесли в старі підземні каменоломні.                  shaft dug, bones fall into the old quarry
 3 Тепер там кілометри тунелів,                                      tunnels race out left/right, lamps on, wide
 4 а стіни викладені черепами.                                       skull walls stack up, push into a close-up
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_scripts(here):
    import glob
    for c in (os.environ.get("KYLO_SCRIPTS", ""), os.path.join(here, "..", "..", "scripts"), os.path.join(here, "scripts")):
        if c and os.path.exists(os.path.join(c, "s3d.py")):
            return os.path.abspath(c)
    hits = sorted(glob.glob(os.path.expanduser("~/.claude/plugins/*/*/kylo-3d-shorts/skills/3d-short/scripts"))
                  + glob.glob(os.path.expanduser("~/.claude/plugins/cache/*/kylo-3d-shorts/*/skills/3d-short/scripts")))
    if hits:
        return hits[-1]
    raise SystemExit("set KYLO_SCRIPTS=<plugin>/skills/3d-short/scripts")


sys.path.insert(0, _find_scripts(HERE))
import s3d  # noqa: E402
import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [HERE]
WORK = argv[0]
MODE = argv[1] if len(argv) > 1 else "full"
B = s3d.load_beats(os.path.join(WORK, "beats.json"))
END = B[-1]["fe"] + 60
W = s3d.when
R = random.Random(11)

# Paris ground: thin fill, then the pale Lutetian limestone the quarries were cut in
s3d.SOIL_LAYERS = [
    ("brown_mud_02", -0.8, 1.4, (0.85, 0.8, 0.75)),
    ("dry_ground_rocks", -2.6, 1.8, (0.95, 0.85, 0.75)),
    ("sandstone_cracks", -5.0, 2.4, (1.0, 0.92, 0.80)),
    ("quarry_wall", -99, 2.6, (1.0, 0.93, 0.82)),
]

s3d.new_short(sky="belfast_sunset_puresky", sun_elev=34, sun_azim=-35)
bpy.context.scene.frame_end = END
sun = bpy.data.objects["Sun"]
sun.data.color = (1.0, 0.86, 0.68)
sun.data.energy = 4.0

WIDTH = 40
g = s3d.ground_section(width=WIDTH, depth=16.0, grass=False, stones=60, roots=10)
slab = bpy.data.objects[g["s3d_lawn"]]
slab.data.materials.clear()
slab.data.materials.append(s3d.tex("cobblestone_floor_05", tile=1.6, tint=(0.9, 0.86, 0.8), fallback=(0.4, 0.38, 0.36), name="Cobbles"))

# ---------------------------------------------------------------- materials
BONE = s3d.mat("Bone", (0.78, 0.70, 0.55), rough=0.62, noise=0.35, noise_scale=40)
BONE_OLD = s3d.mat("BoneOld", (0.62, 0.54, 0.40), rough=0.7, noise=0.5, noise_scale=30)
DARK = s3d.mat("Socket", (0.02, 0.015, 0.01), rough=1.0)
WOOD = s3d.tex("weathered_brown_planks", tile=0.8, tint=(0.75, 0.6, 0.5), fallback=(0.3, 0.18, 0.1), name="CoffinWood")
LIME = s3d.tex("white_sandstone_blocks_02", tile=2.2, tint=(1.05, 0.98, 0.88), fallback=(0.85, 0.8, 0.7), name="Facade")
SLATE = s3d.tex("roof_slates_02", tile=1.4, tint=(0.62, 0.68, 0.78), fallback=(0.3, 0.33, 0.38), name="Slate")
IRON = s3d.mat("Iron", (0.03, 0.03, 0.035), rough=0.45, metal=0.8)
GLASS = s3d.mat("WinGlass", (0.08, 0.1, 0.13), rough=0.08, metal=0.3)
WARM = s3d.mat_emit("WarmWindow", (1.0, 0.72, 0.38), 2.2)
HEADSTONE = s3d.tex("rock_wall_08", tile=0.6, tint=(0.75, 0.75, 0.75), fallback=(0.5, 0.5, 0.5), name="Headstone")


def link(o):
    bpy.context.scene.collection.objects.link(o)
    return o


# ---------------------------------------------------------------- mesh kits (built once, then tiled with numpy)
def mesh_arrays(me):
    """(verts Nx3, faces list of tuples, material index per face) of an evaluated mesh."""
    v = np.array([x.co[:] for x in me.vertices], dtype=np.float32)
    f = [tuple(p.vertices) for p in me.polygons]
    mi = [p.material_index for p in me.polygons]
    return v, f, mi


def bake(obj):
    """Apply modifiers and return arrays, then delete the object."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    me.transform(obj.matrix_world)
    out = mesh_arrays(me)
    bpy.data.meshes.remove(me)
    bpy.data.objects.remove(obj, do_unlink=True)
    return out


def merge(parts):
    vs, fs, ms, off = [], [], [], 0
    for v, f, m in parts:
        vs.append(v)
        fs += [tuple(i + off for i in face) for face in f]
        ms += m
        off += len(v)
    return np.concatenate(vs), fs, ms


def uv_sphere(loc, scale, seg=14, rings=8, mat_index=0):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=1.0)
    me = bpy.data.meshes.new("tmp")
    bm.to_mesh(me)
    bm.free()
    o = link(bpy.data.objects.new("tmp", me))
    o.location, o.scale = loc, scale
    for p in me.polygons:
        p.material_index = mat_index
    return o


def make_skull():
    """Low-poly skull facing -Y (towards the camera): cranium + face, eye sockets and nose cut, dark inside."""
    cran = uv_sphere((0, 0.02, 0.03), (0.072, 0.088, 0.072), seg=16, rings=10)
    face = uv_sphere((0, -0.045, -0.03), (0.056, 0.045, 0.048), seg=14, rings=8)
    u = cran.modifiers.new("u", "BOOLEAN")
    u.operation, u.object, u.solver = "UNION", face, "EXACT"
    cutters = [uv_sphere((sx * 0.027, -0.085, -0.008), (0.021, 0.03, 0.019), seg=12, rings=6) for sx in (-1, 1)]
    cutters.append(uv_sphere((0, -0.095, -0.042), (0.010, 0.03, 0.014), seg=8, rings=5))
    for c in cutters:
        d = cran.modifiers.new("d", "BOOLEAN")
        d.operation, d.object, d.solver = "DIFFERENCE", c, "EXACT"
    skull = bake(cran)
    for o in [face] + cutters:
        bpy.data.objects.remove(o, do_unlink=True)
    inner = [bake(uv_sphere((sx * 0.027, -0.07, -0.008), (0.017, 0.012, 0.016), seg=8, rings=5, mat_index=1)) for sx in (-1, 1)]
    inner.append(bake(uv_sphere((0, -0.083, -0.042), (0.008, 0.01, 0.011), seg=6, rings=4, mat_index=1)))
    jaw = bake(uv_sphere((0, -0.06, -0.083), (0.042, 0.035, 0.016), seg=12, rings=6))
    teeth = bake(uv_sphere((0, -0.088, -0.068), (0.03, 0.006, 0.008), seg=10, rings=4, mat_index=1))
    return merge([skull, jaw, teeth] + inner)


def make_femur(length=0.42):
    """Long bone lying along Y with the knobbly head towards the camera."""
    shaft = bpy.data.objects.new("tmp", bpy.data.meshes.new("tmp"))
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.016, radius2=0.016, depth=length)
    bm.to_mesh(shaft.data)
    bm.free()
    link(shaft)
    shaft.rotation_euler = (math.pi / 2, 0, 0)
    shaft.location = (0, length / 2, 0)
    parts = [bake(shaft)]
    for sx in (-1, 1):
        parts.append(bake(uv_sphere((sx * 0.017, -0.005, 0), (0.024, 0.026, 0.024), seg=10, rings=6)))
        parts.append(bake(uv_sphere((sx * 0.017, length + 0.005, 0), (0.022, 0.024, 0.022), seg=8, rings=5)))
    return merge(parts)


def tile(kit, mats, xforms, name):
    """One object holding many copies of `kit` (verts, faces, mat idx) under 4x4 transforms."""
    v, f, mi = kit
    vh = np.c_[v, np.ones(len(v), np.float32)]
    vs, fs, ms = [], [], []
    for k, M in enumerate(xforms):
        vs.append((vh @ np.array(M, np.float32).T)[:, :3])
        off = k * len(v)
        fs += [tuple(i + off for i in face) for face in f]
        ms += mi
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.concatenate(vs).tolist(), [], fs)
    for m in mats:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", ms)
    me.polygons.foreach_set("use_smooth", [True] * len(fs))
    me.update()
    return link(bpy.data.objects.new(name, me))


def xf(loc, rz=0.0, rx=0.0, ry=0.0, s=1.0):
    return Matrix.Translation(loc) @ Matrix.Rotation(rz, 4, "Z") @ Matrix.Rotation(ry, 4, "Y") @ Matrix.Rotation(rx, 4, "X") @ Matrix.Scale(s, 4)


SKULL = make_skull()
FEMUR = make_femur()


def bone_scatter(n, x0, x1, z0, z1, y0=0.15, y1=0.6, seed=0, skull_share=0.35, mats=(BONE, DARK)):
    """Random jumble of skulls and long bones in a box (for heaps, graves, falling loads)."""
    r = random.Random(seed)
    sk, fe = [], []
    for _ in range(n):
        p = Vector((r.uniform(x0, x1), r.uniform(y0, y1), r.uniform(z0, z1)))
        if r.random() < skull_share:
            sk.append(xf(p, rz=r.uniform(-0.7, 0.7), rx=r.uniform(-0.5, 0.5), ry=r.uniform(-0.6, 0.6), s=r.uniform(0.9, 1.1)))
        else:
            fe.append(xf(p, rz=r.uniform(0, math.tau), rx=r.uniform(-0.4, 0.4), ry=r.uniform(-1.2, 1.2), s=r.uniform(0.8, 1.05)))
    objs = []
    if sk:
        objs.append(tile(SKULL, mats, sk, "Skulls"))
    if fe:
        objs.append(tile(FEMUR, mats, fe, "Femurs"))
    return objs


def heap(name, cx, cz, w, h, n, seed):
    """Mound of bones resting on a floor at cz, piled highest in the middle."""
    r = random.Random(seed)
    sk, fe = [], []
    for _ in range(n):
        x = r.uniform(-1, 1)
        top = h * (1 - x * x)
        z = cz + 0.04 + r.random() ** 0.7 * max(0.02, top)
        p = Vector((cx + x * w / 2, r.uniform(0.25, 2.6), z))
        if r.random() < 0.4:
            sk.append(xf(p, rz=r.uniform(-0.9, 0.9), rx=r.uniform(-0.6, 0.6), ry=r.uniform(-0.8, 0.8)))
        else:
            fe.append(xf(p, rz=r.uniform(0, math.tau), ry=r.uniform(-0.5, 0.5)))
    parts = [tile(SKULL, (BONE, DARK), sk, name + "_sk"), tile(FEMUR, (BONE, DARK), fe, name + "_fe")]
    # a soft core so the heap never looks hollow
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1, location=(cx, 1.4, cz))
    core = bpy.context.active_object
    core.scale = (w / 2 * 0.95, 1.35, h * 0.8)
    core.data.materials.append(BONE_OLD)
    parts.append(core)
    return s3d.group(name, parts, origin="base")


def skull_wall(name, x0, x1, z0, z1, y=2.86, bands=(0.32, 0.72)):
    """Catacomb wall: rows of femur heads facing out, crossed by bands of skulls (and a skull cap row on top).
    Returns per-metre segments so the wall can be laid section by section."""
    segs = []
    x = x0
    while x < x1 - 0.01:
        xe = min(x1, x + 1.0)
        sk, fe = [], []
        hgt = z1 - z0
        band_z = [z0 + b * hgt for b in bands] + [z1 - 0.09]
        z = z0 + 0.03
        while z < z1 - 0.16:
            if any(abs(z - bz) < 0.1 for bz in band_z):
                z += 0.05
                continue
            xx = x + 0.04 + (0.03 if int(z * 20) % 2 else 0)
            while xx < xe - 0.03:
                fe.append(xf((xx, y - 0.02 + R.uniform(-0.02, 0.02), z + 0.024), rz=R.uniform(-0.15, 0.15), s=R.uniform(0.92, 1.05)))
                xx += 0.085
            z += 0.052
        for bz in band_z:
            xx = x + 0.09
            while xx < xe - 0.07:
                sk.append(xf((xx, y - 0.11, bz), rz=R.uniform(-0.18, 0.18), rx=R.uniform(-0.08, 0.12), s=R.uniform(0.95, 1.08)))
                xx += 0.165
        parts = [tile(FEMUR, (BONE, DARK), fe, f"{name}_fe"), tile(SKULL, (BONE, DARK), sk, f"{name}_sk")]
        seg = s3d.group(f"{name}_{len(segs)}", parts, origin="base")
        segs.append(seg)
        x = xe
    return segs


# ---------------------------------------------------------------- boolean voids in the ground
def void(name, x0, x1, z0, z1, back=3.0):
    c = s3d.box(name, (x1 - x0, back + 0.1, z1 - z0), ((x0 + x1) / 2, back / 2 - 0.05, (z0 + z1) / 2), bevel=0)
    c.hide_render = True
    c.display_type = "WIRE"
    c["s3d_always_hidden"] = 1
    m = g.modifiers.new(name, "BOOLEAN")
    m.operation, m.object, m.solver = "DIFFERENCE", c, "EXACT"
    return c


def grow_void(c, frame, dur, from_x):
    """Tunnel races out horizontally from x = from_x (scale X 0 -> 1 with the pivot at that end)."""
    me = c.data
    for v in me.vertices:
        v.co.x += c.location.x - from_x
    c.location.x = from_x
    c.scale = (0.001, 1, 1)
    s3d._key(c, frame, scale=True)
    c.scale = (1, 1, 1)
    s3d._key(c, frame + dur, scale=True)
    s3d._ease(c, "SINE", "EASE_OUT")


def hide_stones_in(x0, x1, z0, z1, frame):
    for st in s3d._ground.get("stones", []):
        p = st.location
        if x0 - 0.4 < p.x < x1 + 0.4 and z0 - 0.4 < p.z < z1 + 0.4:
            if frame <= 1:
                st.hide_render = st.hide_viewport = True
            else:
                s3d.shrink_out(st, frame, dur=5)


def lamp(loc, frame, energy=60, color=(1.0, 0.62, 0.3), radius=0.08):
    L = bpy.data.lights.new("Lamp", "POINT")
    L.color, L.shadow_soft_size = color, radius
    o = link(bpy.data.objects.new("Lamp", L))
    o.location = loc
    L.energy = 0 if frame > 1 else energy
    if frame > 1:
        L.keyframe_insert("energy", frame=frame)
        L.energy = energy
        L.keyframe_insert("energy", frame=frame + 4)
    bulb = s3d.cylinder("Bulb", 0.05, 0.12, loc, mat=s3d.mat_emit("Flame", (1.0, 0.7, 0.35), 8.0), verts=10)
    if frame > 1:
        s3d.pop_in(bulb, frame, dur=6, sfx=None)
    return o


# ---------------------------------------------------------------- the Paris street above
def haussmann(x, y, w, floors=6, seed=0, front_shops=True):
    """Cream limestone block with tall French windows, iron balconies on floors 2 and 5, grey slate mansard."""
    r = random.Random(seed)
    fh = 3.0
    h = floors * fh
    d = 10.0
    parts = [s3d.box("facade", (w, d, h), (x, y + d / 2, h / 2), LIME, bevel=0.04)]
    parts.append(s3d.box("cornice", (w + 0.25, 0.5, 0.25), (x, y + 0.1, h - 0.1), LIME, bevel=0.05))
    for k in (1, 4):
        parts.append(s3d.box("ledge", (w + 0.1, 0.35, 0.16), (x, y + 0.05, k * fh + 0.05), LIME, bevel=0.03))
    me = bpy.data.meshes.new("mansard")
    rh, ins = 3.6, 1.4
    vs = [(-w / 2, 0, 0), (w / 2, 0, 0), (w / 2, d, 0), (-w / 2, d, 0),
          (-w / 2 + 0.3, ins, rh), (w / 2 - 0.3, ins, rh), (w / 2 - 0.3, d - ins, rh), (-w / 2 + 0.3, d - ins, rh)]
    fs = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)]
    me.from_pydata(vs, [], fs)
    ro = link(bpy.data.objects.new("mansard", me))
    ro.location = (x, y, h)
    ro.data.materials.append(SLATE)
    parts.append(ro)
    cols = max(2, int(w / 2.2))
    step = w / cols
    for fl in range(floors):
        z = fl * fh + 1.55
        for c in range(cols):
            wx = x - w / 2 + step * (c + 0.5)
            if fl == 0 and front_shops:
                parts.append(s3d.box("shop", (step * 0.8, 0.1, 2.3), (wx, y - 0.02, 1.3), GLASS if r.random() < 0.6 else WARM, bevel=0.01))
                continue
            lit = r.random() < 0.28
            parts.append(s3d.box("win", (1.0, 0.1, 1.9), (wx, y - 0.02, z), WARM if lit else GLASS, bevel=0.0))
            parts.append(s3d.box("surround", (1.25, 0.06, 2.15), (wx, y + 0.0, z), LIME, bevel=0.02))
            if fl in (1, 4):
                parts.append(s3d.box("rail", (step * 0.95 if fl == 4 else 1.2, 0.04, 0.05), (wx, y - 0.45, z - 0.15), IRON, bevel=0))
                for k in range(7):
                    parts.append(s3d.box("bar", (0.02, 0.02, 0.8), (wx - 0.5 + k * 0.166, y - 0.45, z - 0.55), IRON, bevel=0))
                parts.append(s3d.box("balc", (step * 0.95 if fl == 4 else 1.3, 0.5, 0.08), (wx, y - 0.25, z - 0.95), LIME, bevel=0.02))
    for c in range(cols):                      # dormers in the mansard
        wx = x - w / 2 + step * (c + 0.5)
        parts.append(s3d.box("dormer", (0.9, 0.6, 1.3), (wx, y + 0.95, h + 1.0), LIME, bevel=0.03))
        parts.append(s3d.box("dwin", (0.6, 0.62, 0.9), (wx, y + 0.93, h + 0.95), WARM if r.random() < 0.3 else GLASS, bevel=0))
    for k in range(2):                         # chimney stacks
        parts.append(s3d.box("chimney", (0.8, 0.5, 1.4), (x + (k - 0.5) * w * 0.6, y + d / 2, h + 3.8), s3d.mat("Brick", (0.55, 0.3, 0.22), rough=0.8, noise=0.3), bevel=0.02))
    return s3d.group("Haussmann", parts)


def eiffel(x, y, H):
    """Simple lattice tower silhouette far down the avenue (exponential leg profile, three platforms)."""
    zs = np.linspace(0, 0.93, 24)
    bm = bmesh.new()
    rings = []
    for z in zs:
        hw = 0.19 * math.exp(-3.43 * z) * H if z > 0.02 else 0.19 * H
        rings.append([bm.verts.new((sx * hw, sy * hw, z * H)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    for a, b in zip(rings, rings[1:]):
        for k in range(4):
            bm.faces.new((a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k]))
    me = bpy.data.meshes.new("Tower")
    bm.to_mesh(me)
    bm.free()
    t = link(bpy.data.objects.new("Tower", me))
    t.location = (x, y, 0)
    wf = t.modifiers.new("Lattice", "WIREFRAME")
    wf.thickness = H * 0.006
    sub = s3d.mat("TowerIron", (0.22, 0.14, 0.09), rough=0.6, metal=0.5)
    t.data.materials.append(sub)
    parts = [t]
    for zf, wf_ in ((0.17, 0.115), (0.35, 0.062)):
        parts.append(s3d.box("deck", (wf_ * 2 * H, wf_ * 2 * H, H * 0.012), (x, y, zf * H), sub, bevel=0))
    parts.append(s3d.cylinder("spire", H * 0.006, H * 0.08, (x, y, 0.96 * H), mat=sub, verts=8))
    return parts


for i, (bx, w) in enumerate(((-21.0, 13.0), (-9.5, 10.5), (9.0, 10.0), (20.5, 13.0))):
    haussmann(bx, 6.0 + (i % 2) * 0.4, w, floors=6, seed=i)
for i, (bx, w, yy) in enumerate(((-7.5, 8, 30), (7.5, 8, 30), (-7.5, 8, 52), (7.5, 8, 52))):  # the avenue receding
    haussmann(bx, yy, w, floors=5, seed=10 + i, front_shops=False)
eiffel(1.0, 240.0, 150.0)
far = s3d.box("FarStreet", (60, 300, 0.1), (0, 150, s3d.TOP - 0.06), s3d.tex("asphalt_02", tile=4, fallback=(0.25, 0.25, 0.27), name="Asphalt"), bevel=0)
pave = s3d.box("Pavement", (WIDTH, 4.0, 0.14), (0, 4.0, s3d.TOP + 0.04), s3d.tex("concrete_floor_02", tile=2, tint=(0.9, 0.88, 0.85), fallback=(0.6, 0.6, 0.6), name="Pavement"), bevel=0.02)
for x in (-14.0, -3.2, 3.2, 14.0):          # wrought-iron street lamps
    pole = s3d.cylinder("LampPole", 0.07, 4.2, (x, 2.6, 2.1), mat=IRON, verts=12)
    head = s3d.box("LampHead", (0.45, 0.45, 0.6), (x, 2.6, 4.45), s3d.mat_emit("LampGlass", (1.0, 0.78, 0.45), 6.0), bevel=0.05)
    capm = s3d.box("LampCap", (0.6, 0.6, 0.12), (x, 2.6, 4.8), IRON, bevel=0.03)
    L = link(bpy.data.objects.new("StreetLight", bpy.data.lights.new("StreetLight", "POINT")))
    L.location, L.data.energy, L.data.color = (x, 2.2, 4.3), 150, (1.0, 0.75, 0.45)

# ---------------------------------------------------------------- the old cemetery (left)
CX = -9.0
yard = s3d.box("CemeteryGrass", (7.6, 3.6, 0.06), (CX, 1.8, s3d.TOP + 0.02), s3d.tex("leafy_grass", tile=1.2, tint=(0.75, 0.85, 0.6), fallback=s3d.PAL["grass"], name="CemGrass"), bevel=0)
stones_above = []
for i, x in enumerate(np.linspace(CX - 3.2, CX + 3.0, 7)):
    yy = 0.9 + (i % 2) * 1.2
    if i % 3 == 1:
        a = s3d.box("CrossV", (0.14, 0.12, 1.15), (x, yy, 0.6), HEADSTONE, bevel=0.02)
        b = s3d.box("CrossH", (0.6, 0.12, 0.14), (x, yy, 0.85), HEADSTONE, bevel=0.02)
        st = s3d.group("Cross", [a, b], origin="base")
    else:
        st = s3d.origin_to_base(s3d.box("Headstone", (0.62, 0.16, 0.85), (x, yy, 0.45), HEADSTONE, bevel=0.06))
    st.rotation_euler.y = R.uniform(-0.06, 0.06)
    stones_above.append(st)
for k in range(24):                          # iron railing along the back of the cemetery
    s3d.box("Rail", (0.03, 0.03, 1.1), (CX - 3.7 + k * 0.32, 3.4, 0.58), IRON, bevel=0)
s3d.box("RailTop", (7.6, 0.05, 0.05), (CX, 3.4, 1.05), IRON, bevel=0)

coffins, grave_bones = [], []
for row, z in enumerate((-0.75, -1.35, -1.95, -2.55, -3.15)):
    for k, x in enumerate(np.linspace(CX - 2.7, CX + 2.4, 3)):
        c = s3d.box("Coffin", (1.85, 0.62, 0.48), (x + R.uniform(-0.25, 0.25) + (0.4 if row % 2 else 0), 0.31, z + R.uniform(-0.05, 0.05)), WOOD, bevel=0.05)
        c.rotation_euler.y = R.uniform(-0.08, 0.08)
        coffins.append((row, c))
loose = bone_scatter(60, CX - 3.6, CX + 3.4, -3.4, -0.6, y0=0.06, y1=0.2, seed=3)
hide_stones_in(CX - 4, CX + 4, -3.6, -0.4, 1)

# ---------------------------------------------------------------- the old quarry (centre) + bone heap
QX0, QX1, QZ0, QZ1 = -8.6, 2.6, -9.3, -6.8
void("Quarry", QX0, QX1, QZ0, QZ1)
hide_stones_in(QX0, QX1, QZ0, QZ1, 1)
pillar = s3d.box("Pillar", (0.9, 0.9, QZ1 - QZ0), (-0.6, 2.2, (QZ0 + QZ1) / 2), s3d.tex("stacked_stone_wall", tile=0.9, tint=(1.0, 0.92, 0.8), fallback=(0.7, 0.64, 0.55), name="Masonry"), bevel=0.03)
pile = heap("Heap", -3.6, QZ0, 5.6, 1.5, 420, seed=5)
lamp((-6.5, 1.2, QZ1 - 0.35), 1, energy=40)
lamp((0.8, 1.2, QZ1 - 0.35), 1, energy=40)

# ---------------------------------------------------------------- beat timing
f_bones = W(B, 0, "кістки")
f_mil = W(B, 0, "мільйонів")
f_cem = W(B, 1, "кладовища")
f_over = W(B, 1, "переповнилися")
f_rem = W(B, 2, "останки")
f_moved = W(B, 2, "перенесли")
f_quarry = W(B, 2, "каменоломні")
f_now = W(B, 3, "тепер")
f_km = W(B, 3, "кілометри")
f_tun = W(B, 3, "тунелів")
f_walls = W(B, 4, "стіни")
f_skulls = W(B, 4, "черепами")

# 0 — hook: the heap is already down there; the count tag
s3d.marker("thud", f_bones, prompt="deep low cinematic boom with a faint rattle of dry bones, short", gain=-2)
s3d.tag("6 000 000+", loc=(-3.6, -0.15, QZ0 + 2.2), frame=f_mil, hold=55, size=0.42)

# 1 — the cemetery fills up: coffin rows stack downwards, loose bones, then it bursts
for row, c in coffins:
    s3d.pop_in(c, f_cem - 14 + row * 5 + R.randint(0, 3), dur=8, sfx="wood" if row % 2 == 0 and c == coffins[row * 3][1] else None)
for o in loose:
    s3d.pop_in(o, f_over - 6, dur=10, sfx=None)
s3d.marker("crack", f_over, prompt="old earth heaving and cracking, gravestones grinding and tilting, short")
for i, st in enumerate(stones_above):
    s3d._key(st, f_over, rot=True, loc=True)
    st.rotation_euler.y += R.choice((-1, 1)) * R.uniform(0.18, 0.32)
    st.location.z += 0.12
    s3d._key(st, f_over + 8, rot=True, loc=True)
    s3d._ease(st, "BACK", "EASE_OUT")
bulge = s3d.box("Bulge", (6.8, 3.2, 0.5), (CX, 1.6, s3d.TOP - 0.25), s3d.tex("brown_mud_02", tile=1.0, fallback=s3d.PAL["topsoil"], name="Bulge"), bevel=0.2)
s3d.origin_to_base(bulge)
s3d.grow(bulge, f_over, dur=10, sfx=None)
for _, c in coffins:
    s3d.shake(c, f_over + 2, dur=10, amp=0.04, sfx=None)

# 2 — shaft down to the quarry, the remains go down it, the cemetery empties, the heap grows
SHX = -7.7
shaft = s3d.dig(g, x=SHX, width=1.3, depth=7.1, start=f_rem - 4, end=f_moved + 4, back=1.6, name="Shaft", mound=False)
hide_stones_in(SHX - 0.8, SHX + 0.8, -7.2, 0.2, f_rem)
s3d.hide_at(bulge, f_rem - 4)
falls = []
fr = random.Random(9)
f0, f1 = f_moved, f_quarry + 26
for k in range(26):
    kit = SKULL if k % 3 == 0 else FEMUR
    o = tile(kit, (BONE, DARK), [xf((0, 0, 0), rz=fr.uniform(0, 6.28), rx=fr.uniform(0, 6.28))], "Falling")
    st = f0 + int((f1 - f0) * k / 26)
    o.location = (SHX + fr.uniform(-0.35, 0.35), 0.6 + fr.uniform(0, 0.5), 0.4)
    s3d._key(o, st, loc=True, rot=True)
    o.location.z = QZ0 + 0.6 + fr.uniform(0, 0.5)
    o.location.x += fr.uniform(0.2, 1.4)
    o.rotation_euler.x += fr.uniform(4, 9)
    s3d._key(o, st + 16, loc=True, rot=True)
    for fc in s3d.fcurves(o):
        for kp in fc.keyframe_points:
            kp.interpolation, kp.easing = ("QUAD", "EASE_IN")
    s3d._hide_before(o, st)
    s3d.shrink_out(o, st + 22, dur=6)
    falls.append(o)
for i in range(5):
    s3d.marker("crunch", f0 + 18 + i * int((f1 - f0) / 5), prompt="pile of dry old bones tumbling down a stone shaft and clattering, short")
for i, (_, c) in enumerate(coffins):
    s3d.shrink_out(c, f_moved + i * 2, dur=8)
for o in loose:
    s3d.shrink_out(o, f_quarry, dur=10)
pile.scale = (0.8, 1.0, 0.5)
s3d._key(pile, 1, scale=True)
s3d._key(pile, f_moved, scale=True)
pile.scale = (1.0, 1.0, 1.0)
s3d._key(pile, f1 + 10, scale=True)
s3d.tag("каменоломня", loc=(-3.0, -0.15, QZ1 - 0.35), frame=f_quarry, hold=60, size=0.3)

# 3 — kilometres of tunnels: the quarry galleries race out left and right on two levels, lamps flick on
tunnels = [  # x0, x1, z0, z1, grows from x, start frame
    (QX1 - 0.2, WIDTH / 2 + 0.2, -9.1, -7.25, QX1 - 0.2, f_km - 6),
    (-WIDTH / 2 - 0.2, QX0 + 0.2, -9.1, -7.25, QX0 + 0.2, f_km - 2),
    (2.2, WIDTH / 2 + 0.2, -5.35, -3.45, 2.2, f_km + 6),
    (-WIDTH / 2 - 0.2, -10.0, -5.35, -3.45, -10.0, f_tun),
    (-10.0, 2.2, -5.35, -3.45, 2.2, f_tun + 4),
]
for i, (x0, x1, z0, z1, fx, fs) in enumerate(tunnels):
    c = void(f"Tunnel{i}", x0, x1, z0, z1)
    grow_void(c, fs, 24, fx)
    hide_stones_in(x0, x1, z0, z1, fs + 4)
    s3d.marker("whoosh", fs, prompt="deep stone grinding rumble rushing through an underground tunnel, short", gain=-3)
    span = x1 - x0
    for k, x in enumerate(np.arange(x0 + 1.5, x1 - 0.5, 4.5)):
        t = abs(x - fx) / max(1, span)
        lamp((float(x), 1.2, z1 - 0.3), fs + 4 + int(20 * t), energy=35)
for x, z0, z1 in ((4.6, -7.3, -5.3), (-12.5, -7.3, -5.3)):   # stair shafts linking the two levels
    c = void(f"Link{x}", x - 0.6, x + 0.6, z0 - 0.05, z1 + 0.05, back=2.2)
    s3d._key(c, f_tun + 6, scale=True)
    c.scale = (1, 1, 0.001)
    s3d._key(c, 1, scale=True)
    c.scale = (1, 1, 1)
    hide_stones_in(x - 0.6, x + 0.6, z0, z1, f_tun + 6)
s3d.tag("тунелі", loc=(9.0, -0.15, -2.95), frame=f_tun + 10, hold=50, size=0.3)

# 4 — the walls get lined with skulls, section by section from the camera's close-up outwards
walls = []
for (x0, x1, z0, z1, *_), base in zip(tunnels, (0, 4, 8, 12, 16)):
    lo, hi = max(x0, -16.0), min(x1, 16.0)
    if hi - lo < 1:
        continue
    for seg in skull_wall(f"Wall{base}", lo, hi, z0 + 0.02, z1 - 0.12):
        walls.append(seg)
FOCUS = (6.0, -4.4)
walls.sort(key=lambda s: abs(s.location.x - FOCUS[0]) + 3 * abs(s.location.z - FOCUS[1]))
for k, seg in enumerate(walls):
    s3d.grow(seg, f_walls - 8 + int(k * 0.9), dur=10, sfx=None)
s3d.marker("crunch", f_walls - 6, prompt="many dry skulls and bones being stacked against a stone wall, hollow clatter, short", gain=-1)
s3d.marker("thud", f_skulls + 6, prompt="low ominous cinematic hit with a cold echo in a stone crypt", gain=-2)

# ---------------------------------------------------------------- camera
cam = s3d.camera_cutaway(target=(0.0, 0, 5.0), dist=17, lens=32)
cam.data.clip_end = 1000
s3d.cam_move(cam, f_bones + 26, target=(-3.0, 0, -7.0), dist=10.5, dur=40)
s3d.cam_drift(cam, f_bones + 26, f_cem - 26, amount=0.6)
s3d.cam_move(cam, f_cem + 6, target=(-8.6, 0, -1.4), dist=10.5, dur=26)
s3d.cam_move(cam, f_moved + 18, target=(-5.6, 0, -4.6), dist=13.5, dur=30)
s3d.cam_move(cam, f_tun + 12, target=(0.5, 0, -5.0), dist=21, dur=34)
s3d.cam_move(cam, f_skulls + 4, target=(FOCUS[0], 0, FOCUS[1] + 0.2), dist=4.2, height=0.15, dur=36)
s3d.cam_drift(cam, f_skulls + 4, END, amount=0.5)

# ---------------------------------------------------------------- output
if MODE == "preview":
    os.makedirs(os.path.join(WORK, "preview"), exist_ok=True)
    keys = [10, f_bones + 30, f_mil + 8, f_over + 10, f_moved + 30, f_quarry + 10, f_tun + 16, f_walls + 10, END - 5]
    s3d.qa_gate(abort=False)
    for f in keys:
        s3d.preview_still(os.path.join(WORK, "preview", f"f{f:04d}.png"), frame=f, scale=30, samples=8)
elif MODE.startswith("still:"):
    f = int(MODE.split(":")[1])
    s3d.preview_still(os.path.join(WORK, "preview", f"s{f:04d}.png"), frame=f, scale=50, samples=16)
else:
    s3d.render_mp4(os.path.join(WORK, "render.mp4"), scale=100 if MODE == "full" else 50)
