"""Бібліотека процедурного малювання для «Села, якого немає на жодній карті»."""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw

W, H = 1920, 1080
F32 = np.float32


def C(hexs):
    hexs = hexs.lstrip("#")
    return np.array([int(hexs[i:i + 2], 16) / 255 for i in (0, 2, 4)], F32)


NIGHT_TOP, NIGHT_BOT = C("05070d"), C("1a2433")
MOON = C("dfe8f5")
AMBER = C("ffb256")
AMBER_DEEP = C("e07a28")
CANDLE = C("ffc978")
COLD = C("6f8fb8")
FOG_BLUE = C("4a5a70")
FOG_GREEN = C("6c7568")
DUSK_TOP, DUSK_BOT = C("2b3138"), C("a57a55")
DAWN_TOP, DAWN_BOT = C("6d7184"), C("e6b8a6")
WHITEWASH = C("c9c3b4")
THATCH = C("3b2d1e")
WOOD = C("4a3524")
SKIN = C("b98c72")
JACKET = C("39402c")
SCARF = C("d8d2c6")
EMBROID = C("9b2a22")


def col(c):
    return np.asarray(c, F32)


class Canvas:
    def __init__(self, seed, w=W, h=H):
        self.w, self.h = int(w), int(h)
        self.img = np.zeros((self.h, self.w, 3), F32)
        self.glow = np.zeros((self.h, self.w, 3), F32)
        self.rng = np.random.default_rng(seed)
        self.yy, self.xx = np.mgrid[0:self.h, 0:self.w].astype(F32)

    # ---- маски
    def mask(self, fn, blur=0.0):
        m = Image.new("L", (self.w, self.h), 0)
        fn(ImageDraw.Draw(m))
        a = np.asarray(m, F32) / 255
        if blur > 0:
            a = cv2.GaussianBlur(a, (0, 0), blur)
        return a

    def poly_mask(self, pts, blur=0.8):
        pts = [(float(x), float(y)) for x, y in pts]
        return self.mask(lambda d: d.polygon(pts, fill=255), blur)

    def ell_mask(self, cx, cy, rx, ry, blur=0.8):
        box = [float(cx - rx), float(cy - ry), float(cx + rx), float(cy + ry)]
        return self.mask(lambda d: d.ellipse(box, fill=255), blur)

    def rect_mask(self, x0, y0, x1, y1, blur=0.8):
        box = [float(x0), float(y0), float(x1), float(y1)]
        return self.mask(lambda d: d.rectangle(box, fill=255), blur)

    def line_mask(self, pts, width, blur=0.8):
        pts = [(float(x), float(y)) for x, y in pts]
        width = max(1, int(width))

        def f(d):
            d.line(pts, fill=255, width=width, joint="curve")
            r = width / 2
            for x, y in (pts[0], pts[-1]):
                d.ellipse([x - r, y - r, x + r, y + r], fill=255)
        return self.mask(f, blur)

    # ---- малювання
    def fill(self, m, color, alpha=1.0):
        a = (m * alpha)[:, :, None]
        c = col(color)
        if c.ndim == 1:
            c = c[None, None, :]
        self.img = self.img * (1 - a) + c * a

    def emit(self, m, color, k=1.0):
        self.glow += m[:, :, None] * col(color)[None, None, :] * k

    def light(self, x, y, r, color, k=1.0, core=0.0):
        d2 = ((self.xx - x) ** 2 + (self.yy - y) ** 2) / (r * r)
        g = np.exp(-d2 * 2.2) + 0.35 / (1 + d2 * 6)
        if core:
            g = g + core * np.exp(-d2 * 60)
        self.glow += g[:, :, None] * col(color)[None, None, :] * k

    def tint_light(self, x, y, r, color, k=1.0):
        d2 = ((self.xx - x) ** 2 + (self.yy - y) ** 2) / (r * r)
        g = np.exp(-d2 * 1.6)[:, :, None]
        self.img = self.img * (1 + g * k * col(color)[None, None, :] * 2.2)

    def vgrad(self, top, bot, y0=0, y1=None, curve=1.0):
        y1 = self.h if y1 is None else y1
        t = np.clip((self.yy - y0) / max(y1 - y0, 1), 0, 1) ** curve
        self.img = col(top) * (1 - t[:, :, None]) + col(bot) * t[:, :, None]

    def noise(self, scale, octaves=4, seed=None, aspect=1.0):
        r = self.rng if seed is None else np.random.default_rng(int(seed))
        out = np.zeros((self.h, self.w), F32)
        amp, tot = 1.0, 0.0
        for o in range(octaves):
            gw = max(2, int(self.w / scale * 2 ** o))
            gh = max(2, int(self.h / scale * 2 ** o * aspect))
            g = r.random((gh, gw)).astype(F32)
            out += cv2.resize(g, (self.w, self.h), interpolation=cv2.INTER_CUBIC) * amp
            tot += amp
            amp *= 0.5
        return out / tot

    def fog(self, y0, y1, color, density=0.6, scale=500, soft=120, seed=None):
        n = self.noise(scale, 4, seed, aspect=1.6)
        band = np.clip((self.yy - y0) / soft, 0, 1) * np.clip((y1 - self.yy) / soft, 0, 1)
        m = np.clip((n - 0.25) * 1.6, 0, 1) * band * density
        self.fill(m, color)
        return m

    def haze(self, color, k):
        self.img = self.img * (1 - k) + col(color)[None, None, :] * k

    def stars(self, n=400, ymax=0.5):
        for _ in range(n):
            x = int(self.rng.uniform(0, self.w - 1))
            y = int(self.rng.uniform(0, self.h * ymax))
            self.glow[y, x] += self.rng.uniform(0.15, 0.7) ** 2 * 2

    def moon(self, x, y, r, k=1.0):
        m = self.ell_mask(x, y, r, r, 1.2)
        tex = 0.85 + 0.15 * self.noise(max(r * 0.8, 8), 3)
        self.fill(m, MOON[None, None, :] * tex[:, :, None])
        self.light(x, y, r * 7, MOON * 0.35, k)

    def blur(self, s):
        self.img = cv2.GaussianBlur(self.img, (0, 0), s)

    def finish(self, grade=None, bloom=0.9, vignette=0.5, grain=0.025, lift=0.0):
        img = self.img.copy()
        g = self.glow
        if bloom:
            g = g + cv2.GaussianBlur(g, (0, 0), 18) * bloom * 0.6 + cv2.GaussianBlur(g, (0, 0), 70) * bloom * 0.5
        img = img + g
        img = (1 - np.exp(-img * 1.15)) / (1 - math.exp(-1.15))
        if grade is not None:
            img = grade(img)
        img = img + lift
        r = np.sqrt(((self.xx - self.w / 2) / (self.w / 2)) ** 2 + ((self.yy - self.h / 2) / (self.h / 2)) ** 2)
        img = img * (1 - vignette * np.clip(r - 0.55, 0, None) ** 1.5)[:, :, None]
        img = img + self.rng.normal(0, grain, (self.h, self.w, 1)).astype(F32)
        return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))

    def as_array(self, **kw):
        return np.asarray(self.finish(**kw), F32) / 255


# ---- ґрейди
LUM = np.array([0.3, 0.59, 0.11], F32)


def g_sepia(img):
    l = img @ LUM
    return np.stack([l * 1.08 + 0.06, l * 0.92 + 0.04, l * 0.7 + 0.02], -1) * 0.92


def g_bw(img):
    l = np.clip((img @ LUM - 0.05) * 1.15, 0, 1)
    return np.stack([l, l, l * 0.97], -1)


def g_faded(img):
    return img * np.array([0.92, 0.84, 0.72], F32) + np.array([0.09, 0.07, 0.05], F32)


def g_cold(img):
    return img * np.array([0.82, 0.92, 1.1], F32)


def g_warm(img):
    return img * np.array([1.08, 0.97, 0.85], F32)


# ---- пейзаж
def ridge(c, base, amp, scale, color, seed, blur=1.5):
    r = np.random.default_rng(seed)
    xs = np.linspace(0, c.w, 400)
    k = np.arange(0, c.w + scale * 2, scale)
    y = np.interp(xs, k, r.standard_normal(len(k))) * amp
    k2 = np.arange(0, c.w + scale * 4, scale * 2)
    y = y + np.interp(xs, k2, r.standard_normal(len(k2))) * amp * 1.4
    pts = [(0, c.h)] + [(x, base - abs(v)) for x, v in zip(xs, y)] + [(c.w, c.h)]
    c.fill(c.poly_mask(pts, blur), color)


def pine(d, x, yb, h, wdt):
    tiers = 6
    for i in range(tiers):
        y_t = yb - h + h * (i / tiers) * 0.95
        y_b = min(y_t + h / tiers * 1.9, yb)
        ww = wdt * (0.25 + 0.75 * (i + 1) / tiers)
        d.polygon([(x, y_t - h * 0.03), (x - ww / 2, y_b), (x + ww / 2, y_b)], fill=255)
    d.rectangle([x - wdt * 0.04, yb - h * 0.1, x + wdt * 0.04, yb + 4], fill=255)


def forest_row(c, base, hmin, hmax, density, color, seed, blur=1.0, gap=None):
    r = np.random.default_rng(seed)

    def f(d):
        x = -40.0
        while x < c.w + 40:
            if gap is None or not (gap[0] < x < gap[1]):
                h = r.uniform(hmin, hmax)
                pine(d, x, base + r.uniform(-8, 8), h, h * r.uniform(0.32, 0.45))
            x += r.uniform(0.5, 1.4) * hmax * 0.35 / density
    c.fill(c.mask(f, blur), color)


def trunks(c, n, color, seed, wmin=30, wmax=110, blur=1.0):
    r = np.random.default_rng(seed)
    for _ in range(n):
        x = r.uniform(0, c.w)
        w = r.uniform(wmin, wmax)
        lean = r.uniform(-20, 20)
        tex = 0.7 + 0.3 * c.noise(max(w * 0.3, 6), 2, aspect=0.1)
        m = c.poly_mask([(x - w / 2 + lean, -20), (x + w / 2 + lean, -20), (x + w * 0.6, c.h + 20), (x - w * 0.6, c.h + 20)], blur)
        c.fill(m, col(color)[None, None, :] * tex[:, :, None])


def road_persp(c, vx, vy, w_near, color, curve=0.0, y_near=None):
    y_near = c.h + 10 if y_near is None else y_near
    L, R = [], []
    for t in np.linspace(0, 1, 40):
        y = vy + (y_near - vy) * t
        cx = vx + curve * (1 - t) ** 2 * 1200 * t
        hw = 4 + w_near / 2 * t
        L.append((cx - hw, y))
        R.append((cx + hw, y))
    c.fill(c.poly_mask(L + R[::-1], 1.5), color)


# ---- будівлі й предмети села
def hut(c, x, yb, s, lit=1.0, wall=WHITEWASH, shutters=None, door_open=False, light_col=AMBER,
        wall_light=0.12, windows=2):
    hw, wh = s / 2, s * 0.42
    m = c.rect_mask(x - hw, yb - wh, x + hw, yb)
    tex = 0.8 + 0.2 * c.noise(max(s * 0.3, 8), 3)
    c.fill(m, (col(wall) * wall_light)[None, None, :] * tex[:, :, None])
    roof = [(x - hw * 1.18, yb - wh + s * 0.03), (x - hw * 0.55, yb - wh - s * 0.36),
            (x + hw * 0.55, yb - wh - s * 0.36), (x + hw * 1.18, yb - wh + s * 0.03)]
    rt = 0.6 + 0.4 * c.noise(max(s * 0.08, 4), 2, aspect=3)
    c.fill(c.poly_mask(roof, 1.2), (THATCH * 0.35)[None, None, :] * rt[:, :, None])
    ww, wwh = s * 0.13, s * 0.15
    xs = [x - hw * 0.55, x + hw * 0.55]
    door_x = x - hw * 0.05
    wy = yb - wh * 0.72
    for wx in xs:
        wm = c.rect_mask(wx - ww / 2, wy, wx + ww / 2, wy + wwh, 0.6)
        if lit > 0:
            c.fill(wm, light_col * 0.9 * min(lit, 1))
            c.emit(wm, light_col, 0.8 * lit)
            c.light(wx, yb - wh * 0.55, s * 0.4, light_col, 0.18 * lit)
            c.fill(c.rect_mask(wx - 1.5, wy, wx + 1.5, wy + wwh, 0.4), C("1a1008"))
            c.fill(c.rect_mask(wx - ww / 2, wy + wwh * 0.45, wx + ww / 2, wy + wwh * 0.45 + 3, 0.4), C("1a1008"))
        else:
            c.fill(wm, C("07090c"))
        if shutters is not None:
            for sx in (wx - ww * 0.85, wx + ww * 0.85):
                c.fill(c.rect_mask(sx - ww * 0.32, wy - wwh * 0.04, sx + ww * 0.32, wy + wwh * 1.02, 0.6), shutters)
    dw, dh = s * 0.14, wh * 0.78
    dm = c.rect_mask(door_x - dw / 2, yb - dh, door_x + dw / 2, yb, 0.6)
    if door_open and lit > 0:
        c.fill(dm, light_col * 0.95)
        c.emit(dm, light_col, 1.1 * lit)
        c.light(door_x, yb - dh * 0.5, s * 0.6, light_col, 0.25 * lit)
        c.fill(c.poly_mask([(door_x - dw / 2, yb), (door_x + dw / 2, yb), (door_x + dw * 2, yb + s * 0.25),
                            (door_x - dw * 2, yb + s * 0.25)], 8), light_col * 0.35, 0.5 * min(lit, 1))
    else:
        c.fill(dm, WOOD * 0.25)


def church(c, x, yb, s, color):
    def f(d):
        d.rectangle([x - s * 0.3, yb - s * 0.7, x + s * 0.3, yb], fill=255)
        d.rectangle([x - s * 0.12, yb - s * 1.05, x + s * 0.12, yb - s * 0.7], fill=255)
        d.ellipse([x - s * 0.13, yb - s * 1.25, x + s * 0.13, yb - s * 0.98], fill=255)
        d.polygon([(x - s * 0.02, yb - s * 1.24), (x, yb - s * 1.42), (x + s * 0.02, yb - s * 1.24)], fill=255)
        d.rectangle([x - s * 0.006, yb - s * 1.52, x + s * 0.006, yb - s * 1.38], fill=255)
        d.rectangle([x - s * 0.04, yb - s * 1.48, x + s * 0.04, yb - s * 1.465], fill=255)
        d.rectangle([x - s * 0.5, yb - s * 0.45, x - s * 0.3, yb], fill=255)
        d.polygon([(x - s * 0.52, yb - s * 0.45), (x - s * 0.4, yb - s * 0.62), (x - s * 0.28, yb - s * 0.45)], fill=255)
    c.fill(c.mask(f, 1.2), color)


def lantern(c, x, yb, h, k=1.0, pole=True, lcol=AMBER, lit=True):
    if pole:
        c.fill(c.rect_mask(x - h * 0.012, yb - h, x + h * 0.012, yb), C("0a0806"))
        c.fill(c.rect_mask(x - h * 0.012, yb - h, x + h * 0.08, yb - h + h * 0.012), C("0a0806"))
        lx, ly = x + h * 0.07, yb - h + h * 0.09
    else:
        lx, ly = x, yb
    s = h * 0.05
    c.fill(c.rect_mask(lx - s, ly - s * 1.2, lx + s, ly + s * 1.2, 0.6), C("100a05"))
    if lit:
        cm = c.rect_mask(lx - s * 0.7, ly - s * 0.9, lx + s * 0.7, ly + s * 0.9, 0.8)
        c.fill(cm, lcol)
        c.emit(cm, lcol, 1.5 * k)
        c.light(lx, ly, h * 0.55, lcol, 0.45 * k, core=1.5)
    return lx, ly


def well(c, x, yb, s, color):
    def f(d):
        d.rectangle([x - s * 0.18, yb - s * 0.28, x + s * 0.18, yb], fill=255)
        d.rectangle([x - s * 0.02, yb - s * 0.9, x + s * 0.02, yb], fill=255)
        d.line([(x - s * 0.55, yb - s * 1.2), (x + s * 0.65, yb - s * 0.55)], fill=255, width=max(2, int(s * 0.025)))
        d.line([(x - s * 0.5, yb - s * 1.17), (x - s * 0.5, yb - s * 0.35)], fill=255, width=max(1, int(s * 0.008)))
        d.rectangle([x - s * 0.55, yb - s * 0.38, x - s * 0.45, yb - s * 0.28], fill=255)
    c.fill(c.mask(f, 1.0), color)


def fence(c, y, x0, x1, h, color, seed=0):
    r = np.random.default_rng(seed)

    def f(d):
        x = x0
        while x < x1:
            d.line([(x, y), (x + r.uniform(-4, 4), y - h * r.uniform(0.8, 1.1))], fill=255, width=4)
            x += h * 0.22
        d.line([(x0, y - h * 0.6), (x1, y - h * 0.62)], fill=255, width=3)
        d.line([(x0, y - h * 0.25), (x1, y - h * 0.24)], fill=255, width=3)
    c.fill(c.mask(f, 1.0), color)


def cross(c, x, yb, h, color, tilt=0.0, blur=1.0):
    a = math.radians(tilt)

    def rot(px, py):
        return (x + px * math.cos(a) - py * math.sin(a), yb + px * math.sin(a) + py * math.cos(a))
    w = h * 0.07

    def f(d):
        d.polygon([rot(-w / 2, 0), rot(w / 2, 0), rot(w / 2, -h), rot(-w / 2, -h)], fill=255)
        d.polygon([rot(-h * 0.32, -h * 0.72), rot(h * 0.32, -h * 0.72), rot(h * 0.32, -h * 0.72 - w), rot(-h * 0.32, -h * 0.72 - w)], fill=255)
        d.polygon([rot(-h * 0.2, -h * 0.35), rot(h * 0.2, -h * 0.45), rot(h * 0.2, -h * 0.45 - w * 0.8), rot(-h * 0.2, -h * 0.35 - w * 0.8)], fill=255)
    c.fill(c.mask(f, blur), color)


def candle(c, x, yb, h, k=1.0, w=None):
    w = h * 0.22 if w is None else w
    c.fill(c.rect_mask(x - w / 2, yb - h, x + w / 2, yb, 1.0), C("d9c9a0") * 0.55)
    fx, fy = x, yb - h - h * 0.12
    fl = c.poly_mask([(fx, fy - max(h * 0.28, 14)), (fx + max(w * 0.22, 4), fy), (fx, fy + max(h * 0.06, 3)), (fx - max(w * 0.22, 4), fy)], 1.0)
    c.emit(fl, CANDLE, 2.0 * k)
    c.light(fx, fy - h * 0.05, max(h * 3.2, 120), CANDLE, 0.5 * k, core=2)
    return fx, fy


def rim_edge(c, m, color, dx, dy, px, k=0.9, glow=0.25):
    Mt = np.float32([[1, 0, -dx * px], [0, 1, -dy * px]])
    edge = np.clip(m - cv2.warpAffine(m, Mt, (c.w, c.h)), 0, 1)
    edge = cv2.GaussianBlur(edge, (0, 0), 1.0)
    c.fill(edge, color, min(1.0, k))
    c.emit(edge, color, glow)


# ---- люди
def figure(c, x, yb, h, kind="man", pose="stand", color=C("06070a"), rim=None, rim_dir=(-1, -0.4),
           lantern_hand=False, back=False, flip=1, blur=1.0):
    child = kind == "child"
    fem = kind in ("hanna", "woman")
    hh = h * (0.19 if child else 0.155)
    sh = h * (0.1 if fem else 0.12)
    extra = []
    if pose == "kneel":
        head_y = yb - h * 0.72 + hh / 2
        top = head_y + hh / 2
        hip = yb - h * 0.3
        body = [(x - sh, top + hh * 0.2), (x + sh, top + hh * 0.2), (x + sh * 0.8, hip), (x - sh * 0.85, hip)]
        extra.append([(x - sh * 0.8, hip - 4), (x + sh * 0.9, hip - 4), (x + sh * 1.6 * flip, yb), (x - sh * 0.7, yb)])
    else:
        head_y = yb - h + hh / 2
        top = head_y + hh / 2
        hip = yb - h * 0.47
        lean = {"run": 0.12, "walk": 0.03}.get(pose, 0) * h * flip
        if fem:
            body = [(x - sh * 0.9 + lean, top + hh * 0.15), (x + sh * 0.9 + lean, top + hh * 0.15), (x + sh * 1.6, yb), (x - sh * 1.6, yb)]
        else:
            body = [(x - sh + lean, top + hh * 0.18), (x + sh + lean, top + hh * 0.18), (x + sh * 0.75, hip), (x - sh * 0.75, hip)]
            spread = {"stand": 0.08, "walk": 0.25, "run": 0.5}.get(pose, 0.1) * h
            lw = sh * 0.42
            extra.append([(x - sh * 0.75, hip - 2), (x - sh * 0.75 + lw * 1.6, hip - 2), (x - spread * 0.4 + lw * 0.5, yb), (x - spread * 0.4 - lw * 0.5, yb)])
            if pose == "run":
                extra.append([(x + sh * 0.75 - lw * 1.6, hip - 2), (x + sh * 0.75, hip - 2), (x + spread * 0.9 * flip, yb - h * 0.22), (x + spread * 0.7 * flip, yb - h * 0.12)])
            else:
                extra.append([(x + sh * 0.75 - lw * 1.6, hip - 2), (x + sh * 0.75, hip - 2), (x + spread * 0.4 + lw * 0.5, yb), (x + spread * 0.4 - lw * 0.5, yb)])
        x = x + lean
    aw = max(3, sh * 0.32)
    sy = top + hh * 0.35
    if pose == "run":
        arms = [[(x - sh * 0.9, sy), (x - sh * 1.6 * flip, sy + h * 0.12), (x - sh * 2.2 * flip, sy + h * 0.02)],
                [(x + sh * 0.9, sy), (x + sh * 1.8 * flip, sy + h * 0.15), (x + sh * 2.5 * flip, sy + h * 0.25)]]
    elif pose == "arms_up":
        arms = [[(x - sh * 0.9, sy), (x - sh * 1.5, sy - h * 0.15), (x - sh * 1.7, sy - h * 0.3)],
                [(x + sh * 0.9, sy), (x + sh * 1.2, sy + h * 0.15), (x + sh * 1.1, sy + h * 0.3)]]
    elif not fem:
        arms = [[(x - sh * 0.95, sy), (x - sh * 1.05, sy + h * 0.17), (x - sh * 1.0, sy + h * 0.3)],
                [(x + sh * 0.95, sy), (x + sh * 1.05, sy + h * 0.17), (x + sh * 1.0, sy + h * 0.3)]]
    else:
        arms = []
    hand = (x + sh * 1.0, sy + h * 0.3)
    scarf = [(x - hh * 0.55, head_y - hh * 0.1), (x, head_y - hh * 0.62), (x + hh * 0.55, head_y - hh * 0.1),
             (x + hh * 0.5, head_y + hh * 0.75), (x - hh * 0.5, head_y + hh * 0.75)]

    def f(d):
        d.ellipse([x - hh * 0.42, head_y - hh / 2, x + hh * 0.42, head_y + hh / 2], fill=255)
        d.rectangle([x - hh * 0.16, head_y + hh * 0.3, x + hh * 0.16, top + hh * 0.3], fill=255)
        d.polygon([(float(a), float(b)) for a, b in body], fill=255)
        for p in extra:
            d.polygon([(float(a), float(b)) for a, b in p], fill=255)
        for a in arms:
            d.line([(float(p), float(q)) for p, q in a], fill=255, width=int(aw), joint="curve")
        if fem:
            d.polygon(scarf, fill=255)
            d.polygon([(x - sh * 1.1, top + hh * 0.3), (x + sh * 1.1, top + hh * 0.3), (x + sh * 0.8, top + h * 0.3), (x - sh * 0.8, top + h * 0.3)], fill=255)
        if kind == "andriy" and pose != "kneel":
            d.line([(x - sh * 0.7, top + hh * 0.25), (x + sh * 0.4, hip - h * 0.05)], fill=255, width=max(2, int(h * 0.008)))
        if kind == "old":
            d.ellipse([x - hh * 0.6, head_y - hh * 0.55, x + hh * 0.6, head_y - hh * 0.25], fill=255)
    m = c.mask(f, blur)
    c.fill(m, color)
    if fem and not back:
        hm = c.poly_mask(scarf, 1.0)
        fm = c.ell_mask(x, head_y + hh * 0.12, hh * 0.3, hh * 0.36, 1.0)
        c.fill(np.clip(hm - fm, 0, 1), SCARF * (0.22 if rim is None else 0.4))
    if rim is not None:
        rim_edge(c, m, rim, rim_dir[0], rim_dir[1], max(2, h * 0.008))
    if lantern_hand:
        lantern(c, hand[0] + h * 0.01, hand[1] + h * 0.04, h * 0.6, k=0.8, pole=False)
    return m


def crowd(c, xs, yb, h, kinds=None, color=C("07080b"), rim=None, seed=0, rim_dir=(-1, -0.4), lanterns=False):
    r = np.random.default_rng(seed)
    kinds = kinds or ["man", "woman", "old", "child", "woman", "man"]
    for i, x in enumerate(xs):
        k = kinds[i % len(kinds)]
        hh = h * (0.62 if k == "child" else r.uniform(0.92, 1.04))
        figure(c, x, yb + r.uniform(-3, 3), hh, k, "stand", color, rim=rim, rim_dir=rim_dir,
               lantern_hand=lanterns and k != "child")


PROFILE = [(0.00, -0.62), (0.10, -0.66), (0.24, -0.62), (0.33, -0.50), (0.37, -0.36), (0.36, -0.27),
           (0.40, -0.22), (0.48, -0.08), (0.47, -0.04), (0.40, -0.02), (0.41, 0.04), (0.38, 0.08),
           (0.40, 0.12), (0.37, 0.16), (0.36, 0.22), (0.30, 0.30), (0.20, 0.33), (0.14, 0.33),
           (0.12, 0.55), (0.12, 0.80), (-0.40, 0.80), (-0.42, 0.40), (-0.36, 0.10), (-0.40, -0.25),
           (-0.32, -0.52), (-0.18, -0.63)]


def profile_head(c, cx, cy, s, flip=1, color=C("050608"), rim=AMBER, rim_dir=None, kind="andriy", rim_k=1.0):
    P = lambda px, py: (cx + px * s * flip, cy + py * s)
    m = c.poly_mask([P(*p) for p in PROFILE], 1.2)
    c.fill(m, color)
    if kind == "hanna":
        smk = c.poly_mask([P(*p) for p in [(0.28, -0.70), (0.08, -0.80), (-0.25, -0.75), (-0.50, -0.45), (-0.55, 0.10),
                                            (-0.45, 0.70), (0.05, 0.85), (0.12, 0.40), (0.02, 0.10), (0.04, -0.25), (0.25, -0.50)]], 1.2)
        c.fill(smk, SCARF * 0.2)
        for i in range(14):
            t = i / 13
            ex, ey = P(0.22 - 0.5 * t, -0.62 + 0.15 * math.sin(t * 3))
            c.fill(c.ell_mask(ex, ey, s * 0.012, s * 0.012, 0.6), EMBROID * 0.5)
        m = np.maximum(m, smk)
    if kind == "andriy":
        c.fill(c.poly_mask([P(*p) for p in [(0.26, -0.60), (0.10, -0.70), (-0.20, -0.67), (-0.38, -0.50), (-0.42, -0.25),
                                            (-0.30, -0.35), (0.0, -0.55), (0.25, -0.55)]], 1.5), C("0b0806"))
    if rim is not None:
        dx, dy = rim_dir if rim_dir is not None else (flip, -0.3)
        rim_edge(c, m, rim, dx, dy, max(2, s * 0.012), 0.9 * rim_k, 0.35 * rim_k)
    ex, ey = P(0.27, -0.22)
    c.fill(c.ell_mask(ex, ey, s * 0.03, s * 0.012, 1.0), C("0e0e10"))
    c.emit(c.ell_mask(ex + s * 0.01 * flip, ey, s * 0.006, s * 0.006, 1.0), rim if rim is not None else MOON, 0.6)
    return m


def eye(c, cx, cy, s, iris=C("7f8a92"), warm=AMBER, cold=COLD, wide=1.0, catch=CANDLE, tear=False, split=True):
    skin = SKIN * 0.55
    side = np.clip((c.xx - cx) / (s * 2.5) + 0.5, 0, 1)[:, :, None] if split else 0.5
    base = skin * (col(warm) * 0.9 * side + col(cold) * 0.7 * (1 - side)) * 1.3
    tex = (0.85 + 0.15 * c.noise(max(s * 0.08, 6), 3))[:, :, None]
    c.img = (base * tex).astype(F32)
    for k, dy in ((1.0, -0.62), (0.7, -0.85), (0.5, 0.55)):
        ln = [(cx - s * 1.2, cy + dy * s * 0.4), (cx, cy + dy * s), (cx + s * 1.25, cy + dy * s * 0.35)]
        c.fill(c.line_mask(ln, s * 0.02, 3), skin * 0.25, 0.6 * k)
    op = 0.42 * wide
    top = [(cx - s + 2 * s * t, cy - op * s * math.sin(math.pi * t) ** 0.9 - s * 0.05 * t) for t in np.linspace(0, 1, 30)]
    bot = [(cx - s + 2 * s * t, cy + op * 0.6 * s * math.sin(math.pi * t) ** 1.1) for t in np.linspace(1, 0, 30)]
    em = c.poly_mask(top + bot, 1.5)
    c.fill(em, C("b5aea6") * 0.6)
    ir = s * 0.36
    ix, iy = cx + s * 0.05, cy - s * 0.04
    im = c.ell_mask(ix, iy, ir, ir, 1.5) * em
    rad = np.sqrt((c.xx - ix) ** 2 + (c.yy - iy) ** 2) / ir
    ang = np.arctan2(c.yy - iy, c.xx - ix)
    streak = 0.75 + 0.25 * np.sin(ang * 40 + rad * 3) * np.clip(rad, 0, 1)
    c.fill(im, col(iris)[None, None, :] * (0.55 + 0.45 * rad[:, :, None]) * streak[:, :, None])
    pr = ir * (0.38 + 0.12 * wide)
    c.fill(c.ell_mask(ix, iy, pr, pr, 1.2) * em, C("030303"))
    c.fill(c.poly_mask(top + [(cx + s, cy - op * s * 0.3), (cx - s, cy - op * s * 0.3)], 8) * em, C("000000"), 0.45)
    for t in np.linspace(0.08, 0.95, 26):
        x0 = cx - s + 2 * s * t
        y0 = cy - op * s * math.sin(math.pi * t) ** 0.9 - s * 0.05 * t
        c.fill(c.line_mask([(x0, y0), (x0 + s * 0.06 * (t - 0.3), y0 - s * 0.12)], max(2, s * 0.008), 0.8), C("080605"))
    fx, fy = cx + s * 0.18, cy - s * 0.16
    fm = c.poly_mask([(fx, fy - s * 0.07), (fx + s * 0.025, fy), (fx, fy + s * 0.03), (fx - s * 0.025, fy)], 1.0)
    c.emit(fm, catch, 1.6)
    c.light(fx, fy, s * 0.15, catch, 0.15)
    if tear:
        c.emit(c.line_mask([(cx + s * 0.6, cy + op * 0.5 * s), (cx + s * 0.62, cy + s * 0.9)], s * 0.025, 2), warm, 0.35)


def hand(c, x, y, s, ang=0.0, pose="flat", color=SKIN * 0.4, old=False, rim=None, rim_dir=(-1, -0.5)):
    ca, sa = math.cos(ang), math.sin(ang)
    P = lambda u, v: (x + u * s * ca - v * s * sa, y + u * s * sa + v * s * ca)
    fw = s * 0.16

    def finger(d, a, b):
        d.line([a, b], fill=255, width=int(fw))
        d.ellipse([b[0] - fw / 2, b[1] - fw / 2, b[0] + fw / 2, b[1] + fw / 2], fill=255)

    def f(d):
        d.polygon([P(-0.9, -0.3), P(0.0, -0.32), P(0.05, 0.33), P(-0.9, 0.3)], fill=255)
        px_, py_ = P(-0.25, 0)
        d.ellipse([px_ - s * 0.35, py_ - s * 0.35, px_ + s * 0.35, py_ + s * 0.35], fill=255)
        if pose == "flat":
            for v, L in ((-0.24, 0.55), (-0.08, 0.62), (0.08, 0.6), (0.23, 0.48)):
                finger(d, P(0, v), P(L, v * 1.15))
            finger(d, P(-0.3, -0.3), P(0.05, -0.62))
        elif pose == "grip":
            for v in (-0.22, -0.07, 0.08, 0.22):
                finger(d, P(0, v), P(0.25, v))
                finger(d, P(0.25, v), P(0.18, v + 0.18))
            finger(d, P(-0.2, -0.3), P(0.25, -0.38))
        else:  # touch
            finger(d, P(0, -0.15), P(0.75, -0.2))
            finger(d, P(0, 0.0), P(0.68, 0.02))
            for v in (0.14, 0.26):
                finger(d, P(0, v), P(0.32, v + 0.1))
            finger(d, P(-0.3, -0.3), P(0.1, -0.5))
    m = c.mask(f, 1.2)
    tex = 0.8 + 0.2 * c.noise(max(s * (0.05 if old else 0.15), 4), 3)
    if old:
        tex = tex * (0.85 + 0.15 * np.sin(c.yy * 0.6 + c.noise(30, 2) * 8))
    c.fill(m, col(color)[None, None, :] * tex[:, :, None])
    if rim is not None:
        rim_edge(c, m, rim, rim_dir[0], rim_dir[1], max(2, s * 0.02), 0.8, 0.2)
    return m


def flashlight_beam(c, x0, y0, x1, y1, w1, k=1.0, bcol=C("e8ecf2")):
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    nx, ny = -dy / L, dx / L
    m = c.poly_mask([(x0 + nx * 6, y0 + ny * 6), (x1 + nx * w1, y1 + ny * w1), (x1 - nx * w1, y1 - ny * w1), (x0 - nx * 6, y0 - ny * 6)], 25)
    t = np.clip(((c.xx - x0) * dx + (c.yy - y0) * dy) / (L * L), 0, 1)
    c.emit(m * (1 - t) ** 1.2 * (0.6 + 0.4 * c.noise(250, 3)), bcol, 0.75 * k)
    c.light(x0, y0, 40, bcol, 0.6 * k, core=3)


def paper_sheet(c, pts, k=0.35, pcol=C("d8cfbd")):
    m = c.poly_mask(pts, 1.5)
    c.fill(m, col(pcol)[None, None, :] * (0.25 + k * c.noise(120, 3))[:, :, None])
    return m


def paste(c, im, x, y, m=None, k=1.0):
    """Вставляє масив im (h,w,3) у полотно з обрізанням по краях."""
    x, y = int(x), int(y)
    h, w = im.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, c.w), min(y + h, c.h)
    if x1 <= x0 or y1 <= y0:
        return
    c.img[y0:y1, x0:x1] = im[y0 - y:y1 - y, x0 - x:x1 - x] * k
