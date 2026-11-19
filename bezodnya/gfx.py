"""Невелика 2.5D графічна бібліотека для процедурних підводних сцен (numpy + Pillow + scipy).

Усе малюється у float32 RGB 0..1 у внутрішній роздільності W x H (потім ffmpeg масштабує до 1080p).
"""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import gaussian_filter, zoom

W, H = 960, 540
YY, XX = np.mgrid[0:H, 0:W].astype(np.float32)


def C(*rgb):
    """Колір з 0..255 у float."""
    return np.array(rgb, np.float32) / 255.0


def clamp01(x):
    return np.clip(x, 0.0, 1.0)


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------- фони
def vgrad(stops):
    """Вертикальний градієнт: stops = [(pos 0..1, color), ...]."""
    pos = np.array([s[0] for s in stops], np.float32)
    cols = np.array([s[1] for s in stops], np.float32)
    v = YY[:, :1] / (H - 1)
    out = np.empty((H, 1, 3), np.float32)
    for c in range(3):
        out[:, 0, c] = np.interp(v[:, 0], pos, cols[:, c])
    return np.repeat(out, W, axis=1)


def radial(cx, cy, r, power=2.0):
    d = np.sqrt((XX - cx) ** 2 + (YY - cy) ** 2) / max(r, 1e-3)
    return np.clip(1 - d, 0, 1) ** power


def add_glow(img, cx, cy, r, col, a=1.0):
    """Адитивне гаусове світіння в обмежувальному прямокутнику."""
    r = max(r, 0.5)
    x0, x1 = int(max(cx - 3 * r, 0)), int(min(cx + 3 * r + 1, W))
    y0, y1 = int(max(cy - 3 * r, 0)), int(min(cy + 3 * r + 1, H))
    if x0 >= x1 or y0 >= y1:
        return
    xs = XX[y0:y1, x0:x1] - cx
    ys = YY[y0:y1, x0:x1] - cy
    g = np.exp(-(xs * xs + ys * ys) / (2 * r * r)) * a
    img[y0:y1, x0:x1] += g[..., None] * col


def blur(a, s):
    if s <= 0:
        return a
    if a.ndim == 3:
        return gaussian_filter(a, (s, s, 0))
    return gaussian_filter(a, s)


def fast_blur(a, s):
    """Розмиття великого радіуса через зменшення в 4 рази."""
    if s < 4:
        return blur(a, s)
    k = 4
    small = a[::k, ::k]
    small = blur(small, s / k)
    if a.ndim == 3:
        big = zoom(small, (k, k, 1), order=1)
    else:
        big = zoom(small, (k, k), order=1)
    out = np.zeros_like(a)
    hh, ww = min(big.shape[0], a.shape[0]), min(big.shape[1], a.shape[1])
    out[:hh, :ww] = big[:hh, :ww]
    return out


# ---------------------------------------------------------------- векторні шари
class Layer:
    """RGBA-шар, намальований PIL із суперсемплінгом 2x."""

    SS = 2

    def __init__(self):
        self.im = Image.new("RGBA", (W * self.SS, H * self.SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    @staticmethod
    def _c(col, a=1.0):
        c = np.clip(np.asarray(col, np.float32), 0, 1)
        return (int(c[0] * 255), int(c[1] * 255), int(c[2] * 255), int(np.clip(a, 0, 1) * 255))

    def _p(self, pts):
        s = self.SS
        return [(float(x) * s, float(y) * s) for x, y in pts]

    def poly(self, pts, col, a=1.0):
        if len(pts) >= 3:
            self.d.polygon(self._p(pts), fill=self._c(col, a))

    def ellipse(self, cx, cy, rx, ry, col, a=1.0):
        s = self.SS
        self.d.ellipse([(cx - rx) * s, (cy - ry) * s, (cx + rx) * s, (cy + ry) * s], fill=self._c(col, a))

    def line(self, pts, col, w=1.0, a=1.0):
        if len(pts) >= 2:
            self.d.line(self._p(pts), fill=self._c(col, a), width=max(1, int(round(w * self.SS))), joint="curve")

    def ring(self, cx, cy, r, col, w=1.0, a=1.0):
        s = self.SS
        self.d.ellipse([(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s],
                       outline=self._c(col, a), width=max(1, int(w * s)))

    def rect(self, x0, y0, x1, y1, col, a=1.0):
        s = self.SS
        self.d.rectangle([x0 * s, y0 * s, x1 * s, y1 * s], fill=self._c(col, a))

    def arrays(self, extra_blur=0):
        im = self.im.resize((W, H), Image.BILINEAR)
        if extra_blur:
            im = im.filter(ImageFilter.GaussianBlur(extra_blur))
        a = np.asarray(im, np.float32) / 255.0
        return a[..., :3], a[..., 3]

    def comp(self, img, glow=0.0, glow_r=12, extra_blur=0, opacity=1.0):
        rgb, al = self.arrays(extra_blur)
        al = al * opacity
        img *= 1 - al[..., None]
        img += rgb * al[..., None]
        if glow > 0:
            img += fast_blur(rgb * al[..., None], glow_r) * glow
        return img


# ---------------------------------------------------------------- частинки (морський сніг)
class Snow:
    def __init__(self, n=900, seed=1, spread=1.6):
        r = np.random.default_rng(seed)
        self.p = np.stack([r.uniform(-spread, spread, n), r.uniform(-1, 1, n) * spread * 0.6,
                           r.uniform(0.25, 3.0, n)], 1).astype(np.float32)
        self.ph = r.uniform(0, 6.28, n).astype(np.float32)
        self.br = r.uniform(0.4, 1.0, n).astype(np.float32)
        self.spread = spread

    def render(self, img, t, vel=(0.0, -0.05, 0.0), col=C(170, 200, 220), amount=1.0,
               light=None, rot=0.0, f=520.0):
        """vel — швидкість камери у світі (x, y, z) за секунду; y>0 — частинки летять угору."""
        p = self.p.copy()
        sp = self.spread
        p[:, 0] = (p[:, 0] - vel[0] * t + 0.02 * np.sin(t * 0.5 + self.ph) + sp) % (2 * sp) - sp
        p[:, 1] = (p[:, 1] - vel[1] * t + 0.6 * sp) % (1.2 * sp) - 0.6 * sp
        p[:, 2] = (p[:, 2] - 0.25 - vel[2] * t) % 2.75 + 0.25
        if rot:
            c, s = math.cos(rot), math.sin(rot)
            x, y = p[:, 0].copy(), p[:, 1].copy()
            p[:, 0], p[:, 1] = c * x - s * y, s * x + c * y
        sx = W / 2 + p[:, 0] / p[:, 2] * f
        sy = H / 2 + p[:, 1] / p[:, 2] * f
        ok = (sx > -5) & (sx < W + 5) & (sy > -5) & (sy < H + 5)
        z = p[:, 2]
        bri = self.br * np.clip(1.2 - z / 3.2, 0, 1) * amount
        far = ok & (z > 0.9)
        near = ok & (z <= 0.9)
        buf = np.zeros((H, W), np.float32)
        xi = np.clip(sx[far].astype(int), 0, W - 1)
        yi = np.clip(sy[far].astype(int), 0, H - 1)
        np.add.at(buf, (yi, xi), bri[far])
        buf = blur(buf, 0.7) * 2.2
        buf2 = np.zeros((H, W), np.float32)
        xi = np.clip(sx[near].astype(int), 0, W - 1)
        yi = np.clip(sy[near].astype(int), 0, H - 1)
        np.add.at(buf2, (yi, xi), bri[near] * 9)
        buf2 = fast_blur(buf2, 2.2)
        tot = buf + buf2
        if light is not None:
            tot = tot * (0.15 + light)
        img += tot[..., None] * col
        return img


# ---------------------------------------------------------------- світло
def cone(apex, angle, spread, length, soft=0.35):
    """Маска конуса світла: apex (x,y), angle — напрям у радіанах (0 — вправо, pi/2 — вниз)."""
    dx = XX - apex[0]
    dy = YY - apex[1]
    d = np.sqrt(dx * dx + dy * dy) + 1e-3
    ang = np.arctan2(dy, dx) - angle
    ang = (ang + np.pi) % (2 * np.pi) - np.pi
    m = np.clip(1 - np.abs(ang) / spread, 0, 1)
    m = smooth(0, soft, m)
    fall = np.clip(1 - d / length, 0, 1) ** 1.6
    near = smooth(0, 30, d)
    return m * fall * near


def god_rays(t, strength=0.4, top=0.0, angle=0.25, speed=0.15):
    u = XX / W + (YY / H) * angle
    r = (np.sin(u * 23 + t * speed * 7) * 0.5 + 0.5) * (np.sin(u * 51 - t * speed * 5 + 1.3) * 0.5 + 0.5)
    r = r ** 3
    fade = np.clip(1 - (YY / H - top) * 1.2, 0, 1) ** 1.5
    return r * fade * strength


def caustics(t, scale=1.0):
    u, v = XX / W * 9 * scale, YY / H * 5 * scale
    a = np.sin(u + np.sin(v * 1.3 + t * 0.9) * 1.5 + t * 0.6)
    b = np.sin(v * 1.7 + np.sin(u * 0.8 - t * 0.7) * 1.7 - t * 0.5)
    return np.clip(1 - np.abs(a + b) * 0.9, 0, 1) ** 4


# ---------------------------------------------------------------- шум
def value_noise(shape, scale, seed):
    r = np.random.default_rng(seed)
    gh, gw = int(shape[0] / scale) + 3, int(shape[1] / scale) + 3
    g = r.random((gh, gw)).astype(np.float32)
    z = zoom(g, (scale, scale), order=3)
    return z[: shape[0], : shape[1]]


def fbm(shape, seed, scales=(64, 32, 16, 8)):
    out = np.zeros(shape, np.float32)
    amp, tot = 1.0, 0.0
    for i, s in enumerate(scales):
        out += value_noise(shape, s, seed + i) * amp
        tot += amp
        amp *= 0.5
    return out / tot


def edge_profile(n, seed, rough=1.0):
    """1D шум для обрисів скель."""
    r = np.random.default_rng(seed)
    x = np.zeros(n, np.float32)
    for k, a in ((3, 1.0), (7, 0.5), (17, 0.25), (41, 0.12), (97, 0.06)):
        ph = r.uniform(0, 6.28)
        x += a * np.sin(np.linspace(0, k * 3.14, n) + ph) * rough
    return x


# ---------------------------------------------------------------- фінальна обробка
def finish(img, vignette=0.55, lift=0.0, sat=1.0, fade=1.0, tint=None):
    if tint is not None:
        img = img * tint
    if sat != 1.0:
        g = img.mean(axis=2, keepdims=True)
        img = g + (img - g) * sat
    v = 1 - vignette * (((XX - W / 2) / (W / 2)) ** 2 * 0.6 + ((YY - H / 2) / (H / 2)) ** 2 * 0.6)
    img = img * np.clip(v, 0, 1)[..., None]
    img = img + lift
    # м'яке "плівкове" стискання світлих ділянок
    img = 1 - np.exp(-np.maximum(img, 0) * 1.35)
    img = img / (1 - math.exp(-1.35))
    return np.clip(img * fade, 0, 1)


def to_u8(img):
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
