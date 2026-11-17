#!/usr/bin/env python3
"""
"Ashfall Camp" — vertical 9:16 procedural cinematic (no text, no logos).

A 2.5D renderer: perspective-projected billboard layers (ruined city, rubble
fields, forest, clearing with tent and campfire) over a ray-cast ground plane
and a perspective cloud deck, plus particles (ash, embers), smoke, lightning
and a light film grade. Everything is generated procedurally from fixed seeds.

Usage:
    python3 render.py                    # full 1080x1920 -> out/video_only.mp4
    python3 render.py --preview 0.5 4 10 16 20.7   # PNG stills at half size
"""
import math
import os
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import map_coordinates

# --------------------------------------------------------------------------
# Global settings
# --------------------------------------------------------------------------
SCALE = 1.0
W, H = 1080, 1920
FPS = 30
DUR = 24.0
NF = int(DUR * FPS)
F = (H / 2) / math.tan(math.radians(30))  # focal length in px (60deg vFOV)
S = W / 1080.0

FOG_COL = np.array([108, 32, 20], np.float32) / 255.0
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def set_scale(s):
    global SCALE, W, H, F, S
    SCALE = s
    W, H = int(round(1080 * s)), int(round(1920 * s))
    F = (H / 2) / math.tan(math.radians(30))
    S = W / 1080.0


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def fractal_noise(n, beta, seed):
    r = np.random.default_rng(seed)
    white = r.standard_normal((n, n))
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.fftfreq(n)[None, :]
    k = np.sqrt(fx ** 2 + fy ** 2)
    k[0, 0] = 1.0
    spec = np.fft.fft2(white) / k ** (beta / 2)
    spec[0, 0] = 0
    out = np.real(np.fft.ifft2(spec))
    out = (out - out.min()) / (out.max() - out.min())
    return out.astype(np.float32)


NOISE = fractal_noise(512, 2.3, 11)   # clouds / smoke (tileable)
NOISE2 = fractal_noise(256, 1.7, 22)  # detail


def samp(tex, y, x):
    y = np.asarray(y, np.float32)
    x = np.asarray(x, np.float32)
    y, x = np.broadcast_arrays(y, x)
    n = tex.shape[0]
    return map_coordinates(tex, [np.mod(y, n), np.mod(x, n)], order=1,
                           mode="grid-wrap")


def up_f(a, size):
    """Bilinear upscale of a float 2D array to size=(w,h)."""
    return np.asarray(Image.fromarray(a.astype(np.float32), "F").resize(size, Image.BILINEAR))


def up_rgb(a, size):
    return np.stack([up_f(a[..., c], size) for c in range(3)], -1)


def to_rgba_img(rgb, alpha):
    arr = np.concatenate([np.clip(rgb, 0, 1), np.clip(alpha, 0, 1)[..., None]], -1)
    return Image.fromarray((arr * 255 + 0.5).astype(np.uint8), "RGBA").convert("RGBa")


def img_to_float(im):
    a = np.asarray(im, np.float32) / 255.0
    return a[..., :3], a[..., 3]


def rim_light(rgb, alpha, color, strength, px, sides=0.0):
    """Add a back/top rim to silhouettes (edges whose neighbour above is empty)."""
    A = alpha
    upa = np.zeros_like(A)
    upa[px:] = A[:-px]
    rim = np.clip(A - upa, 0, 1)
    if sides > 0:
        lf = np.zeros_like(A)
        lf[:, px:] = A[:, :-px]
        rt = np.zeros_like(A)
        rt[:, :-px] = A[:, px:]
        rim = np.maximum(rim, sides * np.clip(A - np.minimum(lf, rt), 0, 1))
    rimi = np.asarray(Image.fromarray((rim * 255).astype(np.uint8), "L")
                      .filter(ImageFilter.GaussianBlur(px * 0.6)), np.float32) / 255.0
    rimi = np.minimum(rimi * 1.6, 1.0) * A
    return rgb + rimi[..., None] * np.asarray(color, np.float32) * strength


# --------------------------------------------------------------------------
# Camera
# --------------------------------------------------------------------------
_KT = [0.0, 8.0, 12.5, 15.5, 24.0]
_K = dict(
    cz=[0.0, 250.0, 385.0, 409.0, 414.0],
    cy=[40.0, 34.0, 30.0, 0.70, 0.62],
    hor=[0.47, 0.40, 0.42, 0.615, 0.615],
    cx=[-8.0, 3.0, -1.0, 0.25, 0.35],
)
_INTERP = {k: PchipInterpolator(_KT, v) for k, v in _K.items()}


class Cam:
    def __init__(self, t):
        self.cz = float(_INTERP["cz"](t))
        self.cy = float(_INTERP["cy"](t))
        self.cx = float(_INTERP["cx"](t))
        hor = float(_INTERP["hor"](t))
        # gentle handheld float, stronger once grounded
        g = smoothstep(13.0, 16.0, t)
        self.cx += 0.02 * math.sin(0.7 * t) * g
        self.cy += 0.006 * math.sin(1.1 * t + 1) * g
        self.hor = hor * H + (2.5 * math.sin(0.45 * t) + 1.5 * math.sin(1.3 * t + 2)) * S


# --------------------------------------------------------------------------
# Lightning
# --------------------------------------------------------------------------
# (time, amplitude, screen x frac of bolt, draw bolt?, seed)
STRIKES = [
    (4.40, 0.40, 0.22, True, 5),
    (18.70, 0.45, 0.16, False, 6),
    (20.60, 1.00, 0.62, True, 7),
    (22.55, 0.50, 0.40, False, 8),
]


def flash_env(t, t0):
    e = 0.0
    for dt, a in ((0.0, 1.0), (0.085, 0.55), (0.22, 0.9), (0.40, 0.35)):
        x = t - (t0 + dt)
        if x >= 0:
            e += a * math.exp(-x / 0.075)
    return min(e, 1.3)


def flash_total(t):
    return sum(a * flash_env(t, t0) for t0, a, _, _, _ in STRIKES)


def bolt_paths(seed):
    r = np.random.default_rng(seed)

    def mid(p0, p1, disp, depth, out):
        if depth == 0:
            out.append((p0, p1))
            return
        m = ((p0[0] + p1[0]) / 2 + r.normal(0, disp), (p0[1] + p1[1]) / 2 + r.normal(0, disp * 0.25))
        mid(p0, m, disp * 0.55, depth - 1, out)
        mid(m, p1, disp * 0.55, depth - 1, out)

    segs = []
    main = []
    mid((0.0, 0.0), (r.uniform(-0.10, 0.10), 1.0), 0.09, 7, main)
    segs.append((main, 1.0))
    for _ in range(4):
        k = r.integers(len(main) // 6, len(main) // 2)
        p0 = main[k][0]
        p1 = (p0[0] + r.uniform(-0.25, 0.25), p0[1] + r.uniform(0.15, 0.35))
        br = []
        mid(p0, p1, 0.05, 5, br)
        segs.append((br, 0.45))
    return segs


BOLTS = {s[4]: bolt_paths(s[4]) for s in STRIKES}


# --------------------------------------------------------------------------
# Layer builders (static billboards)
# --------------------------------------------------------------------------
class Layer:
    def __init__(self, img, xl, wm, hm, z, yb=0.0, fogk=1.0, mode="over", name=""):
        self.img, self.xl, self.wm, self.hm, self.z = img, xl, wm, hm, z
        self.yb, self.fogk, self.mode, self.name = yb, fogk, mode, name


def _canvas(wm, hm, ppm):
    w, h = int(wm * ppm), int(hm * ppm)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im), w, h


def _finish(im, rim_col, rim_s, rim_px, sides=0.0, vgrad=(0.75, 1.15), extra=None):
    a = np.asarray(im, np.float32) / 255.0
    rgb, A = a[..., :3], a[..., 3]
    h = A.shape[0]
    g = np.linspace(vgrad[1], vgrad[0], h)[:, None, None]
    rgb = rgb * g
    rgb = rim_light(rgb, A, rim_col, rim_s, rim_px, sides)
    if extra is not None:
        rgb, A = extra(rgb, A)
    return to_rgba_img(rgb, A)


def build_city(seed, wm, hm, ppm, hmin, hmax, base_col, fires=12):
    r = np.random.default_rng(seed)
    im, d, w, h = _canvas(wm, hm, ppm)
    X = lambda xm: (xm + wm / 2) * ppm
    Y = lambda ym: h - ym * ppm
    glow = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(glow)
    x = -wm / 2 + r.uniform(0, 20)
    while x < wm / 2:
        bw = r.uniform(22, 95)
        bh = r.uniform(hmin, hmax) * (0.45 + 0.55 * r.random() ** 0.6)
        c = tuple(int(v * r.uniform(0.8, 1.2)) for v in base_col) + (255,)
        kind = r.random()
        if kind < 0.3:  # mostly intact with antenna
            d.rectangle([X(x), Y(bh), X(x + bw), h], fill=c)
            if r.random() < 0.6:
                ax = x + bw * r.uniform(0.3, 0.7)
                d.line([X(ax), Y(bh), X(ax + r.uniform(-4, 4)), Y(bh + r.uniform(15, 50))], fill=c, width=max(1, int(1.2 * ppm)))
        elif kind < 0.8:  # broken jagged top
            n = max(4, int(bw / 4))
            pts = [(X(x), h)]
            hb = bh * r.uniform(0.55, 0.9)
            for i in range(n + 1):
                xx = x + bw * i / n
                yy = hb + (bh - hb) * (1 - abs(i / n - r.uniform(0.2, 0.8)) * 1.6) + r.uniform(-8, 8)
                pts.append((X(xx), Y(max(yy, hb * 0.6))))
            pts.append((X(x + bw), h))
            d.polygon(pts, fill=c)
        else:  # skeleton frame on top of a lower block
            hb = bh * r.uniform(0.45, 0.7)
            d.rectangle([X(x), Y(hb), X(x + bw), h], fill=c)
            for k in range(int(bw / 9) + 1):
                xx = x + k * 9
                top = hb + (bh - hb) * r.uniform(0.3, 1.0)
                d.line([X(xx), Y(hb), X(xx), Y(top)], fill=c, width=max(1, int(1.5 * ppm)))
            for k in range(int((bh - hb) / 10)):
                yy = hb + k * 10
                x0 = x + r.uniform(0, bw * 0.3)
                d.line([X(x0), Y(yy), X(x0 + r.uniform(0.3, 0.9) * bw), Y(yy)], fill=c, width=max(1, int(1.2 * ppm)))
        # sparse fire-lit windows
        nwin = int(bw * bh / 500 * r.uniform(0.3, 1.0))
        for _ in range(nwin):
            wx, wy = x + r.uniform(2, bw - 2), r.uniform(6, bh * 0.6)
            if r.random() < 0.25:
                col = (int(r.uniform(180, 255)), int(r.uniform(60, 120)), 20, 255)
                d.rectangle([X(wx), Y(wy + 2.5), X(wx + 2.5), Y(wy)], fill=col)
                gd.ellipse([X(wx - 6), Y(wy + 8), X(wx + 8), Y(wy - 6)], fill=int(r.uniform(40, 110)))
        x += bw + r.uniform(2, 16)
    for _ in range(fires):  # ground fires
        fx, fs = r.uniform(-wm / 2, wm / 2), r.uniform(10, 40)
        gd.ellipse([X(fx - fs), Y(fs * 1.2), X(fx + fs), Y(-fs * 0.3)], fill=int(r.uniform(120, 230)))
    glow = np.asarray(glow.filter(ImageFilter.GaussianBlur(6 * ppm)), np.float32) / 255.0

    def extra(rgb, A):
        g = glow[..., None]
        rgb = rgb + g * np.array([1.0, 0.38, 0.1]) * 0.9
        A = np.maximum(A, np.clip(glow * 0.8, 0, 1))
        return rgb, A

    return _finish(im, (0.85, 0.28, 0.12), 0.45, max(2, int(1.5 * ppm)), sides=0.5, vgrad=(0.8, 1.2), extra=extra)


def build_ruins(seed, wm=300.0, hm=46.0, ppm=18.0):
    r = np.random.default_rng(seed)
    im, d, w, h = _canvas(wm, hm, ppm)
    X = lambda xm: (xm + wm / 2) * ppm
    Y = lambda ym: h - ym * ppm
    glow = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(glow)
    # walls
    x = -wm / 2 + r.uniform(0, 8)
    poles = []
    while x < wm / 2:
        bw = r.uniform(6, 24)
        if r.random() < 0.72:
            bh = r.uniform(5, 30) * (1.4 if r.random() < 0.2 else 1.0)
            n = max(3, int(bw / 1.1))
            prof = []
            hb = bh * r.uniform(0.25, 0.7)
            peak = r.uniform(0, 1)
            for i in range(n + 1):
                u = i / n
                yy = hb + (bh - hb) * max(0.0, 1 - abs(u - peak) * r.uniform(1.2, 2.5)) + r.uniform(-0.8, 0.8)
                prof.append((x + bw * u, max(yy, 1.5)))
            c = int(r.uniform(36, 56))
            col = (c, int(c * 0.84), int(c * 0.76), 255)
            d.polygon([(X(x), h)] + [(X(px), Y(py)) for px, py in prof] + [(X(x + bw), h)], fill=col)
            # windows
            for wy in np.arange(1.8, bh, 3.3):
                for wx in np.arange(x + 1.2, x + bw - 1.4, 2.7):
                    i = int((wx - x) / bw * n)
                    if wy + 2.2 > prof[min(i, n)][1] - 0.4 or r.random() < 0.25:
                        continue
                    rr = r.random()
                    if rr < 0.55:
                        fill = (0, 0, 0, 0)
                    elif rr < 0.93:
                        fill = (8, 5, 5, 255)
                    else:
                        fill = (230, 95, 25, 255)
                        gd.ellipse([X(wx - 2), Y(wy + 4), X(wx + 3.2), Y(wy - 2)], fill=150)
                    d.rectangle([X(wx), Y(wy + 1.7), X(wx + 1.2), Y(wy)], fill=fill)
            # rebar
            for _ in range(int(r.uniform(2, 7))):
                px, py = prof[int(r.integers(0, n + 1))]
                d.line([X(px), Y(py), X(px + r.uniform(-1.5, 1.5)), Y(py + r.uniform(0.8, 3.0))],
                       fill=(30, 22, 20, 255), width=max(1, int(0.08 * ppm)))
        elif r.random() < 0.5:
            poles.append(x + bw / 2)
        x += bw + r.uniform(1, 12)
    # poles + sagging wires
    tops = []
    for px in poles:
        lean = r.uniform(-2.5, 2.5)
        ph = r.uniform(8, 12)
        d.line([X(px), h, X(px + lean), Y(ph)], fill=(22, 17, 15, 255), width=max(2, int(0.3 * ppm)))
        d.line([X(px + lean - 1.2), Y(ph - 0.8), X(px + lean + 1.2), Y(ph - 0.6)], fill=(22, 17, 15, 255), width=max(1, int(0.15 * ppm)))
        tops.append((px + lean, ph - 0.7))
    for (a, b) in zip(tops[:-1], tops[1:]):
        if b[0] - a[0] > 45:
            continue
        pts = []
        for i in range(25):
            u = i / 24
            xx = a[0] + (b[0] - a[0]) * u
            yy = a[1] + (b[1] - a[1]) * u - 4 * u * (1 - u) * r.uniform(1.0, 2.5)
            pts.append((X(xx), Y(yy)))
        d.line(pts, fill=(18, 14, 13, 255), width=1)
    # burnt cars
    for _ in range(int(r.uniform(3, 7))):
        cx0 = r.uniform(-wm / 2, wm / 2)
        cy0 = r.uniform(0.6, 2.0)
        col = (26, 20, 19, 255)
        d.rounded_rectangle([X(cx0), Y(cy0 + 1.0), X(cx0 + 4.4), Y(cy0)], radius=int(0.3 * ppm), fill=col)
        d.polygon([(X(cx0 + 1.0), Y(cy0 + 1.0)), (X(cx0 + 1.5), Y(cy0 + 1.6)), (X(cx0 + 3.2), Y(cy0 + 1.6)), (X(cx0 + 3.7), Y(cy0 + 1.0))], fill=col)
    # rubble strip (continuous so nothing floats)
    n = int(wm / 0.5)
    hgt = np.convolve(r.standard_normal(n + 40), np.ones(14) / 14, "same")[20:20 + n + 1]
    hgt = 1.6 + 3.2 * (hgt - hgt.min()) / (np.ptp(hgt) + 1e-6) * r.uniform(0.6, 1.0)
    pts = [(X(-wm / 2), h)] + [(X(-wm / 2 + i * 0.5), Y(hgt[i] + r.uniform(-0.25, 0.25))) for i in range(n + 1)] + [(X(wm / 2), h)]
    d.polygon(pts, fill=(30, 25, 23, 255))
    for _ in range(int(wm * 0.6)):  # chunks
        cx0 = r.uniform(-wm / 2, wm / 2)
        i = int((cx0 + wm / 2) / 0.5)
        cy0 = hgt[min(i, n)]
        s = r.uniform(0.3, 1.4)
        poly = [(X(cx0 + s * math.cos(a)), Y(cy0 + s * 0.6 * math.sin(a) + 0.1)) for a in np.sort(r.uniform(0, 2 * np.pi, 6))]
        cc = int(r.uniform(26, 46))
        d.polygon(poly, fill=(cc, int(cc * 0.86), int(cc * 0.8), 255))
    # small fires in the rubble
    for _ in range(int(r.uniform(2, 6))):
        fx = r.uniform(-wm / 2, wm / 2)
        i = int((fx + wm / 2) / 0.5)
        fy = hgt[min(i, n)]
        for k in range(5):
            s = r.uniform(0.3, 0.8)
            d.ellipse([X(fx + k * 0.4 - s), Y(fy + s * 1.6), X(fx + k * 0.4 + s), Y(fy - 0.2)], fill=(255, int(r.uniform(90, 160)), 30, 255))
        gd.ellipse([X(fx - 6), Y(fy + 7), X(fx + 8), Y(fy - 3)], fill=200)
    glow = np.asarray(glow.filter(ImageFilter.GaussianBlur(2.2 * ppm)), np.float32) / 255.0

    def extra(rgb, A):
        g = glow[..., None]
        rgb = rgb * (1 + g * np.array([2.0, 0.7, 0.2])) + g * np.array([0.9, 0.32, 0.08]) * 0.7
        A = np.maximum(A, np.clip(glow * 0.7, 0, 1))
        return rgb, A

    return _finish(im, (1.0, 0.36, 0.15), 0.85, 3, sides=0.45, extra=extra)


def draw_pine(d, X, Y, xm, hgt, ppm, r, col):
    trunk_w = max(1, int(hgt * 0.025 * ppm))
    d.line([X(xm), Y(0), X(xm), Y(hgt)], fill=col, width=trunk_w)
    maxw = hgt * r.uniform(0.17, 0.26)
    yb = hgt * r.uniform(0.12, 0.3)
    tier = hgt * r.uniform(0.07, 0.11)
    n = max(10, int((hgt - yb) * ppm / 3))
    left, right = [], []
    for i in range(n + 1):
        y = yb + (hgt - yb) * i / n
        f = max(0.0, 1 - (y - yb) / (hgt - yb))
        saw = 0.72 + 0.28 * (((y - yb) / tier) % 1.0)
        wv = maxw * f ** 0.95 * saw
        left.append((X(xm - wv * r.uniform(0.6, 1.2)), Y(y - r.uniform(0, tier * 0.35))))
        right.append((X(xm + wv * r.uniform(0.6, 1.2)), Y(y - r.uniform(0, tier * 0.35))))
    d.polygon(left + right[::-1], fill=col)


def draw_dead_tree(d, X, Y, xm, hgt, ppm, r, col):
    def br(x0, y0, ang, ln, wdt, depth):
        x1 = x0 + math.cos(ang) * ln
        y1 = y0 + math.sin(ang) * ln
        d.line([X(x0), Y(y0), X(x1), Y(y1)], fill=col, width=max(1, int(wdt * ppm)))
        if depth > 0:
            for _ in range(2):
                br(x1, y1, ang + r.uniform(-0.7, 0.7), ln * r.uniform(0.55, 0.75), wdt * 0.6, depth - 1)
    br(xm, 0, math.pi / 2 + r.uniform(-0.1, 0.1), hgt * 0.45, hgt * 0.03, 4)


def build_forest(seed, wm, hm, ppm, xc=0.0, hmin=10, hmax=24, spacing=(1.2, 3.5),
                 excl=None, strip=True, dead=0.08, rim=0.45, base=(12, 15, 12)):
    r = np.random.default_rng(seed)
    im, d, w, h = _canvas(wm, hm, ppm)
    X = lambda xm: (xm - xc + wm / 2) * ppm
    Y = lambda ym: h - ym * ppm
    x = xc - wm / 2 + r.uniform(0, 2)
    while x < xc + wm / 2:
        if excl is None or not excl(x):
            hh = r.uniform(hmin, hmax)
            v = r.uniform(0.8, 1.3)
            col = tuple(int(c * v) for c in base) + (255,)
            if r.random() < dead:
                draw_dead_tree(d, X, Y, x, hh * 0.8, ppm, r, (20, 16, 14, 255))
            else:
                draw_pine(d, X, Y, x, hh, ppm, r, col)
        x += r.uniform(*spacing)
    if strip:
        for _ in range(int(wm * 1.5)):
            bx = r.uniform(xc - wm / 2, xc + wm / 2)
            if excl is not None and excl(bx):
                continue
            s = r.uniform(0.6, 2.0)
            d.ellipse([X(bx - s * 1.4), Y(s * 1.1), X(bx + s * 1.4), Y(-s * 0.4)], fill=(10, 12, 9, 255))
    return _finish(im, (0.95, 0.30, 0.13), rim, max(2, int(0.12 * ppm)), sides=0.3, vgrad=(0.8, 1.25))


def build_grass(seed, wm, hm, ppm, xc):
    r = np.random.default_rng(seed)
    im, d, w, h = _canvas(wm, hm, ppm)
    X = lambda xm: (xm - xc + wm / 2) * ppm
    Y = lambda ym: h - ym * ppm
    for _ in range(int(wm * 140)):
        bx = r.uniform(xc - wm / 2, xc + wm / 2)
        gap = 0.55 < bx < 2.0
        hh = r.uniform(0.04, 0.12) if gap else r.uniform(0.08, 0.40)
        bend = r.uniform(-0.12, 0.12)
        wb = r.uniform(0.006, 0.014)
        pts = [(X(bx - wb), Y(-0.02)), (X(bx + bend * 0.5), Y(hh * 0.6)), (X(bx + bend), Y(hh)),
               (X(bx + bend * 0.5 + wb * 0.4), Y(hh * 0.6)), (X(bx + wb), Y(-0.02))]
        c = int(r.uniform(6, 16))
        d.polygon(pts, fill=(c, c + 2, int(c * 0.8), 255))
    # fire-facing rim (fire is up-right of the strip)
    return _finish(im, (1.0, 0.45, 0.15), 0.35, 2, sides=0.25, vgrad=(0.6, 1.0))


def build_fire_base(ppm=260):
    wm, hm = 1.0, 1.25
    im, d, w, h = _canvas(wm, hm, ppm)
    X = lambda xm: (xm + wm / 2) * ppm
    Y = lambda ym: h - ym * ppm
    r = np.random.default_rng(3)
    # logs
    for a, b, c in (((-0.32, 0.02), (0.22, 0.20), 0), ((0.30, 0.03), (-0.18, 0.22), 1), ((-0.05, 0.0), (0.05, 0.26), 2)):
        d.line([X(a[0]), Y(a[1]), X(b[0]), Y(b[1])], fill=(34, 20, 12, 255), width=int(0.075 * ppm))
    # glowing embers bed
    for _ in range(60):
        ex, ey = r.normal(0, 0.12), abs(r.normal(0.04, 0.03))
        s = r.uniform(0.01, 0.03)
        d.ellipse([X(ex - s), Y(ey + s), X(ex + s), Y(ey - s)], fill=(255, int(r.uniform(80, 170)), 20, 255))
    # stone ring (front arc)
    for i in range(9):
        ang = math.pi * (0.05 + 0.9 * i / 8)
        sx = -math.cos(ang) * 0.42
        sy = 0.0 + 0.02 * math.sin(ang)
        s = r.uniform(0.07, 0.1)
        c = int(r.uniform(40, 60))
        d.ellipse([X(sx - s), Y(sy + s * 1.1), X(sx + s), Y(sy - s * 0.2)], fill=(c, int(c * 0.88), int(c * 0.8), 255))
    a = np.asarray(im, np.float32) / 255.0
    rgb, A = a[..., :3], a[..., 3]
    # top lighting from flames
    rgb = rim_light(rgb, A, (1.0, 0.5, 0.18), 0.9, 5)
    return to_rgba_img(rgb, A)


# --------------------------------------------------------------------------
# Scene assembly
# --------------------------------------------------------------------------
TENT_X, TENT_Z = -0.45, 420.0
FIRE_X, FIRE_Z = 1.25, 418.8
LAYERS = []


def build_scene():
    global LAYERS, FIRE_BASE
    L = []
    L.append(Layer(build_city(101, 4400, 380, 1.0, 120, 360, (30, 13, 13), fires=8), -2200, 4400, 380, 2300, fogk=0.75, name="city2"))
    L.append(Layer(build_city(102, 3600, 440, 1.6, 140, 430, (14, 6, 7), fires=14), -1800, 3600, 440, 1300, fogk=0.45, name="city1"))
    for i, z in enumerate([30, 55, 80, 105, 130, 155, 180, 205, 230, 255, 280, 302]):
        L.append(Layer(build_ruins(200 + i), -150, 300, 46, z, name=f"ruins{z}"))
    # transition: dead trees between ruins and forest
    L.append(Layer(build_forest(299, 300, 20, 16, hmin=7, hmax=15, spacing=(3, 9), dead=0.85, base=(18, 15, 13)), -150, 300, 20, 318, name="dead"))
    for i, z in enumerate([330, 342, 354, 366, 378]):
        L.append(Layer(build_forest(300 + i, 300, 26, 16, hmin=11, hmax=25, spacing=(1.0, 2.8), dead=0.04), -150, 300, 26, z, name=f"forest{z}"))
    # clearing: side trees passing by the camera, background rows
    side = lambda lim: (lambda x: abs(x) < lim)
    for i, (z, lim) in enumerate([(398, 4.5), (404, 4.6), (411, 4.4)]):
        L.append(Layer(build_forest(400 + i, 50, 24, 36, hmin=13, hmax=22, spacing=(1.2, 2.6), excl=side(lim), strip=False, dead=0.05, rim=0.12),
                       -25, 50, 24, z, name=f"side{z}"))
    L.append(Layer(build_forest(410, 80, 24, 30, hmin=12, hmax=21, spacing=(1.0, 2.2), excl=side(6.0), strip=False, dead=0.04, rim=0.25), -40, 80, 24, 432, name="bg432"))
    L.append(Layer(build_forest(411, 120, 24, 24, hmin=12, hmax=22, spacing=(1.0, 2.6), excl=side(9.0), strip=False, dead=0.06, rim=0.35), -60, 120, 24, 458, name="bg458"))
    L.append(Layer(build_forest(412, 200, 24, 16, hmin=10, hmax=20, spacing=(0.9, 2.4), excl=lambda x: abs(x) < 14, dead=0.06), -100, 200, 24, 520, name="bg520"))
    L.append(Layer(build_forest(413, 400, 22, 10, hmin=9, hmax=18, spacing=(1.0, 3.0), dead=0.05), -200, 400, 22, 640, name="bg640"))
    L.append(Layer(build_grass(500, 7.0, 0.45, 200, 0.4), 0.4 - 3.5, 7.0, 0.45, 416.6, name="grass"))
    L.sort(key=lambda l: -l.z)
    LAYERS = L
    FIRE_BASE = build_fire_base()


FIRE_BASE = None

# plumes: (world x, world z, base height, base width, strength, rise speed)
PLUMES = [
    (-950, 1300, 120, 30, 0.85, 9.0), (-420, 1300, 200, 40, 0.9, 8.0), (-60, 1300, 90, 26, 0.7, 10.0),
    (380, 1300, 160, 34, 0.9, 7.0), (820, 1300, 240, 38, 0.8, 9.0), (-260, 2300, 160, 45, 0.6, 7.0),
    (60, 190, 6, 4, 0.75, 2.2), (-70, 240, 8, 5, 0.7, 2.6), (35, 120, 4, 3, 0.65, 2.0),
]


# --------------------------------------------------------------------------
# Per-frame drawing
# --------------------------------------------------------------------------
def fog_amount(dz, k=1.0):
    return min(0.82, 0.82 * (1 - math.exp(-dz / 600.0)) * k)


def draw_billboard(canvas, cov, img, xl, yb, wm, hm, z, cam, fogk=1.0, mode="over", tint=None):
    dz = z - cam.cz
    if dz < 0.35:
        return None
    s = F / dz
    sx0 = W / 2 + (xl - cam.cx) * s
    sx1 = sx0 + wm * s
    syT = cam.hor - (yb + hm - cam.cy) * s
    syB = cam.hor - (yb - cam.cy) * s
    X0, X1 = max(0, int(math.floor(sx0))), min(W, int(math.ceil(sx1)))
    Y0, Y1 = max(0, int(math.floor(syT))), min(H, int(math.ceil(syB)))
    if X1 <= X0 or Y1 <= Y0:
        return None
    iw, ih = img.size
    box = ((X0 - sx0) / (sx1 - sx0) * iw, (Y0 - syT) / (syB - syT) * ih,
           (X1 - sx0) / (sx1 - sx0) * iw, (Y1 - syT) / (syB - syT) * ih)
    box = (min(max(box[0], 0.0), iw), min(max(box[1], 0.0), ih), min(max(box[2], 0.0), iw), min(max(box[3], 0.0), ih))
    if box[2] - box[0] < 1e-3 or box[3] - box[1] < 1e-3:
        return None
    patch = img.resize((X1 - X0, Y1 - Y0), Image.BILINEAR, box=box)
    p = np.asarray(patch, np.float32) / 255.0
    reg = canvas[Y0:Y1, X0:X1]
    if mode == "add":
        reg += p[..., :3]
        return (X0, Y0, X1, Y1)
    rgb, a = p[..., :3], p[..., 3:4]
    if tint is not None:
        rgb = rgb * tint
    fg = fog_amount(dz, fogk)
    if fg > 0.001:
        rgb = rgb * (1 - fg) + FOG_COL * fg * a
    reg *= (1 - a)
    reg += rgb
    c = cov[Y0:Y1, X0:X1]
    c *= (1 - a[..., 0])
    c += a[..., 0]
    return (X0, Y0, X1, Y1)


def fire_flicker(t):
    return (0.86 + 0.07 * math.sin(13.1 * t) + 0.05 * math.sin(29.3 * t + 1.3)
            + 0.04 * math.sin(7.7 * t + 0.4) + 0.03 * math.sin(41.0 * t + 2.2))


def render_sky(cam, t):
    h2, w2 = H // 2, W // 2
    sy = (np.arange(h2) + 0.5) * (H / h2)
    sx = (np.arange(w2) + 0.5) * (W / w2)
    dy = (cam.hor - sy)[:, None]
    up = np.clip(dy / H, 0, None)
    top = np.array([14, 3, 5], np.float32) / 255
    mid = np.array([100, 15, 11], np.float32) / 255
    hz = np.array([228, 80, 32], np.float32) / 255
    base = top + (mid - top) * np.exp(-up / 0.30)[..., None]
    k = np.exp(-up / 0.055)[..., None]
    col = np.broadcast_to(base + (hz - base) * k, (h2, w2, 3)).copy()
    # perspective cloud deck 900 m above the camera
    dyc = np.maximum(dy, 1.0)
    D = np.minimum(900.0 * F / dyc, 40000.0)
    Zc = cam.cz + D + t * 8.0
    Xc = cam.cx + (sx[None, :] - W / 2) * D / F + t * 30.0
    n1 = samp(NOISE, Zc * 0.16, Xc * 0.16)
    n2 = samp(NOISE, Zc * 0.53 + 77, Xc * 0.53 + 31)
    n = 0.62 * n1 + 0.38 * n2
    c = smoothstep(0.40, 0.72, n) * smoothstep(0.0, 0.10, up) * 0.92
    under = np.exp(-up / 0.22)
    cl = (np.array([34, 8, 8], np.float32) / 255
          + (np.array([175, 52, 22], np.float32) / 255) * (under * (0.35 + 0.65 * (1 - n)))[..., None])
    col = col * (1 - c[..., None]) + cl * c[..., None]
    # lightning illumination of the cloud deck
    for t0, amp, bx, _, _ in STRIKES:
        e = flash_env(t, t0) * amp
        if e < 0.003:
            continue
        spread = np.exp(-((sx[None, :] / W - bx) / 0.6) ** 2)
        col += (e * (0.25 + 1.1 * c) * spread)[..., None] * np.array([0.66, 0.62, 0.80], np.float32)
    return up_rgb(col, (W, H))


def draw_bolts(sky, cam, t):
    for t0, amp, bx, bolt, seed in STRIKES:
        if not bolt:
            continue
        e = flash_env(t, t0)
        if e < 0.02:
            continue
        L = Image.new("L", (W, H), 0)
        Gm = Image.new("L", (W // 2, H // 2), 0)
        d, g = ImageDraw.Draw(L), ImageDraw.Draw(Gm)
        y0 = cam.hor - 0.62 * H
        y1 = cam.hor - 0.05 * H
        for segs, wgt in BOLTS[seed]:
            for (p0, p1) in segs:
                a = (W * (bx + p0[0] * 0.9), y0 + (y1 - y0) * p0[1])
                b = (W * (bx + p1[0] * 0.9), y0 + (y1 - y0) * p1[1])
                d.line([a, b], fill=int(255 * wgt), width=max(1, int(3 * S * wgt + 0.5)))
                g.line([(a[0] / 2, a[1] / 2), (b[0] / 2, b[1] / 2)], fill=int(255 * wgt), width=max(1, int(5 * S)))
        core = np.asarray(L, np.float32) / 255
        glow = np.asarray(Gm.filter(ImageFilter.GaussianBlur(14 * S)).resize((W, H), Image.BILINEAR), np.float32) / 255
        ee = min(1.0, e)
        sky += (core * ee * 1.4)[..., None] * np.array([0.95, 0.95, 1.0], np.float32)
        sky += (glow * ee * 1.6 * amp)[..., None] * np.array([0.6, 0.6, 1.0], np.float32)


def render_ground(cam, t, fireI):
    h2, w2 = H // 2, W // 2
    sy = (np.arange(h2) + 0.5) * (H / h2)
    sx = (np.arange(w2) + 0.5) * (W / w2)
    dy = sy - cam.hor
    rows = np.where(dy > 0.25)[0]
    rgb = np.zeros((h2, w2, 3), np.float32)
    alpha = np.zeros((h2, w2), np.float32)
    if len(rows) == 0:
        return up_rgb(rgb, (W, H)), up_f(alpha, (W, H))
    r0 = rows[0]
    D = (cam.cy * F / dy[r0:])[:, None].astype(np.float32)
    D = np.minimum(D, 20000.0)
    Z = cam.cz + D
    Xw = cam.cx + (sx[None, :] - W / 2) * D / F
    tex = samp(NOISE, Z * 0.30, Xw * 0.30)
    det = samp(NOISE2, Z * 2.6, Xw * 2.6)
    fine = samp(NOISE2, Z * 23.0 + 9, Xw * 23.0 + 3)
    fnear = np.exp(-D / 6.0)
    det = det * (1 - 0.6 * fnear) + fine * 0.6 * fnear
    fd = np.exp(-D / 60.0)
    zone = smoothstep(305.0, 335.0, Z)
    ruins = (np.array([60, 49, 45], np.float32) / 255) * (0.55 + 0.9 * tex + 0.5 * (det - 0.5) * fd)[..., None]
    ash = smoothstep(0.55, 0.7, tex)[..., None] * np.array([0.10, 0.09, 0.09], np.float32)
    forest = (np.array([27, 24, 17], np.float32) / 255) * (0.6 + 0.8 * tex + 0.6 * (det - 0.5) * fd)[..., None]
    col = (ruins + ash) * (1 - zone[..., None]) + forest * zone[..., None]
    # clearing: dirt patch around camp
    clr = np.exp(-(((Xw - 0.4) / 5.0) ** 2 + ((Z - 420.0) / 8.0) ** 2))
    pebble = smoothstep(0.62, 0.7, fine) * fnear
    dirt = (np.array([52, 38, 27], np.float32) / 255) * (0.45 + 1.1 * det)[..., None]
    dirt = dirt * (1 - pebble[..., None]) + np.array([0.30, 0.27, 0.25], np.float32) * pebble[..., None]
    col = col * (1 - clr[..., None]) + dirt * clr[..., None]
    # light: red sky ambient + campfire
    amb = np.array([0.95, 0.55, 0.5], np.float32) * (0.75 - 0.35 * smoothstep(380.0, 420.0, cam.cz))
    light = np.broadcast_to(amb, col.shape).copy()
    if fireI > 0:
        d2 = (Xw - FIRE_X) ** 2 + (Z - FIRE_Z) ** 2
        fl = fireI * 3.2 / (1 + d2 * 1.3)
        light += fl[..., None] * np.array([1.0, 0.52, 0.2], np.float32)
        # contact shadow of the tent
        ao = np.exp(-(((Xw - TENT_X) / 1.25) ** 2 + ((Z - TENT_Z - 0.4) / 0.9) ** 2) ** 2)
        light *= (1 - 0.6 * ao)[..., None]
        # warm spill of the flashlight through the tent floor edge
        sp = np.exp(-(((Xw - TENT_X) / 1.3) ** 2 + ((Z - TENT_Z + 0.4) / 0.5) ** 2))
        light += (0.35 * sp)[..., None] * np.array([1.0, 0.7, 0.35], np.float32)
    col = col * light
    fog = (0.82 * (1 - np.exp(-D / 600.0)))
    col = col * (1 - fog[..., None]) + FOG_COL * fog[..., None]
    rgb[r0:] = col
    alpha[r0:] = 1.0
    alpha[max(r0 - 1, 0)] = np.clip(cam.hor - sy[max(r0 - 1, 0)], 0, 1)
    return up_rgb(rgb, (W, H)), up_f(alpha, (W, H))


_QG = None


def quarter_grid():
    global _QG
    if _QG is None or _QG[0].shape != (H // 4, W // 4):
        sy = (np.arange(H // 4) + 0.5) * 4.0
        sx = (np.arange(W // 4) + 0.5) * 4.0
        _QG = np.meshgrid(sx, sy)
    return _QG


def draw_plume(canvas, cov, cam, t, pl):
    xw, zw, base, w0, strength, rise = pl
    dz = zw - cam.cz
    if dz < 25:
        return
    s = F / dz
    SX, SY = quarter_grid()
    Xp = cam.cx + (SX - W / 2) / s
    Yp = cam.cy + (cam.hor - SY) / s
    hgt = Yp - base
    wind = 0.004 * np.clip(hgt, 0, None) ** 1.25 * (w0 / 30.0) ** 0.3
    width = w0 * 0.6 + 0.32 * hgt
    m = np.exp(-((Xp - xw - wind) / np.maximum(width, 1e-3)) ** 2)
    m *= smoothstep(-w0 * 0.3, w0 * 0.6, hgt) * np.exp(-np.clip(hgt, 0, None) / (w0 * 14.0))
    sc = 512.0 / (w0 * 9.0)
    nn = samp(NOISE, (Yp - t * rise) * sc + xw, (Xp - wind) * sc + zw)
    a = np.clip(strength * 1.3 * m * smoothstep(0.25, 0.65, nn), 0, 0.95)
    if a.max() < 0.01:
        return
    glow = np.exp(-np.clip(hgt, 0, None) / (w0 * 2.5))
    col = (np.array([30, 22, 22], np.float32) / 255)[None, None] + (glow * 0.8)[..., None] * np.array([0.55, 0.16, 0.06], np.float32)
    fg = fog_amount(dz, 0.45)
    col = col * (1 - fg) + FOG_COL * fg
    A = up_f(a.astype(np.float32), (W, H))[..., None]
    C = up_rgb(col.astype(np.float32), (W, H))
    canvas *= (1 - A)
    canvas += C * A
    cov *= (1 - A[..., 0])
    cov += A[..., 0]


def draw_haze(canvas, cov, cam, t, strength):
    if strength < 0.01:
        return
    SX, SY = quarter_grid()
    rel = (SY - cam.hor) / H
    band = np.exp(-((rel + 0.02) / 0.16) ** 2)
    n = samp(NOISE, SY * 0.12 + cam.cz * 0.2, SX * 0.08 + t * 6.0 + cam.cz * 0.5)
    a = strength * band * smoothstep(0.35, 0.8, n)
    col = np.array([92, 38, 30], np.float32) / 255
    A = up_f(a.astype(np.float32), (W, H))[..., None]
    canvas *= (1 - A)
    canvas += col * A
    cov *= (1 - A[..., 0])
    cov += A[..., 0]


def person_pose(t):
    raise_ = ease((t - 20.15) / 0.75) * (1 - ease((t - 21.95) / 0.85))
    bob = 0.006 * math.sin(t * 1.5)
    return raise_, bob


_TENT_STATIC = None


def tent_static(ppm):
    global _TENT_STATIC
    if _TENT_STATIC is not None and _TENT_STATIC[0] == ppm:
        return _TENT_STATIC[1]
    wm, hm = 3.4, 1.5
    w, h = int(wm * ppm), int(hm * ppm)
    xs = (np.arange(w) + 0.5) / ppm - wm / 2
    ys = hm - (np.arange(h) + 0.5) / ppm
    Xg, Yg = np.meshgrid(xs, ys)
    ax = np.clip(np.abs(Xg) / 1.15, 0, 1)
    ytop = np.where(np.abs(Xg) < 1.15, 1.35 * (1 - ax ** 2.0) ** 0.62, -1.0)
    body = np.clip((ytop - Yg) * ppm + 0.5, 0, 1) * (Yg >= 0)
    edge_d = ytop - Yg
    rim = np.exp(-np.clip(edge_d, 0, None) / 0.025) * body
    door_top = np.where(np.abs(Xg) < 0.52, 1.0 * np.sqrt(np.clip(1 - (Xg / 0.52) ** 2, 0, 1)), -1)
    door = (Yg < door_top) & (Yg > 0.1)
    zip_ = np.exp(-((Yg - door_top) / 0.008) ** 2) * (np.abs(Xg) < 0.52) * (Yg > 0.1)
    floor = (Yg < 0.1).astype(np.float32)
    folds = 1 + 0.05 * np.sin(Xg * 9 + Yg * 5) + 0.04 * np.sin(Xg * 23 - Yg * 11)
    # inner flashlight glow distribution
    G = np.exp(-(((Xg - 0.12) ** 2) / 0.45 + ((Yg - 0.78) ** 2) / 0.32))
    G += 1.4 * np.exp(-(((Xg - 0.28) ** 2) + ((Yg - 0.98) ** 2)) / 0.012)
    trans = (0.85 + 0.15 * door) * (1 - 0.7 * floor) * (1 - 0.6 * rim)
    side = np.clip(0.5 + 0.5 * Xg / 1.15, 0, 1)
    r = np.random.default_rng(9)
    ash_rand = r.random((h, w)).astype(np.float32)
    ash_dens = smoothstep(0.35, 1.3, Yg) * body
    # guy lines and stakes
    gl = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(gl)
    P = lambda x, y: ((x + wm / 2) * ppm, (hm - y) * ppm)
    for sgn in (-1, 1):
        gd.line([P(sgn * 0.88, 1.02), P(sgn * 1.62, 0.0)], fill=200, width=max(1, int(ppm / 220)))
        gd.line([P(sgn * 1.12, 0.35), P(sgn * 1.45, 0.0)], fill=160, width=max(1, int(ppm / 250)))
        gd.polygon([P(sgn * 1.62 - 0.012, 0.06), P(sgn * 1.62 + 0.012, 0.06), P(sgn * 1.62, -0.02)], fill=255)
    guy = np.asarray(gl, np.float32) / 255
    st = dict(w=w, h=h, wm=wm, hm=hm, X=Xg, Y=Yg, body=body, rim=rim, door=door, zip=zip_, floor=floor,
              folds=folds, G=G, trans=trans, side=side, ash_rand=ash_rand, ash_dens=ash_dens, guy=guy)
    _TENT_STATIC = (ppm, st)
    return st


def person_mask(st, ppm, t):
    """Silhouette of a seated person holding a mug, in tent texture space."""
    sc = 0.5
    w, h = int(st["w"] * sc), int(st["h"] * sc)
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    P = lambda x, y: ((x + st["wm"] / 2) * ppm * sc, (st["hm"] - y) * ppm * sc)
    R = lambda m: m * ppm * sc
    a, bob = person_pose(t)
    lerp = lambda p, q: (p[0] + (q[0] - p[0]) * a, p[1] + (q[1] - p[1]) * a)
    # body
    torso = [(-0.52, 0.08), (-0.50, 0.30), (-0.45, 0.52), (-0.40, 0.64 + bob), (-0.24, 0.67 + bob),
             (-0.16, 0.56 + bob), (-0.12, 0.38), (-0.05, 0.16), (-0.02, 0.08)]
    d.polygon([P(*p) for p in torso], fill=255)
    # legs (knees up)
    d.line([P(-0.25, 0.14), P(0.07, 0.40), P(0.22, 0.08)], fill=255, width=int(R(0.13)), joint="curve")
    d.ellipse([P(0.15, 0.13)[0], P(0.15, 0.13)[1], P(0.30, 0.04)[0], P(0.30, 0.04)[1]], fill=255)
    # head (tilts back while sipping) + beanie
    hc = (-0.26 - 0.015 * a, 0.80 + bob + 0.01 * a)
    hr = 0.10
    d.ellipse([P(hc[0] - hr, hc[1] + hr), P(hc[0] + hr, hc[1] - hr)], fill=255)
    d.polygon([P(hc[0] + 0.07, hc[1] + 0.02), P(hc[0] + 0.125, hc[1] - 0.015), P(hc[0] + 0.08, hc[1] - 0.045)], fill=255)  # nose
    d.ellipse([P(hc[0] - 0.095, hc[1] + 0.135), P(hc[0] + 0.07, hc[1] + 0.03)], fill=255)  # beanie
    d.ellipse([P(hc[0] - 0.05, hc[1] + 0.175), P(hc[0] + 0.0, hc[1] + 0.125)], fill=255)  # pompom
    d.line([P(-0.28, 0.66 + bob), P(hc[0], hc[1] - 0.05)], fill=255, width=int(R(0.09)))  # neck
    # arm with mug
    sh = (-0.30, 0.60 + bob)
    el = lerp((-0.14, 0.40), (-0.12, 0.55 + bob))
    hd = lerp((0.03, 0.50), (hc[0] + 0.10, hc[1] - 0.04))
    d.line([P(*sh), P(*el), P(*hd)], fill=255, width=int(R(0.075)), joint="curve")
    ang = 0.75 * a  # mug tilts toward the mouth
    ca, sa = math.cos(ang), math.sin(ang)
    mug = [(-0.035, -0.04), (0.04, -0.04), (0.04, 0.055), (-0.035, 0.055)]
    cxm, cym = hd[0] + 0.035, hd[1] + 0.01
    pts = [P(cxm + x * ca - y * sa, cym + x * sa + y * ca) for x, y in mug]
    d.polygon(pts, fill=255)
    hcx, hcy = cxm - 0.05 * ca, cym - 0.05 * sa + 0.01
    d.ellipse([P(hcx - 0.025, hcy + 0.025), P(hcx + 0.015, hcy - 0.02)], outline=255, width=max(1, int(R(0.012))))
    # faint steam curling from the mug while resting
    steam = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(steam)
    if a < 0.5:
        for k in range(2):
            pts = []
            for i in range(14):
                yy = cym + 0.07 + i * 0.018
                xx = cxm - 0.01 + k * 0.025 + 0.018 * math.sin(i * 0.7 + t * 2.2 + k * 2)
                pts.append(P(xx, yy))
            sd.line(pts, fill=int(110 * (1 - a * 2)), width=max(1, int(R(0.01))))
    m = np.asarray(im.filter(ImageFilter.GaussianBlur(R(0.012))), np.float32) / 255
    sm = np.asarray(steam.filter(ImageFilter.GaussianBlur(R(0.01))), np.float32) / 255
    m = np.maximum(m, sm * 0.5)
    return np.asarray(Image.fromarray(m, "F").resize((st["w"], st["h"]), Image.BILINEAR))


def tent_image(t, fireI, flash, ppm):
    st = tent_static(ppm)
    S_ = person_mask(st, ppm, t)
    body, Y = st["body"], st["Y"]
    albedo = np.array([0.50, 0.25, 0.10], np.float32)
    amb = (np.array([0.20, 0.07, 0.06], np.float32)[None, None] * (0.7 + 0.5 * Y / 1.35)[..., None])
    fire = (fireI * 1.15 * st["side"] ** 1.4)[..., None] * np.array([1.0, 0.5, 0.2], np.float32)
    fl = flash * np.array([0.55, 0.6, 0.85], np.float32)
    light = amb + fire + fl
    col = albedo * light * st["folds"][..., None]
    Lin = 0.95 + 0.03 * math.sin(t * 1.3)
    Geff = st["G"] * (1 - 0.88 * S_) * st["trans"] * Lin
    col += Geff[..., None] * np.array([1.0, 0.64, 0.30], np.float32) * 1.05
    col *= (1 - 0.55 * st["zip"])[..., None]
    col *= (1 - 0.35 * st["floor"])[..., None]
    # rim from the red sky / lightning
    col += st["rim"][..., None] * (np.array([0.35, 0.10, 0.05], np.float32) + flash * np.array([0.8, 0.85, 1.0], np.float32))
    # ash accumulating on the fabric
    acc = 0.02 + 0.10 * smoothstep(13.0, 24.0, t)
    ashm = ((st["ash_rand"] < acc * st["ash_dens"]) * body).astype(np.float32)
    ashc = np.array([0.55, 0.52, 0.5], np.float32) * (light * 1.2 + 0.05)
    col = col * (1 - 0.85 * ashm[..., None]) + ashc * 0.85 * ashm[..., None]
    # guy lines (catch firelight)
    g = st["guy"]
    gcol = np.array([0.25, 0.14, 0.09], np.float32) + fireI * 0.35 * np.array([1, 0.5, 0.2], np.float32) + flash * 0.6
    col = col * (1 - g[..., None]) + gcol * g[..., None]
    A = np.maximum(body, g)
    return to_rgba_img(col, A)


def fire_flames(t, ppm=260):
    wm, hm = 1.0, 1.25
    w, h = int(wm * ppm), int(hm * ppm)
    xs = (np.arange(w) + 0.5) / ppm - wm / 2
    ys = hm - (np.arange(h) + 0.5) / ppm
    Xg, Yg = np.meshgrid(xs, ys)
    v = (Yg - 0.06) / 0.85
    u = Xg / 0.42
    u = u + 0.18 * np.clip(v, 0, 1) ** 1.5 * math.sin(t * 2.1) + 0.06 * np.clip(v, 0, 1) * math.sin(t * 5.3 + 1)
    vc = np.clip(v, 0, 1)
    halfw = 0.75 * (1 - vc) ** 0.65 + 0.04
    core = np.clip(1 - (u / halfw) ** 2, 0, 1) * (1 - vc) ** 0.6 * (v > -0.05)
    n1 = samp(NOISE2, Yg * 70 - t * 95, Xg * 70)
    n2 = samp(NOISE2, Yg * 160 - t * 210 + 50, Xg * 160 + 20)
    turb = 0.65 * n1 + 0.35 * n2
    I = core * (0.55 + 1.5 * turb) - 0.28 * vc - 0.2
    I = np.clip(I * fire_flicker(t) * 1.6, 0, None)
    r_ = np.clip(I * 2.4, 0, 1.6)
    g_ = np.clip(I * 1.6 - 0.25, 0, 1.3) ** 1.2
    b_ = np.clip(I * 1.1 - 0.85, 0, 1.0)
    rgb = np.stack([r_, g_ * 0.85, b_ * 0.6], -1) * 0.95
    rgb = np.clip(rgb, 0, 1)
    return Image.fromarray((rgb * 255).astype(np.uint8), "RGB")


def draw_particles(canvas, cov, cam, t, fire_vis):
    # ---- ash (stateless, world space, wrapped around the camera) ----
    r = np.random.default_rng(77)
    N = int(1800)
    p0 = r.uniform([-40, -40, 0], [40, 40, 50], (N, 3))
    ph = r.uniform(0, 2 * np.pi, (N, 2))
    vel = np.array([0.9, -0.55, 0.0])
    p = p0 + vel * t
    p[:, 0] += 0.35 * np.sin(1.6 * t + ph[:, 0])
    p[:, 1] += 0.15 * np.sin(2.3 * t + ph[:, 1])
    Xw, Yh, Lz, near = 14.0, 22.0, 46.0, 0.5
    rz = np.mod(p[:, 2] - cam.cz - near, Lz) + near
    rx = np.mod(p[:, 0] - cam.cx + Xw, 2 * Xw) - Xw
    ry = np.mod(p[:, 1] - cam.cy + Yh, 2 * Yh) - Yh
    ok = (cam.cy + ry) > 0.0
    sx = W / 2 + rx * F / rz
    sy = cam.hor - ry * F / rz
    size = F * r.uniform(0.010, 0.026, N) / rz
    alpha = r.uniform(0.45, 0.9, N) * np.clip(1.4 - rz / Lz, 0, 1)
    vis = ok & (sx > -40) & (sx < W + 40) & (sy > -40) & (sy < H + 40)
    sharp = Image.new("L", (W, H), 0)
    soft = Image.new("L", (W // 2, H // 2), 0)
    ds, df = ImageDraw.Draw(sharp), ImageDraw.Draw(soft)
    for i in np.where(vis)[0]:
        s = max(size[i], 0.8 * S)
        a = int(255 * alpha[i])
        if s > 7 * S:
            s = min(s, 40 * S) / 2
            df.ellipse([sx[i] / 2 - s, sy[i] / 2 - s * 0.8, sx[i] / 2 + s, sy[i] / 2 + s * 0.8], fill=int(a * 0.55))
        else:
            ds.ellipse([sx[i] - s, sy[i] - s * 0.75, sx[i] + s, sy[i] + s * 0.75], fill=a)
    A = np.asarray(sharp, np.float32) / 255
    A = np.maximum(A, np.asarray(soft.filter(ImageFilter.GaussianBlur(3 * S)).resize((W, H), Image.BILINEAR), np.float32) / 255)
    warm = smoothstep(395.0, 410.0, cam.cz)
    ashcol = np.array([0.66, 0.60, 0.57], np.float32) * (1 - warm) + np.array([0.70, 0.52, 0.42], np.float32) * warm
    A3 = A[..., None]
    canvas *= (1 - A3)
    canvas += ashcol * A3
    cov *= (1 - A)
    cov += A
    # ---- embers rising from the campfire ----
    if fire_vis:
        re = np.random.default_rng(78)
        M = 46
        life = re.uniform(1.4, 2.8, M)
        phase = re.uniform(0, 3, M)
        tl = np.mod(t + phase, life)
        ex = FIRE_X + re.normal(0, 0.08, M) + 0.25 * tl + 0.08 * np.sin(4 * tl + phase * 5)
        ey = 0.25 + 0.75 * tl + 0.12 * tl ** 2
        ez = FIRE_Z + re.normal(0, 0.1, M)
        dz = ez - cam.cz
        good = dz > 0.4
        esx = W / 2 + (ex - cam.cx) * F / dz
        esy = cam.hor - (ey - cam.cy) * F / dz
        br = (1 - tl / life) ** 1.4 * re.uniform(0.5, 1.0, M) * (0.6 + 0.4 * np.sin(13 * t + phase * 9) ** 2)
        Em = Image.new("L", (W, H), 0)
        de = ImageDraw.Draw(Em)
        for i in np.where(good)[0]:
            s = max(1.0, F * 0.006 / dz[i])
            de.ellipse([esx[i] - s, esy[i] - s, esx[i] + s, esy[i] + s], fill=int(255 * min(1, br[i])))
        E = np.asarray(Em.filter(ImageFilter.GaussianBlur(1.0 * S)), np.float32) / 255
        canvas += (E * 1.8)[..., None] * np.array([1.0, 0.55, 0.18], np.float32)


def radial(cx, cy, R, scale=4):
    SX, SY = quarter_grid()
    g = np.exp(-(((SX - cx) ** 2 + (SY - cy) ** 2) / (R * R)))
    return up_f(g.astype(np.float32), (W, H))


def grade(img, t):
    # bloom
    small = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).resize((W // 4, H // 4), Image.BILINEAR)
    sm = np.asarray(small, np.float32) / 255
    br = np.clip(sm - 0.55, 0, None) * 1.6
    b = Image.fromarray((np.clip(br, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(9 * S)).resize((W, H), Image.BILINEAR)
    img = img + np.asarray(b, np.float32) / 255 * 0.7
    # soft highlight roll-off
    img = np.where(img < 0.8, img, 0.8 + 0.2 * (1 - np.exp(-(img - 0.8) / 0.2)))
    # vignette
    SX, SY = quarter_grid()
    rr = ((SX - W / 2) / (W * 0.62)) ** 2 + ((SY - H * 0.52) / (H * 0.62)) ** 2
    v = up_f((1 - 0.5 * np.clip(rr, 0, 1.6) ** 1.3).astype(np.float32), (W, H))
    img = img * np.clip(v, 0.25, 1)[..., None]
    # grain
    gr = np.random.default_rng(int(t * 1000) + 5).standard_normal((H // 2, W // 2)).astype(np.float32)
    gr = np.asarray(Image.fromarray(gr, "F").resize((W, H), Image.BILINEAR))
    img = img + (gr * 0.018)[..., None]
    # fades
    fade = ease(t / 1.4) * (1 - ease((t - 22.9) / 1.05))
    return np.clip(img * fade, 0, 1)


def render_frame(t):
    cam = Cam(t)
    flash = flash_total(t)
    fire_vis = cam.cz > 360
    fireI = fire_flicker(t) * smoothstep(360.0, 400.0, cam.cz) if fire_vis else 0.0

    sky = render_sky(cam, t)
    draw_bolts(sky, cam, t)

    canvas = np.zeros((H, W, 3), np.float32)
    g_rgb, g_a = render_ground(cam, t, fireI)
    canvas += g_rgb * g_a[..., None]
    cov = g_a.copy()

    drawables = [(l.z, "layer", l) for l in LAYERS]
    drawables += [(pl[1] - 0.5, "plume", pl) for pl in PLUMES]
    drawables += [(1000.0, "haze", None)]
    if fire_vis:
        drawables += [(TENT_Z, "tent", None), (FIRE_Z, "fire", None)]
    drawables.sort(key=lambda d: -d[0])

    lift = 1.0 + 0.10 * flash
    for z, kind, obj in drawables:
        if kind == "layer":
            if z - cam.cz < 0.35:
                continue
            tint = np.array([lift, lift, lift * 1.08], np.float32)
            draw_billboard(canvas, cov, obj.img, obj.xl, obj.yb, obj.wm, obj.hm, obj.z, cam, obj.fogk, tint=tint)
        elif kind == "plume":
            draw_plume(canvas, cov, cam, t, obj)
        elif kind == "haze":
            draw_haze(canvas, cov, cam, t, 0.55 * (1 - smoothstep(380.0, 405.0, cam.cz)) + 0.18)
        elif kind == "tent":
            dz = TENT_Z - cam.cz
            ppm = int(np.clip(F / dz * 1.15, 60, 300))
            img = tent_image(t, fireI, min(flash, 1.2), ppm)
            draw_billboard(canvas, cov, img, TENT_X - 1.7, 0.0, 3.4, 1.5, TENT_Z, cam)
        elif kind == "fire":
            draw_billboard(canvas, cov, FIRE_BASE, FIRE_X - 0.5, 0.0, 1.0, 1.25, FIRE_Z, cam)
            draw_billboard(canvas, cov, fire_flames(t), FIRE_X - 0.5, 0.0, 1.0, 1.25, FIRE_Z, cam, mode="add")

    draw_particles(canvas, cov, cam, t, fire_vis)

    # composite layers over sky
    img = sky * (1 - cov[..., None]) + canvas

    # lightning: overall cool exposure lift on everything
    if flash > 0.003:
        img += flash * np.array([0.05, 0.055, 0.08], np.float32)

    # campfire light glow in the air + flashlight halo around the tent
    if fire_vis and fireI > 0:
        dz = FIRE_Z - cam.cz
        fx = W / 2 + (FIRE_X - cam.cx) * F / dz
        fy = cam.hor - (0.35 - cam.cy) * F / dz
        R = F * 0.9 / dz
        g = radial(fx, fy, R) * 0.35 + radial(fx, fy, R * 3.2) * 0.16
        img += (g * fireI)[..., None] * np.array([1.0, 0.45, 0.15], np.float32)
        dzt = TENT_Z - cam.cz
        tx = W / 2 + (TENT_X + 0.1 - cam.cx) * F / dzt
        ty = cam.hor - (0.8 - cam.cy) * F / dzt
        gt = radial(tx, ty, F * 1.3 / dzt) * 0.08 * smoothstep(395.0, 410.0, cam.cz)
        img += gt[..., None] * np.array([1.0, 0.7, 0.4], np.float32)

    return grade(img, t)


def frame_bytes(i):
    t = i / FPS
    img = render_frame(t)
    return (img * 255 + 0.5).astype(np.uint8).tobytes()


def main():
    args = sys.argv[1:]
    if args and args[0] == "--preview":
        set_scale(float(args[1]))
        build_scene()
        os.makedirs(OUT_DIR, exist_ok=True)
        for ts in args[2:]:
            t = float(ts)
            img = render_frame(t)
            Image.fromarray((img * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT_DIR, f"preview_{t:05.2f}.png"))
            print("saved", t, flush=True)
        return
    nf = NF
    if args and args[0] == "--frames":
        nf = int(args[1])
    build_scene()
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "video_only.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(os.cpu_count()) as pool:
        for k, b in enumerate(pool.imap(frame_bytes, range(nf), chunksize=2)):
            ff.stdin.write(b)
            if k % 30 == 0:
                print(f"frame {k}/{nf}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("wrote", out)


if __name__ == "__main__":
    main()
