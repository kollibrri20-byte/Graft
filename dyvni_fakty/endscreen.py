"""6-second end screen: like, subscribe and bell animation with cursor clicks. Usage: endscreen.py OUTDIR"""
import os, sys, math, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1]
W, H, FPS, SR, DUR = 1920, 1080, 30, 48000, 6.0
SS = 2  # supersampling
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
F_TITLE = ImageFont.truetype(FB, 64 * SS); F_BTN = ImageFont.truetype(FB, 46 * SS); F_SMALL = ImageFont.truetype(FB, 34 * SS)
RED, GREY, WHITE, BLUE, AMBER = (229, 30, 37), (70, 72, 78), (245, 245, 245), (62, 166, 255), (255, 176, 60)

ROW_Y = 0.56 * H
LIKE_C, SUB_C, BELL_C = (W * 0.27, ROW_Y), (W * 0.5, ROW_Y), (W * 0.73, ROW_Y)
CLICK_LIKE, CLICK_SUB, CLICK_BELL = 1.55, 2.65, 3.75


def ease_back(u):
    u = min(max(u, 0), 1); c = 1.7
    return 1 + (c + 1) * (u - 1) ** 3 + c * (u - 1) ** 2


def smooth(a, b, x):
    u = min(max((x - a) / (b - a), 0), 1); return u * u * (3 - 2 * u)


def circle_btn(d, c, r, fill, outline=None):
    x, y = c[0] * SS, c[1] * SS; r *= SS
    d.ellipse([x - r, y - r, x + r, y + r], fill=fill, outline=outline, width=int(4 * SS))


def thumb(d, c, size, col):
    s = size * SS / 100; ox, oy = c[0] * SS - 50 * s, c[1] * SS - 52 * s
    P = lambda pts: [(ox + x * s, oy + y * s) for x, y in pts]
    d.rounded_rectangle(P([(10, 46), (28, 92)]), radius=4 * s, fill=col)
    d.polygon(P([(34, 48), (48, 24), (52, 10), (60, 7), (66, 14), (64, 36), (86, 36), (93, 44), (85, 90), (34, 90)]), fill=col)


def bell_layer(size, col, ang):
    S = int(size * SS * 1.6); im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    s = size * SS / 100; ox, oy = S / 2 - 50 * s, S / 2 - 50 * s
    P = lambda pts: [(ox + x * s, oy + y * s) for x, y in pts]
    d.ellipse(P([(44, 6), (56, 18)]), fill=col)
    d.chord(P([(24, 14), (76, 66)]), 180, 360, fill=col)
    d.polygon(P([(24, 40), (76, 40), (83, 74), (17, 74)]), fill=col)
    d.rounded_rectangle(P([(10, 72), (90, 81)]), radius=4 * s, fill=col)
    d.ellipse(P([(41, 80), (59, 94)]), fill=col)
    # pivot at top knob
    return im.rotate(ang, resample=Image.BICUBIC, center=(S / 2, oy + 12 * s))


def cursor_pos(t):
    keys = [(0.0, (W * 0.95, H * 1.05)), (0.9, (W * 0.95, H * 1.05)), (1.45, LIKE_C), (1.8, LIKE_C),
            (2.55, SUB_C), (2.9, SUB_C), (3.65, BELL_C), (4.4, BELL_C), (5.2, (W * 0.88, H * 0.95))]
    for (t0, p0), (t1, p1) in zip(keys, keys[1:]):
        if t <= t1:
            u = smooth(t0, t1, t) if t1 > t0 else 1
            return (p0[0] + (p1[0] - p0[0]) * u, p0[1] + (p1[1] - p0[1]) * u)
    return keys[-1][1]


def draw_cursor(d, p, press):
    x, y = (p[0] + 18) * SS, (p[1] + 22) * SS; k = SS * (0.85 if press else 1.0)
    pts = [(0, 0), (0, 40), (10, 31), (17, 47), (24, 44), (17, 29), (30, 29)]
    d.polygon([(x + a * k * 1.3, y + b * k * 1.3) for a, b in pts], fill=WHITE, outline=(0, 0, 0), width=int(3 * SS))


def frame(t):
    im = Image.new("RGB", (W * SS, H * SS), (8, 11, 18)); d = ImageDraw.Draw(im)
    # background glow
    g = Image.new("L", (W // 8, H // 8), 0); gd = ImageDraw.Draw(g)
    for r in range(60, 0, -4):
        gd.ellipse([W / 16 - r * 3, H / 16 - r * 1.6, W / 16 + r * 3, H / 16 + r * 1.6], fill=int(40 * (1 - r / 60)))
    glow = g.resize((W * SS, H * SS), Image.BILINEAR)
    im = Image.composite(Image.new("RGB", im.size, (40, 60, 80)), im, glow); d = ImageDraw.Draw(im)
    ta = smooth(0.1, 0.6, t)
    d.text((W / 2 * SS, H * 0.30 * SS + (1 - ta) * 30 * SS), "Сподобалось відео?", font=F_TITLE, fill=tuple(int(c * ta) for c in WHITE), anchor="mm")
    d.text((W / 2 * SS, H * 0.38 * SS), "Підпишись, щоб не пропустити нові факти", font=F_SMALL, fill=tuple(int(c * ta * 0.75) for c in WHITE), anchor="mm")
    pop = lambda t0: ease_back((t - t0) / 0.45)
    pressed = lambda tc: tc - 0.05 <= t <= tc + 0.12
    # LIKE
    k = pop(0.25)
    if k > 0:
        liked = t >= CLICK_LIKE; b = 1 + 0.18 * math.exp(-((t - CLICK_LIKE - 0.12) / 0.1) ** 2) if liked else 1
        r = 78 * k * b * (0.92 if pressed(CLICK_LIKE) else 1)
        circle_btn(d, LIKE_C, r, BLUE if liked else (28, 32, 40), outline=None if liked else (120, 125, 135))
        thumb(d, (LIKE_C[0], LIKE_C[1] + 2), 80 * k * b, WHITE)
        if liked:
            u = (t - CLICK_LIKE) / 0.5
            if u < 1:
                for i in range(8):
                    a = i * math.pi / 4; rr = (r + 20 + 50 * u) * SS
                    x0, y0 = LIKE_C[0] * SS + math.cos(a) * rr, LIKE_C[1] * SS + math.sin(a) * rr
                    d.ellipse([x0 - 7 * SS * (1 - u), y0 - 7 * SS * (1 - u), x0 + 7 * SS * (1 - u), y0 + 7 * SS * (1 - u)], fill=BLUE)
    # SUBSCRIBE
    k = pop(0.4)
    if k > 0:
        subbed = t >= CLICK_SUB
        bw, bh = 420 * k, 110 * k
        if pressed(CLICK_SUB): bw *= 0.95; bh *= 0.95
        x, y = SUB_C[0] * SS, SUB_C[1] * SS
        d.rounded_rectangle([x - bw / 2 * SS, y - bh / 2 * SS, x + bw / 2 * SS, y + bh / 2 * SS], radius=bh / 2 * SS, fill=GREY if subbed else RED)
        if k > 0.6:
            d.text((x, y), "ПІДПИСАНО ✓" if subbed else "ПІДПИСАТИСЯ", font=F_BTN, fill=WHITE, anchor="mm")
    # BELL
    k = pop(0.55)
    if k > 0:
        on = t >= CLICK_BELL
        circle_btn(d, BELL_C, 78 * k * (0.92 if pressed(CLICK_BELL) else 1), AMBER if on else (28, 32, 40), outline=None if on else (120, 125, 135))
        ang = 0.0
        if on:
            dt = t - CLICK_BELL; ang = 28 * math.sin(dt * 22) * math.exp(-dt * 2.2)
            u = (dt % 0.6) / 0.6
            if dt < 1.8:
                for side in (-1, 1):
                    for j in range(2):
                        rr = (95 + 22 * j + 20 * u) * SS; a0 = -40 if side > 0 else 180 - 0
                        bx = [BELL_C[0] * SS - rr, BELL_C[1] * SS - rr, BELL_C[0] * SS + rr, BELL_C[1] * SS + rr]
                        start = -35 if side > 0 else 180 + 0
                        d.arc(bx, start=(-30 if side > 0 else 150), end=(30 if side > 0 else 210), fill=tuple(int(c * (1 - u)) for c in AMBER), width=int(5 * SS))
        bl = bell_layer(76 * k, (20, 20, 24) if on else WHITE, ang)
        im.paste(bl, (int(BELL_C[0] * SS - bl.width / 2), int(BELL_C[1] * SS - bl.height / 2 + 2 * SS)), bl)
        d = ImageDraw.Draw(im)
    # cursor
    if 0.9 < t < 5.3:
        draw_cursor(d, cursor_pos(t), any(pressed(c) for c in (CLICK_LIKE, CLICK_SUB, CLICK_BELL)))
    im = im.resize((W, H), Image.LANCZOS)
    a = smooth(0, 0.4, t) * (1 - smooth(DUR - 0.6, DUR, t))
    if a < 1:
        im = Image.eval(im, lambda v: int(v * a))
    return im


def audio(path):
    n = int(DUR * SR); t = np.arange(n) / SR; out = np.zeros(n)
    r = np.random.default_rng(3)
    def add(sig, at, g):
        i = int(at * SR); out[i:i + len(sig)] += sig[:n - i] * g
    tc = np.arange(int(0.04 * SR)) / SR
    click = r.standard_normal(len(tc)) * np.exp(-tc * 180) + np.sin(2 * np.pi * 2200 * tc) * np.exp(-tc * 120)
    for c in (CLICK_LIKE, CLICK_SUB, CLICK_BELL): add(click, c, 0.25)
    tp = np.arange(int(0.25 * SR)) / SR
    pop = np.sin(2 * np.pi * (500 + 900 * tp) * tp) * np.exp(-tp * 25)
    for p in (0.25, 0.4, 0.55): add(pop, p, 0.12)
    add(np.sin(2 * np.pi * (700 + 600 * tp) * tp) * np.exp(-tp * 18), CLICK_LIKE + 0.03, 0.18)
    tb = np.arange(int(2.0 * SR)) / SR
    ding = sum(a * np.sin(2 * np.pi * f * tb) for f, a in [(1318, 1), (2637, 0.5), (3520, 0.3), (1975, 0.25)]) * np.exp(-tb * 2.5)
    add(ding * (1 + 0.3 * np.sin(2 * np.pi * 7 * tb)), CLICK_BELL + 0.02, 0.12)
    add(ding, CLICK_BELL + 0.32, 0.07)
    pad = (np.sin(2 * np.pi * 110 * t) + 0.5 * np.sin(2 * np.pi * 164.8 * t) + 0.4 * np.sin(2 * np.pi * 220 * t)) * 0.035
    out += pad * np.clip(t / 0.6, 0, 1) * np.clip((DUR - t) / 0.8, 0, 1)
    out /= max(1, np.abs(out).max() / 0.9)
    st = np.repeat(out[:, None], 2, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((st * 32767).astype(np.int16).tobytes())


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    wav = os.path.join(OUT, "end.wav"); audio(wav)
    if len(sys.argv) > 2:
        for x in sys.argv[2:]: frame(float(x)).save(os.path.join(OUT, f"end_{x}.jpg"))
        sys.exit()
    mp4 = os.path.join(OUT, "end.mp4")
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-i", wav, "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                          "-ar", "48000", "-shortest", mp4], stdin=subprocess.PIPE)
    for i in range(int(DUR * FPS)):
        p.stdin.write(frame(i / FPS).tobytes())
    p.stdin.close(); p.wait(); print(mp4)
