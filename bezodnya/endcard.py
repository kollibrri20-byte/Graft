"""Фінальна заставка: курсор натискає «лайк», «Підписатися» і дзвіночок (1920x1080, 24 fps, ~6.5 с).

    python endcard.py OUT_DIR   ->  OUT_DIR/endcard.mp4 (з клацаннями й дзвоником)
"""
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy.io import wavfile

W, H, FPS, DUR = 1920, 1080, 24, 6.5
SS = 2
FONT = "/usr/share/fonts/truetype/inter/Inter-Bold.ttf"


def font(size):
    for p in (FONT, "/usr/share/fonts/opentype/inter/Inter-Bold.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    import glob
    c = glob.glob("/usr/share/fonts/**/Inter*Bold*.*", recursive=True)
    return ImageFont.truetype(c[0], size)


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def back(x):
    """Пружинний вихід (overshoot)."""
    x = min(max(x, 0.0), 1.0)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def pop(t, t0, d=0.35):
    """Масштаб «натискання»: 1 -> 0.85 -> 1.12 -> 1."""
    u = (t - t0) / d
    if u < 0 or u > 1:
        return 1.0
    if u < 0.25:
        return 1 - 0.15 * (u / 0.25)
    return 0.85 + 0.27 * math.sin(min(1, (u - 0.25) / 0.75) * math.pi) * (1 - (u - 0.25) / 0.75) + 0.15 * ((u - 0.25) / 0.75)


def thumb(d, cx, cy, s, col):
    """Великий палець угору (іконка лайка)."""
    pts = [(-0.55, 0.05), (-0.25, 0.05), (-0.25, 0.75), (-0.55, 0.75)]
    d.rounded_rectangle([cx + s * -0.62, cy + s * 0.0, cx + s * -0.3, cy + s * 0.8], radius=s * 0.06, fill=col)
    hand = [(-0.22, 0.05), (0.0, -0.25), (0.08, -0.62), (0.2, -0.68), (0.3, -0.55), (0.25, -0.12),
            (0.58, -0.12), (0.68, 0.0), (0.62, 0.2), (0.6, 0.42), (0.52, 0.62), (0.4, 0.8), (-0.22, 0.8)]
    d.polygon([(cx + x * s, cy + y * s) for x, y in hand], fill=col)


def bell(d, cx, cy, s, col, ang=0.0):
    def r(x, y):
        c, sn = math.cos(ang), math.sin(ang)
        # обертання навколо верхньої точки дзвоника
        y0 = -0.75
        xx, yy = x * c - (y - y0) * sn, x * sn + (y - y0) * c + y0
        return (cx + xx * s, cy + yy * s)
    body = [(-0.08, -0.62), (0.08, -0.62)]
    arc = []
    for k in range(21):
        a = math.pi * k / 20
        arc.append((0.42 * math.cos(math.pi - a), -0.25 - 0.4 * math.sin(a)))
    pts = [(-0.55, 0.45), (-0.45, 0.3)] + [(-0.42, -0.25)] + arc[1:-1] + [(0.42, -0.25), (0.45, 0.3), (0.55, 0.45)]
    d.polygon([r(x, y) for x, y in pts], fill=col)
    d.ellipse([*r(-0.09, -0.78), *r(0.09, -0.6)], fill=col)
    cl = r(0, 0.6)
    d.ellipse([cl[0] - 0.13 * s, cl[1] - 0.1 * s, cl[0] + 0.13 * s, cl[1] + 0.12 * s], fill=col)


def cursor(d, x, y, s=1.0, pressed=False):
    sc = 1.6 * s * (0.9 if pressed else 1.0)
    pts = [(0, 0), (0, 34), (9, 26), (15, 40), (21, 37), (15, 24), (27, 24)]
    P = [(x + px * sc, y + py * sc) for px, py in pts]
    d.polygon(P, fill=(255, 255, 255, 255), outline=(10, 10, 10, 255), width=int(3 * sc))


def frame(t):
    S = SS
    im = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 255))
    # фон: темна вода з легким світлом згори
    bg = np.zeros((H, W, 3), np.float32)
    yy = np.linspace(0, 1, H)[:, None]
    bg[:] = (np.array([8, 22, 40]) * (1 - yy) + np.array([1, 3, 8]) * yy)[:, None, :] if False else 0
    g = (np.array([6, 20, 38], np.float32)[None, None] * (1 - yy[..., None]) + np.array([0, 2, 6], np.float32)[None, None] * yy[..., None])
    bg = np.broadcast_to(g, (H, W, 3)).copy() * min(1, t / 0.6)
    base = Image.fromarray(bg.astype(np.uint8)).resize((W * S, H * S)).convert("RGBA")
    im.alpha_composite(base)
    d = ImageDraw.Draw(im)
    a_in = back((t - 0.2) / 0.6)
    # події курсора
    T_LIKE, T_SUB, T_BELL = 1.6, 2.9, 4.1
    liked = t >= T_LIKE + 0.08
    subbed = t >= T_SUB + 0.08
    rung = t >= T_BELL + 0.08
    # заголовок
    f1 = font(58 * S)
    title = "Підпишись, щоб не пропустити наступне занурення"
    tw = d.textlength(title, font=f1)
    al = int(255 * ease((t - 0.3) / 0.5))
    d.text(((W * S - tw) / 2, 300 * S - (1 - ease((t - 0.3) / 0.5)) * 30 * S), title, font=f1, fill=(235, 242, 250, al))
    cy = 560 * S
    # --- лайк
    lx = 560 * S
    sc = a_in * pop(t, T_LIKE)
    r = 95 * S * sc
    col_bg = (40, 110, 255, 255) if liked else (45, 52, 62, 255)
    if r > 2:
        d.ellipse([lx - r, cy - r, lx + r, cy + r], fill=col_bg)
        thumb(d, lx + 6 * S * sc, cy + 2 * S * sc, 58 * S * sc, (255, 255, 255, 255))
    # --- підписатися
    sx = 960 * S
    sc2 = a_in * pop(t, T_SUB)
    bw, bh = 470 * S * sc2, 120 * S * sc2
    col = (90, 90, 96, 255) if subbed else (222, 20, 32, 255)
    txt = "ВИ ПІДПИСАНІ" if subbed else "ПІДПИСАТИСЯ"
    if bw > 4:
        d.rounded_rectangle([sx - bw / 2, cy - bh / 2, sx + bw / 2, cy + bh / 2], radius=bh / 2, fill=col)
        f2 = font(max(4, int(46 * S * sc2)))
        tw = d.textlength(txt, font=f2)
        d.text((sx - tw / 2, cy - 30 * S * sc2), txt, font=f2, fill=(255, 255, 255, 255))
    # --- дзвоник
    bx = 1360 * S
    sc3 = a_in * pop(t, T_BELL)
    rb = 95 * S * sc3
    if rb > 2:
        d.ellipse([bx - rb, cy - rb, bx + rb, cy + rb], fill=(45, 52, 62, 255))
        ang = 0.0
        if rung:
            u = t - T_BELL
            ang = 0.45 * math.sin(u * 22) * math.exp(-u * 2.2)
        bell(d, bx, cy + 8 * S * sc3, 62 * S * sc3, (255, 214, 60, 255) if rung else (255, 255, 255, 255), ang)
        if rung:
            u = t - T_BELL
            k = math.exp(-u * 1.5)
            for side in (-1, 1):
                for j, (a0, L) in enumerate(((-0.5, 30), (0.0, 36), (0.5, 30))):
                    ax = bx + side * (105 + j * 3) * S
                    ay = cy + (a0 * 70 - 30) * S
                    d.line([ax, ay, ax + side * L * S * k, ay + a0 * 20 * S * k], fill=(255, 214, 60, int(255 * k)), width=6 * S)
    # частинки-сердечка після лайка
    if liked:
        u = t - T_LIKE
        rng = np.random.default_rng(3)
        for i in range(12):
            a = rng.uniform(-2.6, -0.5)
            v = rng.uniform(120, 260)
            px = lx + math.cos(a) * v * u * S
            py = cy + (math.sin(a) * v * u + 160 * u * u) * S
            al = max(0, 1 - u / 1.2)
            if al > 0:
                rr = 9 * S
                d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=(90, 160, 255, int(255 * al)))
    # курсор: шлях лайк -> підписка -> дзвоник -> геть
    keys = [(0.6, (1500, 900)), (T_LIKE, (lx / S + 20, cy / S + 25)), (T_SUB, (sx / S + 60, cy / S + 25)),
            (T_BELL, (bx / S + 20, cy / S + 30)), (5.2, (bx / S + 20, cy / S + 30)), (6.0, (1800, 1000))]
    pos = keys[0][1]
    for (t0, p0), (t1, p1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            u = ease((t - t0) / (t1 - t0) * 1.25)
            pos = (p0[0] + (p1[0] - p0[0]) * u, p0[1] + (p1[1] - p0[1]) * u)
            break
        if t > t1:
            pos = p1
    pressed = any(0 <= t - tc < 0.12 for tc in (T_LIKE, T_SUB, T_BELL))
    if 0.6 < t < 6.0:
        cursor(d, pos[0] * S, pos[1] * S, S, pressed)
    # загальне згасання наприкінці
    out = im.resize((W, H), Image.LANCZOS).convert("RGB")
    fade = 1 - ease((t - 5.9) / 0.6)
    if fade < 1:
        out = Image.fromarray((np.asarray(out, np.float32) * fade).astype(np.uint8))
    return out, (T_LIKE, T_SUB, T_BELL)


def audio(times, path, sr=48000):
    n = int(DUR * sr)
    a = np.zeros(n, np.float32)
    rng = np.random.default_rng(1)
    for tc in times:
        i = int((tc + 0.02) * sr)
        m = int(0.03 * sr)
        tt = np.arange(m) / sr
        click = rng.standard_normal(m) * np.exp(-tt * 300) * 0.5 + np.sin(2 * np.pi * 2200 * tt) * np.exp(-tt * 200) * 0.3
        a[i:i + m] += click
        # м'який "поп" підтвердження
        m2 = int(0.25 * sr)
        tt = np.arange(m2) / sr
        f = 520 if tc != times[2] else 0
        if f:
            a[i:i + m2] += np.sin(2 * np.pi * (f + 300 * tt) * tt) * np.exp(-tt * 18) * 0.25
    # дзвоник
    i = int((times[2] + 0.05) * sr)
    m = int(2.2 * sr)
    tt = np.arange(m) / sr
    ding = sum(amp * np.sin(2 * np.pi * f * tt) * np.exp(-tt * dec) for f, amp, dec in
               ((1320, 0.35, 2.2), (2640, 0.15, 3.5), (3960, 0.08, 5), (1980, 0.12, 2.8)))
    ding *= 1 + 0.3 * np.sin(2 * np.pi * 7 * tt)
    a[i:i + m] += ding[: n - i]
    # тихий низький гул, що згасає
    tt = np.arange(n) / sr
    a += (np.sin(2 * np.pi * 55 * tt) * 0.06 + np.sin(2 * np.pi * 82.5 * tt) * 0.03) * np.minimum(1, tt / 0.5) * np.clip((DUR - tt) / 1.0, 0, 1)
    a = a / max(1e-6, np.abs(a).max()) * 0.7
    st = np.stack([a, a], 1)
    wavfile.write(path, sr, (st * 32767).astype(np.int16))


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    n = int(DUR * FPS)
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
                             os.path.join(out, "endcard_v.mp4")], stdin=subprocess.PIPE)
    times = None
    for f in range(n):
        img, times = frame(f / FPS)
        proc.stdin.write(img.tobytes())
        if f in (30, 45, 75, 105, 130):
            img.save(os.path.join(out, f"endcard_{f}.png"))
    proc.stdin.close()
    proc.wait()
    audio(times, os.path.join(out, "endcard.wav"))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(out, "endcard_v.mp4"), "-i",
                    os.path.join(out, "endcard.wav"), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                    os.path.join(out, "endcard.mp4")], check=True)
    print("ok")


if __name__ == "__main__":
    main()
