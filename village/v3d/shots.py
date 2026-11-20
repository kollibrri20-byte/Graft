"""Шоти 3D-версії. Кожна функція будує сцену й анімацію для свого кадру сценарію.

Запуск одного шоту: python3 render.py 4
"""
import math
import random

import bpy
from mathutils import Vector

import lib
from lib import (M, beam, box, cam_move, camera, church, cone, cyl, distance_fog, flicker, forest, hatchback,
                 headlights, hut, lantern_pole, link, look_at, mat, moon_disc, point_light, road_strip, setp,
                 sphere, spot_light, sun, terrain, trunk_row, world)
from actors import Actor, scan_head
from assets import Hanna, Human, TM, hdri_world


def andriy(name="andr"):
    return Human("marvin", name, 1.8, tint=(0.55, 0.72, 0.38))


def villager(i, name):
    tints = [(0.8, 0.62, 0.45), (0.55, 0.55, 0.6), (0.7, 0.68, 0.6), (0.6, 0.45, 0.35), (0.5, 0.6, 0.5)]
    return Human("marvin", name, 1.72 + 0.04 * (i % 3), tint=tints[i % len(tints)])

SHOTS = {}

# яскравіший нічний «look»
NIGHT_SKY = (0.05, 0.07, 0.12)
NIGHT_FOG = (0.09, 0.12, 0.18)
MOON_K = 2.2


def shot(*nums):
    def deco(fn):
        for n in nums:
            SHOTS[n] = fn
        return fn
    return deco


def night(fog_d=0.035, sky=NIGHT_SKY, fog=NIGHT_FOG, moon=MOON_K, moon_dir=(-0.4, 1.0, 0.55)):
    hdri_world("moonlit_golf", 0.45, tint=(0.65, 0.78, 1.0))
    sun((math.radians(58), 0, math.radians(200)), moon, color=(0.55, 0.68, 1.0))
    return fog_d, fog


def finish_fog(cfg):
    distance_fog(*cfg)


# --------------------------------------------------------------------------
# Набори
# --------------------------------------------------------------------------
def set_forest_road(mats, seed=1, road_w=4.5, curve=0.0, density=1.0):
    terrain(500, 2.0, 0.5, mats["ground"], subdiv=6, seed=seed, loc=(0, 0, -1.25))
    pts = [(curve * math.sin(y / 30.0) * 8, y) for y in range(-60, 260, 4)]
    road_strip(pts, road_w, mats["road"], z=0.25)

    def avoid(x, y):
        rx = curve * math.sin(y / 30.0) * 8
        return abs(x - rx) < road_w / 2 + 9
    forest(mats, (-90, 90, -60, 260), int(900 * density), 16, 30, avoid=avoid, seed=seed)
    # ближні стовбури з корою
    bark = TM()["mosswood"]
    r = random.Random(seed + 50)
    for i in range(int(70 * density)):
        y = r.uniform(-30, 160)
        rx = curve * math.sin(y / 30.0) * 8
        side = r.choice((-1, 1))
        x = rx + side * r.uniform(road_w / 2 + 1.2, road_w / 2 + 9)
        rr = r.uniform(0.18, 0.4)
        o = cyl((x, y, 9), rr, 20, bark, verts=14)
        o.rotation_euler = (r.uniform(-0.04, 0.04), r.uniform(-0.04, 0.04), r.uniform(0, 6))
        # нижні сухі гілки
        for k in range(3):
            z = r.uniform(2.5, 6)
            a = r.uniform(0, 6.28)
            br = cyl((x + math.cos(a) * 0.6, y + math.sin(a) * 0.6, z), 0.03, 1.4, mats["bark"], verts=5,
                     rot=(math.radians(70), 0, a + math.pi / 2))
        # крона високо — темні конуси
        cone((x, y, 16), rr * 9, 0, 9, mats["pine"], verts=10)
        cone((x, y, 21), rr * 6, 0, 7, mats["pine"], verts=10)
    return pts


def set_village(mats, seed=2, doors=False, n=5, lit=True, church_bg=True, lanterns=True, sh_row=1):
    terrain(400, 1.0, 0.6, mats["ground"], subdiv=6, seed=seed, loc=(0, 0, -0.62))
    road_strip([(0, -30), (0, 20), (0.6, 60), (1.2, 120)], 6.0, mats["road"], z=0.22)
    for i in range(n):
        y = 6 + i * 11
        hut(mats, (-10.0, y, 0), math.radians(90), lit=lit, door_open=doors and i < 3, shutters=(i == sh_row))
        hut(mats, (10.0, y + 5, 0), math.radians(-90), lit=lit, door_open=doors and i < 3)
        if lanterns:
            lantern_pole(mats, (-4.2 if i % 2 else 4.0, y + 2, 0), shadow=(i == 0))
    if church_bg:
        church(mats, (6, 75, 0), 1.0)
    forest(mats, (-120, 120, 85, 220), 260, 14, 26, seed=seed + 7)
    forest(mats, (-120, -30, -40, 85), 120, 14, 26, seed=seed + 8)
    forest(mats, (30, 120, -40, 85), 120, 14, 26, seed=seed + 9)


def set_valley(mats, time="night", lights=True, seed=3):
    terrain(1600, 140, 0.35, mats["grass"], subdiv=8, seed=seed)
    forest(mats, (-500, 500, -200, 700), 1600, 18, 34, seed=seed, avoid=lambda x, y: abs(x) < 40 and 120 < y < 220)
    if lights:
        r = random.Random(4)
        for _ in range(14):
            x, y = r.uniform(-25, 25), r.uniform(140, 200)
            sphere((x, y, 2.0), 0.9, mats["win"])
            point_light((x, y, 3), 4000, shadow=False)


def car_interior(mats, outside="night", phone_mode=None):
    """Салон: панель, кермо, лобове скло. Камера дивиться вперед з місця водія."""
    dash = box((0, 0.9, 0.85), (1.8, 0.7, 0.35), mats["boots"], bevel=0.08)
    box((0, 0.55, 1.0), (1.8, 0.2, 0.06), mats["boots"])
    dg = mat("dash_dim", (0.3, 0.5, 1.0), 0.4, emit=(0.35, 0.55, 1.0), strength=1.2)
    box((-0.38, 0.62, 0.98), (0.42, 0.05, 0.16), dg, rot=(math.radians(-60), 0, 0))
    bpy.context.scene.view_settings.exposure = 0.4
    bpy.ops.mesh.primitive_torus_add(major_radius=0.19, minor_radius=0.022, location=(-0.38, 0.45, 0.92),
                                     rotation=(math.radians(65), 0, 0))
    w = bpy.context.object
    w.data.materials.append(mats["boots"])
    # каркас вікна
    for sx in (-0.92, 0.92):
        box((sx, 1.2, 1.45), (0.08, 0.08, 0.9), mats["boots"], rot=(math.radians(-25), 0, 0))
    box((0, 1.0, 1.85), (1.9, 0.6, 0.06), mats["boots"])
    p = None
    if phone_mode:
        p = phone(mats, (0.15, 0.62, 1.12), phone_mode)
    return p


def phone(mats, loc, mode="nomap", k=1.0):
    x, y, z = loc
    body = box((x, y, z), (0.08, 0.012, 0.16), mats["boots"], bevel=0.006)
    col = {"nomap": (0.5, 0.55, 0.62), "nosignal": (0.25, 0.4, 0.8), "full": (1.0, 0.75, 0.5),
           "forest": (0.25, 0.6, 0.3), "photo": (0.55, 0.55, 0.55)}[mode]
    scr = mat("scr_" + mode, col, 0.3, noise=60 if mode in ("nomap", "photo", "forest") else None, bump=0,
              emit=col, strength=0.9 * k, noise_dark=0.3)
    s = box((x, y - 0.0075, z), (0.07, 0.002, 0.145), scr)
    bars = 4 if mode == "full" else (1 if mode in ("photo", "forest") else 0)
    on = mat("bar_on", (1, 1, 1), 0.3, emit=(1, 1, 1), strength=6)
    off = mat("bar_off", (0.15, 0.17, 0.2), 0.5)
    for i in range(4):
        h = 0.004 + i * 0.003
        box((x + 0.012 + i * 0.006, y - 0.009, z + 0.06 + h / 2), (0.004, 0.001, h), on if i < bars else off)
    point_light((x, y - 0.15, z + 0.05), 2.5 * k, col, shadow=False)
    return body, s


def sign(mats, loc, yaw=0.0, s=1.0):
    x, y, z = loc
    cyl((x, y, z + 1.0 * s), 0.07 * s, 2.0 * s, mats["wood"], verts=8)
    plank = mat("plank", (0.33, 0.25, 0.17), 0.95, noise=14, bump=0.6, noise_dark=0.4)
    b = box((x + 0.45 * s, y, z + 1.85 * s), (1.2 * s, 0.06 * s, 0.32 * s), plank, rot=(0, math.radians(-4), yaw), bevel=0.01)
    moss = mat("moss", (0.12, 0.2, 0.05), 1.0, noise=40, bump=0.8)
    box((x + 0.05 * s, y - 0.035 * s, z + 1.75 * s), (0.25 * s, 0.01, 0.1 * s), moss)
    return b


# --------------------------------------------------------------------------
# Хук
# --------------------------------------------------------------------------
@shot(1)
def s001(mats, F):
    cfg = night(0.0012, sky=(0.03, 0.045, 0.085), fog=(0.05, 0.065, 0.1))
    set_valley(mats)
    cam = camera(lens=35)
    cam_move(cam, 1, F, (0, -60, 190), (0, -35, 170), (0, 170, 0), (0, 172, 0))
    finish_fog(cfg)


@shot(2)
def s002(mats, F):
    cfg = night(0.05)
    car_interior(mats, phone_mode="nomap")
    set_forest_road(mats, density=0.4)
    cam = camera(lens=40, dof=0.6, fstop=2.0)
    cam_move(cam, 1, F, (0.0, 0.05, 1.35), (0.08, 0.3, 1.25), (0.15, 0.62, 1.12), (0.15, 0.62, 1.12))
    finish_fog(cfg)


@shot(3)
def s003(mats, F):
    cfg = night(0.06)
    set_forest_road(mats, seed=3)
    hatchback(mats, (0, -6, 0.25), 0)
    headlights((0, -6, 0.25), 0, 1.2, 35)
    cam = camera(lens=24)
    cam_move(cam, 1, F, (1.8, -2.0, 0.5), (1.6, 1.5, 0.45), (0, 25, 2.5), (0, 30, 2.4))
    finish_fog(cfg)


@shot(4)
def s004(mats, F):
    cfg = night(0.07)
    set_forest_road(mats, seed=4, road_w=1.6, curve=0.2)
    a = andriy()
    a.path([(0.0, 0, 0.25), (0.15, 6, 0.25)], 1, F)
    a.play("Walk", 1, F)
    hl = spot_light((0.35, 0.6, 1.25), (0, 0, 0), 600, size_deg=30)
    hl.parent = a.root
    hl.rotation_euler = (math.radians(-80), 0, 0)
    bm = beam((0.35, 0.6, 1.2), (0.3, 14, 0.2), 2.2, k=0.9)
    bm.parent = a.root
    point_light((0.5, 40, 6), 6000, (0.6, 0.72, 1.0), radius=4, shadow=False)  # світло туману попереду
    cam = camera(lens=35)
    cam_move(cam, 1, F, (0.4, -3.2, 1.6), (0.5, 3.0, 1.65), (0.1, 6, 1.3), (0.2, 12, 1.4))
    finish_fog(cfg)


@shot(5)
def s005(mats, F):
    cfg = night(0.06)
    set_forest_road(mats, seed=5, road_w=1.6, density=0.9)
    a = andriy()
    a.path([(0, 0, 0.25), (0.1, 3.0, 0.25)], 1, F)
    a.play("walk", 1, F, speed=0.75)
    for f in (1, F):
        bpy.context.scene.frame_set(f)
    hl = spot_light((0.3, 0.6, 1.2), (0, 0, 0), 900, size_deg=24)
    hl.parent = a.root
    hl.location = (Vector((0.28, -0.35, 1.2)) - Vector((0, 0, a.zoff * a.k))) / a.k
    hl.rotation_euler = (math.radians(-95), 0, 0)
    bm = beam((0.3, 0.4, 1.2), (1.0, 12, 0.6), 1.0, k=0.55)
    for f in range(1, F + 1):
        bm.location.y = 0.4 + 6.5 + 3.0 * f / F
        bm.keyframe_insert("location", frame=f)
    cam = camera(lens=40)
    cam_move(cam, 1, F, (1.6, 6.5, 1.4), (1.5, 6.8, 1.4), (0.1, 1.5, 1.2), (0.1, 3.5, 1.2))
    finish_fog(cfg)

@shot(6, 7)
def s006(mats, F, n=6):
    cfg = night(0.06)
    set_forest_road(mats, seed=6, road_w=1.6)
    sign(mats, (1.6, 6, 0.25), 0)
    hl = spot_light((0.2, 0, 1.4), (0, 0, 0), 1500, size_deg=18, blend=0.3)
    look_at(hl, (2.1, 6, 2.1))
    beam((0.2, 0, 1.4), (2.0, 6, 2.0), 0.9, k=0.7)
    if n == 6:
        cam = camera(lens=28)
        cam_move(cam, 1, F, (0.8, 2.2, 0.6), (1.0, 3.2, 0.7), (2.0, 6, 2.2), (2.0, 6, 2.1))
    else:
        cam = camera(lens=60, dof=1.3, fstop=2.0)
        cam_move(cam, 1, F, (2.0, 4.75, 2.1), (2.25, 4.8, 2.12), (2.0, 6, 2.1), (2.3, 6, 2.1))
    finish_fog(cfg)


@shot(8)
def s008(mats, F):
    cfg = night(0.045)
    set_village(mats, seed=8)
    sign(mats, (-2.6, -6, 0.25), 0, 1.0)
    cam = camera(lens=30)
    cam_move(cam, 1, F, (-3.6, -9.5, 1.7), (-2.8, -7.6, 1.7), (0, 25, 1.8), (0.3, 25, 1.8))
    finish_fog(cfg)


@shot(9)
def s009(mats, F):
    cfg = night(0.045)
    set_village(mats, seed=9, doors=True)
    for i, (x, y, k) in enumerate([(-6.6, 6, "woman"), (6.6, 11, "man"), (-6.6, 17, "old"), (6.6, 22, "woman")]):
        p = villager(i, f"v{i}")
        yaw = 90 if x < 0 else -90
        side = -1 if x < 0 else 1
        p.place((x + side * 0.8, y, 0.2), yaw + 180)
        p.path([(x + side * 1.0, y, 0.2), (x - side * 0.6, y, 0.2)], 1 + i * 4, min(F, 1 + i * 4 + 18))
        p.play("Walk", 1 + i * 4, min(F, 1 + i * 4 + 18), speed=0.6)
        p.play("idle", min(F, 1 + i * 4 + 18) + 1, F + 1)
    cam = camera(lens=30)
    cam_move(cam, 1, F, (0.3, -6, 1.6), (0.3, -2.5, 1.6), (0, 18, 1.4), (0, 20, 1.4))
    finish_fog(cfg)


@shot(10, 89)
def s010(mats, F, n=10):
    cfg = night(0.05)
    set_village(mats, seed=10)
    Hanna((0.0, 14.2, 0.2), 0)
    for i, (x, y) in enumerate(((-1.3, 15.2), (1.4, 15.6))):
        p = villager(i * 2 + 1, f"v{i}")
        p.place((x, y, 0.2), 0)
        p.play("idle", 1, F + 1, offset=i * 17)
    point_light((0, 11.5, 2.4), 260, radius=0.3)
    cam = camera(lens=42, dof=4.0)
    cam_move(cam, 1, F, (0, 10.2, 1.5), (0, 11.0, 1.5), (0, 14, 1.35), (0, 14, 1.4))
    finish_fog(cfg)


@shot(11)
def s011(mats, F):
    cfg = night(0.045)
    set_village(mats, seed=11)
    a = andriy()
    a.place((0, 10, 0.2), 0)
    a.play("idle", 1, F + 1)
    r = random.Random(11)
    for i in range(7):
        ang = math.radians(-150 + i * 50)
        x, y = math.sin(ang) * 5, 10 + math.cos(ang) * 5
        p = villager(i, f"v{i}")
        p.place((x, y, 0.2), math.degrees(math.atan2(-(0 - x), (10 - y))))
        p.play("idle", 1, F + 1, offset=r.uniform(0, 20))
    cam = camera(lens=26)
    cam_move(cam, 1, F, (3.2, 3.8, 1.3), (2.6, 4.6, 1.35), (0, 10.5, 1.3), (0, 10.5, 1.4), roll0=-12, roll1=-15)
    finish_fog(cfg)


@shot(12)
def s012(mats, F):
    cfg = night(0.05)
    hut(mats, (0, 2.5, 0), 0, lit=True, door_open=True, lights=False)
    point_light((0, 0.2, 1.5), 22, radius=0.4)
    h = Hanna((0, -0.05, 0.0), 0)
    c = cyl((0.32, -0.45, 1.05), 0.02, 0.16, mats["candle_wax"], verts=10)
    sphere((0.32, -0.45, 1.16), 0.015, mats["flame"], scale=(1, 1, 2))
    cl = point_light((0.32, -0.5, 1.2), 25, radius=0.02)
    flicker(cl, 1, F, 25, 0.3, seed=12)
    cam = camera(lens=55, dof=2.0, fstop=2.0)
    cam_move(cam, 1, F, (0.1, -2.6, 1.45), (0.05, -2.2, 1.45), (0, 0, 1.4), (0, 0, 1.42))
    finish_fog(cfg)


@shot(13)
def s013(mats, F):
    world(sky=(0.0, 0.0, 0.0), fog=0.0)
    a = andriy()
    a.place((0, 0, 0), 0)
    a.play("idle", 1, F + 1)
    sc = bpy.context.scene
    sc.frame_set(F // 2)
    h = a.bone_world("Head") + Vector((0, 0, 0.1))
    point_light(h + Vector((0.7, -0.6, 0.1)), 20, (1.0, 0.6, 0.25), radius=0.2)
    point_light(h + Vector((-0.7, -0.5, 0.0)), 12, (0.35, 0.5, 1.0), radius=0.25)
    cam = camera(lens=100, dof=0.4, fstop=2.8)
    fwd = Vector((0, -1, 0))
    cam_move(cam, 1, F, h + Vector((0, -0.55, 0.0)), h + Vector((0, -0.42, 0.0)), h, h)

@shot(14)
def s014(mats, F):
    cfg = night(0.05)
    set_village(mats, seed=14)
    a = andriy()
    a.place((0, 12, 0.2), 0)
    a.play("idle", 1, F + 1)
    cam = camera(lens=28)
    cam_move(cam, 1, F, (0, 2, 12), (0, 3, 14), (0, 13, 0), (0, 13.5, 0))
    finish_fog(cfg)


# --------------------------------------------------------------------------
# Розділ 1. Дорога
# --------------------------------------------------------------------------
@shot(15)
def s015(mats, F):
    world(sky=(0.25, 0.27, 0.3), fog=0.0)
    sun((math.radians(78), 0, math.radians(250)), 1.2, color=(1.0, 0.75, 0.55))
    terrain(1600, 150, 0.35, mats["grass"], subdiv=8, seed=15)
    pts = [(math.sin(t / 40.0) * 60, t) for t in range(-200, 600, 6)]
    road_strip([(x, y) for x, y in pts], 6, mats["road"], z=2.0)
    forest(mats, (-500, 500, -300, 700), 1500, 18, 34, seed=15,
           avoid=lambda x, y: abs(x - math.sin(y / 40.0) * 60) < 8)
    cam = camera(lens=30)
    cam_move(cam, 1, F, (-60, -260, 230), (-20, -200, 210), (0, 150, 0), (10, 170, 0))
    distance_fog(0.0009, (0.28, 0.29, 0.32))


def head_closeup(mats, F, light, back, cam_off0, cam_off1, lens=60, look=(0, 0, 0)):
    a = andriy()
    a.place((0, 0, 0), 0)
    a.play("idle", 1, F + 1, speed=0.6)
    bpy.context.scene.frame_set(F // 2)
    h = a.bone_world("Head") + Vector((0, 0, 0.09))
    cam = camera(lens=lens, dof=(Vector(cam_off0).length), fstop=2.2)
    cam_move(cam, 1, F, h + Vector(cam_off0), h + Vector(cam_off1), h + Vector(look), h + Vector(look))
    return a, h


def driver_profile_old(mats, F, sunset=True):
    world(sky=(0.0, 0.0, 0.0), fog=0.0)
    head, mesh = scan_head((0, 0, 0), (0, 0, math.radians(90)), 0.25)
    bpy.context.view_layer.update()
    bb = [mesh.matrix_world @ Vector(v) for v in mesh.bound_box]
    zmin, zmax = min(v.z for v in bb), max(v.z for v in bb)
    # плечі в куртці
    sphere((0, 0, zmin - 0.14), 0.2, mats["jacket"], scale=(1.0, 1.6, 0.6))
    hair = sphere((-0.01, 0, zmax - 0.07), 0.11, mats["hair"], scale=(1.1, 1.0, 0.55))
    return head, mesh, zmin, zmax


@shot(16)
def s016(mats, F):
    world(sky=(0.0, 0.0, 0.0), fog=0.0)
    a, h = head_closeup(mats, F, None, None, (-0.85, -0.05, 0.0), (-0.8, 0.05, 0.0), lens=55)
    sl = point_light(h + Vector((0.9, -0.3, 0.2)), 90, (1.0, 0.5, 0.18), radius=0.4)
    flicker(sl, 1, F, 90, 0.7, seed=16, speed=2.2)
    point_light(h + Vector((-0.6, -0.8, 0.3)), 6, (0.4, 0.5, 0.8), radius=0.4)
    box(h + Vector((0.6, 0, 0.45)), (0.06, 1.6, 0.06), mats["boots"])
    box(h + Vector((0.6, 0.6, 0)), (0.06, 0.06, 1.2), mats["boots"])

@shot(17)
def s017(mats, F):
    world(sky=(0.6, 0.42, 0.25), strength=0.6, fog=0.0)
    a, h = head_closeup(mats, F, None, None, (0.55, -0.45, 0.02), (0.5, -0.4, 0.03), lens=60, look=(0, -0.08, 0))
    # плівкова камера біля ока
    box(h + Vector((0.035, -0.13, 0.0)), (0.15, 0.07, 0.095), mats["metal"], bevel=0.008)
    cyl(h + Vector((0.05, -0.2, -0.005)), 0.034, 0.08, mats["boots"], rot=(math.radians(90), 0, 0))
    point_light(h + Vector((0.0, 1.0, 0.5)), 220, (1.0, 0.7, 0.35), radius=0.6)
    point_light(h + Vector((0.8, -0.8, 0.2)), 25, (1.0, 0.8, 0.6), radius=0.5)

@shot(18)
def s018(mats, F):
    world(sky=(0.5, 0.4, 0.3), fog=0.0)
    sun((math.radians(80), 0, math.radians(260)), 2.5, color=(1.0, 0.7, 0.45))
    terrain(1200, 60, 0.35, mats["grass"], subdiv=8, seed=18)
    pts = [(math.sin(t / 25.0) * 18, t) for t in range(-150, 400, 3)]
    road_strip(pts, 5, mats["road"], z=0.6)
    forest(mats, (-300, 300, -150, 400), 1400, 16, 30, seed=18, avoid=lambda x, y: abs(x - math.sin(y / 25.0) * 18) < 6)
    car = hatchback(mats, (0, 0, 0.6), 0, lights=False, tail=False)
    root = bpy.data.objects.new("carroot", None)
    link(root)
    for p in car:
        p.parent = root
    for f in range(1, F + 1):
        y = -20 + f * 0.55
        x = math.sin(y / 25.0) * 18
        dx = math.cos(y / 25.0) * 18 / 25.0
        root.location = (x, y, 0.0)
        root.rotation_euler = (0, 0, -math.atan(dx))
        root.keyframe_insert("location", frame=f)
        root.keyframe_insert("rotation_euler", frame=f)
    cam = camera(lens=35)
    cam_move(cam, 1, F, (25, -60, 45), (25, -40, 42), (0, -15, 0), (5, 5, 0))
    distance_fog(0.0012, (0.45, 0.36, 0.3))


@shot(19)
def s019(mats, F):
    world(sky=(0.0, 0.0, 0.0), fog=0.0)
    car_interior(mats, phone_mode="photo")
    point_light((-0.2, 0.0, 1.6), 8, (0.5, 0.6, 0.9), radius=0.4, shadow=False)
    cam = camera(lens=45, dof=0.5, fstop=2.0)
    cam_move(cam, 1, F, (-0.5, -0.05, 1.45), (-0.45, 0.05, 1.38), (0.15, 0.62, 1.12), (0.15, 0.62, 1.12))


@shot(20)
def s020(mats, F):
    world(sky=(0.15, 0.17, 0.2), fog=0.0)
    sun((math.radians(70), 0, math.radians(230)), 0.8, color=(1.0, 0.75, 0.55))
    set_forest_road(mats, seed=20, road_w=3.2, density=0.7)
    trunk_row(mats, [-3.2, 3.4], 6, 30, seed=20)
    car = hatchback(mats, (0, 0, 0.25), 0, lights=True, tail=True)
    root = bpy.data.objects.new("carroot", None)
    link(root)
    for p in car:
        p.parent = root
    hl = headlights((0, 0, 0.25), 0, 0.7, 20)
    for o in hl:
        o.parent = root
    for f in range(1, F + 1):
        root.location = (0, -18 + f * 0.6, 0)
        root.keyframe_insert("location", frame=f)
    cam = camera(lens=20)
    cam_move(cam, 1, F, (2.4, 4, 0.4), (2.3, 5, 0.45), (0, 0, 2.5), (0, 14, 3.0))
    distance_fog(0.03, (0.12, 0.13, 0.15))


@shot(21)
def s021(mats, F):
    world(sky=(0.06, 0.07, 0.1), fog=0.0)
    sun((math.radians(80), 0, math.radians(230)), 0.4, color=(0.8, 0.6, 0.6))
    set_forest_road(mats, seed=21, road_w=3.2, density=0.7, curve=0.6)
    car = hatchback(mats, (0, 60, 0.25), math.pi, lights=True, tail=False)
    for sx in (-0.6, 0.6):
        point_light((sx, 58, 1.0), 250, (1, 0.95, 0.85), radius=0.1, shadow=False)
    cam = camera(lens=60)
    cam_move(cam, 1, F, (0.5, 10, 22), (0.5, 14, 21), (0, 60, 1), (0, 60, 1))
    distance_fog(0.03, (0.07, 0.075, 0.1))


@shot(22)
def s022(mats, F):
    world(sky=(0, 0, 0), fog=0.0)
    point_light((-0.2, 0.0, 1.6), 5, (0.5, 0.6, 0.9), radius=0.4, shadow=False)
    car_interior(mats, phone_mode="nosignal")
    cam = camera(lens=55, dof=0.4, fstop=2.8)
    cam_move(cam, 1, F, (0.12, 0.2, 1.2), (0.13, 0.26, 1.18), (0.15, 0.62, 1.12), (0.15, 0.62, 1.12))


@shot(23)
def s023(mats, F):
    world(sky=(0.09, 0.1, 0.13), fog=0.0)
    sun((math.radians(70), 0, math.radians(230)), 0.5, color=(0.8, 0.7, 0.75))
    set_forest_road(mats, seed=23, road_w=3.6, density=0.7)
    hatchback(mats, (0, 0, 0.25), 0, lights=True, tail=True)
    hl = headlights((0, 0, 0.25), 0, 0.9, 20)
    for f in range(1, F + 1):
        u = f / F
        k = 1.0 if u < 0.35 else (0.0 if u > 0.75 else (0.5 + 0.5 * math.sin(f * 2.1)) * (0.75 - u) / 0.4)
        for o in hl:
            if o.type == "LIGHT":
                o.data.energy = 900 * 0.9 * k
                o.data.keyframe_insert("energy", frame=f)
            else:
                o.hide_render = k < 0.15
                o.keyframe_insert("hide_render", frame=f)
    cam = camera(lens=30)
    cam_move(cam, 1, F, (3.5, 6.5, 1.3), (3.3, 6.0, 1.3), (0, 0, 0.8), (0, 0, 0.8))
    distance_fog(0.03, (0.1, 0.11, 0.13))

@shot(24)
def s024(mats, F):
    world(sky=(0.08, 0.1, 0.13), fog=0.0)
    sun((math.radians(60), 0, math.radians(200)), 0.8, color=(0.6, 0.7, 0.9))
    set_forest_road(mats, seed=24, road_w=3.6)
    hatchback(mats, (1.2, 0, 0.25), 0, lights=False, tail=False)
    a = andriy()
    a.place((-0.6, -0.5, 0.25), 0)
    a.play("idle", 1, F + 1)
    cam = camera(lens=32)
    cam_move(cam, 1, F, (0.3, 4.5, 1.7), (0.2, 3.6, 1.65), (-0.4, -10, 1.2), (-0.4, -12, 1.2))
    distance_fog(0.035, (0.16, 0.18, 0.22))


@shot(25)
def s025(mats, F):
    world(sky=(0.05, 0.06, 0.08), fog=0.0)
    set_forest_road(mats, seed=25, road_w=1.6)
    hl = spot_light((0.25, 0, 1.35), (0, 0, 0), 1200, size_deg=24)
    look_at(hl, (0.0, 10, 1.0))
    beam((0.25, 0.1, 1.35), (0.0, 12, 0.8), 1.6, k=1.6)
    cam = camera(lens=24)
    cam_move(cam, 1, F, (0, -0.4, 1.6), (0.05, 1.2, 1.58), (0, 10, 1.3), (0.1, 12, 1.3), shake=0.008)
    distance_fog(0.06, (0.22, 0.24, 0.28))


@shot(26)
def s026(mats, F):
    cfg = night(0.05, moon=2.2)
    set_forest_road(mats, seed=26, road_w=1.2, curve=0.4)
    for i in range(4):
        beam((-20 + i * 9, 40, 40), (-12 + i * 9, 10 + i * 3, 0), 2.5, (0.6, 0.72, 1.0), 0.5)
    cam = camera(lens=28)
    cam_move(cam, 1, F, (0, -6, 6), (0, -3, 5.4), (0, 14, 0), (0, 16, 0))
    finish_fog(cfg)
