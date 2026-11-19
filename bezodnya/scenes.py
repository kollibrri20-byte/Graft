"""32 процедурні сцени "Безодні". Кожна сцена — клас із методом frame(t) -> float RGB (H, W, 3)."""
import math

import numpy as np

from gfx import (H, W, XX, YY, C, Layer, Snow, add_glow, blur, cone, caustics, clamp01, ease,
                 edge_profile, fast_blur, fbm, finish, god_rays, lerp, radial, smooth, vgrad)

DEEP = C(2, 6, 14)
BLACK = C(0, 0, 0)


def rot(pts, a, cx=0.0, cy=0.0):
    c, s = math.cos(a), math.sin(a)
    return [(cx + x * c - y * s, cy + x * s + y * c) for x, y in pts]


def shake(t, amp, seed=0):
    return (amp * (math.sin(t * 37 + seed) * 0.6 + math.sin(t * 61 + 2 * seed) * 0.4),
            amp * (math.sin(t * 43 + 1 + seed) * 0.6 + math.sin(t * 71 + seed) * 0.4))


# ================================================================ спільні "актори"
def fish_shape(x, y, L, ang=0.0, depth=0.35, tail=0.0):
    """Обрис риби довжиною L, головою в напрямку ang."""
    pts = []
    for i in range(13):
        u = i / 12
        px = L * (0.5 - u)
        py = -L * depth * math.sin(math.pi * u ** 0.8) * 0.5
        pts.append((px, py))
    tx = -L * 0.5
    sw = math.sin(tail) * L * 0.08
    pts += [(tx - L * 0.22, -L * 0.18 + sw), (tx - L * 0.12, sw), (tx - L * 0.22, L * 0.18 + sw)]
    for i in range(12, -1, -1):
        u = i / 12
        px = L * (0.5 - u)
        py = L * depth * math.sin(math.pi * u ** 0.8) * 0.45
        pts.append((px, py))
    return rot(pts, ang, x, y)


def draw_fish(L_, x, y, L, col, ang=0.0, t=0.0, eye=None, depth=0.35, a=1.0):
    L_.poly(fish_shape(x, y, L, ang, depth, t * 9), col, a)
    if eye is not None:
        ex, ey = rot([(L * 0.33, -L * 0.05)], ang, x, y)[0]
        L_.ellipse(ex, ey, L * 0.06, L * 0.06, eye, a)


def whale_pts(x, y, L, t, ang=0.0, flip=False):
    """Кашалот збоку: масивна прямокутна голова, тіло звужується до хвоста."""
    s = -1 if flip else 1
    top, bot = [], []
    N = 30
    for i in range(N + 1):
        u = i / N  # 0 — морда, 1 — хвіст
        if u < 0.33:
            h = 0.17
        else:
            h = 0.17 * (1 - smooth(0.33, 1.0, u) * 0.86)
        bend = math.sin(t * 1.2 - u * 3) * 0.035 * u * u
        cx = (0.5 - u) * L
        top.append((cx, (-h + bend - 0.01 * (u < 0.33)) * L))
        bot.append((cx, (h * (0.75 if u < 0.33 else 1) + bend) * L))
    fl = math.sin(t * 1.2 - 3) * 0.06 + 0.035 * 1
    tail = [(-0.5 * L - 0.02 * L, (fl - 0.12) * L), (-0.5 * L - 0.14 * L, (fl - 0.14) * L),
            (-0.5 * L - 0.08 * L, fl * L), (-0.5 * L - 0.14 * L, (fl + 0.14) * L),
            (-0.5 * L - 0.02 * L, (fl + 0.12) * L)]
    pts = top + tail + bot[::-1]
    pts = [(s * px, py) for px, py in pts]
    return rot(pts, ang, x, y)


def tentacle(x0, y0, ang, L, t, n=24, amp=0.25, freq=2.2, ph=0.0, curl=0.0):
    pts = []
    a = ang
    x, y = x0, y0
    for i in range(n):
        u = i / (n - 1)
        a = ang + math.sin(t * 1.3 + ph - u * freq * 3.14) * amp * u + curl * u * u
        x += math.cos(a) * L / n
        y += math.sin(a) * L / n
        pts.append((x, y))
    return [(x0, y0)] + pts


def thick_line(L_, pts, w0, w1, col, a=1.0):
    n = len(pts)
    for i in range(n - 1):
        w = lerp(w0, w1, i / max(n - 2, 1))
        L_.line([pts[i], pts[i + 1]], col, w, a)


def jelly(L_, x, y, r, t, col, a=0.7, ph=0.0):
    pul = 1 + 0.12 * math.sin(t * 2.4 + ph)
    rx, ry = r * pul, r * 0.7 / pul
    pts = [(x + rx * math.cos(th), y - ry * math.sin(th)) for th in np.linspace(0, math.pi, 20)]
    pts += [(x - rx * (1 - 0.1 * k / 5), y + 0.12 * r * math.sin(k * 2 + t * 3)) for k in range(6)]
    L_.poly(pts, col, a * 0.55)
    for k in range(7):
        bx = x + (k - 3) / 3.5 * rx
        pts = [(bx + math.sin(t * 1.7 + k + j * 0.4 + ph) * r * 0.12 * j / 6, y + j * r * 0.35)
               for j in range(10)]
        L_.line(pts, col, 0.8, a * 0.5)


def submersible_white(L_, x, y, s, t, lights=1.0):
    """Сучасний білий батискаф (вигляд збоку)."""
    body = [(x + s * px, y + s * py) for px, py in
            [(-1.0, -0.35), (0.55, -0.42), (0.95, -0.2), (1.02, 0.1), (0.8, 0.38), (-0.9, 0.38), (-1.1, 0.05)]]
    L_.poly(body, C(225, 228, 230))
    L_.poly([(x - s * 1.0, y - s * 0.35), (x + s * 0.55, y - s * 0.42), (x + s * 0.5, y - s * 0.25),
             (x - s * 0.95, y - s * 0.2)], C(250, 250, 250))
    L_.rect(x - s * 0.9, y + s * 0.2, x + s * 0.7, y + s * 0.38, C(230, 110, 30))
    L_.ellipse(x + s * 0.72, y - s * 0.02, s * 0.17, s * 0.17, C(30, 60, 80))
    L_.ellipse(x + s * 0.76, y - s * 0.06, s * 0.05, s * 0.05, C(150, 200, 230), 0.8)
    L_.rect(x - s * 1.25, y - s * 0.12, x - s * 1.05, y + s * 0.12, C(80, 80, 85))
    L_.ellipse(x + s * 0.92, y + s * 0.25, s * 0.06, s * 0.06, C(255, 250, 220), lights)


def trieste(L_, x, y, s, squash=1.0, tone=1.0):
    """Батискаф «Трієст»: довгий поплавець, під ним маленька куля."""
    g = C(150, 155, 160) * tone
    gd = C(95, 100, 105) * tone
    fl = []
    for th in np.linspace(-math.pi / 2, math.pi / 2, 14):
        fl.append((x + s * squash * (0.9 + 0.2 * math.cos(th)), y + s * 0.2 * math.sin(th)))
    for th in np.linspace(math.pi / 2, 3 * math.pi / 2, 14):
        fl.append((x + s * squash * (-0.9 + 0.25 * math.cos(th)), y + s * 0.2 * math.sin(th)))
    L_.poly(fl, g)
    L_.poly([(x - s * squash * 0.9, y + s * 0.05), (x + s * squash * 0.9, y + s * 0.05),
             (x + s * squash * 0.9, y + s * 0.2), (x - s * squash * 0.9, y + s * 0.2)], gd)
    L_.rect(x - s * 0.06, y - s * 0.34, x + s * 0.06, y - s * 0.18, gd)  # рубка
    L_.rect(x - s * 0.04, y + s * 0.18, x + s * 0.04, y + s * 0.32, gd)  # шахта
    L_.ellipse(x, y + s * 0.42, s * 0.13, s * 0.13, C(70, 74, 80) * tone)
    L_.ellipse(x - s * 0.04, y + s * 0.38, s * 0.04, s * 0.04, C(120, 125, 130) * tone)


def men_silhouette(L_, x, y, s, col, lean=0.0):
    head = (x + lean * s * 0.1, y - s * 0.62)
    L_.ellipse(head[0], head[1], s * 0.16, s * 0.2, col)
    L_.poly([(x - s * 0.45, y + s * 0.4), (x - s * 0.38, y - s * 0.2), (x - s * 0.12, y - s * 0.38),
             (x + s * 0.12, y - s * 0.38), (x + s * 0.38, y - s * 0.2), (x + s * 0.45, y + s * 0.4)], col)


def seabed(img, horizon, col_near, col_far, seed=3, t=0.0, speed=0.0, tex=None):
    """Перспективна площина дна від horizon до низу кадру."""
    v = np.clip((YY - horizon) / (H - horizon), 0, 1)
    m = (YY > horizon).astype(np.float32)
    z = 1.0 / (v + 0.02)
    if tex is None:
        tex = fbm((256, 256), seed)
    u = ((XX - W / 2) / W * z * 0.6) % 1.0
    w = (z * 0.08 + t * speed) % 1.0
    ti = tex[(w * 255).astype(int) % 256, (u * 255).astype(int) % 256]
    col = col_far[None, None] * (1 - v[..., None]) + col_near[None, None] * v[..., None]
    col = col * (0.7 + 0.6 * ti[..., None])
    soft = smooth(horizon - 2, horizon + 25, YY)
    img[:] = img * (1 - soft[..., None] * m[..., None]) + col * (soft * m)[..., None]
    return img


# ================================================================ сцени
class Scene:
    def __init__(self, T):
        self.T = T

    def p(self, t):
        return t / self.T


class S01_Bathysphere(Scene):
    """Тісна сталева куля 1960 року, двоє чоловіків, жовта лампа, поштовх-наїзд."""

    def __init__(self, T, crack=False):
        super().__init__(T)
        self.crack = crack
        self.tex = fbm((H, W), 11, (90, 40, 16, 6))
        r = np.random.default_rng(5)
        self.drips = r.uniform(0, 1, (40, 3))
        self.dust = r.uniform(0, 1, (160, 3))
        self.snow = Snow(300, 7, 1.0)
        self.crk = self._crack_tree()

    def _crack_tree(self):
        r = np.random.default_rng(9)
        segs = []

        def grow(x, y, a, L, d, t0):
            if d > 5 or L < 4:
                return
            x2, y2 = x + math.cos(a) * L, y + math.sin(a) * L
            segs.append((x, y, x2, y2, t0, d))
            grow(x2, y2, a + r.uniform(-0.5, 0.5), L * 0.85, d + 1, t0 + 0.07)
            if r.random() < 0.55:
                grow(x2, y2, a + r.choice([-1, 1]) * r.uniform(0.6, 1.2), L * 0.6, d + 1, t0 + 0.09)

        for k in range(7):
            grow(0, 0, k / 7 * 6.28 + r.uniform(-0.3, 0.3), 38, 0, 0)
        return segs

    def frame(self, t):
        T = self.T
        p = t / T
        if not self.crack:
            zoomv = 1.0 + 0.12 * ease(p)
            ox, oy = 0, 0
            swing = math.sin(t * 0.9) * 0.08
        else:
            hit = smooth(0.08, 0.12, p) * (1 - smooth(0.12, 0.55, p))
            ox, oy = shake(t, 14 * hit)
            zoomv = 1.05
            swing = math.sin(t * 2.3) * 0.45 * (1 - smooth(0.1, 0.9, p)) + math.sin(t * 0.9) * 0.08
        cx, cy = W / 2 + ox, H / 2 + oy
        X = (XX - cx) / zoomv
        Y = (YY - cy) / zoomv
        # стіни кулі
        d = np.sqrt(X ** 2 + (Y * 1.15) ** 2) / (H * 0.95)
        lamp = (math.sin(swing) * 160, -H * 0.36 + math.cos(swing) * 30)
        dl = np.sqrt((X - lamp[0]) ** 2 + (Y - lamp[1]) ** 2)
        light = np.exp(-dl / 260) * 1.1 + 0.05
        steel = C(70, 62, 48) * (0.6 + 0.5 * self.tex[..., None])
        img = steel * light[..., None]
        # заклепки — кільця
        for rr in (0.55, 0.78):
            ring = np.abs(d - rr) < 0.004
            ang = np.arctan2(Y, X)
            dots = ring & (np.sin(ang * 46) > 0.6)
            img[dots] += C(140, 120, 80) * 0.6
        img *= (1 - smooth(0.85, 1.25, d))[..., None]
        # конденсат: стікають краплі
        for k, (u, v, s) in enumerate(self.drips):
            x = cx + (u - 0.5) * W * 1.1 * zoomv
            y0 = cy + (v - 0.6) * H * zoomv
            y = y0 + ((t * (8 + 20 * s)) % 120)
            add_glow(img, x, y, 1.6, C(255, 220, 160), 0.35 * light[int(np.clip(y, 0, H - 1)), int(np.clip(x, 0, W - 1))])
        # ілюмінатор праворуч
        px, py, pr = cx + 280 * zoomv, cy - 30 * zoomv, 70 * zoomv
        win = radial(px, py, pr, 0.01) > 0
        img[win] = C(1, 3, 6)
        inner = np.zeros_like(img)
        self.snow.render(inner, t, (0, 0.12, 0), C(90, 110, 130), 0.5)
        img[win] += inner[win]
        L_ = Layer()
        L_.ring(px, py, pr + 6 * zoomv, C(40, 36, 30), 12 * zoomv)
        L_.ring(px, py, pr + 6 * zoomv, C(140, 120, 90), 2 * zoomv, 0.5)
        # лампа
        lx, ly = cx + lamp[0] * zoomv, cy + lamp[1] * zoomv
        L_.line([(cx, cy - H * 0.55 * zoomv), (lx, ly)], C(30, 28, 25), 2)
        L_.ellipse(lx, ly, 14 * zoomv, 10 * zoomv, C(255, 220, 140))
        # двоє чоловіків (силуети з контровим світлом)
        for k, (mx, ms) in enumerate(((-210, 260), (40, 300))):
            bx = cx + mx * zoomv
            by = cy + 230 * zoomv
            men_silhouette(L_, bx, by, ms * zoomv, C(18, 15, 12), lean=(-0.6 if k == 0 else 0.4))
            L_.ellipse(bx + (12 if k else -6) * zoomv, by - ms * 0.62 * zoomv - 8 * zoomv,
                       ms * 0.14 * zoomv, ms * 0.17 * zoomv, C(120, 90, 55), 0.35)
        L_.comp(img)
        add_glow(img, lx, ly, 26 * zoomv, C(255, 200, 120), 0.9)
        add_glow(img, lx, ly, 90 * zoomv, C(255, 170, 90), 0.25)
        if self.crack:
            # пил, що сиплеться після удару
            hitp = smooth(0.1, 0.13, p)
            for u, v, s in self.dust:
                tt = max(t - 0.11 * T - s * 0.5, 0)
                if tt <= 0:
                    continue
                x = cx + (u - 0.5) * W * 1.1 + math.sin(tt * 3 + u * 9) * 6
                y = cy - H * 0.5 + (v * 0.4) * H + tt * tt * 60 * (0.5 + s)
                if 0 <= y < H:
                    add_glow(img, x, y, 1.2, C(220, 190, 140), 0.5 * hitp)
            # крупний план: тріщина на склі (друга половина сцени)
            k = smooth(0.42, 0.52, p)
            if k > 0:
                cp = np.zeros_like(img)
                rr = np.sqrt((XX - W / 2) ** 2 + (YY - H / 2) ** 2)
                glass = rr < 230
                cp[:] = C(3, 6, 10)
                cp[glass] = C(6, 14, 22) + 0.12 * np.exp(-((XX[glass] - W / 2 + 80) ** 2 + (YY[glass] - H / 2 + 90) ** 2) / 9000)[..., None] * C(120, 160, 190)
                cp[(rr >= 230) & (rr < 270)] = C(55, 50, 42)
                Lc = Layer()
                grow = (p - 0.55) / 0.35
                for x1, y1, x2, y2, t0, dd in self.crk:
                    if grow > t0:
                        f = min((grow - t0) / 0.07, 1)
                        sc = 2.8
                        Lc.line([(W / 2 - 40 + x1 * sc, H / 2 + 20 + y1 * sc),
                                 (W / 2 - 40 + (x1 + (x2 - x1) * f) * sc, H / 2 + 20 + (y1 + (y2 - y1) * f) * sc)],
                                C(220, 235, 245), max(2.4 - dd * 0.35, 0.6), 0.9)
                Lc.comp(cp, glow=0.6, glow_r=4)
                cs = shake(t, 4 * smooth(0.55, 0.6, p) * (1 - smooth(0.6, 0.9, p)), 3)
                cp = np.roll(cp, (int(cs[1]), int(cs[0])), (0, 1))
                img = img * (1 - k) + cp * k
        return finish(img, 0.5, sat=0.85)


class S03_TriesteDark(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(1100, 31, 1.6)

    def frame(self, t):
        p = t / self.T
        orb = -0.6 + 1.2 * p
        img = np.zeros((H, W, 3), np.float32) + C(1, 3, 7)
        x, y = W / 2, H * 0.42
        sq = 0.35 + 0.65 * abs(math.cos(orb))
        lights = []
        for side in (-0.45, 0.45):
            lx = x + side * 260 * sq * math.cos(orb)
            ly = y + 120
            lights.append((lx, ly))
        lm = np.zeros((H, W), np.float32)
        for lx, ly in lights:
            lm += cone((lx, ly), math.pi / 2 + 0.15 * math.sin(orb), 0.28, 420, 0.5) * 0.25
        img += lm[..., None] * C(150, 170, 160)
        self.snow.render(img, t, (math.sin(orb) * 0.15, 0.08, 0), C(140, 160, 170), 0.7, light=lm * 3)
        L_ = Layer()
        trieste(L_, x, y, 280, sq, tone=0.35)
        L_.comp(img)
        for lx, ly in lights:
            add_glow(img, lx, ly, 5, C(255, 240, 200), 1.2)
            add_glow(img, lx, ly, 22, C(200, 210, 190), 0.25)
        return finish(img, 0.6)


class S04_Guam(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.isl = edge_profile(400, 4, 1.0)
        self.snow = Snow(600, 41, 1.6)
        self.wave = fbm((256, 512), 42, (32, 16, 8))

    def frame(self, t):
        p = t / self.T
        tilt = ease(smooth(0.05, 0.62, p))
        hor = H * 0.42 - tilt * H * 0.75  # горизонт іде вгору — камера нахиляється вниз
        sky = vgrad([(0, C(60, 30, 80)), (0.5, C(230, 120, 70)), (1, C(255, 190, 120))])
        sea_v = np.clip((YY - hor) / (H - hor + 1e-3), 0, 1)
        z = 1 / (sea_v + 0.03)
        wv = self.wave[((z * 3 + t * 2) % 256).astype(int), ((XX / W * z * 40) % 512).astype(int)]
        sea = C(10, 70, 90)[None, None] * (1 - sea_v[..., None]) + C(20, 130, 140)[None, None] * sea_v[..., None]
        sea = sea * (0.75 + 0.5 * wv[..., None])
        sunx = W * 0.62
        spark = np.exp(-((XX - sunx) / (40 + 200 * sea_v)) ** 2) * (wv > 0.62) * (1 - sea_v) * 1.4
        sea += spark[..., None] * C(255, 200, 140)
        m = (YY > hor)[..., None]
        img = np.where(m, sea, sky)
        img += (np.exp(-np.abs(YY - hor) / 6) * 0.4)[..., None] * C(255, 180, 120) * (YY <= hor + 3)[..., None]
        add_glow(img, sunx, hor - 30, 26, C(255, 230, 170), 1.2)
        add_glow(img, sunx, hor - 30, 120, C(255, 150, 80), 0.3)
        L_ = Layer()
        n = len(self.isl)
        pts = [(W * 0.08 + i / n * W * 0.38, hor - 6 - 26 * smooth(0, 0.3, i / n) * (1 - smooth(0.7, 1, i / n)) * (1 + 0.3 * self.isl[i]))
               for i in range(n)]
        L_.poly(pts + [(W * 0.46, hor + 1), (W * 0.08, hor + 1)], C(25, 25, 45))
        L_.comp(img)
        # пірнання під воду
        k = smooth(0.62, 0.74, p)
        if k > 0:
            under = vgrad([(0, C(60, 170, 190)), (1, C(5, 40, 70))])
            under += god_rays(t, 0.35)[..., None] * C(150, 220, 230)
            self.snow.render(under, t, (0, 0.25, 0.3), C(200, 230, 240), 0.6)
            bub = smooth(0.62, 0.68, p) * (1 - smooth(0.7, 0.85, p))
            if bub > 0:
                r = np.random.default_rng(int(t * 24))
                for _ in range(90):
                    add_glow(under, r.uniform(0, W), r.uniform(0, H), r.uniform(2, 9), C(230, 250, 255), 0.5 * bub)
            img = img * (1 - k) + under * k
        return finish(img, 0.45)


class S05_Everest(Scene):
    """Розріз: Еверест у Маріанській западині, камера спускається вздовж гори."""

    def __init__(self, T):
        super().__init__(T)
        self.mt = edge_profile(500, 51, 1.0)
        self.tr = edge_profile(500, 52, 1.0)
        self.WH = H * 3.2  # висота світу в пікселях: 0 — поверхня, WH — 11 км

    def frame(self, t):
        p = t / self.T
        cam = ease(p) * (self.WH - H)  # верхня межа кадру у світі
        wy = YY + cam
        depth = wy / self.WH  # 0..1 = 0..11 км
        img = np.zeros((H, W, 3), np.float32)
        water = C(40, 120, 160)[None, None] * (1 - depth[..., None]) ** 2 + C(2, 8, 20)[None, None]
        img[:] = water
        sky = wy < 0
        img[sky] = C(150, 190, 220)
        L_ = Layer()
        # западина (V-подібна)
        prof = []
        for i in range(81):
            u = i / 80
            x = u * W
            dd = 0.32 + 0.68 * (1 - abs(u - 0.5) * 2) ** 0.6
            y = dd * self.WH + self.tr[int(u * 499)] * 18 - cam
            prof.append((x, y))
        L_.poly(prof + [(W, H + 10), (0, H + 10)], C(28, 24, 26))
        # Еверест: від дна (11 км) до 8.85 км угору => вершина на глибині ~2.1 км
        base_y = self.WH - cam
        peak_y = (2.1 / 11) * self.WH - cam
        mt = []
        for i in range(61):
            u = i / 60
            x = W * 0.08 + u * W * 0.84
            hgt = (1 - abs(u - 0.5) * 2) ** 0.9
            y = base_y - (base_y - peak_y) * hgt + self.mt[int(u * 499)] * 10 * hgt
            mt.append((x, y))
        L_.poly(mt + [(W * 0.92, base_y + 40), (W * 0.08, base_y + 40)], C(70, 74, 82))
        snow = [(x, y) for x, y in mt[26:35]]
        L_.poly(snow + [(snow[-1][0] - 10, snow[-1][1] + 20), (snow[0][0] + 10, snow[0][1] + 20)], C(210, 220, 230), 0.85)
        # мітки глибини
        for km in range(0, 12):
            y = km / 11 * self.WH - cam
            if -5 < y < H + 5:
                L_.line([(W - 60, y), (W - 30, y)], C(180, 210, 230), 1.4, 0.6)
                for m in range(1, 5):
                    yy = y + m / 5 * self.WH / 11
                    L_.line([(W - 45, yy), (W - 30, yy)], C(180, 210, 230), 1, 0.3)
        # поверхня води
        L_.line([(0, -cam), (W, -cam)], C(200, 230, 255), 2, 0.8)
        L_.comp(img)
        # світіння над вершиною, підкреслює "2 км води"
        add_glow(img, W / 2, peak_y - 40, 40, C(80, 160, 220), 0.25 * smooth(0.4, 0.7, p))
        return finish(img, 0.4)


class S06_Can(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(700, 61, 1.4)

    def frame(self, t):
        p = t / self.T
        img = vgrad([(0, C(10, 40, 80)), (1, C(2, 10, 25))])
        self.snow.render(img, t, (0, 0.06, 0), C(120, 170, 210), 0.6)
        crush = smooth(0.5, 0.56, p)
        cx = W / 2 + math.sin(t * 0.7) * 10
        cy = H * 0.3 + p * H * 0.25
        w0, h0 = 80, 150
        w = w0 * (1 - 0.45 * crush)
        h = h0 * (1 - 0.35 * crush)
        ang = 0.15 * math.sin(t * 0.5) + crush * 0.25
        L_ = Layer()
        n = 24
        left, right = [], []
        for i in range(n + 1):
            v = i / n
            wr = math.sin(v * 37 + 1.3) * 0.25 + math.sin(v * 13) * 0.2
            ww = w * (1 + crush * wr)
            y = (v - 0.5) * h
            left.append((-ww / 2, y))
            right.append((ww / 2 * (1 + crush * 0.2 * math.sin(v * 23)), y))
        body = rot(left + right[::-1], ang, cx, cy)
        L_.poly(body, C(170, 175, 185))
        band = rot([(-w / 2 * 1.02, -h * 0.15), (w / 2 * 1.02, -h * 0.2), (w / 2 * 1.02, h * 0.18), (-w / 2 * 1.02, h * 0.15)], ang, cx, cy)
        L_.poly(band, C(170, 30, 40))
        hl = rot([(-w * 0.25, -h * 0.48), (-w * 0.12, -h * 0.48), (-w * 0.12, h * 0.48), (-w * 0.25, h * 0.48)], ang, cx, cy)
        L_.poly(hl, C(240, 245, 255), 0.45)
        top = rot([(0, -h / 2)], ang, cx, cy)[0]
        L_.ellipse(top[0], top[1], w / 2, 8, C(200, 205, 215))
        L_.comp(img, glow=0.15, glow_r=10)
        if crush > 0:
            r = np.random.default_rng(3)
            for _ in range(70):
                a, s = r.uniform(0, 6.28), r.uniform(20, 160)
                k = max(t - 0.5 * self.T, 0)
                d = s * (1 - math.exp(-k * 3))
                add_glow(img, cx + math.cos(a) * d, cy + math.sin(a) * d - k * 40, r.uniform(1.5, 4), C(200, 230, 255), 0.5 * (1 - smooth(0.6, 0.9, p)))
        img += smooth(0.5, 0.52, p) * (1 - smooth(0.52, 0.6, p)) * 0.25 * C(150, 200, 255)
        return finish(img, 0.55)


class S07_Lights(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(1300, 71, 1.6)

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(3, 10, 24)
        on = smooth(0.18, 0.2, p) * (0.85 + 0.15 * (math.sin(t * 50) > -0.3 if p < 0.24 else 1))
        x, y = W * 0.45, H * 0.38 + p * 50
        lm = (cone((x + 96, y + 30), 0.65, 0.36, 700, 0.5) + cone((x + 90, y + 34), 1.15, 0.3, 600, 0.5)) * on
        img += lm[..., None] * C(150, 175, 180) * 0.45
        self.snow.render(img, t, (0, 0.18, 0), C(170, 190, 200), 0.8, light=lm * 2.5)
        L_ = Layer()
        submersible_white(L_, x, y, 110, t, on)
        L_.comp(img, glow=0.08)
        add_glow(img, x + 101, y + 27, 6, C(255, 250, 220), 1.5 * on)
        return finish(img, 0.55)


class S08_Reef(Scene):
    def __init__(self, T):
        super().__init__(T)
        r = np.random.default_rng(81)
        self.fish = r.uniform(0, 1, (70, 5))
        self.coral = [(r.uniform(0, W), r.uniform(0.6, 1.4), r.integers(0, 5)) for _ in range(26)]
        self.snow = Snow(400, 82, 1.6)

    def frame(self, t):
        p = t / self.T
        img = vgrad([(0, C(120, 220, 230)), (0.6, C(30, 140, 170)), (1, C(10, 70, 110))])
        img += god_rays(t, 0.5)[..., None] * C(220, 250, 255)
        cam = p * 120
        floor_y = H * 0.78 - cam * 0.8
        L_ = Layer()
        L_.poly([(0, floor_y + 40)] + [(x, floor_y + 20 * math.sin(x / 90)) for x in range(0, W + 40, 40)] + [(W, H), (0, H)], C(200, 190, 140))
        cols = [C(240, 110, 90), C(250, 180, 60), C(180, 90, 200), C(250, 130, 160), C(90, 200, 160)]
        for x, s, ci in self.coral:
            base = floor_y + 25 + 15 * math.sin(x)
            for b in range(5):
                a = -math.pi / 2 + (b - 2) * 0.35
                pts = tentacle(x, base, a, 60 * s, t * 0.5, 8, 0.15, 1.0, x + b)
                thick_line(L_, pts, 7 * s, 2 * s, cols[ci], 1.0)
        L_.comp(img)
        img += caustics(t)[..., None] * C(255, 255, 230) * 0.12
        L2 = Layer()
        fc = [C(255, 210, 60), C(60, 160, 255), C(255, 120, 60), C(250, 250, 250)]
        for i, (u, v, s, ph, ci) in enumerate(self.fish):
            school = i % 3
            x = (u * W * 1.4 + t * (40 + 25 * school) + 30 * math.sin(t + ph * 6)) % (W * 1.4) - W * 0.2
            y = H * (0.25 + 0.15 * school) + v * 90 + 12 * math.sin(t * 1.5 + ph * 6) - cam * 0.3
            draw_fish(L2, x, y, 18 + 10 * s, fc[int(ci * 4) % 4], 0.0, t + ph * 6, C(10, 10, 10))
        # дельфіни
        for k in range(2):
            dx = (t * 110 + k * 380) % (W + 600) - 300
            dy = H * 0.3 + k * 70 + 25 * math.sin(t * 1.2 + k)
            L2.poly(fish_shape(dx, dy, 190 - 30 * k, 0.05 * math.cos(t * 1.2 + k), 0.24, t * 6), C(110, 130, 150))
            L2.poly(rot([(10, -20), (30, -48), (45, -20)], 0, dx, dy), C(110, 130, 150))
        L2.comp(img)
        self.snow.render(img, t, (0, 0.1, 0), C(230, 250, 255), 0.3)
        return finish(img, 0.35)


class S09_Twilight(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(900, 91, 1.6)

    def frame(self, t):
        p = t / self.T
        dk = lerp(1.0, 0.25, p)
        img = vgrad([(0, C(40, 90, 150) * dk), (0.5, C(10, 35, 80) * dk), (1, C(2, 8, 25))])
        add_glow(img, W / 2, -60, 260, C(80, 140, 200), 0.6 * dk)
        self.snow.render(img, t, (0, 0.2, 0), C(130, 170, 210), 0.6)
        L_ = Layer()
        turn = ease(smooth(0.3, 0.75, p))
        for k, (x0, y0, s) in enumerate(((W * 0.35, H * 0.55, 110), (W * 0.68, H * 0.4, 80))):
            sq = lerp(1.0, 0.25, turn)
            x = x0 + math.sin(t * 0.6 + k) * 20
            y = y0 + math.cos(t * 0.5 + k) * 10
            if k == 0:  # риба-сокира: високе срібне тіло
                pts = [(x + s * sq * 0.5, y), (x + s * sq * 0.1, y - s * 0.45), (x - s * sq * 0.5, y - s * 0.1),
                       (x - s * sq * 0.7, y - s * 0.15), (x - s * sq * 0.7, y + s * 0.15), (x - s * sq * 0.4, y + s * 0.2),
                       (x + s * sq * 0.1, y + s * 0.55)]
                L_.poly(pts, C(150, 165, 185))
                L_.poly([(x + s * sq * 0.35, y - s * 0.05), (x - s * sq * 0.3, y + s * 0.05), (x + s * sq * 0.1, y + s * 0.45)], C(210, 220, 235), 0.5)
            else:  # світлоносний анчоус
                L_.poly(fish_shape(x, y, s * 1.6 * sq + s * 0.3, 0, 0.3, t * 5), C(90, 105, 130))
            ex = x + s * sq * (0.32 if k == 0 else 0.55) * (1 - turn) + 0
            for side in ((-1, 1) if turn > 0.5 else (0,)):
                exx = ex + side * s * 0.16 * turn
                L_.ellipse(exx, y - s * 0.12, s * 0.14, s * 0.14, C(15, 20, 25))
                L_.ellipse(exx - s * 0.03, y - s * 0.15, s * 0.05, s * 0.05, C(220, 240, 255))
        L_.comp(img, glow=0.1)
        return finish(img, 0.55)


class S10_Biolum(Scene):
    def __init__(self, T):
        super().__init__(T)
        r = np.random.default_rng(101)
        self.j = r.uniform(0, 1, (9, 4))
        self.sp = r.uniform(0, 1, (120, 4))

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(0, 1, 4)
        ra = t * 0.05
        L_ = Layer()
        cols = [C(80, 170, 255), C(90, 255, 200), C(255, 70, 90)]
        on = smooth(0.08, 0.25, p)
        for i, (u, v, s, c) in enumerate(self.j):
            x, y = (u - 0.5) * W * 1.2, (v - 0.5) * H * 1.1 - t * 6
            x, y = rot([(x, y)], ra)[0]
            jelly(L_, W / 2 + x, H / 2 + y, 25 + 40 * s, t, cols[int(c * 2.99)], 0.8 * on, i)
        # гребневики з веселковими хвилями
        for k in range(3):
            x = W * (0.2 + 0.3 * k) + 30 * math.sin(t * 0.4 + k)
            y = H * (0.3 + 0.2 * (k % 2)) + 20 * math.cos(t * 0.3 + k)
            x, y = rot([(x - W / 2, y - H / 2)], ra)[0]
            x += W / 2
            y += H / 2
            for row in range(6):
                th = row / 6 * math.pi
                for j in range(9):
                    v = j / 8
                    px = x + 26 * math.cos(th) * math.sin(v * math.pi)
                    py = y + (v - 0.5) * 80
                    hue = (v * 3 - t * 2 + row * 0.3) % 1
                    col = C(*(np.array([math.sin(hue * 6.28) * 0.5 + 0.5, math.sin(hue * 6.28 + 2.1) * 0.5 + 0.5,
                                        math.sin(hue * 6.28 + 4.2) * 0.5 + 0.5]) * 255))
                    L_.ellipse(px, py, 2.2, 2.2, col, on)
        L_.comp(img, glow=1.4, glow_r=10)
        for u, v, s, c in self.sp:
            ph = (t * (0.4 + s) + u * 10) % 3.0
            fl = math.exp(-((ph - 0.3) ** 2) / 0.02)
            if fl > 0.02:
                x, y = rot([((u - 0.5) * W, (v - 0.5) * H)], ra)[0]
                add_glow(img, W / 2 + x, H / 2 + y, 3 + 5 * s, cols[int(c * 2.99)], fl * 1.2 * on)
                add_glow(img, W / 2 + x, H / 2 + y, 18, cols[int(c * 2.99)], fl * 0.2 * on)
        return finish(img, 0.5)


class S11_Siphonophore(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(500, 111, 1.4)

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(0, 2, 6)
        self.snow.render(img, t, (0.02, 0.03, 0), C(60, 90, 120), 0.4)
        # хижак у глибині (силует закриває фон)
        px = -300 + p * (W + 600)
        L0 = Layer()
        L0.poly(fish_shape(px, H * 0.3, 520, 0, 0.32, t * 2), C(0, 0, 0))
        L0.comp(img)
        L_ = Layer()
        n = 46
        for i in range(n):
            u = i / (n - 1)
            x = W * 0.05 + u * W * 0.9
            y = H * 0.6 + 70 * math.sin(u * 5 + t * 0.6) + 30 * math.sin(u * 13 - t)
            r = 6 + 3 * math.sin(i * 1.7)
            br = 0.6 + 0.4 * math.sin(t * 3 - i * 0.5)
            L_.ellipse(x, y, r * 1.3, r, C(120, 200, 255), 0.6 * br)
            if i % 3 == 0:
                L_.line(tentacle(x, y, math.pi / 2, 50, t, 8, 0.4, 1.0, i), C(90, 160, 255), 0.8, 0.35)
        L_.comp(img, glow=1.2, glow_r=8)
        fx, fy = W * 0.7 + 30 * math.sin(t * 0.5), H * 0.3
        L2 = Layer()
        draw_fish(L2, fx, fy, 70, C(40, 40, 50), math.pi, t, C(10, 10, 10))
        L2.comp(img)
        for k in range(7):
            bl = 0.5 + 0.5 * math.sin(t * 4 + k * 0.9)
            add_glow(img, fx + 25 - k * 8, fy + 9, 2.2, C(120, 200, 255), bl * 1.4)
        return finish(img, 0.55)


class S12_Whale(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(900, 121, 1.6)
        self.skin = fbm((H, W), 122, (40, 12, 4))

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(1, 4, 10)
        lm = cone((-40, H * 0.35), 0.1, 0.5, 1100, 0.7)
        img += lm[..., None] * C(60, 90, 110) * 0.25
        x = W * 0.2 + p * W * 0.22
        y = H * 0.5 + 15 * math.sin(t * 0.4)
        L_ = Layer()
        L_.poly(whale_pts(x, y, 900, t, 0.06, flip=False), C(60, 62, 66))
        jaw = rot([(450, 0.1 * 900), (130, 0.12 * 900)], 0.06, x, y)
        L_.line(jaw, C(35, 36, 40), 3)
        ex, ey = rot([(300, 0.05 * 900)], 0.06, x, y)[0]
        L_.ellipse(ex, ey, 7, 5, C(15, 15, 18))
        rgb, al = L_.arrays()
        shade = (0.35 + lm * 1.6 + 0.25 * self.skin)[..., None]
        img = img * (1 - al[..., None]) + rgb * shade * al[..., None]
        self.snow.render(img, t, (-0.1, 0.05, 0), C(150, 170, 180), 0.6, light=lm * 2)
        return finish(img, 0.6)


class S13_Fight(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(1300, 131, 1.6)

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(2, 3, 8)
        lm = cone((W * 0.1, -30), 1.0, 0.45, 900, 0.6)
        img += lm[..., None] * C(70, 90, 100) * 0.3
        sx, sy = shake(t, 3)
        L_ = Layer()
        x, y = W * 0.55 + sx, H * 0.5 + sy
        L_.poly(whale_pts(x, y, 1000, t * 1.6, -0.12 + 0.05 * math.sin(t), flip=False), C(55, 55, 60))
        # шрами від присосок
        for k in range(18):
            cx = x + 120 + (k % 6) * 30 + 10 * math.sin(k)
            cy = y - 60 + (k // 6) * 40 - (cx - x) * 0.12
            L_.ring(cx, cy, 7, C(150, 150, 150), 1.5, 0.5)
        L_.comp(img)
        L2 = Layer()
        for k in range(8):
            ang = math.pi + (k - 3.5) * 0.25
            pts = tentacle(x + 330, y + 10 * (k - 4), ang + 0.6 * math.sin(t * 0.8 + k), 380, t * 1.5, 30, 0.9, 1.8, k, curl=-0.8 + 0.3 * k / 7)
            thick_line(L2, pts, 16, 3, C(150, 50, 40), 1.0)
            for j in range(4, 28, 3):
                L2.ellipse(pts[j][0], pts[j][1] + 3, 2.5, 2.5, C(230, 170, 150), 0.7)
        L2.comp(img)
        bright = (0.3 + lm * 1.4)
        img *= bright[..., None]
        self.snow.render(img, t, (0.15 * math.sin(t * 0.7), 0.1, 0.05), C(150, 170, 180), 0.9, rot=math.sin(t * 0.3) * 0.4)
        return finish(img, 0.65)


class S14_Squid(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(900, 141, 1.6)

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(1, 2, 6)
        s = lerp(0.3, 1.0, ease(p))
        x, y = W / 2, H * 0.48
        vis = smooth(0.0, 0.35, p)
        L_ = Layer()
        for k in range(10):
            ang = math.pi / 2 + (k - 4.5) * 0.2 * (1 + p)
            pts = tentacle(x, y + 70 * s, ang, (260 + 40 * (k % 3)) * s, t, 24, 0.5 * (1 + p), 1.5, k)
            thick_line(L_, pts, 18 * s, 2 * s, C(170, 40, 35), vis)
        mantle = [(x - 70 * s, y + 10 * s), (x - 62 * s, y - 180 * s), (x - 30 * s, y - 300 * s), (x, y - 330 * s),
                  (x + 30 * s, y - 300 * s), (x + 62 * s, y - 180 * s), (x + 70 * s, y + 10 * s)]
        L_.poly(mantle, C(185, 52, 44), vis)
        L_.poly([(x - 35 * s, y - 280 * s), (x - 120 * s, y - 330 * s), (x - 10 * s, y - 335 * s)], C(165, 45, 40), vis)
        L_.poly([(x + 35 * s, y - 280 * s), (x + 120 * s, y - 330 * s), (x + 10 * s, y - 335 * s)], C(165, 45, 40), vis)
        L_.ellipse(x, y + 30 * s, 75 * s, 60 * s, C(175, 48, 40), vis)
        L_.comp(img)
        img *= (0.25 + 0.9 * radial(W / 2, H * 0.55, W * 0.7, 1.2))[..., None]
        for side in (-1, 1):
            ex, ey = x + side * 52 * s, y + 25 * s
            L2 = Layer()
            L2.ellipse(ex, ey, 26 * s, 26 * s, C(25, 20, 15), vis)
            L2.ellipse(ex, ey, 16 * s, 16 * s, C(5, 5, 8), vis)
            L2.comp(img)
            add_glow(img, ex - 7 * s, ey - 8 * s, 4 * s, C(220, 240, 255), 0.9 * vis)
        self.snow.render(img, t, (0, 0.03, 0.15), C(120, 140, 160), 0.6)
        return finish(img, 0.6)


class S15_Titanic(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(900, 151, 1.6)
        self.rust = fbm((H, W * 2), 152, (60, 20, 6))
        self.tex = fbm((256, 256), 153)

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(2, 5, 9)
        seabed(img, H * 0.62, C(60, 55, 45), C(10, 12, 14), tex=self.tex, t=t, speed=0.02)
        pan = -p * 260
        L_ = Layer()
        bx = W * 0.62 + pan
        hull = [(bx - 700, H * 0.7), (bx - 700, H * 0.24), (bx - 80, H * 0.22), (bx + 150, H * 0.16),
                (bx + 175, H * 0.17), (bx + 70, H * 0.55), (bx - 30, H * 0.78), (bx - 700, H * 0.78)]
        L_.poly(hull, C(95, 50, 30))
        for k in range(14):
            L_.line([(bx - 690 + k * 50, H * 0.215 - 18), (bx - 690 + k * 50, H * 0.225)], C(80, 45, 30), 2)
        L_.line([(bx - 700, H * 0.2 - 18), (bx - 80, H * 0.2 - 22), (bx + 150, H * 0.16 - 16)], C(80, 45, 30), 2.5)
        for k in range(8):
            L_.ellipse(bx - 560 + k * 60, H * 0.36, 6, 6, C(15, 10, 8))
        rgb, al = L_.arrays()
        sh = int(-pan) % W
        rust = np.roll(self.rust[:, :W], -sh, axis=1)
        lm = cone((W * 0.5, -60), math.pi / 2, 0.55, 750, 0.8)
        shade = (0.35 + 0.6 * rust + lm * 0.8)[..., None]
        dr = (rust > 0.62) * (YY > H * 0.25) * smooth(0.6, 0.75, rust)
        col = rgb * shade * (1 + 0.6 * dr[..., None] * C(255, 150, 80) / 255)
        img = img * (1 - al[..., None]) + col * al[..., None]
        img += lm[..., None] * C(50, 70, 80) * 0.15
        self.snow.render(img, t, (0.05, 0.03, 0), C(160, 170, 180), 0.6, light=lm * 2)
        # вудильник пропливає перед об'єктивом
        k = smooth(0.45, 1.0, p)
        if k > 0:
            ax = W * 1.2 - k * W * 1.3
            ay = H * 0.55 + 20 * math.sin(t)
            L2 = Layer()
            body = [(ax + 120 * math.cos(a), ay + 80 * math.sin(a) * (1 - 0.3 * math.cos(a))) for a in np.linspace(0, 6.28, 30)]
            L2.poly(body, C(25, 22, 22))
            L2.poly([(ax + 110, ay), (ax + 220, ay - 40), (ax + 230, ay + 50)], C(20, 18, 18))
            L2.poly([(ax - 110, ay + 10), (ax - 60, ay + 40), (ax - 120, ay + 30)], C(220, 220, 210))  # зуби
            for z in range(7):
                L2.poly([(ax - 115 + z * 12, ay + 12), (ax - 109 + z * 12, ay + 30), (ax - 103 + z * 12, ay + 12)], C(230, 230, 220))
            lure = tentacle(ax - 40, ay - 70, -2.2, 110, t, 10, 0.2, 1.0, 0, curl=-1.2)
            L2.line(lure, C(40, 40, 40), 2.5)
            L2.comp(img)
            lx, ly = lure[-1]
            add_glow(img, lx, ly, 6, C(150, 255, 230), 1.6)
            add_glow(img, lx, ly, 40, C(80, 200, 180), 0.35)
        return finish(img, 0.6)


class S16_Plain(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(800, 161, 1.6)
        self.tex = fbm((256, 256), 162)
        r = np.random.default_rng(163)
        self.obj = [(r.uniform(-3, 3), r.uniform(2, 30), r.integers(0, 3)) for _ in range(22)]

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(4, 8, 14)
        hor = H * 0.38
        seabed(img, hor, C(110, 105, 95), C(8, 10, 14), tex=self.tex, t=t, speed=0.05)
        lm = cone((W / 2, H * 0.2), math.pi / 2 + 0.2, 0.7, 700, 0.6)
        img *= (0.35 + lm * 1.2)[..., None]
        L_ = Layer()
        zcam = t * 1.2
        for x, z, kind in sorted(self.obj, key=lambda o: -((o[1] - zcam) % 30)):
            zz = (z - zcam) % 30 + 1.0
            sx = W / 2 + x / zz * 400
            sy = hor + (H - hor) * 1.2 / zz * 1.6 + 6
            s = 260 / zz
            if sy > H + 40 or s < 1:
                continue
            fog = math.exp(-zz / 12)
            if kind == 0:  # голотурія
                L_.ellipse(sx, sy - s * 0.35, s * 0.9, s * 0.35, C(220, 120, 140) * fog, 0.8)
                for l in range(6):
                    L_.line([(sx - s * 0.6 + l * s * 0.24, sy - s * 0.05), (sx - s * 0.6 + l * s * 0.24 + math.sin(t * 3 + l) * s * 0.06, sy + s * 0.05)], C(220, 130, 150) * fog, 1)
            elif kind == 1:  # скляна губка
                pts = [(sx - s * 0.18, sy), (sx - s * 0.3, sy - s * 1.2), (sx + s * 0.3, sy - s * 1.2), (sx + s * 0.18, sy)]
                L_.poly(pts, C(200, 210, 200) * fog, 0.55)
            else:  # риба-тринога
                L_.line([(sx - s * 0.3, sy), (sx - s * 0.1, sy - s * 0.5)], C(200, 200, 190) * fog, 1)
                L_.line([(sx + s * 0.3, sy), (sx + s * 0.1, sy - s * 0.5)], C(200, 200, 190) * fog, 1)
                L_.poly(fish_shape(sx, sy - s * 0.6, s * 1.1, 0, 0.25, 0), C(150, 150, 140) * fog)
        L_.comp(img)
        self.snow.render(img, t, (0, 0.02, 0.3), C(150, 160, 170), 0.6, light=lm * 2)
        return finish(img, 0.6)


class S17_Isopod(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(700, 171, 1.6)
        self.tex = fbm((256, 256), 172)

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(3, 6, 10)
        seabed(img, H * 0.45, C(90, 85, 75), C(10, 10, 12), tex=self.tex)
        lm = cone((W * 0.3, -50), 1.2, 0.6, 900, 0.6)
        img *= (0.3 + lm * 1.1)[..., None]
        L_ = Layer()
        # туша кита на задньому плані
        wx, wy = W * 0.78, H * 0.52
        L_.ellipse(wx, wy + 10, 280, 60, C(95, 80, 78))
        for k in range(9):
            cx_ = wx - 170 + k * 42
            arc = [(cx_ + 18 * math.sin(a), wy + 10 - 85 * math.sin(a * 0.5 + 0.2)) for a in np.linspace(0, 3.0, 9)]
            L_.line(arc, C(220, 215, 200), 5)
        L_.line([(wx - 200, wy - 30), (wx + 220, wy - 45)], C(225, 220, 205), 8)
        # мiксини, що звиваються
        for k in range(5):
            pts = tentacle(wx - 200 + k * 90, wy - 40, -1.2 + 0.3 * k, 70, t * 2 + k, 12, 0.7, 2, k)
            thick_line(L_, pts, 4, 2, C(150, 120, 120), 0.9)
        # ізопод на передньому плані
        ix = W * 0.12 + ease(p) * W * 0.3
        iy = H * 0.8
        s = 230
        for seg in range(9):
            u = seg / 8
            sx = ix + (u - 0.5) * s
            hh = s * 0.32 * math.sin(math.pi * (0.15 + u * 0.7))
            L_.ellipse(sx, iy - hh * 0.4, s * 0.075, hh * 0.55 + 4, C(185, 175, 160))
            L_.line([(sx, iy - hh * 0.9), (sx, iy + hh * 0.1)], C(120, 110, 100), 1.5)
            for side in (-1, 1):
                leg = math.sin(t * 6 + seg) * 6
                L_.line([(sx, iy), (sx + leg, iy + 14)], C(150, 140, 120), 2)
        L_.ellipse(ix + s * 0.55, iy - s * 0.06, s * 0.09, s * 0.07, C(170, 160, 145))
        L_.ellipse(ix + s * 0.6, iy - s * 0.08, s * 0.03, s * 0.025, C(30, 40, 30))
        L_.line([(ix + s * 0.6, iy - s * 0.1), (ix + s * 0.85, iy - s * 0.25 + math.sin(t * 2) * 8)], C(170, 160, 140), 2)
        L_.comp(img)
        self.snow.render(img, t, (0, 0.03, 0), C(150, 160, 170), 0.5, light=lm * 2)
        return finish(img, 0.6)


class S18_Bloop(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(600, 181, 1.6)

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(1, 4, 10)
        cx, cy = W * 0.7, H * 0.4
        d = np.sqrt((XX - cx) ** 2 + ((YY - cy) * 1.6) ** 2)
        rings = np.zeros((H, W), np.float32)
        for k in range(6):
            r = ((t * 70 + k * 120) % 720)
            fade = 1 - r / 720
            rings += np.exp(-((d - r) / 6) ** 2) * fade
        img += rings[..., None] * C(80, 180, 255) * 0.6 * smooth(0.05, 0.25, p)
        add_glow(img, cx, cy, 30, C(80, 160, 255), 0.4 * (0.6 + 0.4 * math.sin(t * 2)))
        self.snow.render(img, t, (0, 0.02, 0), C(100, 140, 170), 0.5)
        L_ = Layer()
        bx, by = W * 0.2, H * 0.95
        L_.poly([(bx - 150, H + 10), (bx - 90, by - 60), (bx + 90, by - 60), (bx + 150, H + 10)], C(10, 14, 18))
        L_.rect(bx - 12, by - 260, bx + 12, by - 60, C(14, 18, 22))
        L_.ellipse(bx, by - 290, 30, 50, C(18, 22, 28))
        L_.line([(bx, by - 340), (bx, by - 400)], C(18, 22, 28), 3)
        L_.comp(img)
        add_glow(img, bx, by - 400, 4, C(255, 60, 40), 0.8 + 0.6 * (math.sin(t * 3) > 0.7))
        add_glow(img, bx + 25, by - 290, 30, C(80, 180, 255), rings[int(by - 290), int(bx + 25)] * 2)
        return finish(img, 0.55)


class S19_Ice(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.edge = edge_profile(400, 191, 1.0)
        self.snow = Snow(700, 192, 1.6)
        r = np.random.default_rng(193)
        self.blocks = [(r.uniform(0.15, 0.85), r.uniform(0.0, 0.6), r.uniform(40, 120), r.uniform(-1, 1)) for _ in range(9)]

    def frame(self, t):
        p = t / self.T
        cam = ease(p) * H * 1.2
        img = vgrad([(0, C(60, 140, 170)), (1, C(5, 25, 45))])
        img *= (1 - p * 0.6)
        img += god_rays(t, 0.25)[..., None] * C(160, 220, 240) * (1 - p)
        L_ = Layer()
        n = len(self.edge)
        top = -cam * 0.6
        pts = [(i / (n - 1) * W, top + H * 0.28 + self.edge[i] * 30 + (60 if i / n > 0.55 else 0)) for i in range(n)]
        L_.poly([(0, -500)] + pts + [(W, -500)], C(200, 235, 245))
        for x0, t0, s, sp in self.blocks:
            tt = t - t0 * self.T
            if tt < 0:
                continue
            bx = x0 * W + sp * 20 * tt
            by = top + H * 0.32 + 30 * tt * tt * 0.5 + 40 * tt
            pts = rot([(-s, -s * 0.6), (s * 0.9, -s * 0.7), (s, s * 0.5), (-s * 0.8, s * 0.6)], sp * tt * 0.4, bx, by)
            L_.poly(pts, C(170, 215, 230), 0.95)
        L_.comp(img, glow=0.25, glow_r=16)
        self.snow.render(img, t, (0, -0.12, 0), C(210, 240, 250), 0.5)
        return finish(img, 0.5)


class S20_Trench(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.le = edge_profile(1200, 201, 1.0)
        self.re = edge_profile(1200, 202, 1.0)
        self.tex = fbm((H * 3, W), 203, (50, 20, 8, 3))
        self.snow = Snow(800, 204, 1.6)

    def frame(self, t):
        p = t / self.T
        scroll = t * 45
        img = np.zeros((H, W, 3), np.float32) + C(0, 1, 3)
        ys = (YY + scroll).astype(int) % (H * 3)
        tex = self.tex[ys, XX.astype(int)]
        idx = ((YY + scroll) * 0.4).astype(int) % 1200
        narrow = 0.18 + 0.1 * p
        lx = W * narrow + self.le[idx] * 50 + (YY / H) * 80
        rx = W * (1 - narrow) + self.re[idx] * 50 - (YY / H) * 80
        wall = (XX < lx) | (XX > rx)
        lm = cone((W / 2, H * 0.15), math.pi / 2, 0.9, 600, 0.5) + 0.06
        rock = C(45, 42, 40)[None, None] * (0.4 + 0.9 * tex[..., None])
        img = np.where(wall[..., None], rock * (lm[..., None] * 2.2 + 0.12), img)
        img *= (1 - smooth(0.55, 1.0, YY / H) * 0.75)[..., None]
        self.snow.render(img, t, (0, 0.25, 0), C(120, 140, 160), 0.6, light=lm)
        if (t % 1.6) < 0.25:
            add_glow(img, W * 0.5 + 6, H * 0.12, 3, C(255, 40, 30), 1.6)
            add_glow(img, W * 0.5 + 6, H * 0.12, 20, C(255, 40, 30), 0.25)
        return finish(img, 0.6)


class S21_Snailfish(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(700, 211, 1.6)
        self.tex = fbm((256, 256), 212)

    def frame(self, t):
        p = t / self.T
        z = lerp(1.0, 1.35, ease(p))
        img = np.zeros((H, W, 3), np.float32) + C(3, 5, 9)
        seabed(img, H * 0.62, C(80, 75, 65), C(8, 9, 11), tex=self.tex)
        lm = cone((W * 0.5, -40), math.pi / 2, 0.6, 800, 0.7)
        img *= (0.3 + lm)[..., None]
        L_ = Layer()
        cx, cy = W * 0.78, H * 0.62
        for k in range(5):
            L_.line([(cx - 60 + k * 30, cy - 70), (cx - 60 + k * 30, cy + 20)], C(140, 140, 140), 1.5, 0.7)
        for k in range(4):
            L_.line([(cx - 60, cy - 70 + k * 30), (cx + 60, cy - 70 + k * 30)], C(140, 140, 140), 1.5, 0.7)
        L_.comp(img)
        L2 = Layer()
        fx = W * 0.45 + 30 * math.sin(t * 0.3)
        fy = H * 0.48 + 10 * math.sin(t * 0.5)
        s = 230 * z
        body = []
        for i in range(25):
            u = i / 24
            body.append((fx + (0.5 - u) * s, fy - s * 0.18 * (1 - u) ** 0.7 * math.sin(math.pi * (u * 0.9 + 0.1)) - math.sin(t * 2 - u * 6) * s * 0.03 * u))
        for i in range(24, -1, -1):
            u = i / 24
            body.append((fx + (0.5 - u) * s, fy + s * 0.15 * (1 - u) ** 0.7 * math.sin(math.pi * (u * 0.9 + 0.1)) - math.sin(t * 2 - u * 6) * s * 0.03 * u))
        L2.poly(body, C(240, 190, 200), 0.55)
        L2.ellipse(fx + s * 0.2, fy, s * 0.08, s * 0.06, C(170, 70, 80), 0.6)
        L2.ellipse(fx + s * 0.08, fy + s * 0.03, s * 0.06, s * 0.04, C(200, 120, 90), 0.5)
        L2.line([(fx + s * 0.35, fy), (fx - s * 0.4, fy - s * 0.01)], C(250, 230, 230), 1.5, 0.5)
        L2.ellipse(fx + s * 0.4, fy - s * 0.05, s * 0.025, s * 0.025, C(30, 30, 40), 0.9)
        L2.comp(img, glow=0.25, glow_r=10)
        self.snow.render(img, t, (0, 0.02, 0.05), C(160, 170, 180), 0.6, light=lm * 2)
        return finish(img, 0.6)


class S22_Amphipods(Scene):
    def __init__(self, T):
        super().__init__(T)
        r = np.random.default_rng(221)
        self.a = r.uniform(0, 1, (150, 4))
        self.tex = fbm((256, 256), 222)
        self.lump = fbm((H, W), 223, (30, 12, 5, 2))
        self.snow = Snow(600, 224, 1.6)

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(2, 3, 6)
        k = smooth(0.52, 0.6, p)
        if k < 1:
            a = img.copy()
            seabed(a, H * 0.55, C(70, 65, 58), C(6, 7, 9), tex=self.tex)
            lm = cone((W * 0.5, H * 0.1), math.pi / 2, 0.55, 600, 0.6)
            a *= (0.25 + lm)[..., None]
            L_ = Layer()
            bx, by = W / 2, H * 0.72
            L_.ellipse(bx, by, 80, 30, C(170, 120, 100))
            for i, (u, v, s, ph) in enumerate(self.a):
                ang = t * (1 + s) + ph * 6.28
                rad = 40 + 160 * u * (1 + 0.3 * math.sin(t * 2 + i))
                x = bx + math.cos(ang) * rad
                y = by - 20 + math.sin(ang) * rad * 0.4 - v * 60
                pts = [(x + math.cos(ang + 1.57 + j * 0.25) * 8, y + math.sin(ang + 1.57 + j * 0.25) * 4) for j in range(-3, 4)]
                L_.line(pts, C(235, 225, 210), 3)
            L_.comp(a)
            self.snow.render(a, t, (0, 0.02, 0), C(150, 160, 170), 0.5, light=lm * 2)
            img = a * (1 - k)
        if k > 0:
            b = np.zeros_like(img) + C(3, 4, 6)
            seabed(b, H * 0.3, C(90, 82, 70), C(15, 14, 13), tex=self.tex)
            rr = np.sqrt(((XX - W / 2) / 260) ** 2 + ((YY - H * 0.58) / 170) ** 2) + (self.lump - 0.5) * 0.5
            m = smooth(1.0, 0.9, rr)
            lump = C(190, 170, 140)[None, None] * (0.4 + 0.9 * self.lump[..., None]) * (1.2 - rr[..., None] * 0.6)
            b = b * (1 - m[..., None]) + lump * m[..., None]
            lm = cone((W * 0.2, -20), 1.0, 0.7, 900, 0.6)
            b *= (0.3 + lm)[..., None]
            img += b * k
        return finish(img, 0.6)


class S23_Deck1960(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.wave = fbm((256, 512), 231, (32, 12, 5))
        self.grain = np.random.default_rng(232)

    def frame(self, t):
        p = t / self.T
        hor = H * 0.36
        img = vgrad([(0, C(170, 180, 175)), (0.36, C(200, 200, 185)), (0.37, C(70, 90, 95)), (1, C(30, 50, 60))])
        sea_v = np.clip((YY - hor) / (H - hor), 0, 1)
        z = 1 / (sea_v + 0.04)
        wv = self.wave[((z * 4 + t * 3) % 256).astype(int), ((XX / W * z * 30 + t * 4) % 512).astype(int)]
        img += ((YY > hor) * (wv - 0.5) * 0.25)[..., None]
        dolly = p * 120
        L_ = Layer()
        yb = H * 0.55 + 6 * math.sin(t * 0.8)
        s_ = 330
        trieste(L_, W * 0.55 - dolly, yb, s_, 1.0, tone=0.9)
        for k, (mx, ms) in enumerate(((-0.05, 62), (0.035, 66))):
            x = W * 0.55 - dolly + mx * W
            men_silhouette(L_, x, yb - s_ * 0.2 - ms * 0.4, ms, C(40, 40, 45))
            L_.rect(x - ms * 0.3, yb - s_ * 0.2 - ms * 0.02, x - ms * 0.06, yb - s_ * 0.2 + 2, C(40, 40, 45))
            L_.rect(x + ms * 0.06, yb - s_ * 0.2 - ms * 0.02, x + ms * 0.3, yb - s_ * 0.2 + 2, C(40, 40, 45))
        L_.comp(img)
        g = img.mean(axis=2, keepdims=True)
        img = g * C(255, 225, 180) * 1.05 * (0.92 + 0.08 * math.sin(t * 17))
        if self.grain.random() < 0.3:
            x = self.grain.uniform(0, W)
            img[:, int(x):int(x) + 1] *= 0.6
        return finish(img, 0.75, sat=0.7)


class S24_Cutaway(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(600, 241, 1.6)

    def frame(self, t):
        p = t / self.T
        img = vgrad([(0, C(8, 25, 45)), (1, C(2, 6, 14))])
        self.snow.render(img, t, (0, 0.12, 0), C(110, 150, 180), 0.5)
        sq = 0.55 + 0.45 * math.cos(-0.7 + p * 1.4)
        x, y = W / 2, H * 0.4 + p * 30
        s = 330
        L_ = Layer()
        trieste(L_, x, y, s, sq, tone=0.85)
        for k in range(6):
            cx = x + (k - 2.5) / 2.9 * s * 0.85 * sq
            L_.rect(cx - s * 0.11 * sq, y - s * 0.12, cx + s * 0.11 * sq, y + s * 0.14, C(230, 190, 70), 0.75)
        L_.ellipse(x, y + s * 0.42, s * 0.1, s * 0.1, C(30, 30, 35))
        L_.ellipse(x - s * 0.03, y + s * 0.44, s * 0.03, s * 0.04, C(210, 170, 120))
        L_.ellipse(x + s * 0.04, y + s * 0.44, s * 0.03, s * 0.04, C(210, 170, 120))
        L_.comp(img)
        L2 = Layer()
        pul = 0.5 + 0.5 * math.sin(t * 3)
        sx, sy = x, y + s * 0.42
        for k in range(12):
            a = k / 12 * 6.28
            r0, r1 = s * 0.42 + 14 * pul, s * 0.2
            x0, y0 = sx + math.cos(a) * r0, sy + math.sin(a) * r0 * 0.8
            x1, y1 = sx + math.cos(a) * r1, sy + math.sin(a) * r1 * 0.8
            L2.line([(x0, y0), (x1, y1)], C(255, 90, 70), 3, 0.8)
            ha = math.atan2(y1 - y0, x1 - x0)
            L2.poly([(x1, y1), (x1 - 12 * math.cos(ha - 0.5), y1 - 12 * math.sin(ha - 0.5)), (x1 - 12 * math.cos(ha + 0.5), y1 - 12 * math.sin(ha + 0.5))], C(255, 90, 70), 0.8)
        L2.comp(img, glow=0.5, glow_r=6)
        return finish(img, 0.5)


class S25_WindowCrack(S01_Bathysphere):
    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(1, 3, 6)
        hit = smooth(0.12, 0.15, p) * (1 - smooth(0.15, 0.55, p))
        ox, oy = shake(t, 16 * hit, 5)
        cx, cy = W / 2 + ox, H / 2 + oy
        rr = np.sqrt((XX - cx) ** 2 + (YY - cy) ** 2)
        glass = rr < 210
        img[glass] = C(5, 12, 20)
        img[(rr >= 210) & (rr < 260)] = C(70, 72, 75) * 0.6
        bolts = (np.abs(rr - 235) < 7) & (np.sin(np.arctan2(YY - cy, XX - cx) * 12) > 0.85)
        img[bolts] = C(120, 120, 125)
        inner = np.zeros_like(img)
        Snow(400, 251, 1.0).render(inner, t, (0, 0.2 * smooth(0.6, 0.9, p) + 0.04, 0), C(120, 150, 170), 0.6)
        img[glass] += inner[glass]
        Lc = Layer()
        grow = (p - 0.14) / 0.25
        for x1, y1, x2, y2, t0, dd in self.crk:
            if grow > t0:
                f = min((grow - t0) / 0.07, 1)
                sc = 2.6
                Lc.line([(cx + x1 * sc, cy + y1 * sc), (cx + (x1 + (x2 - x1) * f) * sc, cy + (y1 + (y2 - y1) * f) * sc)],
                        C(220, 235, 245), max(2.6 - dd * 0.4, 0.6), 0.9)
        Lc.comp(img, glow=0.7, glow_r=4)
        if p > 0.14:
            r = np.random.default_rng(7)
            k = t - 0.14 * self.T
            for _ in range(40):
                a, v = r.uniform(0, 6.28), r.uniform(30, 120)
                add_glow(img, cx + math.cos(a) * v * k, cy + math.sin(a) * v * k + 30 * k * k, 1.5, C(200, 230, 255), max(0, 0.8 - k * 0.4))
        img += hit * 0.2 * C(200, 220, 255)
        return finish(img, 0.55)


class S26_Landing(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.tex = fbm((256, 256), 261)
        self.silt = fbm((H, W), 262, (80, 40, 20, 10))
        self.silt2 = fbm((H, W), 263, (60, 30, 15))
        self.snow = Snow(700, 264, 1.6)

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(2, 4, 7)
        floor = H * 0.8
        img[YY > floor] = C(70, 65, 55) * 0.5
        land = smooth(0.0, 0.42, p)
        y = lerp(H * 0.25, floor - 0.62 * 260, ease(land))
        L_ = Layer()
        trieste(L_, W / 2, y, 260, 1.0, tone=0.55)
        L_.comp(img)
        lights = [(W / 2 - 70, y + 0.42 * 260), (W / 2 + 70, y + 0.42 * 260)]
        lm = np.zeros((H, W), np.float32)
        for lx, ly in lights:
            lm += cone((lx, ly), math.pi / 2, 0.45, 400, 0.6) * 0.35
        img += lm[..., None] * C(160, 170, 160) * 0.6
        img[YY > floor] *= (0.4 + lm[YY > floor] * 2)[..., None]
        self.snow.render(img, t, (0, 0.03, 0), C(140, 150, 160), 0.5, light=lm * 2)
        k = smooth(0.4, 0.95, p)
        if k > 0:
            cloud = np.roll(self.silt, int(t * 6), axis=1) * 0.6 + np.roll(self.silt2, -int(t * 4), axis=1) * 0.4
            rad = k * W * 0.6
            d = np.sqrt((XX - W / 2) ** 2 + ((YY - floor) * 1.8) ** 2)
            m = smooth(rad, rad * 0.4, d + (cloud - 0.5) * 220) * smooth(0.2, 0.7, cloud + k * 0.4)
            col = C(110, 100, 85) * (0.3 + lm[..., None] * 1.5) * (0.6 + 0.6 * cloud[..., None])
            img = img * (1 - m[..., None] * 0.92) + col * m[..., None] * 0.9
        for lx, ly in lights:
            add_glow(img, lx, ly, 5, C(255, 250, 220), 1.2 * (1 - k * 0.8))
        return finish(img, 0.6)


class S27_Porthole(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.silt = fbm((H, W), 271, (90, 40, 18, 8))
        self.tex = fbm((256, 256), 272)

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(3, 4, 5)
        view = np.zeros_like(img) + C(20, 22, 20)
        seabed(view, H * 0.35, C(110, 100, 85), C(30, 30, 28), tex=self.tex)
        L_ = Layer()
        fx, fy = W * 0.5 + 15 * math.sin(t * 0.2), H * 0.66
        L_.ellipse(fx, fy, 95, 20, C(180, 170, 150), 0.7)
        L_.poly([(fx - 95, fy), (fx - 140, fy - 18), (fx - 140, fy + 18)], C(180, 170, 150), 0.5)
        L_.comp(view, extra_blur=4)
        haze = smooth(0.3, 0.9, p)
        cloud = np.roll(self.silt, int(t * 5), axis=1)
        view = view * (1 - (0.35 + 0.6 * haze) * cloud[..., None]) + C(90, 85, 70) * ((0.35 + 0.6 * haze) * cloud)[..., None]
        view = blur(view, 1.5 + 2 * haze)
        rr = np.sqrt((XX - W / 2) ** 2 + (YY - H / 2) ** 2)
        m = rr < 200
        img[m] = view[m]
        ring = (rr >= 200) & (rr < 250)
        img[ring] = C(40, 40, 42)
        img += (np.exp(-((rr - 200) / 3) ** 2) * 0.3)[..., None] * C(200, 210, 220)
        return finish(img, 0.75)


class S28_Challenger(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(900, 281, 1.6)
        self.tex = fbm((256, 256), 282)

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(1, 3, 6)
        reveal = smooth(0.45, 0.8, p)
        if reveal > 0:
            bed = img.copy()
            seabed(bed, H * lerp(0.95, 0.55, ease(reveal)), C(140, 140, 135), C(40, 40, 42), tex=self.tex)
            lm = cone((W * 0.5, H * 0.3), math.pi / 2, 0.8, 900, 0.5)
            bed *= (0.2 + lm * 1.3)[..., None]
            img = img * (1 - reveal) + bed * reveal
        x = W * 0.5
        y = lerp(-80, H * 0.35, ease(smooth(0, 0.5, p)))
        L_ = Layer()
        L_.poly([(x - 22, y - 170), (x + 22, y - 170), (x + 30, y + 120), (x, y + 150), (x - 30, y + 120)], C(150, 200, 40))
        L_.rect(x - 34, y + 60, x + 34, y + 90, C(120, 160, 30))
        L_.rect(x - 70, y - 40, x - 30, y - 30, C(180, 180, 170))
        L_.comp(img)
        lm2 = cone((x, y + 150), math.pi / 2, 0.5, 600, 0.6) * smooth(0.1, 0.2, p)
        img += lm2[..., None] * C(140, 150, 150) * 0.35
        self.snow.render(img, t, (0, 0.2 * (1 - reveal) + 0.02, 0), C(150, 160, 170), 0.6, light=lm2 * 2)
        add_glow(img, x, y + 150, 5, C(255, 250, 230), 1.3 * smooth(0.1, 0.2, p))
        return finish(img, 0.6)


class S29_LimitingFactor(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(800, 291, 1.6)
        self.tex = fbm((256, 256), 292)

    def frame(self, t):
        p = t / self.T
        img = np.zeros((H, W, 3), np.float32) + C(2, 4, 7)
        seabed(img, H * 0.62, C(100, 96, 88), C(15, 15, 16), tex=self.tex)
        y = lerp(H * 0.15, H * 0.5, ease(smooth(0, 0.35, p)))
        x = W * 0.35
        sweep = math.pi / 2 + 0.9 * math.sin(min(p, 0.8) * 7) * (1 - smooth(0.6, 0.8, p)) - 0.5 * smooth(0.6, 0.8, p)
        lm = cone((x + 95, y + 30), sweep - 0.3, 0.3, 800, 0.6) * smooth(0.3, 0.4, p)
        img *= (0.25 + lm * 1.6)[..., None]
        img += lm[..., None] * C(100, 110, 110) * 0.2
        L_ = Layer()
        submersible_white(L_, x, y, 100, t, 1.0)
        L_.comp(img)
        self.snow.render(img, t, (0, 0.02, 0), C(150, 160, 170), 0.6, light=lm * 2)
        tx, ty = W * 0.75, H * 0.78
        add_glow(img, tx, ty, 18, C(220, 220, 230), 0.25 * smooth(0.75, 0.95, p))
        return finish(img, 0.6)


class S30_Plastic(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.snow = Snow(900, 301, 1.6)
        self.tex = fbm((256, 256), 302)
        self.crumple = fbm((H, W), 303, (24, 10, 4))

    def frame(self, t):
        p = t / self.T
        z = lerp(1.0, 1.5, ease(p))
        img = np.zeros((H, W, 3), np.float32) + C(2, 3, 5)
        seabed(img, H * 0.4, C(105, 100, 92), C(12, 12, 13), tex=self.tex)
        lm = cone((W * 0.5, -80), math.pi / 2, 0.38, 900, 0.35)
        img *= (0.12 + lm * 1.6)[..., None]
        cx, cy = W / 2, H * 0.68
        L_ = Layer()
        bag = []
        for a in np.linspace(0, 6.28, 40):
            r = 1 + 0.18 * math.sin(a * 5 + 1) + 0.1 * math.sin(a * 11) + 0.03 * math.sin(t + a * 3)
            bag.append((cx + math.cos(a) * 150 * z * r, cy + math.sin(a) * 55 * z * r))
        L_.poly(bag, C(235, 238, 240), 0.55)
        L_.line([(cx + 120 * z, cy - 20 * z), (cx + 190 * z, cy - 60 * z + 6 * math.sin(t * 0.8)), (cx + 170 * z, cy - 10 * z)], C(235, 238, 240), 6 * z, 0.5)
        for k, (wx, wy, col) in enumerate(((-260, 30, C(220, 40, 60)), (230, 45, C(250, 200, 40)), (-120, 70, C(60, 120, 230)))):
            pts = rot([(-30, -12), (-10, -16), (10, -10), (30, -14), (28, 12), (5, 16), (-28, 12)], 0.3 * k, cx + wx * z, cy + wy * z)
            pts = [(cx + (px - cx), cy + (py - cy)) for px, py in pts]
            L_.poly([(px * 1, py) for px, py in pts], col, 0.95)
        rgb, al = L_.arrays()
        cr = (0.7 + 0.6 * self.crumple)[..., None]
        img = img * (1 - al[..., None]) + rgb * cr * (0.25 + lm[..., None] * 1.4) * al[..., None]
        self.snow.render(img, t, (0, 0.05, 0), C(170, 175, 180), 0.6, light=lm * 3)
        return finish(img, 0.65, sat=0.9)


class S31_MoonGlobe(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.tex = fbm((256, 256), 311)
        self.land = fbm((300, 600), 312, (60, 30, 12))
        self.stars = np.random.default_rng(313).uniform(0, 1, (160, 3))

    def frame(self, t):
        p = t / self.T
        k = smooth(0.48, 0.62, p)
        a = np.zeros((H, W, 3), np.float32)
        if k < 1:
            left = np.zeros((H, W, 3), np.float32)
            for u, v, s in self.stars:
                if u < 0.5:
                    left[int(v * H * 0.5), int(u * W)] += s * 0.8
            seabed(left, H * 0.55, C(150, 150, 150), C(80, 80, 80), tex=self.tex)
            add_glow(left, W * 0.38, H * 0.18, 18, C(80, 140, 255), 0.6)
            L_ = Layer()
            ax, ay = W * 0.25, H * 0.7
            L_.ellipse(ax, ay - 70, 16, 18, C(230, 230, 230))
            L_.rect(ax - 18, ay - 55, ax + 18, ay, C(225, 225, 225))
            L_.rect(ax - 16, ay, ax - 4, ay + 30, C(215, 215, 215))
            L_.rect(ax + 4, ay, ax + 16, ay + 30, C(215, 215, 215))
            L_.ellipse(ax + 4, ay - 70, 9, 8, C(200, 160, 60))
            L_.comp(left)
            right = np.zeros((H, W, 3), np.float32) + C(1, 3, 7)
            seabed(right, H * 0.55, C(70, 68, 62), C(8, 9, 10), tex=self.tex)
            lm = cone((W * 0.72 + 50, H * 0.45), 1.1, 0.4, 500, 0.6)
            right *= (0.25 + lm * 1.5)[..., None]
            L2 = Layer()
            submersible_white(L2, W * 0.72, H * 0.45, 60, t, 1.0)
            L2.comp(right)
            a = np.where((XX < W / 2)[..., None], left, right)
            a[:, W // 2 - 1: W // 2 + 1] = 0.6
            pull = 1 + 0.1 * p
            a = a * (1 - k)
        if k > 0:
            b = np.zeros((H, W, 3), np.float32)
            for u, v, s in self.stars:
                b[int(v * (H - 1)), int(u * (W - 1))] += s * 0.6
            R = lerp(380, 220, ease(smooth(0.5, 1.0, p)))
            dx, dy = (XX - W / 2) / R, (YY - H / 2) / R
            rr = dx * dx + dy * dy
            m = rr < 1
            zz = np.sqrt(np.clip(1 - rr, 0, 1))
            lon = (np.arctan2(dx, zz) / math.pi * 0.5 + 0.5 + t * 0.02) % 1
            lat = np.arcsin(np.clip(dy, -1, 1)) / math.pi + 0.5
            li = self.land[(lat * 299).astype(int), (lon * 599).astype(int)]
            landm = li > 0.56
            mapped = (np.sin(lon * 6.28 * 7) > 0.55) & ~landm
            col = np.where(landm[..., None], C(60, 80, 55), C(4, 10, 25))
            col = np.where(mapped[..., None], C(30, 90, 140), col)
            shade = (0.25 + 0.9 * np.clip(dx * -0.4 + dy * -0.3 + zz * 0.8, 0, 1))
            b[m] = (col * shade[..., None])[m]
            b += (np.exp(-((np.sqrt(rr) - 1) / 0.03) ** 2) * 0.5)[..., None] * C(80, 140, 255)
            a = a + b * k
        return finish(a, 0.45)


class S32_Eyes(Scene):
    def __init__(self, T):
        super().__init__(T)
        self.wave = fbm((256, 512), 321, (32, 12, 5))
        self.snow = Snow(600, 322, 1.6)

    def frame(self, t):
        p = t / self.T
        hor = H * 0.45 + 4 * math.sin(t * 0.6) + smooth(0.2, 0.42, p) * H * 0.4
        sky = vgrad([(0, C(4, 8, 20)), (1, C(20, 30, 55))])
        sea_v = np.clip((YY - hor) / (H - hor + 1e-3), 0, 1)
        z = 1 / (sea_v + 0.03)
        wv = self.wave[((z * 3 + t * 1.5) % 256).astype(int), ((XX / W * z * 30) % 512).astype(int)]
        sea = C(5, 12, 25)[None, None] * (0.6 + 0.6 * wv[..., None])
        path = np.exp(-((XX - W * 0.55) / (20 + 160 * sea_v)) ** 2) * (wv > 0.6) * 1.2
        sea += path[..., None] * C(200, 210, 230)
        img = np.where((YY > hor)[..., None], sea, sky)
        add_glow(img, W * 0.55, hor - 150, 22, C(230, 235, 250), 1.2)
        add_glow(img, W * 0.55, hor - 150, 90, C(120, 140, 200), 0.25)
        k = smooth(0.4, 0.48, p)
        if k > 0:
            under = vgrad([(0, C(10, 25, 45)), (0.5, C(1, 3, 8)), (1, C(0, 0, 0))])
            under *= (1 - smooth(0.5, 0.85, p) * 0.85)
            self.snow.render(under, t, (0, 0.3 * (1 - smooth(0.6, 0.8, p)), 0), C(90, 110, 140), 0.5 * (1 - smooth(0.6, 0.85, p)))
            img = img * (1 - k) + under * k
        e = smooth(0.82, 0.92, p)
        if e > 0:
            for side in (-1, 1):
                ex, ey = W / 2 + side * 46, H * 0.55
                h = 7 * e
                L_ = Layer()
                L_.ellipse(ex, ey, 15, h, C(200, 230, 120), 0.9)
                L_.ellipse(ex, ey, 2.5, h * 0.9, C(0, 0, 0), 1.0)
                L_.comp(img, glow=1.5, glow_r=8)
        fade = 1 - smooth(0.965, 0.985, p)
        return finish(img, 0.6, fade=fade)


SCENE_CLASSES = [
    lambda T: S01_Bathysphere(T, False), lambda T: S01_Bathysphere(T, True), S03_TriesteDark, S04_Guam,
    S05_Everest, S06_Can, S07_Lights, S08_Reef, S09_Twilight, S10_Biolum, S11_Siphonophore, S12_Whale,
    S13_Fight, S14_Squid, S15_Titanic, S16_Plain, S17_Isopod, S18_Bloop, S19_Ice, S20_Trench,
    S21_Snailfish, S22_Amphipods, S23_Deck1960, S24_Cutaway, S25_WindowCrack, S26_Landing, S27_Porthole,
    S28_Challenger, S29_LimitingFactor, S30_Plastic, S31_MoonGlobe, S32_Eyes,
]
