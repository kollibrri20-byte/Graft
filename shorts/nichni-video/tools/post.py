"""Per-shot looks + overlays for the rendered PNG sequence -> render.mp4 (1080x1920, 24 fps, no audio).

  python3 tools/post.py <project dir> [--from F --to F]

Looks (shots.json "fx"):
  clean   story shots: soft grade, grain, vignette
  phone   night phone footage: lifted blacks, heavy noise, cold tint, phone camera UI with a running timer
  selfie  his own video: phone UI, warmer
  cam     old camcorder night vision: green mono, scanlines, tape noise, PLAY + 03:00 clock
  rew     camcorder rewinding: tracking tears, << REW, the clock running back to 03:00:00
  glitch  camcorder close-up during the whisper: cam + growing glitches
  flash   memory: cold, desaturated, blooming
  black   black
"""
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SANSB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
for p in (MONO, SANS, SANSB):
    if not os.path.exists(p):
        MONO = SANS = SANSB = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

proj = os.path.abspath(sys.argv[1])
meta = json.load(open(os.path.join(proj, "shots.json")))
FPS, END = meta["fps"], meta["end"]
SHOTS = meta["shots"]
args = sys.argv[2:]
F0 = int(args[args.index("--from") + 1]) if "--from" in args else 1
F1 = int(args[args.index("--to") + 1]) if "--to" in args else END
OUT = args[args.index("--out") + 1] if "--out" in args else os.path.join(proj, "render.mp4")

yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
R = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
VIG = np.clip(1.0 - 0.38 * np.clip(R - 0.45, 0, None) ** 1.6, 0, 1)[..., None]
VIG_HARD = np.clip(1.0 - 0.75 * np.clip(R - 0.35, 0, None) ** 1.3, 0, 1)[..., None]
SCAN = (1.0 - 0.18 * ((np.arange(H) // 3) % 2)).astype(np.float32)[:, None, None]
rng = np.random.default_rng(5)
GRAIN = [rng.standard_normal((H // 2, W // 2)).astype(np.float32) for _ in range(8)]


def grain(fr, amt):
    g = GRAIN[fr % 8]
    g = np.repeat(np.repeat(g, 2, 0), 2, 1)
    return g[..., None] * amt


def font(p, s):
    return ImageFont.truetype(p, s)


F_MONO = font(MONO, 54)
F_MONO_S = font(MONO, 40)
F_UI = font(SANSB, 40)
F_UI_S = font(SANS, 30)


def shot_of(fr):
    cur = SHOTS[0]
    for s in SHOTS:
        if s["f0"] <= fr:
            cur = s
    return cur


def load(fr):
    for k in (range(fr, 0, -1) if os.environ.get("POST_PREVIEW") != "1" else []):
        p = os.path.join(proj, "frames", f"{k:05d}.png")
        if os.path.exists(p):
            im = Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS)
            return np.asarray(im).astype(np.float32) / 255.0
    p = os.path.join(proj, "preview", f"f{fr:05d}.png")
    if os.path.exists(p):
        return np.asarray(Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS)).astype(np.float32) / 255.0
    return np.zeros((H, W, 3), np.float32)


def hms(t):
    t = max(0, int(t))
    return f"{t // 3600:02d}:{t // 60 % 60:02d}:{t % 60:02d}"


def text_layer(draws):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for fn in draws:
        fn(d)
    return img


def comp(rgb, layer):
    a = np.asarray(layer).astype(np.float32) / 255.0
    return rgb * (1 - a[..., 3:4]) + a[..., :3] * a[..., 3:4]


def look_clean(x, fr, s):
    lum = x.mean(2, keepdims=True)
    x = x + (np.array([-0.012, 0.0, 0.02]) * (1 - lum)) + np.array([0.015, 0.005, -0.01]) * lum
    x = x * VIG + grain(fr, 0.025)
    return x


def phone_ui(fr, s, selfie=False):
    t = (fr - s["f0"]) / FPS + s.get("timer", 0)

    def draw(d):
        # timer pill top centre
        label = hms(t)[3:] if t < 3600 else hms(t)
        tw = d.textlength(label, font=F_UI)
        x0 = (W - tw) / 2 - 26
        d.rounded_rectangle((x0, 118, x0 + tw + 52, 178), radius=14, fill=(220, 30, 40, 235))
        d.text((x0 + 26, 124), label, font=F_UI, fill=(255, 255, 255, 255))
        # record (stop) button bottom centre
        cx, cy = W // 2, H - 250
        d.ellipse((cx - 72, cy - 72, cx + 72, cy + 72), outline=(255, 255, 255, 230), width=7)
        d.rounded_rectangle((cx - 28, cy - 28, cx + 28, cy + 28), radius=8, fill=(225, 35, 45, 240))
        # small icons
        d.text((70, H - 270), "0.5×" if not selfie else "1×", font=F_UI_S, fill=(255, 255, 255, 210))
        if selfie:
            d.ellipse((W - 150, H - 290, W - 70, H - 210), outline=(255, 255, 255, 200), width=5)
        # corner brackets
        for (ax, ay, sx, sy) in ((60, 240, 1, 1), (W - 60, 240, -1, 1), (60, H - 400, 1, -1), (W - 60, H - 400, -1, -1)):
            d.line((ax, ay, ax + 60 * sx, ay), fill=(255, 255, 255, 140), width=4)
            d.line((ax, ay, ax, ay + 60 * sy), fill=(255, 255, 255, 140), width=4)
    return text_layer([draw])


def look_phone(x, fr, s, selfie=False):
    lum = x.mean(2, keepdims=True)
    if selfie:
        x = np.clip(x * 1.15 + 0.02, 0, 1)
    else:
        x = np.clip((x * 1.9 + 0.035) ** 0.85, 0, 1)
        x = x * 0.75 + lum * 0.25
        x = x * np.array([0.88, 0.97, 1.08])
    x = x + grain(fr, 0.055 if not selfie else 0.03)
    cn = np.repeat(np.repeat(np.random.default_rng(fr).standard_normal((H // 8, W // 8, 3)).astype(np.float32), 8, 0), 8, 1)
    x = x + cn * 0.012
    x = np.clip(x, 0, 1) * (VIG * 0.5 + 0.5)
    return comp(x, phone_ui(fr, s, selfie))


def cam_ui(fr, s, mode):
    def draw(d):
        if mode == "rew":
            prog = (fr - s["f0"]) / max(1, s["f1"] - s["f0"])
            clock = 3 * 3600 + (1 - prog) ** 2 * (4 * 3600 + 17 * 60 + 41)
            d.text((80, 150), "◀◀ REW", font=F_MONO, fill=(240, 240, 240, 255))
        else:
            clock = s.get("clock", 3 * 3600) + (fr - s["f0"]) / FPS
            d.text((80, 150), "▶ PLAY", font=F_MONO, fill=(240, 240, 240, 255))
        d.text((W - 270, 150), "SP", font=F_MONO, fill=(240, 240, 240, 255))
        d.text((80, H - 330), "18.11.2026", font=F_MONO_S, fill=(240, 240, 240, 255))
        d.text((80, H - 270), hms(clock) + (" AM" if clock < 12 * 3600 else " PM"), font=F_MONO, fill=(240, 240, 240, 255))
        d.text((W - 380, H - 270), "CH 1", font=F_MONO_S, fill=(240, 240, 240, 200))
    return text_layer([draw])


def look_cam(x, fr, s, mode="cam"):
    lum = x[..., 0] * 0.3 + x[..., 1] * 0.59 + x[..., 2] * 0.11
    lum = np.clip(lum * 1.6 + 0.04, 0, 1) ** 0.8
    r = np.random.default_rng(fr * 7 + 1)
    # soft blur (cheap camcorder optics) by down/up sampling
    small = Image.fromarray((lum * 255).astype(np.uint8)).resize((W // 3, H // 3), Image.BILINEAR).resize((W, H), Image.BILINEAR)
    lum = np.asarray(small).astype(np.float32) / 255.0
    # horizontal line jitter
    shift = np.zeros(H, np.int32)
    if mode in ("rew", "glitch"):
        k = (fr - s["f0"]) / max(1, s["f1"] - s["f0"])
        nb = 6 if mode == "rew" else int(1 + 7 * k * (r.random() < 0.35 + 0.5 * k))
        for _ in range(nb):
            y0 = r.integers(0, H)
            hgt = r.integers(10, 120 if mode == "rew" else 60)
            shift[y0:y0 + hgt] = r.integers(-60, 60) if mode == "rew" else r.integers(-40, 40)
    shift += (r.standard_normal(H) * 1.5).astype(np.int32)
    idx = (np.arange(W)[None, :] - shift[:, None]) % W
    lum = lum[np.arange(H)[:, None], idx]
    lum = lum + r.standard_normal((H, W)).astype(np.float32) * 0.07
    if mode == "rew":
        band = (fr * 37) % H
        lum[band:band + 70] = lum[band:band + 70] * 0.4 + r.random((min(70, H - band), W)).astype(np.float32) * 0.6
        lum[-90:] = lum[-90:] * 0.3 + r.random((90, W)).astype(np.float32) * 0.5
    x = lum[..., None] * np.array([0.42, 1.0, 0.50], np.float32)
    x = x * SCAN * VIG_HARD
    if mode == "glitch" and r.random() < 0.25:
        x[..., 0] = np.roll(x[..., 0], r.integers(6, 20), 1)
        x[..., 2] = np.roll(x[..., 2], -r.integers(6, 20), 1)
    x = np.clip(x, 0, 1)
    return comp(x, cam_ui(fr, s, mode))


def look_flash(x, fr, s):
    lum = x.mean(2, keepdims=True)
    x = x * 0.35 + lum * 0.65
    x = x * np.array([0.85, 0.95, 1.12]) * 1.25 + 0.03
    blur = np.asarray(Image.fromarray((np.clip(x, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(18))).astype(np.float32) / 255
    x = x + blur * 0.35
    x = x * VIG_HARD + grain(fr, 0.04)
    return x


def frame(fr):
    s = shot_of(fr)
    fx = s["fx"]
    if fx == "black":
        return np.zeros((H, W, 3), np.float32)
    x = load(fr)
    if fx == "phone":
        x = look_phone(x, fr, s)
    elif fx == "selfie":
        x = look_phone(x, fr, s, selfie=True)
    elif fx in ("cam", "rew", "glitch"):
        x = look_cam(x, fr, s, fx)
    elif fx == "flash":
        x = look_flash(x, fr, s)
    else:
        x = look_clean(x, fr, s)
    # 2-frame dip to black on the hard "hit" cuts is handled by the cut itself; keep it clean
    return np.clip(x, 0, 1)


def main():
    if "--still" in args:
        for fr in [int(a) for a in args[args.index("--still") + 1:]]:
            Image.fromarray((frame(fr) * 255).astype(np.uint8)).save(os.path.join(proj, "preview", f"post_{fr:05d}.jpg"), quality=88)
        return
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                           "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", OUT],
                          stdin=subprocess.PIPE)
    for fr in range(F0, F1 + 1):
        ff.stdin.write((frame(fr) * 255).astype(np.uint8).tobytes())
        if fr % 200 == 0:
            print("post", fr, "/", F1, flush=True)
    ff.stdin.close()
    ff.wait()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
