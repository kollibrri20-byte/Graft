import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paint_core import *

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def sky_night(c, moon=None, stars=300, top=NIGHT_TOP, bot=NIGHT_BOT, horizon=None):
    c.vgrad(top, bot, 0, horizon or c.h, 0.8)
    if stars:
        c.stars(stars, 0.55)
    if moon:
        c.moon(*moon)


def s008(c):
    hz = c.h * 0.52
    sky_night(c, stars=250, horizon=hz)
    forest_row(c, hz + 10, 80, 160, 1.3, C("0b111a"), 81, 2.0)
    c.fog(hz - 120, hz + 60, FOG_BLUE, 0.5, 500, seed=82)
    c.fill(c.rect_mask(0, hz, c.w, c.h, 2), C("15120f"))
    road_persp(c, c.w / 2, hz, c.w * 0.9, C("2a2620"))
    for i in range(4, 0, -1):
        t = i / 4
        s = 900 * (1 - t) ** 1.25 + 140
        yb = hz + (c.h * 0.98 - hz) * (1 - t) ** 1.3 + 12
        for side in (-1, 1):
            hut(c, c.w / 2 + side * (s * 0.75 + 120 * (1 - t) + 70), yb, s, lit=1.2, wall_light=0.09 + 0.05 * (1 - t))
        c.fog(hz - 40, yb + 20, FOG_BLUE, 0.12, 400, seed=90 + i)
    # знак на передньому плані
    x, y, s = c.w * 0.13, c.h * 0.58, 420
    c.fill(c.rect_mask(x - 12, y, x + 12, c.h + 10, 1.5), C("060403"))
    pm = c.poly_mask([(x - s * 0.5, y - s * 0.16), (x + s * 0.48, y - s * 0.19), (x + s * 0.5, y + s * 0.12), (x - s * 0.47, y + s * 0.15)], 2)
    c.fill(pm, (WOOD * 0.2)[None, None, :] * (0.6 + 0.4 * c.noise(30, 3, aspect=0.15))[:, :, None])
    c.glow *= 0.75
    c.fog(c.h * 0.5, c.h * 1.1, FOG_BLUE, 0.2, 450, seed=99)
    return {}


def s036(c):
    c.vgrad(C("05070b"), C("120f0b"), 0, c.h)
    c.fill(c.rect_mask(c.w * 0.18, c.h * 0.0, c.w * 0.82, c.h * 0.86, 2), (WHITEWASH * 0.13)[None, None, :] * (0.8 + 0.2 * c.noise(120, 4))[:, :, None])
    for wx in (c.w * 0.27, c.w * 0.73):   # вікна з синіми віконницями
        wm = c.rect_mask(wx - 70, c.h * 0.3, wx + 70, c.h * 0.52, 1)
        c.fill(wm, AMBER * 0.85); c.emit(wm, AMBER, 0.6)
        for sx in (wx - 115, wx + 115):
            c.fill(c.rect_mask(sx - 40, c.h * 0.29, sx + 40, c.h * 0.53, 1), C("2c5a9a") * 0.45)
    dm = c.rect_mask(c.w * 0.42, c.h * 0.2, c.w * 0.58, c.h * 0.86, 1.5)
    c.fill(dm, AMBER * 0.9); c.emit(dm, AMBER, 1.0)
    c.light(c.w * 0.5, c.h * 0.55, 600, AMBER, 0.25)
    c.fill(c.rect_mask(c.w * 0.1, c.h * 0.86, c.w * 0.9, c.h * 0.9, 1.5), WOOD * 0.25)
    c.fill(c.rect_mask(c.w * 0.05, c.h * 0.9, c.w * 0.95, c.h, 1.5), WOOD * 0.15)
    for x in (c.w * 0.36, c.w * 0.64):
        c.fill(c.rect_mask(x - 12, c.h * 0.05, x + 12, c.h * 0.86, 1), WOOD * 0.2)
    c.fill(c.rect_mask(c.w * 0.15, 0, c.w * 0.85, c.h * 0.06, 2), THATCH * 0.2)
    m = figure(c, c.w * 0.5, c.h * 0.875, 600, "hanna", color=C("030303"), rim=AMBER, rim_dir=(0, -1), back=True)
    c.glow *= (1 - 0.97 * m)[:, :, None]
    c.fog(c.h * 0.4, c.h * 1.05, FOG_BLUE, 0.3, 400, seed=361)
    return {}


def s067(c):
    hz = c.h * 0.5
    sky_night(c, moon=(c.w * 0.85, c.h * 0.1, 45), stars=200, horizon=hz)
    church(c, c.w * 0.15, hz + 20, 240, C("070a10"))
    c.fill(c.rect_mask(0, hz, c.w, c.h, 2), C("101318"))
    r = np.random.default_rng(67)
    for i in range(18):
        x, t = r.uniform(0, c.w), r.uniform(0, 1)
        yb = hz + 30 + t * c.h * 0.45
        if abs(x - c.w * 0.5) < 200 and yb > c.h * 0.65:
            continue
        cross(c, x, yb, 70 + 220 * t, C("080a0e"), tilt=r.uniform(-14, 14))
    c.fog(hz - 60, c.h, FOG_BLUE, 0.55, 400, seed=671)
    c.fill(c.ell_mask(c.w * 0.5, c.h * 0.87, 270, 70, 4), C("2a2018"))
    for i in range(10):
        a = i / 10 * 6.28
        fx, fy = c.w * 0.5 + np.cos(a) * 120, c.h * 0.85 + np.sin(a) * 25
        c.fill(c.ell_mask(fx, fy, 14, 10, 1.5), C("e8e4dc") * 0.6 if i % 2 else C("b01818") * 0.7)
    c.emit(c.poly_mask([(c.w * 0.62, -10), (c.w * 0.7, -10), (c.w * 0.56, c.h * 0.9), (c.w * 0.42, c.h * 0.9)], 40), MOON, 0.2)
    cross(c, c.w * 0.5, c.h * 0.85, 280, C("3a2c1e"))
    tw = c.poly_mask([(c.w * 0.5 + 60, c.h * 0.85 - 210), (c.w * 0.5 + 85, c.h * 0.85 - 210), (c.w * 0.5 + 80, c.h * 0.85 - 90), (c.w * 0.5 + 62, c.h * 0.85 - 85)], 1.5)
    c.fill(tw, SCARF * 0.55)
    c.tint_light(c.w * 0.5, c.h * 0.78, 300, MOON, 0.5)
    return {"grade": g_cold}


for n, fn in ((8, s008), (36, s036), (67, s067)):
    c = Canvas(1000 + n)
    o = fn(c)
    c.finish(o.get("grade"), vignette=0.55, grain=0.022).save(os.path.join(OUT, f"sample_{n:03d}.jpg"), quality=92)
    print("ok", n)
