#!/usr/bin/env python3
"""
«Село, якого немає на жодній карті» — збирання слайд-шоу з 119 кадрів.

Бере картинки frames/001.jpg … frames/119.jpg і файл озвучки, ставить кожен
кадр під своє речення й рендерить 1920×1080 / 30 fps відео з рухом камери
(наїзд, від'їзд, панорами, нахили, «ручна» камера в погоні), мерехтінням
світла (свічки, ліхтарі), плавними переходами, затемненням на початку
розділів, віньєткою й плівковим зерном, тихим ембієнтом під голосом.

Використання:
    python3 assemble.py                         # усе за замовчуванням
    python3 assemble.py --voice my_voice.mp3    # інший файл озвучки
    python3 assemble.py --timings out/timings.csv   # ручні таймінги
    python3 assemble.py --scale 0.5             # швидкий чорновий рендер
    python3 assemble.py --preview 12 95.5       # PNG-кадри на 12 с і 95.5 с

Якщо озвучки немає — тривалість кожного кадру оцінюється за довжиною
речення (2–5 с). Якщо картинки немає — малюється заглушка з номером і
текстом, тож відео можна зібрати й перевірити ще до генерації картинок.

Після кожного запуску пишеться out/timings.csv (номер, початок, кінець,
текст). Якщо автоматичне вирівнювання десь промахнулося, виправ час у
цьому файлі й запусти з --timings out/timings.csv.
"""
import argparse
import csv
import math
import os
import re
import shutil
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

try:  # OpenCV у ~20 разів швидший за PIL для зсуву/масштабу кадру
    import cv2
except ImportError:
    cv2 = None

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
W, H = 1920, 1080
XFADE = 0.5          # звичайний перехід між кадрами, с
CHAPTER_DIP = 1.2    # перехід через чорне перед розділом, с
INTRO_FADE = 1.2
OUTRO_HOLD = 2.5     # останній кадр після голосу, с
OUTRO_FADE = 2.0
SR = 48000
VOWELS = set("аеєиіїоуюяАЕЄИІЇОУЮЯ")


# --------------------------------------------------------------------------
# Сценарій
# --------------------------------------------------------------------------
def load_shots(path):
    shots = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            num, text, prompt = [p.strip() for p in line.split("|", 2)]
            shots.append({"num": int(num), "text": text, "prompt": prompt})
    for i, s in enumerate(shots):
        assert s["num"] == i + 1, f"кадр {s['num']} стоїть на місці {i + 1}"
        s["chapter"] = s["text"].startswith("Розділ")
    return shots


def syllables(text):
    n = sum(ch in VOWELS for ch in text)
    n += 2 * text.count("...") + text.count("—") + text.count(".") * 0.5
    return max(n, 1)


# --------------------------------------------------------------------------
# Таймінги
# --------------------------------------------------------------------------
def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def detect_silences(path, noise_db=-35, min_dur=0.18):
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
         f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    sil = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        sil.append((s, e))
    return sil


def align_to_voice(shots, voice):
    """Ділить запис на 119 речень.

    Запис розбивається паузами на шматки мовлення; DP групує їх у речення так,
    щоб тривалість кожного речення була пропорційна кількості складів, а межі
    речень падали на довші паузи (коми всередині речення дають коротші).
    """
    dur = probe_duration(voice)
    sil = detect_silences(voice)
    speech_start, speech_end = 0.0, dur
    if sil and sil[0][0] < 0.05 and sil[0][1]:
        speech_start = sil[0][1]
    if sil and sil[-1][1] is None:
        speech_end = sil[-1][0]
    gaps = [(s, e) for s, e in sil
            if e is not None and s > speech_start + 0.05 and e < speech_end - 0.05]
    # шматки мовлення між паузами
    seg_a = [speech_start] + [e for _, e in gaps]
    seg_b = [s for s, _ in gaps] + [speech_end]
    gap_len = [e - s for s, e in gaps]
    M, K = len(seg_a), len(shots)
    syl = np.array([sum(ch in VOWELS for ch in s["text"]) or 1 for s in shots], float)
    if M < K:
        print(f"  ! шматків мовлення {M}, речень {K}: таймінги за складами")
        w = syl + 1.2
        cum = np.cumsum(w)[:-1] / w.sum()
        bounds = list(speech_start + (speech_end - speech_start) * cum)
    else:
        spoken = np.array(seg_b) - np.array(seg_a)
        rate = spoken.sum() / syl.sum()          # с на склад
        csum = np.concatenate([[0], np.cumsum(spoken)])
        med_gap = float(np.median(gap_len)) if gap_len else 0.3
        L = 8                                     # макс. шматків на речення
        INF = 1e18
        # cost[k][m] — перші k речень покривають перші m шматків
        cost = np.full((K + 1, M + 1), INF)
        back = np.zeros((K + 1, M + 1), int)
        cost[0][0] = 0
        for k in range(1, K + 1):
            exp_d = syl[k - 1] * rate
            lo = max(k, M - (K - k) * L)
            for m in range(lo, min(M - (K - k), k * L) + 1):
                best, arg = INF, -1
                for j in range(max(k - 1, m - L), m):
                    if cost[k - 1][j] >= INF:
                        continue
                    d = csum[m] - csum[j]
                    c = cost[k - 1][j] + math.log((d + 0.3) / (exp_d + 0.3)) ** 2
                    # внутрішні паузи речення мають бути короткими
                    for g in range(j, m - 1):
                        c += 0.5 * max(0.0, gap_len[g] / med_gap - 1.0)
                    if c < best:
                        best, arg = c, j
                if arg >= 0:
                    # межа після речення — бажано довга пауза
                    if m < M:
                        best += 0.3 * max(0.0, 1.0 - gap_len[m - 1] / med_gap)
                    cost[k][m], back[k][m] = best, arg
        cuts, m = [], M
        for k in range(K, 0, -1):
            j = back[k][m]
            cuts.append(j)
            m = j
        cuts = cuts[::-1][1:]                     # індекси першого шматка речень 2..K
        # ріжемо в паузі, трохи раніше за початок наступного речення
        bounds = [max((seg_b[c - 1] + seg_a[c]) / 2, seg_a[c] - 0.15) for c in cuts]
    starts = [0.0] + bounds
    ends = bounds + [speech_end + OUTRO_HOLD]
    return starts, ends, dur


def estimate_without_voice(shots):
    t, starts, ends = 0.6, [], []
    for s in shots:
        d = 0.9 + 0.17 * syllables(s["text"]) + (0.6 if s["chapter"] else 0)
        d = min(max(d, 2.0), 5.0)
        starts.append(t)
        t += d
        ends.append(t)
    starts[0] = 0.0
    ends[-1] += OUTRO_HOLD
    return starts, ends, None


def read_timings(path, shots):
    starts, ends = [], []
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(shots), "у timings.csv має бути 119 рядків"
    for r in rows:
        starts.append(float(r["start"]))
        ends.append(float(r["end"]))
    return starts, ends


def write_timings(path, shots, starts, ends):
    with open(path, "w", encoding="utf-8", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["num", "start", "end", "dur", "text"])
        for s, a, b in zip(shots, starts, ends):
            wr.writerow([f"{s['num']:03d}", f"{a:.2f}", f"{b:.2f}",
                         f"{b - a:.2f}", s["text"]])


# --------------------------------------------------------------------------
# Рух камери й світло
# --------------------------------------------------------------------------
LIGHT_WORDS = ("candle", "lantern", "flame", "flashlight", "fire")
RUN_SHOTS = set(range(73, 84))


def plan_motion(shots):
    rng = np.random.default_rng(119)
    cycle = ["push_in", "pan_r", "pull_out", "tilt_up", "pan_l", "push_diag",
             "tilt_down", "pull_diag"]
    prev = None
    k = 0
    for s in shots:
        p = s["prompt"].lower()
        if "extreme close-up" in p or "macro" in p:
            m = "push_slow"
        elif "aerial" in p and "top-down" in p:
            m = "pull_out"
        elif "aerial" in p:
            m = "pan_r" if prev != "pan_r" else "pan_l"
        elif "low-angle" in p:
            m = "tilt_up"
        elif "high-angle" in p:
            m = "pull_out"
        else:
            m = cycle[k % len(cycle)]
            k += 1
        if m == prev:
            m = cycle[k % len(cycle)]
            k += 1
        prev = m
        s["motion"] = m
        s["dutch"] = ("dutch" in p) * rng.choice([-1, 1])
        s["shake"] = s["num"] in RUN_SHOTS
        s["flicker"] = 0.07 if any(w in p for w in LIGHT_WORDS) else 0.018
        s["seed"] = int(rng.integers(1 << 30))
        s["jit"] = rng.uniform(-0.04, 0.04, 2)


def camera(s, u):
    """u ∈ [0,1] — прогрес кадру. Повертає (zoom, cx, cy, angle_deg)."""
    p = 0.3 * u + 0.7 * (u * u * (3 - 2 * u))
    m = s["motion"]
    jx, jy = s["jit"]
    z0, z1, c0, c1 = 1.10, 1.10, (0.5, 0.5), (0.5, 0.5)
    if m == "push_in":
        z0, z1, c0, c1 = 1.03, 1.17, (0.5, 0.5), (0.5 + jx, 0.5 + jy)
    elif m == "push_slow":
        z0, z1 = 1.04, 1.13
    elif m == "push_diag":
        z0, z1, c0, c1 = 1.05, 1.16, (0.44, 0.54), (0.56, 0.46)
    elif m == "pull_out":
        z0, z1, c0, c1 = 1.18, 1.03, (0.5 + jx, 0.5 + jy), (0.5, 0.5)
    elif m == "pull_diag":
        z0, z1, c0, c1 = 1.17, 1.05, (0.56, 0.45), (0.47, 0.52)
    elif m in ("pan_r", "pan_l"):
        z0 = z1 = 1.15
        d = (1 - 1 / 1.15) / 2 * 0.85
        a, b = (0.5 - d, 0.5 + d) if m == "pan_r" else (0.5 + d, 0.5 - d)
        c0, c1 = (a, 0.5 + jy), (b, 0.5 - jy)
    elif m in ("tilt_up", "tilt_down"):
        z0, z1 = 1.12, 1.15
        d = (1 - 1 / 1.15) / 2 * 0.85
        a, b = (0.5 + d, 0.5 - d) if m == "tilt_up" else (0.5 - d, 0.5 + d)
        c0, c1 = (0.5 + jx, a), (0.5 - jx, b)
    z = z0 + (z1 - z0) * p
    cx = c0[0] + (c1[0] - c0[0]) * p
    cy = c0[1] + (c1[1] - c0[1]) * p
    ang = s["dutch"] * (0.8 + 1.4 * p)
    return z, cx, cy, ang


def noise1(t, seed, freqs):
    r = np.random.default_rng(seed)
    ph = r.uniform(0, 2 * np.pi, len(freqs))
    return sum(math.sin(2 * np.pi * f * t + q) for f, q in zip(freqs, ph)) / len(freqs)


# --------------------------------------------------------------------------
# Картинки
# --------------------------------------------------------------------------
PALETTE = {  # фон заглушок за розділами
    0: ((24, 34, 40), (70, 80, 72)), 1: ((40, 44, 38), (110, 104, 80)),
    2: ((46, 30, 16), (150, 98, 46)), 3: ((40, 26, 14), (140, 90, 40)),
    4: ((12, 20, 40), (60, 80, 120)), 5: ((14, 18, 34), (90, 70, 50)),
    6: ((20, 16, 30), (80, 70, 100)), 7: ((50, 44, 52), (170, 150, 140)),
}


def chapter_index(shots, i):
    return sum(1 for s in shots[: i + 1] if s["chapter"])


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in ("/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "C:/Windows/Fonts"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def placeholder(s, chap):
    a, b = PALETTE.get(chap, PALETTE[0])
    y = np.linspace(0, 1, H)[:, None, None]
    x = np.linspace(0, 1, W)[None, :, None]
    base = np.array(a, float) * (1 - y) + np.array(b, float) * y
    r = np.random.default_rng(s["num"])
    for _ in range(9):  # м'які плями, щоб було видно рух камери
        cx, cy, rad = r.uniform(0, 1), r.uniform(0, 1), r.uniform(0.08, 0.25)
        g = np.exp(-(((x - cx) * 16 / 9) ** 2 + (y - cy) ** 2) / rad ** 2)
        base = base + g * r.uniform(15, 45)
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    d.text((W / 2, H * 0.36), f"{s['num']:03d}", font=font(220, True),
           fill=(235, 225, 205), anchor="mm")
    words, lines, cur = s["text"].split(), [], ""
    for w_ in words:
        if len(cur) + len(w_) > 38:
            lines.append(cur)
            cur = w_
        else:
            cur = (cur + " " + w_).strip()
    lines.append(cur)
    for i, ln in enumerate(lines):
        d.text((W / 2, H * 0.6 + i * 64), ln, font=font(52), fill=(225, 215, 195), anchor="mm")
    d.text((W / 2, H * 0.8), "заглушка — тут буде картинка " + f"{s['num']:03d}.jpg",
           font=font(30), fill=(170, 160, 150), anchor="mm")
    return img


def find_image(frames_dir, num):
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".JPG", ".JPEG", ".PNG"):
        for name in (f"{num:03d}{ext}", f"{num}{ext}"):
            p = os.path.join(frames_dir, name)
            if os.path.exists(p):
                return p
    return None


# --------------------------------------------------------------------------
# Рендер
# --------------------------------------------------------------------------
G = {}  # стан воркера


def worker_init(cfg):
    G.update(cfg)
    G["cache"] = {}
    ow, oh = G["ow"], G["oh"]
    yy, xx = np.mgrid[0:oh, 0:ow].astype(np.float32)
    r = np.sqrt(((xx - ow / 2) / (ow / 2)) ** 2 * 0.8 + ((yy - oh / 2) / (oh / 2)) ** 2 * 0.8)
    G["vign"] = (1 - 0.42 * np.clip(r - 0.45, 0, None) ** 1.6)[:, :, None].astype(np.float32)
    rng = np.random.default_rng(7)
    G["grain"] = [rng.normal(0, 3.0, (oh, ow, 1)).astype(np.float32) for _ in range(6)]


def source(i):
    c = G["cache"]
    if i in c:
        return c[i]
    if len(c) > 6:
        c.pop(next(iter(c)))
    s = G["shots"][i]
    p = find_image(G["frames"], s["num"])
    img = Image.open(p).convert("RGB") if p else placeholder(s, chapter_index(G["shots"], i))
    # cover-кроп до 16:9 і запас роздільності під наїзд
    tw, th = int(G["ow"] * 1.2), int(G["oh"] * 1.2)
    sw, sh = img.size
    sc = max(tw / sw, th / sh)
    img = img.resize((max(tw, round(sw * sc)), max(th, round(sh * sc))), Image.LANCZOS)
    l, t = (img.width - tw) // 2, (img.height - th) // 2
    img = img.crop((l, t, l + tw, t + th))
    if cv2 is not None:
        img = np.ascontiguousarray(np.asarray(img))
    c[i] = img
    return img


def shot_frame(i, t):
    s = G["shots"][i]
    a, b = G["vis"][i]
    u = (t - a) / max(b - a, 1e-6)
    z, cx, cy, ang = camera(s, min(max(u, 0), 1))
    if s["shake"]:
        cx += 0.006 * noise1(t, s["seed"], [1.7, 2.9, 4.3])
        cy += 0.006 * noise1(t, s["seed"] + 1, [1.3, 3.1, 5.2])
        ang += 0.5 * noise1(t, s["seed"] + 2, [0.9, 2.2])
    img = source(i)
    sw, sh = (img.shape[1], img.shape[0]) if cv2 is not None else img.size
    ow, oh = G["ow"], G["oh"]
    vw = sw / z            # видиме вікно в пікселях джерела
    k = vw / ow
    # тримаємо вікно в межах картинки (з урахуванням нахилу)
    marg = 1 + abs(math.radians(ang)) * 1.0
    half_w, half_h = vw / 2 * marg, (vw * oh / ow) / 2 * marg
    px = min(max(cx * sw, half_w), sw - half_w)
    py = min(max(cy * sh, half_h), sh - half_h)
    th = math.radians(ang)
    ca, sa = math.cos(th) * k, math.sin(th) * k
    # x_src = ca*(x-ow/2) - sa*(y-oh/2) + px ; y_src = sa*(x-ow/2) + ca*(y-oh/2) + py
    data = (ca, -sa, px - ca * ow / 2 + sa * oh / 2,
            sa, ca, py - sa * ow / 2 - ca * oh / 2)
    if cv2 is not None:
        m = np.array(data, np.float64).reshape(2, 3)
        arr = cv2.warpAffine(img, m, (ow, oh), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                             borderMode=cv2.BORDER_REFLECT).astype(np.float32)
    else:
        out = img.transform((ow, oh), Image.AFFINE, data, resample=Image.BICUBIC)
        arr = np.asarray(out, np.float32)
    fl = s["flicker"]
    f = 1 + fl * (0.6 * noise1(t, s["seed"] + 3, [5.3, 8.9, 13.1])
                  + 0.4 * noise1(t, s["seed"] + 4, [0.7, 1.9]))
    return arr * f


def frame_at(fi):
    t = fi / FPS
    vis = G["vis"]
    active = [i for i, (a, b) in enumerate(vis) if a - 1e-9 <= t < b]
    if not active:
        active = [len(vis) - 1]
    if len(active) == 1:
        arr = shot_frame(active[0], t)
    else:
        i, j = active[0], active[-1]
        a = vis[j][0]
        xa, xb = G["xf"][j]
        w = min(max((t - xa) / max(xb - xa, 1e-6), 0), 1)
        if G["shots"][j]["chapter"]:      # перехід через чорне
            if w < 0.5:
                arr = shot_frame(i, t) * (1 - w * 2) ** 2
            else:
                arr = shot_frame(j, t) * ((w - 0.5) * 2) ** 1.5
        else:
            w = w * w * (3 - 2 * w)
            arr = shot_frame(i, t) * (1 - w) + shot_frame(j, t) * w
    # загальні фейди
    g = 1.0
    if t < INTRO_FADE:
        g = (t / INTRO_FADE) ** 1.5
    end = G["total"]
    if t > end - OUTRO_FADE:
        g = min(g, max(end - t, 0) / OUTRO_FADE) ** 1.5
    arr = arr * G["vign"] * g + G["grain"][fi % len(G["grain"])]
    return np.clip(arr, 0, 255).astype(np.uint8)


def render_chunk(args):
    f0, f1, path = args
    ow, oh = G["ow"], G["oh"]
    p = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{ow}x{oh}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
         "-preset", "medium", "-crf", str(G["crf"]), "-pix_fmt", "yuv420p", path],
        stdin=subprocess.PIPE)
    for fi in range(f0, f1):
        p.stdin.write(frame_at(fi).tobytes())
    p.stdin.close()
    p.wait()
    return path


# --------------------------------------------------------------------------
# Звук
# --------------------------------------------------------------------------
def ambient(total, chapter_times, path):
    n = int(total * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(3)

    def lp(x, hz):
        return sosfilt(butter(2, hz, fs=SR, output="sos"), x)

    wind = lp(rng.standard_normal(n), 380) * (0.6 + 0.4 * np.sin(2 * np.pi * t / 23.0))
    drone = (np.sin(2 * np.pi * 55 * t) * 0.5 + np.sin(2 * np.pi * 82.4 * t + 1) * 0.3
             + np.sin(2 * np.pi * 110.3 * t) * 0.12) * (0.7 + 0.3 * np.sin(2 * np.pi * t / 17.0))
    x = 0.55 * wind / (np.abs(wind).max() + 1e-9) + 0.45 * drone
    for ct in chapter_times:  # глухий удар на початку розділу
        k = (t >= ct) & (t < ct + 3)
        tt = t[k] - ct
        x[k] += 1.4 * np.sin(2 * np.pi * (48 - 10 * tt) * tt) * np.exp(-tt * 1.6)
    fade = np.minimum(1, np.minimum(t / 3.0, (total - t) / 3.0)).clip(0, 1)
    x = x * fade
    x = x / (np.abs(x).max() + 1e-9) * 0.5
    st = np.stack([x, np.roll(x, 900)], 1)
    wavfile.write(path, SR, (st * 32767).astype(np.int16))


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default=os.path.join(HERE, "shots.txt"))
    ap.add_argument("--frames", default=os.path.join(HERE, "frames"))
    ap.add_argument("--voice", default=None)
    ap.add_argument("--timings", default=None)
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--no-ambient", action="store_true")
    ap.add_argument("--preview", type=float, nargs="*")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    shots = load_shots(a.shots)
    plan_motion(shots)

    voice = a.voice
    if voice is None:
        for ext in ("wav", "mp3", "m4a", "ogg", "flac"):
            p = os.path.join(HERE, f"voice.{ext}")
            if os.path.exists(p):
                voice = p
                break
    if a.timings:
        starts, ends = read_timings(a.timings, shots)
        print(f"таймінги з {a.timings}")
    elif voice:
        print(f"озвучка: {voice} — шукаю межі речень")
        starts, ends, _ = align_to_voice(shots, voice)
    else:
        print("озвучки немає — тривалості за довжиною речень")
        starts, ends, _ = estimate_without_voice(shots)
    write_timings(os.path.join(a.out, "timings.csv"), shots, starts, ends)

    # видимість кадрів з перекриттям на переходи
    vis, xf = [], []
    for i in range(len(shots)):
        x = CHAPTER_DIP if shots[i]["chapter"] and i else XFADE
        xa = starts[i] - x / 2 if i else 0.0
        xb = starts[i] + x / 2 if i else 0.0
        xf.append((xa, xb))
    for i in range(len(shots)):
        a0 = xf[i][0]
        b0 = xf[i + 1][1] if i + 1 < len(shots) else ends[i]
        vis.append((a0, b0))
    total = ends[-1]
    durs = np.diff(starts + [ends[-1]])
    missing = [s["num"] for s in shots if not find_image(a.frames, s["num"])]
    print(f"тривалість {total / 60:.1f} хв, кадр {durs.min():.1f}–{durs.max():.1f} с "
          f"(сер. {durs.mean():.1f}); без картинки: {len(missing)}")

    ow, oh = int(round(W * a.scale)) // 2 * 2, int(round(H * a.scale)) // 2 * 2
    cfg = dict(shots=shots, frames=a.frames, vis=vis, xf=xf, total=total,
               ow=ow, oh=oh, crf=a.crf)

    if a.preview is not None:
        worker_init(cfg)
        for t in a.preview:
            p = os.path.join(a.out, f"preview_{t:07.2f}.png")
            Image.fromarray(frame_at(int(t * FPS))).save(p)
            print(p)
        return

    nf = int(math.ceil(total * FPS))
    chunk = max(FPS * 10, nf // (a.workers * 4))
    tmp = os.path.join(a.out, "chunks")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    jobs = [(f, min(f + chunk, nf), os.path.join(tmp, f"c{k:04d}.mp4"))
            for k, f in enumerate(range(0, nf, chunk))]
    print(f"рендер {nf} кадрів {ow}×{oh} у {len(jobs)} шматках…")
    done = 0
    with Pool(a.workers, initializer=worker_init, initargs=(cfg,)) as pool:
        for _ in pool.imap_unordered(render_chunk, jobs):
            done += 1
            print(f"  {done}/{len(jobs)}", end="\r", flush=True)
    print()
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        for _, _, p in jobs:
            f.write(f"file '{os.path.abspath(p)}'\n")
    video = os.path.join(a.out, "video_only.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c", "copy", video], check=True)

    final = os.path.join(a.out, "selo.mp4")
    inputs, filt, maps = ["-i", video], [], []
    n_in = 1
    if voice:
        inputs += ["-i", voice]
        filt.append(f"[{n_in}:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample={SR},"
                    f"aformat=channel_layouts=stereo[v]")
        n_in += 1
    if not a.no_ambient:
        amb = os.path.join(a.out, "ambient.wav")
        ambient(total, [starts[i] for i, s in enumerate(shots) if s["chapter"]], amb)
        inputs += ["-i", amb]
        filt.append(f"[{n_in}:a]volume={'-24dB' if voice else '-14dB'}[m]")
        n_in += 1
    if voice and not a.no_ambient:
        filt.append("[v]asplit[v1][v2];[m][v1]sidechaincompress=threshold=0.05:"
                    "ratio=4:release=600[d];[d][v2]amix=inputs=2:normalize=0,"
                    "alimiter=limit=0.95[a]")
    elif voice:
        filt.append("[v]anull[a]")
    elif not a.no_ambient:
        filt.append("[m]anull[a]")
    if filt:
        maps = ["-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[a]",
                "-c:a", "aac", "-b:a", "192k"]
    else:
        maps = ["-map", "0:v"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, *maps, "-c:v", "copy",
                    "-t", f"{total:.3f}", "-movflags", "+faststart", final], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    for p in (video, os.path.join(a.out, "ambient.wav")):
        if os.path.exists(p):
            os.remove(p)
    print(f"готово: {final}")


if __name__ == "__main__":
    sys.exit(main())
