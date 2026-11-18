"""Render the 16:9 YouTube video: frames (numpy/PIL) + mixed audio + burned ASS subtitles."""
import os, sys, subprocess, math, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy.ndimage import gaussian_filter, zoom, map_coordinates

sys.path.insert(0, os.path.dirname(__file__))
from subs import flatten

ROOT = sys.argv[1]  # vid dir
OUT = os.path.join(ROOT, "out"); os.makedirs(OUT, exist_ok=True)
PREVIEW = [float(x) for x in sys.argv[2:]]  # optional preview times
W, H, FPS = 1920, 1080, 30
SR = 48000
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
rng = np.random.default_rng(7)

# ------------------------------------------------------------------ timeline
LEAD, GAP, OUTRO = 1.2, 1.1, 4.0
TOPICS = [
    ("01", "01", "КИТ 52 ГЕРЦ"),
    ("03", "02", "НАЙТИХІША КІМНАТА"),
    ("06", "03", "ТИХОХОДКИ В КОСМОСІ"),
    ("07", "04", "ОКО КОЛОСАЛЬНОГО КАЛЬМАРА"),
    ("08", "05", "ЧУЖИЙ ГОЛОС"),
]


def load_voice(seg):
    p = os.path.join(ROOT, "audio", f"{seg}.mp3")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


voices = {seg: load_voice(seg) for seg, _, _ in TOPICS}
starts, t = {}, LEAD
for seg, _, _ in TOPICS:
    starts[seg] = t
    t += len(voices[seg]) / SR + GAP
TOTAL = t - GAP + OUTRO
# topic visual windows: from (start - GAP/2) to next start - GAP/2
windows = []
for i, (seg, num, title) in enumerate(TOPICS):
    a = 0.0 if i == 0 else starts[seg] - GAP / 2
    b = (starts[TOPICS[i + 1][0]] - GAP / 2) if i + 1 < len(TOPICS) else TOTAL
    windows.append((a, b, seg, num, title))
print("total", TOTAL, starts, file=sys.stderr)


# ------------------------------------------------------------------ helpers
def fbm(h, w, scales=(4, 8, 16, 32, 64), seed=0):
    r = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32); amp = 1.0; tot = 0
    for s in scales:
        g = r.random((s + 1, int(s * w / h) + 2)).astype(np.float32)
        z = zoom(g, (h / s, h / s), order=3)[:h, :w]
        acc += amp * z; tot += amp; amp *= 0.55
    acc /= tot
    return (acc - acc.min()) / (acc.max() - acc.min() + 1e-6)


def to_img(a):
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


def from_img(im):
    return np.asarray(im.convert("RGB"), np.float32) / 255.0


def kenburns(base_img, u, z0=1.0, z1=1.12, c0=(0.5, 0.5), c1=(0.5, 0.5)):
    """base_img PIL, u in [0,1]. zoom relative to fit-to-16:9."""
    bw, bh = base_img.size
    e = u * u * (3 - 2 * u) * 0.6 + u * 0.4
    z = z0 + (z1 - z0) * e
    cx = c0[0] + (c1[0] - c0[0]) * e; cy = c0[1] + (c1[1] - c0[1]) * e
    cw = bw / z; ch = cw * H / W
    if ch > bh / z: ch = bh / z; cw = ch * W / H
    x0 = min(max(cx * bw - cw / 2, 0), bw - cw); y0 = min(max(cy * bh - ch / 2, 0), bh - ch)
    return from_img(base_img.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch)))


def soft_layer(draw_fn, scale=2, blur=6):
    """draw on a half-res L canvas then blur & upsample -> float HxW."""
    im = Image.new("L", (W // scale, H // scale), 0)
    draw_fn(ImageDraw.Draw(im), 1.0 / scale)
    a = np.asarray(im, np.float32) / 255.0
    g = gaussian_filter(a, blur / scale) if blur else a
    return np.array(Image.fromarray(g.astype(np.float32), "F").resize((W, H), Image.BILINEAR))


YY, XX = np.mgrid[0:H, 0:W].astype(np.float32)
VIGNETTE = (1 - 0.55 * (((XX - W / 2) / (W * 0.62)) ** 2 + ((YY - H / 2) / (H * 0.70)) ** 2)).clip(0.25, 1)[..., None]
GRAIN = [(rng.standard_normal((H // 2, W // 2)).astype(np.float32)) for _ in range(6)]
GRAIN = [np.asarray(Image.fromarray(g, "F").resize((W, H), Image.BILINEAR))[..., None] for g in GRAIN]


def grade(img, fi):
    img = img * VIGNETTE
    # teal shadows / amber highlights split tone
    lum = img.mean(axis=2, keepdims=True)
    img = img + (0.035 * (1 - lum) * np.array([-0.4, 0.2, 0.5], np.float32)) + (0.04 * lum * np.array([0.5, 0.2, -0.4], np.float32))
    img = img + GRAIN[fi % len(GRAIN)] * 0.022
    return img


def particles(n, seed, t, speed=(6, -10), size=(1, 3.5), bright=0.5, depth=True):
    r = np.random.default_rng(seed)
    px = r.random(n) * W; py = r.random(n) * H; z = r.random(n) * 0.8 + 0.2
    ph = r.random(n) * 6.28
    def draw(d, s):
        for i in range(n):
            x = (px[i] + speed[0] * t * z[i] + 8 * math.sin(t * 0.7 + ph[i])) % W
            y = (py[i] + speed[1] * t * z[i]) % H
            rr = (size[0] + (size[1] - size[0]) * z[i]) * s * 2
            v = int(255 * bright * (0.4 + 0.6 * z[i]) * (0.6 + 0.4 * math.sin(t * 1.3 + ph[i])))
            d.ellipse([x * s - rr, y * s - rr, x * s + rr, y * s + rr], fill=v)
    return soft_layer(draw, 2, 2.5)


# ------------------------------------------------------------------ assets
def load_ai(name, scale=1.6):
    im = Image.open(os.path.join(ROOT, "img", name)).convert("RGB")
    return im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)


IMG_WHALE = load_ai("whale.png"); IMG_SCI = load_ai("scientist.png")
BW, BH = 2304, 1296


def build_foam():
    cell = 96
    yy, xx = np.mgrid[0:BH, 0:BW].astype(np.float32)
    u = (xx % cell) / cell; v = (yy % cell) / cell
    ci = (xx // cell).astype(int); cj = (yy // cell).astype(int)
    alt = ((ci + cj) % 2 == 1)
    # wedges: alternating horizontal / vertical ridges
    uu = np.where(alt, v, u)
    face_a = uu < 0.5
    shade_h = np.where(face_a, 0.78, 0.42)
    shade_v = np.where(face_a, 0.62, 0.30)
    shade = np.where(alt, shade_h, shade_v)
    ridge = np.abs(uu - 0.5) * 2  # 0 at ridge
    shade = shade * (0.75 + 0.25 * ridge) + 0.12 * (1 - ridge) ** 6
    groove = np.minimum(np.minimum(u, 1 - u), np.minimum(v, 1 - v))
    shade *= np.clip(groove * 14, 0.25, 1.0)
    tex = fbm(BH, BW, (40, 120, 300), seed=3)
    shade *= 0.85 + 0.3 * tex
    light = np.exp(-(((xx - BW * 0.5) / (BW * 0.45)) ** 2 + ((yy - BH * 0.15) / (BH * 0.8)) ** 2))
    shade = shade * (0.18 + 0.82 * light)
    base = np.array([0.42, 0.46, 0.52], np.float32)
    img = shade[..., None] * base
    return to_img(img)


def shaded_ellipse(acc, alpha, cx, cy, a, b, col, light=(-0.45, -0.6, 0.66), ang=0.0, bands=0, rim=0.35):
    R_ = max(a, b) + 2
    x0, x1 = int(max(cx - R_, 0)), int(min(cx + R_, acc.shape[1]))
    y0, y1 = int(max(cy - R_, 0)), int(min(cy + R_, acc.shape[0]))
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dx, dy = xx - cx, yy - cy
    ca, sa = math.cos(ang), math.sin(ang)
    rx = (dx * ca + dy * sa) / a; ry = (-dx * sa + dy * ca) / b
    r2 = rx * rx + ry * ry
    m = np.clip((1 - r2) * a * 0.5, 0, 1)
    nz = np.sqrt(np.clip(1 - r2, 0, 1))
    L = np.array(light, np.float32); L /= np.linalg.norm(L)
    lam = np.clip(rx * L[0] + ry * L[1] + nz * L[2], 0, 1)
    sh = 0.18 + 0.82 * lam + rim * (1 - nz) ** 3
    if bands:
        sh *= 0.85 + 0.15 * np.cos(rx * math.pi * bands) ** 2
    spec = np.clip(rx * L[0] + ry * L[1] + nz * L[2], 0, 1) ** 30 * 0.5
    c = sh[..., None] * np.array(col, np.float32) + spec[..., None]
    acc[y0:y1, x0:x1] = acc[y0:y1, x0:x1] * (1 - m[..., None]) + c * m[..., None]
    alpha[y0:y1, x0:x1] = np.maximum(alpha[y0:y1, x0:x1], m)


def build_tardigrade():
    TW, TH = 1400, 900
    acc = np.zeros((TH, TW, 3), np.float32); al = np.zeros((TH, TW), np.float32)
    col = (0.86, 0.72, 0.55); legc = (0.80, 0.64, 0.48)
    xs = [300, 470, 650, 830, 1010]
    # legs (behind body)
    for i, lx in enumerate([380, 600, 820, 1010]):
        shaded_ellipse(acc, al, lx - 30, 610, 55, 85, [c * 0.8 for c in legc], ang=0.15)
    for i, lx in enumerate([330, 560, 780, 960]):
        shaded_ellipse(acc, al, lx + 10, 640, 62, 95, legc, ang=-0.1)
    for i, x in enumerate(xs):
        a = [150, 175, 185, 175, 165][i]
        b = [175, 205, 215, 205, 185][i]
        shaded_ellipse(acc, al, x, 420 + (i % 2) * 6, a, b, col, bands=0)
    # head
    shaded_ellipse(acc, al, 1150, 455, 140, 150, col)
    shaded_ellipse(acc, al, 1255, 470, 55, 60, (0.7, 0.55, 0.42))
    im = to_img(acc); a_im = Image.fromarray((al * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.ellipse([1255, 450, 1295, 492], fill=(40, 25, 20))  # mouth
    # claws
    for lx in [340, 570, 790, 970]:
        for k in range(3):
            x = lx - 20 + k * 18
            d.line([(x, 720), (x - 8, 760)], fill=(60, 40, 30), width=6)
    d2 = ImageDraw.Draw(a_im)
    for lx in [340, 570, 790, 970]:
        for k in range(3):
            x = lx - 20 + k * 18
            d2.line([(x, 720), (x - 8, 760)], fill=255, width=6)
    # skin wrinkles
    wr = fbm(TH, TW, (30, 90), seed=11)
    arr = from_img(im) * (0.85 + 0.3 * wr[..., None])
    im = to_img(arr); im.putalpha(a_im.filter(ImageFilter.GaussianBlur(1.5)))
    return im


def build_eye():
    yy, xx = np.mgrid[0:BH, 0:BW].astype(np.float32)
    cx, cy = BW * 0.5, BH * 0.5
    skin = fbm(BH, BW, (6, 20, 60, 200), seed=21)
    spots = gaussian_filter((rng.random((BH, BW)) > 0.9985).astype(np.float32), 6) * 60
    img = np.stack([0.30 + 0.25 * skin, 0.07 + 0.06 * skin, 0.06 + 0.05 * skin], -1)
    img *= (1 - np.clip(spots, 0, 0.6))[..., None]
    r = np.sqrt(((xx - cx) / 1.08) ** 2 + (yy - cy) ** 2)
    R = 470
    # socket shadow ring
    img *= (1 - 0.8 * np.exp(-((r - R * 1.05) / 60) ** 2))[..., None]
    img *= np.clip((r - R * 0.6) / (R * 0.9), 0.15, 1)[..., None] ** 0.5
    inside = np.clip((R - r) / 4, 0, 1)[..., None]
    ang = np.arctan2(yy - cy, xx - cx)
    stri = fbm(BH, BW, (8, 40), seed=5)
    stria = 0.5 + 0.5 * np.sin(ang * 90 + stri * 20)
    iris_r = R * 0.92; pup = R * 0.55
    rn = r / R
    iris = np.stack([0.55 + 0.25 * stria, 0.58 + 0.25 * stria, 0.62 + 0.25 * stria], -1) * (0.5 + 0.5 * np.clip((r - pup) / (iris_r - pup), 0, 1))[..., None]
    iris *= (0.35 + 0.65 * np.exp(-((rn - 0.75) / 0.25) ** 2))[..., None]
    eye = np.where((r < pup)[..., None], np.array([0.01, 0.012, 0.02], np.float32), iris)
    eye = np.where((r > iris_r)[..., None], np.array([0.06, 0.05, 0.06], np.float32), eye)
    nz = np.sqrt(np.clip(1 - rn ** 2, 0, 1))
    eye = eye * (0.55 + 0.45 * nz)[..., None]
    img = img * (1 - inside) + eye * inside
    # highlights
    hl = np.exp(-(((xx - cx + R * 0.35) / (R * 0.28)) ** 2 + ((yy - cy + R * 0.38) / (R * 0.16)) ** 2)) * 0.55
    hl += np.exp(-(((xx - cx + R * 0.18) / 22) ** 2 + ((yy - cy + R * 0.22) / 16) ** 2)) * 0.9
    img += (hl * inside[..., 0])[..., None] * np.array([0.9, 0.95, 1.0])
    img *= np.exp(-(((xx - cx) / (BW * 0.55)) ** 2 + ((yy - cy) / (BH * 0.6)) ** 2))[..., None] * 1.1
    return to_img(img)


# earth lookup
EH = 1.15 * H
E_CX, E_CY, E_R = W * 0.5, H * 1.62, H * 1.08
dx = (XX - E_CX) / E_R; dy = (YY - E_CY) / E_R
E_RR = dx * dx + dy * dy
E_IN = E_RR < 1
E_NZ = np.sqrt(np.clip(1 - E_RR, 0, 1))
E_LAT = np.arcsin(np.clip(-dy, -1, 1))
E_LON = np.arctan2(dx, E_NZ + 1e-6)
TEX_W, TEX_H = 2048, 1024
LAND = fbm(TEX_H, TEX_W, (4, 8, 16, 48, 128), seed=31)
CLOUD = fbm(TEX_H, TEX_W, (6, 18, 60, 160), seed=41)
STARS = gaussian_filter((rng.random((H, W)) > 0.9993).astype(np.float32) * rng.random((H, W)), 0.8) * 9


def earth_frame(t):
    lon = (E_LON + math.pi + t * 0.025) % (2 * math.pi)
    tx = lon / (2 * math.pi) * (TEX_W - 1); ty = (0.5 - E_LAT / math.pi) * (TEX_H - 1)
    land = map_coordinates(LAND, [ty[E_IN], tx[E_IN]], order=1)
    cl = map_coordinates(CLOUD, [ty[E_IN], (tx[E_IN] * 1.0 + t * 6) % (TEX_W - 1)], order=1)
    isl = np.clip((land - 0.56) * 25, 0, 1)
    ocean = np.array([0.03, 0.12, 0.30]); green = np.array([0.18, 0.26, 0.12]); brown = np.array([0.36, 0.30, 0.18])
    lc = green + (brown - green) * np.clip((land - 0.6) * 6, 0, 1)[:, None]
    col = ocean + (lc - ocean) * isl[:, None]
    cc = np.clip((cl - 0.5) * 3, 0, 1)[:, None] * 0.85
    col = col * (1 - cc) + cc * 0.95
    nx, ny, nz = dx[E_IN], dy[E_IN], E_NZ[E_IN]
    L = np.array([-0.6, -0.55, 0.58]); L /= np.linalg.norm(L)
    lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    col = col * (0.06 + 1.1 * lam[:, None]) + np.array([0.15, 0.3, 0.6]) * (1 - nz[:, None]) ** 2 * 0.8
    img = np.zeros((H, W, 3), np.float32)
    img += STARS[..., None] * np.array([0.9, 0.95, 1.0])
    rr = np.sqrt(E_RR)
    atm = np.exp(-np.clip(rr - 1, 0, None) * 28) * (~E_IN)
    img += atm[..., None] * np.array([0.25, 0.5, 1.0]) * 0.7 * np.clip(0.4 - dx * 0.8, 0.1, 1)[..., None]
    img[E_IN] = col
    sun = np.exp(-(((XX - W * 0.08) / 70) ** 2 + ((YY - H * 0.12) / 70) ** 2)) * 1.2 + np.exp(-(((XX - W * 0.08) / 420) ** 2 + ((YY - H * 0.12) / 420) ** 2)) * 0.25
    img += sun[..., None] * np.array([1.0, 0.85, 0.6])
    return img


HEAD = [(0.30, 1.0), (0.31, 0.80), (0.27, 0.70), (0.25, 0.55), (0.26, 0.40), (0.30, 0.28), (0.37, 0.19), (0.46, 0.14),
        (0.55, 0.13), (0.63, 0.16), (0.69, 0.22), (0.72, 0.30), (0.73, 0.38), (0.735, 0.43), (0.78, 0.50), (0.775, 0.53),
        (0.745, 0.545), (0.75, 0.58), (0.758, 0.60), (0.745, 0.62), (0.752, 0.645), (0.735, 0.67), (0.725, 0.71),
        (0.68, 0.735), (0.62, 0.745), (0.60, 0.80), (0.59, 1.0)]
HS = H * 1.0; HX0 = W * 0.5 - HS * 0.52; HY0 = H * 0.02
HEAD_PX = [(HX0 + x * HS, HY0 + y * HS) for x, y in HEAD]
_m = Image.new("L", (W, H), 0); ImageDraw.Draw(_m).polygon(HEAD_PX, fill=255)
HEAD_MASK = np.asarray(_m, np.float32) / 255.0
HEAD_RIM = np.clip(gaussian_filter(HEAD_MASK, 5) - gaussian_filter(HEAD_MASK, 18), 0, 1) * 4
MOUTH = (HX0 + 0.75 * HS, HY0 + 0.61 * HS); EAR = (HX0 + 0.43 * HS, HY0 + 0.50 * HS)


def head_frame(t):
    img = np.zeros((H, W, 3), np.float32) + np.array([0.02, 0.03, 0.045])
    bg = np.exp(-(((XX - W * 0.75) / 700) ** 2 + ((YY - H * 0.4) / 500) ** 2)) * 0.12
    img += bg[..., None] * np.array([0.3, 0.6, 0.8])
    # skull hint (inner ellipse)
    sk = np.exp(-((np.sqrt(((XX - (HX0 + 0.49 * HS)) / (0.22 * HS)) ** 2 + ((YY - (HY0 + 0.37 * HS)) / (0.22 * HS)) ** 2) - 1) / 0.025) ** 2)
    head = np.array([0.05, 0.05, 0.06]) + 0.06 * sk[..., None] * np.array([1.0, 0.75, 0.45])
    img = img * (1 - HEAD_MASK[..., None]) + head * HEAD_MASK[..., None]
    img += HEAD_RIM[..., None] * np.array([1.0, 0.62, 0.25]) * 0.55
    # waves
    rm = np.sqrt((XX - MOUTH[0]) ** 2 + (YY - MOUTH[1]) ** 2)
    outw = np.zeros((H, W), np.float32); inw = np.zeros((H, W), np.float32)
    for k in range(5):
        ph = ((t * 0.55 + k / 5) % 1.0)
        rad = 30 + ph * 900; fade = (1 - ph) ** 1.5
        outw += np.exp(-((rm - rad) / 6) ** 2) * fade
        inw += np.exp(-((rm - rad * 0.55) / 9) ** 2) * fade
    outside = (1 - HEAD_MASK) * (XX > MOUTH[0] - 20)
    img += (outw * outside)[..., None] * np.array([0.35, 0.75, 1.0]) * 0.8
    img += (inw * HEAD_MASK)[..., None] * np.array([1.0, 0.6, 0.2]) * 0.9
    re = np.sqrt((XX - EAR[0]) ** 2 + (YY - EAR[1]) ** 2)
    img += (np.exp(-(re / 40) ** 2) * (0.5 + 0.5 * math.sin(t * 6)))[..., None] * np.array([1.0, 0.65, 0.3]) * 0.5
    return img


ENV8 = None


def wave_frame(t, seg_t):
    v = voices["08"]
    img = np.zeros((H, W, 3), np.float32) + np.array([0.02, 0.025, 0.04])
    span = 4.0
    n = 480
    ts = seg_t - span * 0.75 + np.arange(n) / n * span
    amps = []
    for tt in ts:
        i = int(tt * SR)
        if i < 0 or i + 600 > len(v): amps.append(0.0); continue
        amps.append(float(np.sqrt(np.mean(v[i:i + 600] ** 2))))
    amps = np.array(amps) * 4.5
    def draw(d, s):
        cy = H * 0.5
        for i, a in enumerate(amps):
            x = (i + 0.5) / n * W
            h = 4 + min(a, 1.0) * H * 0.2
            past = ts[i] <= seg_t
            v_ = 255 if past else 90
            d.line([(x * s, (cy - h) * s), (x * s, (cy + h) * s)], fill=v_, width=max(1, int(3 * s)))
    sharp = soft_layer(draw, 1, 0)
    glow = gaussian_filter(sharp[::2, ::2], 8)
    glow = np.asarray(Image.fromarray(glow, "F").resize((W, H), Image.BILINEAR))
    col = np.array([1.0, 0.62, 0.25])
    img += sharp[..., None] * col * 0.8 + glow[..., None] * col * 1.2
    xnow = W * 0.75
    img += (np.exp(-((XX - xnow) / 3) ** 2) * 0.6)[..., None] * np.array([0.6, 0.85, 1.0])
    return img


def ecg(x):
    # x in beats (phase), returns -1..1 shape of heartbeat
    p = x % 1.0
    g = lambda c, w, a: a * np.exp(-((p - c) / w) ** 2)
    return g(0.12, 0.03, 0.12) - g(0.27, 0.008, 0.15) + g(0.30, 0.012, 1.0) - g(0.33, 0.01, 0.3) + g(0.55, 0.05, 0.25)


BEAT = 0.95  # seconds per beat


def ecg_overlay(t):
    n = 700
    xs = np.linspace(0, 1, n)
    head = (t / 3.0) % 1.2
    beats = (xs * 3.0 + t / BEAT - 0) * 0 + (t - (head - xs) * 3.0) / BEAT
    ys = ecg(beats)
    def draw(d, s):
        pts = []
        for i in range(n):
            if xs[i] > head: break
            pts.append((xs[i] * W * s, (H * 0.5 - ys[i] * H * 0.22) * s))
        if len(pts) > 1:
            d.line(pts, fill=255, width=max(1, int(4 * s)))
    sharp = soft_layer(draw, 1, 0)
    trail = np.clip(1 - np.clip((head * W - XX) / (W * 0.9), 0, 1), 0, 1)
    sharp *= trail
    glow = gaussian_filter(sharp[::2, ::2], 7)
    glow = np.asarray(Image.fromarray(glow, "F").resize((W, H), Image.BILINEAR))
    return sharp, glow


print("building assets", file=sys.stderr)
IMG_FOAM = build_foam()
IMG_TARDI = build_tardigrade()
IMG_EYE = build_eye()
TARDI_BG = None


def tardi_frame(t, u):
    bg = np.zeros((H, W, 3), np.float32) + np.array([0.02, 0.05, 0.06])
    bg += (np.exp(-(((XX - W * 0.55) / 900) ** 2 + ((YY - H * 0.45) / 600) ** 2)) * 0.18)[..., None] * np.array([0.3, 0.7, 0.75])
    # moss blob ground
    canvas = to_img(bg)
    z = 0.92 + 0.12 * u
    tw, th = IMG_TARDI.size
    sc = (W * 0.62 / tw) * z
    im = IMG_TARDI.resize((int(tw * sc), int(th * sc)), Image.BILINEAR)
    im = im.rotate(math.sin(t * 0.8) * 2.0, resample=Image.BILINEAR, expand=False)
    x = int(W * 0.5 - im.width / 2 + math.sin(t * 0.5) * 20 - u * 60); y = int(H * 0.5 - im.height / 2 + math.sin(t * 1.1) * 10)
    canvas.paste(im, (x, y), im)
    arr = from_img(canvas)
    arr += particles(60, 9, t, speed=(-12, -4), bright=0.35)[..., None] * np.array([0.6, 0.9, 0.9])
    return arr


# ------------------------------------------------------------------ shots
def shot_list(seg, dur):
    if seg == "01":
        return [(0.55, lambda t, u: kenburns(IMG_WHALE, u, 1.0, 1.18, (0.5, 0.5), (0.47, 0.52)) + particles(70, 1, t, (4, -8), bright=0.25)[..., None] * 0.5),
                (0.45, lambda t, u: kenburns(IMG_SCI, u, 1.12, 1.0, (0.55, 0.5), (0.5, 0.5)))]
    if seg == "03":
        def foam(t, u):
            return kenburns(IMG_FOAM, u, 1.0, 1.25)
        def heart(t, u):
            base = kenburns(IMG_FOAM, u, 1.25, 1.4) * 0.45
            ph = (t / BEAT) % 1.0
            pulse = math.exp(-((ph - 0.30) / 0.06) ** 2)
            sharp, glow = ecg_overlay(t)
            col = np.array([1.0, 0.35, 0.22])
            base = base * (1 + 0.25 * pulse)
            return base + sharp[..., None] * col + glow[..., None] * col * 1.4
        return [(0.45, foam), (0.55, heart)]
    if seg == "06":
        return [(0.55, tardi_frame), (0.45, lambda t, u: earth_frame(t))]
    if seg == "07":
        def eye(t, u):
            a = kenburns(IMG_EYE, u, 1.0, 1.35)
            sweep = np.exp(-((XX - (u * 1.6 - 0.3) * W) / 500) ** 2)[..., None] * 0.25
            return a * (0.8 + sweep * 2) + particles(80, 7, t, (3, -14), bright=0.3)[..., None] * np.array([0.6, 0.8, 0.9])
        return [(1.0, eye)]
    if seg == "08":
        return [(0.58, lambda t, u: head_frame(t)), (0.42, None)]


TITLE_FONT = ImageFont.truetype(FONT_B, 92); CHIP_FONT = ImageFont.truetype(FONT_B, 34); NUM_FONT = ImageFont.truetype(FONT_B, 34)
SMALL_FONT = ImageFont.truetype(FONT_B, 40)


def text_layer(fn):
    im = Image.new("L", (W, H), 0); fn(ImageDraw.Draw(im)); return np.asarray(im, np.float32) / 255.0


def chip(num, title):
    def f(d):
        d.rectangle([80, 80, 88, 140], fill=255)
        d.text((110, 78), num, font=NUM_FONT, fill=255)
        d.text((110, 112), title, font=CHIP_FONT, fill=200)
    return text_layer(f)


CHIPS = {seg: chip(num, title) for seg, num, title in TOPICS}
TITLE = text_layer(lambda d: d.text((W / 2, H * 0.42), "ДИВНІ ФАКТИ", font=TITLE_FONT, fill=255, anchor="mm"))
SUBT = text_layer(lambda d: d.text((W / 2, H * 0.52), "ПРО НАШ СВІТ", font=SMALL_FONT, fill=255, anchor="mm"))
END1 = text_layer(lambda d: d.text((W / 2, H * 0.45), "А який факт здивував вас найбільше?", font=ImageFont.truetype(FONT_B, 58), fill=255, anchor="mm"))
END2 = text_layer(lambda d: d.text((W / 2, H * 0.55), "Напишіть у коментарях", font=SMALL_FONT, fill=255, anchor="mm"))


def sstep(a, b, x):
    u = min(max((x - a) / (b - a), 0), 1); return u * u * (3 - 2 * u)


def frame(T, fi):
    for (a, b, seg, num, title) in windows:
        if a <= T < b or (b == TOTAL and T >= a):
            break
    dur = b - a; lt = T - a
    shots = shot_list(seg, dur)
    # topic 5 waveform shot needs voice-local time
    edges = [0.0]
    for frac, _ in shots: edges.append(edges[-1] + frac * dur)
    XF = 0.8
    def render_shot(k):
        frac, fn = shots[k]
        s0, s1 = edges[k], edges[k + 1]
        u = min(max((lt - s0) / (s1 - s0), 0), 1)
        if fn is None:
            return wave_frame(lt, T - starts[seg])
        return fn(lt, u)
    k = 0
    while k + 1 < len(shots) and lt >= edges[k + 1]: k += 1
    img = render_shot(k)
    if k + 1 < len(shots) and lt > edges[k + 1] - XF:
        w = sstep(edges[k + 1] - XF, edges[k + 1], lt)
        img = img * (1 - w) + render_shot(k + 1) * w
    # topic dip to black
    fade = sstep(0, 0.55, lt) if a > 0 else sstep(0, 1.0, lt)
    if b < TOTAL: fade *= 1 - sstep(dur - 0.55, dur, lt)
    img = img * fade
    img = grade(img, fi)
    # chip
    vs = starts[seg]
    ca = sstep(vs - 0.2, vs + 0.4, T) * (1 - sstep(vs + 4.0, vs + 4.8, T))
    if ca > 0:
        img = img + CHIPS[seg][..., None] * ca * (1 - img) * 0.95
    if seg == "01":
        ta = sstep(0.2, 1.0, T) * (1 - sstep(3.6, 4.6, T))
        if ta > 0:
            img = img * (1 - 0.35 * ta) + (TITLE + SUBT * 0.85)[..., None] * ta * np.array([1.0, 0.92, 0.82])
    if b == TOTAL:
        et = T - (starts[seg] + len(voices[seg]) / SR + 0.4)
        ea = sstep(0, 0.8, et)
        if ea > 0:
            img = img * (1 - 0.7 * ea) + (END1 + END2 * 0.8)[..., None] * ea
        img = img * (1 - sstep(TOTAL - 1.0, TOTAL, T))
    return np.clip(img, 0, 1)


# ------------------------------------------------------------------ audio
def build_audio():
    N = int(TOTAL * SR) + SR
    t = np.arange(N) / SR
    voice = np.zeros(N, np.float32)
    for seg in voices:
        i = int(starts[seg] * SR); v = voices[seg]
        voice[i:i + len(v)] += v
    # music: dark drone pad
    r = np.random.default_rng(1)
    pad = np.zeros((N, 2), np.float32)
    notes = [55.0, 82.41, 110.0, 130.81, 164.81]
    for j, f in enumerate(notes):
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * (0.03 + 0.01 * j) * t + j)
        for ch, det in enumerate([-0.15, 0.15]):
            ph = 2 * np.pi * (f + det) * t
            s = np.sin(ph) + 0.3 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph)
            pad[:, ch] += s * lfo * (0.10 if j < 2 else 0.05)
    noise = r.standard_normal((N, 2)).astype(np.float32)
    from scipy.signal import butter, sosfilt
    sos = butter(2, 300, "lp", fs=SR, output="sos")
    wind = sosfilt(sos, noise, axis=0) * 0.25
    music = pad + wind * (0.5 + 0.5 * np.sin(2 * np.pi * 0.05 * t))[:, None]
    music /= np.abs(music).max()
    music *= 0.16
    # whale song at start
    sfx = np.zeros((N, 2), np.float32)
    def add(sig, at, gain, pan=0.0):
        i = int(at * SR); sig = sig[:max(0, N - i)]
        sfx[i:i + len(sig), 0] += sig * gain * (1 - pan); sfx[i:i + len(sig), 1] += sig * gain * (1 + pan)
    tt = np.arange(int(4.5 * SR)) / SR
    f = 240 - 90 * np.sin(np.pi * tt / 4.5) + 6 * np.sin(2 * np.pi * 5 * tt)
    whale = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * tt / 4.5) ** 2
    whale = sosfilt(butter(2, 900, "lp", fs=SR, output="sos"), whale)
    add(whale, 0.2, 0.22, -0.2); add(whale[::-1] * 0.7, 11.0, 0.12, 0.3)
    # heartbeat during room heart shot
    a, b = [(w[0], w[1]) for w in windows if w[2] == "03"][0]
    hs = a + 0.45 * (b - a) - 0.4
    tb = np.arange(int(0.25 * SR)) / SR
    thump = np.sin(2 * np.pi * 52 * tb) * np.exp(-tb * 22)
    k = 0
    while hs + k * BEAT < b - 0.6:
        bt = hs + 0.4 + k * BEAT + 0.30 * BEAT - 0.02
        add(thump, bt, 0.5); add(thump * 0.6, bt + 0.16, 0.5)
        k += 1
    # whooshes at topic transitions
    tw = np.arange(int(1.2 * SR)) / SR
    wn = sosfilt(butter(2, [300, 3000], "bp", fs=SR, output="sos"), r.standard_normal(len(tw)))
    wh = wn * np.sin(np.pi * tw / 1.2) ** 3
    for (a, b, seg, _, _) in windows[1:]:
        add(wh, a - 0.6, 0.10)
    # radio static-ish texture under topic 5? keep clean
    env = np.convolve(np.abs(voice), np.ones(4800) / 4800, mode="same")
    duck = 1 - 0.55 * np.clip(env * 12, 0, 1)
    fadein = np.clip(t / 1.5, 0, 1); fadeout = np.clip((TOTAL - t) / 2.5, 0, 1)
    mix = music * duck[:, None] + sfx + voice[:, None] * 1.0
    mix *= (fadein * fadeout)[:, None]
    mix /= max(1.0, np.abs(mix).max() / 0.95)
    p = os.path.join(OUT, "mix.wav")
    with wave.open(p, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    return p


def ts(x):
    h = int(x // 3600); m = int(x % 3600 // 60); s = x % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass():
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
             "Style: Default,DejaVu Sans,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,3.2,1.5,2,160,160,70,1",
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for seg, _, _ in TOPICS:
        for s, e, txt in flatten(seg):
            S = starts[seg] + s; E = starts[seg] + e + 0.15
            lines.append(f"Dialogue: 0,{ts(S)},{ts(E)},Default,,0,0,0,,{{\\fad(120,120)}}{txt}")
    p = os.path.join(OUT, "subs.ass")
    open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return p


if PREVIEW:
    for x in PREVIEW:
        to_img(frame(x, 0)).save(os.path.join(OUT, f"prev_{x:06.2f}.jpg"), quality=88)
    sys.exit(0)

wav = build_audio(); ass = build_ass()
final = os.path.join(OUT, "video.mp4")
cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
       "-i", wav, "-vf", f"ass={ass}", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", final]
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
nf = int(TOTAL * FPS)
for fi in range(nf):
    proc.stdin.write((frame(fi / FPS, fi) * 255).astype(np.uint8).tobytes())
    if fi % 150 == 0: print(f"frame {fi}/{nf}", file=sys.stderr, flush=True)
proc.stdin.close(); proc.wait()
print("done", final, file=sys.stderr)
