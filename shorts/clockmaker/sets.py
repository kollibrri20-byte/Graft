"""The four sets of the short, placed far apart in one scene:
TOWN (x≈0), SHOP interior (x≈100), ROOM (grandma, x≈200), VOID (black, x≈300)."""
from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

import lib
from lib import box, cyl, sphere, torus, empty, obj, mat, emit, light, text
import clocks

D = math.radians
R = {}  # registry of things the handler animates


# ------------------------------------------------------------------ world
def world():
    w = bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_WORLD":
            nt.nodes.remove(n)
    out = next(n for n in nt.nodes if n.type == "OUTPUT_WORLD")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    grad = nt.nodes.new("ShaderNodeValToRGB")
    grad.name = "skygrad"
    grad.color_ramp.elements[0].position = 0.0
    grad.color_ramp.elements[0].color = (0.035, 0.05, 0.10, 1)
    grad.color_ramp.elements[1].position = 0.5
    grad.color_ramp.elements[1].color = (0.004, 0.007, 0.02, 1)
    nt.links.new(sep.outputs["Z"], grad.inputs["Fac"])
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 260
    nt.links.new(tc.outputs["Generated"], vor.inputs["Vector"])
    st = nt.nodes.new("ShaderNodeMath"); st.operation = "LESS_THAN"; st.inputs[1].default_value = 0.035
    nt.links.new(vor.outputs["Distance"], st.inputs[0])
    sm = nt.nodes.new("ShaderNodeMath"); sm.operation = "MULTIPLY"; sm.name = "stars"; sm.inputs[1].default_value = 0.6
    nt.links.new(st.outputs[0], sm.inputs[0])
    add = nt.nodes.new("ShaderNodeMixRGB"); add.blend_type = "ADD"; add.inputs["Fac"].default_value = 1.0
    nt.links.new(grad.outputs["Color"], add.inputs[1])
    nt.links.new(sm.outputs[0], add.inputs[2])
    bg = nt.nodes.new("ShaderNodeBackground"); bg.name = "bg"
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(add.outputs[0], bg.inputs["Color"])
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    R["world"] = w


# ------------------------------------------------------------------ TOWN
PLASTER = [(0.52, 0.42, 0.32), (0.42, 0.36, 0.30), (0.34, 0.38, 0.40), (0.50, 0.40, 0.28), (0.40, 0.33, 0.38), (0.46, 0.44, 0.36)]


def _window_mat(name, lit):
    """Window glass: lit ones glow warm; every window also flares as the golden wave passes (value 'wave')."""
    m = mat(name, (0.05, 0.05, 0.06) if not lit else (0.9, 0.6, 0.3), 0.15)
    nt = m.node_tree
    b = lib._bsdf(m)
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    dist = nt.nodes.new("ShaderNodeVectorMath"); dist.operation = "DISTANCE"
    dist.inputs[1].default_value = (0.0, 26.0, 0.0)
    nt.links.new(oi.outputs["Location"], dist.inputs[0])
    wave = nt.nodes.new("ShaderNodeValue"); wave.name = "wave"; wave.outputs[0].default_value = -100.0
    sub = nt.nodes.new("ShaderNodeMath"); sub.operation = "SUBTRACT"
    nt.links.new(wave.outputs[0], sub.inputs[0]); nt.links.new(dist.outputs["Value"], sub.inputs[1])
    # bump around the wave front, then stays a bit brighter after it passed
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -1.0
    mr.inputs["From Max"].default_value = 0.0
    mr.inputs["To Min"].default_value = 0.0
    mr.inputs["To Max"].default_value = 1.0
    nt.links.new(sub.outputs[0], mr.inputs["Value"])
    mr2 = nt.nodes.new("ShaderNodeMapRange")
    mr2.inputs["From Min"].default_value = 0.0
    mr2.inputs["From Max"].default_value = 6.0
    mr2.inputs["To Min"].default_value = 1.0
    mr2.inputs["To Max"].default_value = 0.35
    nt.links.new(sub.outputs[0], mr2.inputs["Value"])
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
    nt.links.new(mr.outputs[0], mul.inputs[0]); nt.links.new(mr2.outputs[0], mul.inputs[1])
    base = nt.nodes.new("ShaderNodeValue"); base.name = "base"; base.outputs[0].default_value = 3.5 if lit else 0.0
    w8 = nt.nodes.new("ShaderNodeMath"); w8.operation = "MULTIPLY"; w8.inputs[1].default_value = 25.0
    nt.links.new(mul.outputs[0], w8.inputs[0])
    tot = nt.nodes.new("ShaderNodeMath"); tot.operation = "ADD"
    nt.links.new(base.outputs[0], tot.inputs[0]); nt.links.new(w8.outputs[0], tot.inputs[1])
    nt.links.new(tot.outputs[0], b.inputs["Emission Strength"])
    col = nt.nodes.new("ShaderNodeMixRGB")
    col.inputs[1].default_value = (1.0, 0.62, 0.28, 1)
    col.inputs[2].default_value = (1.0, 0.8, 0.35, 1)
    nt.links.new(mr.outputs[0], col.inputs["Fac"])
    nt.links.new(col.outputs[0], b.inputs["Emission Color"])
    return m


def house(x_face, side, yc, w, d, h, rng, M):
    """Row house; facade on the street plane x = x_face, side = +1 (right of street) / -1 (left)."""
    cx = x_face + side * d / 2
    pl = M["plaster"][rng.randrange(len(M["plaster"]))]
    box("house", (cx, yc, h / 2), (d, w, h), pl)
    roof = obj("roof", lib.m_prism(), (cx, yc, h - 0.02), M["roof"], scale=(d + 0.4, w + 0.35, w * 0.55))
    # timber bands and corner posts
    for z in [z for z in (2.9, 5.6, 8.3) if z < h - 0.4]:
        box("beam", (x_face - side * 0.06, yc, z), (0.12, w + 0.02, 0.16), M["timber"])
    for yy in (yc - w / 2 + 0.08, yc + w / 2 - 0.08):
        box("post", (x_face - side * 0.06, yy, h / 2), (0.12, 0.16, h), M["timber"])
    # windows
    floors = [z for z in (1.6, 4.25, 6.9, 9.5) if z < h - 1.0]
    cols = [yc - w * 0.25, yc + w * 0.25] if w > 3.6 else [yc]
    wins = []
    for fz in floors:
        for yy in cols:
            if fz < 2 and abs(yy - cols[0]) < 0.01 and len(cols) > 1:
                # door instead of the left ground-floor window
                box("door", (x_face - side * 0.03, yy, 1.05), (0.08, 1.0, 2.1), M["door"])
                continue
            lit = rng.random() < 0.45
            wo = box("win", (x_face - side * 0.035, yy, fz + 0.15), (0.05, 0.8, 1.15), M["win_lit" if lit else "win_dark"])
            wins.append(wo)
            box("sill", (x_face - side * 0.08, yy, fz - 0.47), (0.16, 0.95, 0.07), M["timber"])
            for sy in (-1, 1):
                box("shutter", (x_face - side * 0.06, yy + sy * 0.62, fz + 0.15), (0.05, 0.4, 1.2), M["shutter"])
            box("mull", (x_face - side * 0.065, yy, fz + 0.15), (0.03, 0.05, 1.15), M["timber"])
    # chimney
    if rng.random() < 0.6:
        box("chimney", (cx + side * rng.uniform(-0.5, 1.5), yc + rng.uniform(-w * 0.3, w * 0.3), h + w * 0.45), (0.5, 0.5, 1.4), M["brick"])
    return wins


def town():
    rng = random.Random(11)
    M = {
        "plaster": [lib.noise_mat(f"plaster{i}", c, tuple(x * 0.8 for x in c), scale=3, rough=0.9, bump=0.15) for i, c in enumerate(PLASTER)],
        "roof": lib.noise_mat("rooftiles", (0.22, 0.08, 0.06), (0.32, 0.13, 0.08), scale=9, rough=0.7, bump=0.4, kind="wave"),
        "timber": mat("timber", (0.10, 0.06, 0.04), 0.7),
        "shutter": mat("shutter", (0.12, 0.18, 0.14), 0.7),
        "door": mat("door", (0.16, 0.09, 0.05), 0.6),
        "brick": lib.noise_mat("brick", (0.30, 0.12, 0.08), (0.20, 0.08, 0.05), scale=12, rough=0.9, bump=0.2),
        "win_lit": _window_mat("win_lit", True),
        "win_dark": _window_mat("win_dark", False),
    }
    R["win_mats"] = [M["win_lit"], M["win_dark"]]
    cob = lib.cobble_mat("cobble", 0.33)
    box("street", (0, 20, -0.05), (30, 100, 0.1), cob)
    # houses on both sides, leaving a gap at y 10..14 on the right (the shop)
    wins = []
    for side in (1, -1):
        y = -14.0
        while y < 52:
            w = rng.uniform(4.2, 5.8)
            if side == 1 and y < 14 and y + w > 10:
                if y < 10:
                    w = 10 - y
                    if w < 2.5:
                        y = 14.0
                        continue
                else:
                    y = 14.0
                    continue
            h = rng.uniform(6.0, 9.5)
            wins += house(4.0 * side, side, y + w / 2, w, 7.0, h, rng, M)
            y += w
    R["town_windows"] = wins
    # back wall behind the shop gap + dirt patch (seen in the morning)
    box("backwall", (11.6, 12, 4.5), (0.4, 4.4, 9), M["plaster"][3])
    dirt = lib.noise_mat("dirt", (0.16, 0.11, 0.07), (0.30, 0.22, 0.14), scale=6, rough=0.95, bump=0.5)
    box("lot", (7.8, 12, 0.0), (7.5, 4.0, 0.04), dirt)
    for k in range(14):
        sphere("weed", (rng.uniform(5, 11), rng.uniform(10.3, 13.7), 0.02), (rng.uniform(0.05, 0.12),) * 2 + (rng.uniform(0.05, 0.15),),
               mat("weed", (0.12, 0.2, 0.05), 0.8))
    # the shop facade (hidden in the morning)
    shop_ext = empty("shop_ext", (0, 0, 0))
    R["shop_ext"] = shop_ext
    wood = lib.noise_mat("shopwood", (0.10, 0.05, 0.03), (0.20, 0.10, 0.05), scale=10, rough=0.55, bump=0.1, kind="wave")
    box("shopbody", (7.7, 12, 2.4), (7.2, 4.0, 4.8), wood, shop_ext)
    obj("shoproof", lib.m_prism(), (7.7, 12, 4.78), M["roof"], shop_ext, scale=(7.6, 4.4, 2.2))
    import os
    win_png = os.path.join(lib.TEX, "shopwindow.png")
    _shop_window_png(win_png)
    wm = lib.image_mat("shopwin", win_png, rough=0.2, emit_str=4.0)
    box("shopwin", (4.06, 11.5, 1.55), (0.04, 2.4, 1.8), wm, shop_ext)
    for z in (0.62, 2.48):
        box("shopframe", (4.0, 11.5, z), (0.12, 2.6, 0.12), M["timber"], shop_ext)
    for yy in (10.28, 12.72, 11.5):
        box("shopframe", (4.0, yy, 1.55), (0.12, 0.1, 1.95), M["timber"], shop_ext)
    box("shopdoor", (4.05, 13.4, 1.1), (0.08, 0.9, 2.2), M["door"], shop_ext)
    box("doorglow", (4.0, 13.4, 1.7), (0.02, 0.4, 0.5), lib.emit("doorglow", (1, 0.6, 0.25), 3), shop_ext)
    # hanging sign
    signm = mat("sign", (0.12, 0.07, 0.04), 0.5)
    gold = emit("signgold", (1.0, 0.7, 0.3), 2.5)
    box("signarm", (3.4, 12.8, 3.4), (1.3, 0.05, 0.05), M["timber"], shop_ext)
    box("signboard", (3.1, 12.8, 3.0), (0.06, 1.2, 0.6), signm, shop_ext)
    text("signtext", "ГОДИННИКИ", (3.06, 12.8, 3.0), 0.16, gold, shop_ext, rot=(D(90), 0, D(-90)))
    light("shopglow", "AREA", (3.2, 11.5, 1.6), 260, (1.0, 0.6, 0.3), size=2.2, rot=(0, D(-90), 0), parent=shop_ext)
    # street lamps
    iron = mat("iron", (0.03, 0.03, 0.035), 0.4, metal=0.8)
    lampm = emit("lampglass", (1.0, 0.62, 0.28), 14.0)
    R["lamp_mat"] = lampm
    R["lamps"] = []
    for side in (1, -1):
        for y in range(-6, 52, 9):
            yy = y + (4.5 if side < 0 else 0)
            x = side * 3.2
            cyl("pole", (x, yy, 1.5), 0.05, 3.0, iron)
            box("lantern", (x, yy, 3.15), (0.24, 0.24, 0.34), lampm)
            obj("lampcap", lib.m_prism(), (x, yy, 3.32), iron, scale=(0.32, 0.32, 0.18))
            L = light("lamp", "POINT", (x, yy, 3.0), 90, (1.0, 0.6, 0.28), size=0.12)
            R["lamps"].append(L)
    # clock tower at the end of the street
    stone = lib.noise_mat("stone", (0.26, 0.25, 0.24), (0.36, 0.34, 0.31), scale=4, rough=0.9, bump=0.3)
    box("tower", (0, 58, 8), (6, 5, 16), stone)
    obj("towerroof", lib.m_prism(), (0, 58, 15.98), M["roof"], scale=(6.6, 5.6, 4.0))
    tc = clocks.Clock("towerclock", (0, 55.42, 12), 0, "round", 1.6, dial="ivory", body=stone)
    R["tower_clock"] = tc
    tg = light("towerglow", "POINT", (0, 54.0, 12), 250, (1.0, 0.75, 0.4), size=0.5)
    R["tower_glow"] = tg
    # moon + moonlight
    moonm = emit("moon", (0.80, 0.86, 1.0), 8.0)
    sphere("moon", (-60, 220, 95), 9, moonm)
    moon = light("moonlight", "SUN", (0, 0, 30), 0.35, (0.55, 0.66, 1.0), size=0.02)
    moon.rotation_euler = (D(55), 0, D(195))
    R["moonlight"] = moon
    sun = light("sun", "SUN", (0, 0, 30), 0.0, (1.0, 0.80, 0.55), size=0.02)
    sun.rotation_euler = (D(68), 0, D(-120))
    R["sun"] = sun
    # fog
    fogm = lib.volume_mat("townfog", (0.60, 0.68, 0.85), density=0.03, anisotropy=0.45)
    R["town_fog"] = fogm
    box("townfog", (0, 20, 4), (28, 90, 8), fogm)


def _shop_window_png(path):
    import os
    if os.path.exists(path):
        return
    from PIL import Image, ImageDraw, ImageFilter
    import numpy as np
    W, H = 768, 576
    yy, xx = np.mgrid[0:H, 0:W]
    g = np.exp(-(((xx - W * 0.45) / (W * 0.5)) ** 2 + ((yy - H * 0.55) / (H * 0.6)) ** 2))
    base = np.stack([255 * (0.55 + 0.45 * g), 160 * (0.4 + 0.6 * g), 70 * (0.3 + 0.7 * g)], -1)
    img = Image.fromarray(base.clip(0, 255).astype("uint8"))
    d = ImageDraw.Draw(img)
    rng = random.Random(5)
    for row, y0 in enumerate((150, 300, 450)):
        d.rectangle([0, y0 + 40, W, y0 + 52], fill=(60, 30, 12))
        x = 20
        while x < W - 40:
            r = rng.randint(22, 40)
            d.ellipse([x, y0 + 40 - 2 * r, x + 2 * r, y0 + 40], fill=(70, 38, 16))
            d.ellipse([x + r * 0.25, y0 + 40 - 1.75 * r, x + 1.75 * r, y0 + 40 - 0.25 * r], fill=(235, 205, 150))
            x += 2 * r + rng.randint(8, 30)
    img = img.filter(ImageFilter.GaussianBlur(2.2))
    img.save(path)


# ------------------------------------------------------------------ SHOP interior
X0 = 100.0


def shop():
    rng = random.Random(3)
    x0 = X0
    floor = lib.noise_mat("planks", (0.16, 0.09, 0.05), (0.28, 0.16, 0.08), scale=3, rough=0.55, bump=0.2, kind="wave")
    panel = lib.noise_mat("panel", (0.12, 0.06, 0.035), (0.20, 0.11, 0.06), scale=6, rough=0.6, bump=0.1, kind="wave")
    plaster = lib.noise_mat("shopplaster", (0.20, 0.17, 0.12), (0.26, 0.22, 0.16), scale=4, rough=0.9, bump=0.15)
    box("sfloor", (x0, 3, -0.05), (6.4, 7, 0.1), floor)
    box("sceil", (x0, 3, 3.45), (6.4, 7, 0.1), panel)
    box("sback", (x0, 6.05, 1.7), (6.4, 0.1, 3.5), plaster)
    box("sbackpanel", (x0, 5.98, 0.5), (6.4, 0.06, 1.0), panel)
    # left wall with a window (y 1.6..3.0, z 1.1..2.5)
    wl = x0 - 3.05
    box("swl1", (wl, 0.8, 1.7), (0.1, 1.6, 3.5), plaster)
    box("swl2", (wl, 4.5, 1.7), (0.1, 3.0, 3.5), plaster)
    box("swl3", (wl, 2.3, 0.55), (0.1, 1.4, 1.1), plaster)
    box("swl4", (wl, 2.3, 2.98), (0.1, 1.4, 0.95), plaster)
    tim = mat("stimber", (0.08, 0.045, 0.025), 0.6)
    for yy in (1.6, 2.3, 3.0):
        box("swinbar", (wl, yy, 1.8), (0.12, 0.06, 1.4), tim)
    for zz in (1.1, 1.8, 2.5):
        box("swinbar", (wl, 2.3, zz), (0.12, 1.45, 0.06), tim)
    light("smoonwin", "AREA", (wl - 1.2, 2.3, 2.6), 520, (0.45, 0.6, 1.0), size=1.6, rot=(0, D(-70), 0))
    box("soutside", (wl - 3.0, 2.3, 1.7), (0.1, 6, 6), emit("snight", (0.05, 0.08, 0.16), 1.0))
    # right wall with the door (y 1.0..1.9, z 0..2.2)
    wr = x0 + 3.05
    box("swr1", (wr, 0.5, 1.7), (0.1, 1.0, 3.5), plaster)
    box("swr2", (wr, 4.0, 1.7), (0.1, 4.2, 3.5), plaster)
    box("swr3", (wr, 1.45, 2.85), (0.1, 0.9, 1.3), plaster)
    box("sdoorframe", (wr - 0.06, 1.45, 2.24), (0.14, 1.05, 0.1), tim)
    hinge = empty("sdoorhinge", (wr - 0.05, 1.0, 0))
    dm = mat("sdoor", (0.14, 0.08, 0.04), 0.55)
    box("sdoor", (0, 0.45, 1.1), (0.06, 0.9, 2.2), dm, hinge)
    box("sdoorwin", (-0.035, 0.45, 1.6), (0.01, 0.45, 0.55), emit("sdoorwin", (0.3, 0.45, 0.8), 1.5), hinge)
    sphere("sdoorknob", (-0.06, 0.8, 1.05), 0.03, clocks.mats()["brass"], hinge)
    R["shop_door"] = hinge
    bellp = empty("sbell", (wr - 0.15, 1.75, 2.15))
    box("sbellarm", (0.06, 0, 0.0), (0.14, 0.015, 0.015), clocks.mats()["brass"], bellp)
    bb = empty("sbellbob", (0.0, 0, -0.01), bellp)
    lib.lathe("sbellcup", (0, 0, -0.03), [(0.01, 0.0), (0.03, -0.01), (0.04, -0.05), (0.05, -0.075), (0.035, -0.075)], clocks.mats()["brass"], bb)
    R["shop_bell"] = bb
    light("sdoorback", "AREA", (wr + 1.6, 1.45, 1.4), 900, (0.45, 0.62, 1.0), size=1.5, rot=(0, D(90), 0))
    box("sdoorout", (wr + 3.0, 1.45, 1.7), (0.1, 4, 4), emit("snight2", (0.10, 0.16, 0.32), 1.0))
    fo = lib.volume_mat("sdoorfog", (0.6, 0.7, 0.9), density=0.35, anisotropy=0.5)
    box("sdoorfogbox", (wr + 1.0, 1.45, 1.5), (1.8, 2.4, 3.0), fo)
    # haze inside (candle + window beams)
    hz = lib.volume_mat("shaze", (0.9, 0.85, 0.8), density=0.035, anisotropy=0.35)
    box("shazebox", (x0, 3.0, 1.7), (6.0, 6.0, 3.4), hz)
    # shelves on the back wall + clocks
    shelfm = lib.noise_mat("shelf", (0.16, 0.08, 0.04), (0.26, 0.14, 0.07), scale=8, rough=0.5, bump=0.1, kind="wave")
    R["shelf_clocks"] = []
    boards = [0.95, 1.45, 1.95, 2.45]
    for z in boards:
        box("board", (x0, 5.82, z - 0.03), (6.0, 0.36, 0.05), shelfm)
    for xx in (x0 - 3.0, x0 - 1.0, x0 + 1.0, x0 + 3.0):
        box("upright", (xx, 5.82, 1.6), (0.06, 0.36, 2.0), shelfm)
    styles = ["round", "mantel", "square", "round", "mantel"]
    dials = ["cream", "ivory", "dark", "cream", "ivory", "blue"]
    bodies = [None, clocks.mats()["wood"], clocks.mats()["wood2"], clocks.mats()["wood3"], clocks.mats()["brass_dark"]]
    reserved = {(1, 0.2), (0, 1.7)}  # hero spots (board index, x offset)
    for bi, z in enumerate(boards):
        x = x0 - 2.85
        while x < x0 + 2.85:
            st = rng.choice(styles)
            r = rng.uniform(0.07, 0.11) if st != "square" else rng.uniform(0.06, 0.08)
            wdt = r * (2.7 if st != "round" else 2.3)
            cx = x + wdt / 2
            if any(bi == b and abs(cx - (x0 + ox)) < 0.25 for b, ox in reserved):
                x += 0.5
                continue
            if cx + wdt / 2 > x0 + 2.9:
                break
            zc = z + (r * 2.18 if st == "mantel" else r * 1.12 if st == "round" else r * 1.25)
            if st == "round":
                zc = z + r * 1.1
            c = clocks.Clock(f"sc{bi}_{len(R['shelf_clocks'])}", (cx, 5.62 + rng.uniform(-0.03, 0.03), zc), rng.uniform(-8, 8), st, r,
                             dial=rng.choice(dials), body=rng.choice(bodies))
            c.phase = rng.uniform(0, 360)
            R["shelf_clocks"].append(c)
            x += wdt + rng.uniform(0.03, 0.08)
    # wall clocks high on the back wall
    for k in range(9):
        cx = x0 - 2.7 + k * 0.68 + rng.uniform(-0.05, 0.05)
        r = rng.uniform(0.12, 0.17)
        c = clocks.Clock(f"wc{k}", (cx, 5.96, 3.0 + rng.uniform(-0.08, 0.08)), 0, "round", r, dial=rng.choice(dials), body=rng.choice(bodies))
        c.phase = rng.uniform(0, 360)
        R["shelf_clocks"].append(c)
    # clocks on the left wall (facing +X) between window and back
    for k in range(10):
        r = rng.uniform(0.09, 0.15)
        c = clocks.Clock(f"lc{k}", (x0 - 2.98, 3.4 + (k % 5) * 0.5, 1.4 + (k // 5) * 0.75 + rng.uniform(-0.05, 0.05)), -90, "round", r,
                         dial=rng.choice(dials), body=rng.choice(bodies))
        c.phase = rng.uniform(0, 360)
        R["shelf_clocks"].append(c)
    # pendulum clocks in the corners
    R["pendulums"] = []
    for k, (px, py) in enumerate(((x0 - 2.6, 5.35), (x0 + 2.6, 5.35))):
        c = clocks.Clock(f"pc{k}", (px, py - 0.25, 1.75), 0, "pendulum", 0.14, dial="cream", body=clocks.mats()["wood2"])
        c.phase = rng.uniform(0, 360)
        R["shelf_clocks"].append(c)
        R["pendulums"].append(c)
    # hero clocks on the shelves
    names = {"ostap": ("ОСТАП", 1, -1.3), "marta": ("МАРТА", 2, -0.4), "ivan": ("ІВАН", 1, 0.9), "sofia": ("СОФІЯ", 2, 1.5),
             "taras": ("ТАРАС", 0, 1.7)}
    R["heroes"] = {}
    for key, (nm, bi, ox) in names.items():
        z = boards[bi]
        st = "round" if key in ("ostap", "ivan") else "mantel"
        r = 0.1
        zc = z + (r * 2.18 if st == "mantel" else r * 1.1)
        c = clocks.Clock("hero_" + key, (x0 + ox, 5.55, zc), 0, st, r, dial="cream" if key != "sofia" else "ivory", label=nm,
                         body=clocks.mats()["wood"], seconds=True, glass=False)
        c.phase = rng.uniform(0, 360)
        R["heroes"][key] = c
    # grandma's small silver alarm clock on the lowest shelf (front)
    redlab = emit("olena_lab", (1.0, 0.12, 0.06), 6.0)
    g = clocks.Clock("olena", (x0 + 0.2, 5.5, boards[0] + 0.088), 0, "alarm", 0.065, dial="silver", label="ОЛЕНА", label_mat=redlab,
                     body=clocks.mats()["silver"], seconds=True, glass=True, counter="1:00")
    R["olena_shop"] = g
    # workbench, stool, candle, tools
    bench = lib.noise_mat("bench", (0.18, 0.10, 0.05), (0.30, 0.17, 0.08), scale=5, rough=0.45, bump=0.1, kind="wave")
    box("benchtop", (x0 - 0.7, 2.3, 0.86), (2.0, 0.8, 0.07), bench)
    box("benchfront", (x0 - 0.7, 1.93, 0.45), (2.0, 0.05, 0.8), bench)
    for sx in (-0.95, 0.95):
        box("benchleg", (x0 - 0.7 + sx, 2.3, 0.42), (0.08, 0.7, 0.84), bench)
    cream = mat("candlewax", (0.95, 0.88, 0.70), 0.4, sss=0.6)
    cyl("candle", (x0 - 1.35, 2.15, 0.96), 0.025, 0.14, cream, seg=24)
    cyl("candlestick", (x0 - 1.35, 2.15, 0.9), 0.06, 0.012, clocks.mats()["brass"], seg=24)
    flame = sphere("flame", (x0 - 1.35, 2.15, 1.055), (0.012, 0.012, 0.03), emit("flame", (1.0, 0.55, 0.15), 30.0))
    R["flame"] = flame
    R["candle"] = light("candlelight", "POINT", (x0 - 1.35, 2.12, 1.09), 22, (1.0, 0.55, 0.22), size=0.02)
    # second / third candle on brackets for shelf light
    for k, (cx, cy, cz) in enumerate(((x0 - 1.9, 5.55, 2.25), (x0 + 1.9, 5.55, 1.75))):
        cyl("candle2", (cx, cy, cz), 0.02, 0.1, cream, seg=16)
        sphere("flame2", (cx, cy, cz + 0.07), (0.01, 0.01, 0.025), emit("flame2", (1.0, 0.55, 0.15), 30.0))
        R.setdefault("candles2", []).append(light("candle2", "POINT", (cx, cy - 0.12, cz + 0.1), 10, (1.0, 0.55, 0.22), size=0.02))
    # open clock movement, magnifier, tools on the bench
    br = clocks.mats()["brass"]
    R["gears"] = []
    for k, (gx, gy, gr) in enumerate(((x0 - 0.75, 2.2, 0.06), (x0 - 0.62, 2.28, 0.035), (x0 - 0.86, 2.3, 0.03), (x0 - 0.5, 2.18, 0.022))):
        gp = empty("gear", (gx, gy, 0.905))
        cyl("gearw", (0, 0, 0), gr, 0.006, br, gp, seg=36)
        for t in range(int(gr * 300)):
            a = 2 * math.pi * t / int(gr * 300)
            box("tooth", (math.cos(a) * gr, math.sin(a) * gr, 0), (0.006, 0.006, 0.006), br, gp, rot=(0, 0, a))
        R["gears"].append((gp, (1 if k % 2 else -1) * 0.06 / gr))
    sphere("loupe", (x0 - 0.2, 2.25, 0.92), (0.03, 0.03, 0.03), mat("loupe", (0.05, 0.05, 0.05), 0.3))
    box("tweezers", (x0 - 1.05, 2.05, 0.9), (0.12, 0.008, 0.004), clocks.mats()["silver"], rot=(0, 0, 0.4))
    cyl("stool", (x0 - 0.7, 2.95, 0.27), 0.2, 0.54, bench, seg=24)
    # warm bounce so faces are readable
    light("sfill", "AREA", (x0 - 0.5, 0.5, 2.6), 60, (1.0, 0.7, 0.45), size=2.5, rot=(D(50), 0, 0))
    light("sshelfwash", "AREA", (x0, 4.3, 3.3), 45, (1.0, 0.68, 0.4), size=4.0, rot=(D(30), 0, 0))


# ------------------------------------------------------------------ ROOM
X1 = 200.0


def room():
    x1 = X1
    rng = random.Random(9)
    floor = lib.noise_mat("rplanks", (0.20, 0.12, 0.07), (0.32, 0.20, 0.11), scale=3, rough=0.55, bump=0.2, kind="wave")
    wall = lib.noise_mat("rwall", (0.30, 0.20, 0.13), (0.38, 0.26, 0.16), scale=5, rough=0.8, bump=0.1, kind="wave")
    box("rfloor", (x1, 2.5, -0.05), (6.4, 6, 0.1), floor)
    box("rceil", (x1, 2.5, 2.85), (6.4, 6, 0.1), wall)
    # back wall with window (x 199.6..201.0, z 1.0..2.3)
    by = 5.05
    box("rb1", (x1 - 1.85, by, 1.4), (2.7, 0.1, 2.8), wall)
    box("rb2", (x1 + 2.1, by, 1.4), (2.2, 0.1, 2.8), wall)
    box("rb3", (x1 + 0.3, by, 0.5), (1.4, 0.1, 1.0), wall)
    box("rb4", (x1 + 0.3, by, 2.58), (1.4, 0.1, 0.55), wall)
    tim = mat("rtimber", (0.12, 0.07, 0.04), 0.6)
    for xx in (x1 - 0.4, x1 + 0.3, x1 + 1.0):
        box("rwinbar", (xx, by, 1.65), (0.06, 0.12, 1.3), tim)
    for zz in (1.0, 1.65, 2.3):
        box("rwinbar", (x1 + 0.3, by, zz), (1.45, 0.12, 0.06), tim)
    box("rsill", (x1 + 0.3, by - 0.12, 0.97), (1.6, 0.25, 0.05), tim)
    light("rmoon", "AREA", (x1 + 0.3, by + 1.5, 2.4), 650, (0.45, 0.6, 1.0), size=1.4, rot=(D(-60), 0, 0))
    sky = lib.noise_mat("rsky", (0.02, 0.04, 0.10), (0.06, 0.09, 0.2), scale=2, rough=1.0, bump=0.0)
    lib._bsdf(sky).inputs["Emission Color"].default_value = (0.05, 0.08, 0.18, 1)
    lib._bsdf(sky).inputs["Emission Strength"].default_value = 1.0
    box("rsky", (x1, by + 8, 3), (20, 0.1, 12), sky)
    sphere("rmoondisc", (x1 + 0.9, by + 7.9, 3.4), 0.55, emit("rmoond", (0.85, 0.9, 1.0), 6.0))
    # snowy roofs outside
    snow = mat("snow", (0.75, 0.8, 0.9), 0.6)
    for k in range(5):
        obj("rroof", lib.m_prism(), (x1 - 3 + k * 2.2, by + 5 + rng.uniform(0, 1.5), rng.uniform(-0.5, 0.6)), snow, scale=(2.0, 2.2, 1.2))
    # left wall with door (y 1.4..2.3)
    wx = x1 - 3.05
    box("rl1", (wx, 0.7, 1.4), (0.1, 1.4, 2.8), wall)
    box("rl2", (wx, 3.7, 1.4), (0.1, 2.8, 2.8), wall)
    box("rl3", (wx, 1.85, 2.5), (0.1, 0.9, 0.7), wall)
    hinge = empty("rdoorhinge", (wx + 0.05, 1.4, 0))
    box("rdoor", (0, 0.45, 1.075), (0.06, 0.9, 2.15), mat("rdoorm", (0.25, 0.14, 0.07), 0.6), hinge)
    sphere("rknob", (0.06, 0.78, 1.0), 0.03, clocks.mats()["brass"], hinge)
    R["room_door"] = hinge
    light("rdoorback", "AREA", (wx - 1.5, 1.85, 1.3), 500, (0.45, 0.6, 1.0), size=1.4, rot=(0, D(-90), 0))
    box("rdoorout", (wx - 3, 1.85, 1.5), (0.1, 4, 4), emit("rnight", (0.10, 0.15, 0.30), 1.0))
    # right wall
    box("rr", (x1 + 3.05, 2.5, 1.4), (0.1, 6, 2.8), wall)
    # furniture: rug, rocking chair, side table with oil lamp, picture frames, dresser
    rug = lib.noise_mat("rug", (0.45, 0.08, 0.06), (0.65, 0.35, 0.12), scale=6, rough=0.95, bump=0.2, kind="wave")
    cyl("rrug", (x1 + 0.1, 3.0, 0.005), 1.3, 0.01, rug, seg=48)
    chair = empty("rchair", (x1 + 0.3, 3.75, 0), rot=(0, 0, D(-20)))
    R["chair"] = chair
    cw = mat("rchairw", (0.28, 0.14, 0.06), 0.45, coat=0.2)
    rock = empty("rrock", (0, 0, 0), chair)
    R["rock"] = rock
    for sx in (-0.26, 0.26):
        torus("rocker", (sx, 0.05, 0.62), 0.62, 0.025, cw, rock, rot=(0, D(90), 0), a0=D(240), a1=D(300))
        box("rleg", (sx, -0.18, 0.22), (0.04, 0.04, 0.4), cw, rock)
        box("rleg", (sx, 0.22, 0.22), (0.04, 0.04, 0.4), cw, rock)
        box("rpost", (sx, 0.26, 0.9), (0.04, 0.04, 1.0), cw, rock, rot=(D(-12), 0, 0))
        box("rarm", (sx, 0.0, 0.66), (0.05, 0.5, 0.04), cw, rock)
    box("rseat", (0, 0.02, 0.44), (0.58, 0.5, 0.05), cw, rock)
    box("rback", (0, 0.3, 0.95), (0.55, 0.04, 0.75), cw, rock, rot=(D(-12), 0, 0))
    cush = lib.noise_mat("cushion", (0.55, 0.30, 0.10), (0.7, 0.45, 0.2), scale=40, rough=0.9, bump=0.3, kind="wave")
    box("rcush", (0, 0.02, 0.48), (0.5, 0.45, 0.06), cush, rock, bevel=0.0)
    table = empty("rtable", (x1 + 1.25, 3.7, 0))
    cyl("rtabletop", (0, 0, 0.6), 0.28, 0.04, cw, table)
    cyl("rtableleg", (0, 0, 0.3), 0.04, 0.6, cw, table)
    lampg = emit("oillamp", (1.0, 0.6, 0.25), 6.0)
    R["oillamp_mat"] = lampg
    lib.lathe("lampglass", (0, 0, 0.82), [(0.03, 0.12), (0.06, 0.06), (0.07, 0.0), (0.05, -0.05), (0.03, -0.06)], lampg, table)
    cyl("lampbase", (0, 0, 0.68), 0.07, 0.08, clocks.mats()["brass"], table)
    R["oillamp"] = light("roillamp", "POINT", (x1 + 1.25, 3.7, 0.85), 45, (1.0, 0.58, 0.25), size=0.05)
    box("rdresser", (x1 + 2.6, 2.0, 0.45), (0.6, 1.2, 0.9), cw)
    for k, (fx, fz) in enumerate(((x1 + 2.98, 1.7), (x1 + 2.98, 1.65))):
        pass
    for k in range(3):
        f = box("rframe", (x1 - 1.6 + k * 0.5, by - 0.07, 1.6 + (k % 2) * 0.25), (0.3, 0.03, 0.38), clocks.mats()["brass_dark"])
        box("rpic", (x1 - 1.6 + k * 0.5, by - 0.09, 1.6 + (k % 2) * 0.25), (0.24, 0.01, 0.3), mat("rpic", (0.3 + 0.1 * k, 0.25, 0.2), 0.8))
    # warm golden hug light + ripple sphere
    R["hug_light"] = light("rhug", "POINT", (x1 - 0.1, 3.0, 1.1), 0, (1.0, 0.7, 0.3), size=0.6)
    R["room_fill"] = light("rfill", "AREA", (x1 - 1.0, 0.6, 2.4), 50, (1.0, 0.75, 0.5), size=2.5, rot=(D(50), 0, D(-20)))
    ripm = ripple_mat()
    R["ripple"] = sphere("ripple", (x1, 3.0, 1.0), 0.01, ripm)
    R["ripple_mat"] = ripm
    hz = lib.volume_mat("rhaze", (0.9, 0.85, 0.8), density=0.02, anisotropy=0.4)
    box("rhazebox", (x1, 2.5, 1.4), (6.0, 5.8, 2.8), hz)


def ripple_mat():
    m = bpy.data.materials.new("ripple")
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.08
    pw = nt.nodes.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = 3.0
    nt.links.new(lw.outputs["Facing"], pw.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 0.72, 0.3, 1)
    st = nt.nodes.new("ShaderNodeValue"); st.name = "strength"; st.outputs[0].default_value = 0.0
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
    nt.links.new(pw.outputs[0], mul.inputs[0]); nt.links.new(st.outputs[0], mul.inputs[1])
    nt.links.new(mul.outputs[0], em.inputs["Strength"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(tr.outputs[0], add.inputs[0]); nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


# ------------------------------------------------------------------ VOID (black end card)
X2 = 300.0


def void():
    x2 = X2
    black = mat("void", (0, 0, 0), 1.0, spec=0.0)
    s = sphere("voidsphere", (x2, 0, 1), 12, black)
    blue = emit("endlab", (0.3, 0.6, 1.0), 6.0)
    c = clocks.Clock("endclock", (x2, 0, 1.0), 0, "alarm", 0.32, dial="blue", label=None, body=clocks.mats()["silver"], seconds=True)
    R["endclock"] = c
    R["endlight"] = light("endkey", "SPOT", (x2 - 0.8, -1.6, 2.2), 0, (0.6, 0.75, 1.0), size=0.2, spot=D(40))
    lib.aim(R["endlight"], (x2, 0, 1.0))
    R["endrim"] = light("endrim", "AREA", (x2 + 0.6, 0.9, 1.8), 0, (1.0, 0.7, 0.35), size=0.6)
    lib.aim(R["endrim"], (x2, 0, 1.0))
    R["enddial_mat"] = c.dial.material_slots[0].material
